import asyncio
import unittest
from unittest.mock import patch

import elupdate
import ffwebscrape


class FakeSpreadsheet:
    url = "https://docs.google.com/spreadsheets/d/copy-id"


class FakeWorksheet:
    spreadsheet = FakeSpreadsheet()

    def __init__(self):
        self.insert_calls = []
        self.update_value_calls = []
        self.update_calls = []

    def insert_cols(self, col, number=1, values=None, inherit=False):
        self.insert_calls.append(
            {
                "col": col,
                "number": number,
                "values": values,
                "inherit": inherit,
            }
        )

    def update_value(self, addr, value):
        self.update_value_calls.append(
            {
                "addr": addr,
                "value": value,
            }
        )

    def update_col(self, index, values, row_offset=0):
        self.update_calls.append(
            {
                "index": index,
                "values": values,
                "row_offset": row_offset,
            }
        )


def score_by_row(tasks):
    return [
        elupdate.AuthorScoreResult(task.sheet_row, task.link, task.sheet_row * 10)
        for task in tasks
    ]


class ElupdateTests(unittest.TestCase):
    def test_build_score_column_preserves_original_sheet_rows(self):
        cells = [
            ["Pen Names", "Discord Tags", "Links", "Author rank"],
            ["Alpha", "alpha", "https://www.fanfiction.net/~alpha", "old"],
            [],
            ["Blank", "blank", "", "old"],
            ["Bravo", "bravo", "https://archiveofourown.org/users/bravo", "old"],
            ["Ignored", "ignored", "ignore", "old"],
            ["Unsupported", "unsupported", "https://example.com/unsupported", "old"],
        ]

        result = elupdate.build_biweekly_result(
            cells,
            "copy-id",
            "Authorlist",
            score_fetcher=score_by_row,
            dry_run=True,
        )

        self.assertEqual([task.sheet_row for task in result.score_tasks], [2, 5])
        self.assertEqual(result.column_values, [20, "", "", 50, "", ""])
        self.assertEqual([row.reason for row in result.skipped_rows], [
            "missing link cell",
            "blank link",
            "ignored",
            "unsupported link",
        ])

    def test_run_biweekly_writes_full_row_aligned_column(self):
        cells = [
            ["Pen Names", "Links", "Other", "Author rank"],
            ["Alpha", "https://www.fanfiction.net/~alpha", "", "old"],
            ["Blank", "", "", "old"],
            ["Bravo", "https://archiveofourown.org/users/bravo", "", "old"],
        ]
        target = FakeWorksheet()
        original_sheet = elupdate.sheet

        def fake_sheet(rosterkey, sheetname):
            return cells, target

        try:
            elupdate.sheet = fake_sheet
            result = elupdate.run_biweekly(
                "copy-id",
                "Authorlist",
                score_fetcher=score_by_row,
            )
        finally:
            elupdate.sheet = original_sheet

        self.assertEqual(result.column_values, [20, "", 40])
        self.assertEqual(target.insert_calls, [
            {
                "col": 3,
                "number": 1,
                "values": None,
                "inherit": True,
            }
        ])
        self.assertEqual(target.update_value_calls, [
            {
                "addr": (1, 4),
                "value": elupdate.today_score_header(),
            }
        ])
        self.assertEqual(target.update_calls, [
            {
                "index": 4,
                "values": [20, "", 40],
                "row_offset": 1,
            }
        ])

    def test_unsupported_links_are_skipped_without_calling_fetcher(self):
        cells = [
            ["Links", "Author rank"],
            ["https://example.com/not-supported", "old"],
            ["https://tapas.io/supported", "old"],
            ["https://archive.transformativeworks.org/users/name/profile", "old"],
        ]
        seen_tasks = []

        def fetcher(tasks):
            seen_tasks.extend(tasks)
            return [
                elupdate.AuthorScoreResult(task.sheet_row, task.link, task.sheet_row * 10)
                for task in tasks
            ]

        result = elupdate.build_biweekly_result(
            cells,
            "copy-id",
            "Authorlist",
            score_fetcher=fetcher,
            dry_run=True,
        )

        self.assertEqual(len(seen_tasks), 2)
        self.assertEqual(seen_tasks[0].platform_name, "tapas.io")
        self.assertEqual(seen_tasks[1].platform_name, "archiveofourown.org")
        self.assertEqual(result.column_values, ["", 30, 40])
        self.assertEqual(result.skipped_rows[0].reason, "unsupported link")

    def test_failed_and_unsupported_rows_carry_forward_previous_score(self):
        cells = [
            ["Links", "5/21/25", "Author rank"],
            ["https://archiveofourown.org/users/failing", "1,234", "old"],
            ["https://example.com/not-supported", "55", "old"],
            ["", "", "old"],
        ]

        def fetcher(tasks):
            return [
                elupdate.AuthorScoreResult(
                    tasks[0].sheet_row,
                    tasks[0].link,
                    None,
                    "failed",
                    "network error",
                )
            ]

        result = elupdate.build_biweekly_result(
            cells,
            "copy-id",
            "Authorlist",
            score_fetcher=fetcher,
            dry_run=True,
        )

        self.assertEqual(result.column_values, [1234, 55, ""])
        self.assertEqual(result.fallback_count, 2)
        self.assertEqual(
            [(row.sheet_row, row.score, row.reason) for row in result.fallback_rows],
            [(2, 1234, "failed"), (3, 55, "unsupported link")],
        )

    def test_ao3_bot_restriction_aborts_score_fetch_instead_of_row_failure(self):
        tasks = [
            elupdate.AuthorScoreTask(2, "https://archiveofourown.org/users/first", elupdate.PLATFORM_AO3, "archiveofourown.org"),
            elupdate.AuthorScoreTask(3, "https://archiveofourown.org/users/second", elupdate.PLATFORM_AO3, "archiveofourown.org"),
        ]
        calls = []

        async def fake_followcount(url, platform):
            calls.append((url, platform))
            raise ffwebscrape.Ao3BotRestrictedError()

        with patch("ffwebscrape.followcount", side_effect=fake_followcount):
            with self.assertRaises(ffwebscrape.Ao3BotRestrictedError):
                asyncio.run(elupdate._fetch_scores_async(tasks, max_concurrency=1))

        self.assertEqual(calls, [(tasks[0].link, tasks[0].platform)])


if __name__ == "__main__":
    unittest.main()
