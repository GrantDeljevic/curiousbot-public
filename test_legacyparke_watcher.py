import unittest
from datetime import datetime
from io import BytesIO
from urllib.error import HTTPError
from unittest.mock import patch

from legacyparke_watcher import (
    ChangeSet,
    EMPTY_OBSERVATION_MARKER,
    LegacyParkeDataError,
    RealPageAccessBlockedError,
    SHEET_HEADERS,
    UnitRent,
    _detect_changes,
    _format_summary,
    _last_seen_units,
    _latest_units,
    _realpage_get,
    fetch_relevant_units,
)


def row(
    observed_at,
    unit_name,
    external_id,
    rent,
    floorplan_name="2 Bed 2 Bath",
    sqft="1008",
    availability_date="2026-06-06",
    last_move_in_date="2026-08-05",
    rent_per_sqft="$1.36",
):
    return [
        observed_at,
        floorplan_name,
        sqft,
        unit_name,
        external_id,
        availability_date,
        last_move_in_date,
        rent,
        rent_per_sqft,
    ]


def unit(unit_name, external_id, price, floorplan_name="2 Bed 2 Bath", sqft=1008, beds=2):
    return UnitRent(
        floorplan_id=1,
        floorplan_name=floorplan_name,
        beds=beds,
        baths="2",
        sqft=sqft,
        unit_id=1,
        external_id=external_id,
        unit_name=unit_name,
        availability_date="2026-06-06",
        last_move_in_date="2026-08-05",
        price=price,
        formatted_price=f"${price:,.0f}",
    )


def urllib_error(code, body):
    return HTTPError("https://example.test", code, "error", {}, BytesIO(body.encode("utf-8")))


def empty_snapshot(observed_at):
    return [
        observed_at,
        EMPTY_OBSERVATION_MARKER,
        "",
        "",
        "",
        "",
        "",
        "",
        "",
    ]


