import unittest
from unittest.mock import patch

import ffwebscrape


class Ao3UrlNormalizationTests(unittest.TestCase):
    def test_ao3_author_urls_normalize_to_works_route(self):
        cases = {
            "https://archiveofourown.org/users/EmeraldEclipse": "https://archiveofourown.org/users/EmeraldEclipse/works",
            "https://archiveofourown.org/users/EmeraldEclipse/works": "https://archiveofourown.org/users/EmeraldEclipse/works",
            "https://archiveofourown.org/users/EmeraldEclipse/profile": "https://archiveofourown.org/users/EmeraldEclipse/works",
            "https://archive.transformativeworks.org/users/EmeraldEclipse/works": "https://archiveofourown.org/users/EmeraldEclipse/works",
            "https://archiveofourown.org/users/Author/pseuds/Pseud/works": "https://archiveofourown.org/users/Author/pseuds/Pseud/works",
        }

        for original, expected in cases.items():
            with self.subTest(original=original):
                self.assertEqual(ffwebscrape._normalize_ao3_works_url(original), expected)

    def test_ao3_candidates_keep_works_route_as_fallback(self):
        self.assertEqual(
            ffwebscrape._ao3_url_candidates("https://archiveofourown.org/users/EmeraldEclipse/works"),
            [
                "https://archiveofourown.org/users/EmeraldEclipse/works",
                "https://archiveofourown.org/users/EmeraldEclipse/works?view_adult=true",
            ],
        )

    def test_ao3_page_url_includes_adult_view_and_page(self):
        self.assertEqual(
            ffwebscrape._ao3_page_url("https://archiveofourown.org/users/EmeraldEclipse/works"),
            "https://archiveofourown.org/users/EmeraldEclipse/works",
        )
        self.assertEqual(
            ffwebscrape._ao3_page_url("https://archiveofourown.org/users/EmeraldEclipse/works", 2),
            "https://archiveofourown.org/users/EmeraldEclipse/works?page=2",
        )
        self.assertEqual(
            ffwebscrape._ao3_page_url(
                "https://archiveofourown.org/users/EmeraldEclipse/works",
                2,
                view_adult=True,
            ),
            "https://archiveofourown.org/users/EmeraldEclipse/works?view_adult=true&page=2",
        )


class Ao3RetryPolicyTests(unittest.TestCase):
    def test_first_page_none_fails_fast_without_retry_path(self):
        calls = []

        def fake_fetch(_session, url, **kwargs):
            calls.append((url, kwargs))
            return None, None

        with patch("ffwebscrape._fetch_ao3_text_sync", side_effect=fake_fetch):
            with self.assertRaisesRegex(RuntimeError, "AO3 returned status None"):
                ffwebscrape._ao3_followcount_sync("https://archiveofourown.org/users/MissingAuthor")

        self.assertEqual(len(calls), 1)
        self.assertFalse(calls[0][1]["retry_none"])

    def test_first_page_404_fails_fast_without_adult_fallback(self):
        calls = []

        def fake_fetch(_session, url, **kwargs):
            calls.append((url, kwargs))
            return "<html></html>", 404

        with patch("ffwebscrape._fetch_ao3_text_sync", side_effect=fake_fetch):
            with self.assertRaisesRegex(RuntimeError, "AO3 returned status 404"):
                ffwebscrape._ao3_followcount_sync("https://archiveofourown.org/users/MissingAuthor")

        self.assertEqual(len(calls), 1)
        self.assertFalse(calls[0][1]["retry_none"])

    def test_page_none_uses_retry_path(self):
        first_page = """
        <html>
            <body>
                <dd class="kudos">1</dd>
                <ol class="pagination actions"><li><a href="?page=2">2</a></li></ol>
            </body>
        </html>
        """
        calls = []

        def fake_fetch(_session, url, **kwargs):
            calls.append((url, kwargs))
            if "page=2" in url:
                return None, None
            return first_page, 200

        with patch("ffwebscrape._fetch_ao3_text_sync", side_effect=fake_fetch):
            with self.assertRaisesRegex(RuntimeError, "AO3 returned status None on page 2"):
                ffwebscrape._ao3_followcount_sync("https://archiveofourown.org/users/ExistingAuthor")

        first_page_calls = [call for call in calls if "page=2" not in call[0]]
        page_two_calls = [call for call in calls if "page=2" in call[0]]
        self.assertEqual(len(first_page_calls), 1)
        self.assertFalse(first_page_calls[0][1]["retry_none"])
        self.assertTrue(page_two_calls)
        self.assertTrue(all(call[1]["retry_none"] for call in page_two_calls))


class FakeAo3Response:
    def __init__(self, text, status_code):
        self.text = text
        self.status_code = status_code
        self.headers = {}


class FakeAo3Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


class Ao3BotRestrictedTests(unittest.TestCase):
    def test_teapot_status_is_bot_restricted(self):
        self.assertTrue(ffwebscrape._is_ao3_bot_restricted_response("", 418))

    def test_teapot_body_is_bot_restricted(self):
        self.assertTrue(
            ffwebscrape._is_ao3_bot_restricted_response("<html>418 I'm a teapot</html>", 200)
        )

    def test_fetch_teapot_status_raises_without_retries(self):
        session = FakeAo3Session([FakeAo3Response("418 I'm a teapot", 418)])

        with self.assertRaises(ffwebscrape.Ao3BotRestrictedError):
            ffwebscrape._fetch_ao3_text_sync(session, "https://archiveofourown.org", max_retries=3)

        self.assertEqual(len(session.calls), 1)

    def test_fetch_teapot_body_raises_without_retries(self):
        session = FakeAo3Session([FakeAo3Response("<html>418 I'm a teapot</html>", 200)])

        with self.assertRaises(ffwebscrape.Ao3BotRestrictedError):
            ffwebscrape._fetch_ao3_text_sync(session, "https://archiveofourown.org", max_retries=3)

        self.assertEqual(len(session.calls), 1)

    def test_followcount_teapot_aborts_before_adult_fallback(self):
        calls = []

        def fake_fetch(_session, url, **kwargs):
            calls.append((url, kwargs))
            return "<html>418 I'm a teapot</html>", 200

        with patch("ffwebscrape._fetch_ao3_text_sync", side_effect=fake_fetch):
            with self.assertRaises(ffwebscrape.Ao3BotRestrictedError):
                ffwebscrape._ao3_followcount_sync("https://archiveofourown.org/users/MissingAuthor")

        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
