import argparse
import asyncio
import os
import re
from dataclasses import dataclass
from datetime import date
from typing import Callable, Iterable, Optional

import pygsheets

from bot_config import google_client as authorize_google_client

AUTHORLIST_KEY_ENV = "BIWEEKLY_AUTHORLIST_KEY"
AUTHORLIST_SHEET_ENV = "BIWEEKLY_AUTHORLIST_SHEET"
GOOGLE_SERVICE_FILE_ENV = "GOOGLE_SERVICE_FILE"
SCORE_TIMEOUT_SECONDS = int(os.getenv("BIWEEKLY_SCORE_TIMEOUT_SECONDS", "1800"))

authorlistsheet = "Authorlist"

PLATFORM_FFN = 0
PLATFORM_AO3 = 1
PLATFORM_TAPAS = 2


@dataclass(frozen=True)
class AuthorScoreTask:
    sheet_row: int
    link: str
    platform: int
    platform_name: str


@dataclass(frozen=True)
class AuthorScoreResult:
    sheet_row: int
    link: str
    score: Optional[int]
    status: str = "ok"
    note: str = ""


@dataclass(frozen=True)
class SkippedAuthorRow:
    sheet_row: int
    link: str
    reason: str


@dataclass(frozen=True)
class FallbackScoreRow:
    sheet_row: int
    score: int
    reason: str


@dataclass
class BiweeklyRunResult:
    spreadsheet_key: str
    sheet_name: str
    rank_col: int
    link_col: int
    fallback_col: Optional[int]
    data_row_count: int
    score_tasks: list[AuthorScoreTask]
    score_results: list[AuthorScoreResult]
    skipped_rows: list[SkippedAuthorRow]
    fallback_rows: list[FallbackScoreRow]
    column_values: list[object]
    column_header: str
    dry_run: bool
    target_url: Optional[str] = None

    @property
    def updated_count(self) -> int:
        return sum(1 for result in self.score_results if result.status == "ok")

    @property
    def failed_count(self) -> int:
        return sum(1 for result in self.score_results if result.status != "ok")

    @property
    def skipped_count(self) -> int:
        return len(self.skipped_rows)

    @property
    def fallback_count(self) -> int:
        return len(self.fallback_rows)


def google_client():
    return authorize_google_client()


def sheet(rosterkey, sheetname):
    gc = google_client()
    target = gc.open_by_key(rosterkey).worksheet_by_title(sheetname)
    cells = target.get_all_values(
        include_tailing_empty_rows=False,
        include_tailing_empty=False,
        returnas="matrix",
    )
    return cells, target


def resolve_authorlist_key(rosterkey=None):
    key = rosterkey or os.getenv(AUTHORLIST_KEY_ENV)
    if not key:
        raise RuntimeError(f"Set the {AUTHORLIST_KEY_ENV} environment variable")
    return key


def resolve_authorlist_sheet(sheetname=None):
    return sheetname or os.getenv(AUTHORLIST_SHEET_ENV) or authorlistsheet


def find_columns(headers):
    try:
        rank_col = headers.index("Author rank") + 1
    except ValueError as exc:
        raise ValueError("Could not find required 'Author rank' header") from exc

    for header in ("Links", "Links:"):
        try:
            return rank_col, headers.index(header)
        except ValueError:
            continue

    raise ValueError("Could not find required 'Links' header")


def previous_score_col(headers, rank_col):
    col = rank_col - 2
    if col >= 0 and headers[col] != "":
        return col
    return None


def today_score_header():
    today = date.today()
    return f"{today.month}/{today.day}/{str(today.year)[-2:]}"


def normalize_link(link):
    link = str(link or "").strip()
    return re.sub(r"https?://m\.fanfiction\.net", "https://www.fanfiction.net", link)


def classify_link(link):
    lowered = link.lower()
    if "fanfiction.net" in lowered:
        return PLATFORM_FFN, "fanfiction.net"
    if "archiveofourown.org" in lowered or "archive.transformativeworks.org" in lowered:
        return PLATFORM_AO3, "archiveofourown.org"
    if "tapas.io" in lowered:
        return PLATFORM_TAPAS, "tapas.io"
    return None, None