class LegacyParkeWatcherTests(unittest.TestCase):
    def test_latest_snapshot_uses_datetime_not_string_sorting(self):
        cells = [
            SHEET_HEADERS,
            row("2026-05-04 9:47:38", "2425", "14634015", "$1,366"),
            row("2026-05-04 12:47:33", "2422", "14634048", "$1,496"),
        ]

        latest = _latest_units(cells)

        self.assertEqual(set(latest), {"2422"})
        self.assertEqual(latest["2422"].unit_name, "2422")

    def test_seen_unit_is_not_reported_new_again(self):
        cells = [
            SHEET_HEADERS,
            row("2026-05-04 11:47:29", "2428", "14634071", "$1,351"),
            row("2026-05-04 12:47:33", "2422", "14634048", "$1,496"),
        ]
        previous = _last_seen_units(cells)
        latest = _latest_units(cells)

        changes = _detect_changes(
            [unit("2428", "14634071", 1351), unit("2422", "14634048", 1496)],
            previous,
            latest,
            datetime(2026, 5, 6, 12, 0, 0),
        )

        self.assertEqual(changes.new_units, [])

    def test_removed_unit_is_not_reported_again_after_absent_snapshot(self):
        cells = [
            SHEET_HEADERS,
            row("2026-05-04 11:47:29", "2425", "14634015", "$1,366"),
            row("2026-05-04 12:47:33", "2422", "14634048", "$1,496"),
        ]
        previous = _last_seen_units(cells)
        latest = _latest_units(cells)

        changes = _detect_changes(
            [unit("2422", "14634048", 1496)],
            previous,
            latest,
            datetime(2026, 5, 6, 12, 0, 0),
        )

        self.assertEqual(changes.removed_units, [])

    def test_removed_unit_is_reported_when_present_in_latest_snapshot(self):
        cells = [
            SHEET_HEADERS,
            row("2026-05-04 12:47:33", "2425", "14634015", "$1,366"),
            row("2026-05-04 12:47:33", "2422", "14634048", "$1,496"),
        ]
        previous = _last_seen_units(cells)
        latest = _latest_units(cells)

        changes = _detect_changes(
            [unit("2422", "14634048", 1496)],
            previous,
            latest,
            datetime(2026, 5, 6, 12, 0, 0),
        )

        self.assertEqual([removed.unit_name for removed in changes.removed_units], ["2425"])

    def test_first_empty_snapshot_reports_removed_unit(self):
        cells = [
            SHEET_HEADERS,
            row(
                "2026-05-04 12:47:33",
                "1597",
                "14634057",
                "$1,331",
                floorplan_name="3 Bed 2 Bath",
                sqft="1186",
            ),
        ]
        previous = _last_seen_units(cells)
        latest = _latest_units(cells)

        changes = _detect_changes(
            [],
            previous,
            latest,
            datetime(2026, 5, 6, 12, 0, 0),
            watched_beds=(3,),
        )

        self.assertEqual([removed.unit_name for removed in changes.removed_units], ["1597"])

    def test_empty_snapshot_silences_repeated_removed_alert(self):
        cells = [
            SHEET_HEADERS,
            row(
                "2026-05-04 12:47:33",
                "1597",
                "14634057",
                "$1,331",
                floorplan_name="3 Bed 2 Bath",
                sqft="1186",
            ),
            empty_snapshot("2026-05-04 13:47:33"),
        ]
        previous = _last_seen_units(cells)
        latest = _latest_units(cells)

        changes = _detect_changes(
            [],
            previous,
            latest,
            datetime(2026, 5, 6, 12, 0, 0),
            watched_beds=(3,),
        )

        self.assertEqual(latest, {})
        self.assertIn("1597", previous)
        self.assertEqual(changes.removed_units, [])

    def test_compact_empty_snapshot_from_sheets_silences_repeated_removed_alert(self):
        cells = [
            SHEET_HEADERS,
            row(
                "2026-05-04 12:47:33",
                "1597",
                "14634057",
                "$1,331",
                floorplan_name="3 Bed 2 Bath",
                sqft="1186",
            ),
            ["2026-05-04 13:47:33", EMPTY_OBSERVATION_MARKER],
        ]
        previous = _last_seen_units(cells)
        latest = _latest_units(cells)

        changes = _detect_changes(
            [],
            previous,
            latest,
            datetime(2026, 5, 6, 12, 0, 0),
            watched_beds=(3,),
        )

        self.assertEqual(latest, {})
        self.assertEqual(changes.removed_units, [])

    def test_unwatched_bed_is_not_reported_removed(self):
        cells = [
            SHEET_HEADERS,
            row("2026-05-04 12:47:33", "1744", "14633987", "$1,406"),
            row(
                "2026-05-04 12:47:33",
                "1597",
                "14634057",
                "$1,331",
                floorplan_name="3 Bed 2 Bath",
                sqft="1186",
            ),
        ]
        previous = _last_seen_units(cells)
        latest = _latest_units(cells)

        changes = _detect_changes(
            [unit("1597", "14634057", 1331, floorplan_name="3 Bed 2 Bath", sqft=1186)],
            previous,
            latest,
            datetime(2026, 5, 6, 12, 0, 0),
            watched_beds=(3,),
        )

        self.assertEqual(changes.removed_units, [])

    def test_three_bed_switch_status_change_is_reported(self):
        cells = [
            SHEET_HEADERS,
            row(
                "2026-05-06 17:35:50",
                "1597",
                "14634057",
                "$1,331",
                floorplan_name="3 Bed 2 Bath",
                sqft="1186",
                availability_date="2026-05-01",
            ),
            row(
                "2026-05-06 17:35:50",
                "1956",
                "14634060",
                "$1,331",
                floorplan_name="3 Bed 2 Bath",
                sqft="1186",
                availability_date="2026-03-30",
            ),
        ]
        previous = _last_seen_units(cells)
        latest = _latest_units(cells)

        changes = _detect_changes(
            [
                unit("1597", "14634057", 1331, floorplan_name="3 Bed 2 Bath", sqft=1186),
                unit("1956", "14634060", 1331, floorplan_name="3 Bed 2 Bath", sqft=1186),
            ],
            previous,
            latest,
            datetime(2026, 6, 25, 12, 0, 0),
        )

        self.assertEqual(
            [(decision.unit_name, old, decision.status) for decision, old in changes.switch_status_changes],
            [("1597", "WAIT", "SWITCH"), ("1956", "WAIT", "SWITCH")],
        )

    def test_summary_compares_current_prices_to_selected_two_bed(self):
        message = _format_summary(
            [
                unit("1744", "14633987", 1406),
                unit("1597", "14634057", 1431, floorplan_name="3 Bed 2 Bath", sqft=1186, beds=3),
            ],
            ChangeSet([], [], [], []),
        )

        self.assertIn("**Selected 2BR Baseline**: $1,406/mo", message)
        self.assertIn("+$25/mo vs 2BR", message)
        self.assertIn("+$0/mo vs 2BR", message)

    def test_alert_condition_only_matches_price_decreases(self):
        self.assertTrue(ChangeSet([], [(unit("1597", "14634057", 1331), 1400)], [], []).has_price_decreases)
        self.assertFalse(ChangeSet([], [(unit("1597", "14634057", 1400), 1331)], [], []).has_price_decreases)
        self.assertFalse(ChangeSet([unit("1597", "14634057", 1331)], [], [], []).has_price_decreases)
        self.assertFalse(ChangeSet([], [], [], []).has_price_decreases)

    def test_ping_condition_excludes_price_increases(self):
        removed_unit = _latest_units(
            [
                SHEET_HEADERS,
                row(
                    "2026-05-04 12:47:33",
                    "1597",
                    "14634057",
                    "$1,331",
                    floorplan_name="3 Bed 2 Bath",
                    sqft="1186",
                ),
            ]
        )["1597"]

        self.assertFalse(ChangeSet([], [(unit("1597", "14634057", 1400), 1331)], [], []).has_pingworthy_changes)
        self.assertTrue(ChangeSet([], [(unit("1597", "14634057", 1331), 1400)], [], []).has_pingworthy_changes)
        self.assertTrue(ChangeSet([unit("1597", "14634057", 1331)], [], [], []).has_pingworthy_changes)
        self.assertTrue(ChangeSet([], [], [removed_unit], []).has_pingworthy_changes)

    def test_malformed_history_raises_instead_of_silently_skipping(self):
        cells = [
            SHEET_HEADERS,
            row("not a date", "2425", "14634015", "$1,366"),
        ]

        with self.assertRaises(LegacyParkeDataError):
            _latest_units(cells)

    def test_realpage_transient_error_is_retried(self):
        transient = {
            "ResponseStatus": {
                "ErrorCode": "OllRError",
                "Message": "SystemTechnicalError",
            }
        }
        success = {"ResponseStatus": {}, "Floorplans": []}

        with patch("legacyparke_watcher.time.sleep") as sleep, patch(
            "legacyparke_watcher._realpage_request",
            side_effect=[transient, success],
        ) as request:
            data = _realpage_get("/FloorplanList/v1?MoveInDate=05/09/2026", "SearchFloorPlan")

        self.assertEqual(data, success)
        self.assertEqual(request.call_count, 2)
        sleep.assert_called_once()

    def test_realpage_timeout_is_retried(self):
        success = {"ResponseStatus": {}, "Floorplans": []}

        with patch("legacyparke_watcher.time.sleep"), patch(
            "legacyparke_watcher._realpage_request",
            side_effect=[TimeoutError("read timed out"), success],
        ) as request:
            data = _realpage_get("/FloorplanList/v1?MoveInDate=05/14/2026", "SearchFloorPlan")

        self.assertEqual(data, success)
        self.assertEqual(request.call_count, 2)

    def test_realpage_captcha_is_not_retried(self):
        error = urllib_error(403, '{"url":"https://geo.captcha-delivery.com/interstitial/"}')

        with patch("legacyparke_watcher._realpage_request", side_effect=error) as request:
            with self.assertRaises(RealPageAccessBlockedError):
                _realpage_get("/FloorplanList/v1?MoveInDate=05/21/2026", "SearchFloorPlan")

        self.assertEqual(request.call_count, 1)

    def test_relevant_units_default_to_g5_source(self):
        with patch("legacyparke_watcher.fetch_g5_units", return_value=["g5"]) as g5, patch(
            "legacyparke_watcher.fetch_realpage_units",
            return_value=["realpage"],
        ) as realpage:
            units = fetch_relevant_units(beds=(3,))

        self.assertEqual(units, ["g5"])
        g5.assert_called_once_with(move_in_date="", beds=(3,))
        realpage.assert_not_called()

    def test_relevant_units_can_opt_into_realpage_source(self):
        with patch.dict("legacyparke_watcher.os.environ", {"LEGACYPARKE_DATA_SOURCE": "realpage"}), patch(
            "legacyparke_watcher.fetch_g5_units",
            return_value=["g5"],
        ) as g5, patch("legacyparke_watcher.fetch_realpage_units", return_value=["realpage"]) as realpage:
            units = fetch_relevant_units(beds=(3,))

        self.assertEqual(units, ["realpage"])
        realpage.assert_called_once_with(move_in_date="", beds=(3,))
        g5.assert_not_called()


if __name__ == "__main__":
    unittest.main()
