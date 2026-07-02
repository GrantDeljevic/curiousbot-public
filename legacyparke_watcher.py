"""
Legacy Parke rent watcher for curiousbot.

Polls the same public G5 Inventory GraphQL endpoint used by Legacy Parke's
floor-plan widget and posts notable 2BR/3BR price observations to Discord.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import random
import re
import socket
import string
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import pygsheets

from bot_config import google_client


GRAPHQL_URL = "https://inventory.g5marketingcloud.com/graphql"
LOCATION_URN = "g5-cl-1n2fs5tj0t-gillespie-group-charlotte-mi"
REALPAGE_BASE_URL = "https://leasing.realpage.com/RP.Leasing.AppService.WebHost"
REALPAGE_SITE_ID = "4798053"
REALPAGE_PMC_ID = "4798035"
REALPAGE_USER_AGENT = "Mozilla/5.0"
DEFAULT_CHANNEL_ID = 1515918998255042620
DEFAULT_PING_USER_ID = 282599041244594176
SHEET_KEY = "1dUfsLn7f02LkOsnI0qAgd1YMAfBysggxXOzIkVmkh1g"
DEFAULT_WORKSHEET_TITLE = "legacyparke_rents"
LOCAL_TIMEZONE = ZoneInfo("America/New_York")
DEFAULT_SWITCH_TARGET_DATE = "2026-07-08"
DEFAULT_LOCKED_1744_RENT = 1406.0
DEFAULT_MAX_3BR_PREMIUM = 0.0
DEFAULT_3BR_DANGER_COUNT = 1
DEFAULT_WATCHED_BEDS = "2,3"
DEFAULT_DATA_SOURCE = "g5"
DEFAULT_REALPAGE_RETRY_ATTEMPTS = 3
DEFAULT_REALPAGE_RETRY_BASE_SECONDS = 15.0
LEASE_MONTHS = 15
DAYS_PER_MONTH = 30.44
SHEET_HEADERS = [
    "observed_at",
    "floorplan_name",
    "sqft",
    "unit_name",
    "external_id",
    "availability_date",
    "last_move_in_date",
    "formatted_rent",
    "rent_per_sqft",
]
HEADER_INDEX = {header: index for index, header in enumerate(SHEET_HEADERS)}
EMPTY_OBSERVATION_MARKER = "__NO_WATCHED_UNITS__"

APARTMENT_COMPLEX_QUERY = """
query ApartmentComplex($locationUrn: String!, $moveInDate: String!, $unitsLimit: Int) {
  apartmentComplex(locationUrn: $locationUrn) {
    pricingDisclaimer
    floorplans {
      id
      name
      beds
      baths
      sqft
      sqftDisplay
      totalAvailableUnits
      rateDisplay
      startingRate
      endingRate
      unitsAvailableByFilters(moveInDate: $moveInDate, limit: $unitsLimit)
    }
  }
}
"""

REALPAGE_FLOORPLAN_LIST_PATH = (
    "/FloorplanList/v1?MoveInDate={move_in_date}&PmcId={pmc_id}&SiteId={site_id}"
)
REALPAGE_APARTMENT_LIST_PATH = (
    "/ApartmentList/v1?FloorplanId={floorplan_id}&MoveInDate={move_in_date}&PmcId={pmc_id}&SiteId={site_id}"
)
REALPAGE_SHOP_UNIT_DETAILS_PATH = (
    "/shopunitdetails/v1/?PmcId={pmc_id}&SiteId={site_id}&UnitId={unit_id}&MoveInDate={move_in_date}"
)

UNITS_QUERY = """
query Units($floorplanId: Int!, $locationUrn: String!, $limit: Int, $moveInDate: String) {
  units(floorplanId: $floorplanId, locationUrn: $locationUrn, limit: $limit, moveInDate: $moveInDate) {
    id
    externalId
    name
    displayName
    building
    sqftDisplay
    availabilityDate
    lastAvailableMoveInDate
    prices {
      id
      priceType
      formattedPrice
      value
      leaseTermBasisMin
    }
  }
}
"""


@dataclass(frozen=True)
class UnitRent:
    floorplan_id: int
    floorplan_name: str
    beds: int
    baths: str
    sqft: int
    unit_id: int
    external_id: str
    unit_name: str
    availability_date: str | None
    last_move_in_date: str | None
    price: float
    formatted_price: str

    @property
    def key(self) -> str:
        return _unit_key(self.external_id, self.unit_name)


class LegacyParkeDataError(RuntimeError):
    """Raised when sheet history cannot be trusted for alert decisions."""


class RealPageAccessBlockedError(RuntimeError):
    """Raised when RealPage asks for interactive verification."""


@dataclass(frozen=True)
class HistoricalUnit:
    observed_at: str
    observed_at_datetime: datetime
    price: float
    unit_name: str
    floorplan_name: str
    formatted_rent: str
    availability_date: str | None


@dataclass(frozen=True)
class ChangeSet:
    new_units: list[UnitRent]
    price_changes: list[tuple[UnitRent, float]]
    removed_units: list[HistoricalUnit]
    switch_status_changes: list[tuple["SwitchDecision", str | None]]

    @property
    def has_changes(self) -> bool:
        return bool(
            self.new_units
            or self.price_changes
            or self.removed_units
            or self.switch_status_changes
        )

    @property
    def has_price_decreases(self) -> bool:
        return any(unit.price < old_price for unit, old_price in self.price_changes)

    @property
    def has_pingworthy_changes(self) -> bool:
        return bool(
            self.has_price_decreases
            or self.new_units
            or self.removed_units
            or self.switch_status_changes
        )


@dataclass(frozen=True)
class SwitchDecision:
    key: str
    unit_name: str
    status: str
    effective_monthly: float
    premium: float
    monthly_rent: float
    early_unused_days: int
    rent_start_date: date


def _unit_key(external_id: Any, unit_name: Any) -> str:
    return str(unit_name or external_id or "").strip()


def _switch_target_date() -> date:
    value = os.getenv("LEGACYPARKE_SWITCH_TARGET_DATE", DEFAULT_SWITCH_TARGET_DATE)
    return datetime.strptime(value, "%Y-%m-%d").date()


def _locked_1744_rent() -> float:
    return float(os.getenv("LEGACYPARKE_LOCKED_1744_RENT", DEFAULT_LOCKED_1744_RENT))


def _max_3br_premium() -> float:
    return float(os.getenv("LEGACYPARKE_MAX_3BR_PREMIUM", DEFAULT_MAX_3BR_PREMIUM))


def _three_bed_danger_count() -> int:
    return int(os.getenv("LEGACYPARKE_3BR_DANGER_COUNT", DEFAULT_3BR_DANGER_COUNT))


def _watched_beds() -> tuple[int, ...]:
    value = os.getenv("LEGACYPARKE_WATCHED_BEDS", DEFAULT_WATCHED_BEDS)
    beds = tuple(
        int(part.strip())
        for part in value.split(",")
        if part.strip()
    )
    if not beds:
        raise LegacyParkeDataError("LEGACYPARKE_WATCHED_BEDS must include at least one bed count.")
    return beds


def _realpage_retry_attempts() -> int:
    return max(1, int(os.getenv("LEGACYPARKE_REALPAGE_RETRY_ATTEMPTS", DEFAULT_REALPAGE_RETRY_ATTEMPTS)))


def _realpage_retry_base_seconds() -> float:
    return max(0.0, float(os.getenv("LEGACYPARKE_REALPAGE_RETRY_BASE_SECONDS", DEFAULT_REALPAGE_RETRY_BASE_SECONDS)))


def _date_or_none(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def _is_three_bed(floorplan_name: str, beds: int | None = None) -> bool:
    return beds == 3 or bool(re.search(r"\b3\s*Bed\b", floorplan_name, re.IGNORECASE))


def _is_watched_bed(
    floorplan_name: str,
    beds: int | None,
    watched_beds: Iterable[int],
) -> bool:
    watched = set(watched_beds)
    if beds is not None:
        return beds in watched
    match = re.search(r"\b(\d+)\s*Bed\b", floorplan_name, re.IGNORECASE)
    return bool(match and int(match.group(1)) in watched)


def _post_graphql(query: str, variables: dict[str, Any]) -> dict[str, Any]:
    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    request = urllib.request.Request(
        GRAPHQL_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "curiousbot LegacyParkeRentWatcher/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"G5 GraphQL HTTP {exc.code}: {detail[:500]}") from exc
    data = json.loads(body)
    if data.get("errors"):
        raise RuntimeError(f"G5 GraphQL errors: {data['errors']}")
    return data["data"]


def _realpage_xyz_token(site_id: str = REALPAGE_SITE_ID, user_agent: str = REALPAGE_USER_AGENT) -> str:
    chars = string.ascii_letters + string.digits

    def rand(length: int) -> str:
        return "".join(random.choice(chars) for _ in range(length))

    token = (
        rand(1)
        + hashlib.md5(site_id.encode("utf-8")).hexdigest().upper()
        + rand(3)
        + hashlib.md5(user_agent.encode("utf-8")).hexdigest().upper()
        + rand(5)
        + base64.b64encode(str(int(time.time() * 1000)).encode("utf-8")).decode("ascii")
        + rand(7)
    )
    return base64.b64encode(token.encode("utf-8")).decode("ascii")


def _realpage_is_transient_http(code: int, detail: str) -> bool:
    return code >= 500 or "SystemTechnicalError" in detail or "OllRError" in detail


def _realpage_is_access_blocked(code: int, detail: str) -> bool:
    return code in (401, 403) and (
        "captcha-delivery.com" in detail
        or "interstitial" in detail.lower()
        or "captcha" in detail.lower()
    )


def _realpage_is_transient_status(status: dict[str, Any]) -> bool:
    text = json.dumps(status)
    return (
        status.get("ErrorCode") == "OllRError"
        or "SystemTechnicalError" in text
    )


def _realpage_request(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": REALPAGE_USER_AGENT,
            "XYZ": _realpage_xyz_token(),
            "X-AuthToken": "",
            "X-Phased": "",
        },
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        body = response.read().decode("utf-8")
    return json.loads(body)


def _realpage_get(path: str, bpm_id: str, sequence: int = 0) -> dict[str, Any]:
    separator = "&" if "?" in path else "?"
    url = (
        f"{REALPAGE_BASE_URL}{path}{separator}"
        f"BpmId=OLL.{bpm_id}&BpmSequence={sequence}&LogSequence={sequence}"
    )
    attempts = _realpage_retry_attempts()
    last_error = ""
    for attempt in range(attempts):
        is_last_attempt = attempt == attempts - 1
        if attempt:
            time.sleep(_realpage_retry_base_seconds() * attempt)
        try:
            data = _realpage_request(url)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            last_error = f"RealPage HTTP {exc.code}: {detail[:500]}"
            if _realpage_is_access_blocked(exc.code, detail):
                raise RealPageAccessBlockedError(
                    "RealPage returned an interactive captcha/interstitial; skipping that source."
                ) from exc
            if not is_last_attempt and _realpage_is_transient_http(exc.code, detail):
                continue
            raise RuntimeError(last_error) from exc
        except (TimeoutError, socket.timeout, urllib.error.URLError) as exc:
            last_error = f"RealPage request timed out or failed transiently: {exc}"
            if not is_last_attempt:
                continue
            raise RuntimeError(last_error) from exc

        status = data.get("ResponseStatus") or {}
        if status.get("ErrorCode"):
            last_error = f"RealPage error: {status}"
            if not is_last_attempt and _realpage_is_transient_status(status):
                continue
            raise RuntimeError(last_error)
        return data
    raise RuntimeError(last_error or "RealPage request failed.")


def _realpage_date(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"/Date\((-?\d+)", value)
    if not match:
        return value
    milliseconds = int(match.group(1))
    if milliseconds < 0:
        return None
    return datetime.fromtimestamp(milliseconds / 1000, LOCAL_TIMEZONE).strftime("%Y-%m-%d")


def _format_realpage_rent(value: Any) -> str:
    return f"${float(value):,.0f}"


def _realpage_date_for_api(value: datetime) -> str:
    return value.strftime("%m/%d/%Y")


def _realpage_move_in_date(move_in_date: str) -> str:
    if not move_in_date:
        return _realpage_date_for_api(datetime.now(LOCAL_TIMEZONE))
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(move_in_date, fmt).strftime("%m/%d/%Y")
        except ValueError:
            continue
    raise LegacyParkeDataError(f"Could not parse RealPage move-in date: {move_in_date!r}")


def _realpage_move_in_window() -> tuple[datetime, datetime]:
    start = datetime.now(LOCAL_TIMEZONE).replace(hour=0, minute=0, second=0, microsecond=0)
    end = datetime(start.year, 7, 10, tzinfo=LOCAL_TIMEZONE)
    if end < start:
        end = start
    return start, end


def _realpage_discovery_dates() -> list[str]:
    start, end = _realpage_move_in_window()
    july_first = datetime(start.year, 7, 1, tzinfo=LOCAL_TIMEZONE)
    # Keep discovery sparse to reduce public endpoint traffic. Rent is still
    # normalized per unit with shopunitdetails on the first usable move-in date.
    dates = [_realpage_date_for_api(start), _realpage_date_for_api(end)]
    if start <= july_first <= end:
        dates.append(_realpage_date_for_api(july_first))
    return sorted(set(dates), key=lambda item: datetime.strptime(item, "%m/%d/%Y"))


def _realpage_move_in_dates(move_in_date: str) -> list[str]:
    if move_in_date:
        return [_realpage_move_in_date(move_in_date)]
    return _realpage_discovery_dates()


def _realpage_unit_available_datetime(unit: UnitRent) -> datetime | None:
    if not unit.availability_date:
        return None
    return datetime.strptime(unit.availability_date, "%Y-%m-%d").replace(tzinfo=LOCAL_TIMEZONE)


def _realpage_unit_move_in_date(unit: UnitRent) -> str:
    start, _ = _realpage_move_in_window()
    available = _realpage_unit_available_datetime(unit)
    if available is None or available < start:
        return _realpage_date_for_api(start)
    return _realpage_date_for_api(available)


def _realpage_unit_in_window(unit: UnitRent) -> bool:
    _, end = _realpage_move_in_window()
    available = _realpage_unit_available_datetime(unit)
    if available is None:
        return True
    return available <= end


def _select_realpage_price_plan(price_plans: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not price_plans:
        return None
    # The user wants the max/15-month lease term when this read-only endpoint
    # exposes term-specific rents. Do not use quote creation for pricing.
    fifteen_month = [
        plan for plan in price_plans
        if int(plan.get("DurationInMonths") or 0) == 15
    ]
    if fifteen_month:
        return fifteen_month[0]
    return max(price_plans, key=lambda plan: int(plan.get("DurationInMonths") or 0))


def _with_realpage_unit_details(unit: UnitRent) -> UnitRent:
    move_in_date = _realpage_unit_move_in_date(unit)
    details_path = REALPAGE_SHOP_UNIT_DETAILS_PATH.format(
        pmc_id=REALPAGE_PMC_ID,
        site_id=REALPAGE_SITE_ID,
        unit_id=unit.external_id or unit.unit_id,
        move_in_date=move_in_date,
    )
    details = _realpage_get(details_path, "HomeDetails", sequence=2).get("UnitDetails") or {}
    plan = _select_realpage_price_plan(details.get("PricePlans") or [])
    if not plan or plan.get("MonthlyRent") in (None, ""):
        return unit
    price = float(plan["MonthlyRent"])
    return UnitRent(
        floorplan_id=unit.floorplan_id,
        floorplan_name=unit.floorplan_name,
        beds=unit.beds,
        baths=unit.baths,
        sqft=unit.sqft,
        unit_id=unit.unit_id,
        external_id=unit.external_id,
        unit_name=unit.unit_name,
        availability_date=unit.availability_date,
        last_move_in_date=unit.last_move_in_date,
        price=price,
        formatted_price=_format_realpage_rent(price),
    )


def fetch_realpage_units_for_date(move_in_date: str, beds: Iterable[int] = (2, 3)) -> list[UnitRent]:
    wanted_beds = set(beds)
    floorplan_path = REALPAGE_FLOORPLAN_LIST_PATH.format(
        move_in_date=move_in_date,
        pmc_id=REALPAGE_PMC_ID,
        site_id=REALPAGE_SITE_ID,
    )
    floorplans = _realpage_get(floorplan_path, "SearchFloorPlan").get("Floorplans") or []
    units: list[UnitRent] = []
    for floorplan in floorplans:
        if floorplan.get("Bedrooms") not in wanted_beds:
            continue
        if not floorplan.get("AvailableUnits"):
            continue
        floorplan_id = str(floorplan["Id"])
        apartment_path = REALPAGE_APARTMENT_LIST_PATH.format(
            floorplan_id=floorplan_id,
            move_in_date=move_in_date,
            pmc_id=REALPAGE_PMC_ID,
            site_id=REALPAGE_SITE_ID,
        )
        apartments = _realpage_get(apartment_path, "HomeDetails", sequence=1).get("Units") or []
        for apartment in apartments:
            price = apartment.get("MinPriceRange") or apartment.get("TwelveMonthsRent")
            if price in (None, ""):
                continue
            unit_name = str(apartment.get("UnitNumber") or apartment.get("Id") or "").strip()
            if not unit_name:
                continue
            sqft = int(apartment.get("Squarefeet") or floorplan.get("Squarefeet") or 0)
            units.append(
                UnitRent(
                    floorplan_id=int(floorplan_id),
                    floorplan_name=floorplan.get("Name") or f"{floorplan.get('Bedrooms')} Bed",
                    beds=int(floorplan["Bedrooms"]),
                    baths=str(floorplan.get("Bathrooms") or ""),
                    sqft=sqft,
                    unit_id=int(apartment.get("Id") or 0),
                    external_id=str(apartment.get("Id") or ""),
                    unit_name=unit_name,
                    availability_date=_realpage_date(apartment.get("AvailableDate")),
                    last_move_in_date=None,
                    price=float(price),
                    formatted_price=_format_realpage_rent(price),
                )
            )
    return sorted(units, key=lambda item: (item.price, item.beds, item.sqft, item.unit_name))


def fetch_realpage_units(move_in_date: str = "", beds: Iterable[int] = (2, 3)) -> list[UnitRent]:
    units_by_key: dict[str, UnitRent] = {}
    for date in _realpage_move_in_dates(move_in_date):
        for unit in fetch_realpage_units_for_date(date, beds=beds):
            if not move_in_date and not _realpage_unit_in_window(unit):
                continue
            existing = units_by_key.get(unit.key)
            if existing is None or unit.price < existing.price:
                units_by_key[unit.key] = unit
    units = [
        _with_realpage_unit_details(unit)
        for unit in units_by_key.values()
    ]
    return sorted(units, key=lambda item: (item.price, item.beds, item.sqft, item.unit_name))


def fetch_relevant_units(move_in_date: str = "", beds: Iterable[int] = (2, 3)) -> list[UnitRent]:
    source = os.getenv("LEGACYPARKE_DATA_SOURCE", DEFAULT_DATA_SOURCE).strip().lower()
    if source == "realpage":
        return fetch_realpage_units(move_in_date=move_in_date, beds=beds)
    if source == "g5":
        return fetch_g5_units(move_in_date=move_in_date, beds=beds)
    raise LegacyParkeDataError("LEGACYPARKE_DATA_SOURCE must be either 'g5' or 'realpage'.")


def fetch_g5_units(move_in_date: str = "", beds: Iterable[int] = (2, 3)) -> list[UnitRent]:
    wanted_beds = set(beds)
    complex_data = _post_graphql(
        APARTMENT_COMPLEX_QUERY,
        {"locationUrn": LOCATION_URN, "moveInDate": move_in_date, "unitsLimit": 9},
    )["apartmentComplex"]

    units: list[UnitRent] = []
    for floorplan in complex_data["floorplans"]:
        if floorplan.get("beds") not in wanted_beds:
            continue
        if not floorplan.get("totalAvailableUnits"):
            continue
        units_data = _post_graphql(
            UNITS_QUERY,
            {
                "floorplanId": floorplan["id"],
                "locationUrn": LOCATION_URN,
                "limit": 9,
                "moveInDate": move_in_date,
            },
        )["units"]
        for unit in units_data:
            rate = next((p for p in unit.get("prices", []) if p.get("priceType") == "rate"), None)
            if not rate or rate.get("value") in (None, ""):
                continue
            units.append(
                UnitRent(
                    floorplan_id=floorplan["id"],
                    floorplan_name=floorplan["name"],
                    beds=floorplan["beds"],
                    baths=floorplan["baths"],
                    sqft=floorplan["sqft"],
                    unit_id=unit["id"],
                    external_id=unit.get("externalId") or "",
                    unit_name=unit["name"],
                    availability_date=unit.get("availabilityDate"),
                    last_move_in_date=unit.get("lastAvailableMoveInDate"),
                    price=float(rate["value"]),
                    formatted_price=rate.get("formattedPrice") or f"${float(rate['value']):,.0f}",
                )
            )
    return sorted(units, key=lambda item: (item.price, item.beds, item.sqft, item.unit_name))


def _worksheet(sheet_key: str, worksheet_title: str):
    gc = google_client()
    spreadsheet = gc.open_by_key(sheet_key)
    try:
        target = spreadsheet.worksheet_by_title(worksheet_title)
    except pygsheets.WorksheetNotFound:
        target = spreadsheet.add_worksheet(worksheet_title, rows=100, cols=len(SHEET_HEADERS))
        target.update_values("A1", [SHEET_HEADERS])
    cells = target.get_all_values(
        include_tailing_empty_rows=False,
        include_tailing_empty=False,
        returnas="matrix",
    )
    if not cells:
        target.update_values("A1", [SHEET_HEADERS])
        cells = [SHEET_HEADERS]
    elif cells[0] != SHEET_HEADERS:
        raise LegacyParkeDataError(
            f"Unexpected header row in {worksheet_title}. "
            f"Expected {SHEET_HEADERS}, got {cells[0]}."
        )
    return target, cells


def _parse_observed_at(value: Any) -> datetime:
    value = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise LegacyParkeDataError(f"Could not parse observed_at value: {value!r}")


def _parse_price(value: Any) -> float:
    normalized = str(value).replace("$", "").replace(",", "").strip()
    try:
        return float(normalized)
    except ValueError as exc:
        raise LegacyParkeDataError(f"Could not parse formatted_rent value: {value!r}") from exc


def _history_row(row: list[str], row_number: int) -> HistoricalUnit | None:
    if not row or not str(row[0]).strip():
        return None
    if _is_empty_observation_row(row):
        return None
    if len(row) < len(SHEET_HEADERS):
        raise LegacyParkeDataError(
            f"Row {row_number} is incomplete: expected {len(SHEET_HEADERS)} cells, got {len(row)}."
        )
    observed_at = row[HEADER_INDEX["observed_at"]]
    external_id = row[HEADER_INDEX["external_id"]]
    unit_name = row[HEADER_INDEX["unit_name"]]
    key = _unit_key(external_id, unit_name)
    if not key:
        raise LegacyParkeDataError(f"Row {row_number} has neither external_id nor unit_name.")
    return HistoricalUnit(
        observed_at=observed_at,
        observed_at_datetime=_parse_observed_at(observed_at),
        price=_parse_price(row[HEADER_INDEX["formatted_rent"]]),
        unit_name=str(unit_name).strip(),
        floorplan_name=row[HEADER_INDEX["floorplan_name"]],
        formatted_rent=row[HEADER_INDEX["formatted_rent"]],
        availability_date=row[HEADER_INDEX["availability_date"]] or None,
    )


def _history_units_by_snapshot(cells: list[list[str]]) -> dict[datetime, dict[str, HistoricalUnit]]:
    snapshots: dict[datetime, dict[str, HistoricalUnit]] = {}
    for row_number, row in enumerate(cells[1:], start=2):
        if _is_empty_observation_row(row):
            observed_at = row[HEADER_INDEX["observed_at"]]
            snapshots.setdefault(_parse_observed_at(observed_at), {})
            continue
        unit = _history_row(row, row_number)
        if unit is None:
            continue
        key = _unit_key(row[HEADER_INDEX["external_id"]], row[HEADER_INDEX["unit_name"]])
        snapshots.setdefault(unit.observed_at_datetime, {})[key] = unit
    return snapshots


def _latest_units(cells: list[list[str]]) -> dict[str, HistoricalUnit]:
    snapshots = _history_units_by_snapshot(cells)
    if not snapshots:
        return {}
    return snapshots[max(snapshots)]


def _last_seen_units(cells: list[list[str]]) -> dict[str, HistoricalUnit]:
    units: dict[str, HistoricalUnit] = {}
    for snapshot in _history_units_by_snapshot(cells).values():
        for key, unit in snapshot.items():
            if key not in units or unit.observed_at_datetime >= units[key].observed_at_datetime:
                units[key] = unit
    return units


def _unit_row(observed_at: str, unit: UnitRent) -> list[Any]:
    return [
        observed_at,
        unit.floorplan_name,
        unit.sqft,
        unit.unit_name,
        unit.external_id,
        unit.availability_date or "",
        unit.last_move_in_date or "",
        unit.formatted_price,
        round(unit.price / unit.sqft, 2) if unit.sqft else "",
    ]


def _empty_observation_row(observed_at: str) -> list[Any]:
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


def _is_empty_observation_row(row: list[str]) -> bool:
    floorplan_index = HEADER_INDEX["floorplan_name"]
    return (
        len(row) > floorplan_index
        and str(row[floorplan_index]).strip() == EMPTY_OBSERVATION_MARKER
    )


def _save_observation(target: Any, observed_at: str, units: list[UnitRent]) -> None:
    rows = [_unit_row(observed_at, unit) for unit in units]
    if not rows:
        rows = [_empty_observation_row(observed_at)]
    target.append_table(rows)


def _switch_decision(
    key: str,
    unit_name: str,
    floorplan_name: str,
    monthly_rent: float,
    availability_date: str | None,
    observed_at: datetime,
    three_bed_count: int,
) -> SwitchDecision | None:
    if not _is_three_bed(floorplan_name):
        return None
    observed_date = observed_at.date()
    available = _date_or_none(availability_date) or observed_date
    rent_start = max(available, observed_date)
    early_unused_days = max((_switch_target_date() - rent_start).days, 0)
    early_unused_rent = early_unused_days * monthly_rent / DAYS_PER_MONTH
    monthly_penalty = early_unused_rent / LEASE_MONTHS
    effective_monthly = monthly_rent + monthly_penalty
    premium = effective_monthly - _locked_1744_rent()
    status = (
        "SWITCH"
        if three_bed_count <= _three_bed_danger_count()
        or premium <= _max_3br_premium()
        else "WAIT"
    )
    return SwitchDecision(
        key=key,
        unit_name=unit_name,
        status=status,
        effective_monthly=effective_monthly,
        premium=premium,
        monthly_rent=monthly_rent,
        early_unused_days=early_unused_days,
        rent_start_date=rent_start,
    )


def _switch_decisions_from_units(units: list[UnitRent], observed_at: datetime) -> dict[str, SwitchDecision]:
    three_bed_count = sum(1 for unit in units if _is_three_bed(unit.floorplan_name, unit.beds))
    decisions: dict[str, SwitchDecision] = {}
    for unit in units:
        if not _is_three_bed(unit.floorplan_name, unit.beds):
            continue
        decision = _switch_decision(
            unit.key,
            unit.unit_name,
            unit.floorplan_name,
            unit.price,
            unit.availability_date,
            observed_at,
            three_bed_count,
        )
        if decision is not None:
            decisions[unit.key] = decision
    return decisions


def _switch_decisions_from_snapshot(snapshot: dict[str, HistoricalUnit]) -> dict[str, SwitchDecision]:
    if not snapshot:
        return {}
    observed_at = next(iter(snapshot.values())).observed_at_datetime
    three_bed_count = sum(1 for unit in snapshot.values() if _is_three_bed(unit.floorplan_name))
    decisions: dict[str, SwitchDecision] = {}
    for key, unit in snapshot.items():
        if not _is_three_bed(unit.floorplan_name):
            continue
        decision = _switch_decision(
            key,
            unit.unit_name,
            unit.floorplan_name,
            unit.price,
            unit.availability_date,
            observed_at,
            three_bed_count,
        )
        if decision is not None:
            decisions[key] = decision
    return decisions


def _detect_switch_status_changes(
    current: dict[str, SwitchDecision],
    previous: dict[str, SwitchDecision],
) -> list[tuple[SwitchDecision, str | None]]:
    changes: list[tuple[SwitchDecision, str | None]] = []
    for key, decision in sorted(current.items(), key=lambda item: item[1].unit_name):
        old = previous.get(key)
        if old is None:
            if decision.status == "SWITCH":
                changes.append((decision, None))
            continue
        if old.status != decision.status:
            changes.append((decision, old.status))
    return changes


def _detect_changes(
    units: list[UnitRent],
    previous: dict[str, HistoricalUnit],
    latest_snapshot: dict[str, HistoricalUnit],
    observed_at_datetime: datetime,
    watched_beds: Iterable[int] = (2, 3),
) -> ChangeSet:
    current_keys = {unit.key for unit in units}
    new_units = [unit for unit in units if unit.key not in previous]
    price_changes = [
        (unit, previous[unit.key].price)
        for unit in units
        if unit.key in previous and previous[unit.key].price != unit.price
    ]
    removed_units = [
        latest_snapshot[key]
        for key in sorted(set(latest_snapshot) - current_keys)
        if _is_watched_bed(latest_snapshot[key].floorplan_name, None, watched_beds)
    ]
    switch_status_changes = _detect_switch_status_changes(
        _switch_decisions_from_units(units, observed_at_datetime),
        _switch_decisions_from_snapshot(latest_snapshot),
    )
    return ChangeSet(new_units, price_changes, removed_units, switch_status_changes)


def _format_signed_currency(value: float) -> str:
    sign = "+" if value >= 0 else "-"
    return f"{sign}${abs(value):,.0f}"


def _format_vs_selected_2br(price: float) -> str:
    return f"{_format_signed_currency(price - _locked_1744_rent())}/mo vs 2BR"


def _format_summary(
    units: list[UnitRent],
    changes: ChangeSet,
) -> str:
    watched_label = "/".join(f"{bed}BR" for bed in sorted({unit.beds for unit in units})) or "watched"
    if not units:
        return "Legacy Parke watcher: no available watched units returned."

    cheapest = units[0]
    selected_2br_rent = _locked_1744_rent()
    lines = [
        f"**Legacy Parke {watched_label} Check**",
        "",
        f"**Selected 2BR Baseline**: ${selected_2br_rent:,.0f}/mo",
        "",
        "**Cheapest**",
        (
            f"- {cheapest.beds}BR unit `{cheapest.unit_name}` | "
            f"{cheapest.sqft:,} sqft | **{cheapest.formatted_price}** | "
            f"{_format_vs_selected_2br(cheapest.price)} | "
            f"available {cheapest.availability_date or 'unknown'}"
        ),
    ]
    if changes.switch_status_changes:
        lines.extend(["", "**Important: 3BR Switch Status Changed**"])
        for decision, old_status in changes.switch_status_changes[:8]:
            old = old_status or "NEW"
            lines.append(
                f"- unit `{decision.unit_name}`: **{old} -> {decision.status}** | "
                f"effective **${decision.effective_monthly:,.2f}/mo** | "
                f"vs selected 2BR **{_format_signed_currency(decision.premium)}/mo** | "
                f"rent start {decision.rent_start_date.isoformat()} | "
                f"{decision.early_unused_days} early unused days"
            )
    changed = [f"new {unit.unit_name}: {unit.formatted_price}" for unit in changes.new_units]
    for unit, old in changes.price_changes:
        direction = "down" if unit.price < old else "up"
        changed.append(f"{unit.unit_name}: ${old:,.0f} -> {unit.formatted_price} ({direction})")
    if changed:
        lines.extend(["", "**Changes**"])
        lines.extend(f"- {entry}" for entry in changed[:8])
    if changes.removed_units:
        lines.extend(["", "**Removed From Listing**"])
        lines.extend(
            f"- {unit.unit_name} ({unit.floorplan_name}, {unit.formatted_rent})"
            for unit in changes.removed_units[:8]
        )

    lines.extend(["", f"**Current {watched_label} Units**", "```"])
    lines.extend(
        (
            f"{unit.beds}BR  unit {unit.unit_name:<4}  {unit.sqft:>5,} sqft  "
            f"{unit.formatted_price:>7}  {_format_vs_selected_2br(unit.price):>13}  "
            f"avail {unit.availability_date or 'unknown'}"
        )
        for unit in units[:8]
    )
    lines.append("```")
    return "\n".join(lines)


def check_once(sheet_key: str, worksheet_title: str, move_in_date: str = "") -> tuple[str, bool, bool]:
    target, cells = _worksheet(sheet_key, worksheet_title)
    latest_snapshot = _latest_units(cells)
    previous = _last_seen_units(cells)
    watched_beds = _watched_beds()
    units = fetch_relevant_units(move_in_date=move_in_date, beds=watched_beds)
    observed_at_datetime = datetime.now(LOCAL_TIMEZONE)
    observed_at = observed_at_datetime.strftime("%Y-%m-%d %H:%M:%S")
    changes = _detect_changes(units, previous, latest_snapshot, observed_at_datetime, watched_beds)
    _save_observation(target, observed_at, units)
    message = _format_summary(units, changes)
    return message, changes.has_changes, changes.has_pingworthy_changes


async def check_legacyparke_once(bot: Any, post_unchanged: bool = False) -> str:
    worksheet_title = os.getenv("LEGACYPARKE_WORKSHEET_TITLE", DEFAULT_WORKSHEET_TITLE)
    move_in_date = os.getenv("LEGACYPARKE_MOVE_IN_DATE", "")
    channel_id = int(os.getenv("LEGACYPARKE_CHANNEL_ID", str(DEFAULT_CHANNEL_ID)))
    ping_user_id = int(os.getenv("LEGACYPARKE_PING_USER_ID", str(DEFAULT_PING_USER_ID)))

    try:
        message, should_post, should_ping = await asyncio.to_thread(check_once, SHEET_KEY, worksheet_title, move_in_date)
    except Exception as exc:
        channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
        await channel.send(
            f"Legacy Parke rent watcher failed before it could make a reliable comparison: {exc}"
        )
        raise
    if should_post or post_unchanged:
        channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
        prefix = f"<@{ping_user_id}> " if should_ping else ""
        await channel.send(f"{prefix}{message}")
    return message


if __name__ == "__main__":
    message, _, _ = check_once(
        SHEET_KEY,
        os.getenv("LEGACYPARKE_WORKSHEET_TITLE", DEFAULT_WORKSHEET_TITLE),
        os.getenv("LEGACYPARKE_MOVE_IN_DATE", ""),
    )
    print(message)