def plan_score_tasks(cells):
    if not cells:
        raise ValueError("The author sheet is empty")

    rank_col, link_col = find_columns(cells[0])
    tasks = []
    skipped = []

    for sheet_row, row in enumerate(cells[1:], start=2):
        try:
            link = normalize_link(row[link_col])
        except IndexError:
            skipped.append(SkippedAuthorRow(sheet_row, "", "missing link cell"))
            continue

        if link == "":
            skipped.append(SkippedAuthorRow(sheet_row, link, "blank link"))
            continue
        if link.lower() == "ignore":
            skipped.append(SkippedAuthorRow(sheet_row, link, "ignored"))
            continue

        platform, platform_name = classify_link(link)
        if platform is None:
            skipped.append(SkippedAuthorRow(sheet_row, link, "unsupported link"))
            continue

        tasks.append(AuthorScoreTask(sheet_row, link, platform, platform_name))

    return rank_col, link_col, tasks, skipped


async def _fetch_scores_async(tasks: Iterable[AuthorScoreTask], max_concurrency=5):
    import ffwebscrape

    semaphore = asyncio.Semaphore(max_concurrency)
    ao3_restricted = asyncio.Event()
    ao3_restricted_exc = None
    platform_semaphores = {
        PLATFORM_AO3: asyncio.Semaphore(1),
        PLATFORM_TAPAS: asyncio.Semaphore(1),
    }

    async def fetch_one(task):
        async with semaphore:
            platform_semaphore = platform_semaphores.get(task.platform)
            if platform_semaphore is None:
                return await fetch_one_unlocked(task)
            async with platform_semaphore:
                if task.platform == PLATFORM_AO3 and ao3_restricted.is_set():
                    raise ao3_restricted_exc or ffwebscrape.Ao3BotRestrictedError()
                return await fetch_one_unlocked(task)

    async def fetch_one_unlocked(task):
        nonlocal ao3_restricted_exc
        try:
            score = await asyncio.wait_for(
                ffwebscrape.followcount(task.link, task.platform),
                timeout=SCORE_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            return AuthorScoreResult(
                task.sheet_row,
                task.link,
                None,
                "failed",
                f"timed out after {SCORE_TIMEOUT_SECONDS} seconds",
            )
        except ffwebscrape.Ao3BotRestrictedError as exc:
            ao3_restricted_exc = exc
            ao3_restricted.set()
            raise
        except Exception as exc:
            return AuthorScoreResult(task.sheet_row, task.link, None, "failed", repr(exc))

        if score is False or score is None:
            return AuthorScoreResult(task.sheet_row, task.link, None, "failed", "empty result")

        try:
            score = int(score)
        except (TypeError, ValueError):
            return AuthorScoreResult(
                task.sheet_row,
                task.link,
                None,
                "failed",
                f"non-numeric result: {score!r}",
            )

        return AuthorScoreResult(task.sheet_row, task.link, score)

    return list(await asyncio.gather(*(fetch_one(task) for task in tasks)))


def fetch_scores(tasks):
    if not tasks:
        return []
    return asyncio.run(_fetch_scores_async(tasks))


def build_score_column(data_row_count, score_results):
    values = ["" for _ in range(data_row_count)]
    for result in score_results:
        if result.status != "ok":
            continue
        index = result.sheet_row - 2
        if index < 0 or index >= data_row_count:
            raise ValueError(f"Score result row {result.sheet_row} is outside the sheet data range")
        values[index] = result.score
    return values


def parse_score(value):
    value = str(value or "").strip()
    if value == "":
        return None
    try:
        return int(value.replace(",", ""))
    except ValueError:
        return None


def previous_score_for_row(cells, sheet_row, fallback_col):
    if fallback_col is None:
        return None
    try:
        return parse_score(cells[sheet_row - 1][fallback_col])
    except IndexError:
        return None


def apply_score_fallbacks(cells, column_values, score_results, skipped_rows, fallback_col):
    fallback_rows = []
    result_by_row = {result.sheet_row: result for result in score_results}

    for result in score_results:
        if result.status == "ok":
            continue
        fallback = previous_score_for_row(cells, result.sheet_row, fallback_col)
        if fallback is None:
            continue
        column_values[result.sheet_row - 2] = fallback
        fallback_rows.append(FallbackScoreRow(result.sheet_row, fallback, result.status))

    for skipped in skipped_rows:
        if skipped.sheet_row in result_by_row:
            continue
        fallback = previous_score_for_row(cells, skipped.sheet_row, fallback_col)
        if fallback is None:
            continue
        column_values[skipped.sheet_row - 2] = fallback
        fallback_rows.append(FallbackScoreRow(skipped.sheet_row, fallback, skipped.reason))

    return fallback_rows


def build_biweekly_result(
    cells,
    spreadsheet_key,
    sheet_name,
    *,
    score_fetcher: Optional[Callable[[list[AuthorScoreTask]], list[AuthorScoreResult]]] = None,
    dry_run=False,
    target_url=None,
):
    rank_col, link_col, tasks, skipped = plan_score_tasks(cells)
    if score_fetcher is None:
        score_fetcher = fetch_scores
    score_results = score_fetcher(tasks)
    fallback_col = previous_score_col(cells[0], rank_col)
    column_values = build_score_column(len(cells) - 1, score_results)
    fallback_rows = apply_score_fallbacks(cells, column_values, score_results, skipped, fallback_col)
    return BiweeklyRunResult(
        spreadsheet_key=spreadsheet_key,
        sheet_name=sheet_name,
        rank_col=rank_col,
        link_col=link_col,
        fallback_col=fallback_col,
        data_row_count=len(cells) - 1,
        score_tasks=tasks,
        score_results=score_results,
        skipped_rows=skipped,
        fallback_rows=fallback_rows,
        column_values=column_values,
        column_header=today_score_header(),
        dry_run=dry_run,
        target_url=target_url,
    )


def run_biweekly(rosterkey=None, sheetname=None, *, dry_run=False, score_fetcher=None):
    rosterkey = resolve_authorlist_key(rosterkey)
    sheetname = resolve_authorlist_sheet(sheetname)
    cells, target = sheet(rosterkey, sheetname)
    target_url = getattr(getattr(target, "spreadsheet", None), "url", None)
    result = build_biweekly_result(
        cells,
        rosterkey,
        sheetname,
        score_fetcher=score_fetcher,
        dry_run=dry_run,
        target_url=target_url,
    )

    if dry_run:
        return result

    target.insert_cols(result.rank_col - 1, inherit=True)
    target.update_value((1, result.rank_col), result.column_header)
    target.update_col(index=result.rank_col, values=result.column_values, row_offset=1)
    return result


def format_biweekly_summary(result: BiweeklyRunResult):
    failed_results = [r for r in result.score_results if r.status != "ok"]
    failed_rows = [str(r.sheet_row) for r in failed_results]
    skipped_reasons = {}
    for row in result.skipped_rows:
        skipped_reasons[row.reason] = skipped_reasons.get(row.reason, 0) + 1
    summary = [
        f"Updated scores: {result.updated_count}",
        f"Failed scores: {result.failed_count}",
        f"Skipped rows: {result.skipped_count}",
        f"Fallback scores carried forward: {result.fallback_count}",
        f"Data rows checked: {result.data_row_count}",
    ]
    if skipped_reasons:
        reason_text = ", ".join(f"{reason}: {count}" for reason, count in sorted(skipped_reasons.items()))
        summary.append(f"Skipped breakdown: {reason_text}")
    if failed_rows:
        summary.append(f"Failed sheet rows: {', '.join(failed_rows[:15])}")
        if len(failed_rows) > 15:
            summary.append(f"...and {len(failed_rows) - 15} more failed rows")
        summary.append("Failed examples:")
        for result_row in failed_results[:5]:
            note = result_row.note or result_row.status
            summary.append(f"Row {result_row.sheet_row}: {note}; {result_row.link}")
    if result.target_url:
        summary.append(f"Sheet: {result.target_url}")
    if result.dry_run:
        summary.append("Dry run: no sheet changes were written.")
    return "\n".join(summary)


def _main():
    parser = argparse.ArgumentParser(description="Run the Emerald Library biweekly author score update.")
    parser.add_argument("--spreadsheet-key", default=None)
    parser.add_argument("--sheet", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    result = run_biweekly(args.spreadsheet_key, args.sheet, dry_run=args.dry_run)
    print(format_biweekly_summary(result))


if __name__ == "__main__":
    _main()
