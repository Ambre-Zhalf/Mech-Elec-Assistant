import concurrent.futures
import contextlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

from agent import books


MIRROR = "https://zh.834101.ru"
MIRROR_INDEX = "https://zz.sodanav.com/"

ENTRIES_HTML = """
<section id="entries">
  <div class="grid3">
    <div class="card entry main">
      <h3>Z-Library官网入口<span class="tag">推荐</span></h3>
      <p class="d">✅ 目前正常，需梯</p>
      <div class="b">
        <a class="btn" href="https://z-lib.sk/" target="_blank">官网入口 1</a>
        <a class="btn ghost" href="https://z-lib.by" target="_blank">官网入口 2</a>
      </div>
    </div>
    <div class="card entry">
      <h3>Z-Library镜像入口</h3>
      <p class="d">✅ 目前正常，会重定向</p>
      <div class="b">
        <a class="btn" href="https://zlib.re/" target="_blank">镜像一</a>
        <a class="btn ghost" href="https://zlib.ch" target="_blank">镜像二</a>
      </div>
    </div>
    <div class="card entry">
      <h3>🔥 OLIB图书馆</h3>
      <div class="b"><a class="btn hot" href="https://olibz.wwwnav.com/" target="_blank">立即访问</a></div>
    </div>
  </div>
</section>
"""

BOOK_HTML = """
<z-bookcard href='/book/123/test' download='/dl/123/old'
 publisher='测试出版社' year='2026' language='Chinese' extension='pdf' filesize='1 MB'>
 <div class='title' slot='title'><span>高等数学</span></div>
 <div slot='author'>测试作者</div>
</z-bookcard>
"""


def _response(status=200, headers=None, body=b"", encoding="utf-8"):
    return MagicMock(
        status_code=status,
        headers=headers or {},
        content=body,
        encoding=encoding,
        is_redirect=300 <= status < 400,
        url=MIRROR_INDEX,
    )


class BookTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.real_discover_mirrors = books._discover_mirrors
        for patcher in (
            patch.object(books, "BOOKS_DIR", str(self.directory)),
            patch.object(books, "ZBOOK_BASE_URL", ""),
            patch.object(books, "_discover_mirrors", return_value=[]),
            patch.object(books, "BOOK_STORAGE_STATE", ""),
            patch.dict(books._MIRROR_CACHE, {"t": 0.0, "list": None}, clear=True),
            patch.dict(books._SESSION_STATES, {}, clear=True),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_default_mirror_is_the_fallback_address(self):
        self.assertEqual(books.DEFAULT_MIRROR_URL, MIRROR)
        self.assertEqual(books.MIRROR_INDEX_URL, MIRROR_INDEX)

    def test_mirror_index_parses_the_domestic_entry_card(self):
        self.assertEqual(books._parse_mirror_index(ENTRIES_HTML, MIRROR_INDEX), [
            "https://zlib.re", "https://zlib.ch",
        ])

    def test_mirror_index_never_returns_the_official_entries(self):
        mirrors = books._parse_mirror_index(ENTRIES_HTML, MIRROR_INDEX)
        for official in ("https://z-lib.sk", "https://z-lib.by", "https://olibz.wwwnav.com"):
            self.assertNotIn(official, mirrors)

    def test_mirror_links_fallback_matches_button_labels(self):
        html = ('<a class="btn" href="https://zlib.re/">镜像一</a>'
                '<a href="https://zlib.ch">镜像二</a>'
                '<a href="https://nav.example/">镜像已更新，最新入口可在此查看</a>')
        self.assertEqual(books._parse_mirror_index(html, MIRROR_INDEX), [])
        self.assertEqual(books._parse_mirror_links(html, MIRROR_INDEX), [
            "https://zlib.re", "https://zlib.ch",
        ])

    def test_page_html_decodes_utf8_despite_iso_8859_1_header(self):
        response = _response(body="<h3>镜像入口</h3>".encode("utf-8"), encoding="ISO-8859-1")
        self.assertEqual(books._page_html(response), "<h3>镜像入口</h3>")

    def test_mirror_doorway_is_resolved_to_the_site_it_lands_on(self):
        redirect = _response(302, {"Location": "https://zh.834101.ru/"})
        landing = _response(503)
        with patch.object(books, "_get", side_effect=[redirect, landing]) as get:
            self.assertEqual(books._resolve_mirror_origin("https://zlib.re"), MIRROR)
        self.assertEqual([call.args[0] for call in get.call_args_list], [
            "https://zlib.re", "https://zh.834101.ru/",
        ])

    def test_discovery_returns_empty_when_the_index_is_unreachable(self):
        with patch.object(books, "_get", side_effect=requests.ConnectionError()):
            self.assertEqual(books._discover_mirrors(), [])

    def test_unreachable_doorway_is_dropped_instead_of_used_as_base(self):
        with patch.object(books, "_get", side_effect=requests.ConnectionError()):
            self.assertEqual(books._resolve_mirror_origin("https://zlib.re"), "")

    def test_discovery_resolves_each_doorway_and_drops_duplicates(self):
        with patch.object(books, "_get", return_value=_response(body=ENTRIES_HTML.encode("utf-8"))), \
             patch.object(books, "_discover_mirrors", self.real_discover_mirrors), \
             patch.object(books, "_resolve_mirror_origin", return_value=MIRROR) as resolve:
            self.assertEqual(books._discover_mirrors(), [MIRROR])
        self.assertEqual(resolve.call_count, 2)

    def test_candidate_bases_puts_discovered_mirrors_before_the_fallback(self):
        with patch.object(books, "_discover_mirrors", return_value=["https://a.example"]), \
             patch.object(books, "ZBOOK_BASE_URL", MIRROR), \
             patch.object(books.time, "monotonic", return_value=1000):
            self.assertEqual(books._candidate_bases(), ["https://a.example", MIRROR])

    def test_candidate_bases_caches_the_discovered_list(self):
        with patch.object(books, "_discover_mirrors", return_value=["https://a.example"]) as discover, \
             patch.object(books.time, "monotonic", return_value=1000):
            books._candidate_bases()
            books._candidate_bases()
        discover.assert_called_once()

    def test_candidate_bases_ignores_an_invalid_fallback(self):
        for value in ("", "javascript:alert(1)", "https://user:password@example.test"):
            with self.subTest(value=value), patch.object(books, "ZBOOK_BASE_URL", value), \
                 patch.object(books.time, "monotonic", return_value=1000):
                self.assertEqual(books._candidate_bases(), [])

    def test_invalid_and_credential_bearing_origins_are_rejected(self):
        for url in ("http://[", "javascript:alert(1)", "https://user:password@example.test"):
            with self.subTest(url=url):
                self.assertEqual(books._origin(url), "")

    def test_modern_book_cards_preserve_metadata_and_resolve_links(self):
        item = books._parse_book_results(BOOK_HTML, "https://canonical.example/s/test")[0]
        self.assertEqual(item["title"], "高等数学")
        self.assertEqual(item["author"], "测试作者")
        self.assertEqual(item["extension"], "pdf")
        self.assertEqual(item["url"], "https://canonical.example/book/123/test")
        self.assertEqual(item["download"], "https://canonical.example/dl/123/old")

    def test_book_page_title_removes_mirror_download_suffix(self):
        self.assertEqual(books._parse_title("<title>呐喊 | 鲁迅 | download on Z-Library</title>"), "呐喊 | 鲁迅")

    def test_search_uses_canonical_url_and_survives_a_blocked_base(self):
        with patch.object(books, "_candidate_bases", return_value=["https://a.example", "https://b.example"]), \
             patch.object(books, "_fetch_page", side_effect=[
                 books._BookAccessError("镜像站要求浏览器验证"),
                 (BOOK_HTML, "https://canonical.example/s/test"),
             ]) as fetch:
            results = books.search_books("书名/版本", max_results=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["url"], "https://canonical.example/book/123/test")
        self.assertIn("%2F", fetch.call_args.args[0])

    def test_search_supports_legacy_anchors(self):
        html = "<a href='/book/42/name'><span>书名</span></a><a href='/login'>登录</a>"
        with patch.object(books, "_candidate_bases", return_value=["https://a.example"]), \
             patch.object(books, "_fetch_page", return_value=(html, "https://a.example/s/test")):
            self.assertEqual(books.search_books("书名"), [{"title": "书名", "url": "https://a.example/book/42/name"}])

    def test_no_results_and_unavailable_pages_have_different_outcomes(self):
        with patch.object(books, "_candidate_bases", return_value=["https://a.example"]), \
             patch.object(books, "_fetch_page", return_value=("<p>No books found</p>", "https://a.example")):
            self.assertEqual(books.search_books("没有的书"), [])
        with patch.object(books, "_candidate_bases", return_value=["https://a.example"]), \
             patch.object(books, "_fetch_page", return_value=("<script>No books found</script>", "https://a.example")):
            with self.assertRaisesRegex(RuntimeError, "未解析到书目"):
                books.search_books("书名")

    def test_unexpected_errors_do_not_expose_request_details(self):
        private = "test-private-value"
        logs = []
        with patch.object(books, "_candidate_bases", return_value=["https://a.example"]), \
             patch.object(books, "_fetch_page", side_effect=RuntimeError(private)):
            with self.assertRaises(RuntimeError) as raised:
                books.search_books("书名", log_cb=logs.append)
        self.assertNotIn(private, str(raised.exception))
        self.assertNotIn(private, "\n".join(logs))

    def test_known_challenges_are_not_results(self):
        for title in ("Access Denied | DiamWall", "Verifying your browser | DiamWall", "正在打开镜像 | DiamWall", "Checking your browser"):
            with self.subTest(title=title), self.assertRaises(books._BookAccessError):
                books._ensure_not_blocked(f"<title>{title}</title>")

    def test_browser_state_is_reused_for_requested_and_redirected_origins(self):
        browser = MagicMock()
        context = browser.new_context.return_value
        context.storage_state.return_value = {"cookies": [], "origins": []}
        context.pages = [MagicMock(url="https://canonical.example/s/test")]
        with patch("playwright.sync_api.sync_playwright"), \
             patch.object(books, "_launch_browser", return_value=browser):
            with books._browser_context("https://a.example/s/test"):
                pass
            with books._browser_context("https://canonical.example/book/1/test"):
                pass
        self.assertEqual(browser.new_context.call_args.kwargs["storage_state"], {"cookies": [], "origins": []})
        self.assertEqual(browser.close.call_count, 2)
        self.assertEqual(context.close.call_count, 2)
        self.assertNotIn("ignore_https_errors", browser.new_context.call_args.kwargs)

    def test_download_refreshes_link_and_falls_back_after_html_response(self):
        context = MagicMock()
        context.new_page.return_value.url = "https://a.example/book/123/test"
        context.cookies.return_value = [{"name": "session", "value": "test-value", "domain": "a.example", "path": "/", "secure": True}]
        context.request.get.return_value.status = 200
        context.request.get.return_value.body.return_value = b"%PDF-browser"
        response = MagicMock(status_code=200, headers={"Content-Length": "100"})
        response.iter_content.return_value = [b"<html>Login required</html>"]
        with patch.object(books, "_browser_context", return_value=contextlib.nullcontext(context)), \
             patch.object(books, "_open_page", return_value='<a href="/fresh.pdf">下载</a>'), \
             patch.object(books.requests, "get") as get:
            get.return_value.__enter__.return_value = response
            status, content = books._browser_download("https://a.example/book/123/test", "https://a.example/old.pdf")
        self.assertEqual((status, content), (200, b"%PDF-browser"))
        self.assertEqual(get.call_args.args[0], "https://a.example/fresh.pdf")
        cookie = list(get.call_args.kwargs["cookies"])[0]
        self.assertEqual((cookie.domain, cookie.path, cookie.secure), ("a.example", "/", True))

    def test_download_switches_mirror_without_forwarding_old_download_url(self):
        progress = []
        with patch.object(books, "_candidate_bases", return_value=["https://b.example"]), \
             patch.object(books, "_browser_download", side_effect=[(403, b"access denied"), (200, b"%PDF-test")]) as download:
            info = books.download_book("https://a.example/book/123/test?session=old", "https://a.example/dl/old", title="书名", progress_cb=progress.append)
        self.assertEqual(download.call_args.args, ("https://b.example/book/123/test", None))
        self.assertEqual((self.directory / info["filename"]).read_bytes(), b"%PDF-test")
        self.assertEqual(progress[-1], 100)

    def test_browser_download_uses_native_download_for_dl_page(self):
        context = MagicMock()
        page = context.new_page.return_value
        page.url = "https://a.example/book/123/test"
        context.cookies.return_value = []
        with patch.object(books, "_browser_context", return_value=contextlib.nullcontext(context)), \
             patch.object(books, "_open_page", return_value='<a href="/dl/123/fresh">PDF</a>'), \
             patch.object(books.requests, "get") as get, \
             patch.object(books, "_native_download", return_value=(200, b"%PDF-native")) as native:
            self.assertEqual(books._browser_download("https://a.example/book/123/test", None), (200, b"%PDF-native"))
        get.assert_not_called()
        context.request.get.assert_not_called()
        self.assertIs(native.call_args.args[0], page)
        self.assertEqual(native.call_args.args[1], "https://a.example/dl/123/fresh")

    def test_native_download_receives_file_from_browser_event(self):
        path = self.directory / "native.tmp"
        path.write_bytes(b"%PDF-native")
        page = MagicMock()
        page.content.return_value = "<title>Downloading Book</title><script>captcha</script>"
        download = page.expect_download.return_value.__enter__.return_value.value
        download.failure.return_value = None
        download.path.return_value = path
        self.assertEqual(books._native_download(page, "https://a.example/dl/123/test", 1000), (200, b"%PDF-native"))
        page.locator.return_value.first.click.assert_called_once()
        page.locator.return_value.first.count.assert_not_called()

    def test_download_uses_rendered_component_link_instead_of_html_template(self):
        context = MagicMock()
        page = context.new_page.return_value
        page.url = "https://a.example/book/123/test"
        page.locator.return_value.evaluate_all.return_value = ["https://a.example/dl/rendered"]
        html = '<script>const template = `<a href="/dl/template">PDF</a>`;</script>'
        with patch.object(books, "_browser_context", return_value=contextlib.nullcontext(context)), \
             patch.object(books, "_open_page", return_value=html), \
             patch.object(books, "_native_download", return_value=(200, b"%PDF-native")) as native:
            self.assertEqual(books._browser_download(page.url, "https://a.example/dl/stale"), (200, b"%PDF-native"))
        self.assertEqual(native.call_args.args[1], "https://a.example/dl/rendered")
        self.assertIsNone(books._parse_download_url(html, page.url))

    def test_native_download_preserves_link_handler_when_pointer_click_times_out(self):
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

        path = self.directory / "native.tmp"
        path.write_bytes(b"%PDF-native")
        page = MagicMock()
        page.content.return_value = "<title>Downloading Book</title>"
        link = page.locator.return_value.first
        link.click.side_effect = PlaywrightTimeoutError("pointer interception")
        link.count.return_value = 1
        download = page.expect_download.return_value.__enter__.return_value.value
        download.failure.return_value = None
        download.path.return_value = path
        self.assertEqual(books._native_download(page, "https://a.example/dl/123/test", 1000), (200, b"%PDF-native"))
        link.evaluate.assert_called_once_with("element => element.click()")
        page.evaluate.assert_not_called()

    def test_browser_request_failure_still_tries_native_download(self):
        context = MagicMock()
        context.new_page.return_value.url = "https://a.example/book/123/test"
        context.cookies.return_value = []
        context.request.get.side_effect = RuntimeError("request failed")
        with patch.object(books, "_browser_context", return_value=contextlib.nullcontext(context)), \
             patch.object(books, "_open_page", return_value='<a href="/file.pdf">PDF</a>'), \
             patch.object(books.requests, "get", side_effect=requests.ConnectionError()), \
             patch.object(books, "_native_download", return_value=(200, b"%PDF-native")) as native:
            self.assertEqual(books._browser_download("https://a.example/book/123/test", None), (200, b"%PDF-native"))
        native.assert_called_once()

    def test_quota_error_stops_before_other_mirror_lookup(self):
        with patch.object(books, "_candidate_bases") as candidates, \
             patch.object(books, "_browser_download", return_value=(200, b"<h1>Daily limit reached</h1>")):
            with self.assertRaisesRegex(RuntimeError, "下载额度已用完"):
                books.download_book("https://a.example/book/123/test")
        candidates.assert_not_called()
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_native_download_reports_quota_without_waiting_for_file(self):
        page = MagicMock()
        page.content.return_value = "<h1>Daily limit reached</h1>"
        with self.assertRaises(books._BookLoginRequired):
            books._native_download(page, "https://a.example/dl/123/test", 1000)
        page.expect_download.return_value.__enter__.return_value.value.path.assert_not_called()

    def test_download_resolves_missing_title_from_book_page(self):
        def download(_url, _download_url, progress_cb=None, metadata=None):
            metadata["title"] = "书籍页标题"
            return 200, b"%PDF-test"

        with patch.object(books, "_candidate_bases", return_value=[]), \
             patch.object(books, "_browser_download", side_effect=download):
            info = books.download_book("https://a.example/book/123/test")
        self.assertEqual(info["filename"], "书籍页标题.pdf")

    def test_successful_original_download_works_without_index_lookup(self):
        with patch.object(books, "_candidate_bases") as candidates, \
             patch.object(books, "_browser_download", return_value=(200, b"%PDF-test")):
            books.download_book("https://a.example/book/123/test", title="书名")
        candidates.assert_not_called()

    def test_failed_download_saves_nothing_and_reports_login(self):
        with patch.object(books, "_candidate_bases", return_value=[]), \
             patch.object(books, "_browser_download", return_value=(200, b"<p>Please log in</p>")):
            with self.assertRaisesRegex(RuntimeError, "ZBOOK_STORAGE_STATE"):
                books.download_book("https://a.example/book/123/test")
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_upload_and_concurrent_downloads_keep_distinct_files(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda number: books.upload_book("同名", b"%PDF-" + bytes([number])), (1, 2)))
        self.assertEqual(len({result["filename"] for result in results}), 2)
        self.assertEqual(len(books.list_books()), 2)
        self.assertTrue(books.delete_book(results[0]["filename"]))
        self.assertEqual(len(books.list_books()), 1)

    def test_save_failure_cleans_up_temporary_file(self):
        with patch.object(books.os, "replace", side_effect=OSError()):
            with self.assertRaises(OSError):
                books._save_book("书名", b"%PDF-test")
        self.assertEqual(os.listdir(self.directory), [])


if __name__ == "__main__":
    unittest.main()
