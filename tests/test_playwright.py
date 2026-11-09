import contextlib
import io
import json
import threading
import unittest
from unittest.mock import MagicMock, patch

from agent import books, llm, tools


class PlaywrightTests(unittest.TestCase):
    def test_model_timing_log_does_not_include_request_content(self):
        response = MagicMock(status_code=200)
        response.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        output = io.StringIO()
        credential = "test-credential-value"
        user_text = "test-private-prompt"
        with patch.object(llm, "API_KEY", credential), \
             patch.object(llm.requests, "post", return_value=response), \
             contextlib.redirect_stdout(output):
            self.assertEqual(llm.chat([{"role": "user", "content": user_text}])["content"], "ok")
        self.assertIn("耗时", output.getvalue())
        self.assertNotIn(credential, output.getvalue())
        self.assertNotIn(user_text, output.getvalue())

    def test_automatic_browser_channel_falls_back(self):
        playwright = MagicMock()
        browser = MagicMock()
        playwright.chromium.launch.side_effect = [RuntimeError("unavailable"), browser]
        with patch.object(tools.os, "name", "nt"):
            result = tools._launch_browser(playwright, "", [])
        self.assertIs(result, browser)
        self.assertEqual(
            [call.kwargs["channel"] for call in playwright.chromium.launch.call_args_list],
            ["msedge", "chrome"],
        )

    def test_browser_sessions_are_isolated_between_threads(self):
        barrier = threading.Barrier(2)
        sessions = []

        def worker():
            with tools.browser_session() as session:
                sessions.append(session)
                barrier.wait(timeout=5)

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        self.assertFalse(barrier.broken)
        self.assertEqual(len(sessions), 2)
        self.assertIsNot(sessions[0], sessions[1])

    def test_job_links_support_html_and_structured_data(self):
        html = '''
        <a href='/job/1'><span>机械工程师</span></a>
        <button data-url='../job/2' aria-label='电气工程师'></button>
        <a href="/job/1">重复链接</a>
        <script type="application/ld+json">
          {"@graph": [{"@type": "https://schema.org/JobPosting", "title": "软件工程师", "url": "/detail/3"},
                      {"@type": "JobPosting", "title": "无链接的岗位", "url": ""}]}
        </script>
        '''
        jobs = tools._collect_jobs(html, "https://example.test/careers/")
        self.assertEqual([job["title"] for job in jobs], ["机械工程师", "电气工程师", "软件工程师"])
        self.assertEqual([job["url"] for job in jobs], [
            "https://example.test/job/1", "https://example.test/job/2", "https://example.test/detail/3",
        ])

    def test_campus_link_accepts_single_quoted_relative_url(self):
        html = "<a href='../campus'>校园招聘</a>"
        self.assertEqual(
            tools._find_campus_url(html, "https://example.test/about/"),
            "https://example.test/campus",
        )

    def test_certificate_error_does_not_use_fallback(self):
        error = tools._PageRenderError("certificate_error", "证书验证失败")
        with patch.object(tools, "_url_resolves", return_value=True), \
             patch.object(tools, "_render_dom_playwright", side_effect=error), \
             patch.object(tools, "_render_dom") as fallback:
            result = tools.render_page("https://example.test")
        self.assertEqual(result["error_type"], "certificate_error")
        self.assertFalse(result.get("unreachable", False))
        fallback.assert_not_called()

    def test_timeout_uses_fallback_and_reports_duration(self):
        error = tools._PageRenderError("timeout", "浏览器加载页面超时")
        html = "<html><title>Jobs</title><body>" + "招聘信息" * 20 + "</body></html>"
        with patch.object(tools, "_url_resolves", return_value=True), \
             patch.object(tools, "_render_dom_playwright", side_effect=error), \
             patch.object(tools, "_render_dom", return_value=html):
            result = tools.render_page("https://example.test")
        self.assertEqual(result["render_method"], "browser_fallback")
        self.assertGreaterEqual(result["render_duration_ms"], 0)

    def test_empty_content_is_not_reported_as_dns_failure(self):
        with patch.object(tools, "_url_resolves", return_value=True), \
             patch.object(tools, "_render_dom_playwright", return_value="<html><body></body></html>"), \
             patch.object(tools, "_render_dom", side_effect=RuntimeError("unavailable")):
            result = tools.render_page("https://example.test")
        self.assertEqual(result["error_type"], "empty_content")
        self.assertFalse(result.get("unreachable", False))

    def test_empty_content_uses_browser_fallback(self):
        html = "<html><body>" + "招聘信息" * 20 + "</body></html>"
        with patch.object(tools, "_url_resolves", return_value=True), \
             patch.object(tools, "_render_dom_playwright", return_value="<html><body></body></html>"), \
             patch.object(tools, "_render_dom", return_value=html) as fallback:
            result = tools.render_page("https://example.test")
        self.assertEqual(result["render_method"], "browser_fallback")
        fallback.assert_called_once()

    def test_browser_session_reuses_browser_and_closes_contexts(self):
        browser = MagicMock()
        contexts = [MagicMock(), MagicMock()]
        browser.new_context.side_effect = contexts
        for context in contexts:
            page = context.new_page.return_value
            page.title.return_value = "Example"
            page.content.return_value = "<html><body>content</body></html>"
        with patch("playwright.sync_api.sync_playwright") as playwright_factory, \
             patch.object(tools, "_launch_browser", return_value=browser) as launch:
            with tools.browser_session():
                tools._render_dom_playwright("https://example.test/a")
                tools._render_dom_playwright("https://example.test/b")
            launch.assert_called_once()
        for context in contexts:
            context.close.assert_called_once()
            self.assertNotIn("ignore_https_errors", browser.new_context.call_args.kwargs)
        browser.close.assert_called_once()
        playwright_factory.return_value.start.return_value.stop.assert_called_once()

    def test_requests_download_timeout_is_seconds(self):
        browser = MagicMock()
        context = browser.new_context.return_value
        context.cookies.return_value = []
        context.new_page.return_value.url = "https://example.test/book"
        context.new_page.return_value.content.return_value = "<html><title>Book</title></html>"
        response = MagicMock()
        response.status_code = 200
        response.headers = {"Content-Length": "5"}
        response.iter_content.return_value = [b"%PDF-"]
        with patch("playwright.sync_api.sync_playwright"), \
             patch.object(books, "_launch_browser", return_value=browser), \
             patch.object(books.requests, "get") as get:
            get.return_value.__enter__.return_value = response
            status, content = books._browser_download("https://example.test/book", "https://example.test/file")
        self.assertEqual((status, content), (200, b"%PDF-"))
        self.assertEqual(get.call_args.kwargs["timeout"], 90)
        browser.close.assert_called_once()

    def test_bilibili_waits_for_results_without_disabling_certificate_checks(self):
        browser = MagicMock()
        context = browser.new_context.return_value
        page = context.new_page.return_value
        page.evaluate.return_value = json.dumps({"items": [{"bvid": "BV123", "play": 1}]})
        with patch("playwright.sync_api.sync_playwright"), \
             patch.object(tools, "_launch_browser", return_value=browser):
            raw = tools._render_bilibili_search_pinia("https://example.test", wait_ms=100)
        self.assertIn("BV123", raw)
        page.wait_for_function.assert_called_once()
        self.assertNotIn("ignore_https_errors", browser.new_context.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
