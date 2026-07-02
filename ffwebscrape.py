# ffwebscrape.py
# -*- coding: utf-8 -*-
"""
Created on Fri Jan 22 23:04:17 2021
@author: Curious Beats
"""

import os
import re
import random
import asyncio
import time
import threading
from typing import Optional, Tuple
from urllib.parse import urlencode, urlsplit, urlunsplit

import aiohttp
import requests
from bs4 import BeautifulSoup

from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.wait import WebDriverWait
from selenium import webdriver
from selenium.webdriver.support import expected_conditions as EC

from bot_config import require_env

AO3_BOT_RESTRICTED_MESSAGE = (
    "AO3 is restricting bot traffic right now. Please try again in a few hours or days."
)


class Ao3BotRestrictedError(RuntimeError):
    def __init__(self):
        super().__init__(AO3_BOT_RESTRICTED_MESSAGE)


useragents = ['Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2228.0 Safari/537.36', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2227.1 Safari/537.36', 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2227.0 Safari/537.36', 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2227.0 Safari/537.36', 'Mozilla/5.0 (Windows NT 6.3; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2226.0 Safari/537.36', 'Mozilla/5.0 (Windows NT 6.4; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2225.0 Safari/537.36', 'Mozilla/5.0 (Windows NT 6.3; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2225.0 Safari/537.36', 'Mozilla/5.0 (Windows NT 5.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2224.3 Safari/537.36', 'Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/40.0.2214.93 Safari/537.36', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/37.0.2062.124 Safari/537.36', 'Mozilla/5.0 (Windows NT 6.3; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/37.0.2049.0 Safari/537.36', 'Mozilla/5.0 (Windows NT 4.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/37.0.2049.0 Safari/537.36', 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/36.0.1985.67 Safari/537.36', 'Mozilla/5.0 (Windows NT 5.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/36.0.1985.67 Safari/537.36', 'Mozilla/5.0 (X11; OpenBSD i386) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/36.0.1985.125 Safari/537.36', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/36.0.1944.0 Safari/537.36', 'Mozilla/5.0 (Windows NT 5.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/35.0.3319.102 Safari/537.36', 'Mozilla/5.0 (Windows NT 5.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/35.0.2309.372 Safari/537.36', 'Mozilla/5.0 (Windows NT 5.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/35.0.2117.157 Safari/537.36', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/35.0.1916.47 Safari/537.36', 'Mozilla/5.0 (Windows NT 5.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/34.0.1866.237 Safari/537.36', 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/34.0.1847.137 Safari/4E423F', 'Mozilla/5.0 (Windows NT 5.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/34.0.1847.116 Safari/537.36 Mozilla/5.0 (iPad; U; CPU OS 3_2 like Mac OS X; en-us) AppleWebKit/531.21.10 (KHTML, like Gecko) Version/4.0.4 Mobile/7B334b Safari/531.21.10', 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/33.0.1750.517 Safari/537.36', 'Mozilla/5.0 (Windows NT 6.2; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/32.0.1667.0 Safari/537.36', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/32.0.1664.3 Safari/537.36', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_8_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/32.0.1664.3 Safari/537.36', 'Mozilla/5.0 (Windows NT 5.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/31.0.1650.16 Safari/537.36', 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/31.0.1623.0 Safari/537.36', 'Mozilla/5.0 (Windows NT 6.2; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/30.0.1599.17 Safari/537.36', 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/29.0.1547.62 Safari/537.36', 'Mozilla/5.0 (X11; CrOS i686 4319.74.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/29.0.1547.57 Safari/537.36', 'Mozilla/5.0 (Windows NT 6.2; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/29.0.1547.2 Safari/537.36', 'Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/28.0.1468.0 Safari/537.36', 'Mozilla/5.0 (Windows NT 6.2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/28.0.1467.0 Safari/537.36', 'Mozilla/5.0 (Windows NT 6.2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/28.0.1464.0 Safari/537.36', 'Mozilla/5.0 (Windows NT 6.2; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/27.0.1500.55 Safari/537.36', 'Mozilla/5.0 (Windows NT 6.2; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/27.0.1453.93 Safari/537.36', 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/27.0.1453.93 Safari/537.36', 'Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/27.0.1453.93 Safari/537.36', 'Mozilla/5.0 (Windows NT 5.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/27.0.1453.93 Safari/537.36', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_8_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/27.0.1453.93 Safari/537.36', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_7_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/27.0.1453.93 Safari/537.36', 'Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/27.0.1453.90 Safari/537.36', 'Mozilla/5.0 (X11; NetBSD) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/27.0.1453.116 Safari/537.36', 'Mozilla/5.0 (X11; CrOS i686 3912.101.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/27.0.1453.116 Safari/537.36', 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.17 (KHTML, like Gecko) Chrome/24.0.1312.60 Safari/537.17', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_8_2) AppleWebKit/537.17 (KHTML, like Gecko) Chrome/24.0.1309.0 Safari/537.17', 'Mozilla/5.0 (Windows NT 6.2; WOW64) AppleWebKit/537.15 (KHTML, like Gecko) Chrome/24.0.1295.0 Safari/537.15', 'Mozilla/5.0 (Windows NT 6.2; WOW64) AppleWebKit/537.14 (KHTML, like Gecko) Chrome/24.0.1292.0 Safari/537.14']


def _repo_file(name: str) -> Optional[str]:
    path = os.path.join(os.path.dirname(__file__), name)
    if os.path.exists(path):
        return path
    return None


# ----------------------------
# Selenium helpers (unchanged)
# ----------------------------
def setoptions():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    chrome_bin = os.environ.get("GOOGLE_CHROME_BIN")
    if not chrome_bin and os.name == "nt":
        chrome_bin = _repo_file("chrome.exe")
    if chrome_bin:
        options.binary_location = chrome_bin
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-extensions")
    options.add_argument("--proxy-server='direct://'")
    options.add_argument("start-maximized")
    options.add_argument("--proxy-bypass-list=*")
    options.add_argument("--disable-gpu")
    return options


def _make_driver():
    options = setoptions()
    options.add_argument(f"user-agent={random.choice(useragents)}")
    driver_path = os.environ.get("CHROMEDRIVER_PATH")
    if not driver_path and os.name == "nt":
        driver_path = _repo_file("chromedriver.exe")
    chrome_service = Service(driver_path) if driver_path else Service()
    return webdriver.Chrome(options=options, service=chrome_service)


# ----------------------------
# aiohttp helpers
# ----------------------------
def _headers() -> dict:
    return {
        "User-Agent": random.choice(useragents),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
    }


def _weaver_request(url: str):
    params = {
        "apiKey": require_env("WEAVER_API_KEY"),
        "q": url,
    }
    auth = aiohttp.BasicAuth(
        require_env("WEAVER_BASIC_AUTH_USER"),
        require_env("WEAVER_BASIC_AUTH_PASSWORD"),
    )
    endpoint = os.getenv("WEAVER_CRAWL_URL", "https://weaver.fanfic.dev/v0/ffn/crawl")
    return endpoint, params, auth


async def _fetch_text(
    session: aiohttp.ClientSession,
    url: str,
    *,
    params: Optional[dict] = None,
    auth: Optional[aiohttp.BasicAuth] = None,
    timeout_s: int = 20,
    max_retries: int = 3,
    backoff_s: float = 2.0,
) -> Tuple[Optional[str], Optional[int]]:
    """
    Returns (text, status_code). If it ultimately fails, returns (None, None or last_status).
    Handles 429 with Retry-After when present.
    """
    last_status = None

    for attempt in range(1, max_retries + 1):
        try:
            timeout = aiohttp.ClientTimeout(total=timeout_s)
            async with session.get(
                url,
                params=params,
                auth=auth,
                headers=_headers(),
                timeout=timeout,
                allow_redirects=True,
            ) as resp:
                last_status = resp.status

                # Rate limit handling
                if resp.status == 429:
                    retry_after = resp.headers.get("Retry-After")
                    if retry_after:
                        try:
                            sleep_s = int(retry_after)
                        except ValueError:
                            sleep_s = int(backoff_s * attempt)
                    else:
                        sleep_s = int(backoff_s * attempt)
                    await asyncio.sleep(sleep_s)
                    continue

                # For non-200, still read text (some sites return useful HTML)
                text = await resp.text(errors="ignore")
                return text, resp.status

        except (aiohttp.ClientError, asyncio.TimeoutError):
            # exponential-ish backoff
            if attempt < max_retries:
                await asyncio.sleep(backoff_s * attempt)
            continue

    return None, last_status


def _ao3_headers() -> dict:
    return {
        "User-Agent": "Mozilla/5.0 (compatible; curiousbot-biweekly/1.0; Emerald Library Discord bot)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }


def _normalize_ao3_works_url(url: str) -> str:
    url = str(url or "").strip()
    if not url:
        return url

    url = re.sub(r"^http://archive\.transformativeworks\.org", "https://archiveofourown.org", url)
    url = re.sub(r"^https://archive\.transformativeworks\.org", "https://archiveofourown.org", url)

    parts = urlsplit(url)
    if "archiveofourown.org" not in parts.netloc.lower():
        return url.rstrip("/")

    path_parts = [part for part in parts.path.split("/") if part]
    if len(path_parts) >= 2 and path_parts[0] == "users":
        normalized_path = f"/users/{path_parts[1]}"
        if len(path_parts) >= 4 and path_parts[2] == "pseuds":
            normalized_path += f"/pseuds/{path_parts[3]}"
        normalized_path += "/works"
        return urlunsplit(("https", "archiveofourown.org", normalized_path, "", ""))

    return url.rstrip("/") + "/works"


def _is_ao3_retry_or_shield_page(soup: Optional[BeautifulSoup], text: Optional[str]) -> bool:
    if not soup or not text:
        return True
    return soup.select_one("pre") is not None or "Shields are up" in text


def _is_ao3_bot_restricted_response(text: Optional[str], status: Optional[int]) -> bool:
    if status == 418:
        return True
    if not text:
        return False

    normalized = text.casefold().replace("&apos;", "'").replace("&#39;", "'")
    normalized = normalized.replace("\u2019", "'")
    return "418 i'm a teapot" in normalized or "418 im a teapot" in normalized


def _raise_if_ao3_bot_restricted(text: Optional[str], status: Optional[int]):
    if _is_ao3_bot_restricted_response(text, status):
        raise Ao3BotRestrictedError()


AO3_PROFILE_TIMEOUT_SECONDS = int(os.getenv("AO3_PROFILE_TIMEOUT_SECONDS", "1800"))
AO3_REQUEST_INTERVAL_SECONDS = float(os.getenv("AO3_REQUEST_INTERVAL_SECONDS", "1.0"))
_ao3_request_lock = threading.Lock()
_last_ao3_request_at = 0.0


def _wait_for_ao3_slot():
    global _last_ao3_request_at
    if AO3_REQUEST_INTERVAL_SECONDS <= 0:
        return
    with _ao3_request_lock:
        now = time.monotonic()
        wait_s = AO3_REQUEST_INTERVAL_SECONDS - (now - _last_ao3_request_at)
        if wait_s > 0:
            time.sleep(wait_s)
        _last_ao3_request_at = time.monotonic()


def _ao3_page_url(url: str, page: Optional[int] = None, *, view_adult=False) -> str:
    parts = urlsplit(url)
    query = {}
    if view_adult:
        query["view_adult"] = "true"
    if page is not None:
        query["page"] = str(page)
    return urlunsplit((parts.scheme or "https", parts.netloc, parts.path, urlencode(query), ""))


def _ao3_url_candidates(url: str, page: Optional[int] = None) -> list[str]:
    works_url = _normalize_ao3_works_url(url)
    candidates = [_ao3_page_url(works_url, page)]
    adult_url = _ao3_page_url(works_url, page, view_adult=True)
    if adult_url not in candidates:
        candidates.append(adult_url)
    return candidates


def _fetch_ao3_text_sync(
    session: requests.Session,
    url: str,
    timeout_s=12,
    max_retries=3,
    retry_none=True,
):
    last_status = None
    retryable_statuses = {500, 502, 503, 504, 520, 521, 522, 523, 524, 525}
    for attempt in range(1, max_retries + 1):
        try:
            _wait_for_ao3_slot()
            response = session.get(
                url,
                timeout=(8, timeout_s),
                allow_redirects=True,
            )
            last_status = response.status_code
            _raise_if_ao3_bot_restricted(response.text, response.status_code)
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                try:
                    sleep_s = int(retry_after) if retry_after else attempt * 2
                except ValueError:
                    sleep_s = attempt * 2
                time.sleep(sleep_s)
                continue
            if (
                response.status_code in retryable_statuses
                or "Shields are up" in response.text
            ) and attempt < max_retries:
                time.sleep(attempt * 2)
                continue
            return response.text, response.status_code
        except requests.RequestException:
            if retry_none and attempt < max_retries:
                time.sleep(attempt * 2)
                continue
            break

    return None, last_status


def _ao3_soup_sync(url: str):
    with requests.Session() as session:
        session.headers.update(_ao3_headers())
        text, status = _fetch_ao3_text_sync(session, _ao3_url_candidates(url)[0])
    _raise_if_ao3_bot_restricted(text, status)
    soup = BeautifulSoup(text, "lxml") if text else None
    return soup, text, status


async def _ao3_soup(url: str):
    return await asyncio.to_thread(_ao3_soup_sync, url)


def _parse_ao3_kudos_from_soup(soup: BeautifulSoup):
    values = []
    for item in soup.select("dd.kudos"):
        text = item.get_text(strip=True)
        if text:
            values.append(int(re.sub(",", "", text)))
    return values


def _ao3_followcount_sync(url: str) -> int:
    url = _normalize_ao3_works_url(url)
    all_kudos = []
    started = time.monotonic()

    with requests.Session() as session:
        session.headers.update(_ao3_headers())
        last_status = None
        for candidate_url in _ao3_url_candidates(url):
            text, status = _fetch_ao3_text_sync(session, candidate_url, retry_none=False)
            _raise_if_ao3_bot_restricted(text, status)
            soup = BeautifulSoup(text, "lxml") if text else None
            last_status = status
            if status == 200 and not _is_ao3_retry_or_shield_page(soup, text):
                break
            if status is None or status == 404:
                raise RuntimeError(f"AO3 returned status {status}")
        else:
            raise RuntimeError(f"AO3 returned status {last_status}")

        all_kudos.extend(_parse_ao3_kudos_from_soup(soup))
        pagination = soup.select_one("ol.pagination.actions")
        page_nums = []
        if pagination is not None:
            for link in pagination.select("a"):
                label = link.get_text(strip=True)
                if label.isdigit():
                    page_nums.append(int(label))

        pages = max(page_nums) if page_nums else 1
        for page in range(2, pages + 1):
            if time.monotonic() - started > AO3_PROFILE_TIMEOUT_SECONDS:
                raise RuntimeError(f"AO3 profile timed out after {AO3_PROFILE_TIMEOUT_SECONDS} seconds")
            last_status = None
            for candidate_url in _ao3_url_candidates(url, page):
                text, status = _fetch_ao3_text_sync(session, candidate_url, retry_none=True)
                _raise_if_ao3_bot_restricted(text, status)
                soup = BeautifulSoup(text, "lxml") if text else None
                last_status = status
                if status == 200 and not _is_ao3_retry_or_shield_page(soup, text):
                    break
            else:
                raise RuntimeError(f"AO3 returned status {last_status} on page {page}")
            all_kudos.extend(_parse_ao3_kudos_from_soup(soup))

    return sum(all_kudos)


async def _ao3_followcount(url: str) -> int:
    return await asyncio.to_thread(_ao3_followcount_sync, url)


# ----------------------------
# Public API: get_story_info
# ----------------------------
async def get_story_info(url: str, platform: int):
    """
    platform:
      0 = ff.net (via weaver endpoint)
      1 = AO3
    """
    if platform == 0:
        # ff.net via weaver proxy
        endpoint, params, auth = _weaver_request(url)

        async with aiohttp.ClientSession() as session:
            text, status = await _fetch_text(
                session,
                endpoint,
                params=params,
                auth=auth,
                timeout_s=25,
                max_retries=4,
            )
        if not text or status != 200:
            return None, None

        soup = BeautifulSoup(text, "lxml")
        title_element = soup.select_one("#profile_top b")
        fandom_element = soup.select_one("#pre_story_links a")

        title = title_element.get_text(strip=True) if title_element else None
        fandom = fandom_element.get_text(strip=True) if fandom_element else None
        return fandom, title

    elif platform == 1:
        # AO3 - works list to infer fandom + title
        url = _normalize_ao3_works_url(url)
        soup, text, status = await _ao3_soup(url)

        # If blocked / weird response, fall back to selenium
        if status != 200 or _is_ao3_retry_or_shield_page(soup, text):
            driver = _make_driver()
            try:
                driver.get(url)
                soup = BeautifulSoup(driver.page_source, "lxml")
            finally:
                driver.quit()

        fandom_elements = soup.select("dd.fandom a.tag")
        fandoms = [tag.get_text(strip=True) for tag in fandom_elements[:2]]
        fandom = ", ".join(fandoms) if fandoms else None

        title_element = soup.select_one("h2.title")
        title = title_element.get_text(strip=True) if title_element else None
        return fandom, title

    return None, None


# ----------------------------
# Public API: followcount
# ----------------------------
async def followcount(url: str, platform: int):
    """
    platform:
      0 = ff.net (via weaver endpoint)
      1 = AO3 (sum kudos across works pages)
      2 = tapas (uses page attribute data-title)
    """

    # selectors
    if platform == 0:
        element = "div.z-list.mystories"
    elif platform == 1:
        element = "dd.kudos"
        url = _normalize_ao3_works_url(url)
    elif platform == 2:
        element = "li.custom-tooltip"
    else:
        return 0

    list_header = []

    # ---------- FFN ----------
    if platform == 0:
        endpoint, params, auth = _weaver_request(url)

        async with aiohttp.ClientSession() as session:
            text, status = await _fetch_text(
                session,
                endpoint,
                params=params,
                auth=auth,
                timeout_s=25,
                max_retries=4,
            )

        if not text:
            # emulate your "return 3" after multiple failures
            return 3

        soup = BeautifulSoup(text, "lxml")
        header = soup.select(element)

        # parse follows from each story block
        for items in header:
            try:
                follows = items.get_text().split()
                if "Complete" in follows:
                    list_header.append(follows[follows.index("Favs:") + 1])
                else:
                    list_header.append(follows[follows.index("Follows:") + 1])
            except Exception:
                continue

        num_follows_list = [int(re.sub(",", "", x)) for x in list_header if x]
        return sum(num_follows_list)

    # ---------- AO3 ----------
    if platform == 1:
        return await _ao3_followcount(url)

    # ---------- Tapas ----------
    async with aiohttp.ClientSession() as session:
        text, status = await _fetch_text(session, url, timeout_s=20, max_retries=3)

    soup = BeautifulSoup(text, "lxml") if text else None

    if platform == 2:
        # if blocked/bad response -> selenium fallback
        if (not text) or (status != 200) or (soup is None):
            driver = _make_driver()
            try:
                driver.get(url)
                soup = BeautifulSoup(driver.page_source, "lxml")
            finally:
                driver.quit()

        if not soup:
            return 0

        header = soup.select(element)
        for items in header:
            try:
                follows = items["data-title"].split()[0]
                follows = int(re.sub(",", "", follows))
                return follows
            except Exception:
                continue

        return 0

    return 0
