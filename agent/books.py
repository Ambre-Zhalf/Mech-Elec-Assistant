"""图书搜索与下载:对接 Z-Library 国内镜像。

- 搜索:抓取镜像站 /s/<关键词> 的结果页,解析书名与书籍页链接。
- 下载:进入书籍页找到 /dl/<token> 下载链接,下载 PDF 存入 data/books。
- 镜像从 z-library 镜像大全(zz.sodanav.com)的「Z-Library镜像入口」卡片读取。
- 搜索与下载复用镜像的浏览器 Cookie,支持加载个人登录状态。
"""

import html as html_mod
import os
import re
import tempfile
import threading
import time
from contextlib import contextmanager
from urllib.parse import quote, urljoin, urlparse

import requests

from .config import load_dotenv
from .tools import _launch_browser, _wait_for_network

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOOKS_DIR = os.path.join(BASE_DIR, "data", "books")
# 国内镜像入口:从 z-library 镜像大全的「Z-Library镜像入口」卡片读取(该页会不定期更新)。
MIRROR_INDEX_URL = os.environ.get("ZBOOK_INDEX_URL", "https://zz.sodanav.com/").strip()
# 兜底地址:镜像大全不可达或改版时仍能检索,不会因为一处解析失败就整个功能不可用。
DEFAULT_MIRROR_URL = "https://zh.834101.ru"
ZBOOK_BASE_URL = (os.environ.get("ZBOOK_BASE_URL", "").strip() or DEFAULT_MIRROR_URL).rstrip("/")
MIRROR_CACHE_TTL = 1800      # 镜像列表缓存 30 分钟
MIRROR_RETRY_TTL = 60        # 上次没取到列表时,1 分钟后再试
BOOK_TIMEOUT = int(os.environ.get("BOOK_TIMEOUT", "25"))
BOOK_BROWSER_CHANNEL = os.environ.get("BOOK_BROWSER_CHANNEL", "").strip()
BOOK_STORAGE_STATE = os.environ.get("ZBOOK_STORAGE_STATE", "").strip()

_MIRROR_CACHE = {"t": 0.0, "list": None}
_MIRROR_LOCK = threading.Lock()
_SESSION_STATES = {}
_SESSION_LOCK = threading.Lock()
_BOOK_FILE_LOCK = threading.Lock()

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


class _BookAccessError(RuntimeError):
    """可向用户展示的镜像访问错误。"""


class _BookLoginRequired(_BookAccessError):
    """下载需要用户登录或检查账号额度。"""


def _ensure_dir():
    os.makedirs(BOOKS_DIR, exist_ok=True)


def _get(url, timeout=None, referer=None, allow_redirects=True):
    headers = {"User-Agent": UA}
    if referer:
        headers["Referer"] = referer
    return requests.get(
        url, headers=headers, timeout=timeout or BOOK_TIMEOUT,
        allow_redirects=allow_redirects,
    )


@contextmanager
def _browser_context(url):
    """每个任务独立创建浏览器,只复用同一镜像的存储状态。"""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = _launch_browser(
            playwright, BOOK_BROWSER_CHANNEL,
            ["--disable-blink-features=AutomationControlled", "--no-sandbox",
             "--disable-dev-shm-usage", "--lang=zh-CN"],
        )
        try:
            options = {
                "user_agent": UA, "accept_downloads": True,
                "viewport": {"width": 1920, "height": 1080}, "locale": "zh-CN",
            }
            with _SESSION_LOCK:
                state = _SESSION_STATES.get(_origin(url))
            if state is not None:
                options["storage_state"] = state
            elif BOOK_STORAGE_STATE:
                state_path = os.path.join(BASE_DIR, BOOK_STORAGE_STATE)
                if not os.path.isfile(state_path):
                    raise _BookAccessError("ZBOOK_STORAGE_STATE 指向的登录状态文件不存在")
                options["storage_state"] = state_path
            context = browser.new_context(**options)
            try:
                yield context
            finally:
                try:
                    state = context.storage_state()
                    origins = {_origin(url)}
                    origins.update(_origin(page.url) for page in context.pages)
                    with _SESSION_LOCK:
                        for origin in origins - {""}:
                            _SESSION_STATES[origin] = state
                except Exception:
                    pass
                finally:
                    context.close()
        finally:
            browser.close()


def _open_page(page, url, wait_ms=5000, timeout=None):
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    page.goto(url, wait_until="domcontentloaded", timeout=timeout or BOOK_TIMEOUT * 1000)
    _wait_for_network(page, wait_ms)
    try:
        page.wait_for_function(
            "() => !/checking your browser|verifying your browser|just a moment|verify you are human|diamwall|正在验证/i.test("
            "(document.title || '') + ' ' + (document.body ? document.body.innerText.slice(0, 1000) : ''))",
            timeout=max(1, wait_ms),
        )
    except PlaywrightTimeoutError:
        pass
    path = urlparse(url).path
    if path.startswith(("/s/", "/book/")):
        selector = 'z-bookcard, a[href*="/book/"]' if path.startswith("/s/") else 'a[href*="/dl/"], a[href$=".pdf"]'
        try:
            page.locator(selector).first.wait_for(state="attached", timeout=max(1, wait_ms))
        except PlaywrightTimeoutError:
            pass
    html = page.content()
    _ensure_not_blocked(html)
    return html


def _fetch_page(url):
    """返回 HTML 与最终地址,保留重定向后的链接基准和浏览器会话。"""
    try:
        with _browser_context(url) as context:
            page = context.new_page()
            html = _open_page(page, url)
            return html, page.url
    except _BookAccessError:
        raise
    except Exception:
        try:
            response = _get(url)
            response.raise_for_status()
            return response.text, response.url
        except requests.RequestException as exc:
            raise _BookAccessError(f"镜像站连接失败({type(exc).__name__})") from None


_RATE_LIMIT_MARKERS = (
    "checking your browser", "cookies are required", "verify you are human",
    "verifying your browser", "just a moment", "access denied | diamwall",
    "<title>access denied", "protected site diamwall",
)
_NET_ERROR_MARKERS = (
    "err_connection_timed_out", "err_name_not_resolved", "dns_probe",
    "无法访问此网站", "响应时间过长", "err_connection_reset",
    "err_connection_refused", "err_ssl_protocol_error", "err_proxy_connection_failed",
)


def _ensure_not_blocked(html):
    low = (html or "").lower()
    if "diamwall" in _parse_title(html or "").lower():
        raise _BookAccessError("镜像站要求通过浏览器验证,当前仍未能通过")
    for marker in _RATE_LIMIT_MARKERS:
        if marker in low:
            raise _BookAccessError("镜像站要求通过浏览器验证,当前仍未能通过")
    if any(k in low for k in _NET_ERROR_MARKERS):
        raise _BookAccessError("无法访问该镜像(连接超时或被阻断),建议配置代理或更换网络")


def _clean(text):
    return re.sub(r"\s+", " ", html_mod.unescape(text or "")).strip()


def _parse_title(html):
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    if not m:
        return ""
    title = _clean(re.sub(r"<[^>]+>", "", m.group(1)))
    for suffix in ("| download on Z-Library", "| Z-Library", "- Z-Library", "_Z-Library", "Z-Library"):
        if title.endswith(suffix):
            title = title[: -len(suffix)].strip()
    return title


def _safe_filename(title):
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", title or "book").strip(" ._")
    name = name[:120] or "book"
    return name


def _unique_path(path):
    if not os.path.exists(path):
        return path
    root, ext = os.path.splitext(path)
    i = 2
    while os.path.exists(f"{root}({i}){ext}"):
        i += 1
    return f"{root}({i}){ext}"


# ---------------- 镜像入口回退 ----------------

def _origin(url):
    if not isinstance(url, str):
        return ""
    try:
        p = urlparse(url)
    except ValueError:
        return ""
    if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password:
        return ""
    return f"{p.scheme}://{p.netloc.lower()}"


def _links(html, base):
    out = []
    for m in re.finditer(
        r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.S | re.I,
    ):
        href = html_mod.unescape(m.group(1))
        text = _clean(re.sub(r"<[^>]+>", "", m.group(2)))
        try:
            url = urljoin(base, href)
        except ValueError:
            continue
        if _origin(url):
            out.append((text, url))
    return out


def _is_book_url(url):
    """判断某个链接是否为真正的书籍详情页。

    zlibrary 搜索结果里常混有导航/分类/客户端下载/广告卡片,它们的 href 不是
    `/book/<id>/...`。这里只认真正的书籍详情链接,避免把非书条目当成书。
    """
    if not _origin(url):
        return False
    p = urlparse(url)
    path = (p.path or "").lower()
    if not path.startswith("/book/"):
        return False
    # 排除客户端/应用/文件下载
    if path.endswith((".dmg", ".exe", ".zip", ".apk", ".7z", ".tar.gz")):
        return False
    return True


def _page_html(response):
    """按 UTF-8 解码正文:该站未在响应头声明字符集,requests 会误判成 ISO-8859-1。"""
    encoding = (response.encoding or "").lower()
    if not encoding or encoding == "iso-8859-1":
        encoding = "utf-8"
    return response.content.decode(encoding, "replace")


def _parse_mirror_index(html, base):
    """取出「Z-Library镜像入口」卡片里的按钮链接(排除「官网入口」卡片)。"""
    mirrors = []

    def collect(block):
        for m in re.finditer(r'<a\b[^>]*href=["\']([^"\']+)["\']', block, re.S | re.I):
            origin = _origin(urljoin(base, html_mod.unescape(m.group(1))))
            if origin and origin not in mirrors:
                mirrors.append(origin)

    for chunk in re.split(r"<div\b[^>]*class=[\"'][^\"']*\bcard\b", html, flags=re.I)[1:]:
        heading = re.search(r"<h3\b[^>]*>(.*?)</h3>", chunk, re.S | re.I)
        if not heading:
            continue
        title = _clean(re.sub(r"<[^>]+>", "", heading.group(1)))
        if "镜像" in title and "官网" not in title:
            collect(chunk)
            return mirrors
    return mirrors


def _parse_mirror_links(html, base):
    """兜底:按按钮文案(镜像一 / 镜像二 / 镜像3 …)识别入口。"""
    mirrors = []
    for m in re.finditer(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.S | re.I):
        text = _clean(re.sub(r"<[^>]+>", "", m.group(2)))
        if not re.fullmatch(r"镜像\s*[一二三四五六七八九十\d]+", text):
            continue
        origin = _origin(urljoin(base, html_mod.unescape(m.group(1))))
        if origin and origin not in mirrors:
            mirrors.append(origin)
    return mirrors


def _resolve_mirror_origin(doorway, max_hops=3):
    """解析镜像入口真正落地的站点。

    镜像大全里的入口域名往往只是跳转门面:任意路径都会被 302 到首页(如
    `/book`),搜索词随之丢失。因此先跟随跳转拿到真实站点,再拿它作为检索 base。
    """
    current = doorway
    for hop in range(max_hops):
        try:
            response = _get(current, timeout=min(BOOK_TIMEOUT, 12), allow_redirects=False)
        except requests.RequestException:
            # 第一跳就失败说明该入口不可用,丢弃它,交给兜底地址
            return "" if hop == 0 else _origin(current)
        location = response.headers.get("Location") or ""
        target = urljoin(current, location) if location else ""
        origin, target_origin = _origin(current), _origin(target)
        if response.is_redirect and target_origin and target_origin != origin:
            current = target
            continue
        break
    return _origin(current)


def _discover_mirrors(max_found=6):
    """读取镜像大全页面,返回国内镜像站的 origin 列表;失败时返回空列表。"""
    try:
        response = _get(MIRROR_INDEX_URL, timeout=min(BOOK_TIMEOUT, 15))
        response.raise_for_status()
    except requests.RequestException:
        return []
    html = _page_html(response)
    doorways = _parse_mirror_index(html, response.url) or _parse_mirror_links(html, response.url)
    mirrors = []
    for doorway in doorways:
        origin = _resolve_mirror_origin(doorway)
        if origin and origin not in mirrors:
            mirrors.append(origin)
        if len(mirrors) >= max_found:
            break
    return mirrors


def _candidate_bases():
    """本次检索可用的镜像站:镜像大全发现的结果优先,兜底地址排在最后。"""
    with _MIRROR_LOCK:
        now = time.monotonic()
        ttl = MIRROR_CACHE_TTL if _MIRROR_CACHE["list"] else MIRROR_RETRY_TTL
        if _MIRROR_CACHE["list"] is None or now - _MIRROR_CACHE["t"] >= ttl:
            discovered = _discover_mirrors()
            if discovered or _MIRROR_CACHE["list"] is None:
                _MIRROR_CACHE["list"] = discovered
            _MIRROR_CACHE["t"] = now
        bases = list(_MIRROR_CACHE["list"] or [])
    fallback = _origin(ZBOOK_BASE_URL)
    if fallback and fallback not in bases:
        bases.append(fallback)
    return bases


# ---------------- 搜索 ----------------

def _parse_search_results(html, base):
    results = []
    seen = set()
    for m in re.finditer(
        r'<a[^>]+href=["\']([^"\']*/book/[^"\']+)["\'][^>]*>(.*?)</a>',
        html, re.S | re.I,
    ):
        href = html_mod.unescape(m.group(1))
        title = _clean(re.sub(r"<[^>]+>", "", m.group(2)))
        if not title:
            continue
        url = urljoin(base, href)
        if not _is_book_url(url):
            continue
        if url in seen:
            continue
        seen.add(url)
        results.append({"title": title[:200], "url": url})
    return results


def _parse_search_results_generic(html, base):
    """更宽松的兜底解析:把所有看起来像书籍详情页的链接都收进来。"""
    results = []
    seen = set()
    skip_text = {"下载", "download", "详情", "登录", "注册", "下一页", "上一页", "next", "prev", "首页", "books"}
    for m in re.finditer(
        r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.S | re.I,
    ):
        href = html_mod.unescape(m.group(1))
        text = _clean(re.sub(r"<[^>]+>", "", m.group(2)))
        if not text or len(text) < 2 or text in skip_text:
            continue
        url = urljoin(base, href)
        blob = (href + " " + text).lower()
        if not any(k in blob for k in ("book", ".html", ".htm", "/b/", "zlib", "1lib")):
            continue
        if not _is_book_url(url):
            continue
        if url in seen:
            continue
        seen.add(url)
        results.append({"title": text[:200], "url": url})
    return results


def _parse_book_results(html, base):
    """解析书籍列表:每本书是一个 <z-bookcard>,字段在其属性与 slot 中。"""
    results = []
    seen = set()
    for m in re.finditer(r"<z-bookcard\b([^>]*)>(.*?)</z-bookcard>", html, re.S | re.I):
        attrs, inner = m.group(1), m.group(2)

        def attr(name):
            mm = re.search(r'\b' + re.escape(name) + r'''\s*=\s*(["'])(.*?)\1''', attrs, re.S | re.I)
            return html_mod.unescape(mm.group(2)) if mm else ""

        def slot(name):
            sm = re.search(r'''<[^>]+\bslot\s*=\s*["']''' + re.escape(name) + r'''["'][^>]*>(.*?)</[^>]+>''', inner, re.S | re.I)
            return _clean(re.sub(r"<[^>]+>", "", sm.group(1))) if sm else ""

        href = attr("href")
        if not href:
            continue
        url = urljoin(base, href)
        if not _is_book_url(url):
            continue
        if url in seen:
            continue
        seen.add(url)
        download = urljoin(base, attr("download")) if attr("download") else ""
        if not _origin(download):
            download = ""
        results.append(
            {
                "title": slot("title") or "未命名书籍",
                "author": slot("author"),
                "publisher": attr("publisher"),
                "year": attr("year"),
                "language": attr("language"),
                "extension": attr("extension"),
                "filesize": attr("filesize"),
                "isbn": attr("isbn"),
                "url": url,
                "download": download,
            }
        )
    return results


def search_books(query, max_results=10, log_cb=None):
    """按书名在镜像站检索,返回 [{title, url}]。log_cb 可选,用于输出过程日志。"""
    query = (query or "").strip()
    if not query:
        raise ValueError("请输入书籍名称")
    if max_results <= 0:
        return []
    errors = []
    bases = _candidate_bases()
    if not bases:
        raise RuntimeError("未能获取可用的图书镜像,请检查 ZBOOK_INDEX_URL / ZBOOK_BASE_URL 配置")
    if log_cb:
        log_cb(f"开始搜索: “{query}”")
        log_cb("镜像站: " + "、".join(bases))
    empty_results = False
    for index, base in enumerate(bases, 1):
        try:
            if log_cb and len(bases) > 1:
                log_cb(f"尝试镜像({index}/{len(bases)}): {base}")
            url = f"{base}/s/{quote(query, safe='')}?content_type=book"
            html, final_url = _fetch_page(url)
            _ensure_not_blocked(html)
            items = _parse_book_results(html, final_url)
            if not items:
                items = _parse_search_results(html, final_url)
            if not items:
                items = _parse_search_results_generic(html, final_url)
            if items:
                if log_cb:
                    log_cb(f"{base} 解析成功,找到 {len(items)} 本")
                return items[:max_results]
            visible_html = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", "", html, flags=re.S | re.I)
            visible_text = _clean(re.sub(r"<[^>]+>", " ", visible_html)).lower()
            if any(marker in visible_text for marker in (
                "nothing has been found", "no books found", "no results found",
                "未找到相关书籍", "没有找到任何", "没有找到符合",
            )):
                empty_results = True
            errors.append(f"{base}: 未解析到书目")
            if log_cb:
                log_cb(f"{base}: 未解析到结果")
        except Exception as exc:
            detail = str(exc) if isinstance(exc, _BookAccessError) else type(exc).__name__
            errors.append(f"{base}: {detail}")
            if log_cb:
                log_cb(f"{base}: {detail}")
    if empty_results:
        return []
    # 所有镜像都失败:清掉缓存时间戳,下次检索重新从镜像大全取一遍
    with _MIRROR_LOCK:
        _MIRROR_CACHE["t"] = 0.0
    if log_cb and errors:
        log_cb("搜索结束,镜像站未返回可用结果")
    raise RuntimeError("图书搜索失败(" + "; ".join(errors[:4]) + "),请检查镜像访问、浏览器验证或登录状态")


# ---------------- 下载 ----------------

def _parse_download_url(html, base):
    html = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", "", html, flags=re.S | re.I)
    links = _links(html, base)
    for _text, url in links:
        if "/dl/" in urlparse(url).path:
            return url
    for _text, url in links:
        if urlparse(url).path.lower().endswith(".pdf"):
            return url
    return None


# 识别“额度用完/被拦截”的页面关键字(兼中英文)
_LIMIT_KEYS = (
    "下载次数已", "下载额度已", "达到每日", "daily limit reached", "download limit reached",
    "quota exceeded", "too many requests", "checking your browser", "验证码",
    "captcha", "access denied", "diamwall",
)


def _looks_quota_or_blocked(content):
    """判断下载到的内容是否像“账号额度用完/被拦截”而不是 PDF。"""
    if not content or content[:5] == b"%PDF-":
        return False
    text = content[:200000].decode("utf-8", "replace").lower()
    return any(k in text for k in _LIMIT_KEYS)


def _download_error(content, status=None, known_only=False):
    text = (content or b"")[:200000].decode("utf-8", "replace").lower()
    text = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", "", text, flags=re.S)
    has_password = bool(re.search(r'''<input\b[^>]*\btype\s*=\s*["']password["']''', text))
    text = _clean(re.sub(r"<[^>]+>", " ", text))
    if any(marker in text for marker in (
        "daily limit reached", "daily download limit reached", "download limit reached",
        "quota exceeded", "下载次数已用完", "下载额度已用完", "达到每日下载",
    )):
        return _BookLoginRequired(
            "当前镜像下载额度已用完,游客可通过 ZBOOK_STORAGE_STATE 加载个人登录状态后重试"
        )
    if has_password or any(marker in text for marker in (
        "please log in", "please sign in", "login required", "sign in to download",
        "需要登录", "请先登录", "登录后下载",
    )):
        return _BookLoginRequired("镜像要求登录,可通过 ZBOOK_STORAGE_STATE 配置已登录的浏览器状态")
    if status in (403, 429, 513, 517) or _looks_quota_or_blocked(text.encode("utf-8")):
        return _BookAccessError("镜像下载受限或需要浏览器验证,请检查账号额度与网络访问")
    if known_only:
        return None
    return _BookAccessError("未获取到 PDF 文件,请在书籍页确认该版本为 PDF 且允许下载")


def _native_download(page, download_url, timeout, progress_cb=None):
    """点击下载链接,处理 HTML 中转页并接收浏览器文件下载事件。"""
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    selector = 'a[href*="/dl/"]' if "/dl/" in urlparse(download_url).path else 'a[href*=".pdf"]'
    try:
        with page.expect_download(timeout=timeout) as pending:
            link = page.locator(selector).first
            try:
                link.click(timeout=min(timeout, 10000))
            except PlaywrightTimeoutError:
                if link.count():
                    link.evaluate("element => element.click()")
                else:
                    page.evaluate("url => { window.location.assign(url); }", download_url)
            page.wait_for_load_state("domcontentloaded", timeout=timeout)
            _wait_for_network(page, 4000)
            error = _download_error(page.content().encode("utf-8"), known_only=True)
            if error:
                raise error
        download = pending.value
        if download.failure():
            raise _BookAccessError("浏览器文件下载失败,请在书籍页重试")
        content = download.path().read_bytes()
        if progress_cb:
            progress_cb(95)
        return 200, content
    except PlaywrightTimeoutError:
        error = _download_error(page.content().encode("utf-8"), known_only=True)
        raise error or _BookAccessError("浏览器下载未开始,请在书籍页检查下载权限或登录状态") from None


def _browser_download(full_url, download_url, wait_ms=10000, timeout=90000, progress_cb=None, metadata=None):
    """复用搜索会话打开书籍页,刷新下载链接,返回 (状态码, 字节)。"""
    with _browser_context(full_url) as context:
        page = context.new_page()
        html = _open_page(page, full_url, wait_ms, timeout)
        resolved_url = page.url
        if metadata is not None:
            metadata["title"] = _parse_title(html)
        rendered_links = page.locator('a[href*="/dl/"]').evaluate_all(
            "elements => elements.map(element => element.href)"
        )
        rendered_download = next((url for url in rendered_links if _origin(url)), None)
        download_url = rendered_download or _parse_download_url(html, resolved_url) or download_url
        if not download_url or not _origin(download_url):
            raise _download_error(html.encode("utf-8"))
        if urlparse(download_url).path.startswith("/dl/"):
            return _native_download(page, download_url, timeout, progress_cb)
        cookies = requests.cookies.RequestsCookieJar()
        for cookie in context.cookies():
            cookies.set(
                cookie["name"], cookie["value"], domain=cookie["domain"],
                path=cookie.get("path", "/"), secure=cookie.get("secure", False),
            )
        # CookieJar 保留域名、路径和 secure 限制,由 requests 在重定向时逐跳匹配。
        try:
            with requests.get(
                download_url,
                headers={"User-Agent": UA, "Referer": _origin(resolved_url) + urlparse(resolved_url).path},
                cookies=cookies, stream=True, timeout=max(1, timeout / 1000),
                allow_redirects=True,
            ) as response:
                if response.status_code == 200:
                    total = int(response.headers.get("Content-Length") or 0)
                    data = bytearray()
                    for chunk in response.iter_content(chunk_size=65536):
                        if not chunk:
                            continue
                        data.extend(chunk)
                        if len(data) >= 5 and data[:5] != b"%PDF-":
                            break
                        if progress_cb and total and len(data) >= 5:
                            progress_cb(min(95, int(len(data) * 95 / total)))
                    if data[:5] == b"%PDF-":
                        return response.status_code, bytes(data)
        except Exception:
            pass
        try:
            response = context.request.get(download_url, timeout=min(timeout, BOOK_TIMEOUT * 1000))
            content = response.body()
        except Exception:
            return _native_download(page, download_url, timeout, progress_cb)
        if response.status == 200 and content[:5] == b"%PDF-":
            return response.status, content
        error = _download_error(content, response.status, known_only=True)
        if isinstance(error, _BookLoginRequired):
            raise error
        return _native_download(page, download_url, timeout, progress_cb)


def _save_book(title, content):
    """完成写入后原子发布文件,并为并发同名下载分配不同文件名。"""
    _ensure_dir()
    with _BOOK_FILE_LOCK:
        fd, temporary = tempfile.mkstemp(prefix=".book-", suffix=".tmp", dir=BOOKS_DIR)
        try:
            with os.fdopen(fd, "wb") as output:
                output.write(content)
            path = _unique_path(os.path.join(BOOKS_DIR, _safe_filename(title) + ".pdf"))
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.remove(temporary)
    return {"title": title, "filename": os.path.basename(path), "size": len(content)}


def _download_mirrors(original):
    """先尝试书籍原地址,失败后再获取其他镜像。"""
    yield original
    for base in _candidate_bases():
        if base != original:
            yield base


def download_book(book_url, download_url=None, title=None, progress_cb=None):
    """进入书籍页找到下载链接并下载 PDF,返回 {title, filename, size}。"""
    book_url = (book_url or "").strip()
    if not _origin(book_url):
        raise ValueError("书籍链接无效")
    resolved_title = (title or "").strip()
    original = _origin(book_url)
    errors = []
    for base in _download_mirrors(original):
        candidate_url = book_url if base == original else urljoin(base, urlparse(book_url).path)
        metadata = {}
        try:
            status, content = _browser_download(
                candidate_url, download_url if base == original else None,
                progress_cb=progress_cb, metadata=metadata,
            )
            if status != 200 or content[:5] != b"%PDF-":
                raise _download_error(content, status)
        except _BookLoginRequired as exc:
            raise RuntimeError(str(exc)) from None
        except Exception as exc:
            detail = str(exc) if isinstance(exc, _BookAccessError) else type(exc).__name__
            errors.append(f"{base}: {detail}")
            continue
        try:
            info = _save_book(resolved_title or metadata.get("title") or "未命名图书", content)
        except OSError as exc:
            raise RuntimeError(f"PDF 保存失败({type(exc).__name__})") from None
        if progress_cb:
            progress_cb(100)
        return info
    raise RuntimeError("下载失败(" + "; ".join(errors[:3]) + ")")


# ---------------- 我的书籍 ----------------

def list_books():
    _ensure_dir()
    books = []
    for name in os.listdir(BOOKS_DIR):
        if name.startswith(".book-") and name.endswith(".tmp"):
            continue
        path = os.path.join(BOOKS_DIR, name)
        if not os.path.isfile(path):
            continue
        st = os.stat(path)
        books.append(
            {
                "filename": name,
                "size": st.st_size,
                "mtime": int(st.st_mtime * 1000),
            }
        )
    books.sort(key=lambda b: b["mtime"], reverse=True)
    return books


def book_file_path(filename):
    """安全地解析书籍文件名,阻止目录穿越。"""
    name = os.path.basename(filename or "")
    path = os.path.join(BOOKS_DIR, name)
    if not os.path.isfile(path):
        return None
    return path


def delete_book(filename):
    path = book_file_path(filename)
    if path:
        os.remove(path)
        return True
    return False


def upload_book(title, content):
    """把用户本地上传的 PDF 保存到“我的书籍”,返回 {title, filename, size}。"""
    _ensure_dir()
    if not content or content[:5] != b"%PDF-":
        raise RuntimeError("文件不是合法的 PDF 文件")
    if len(content) > 300 * 1024 * 1024:
        raise RuntimeError("PDF 文件过大(超过 300MB)")
    name = (title or "").strip() or "未命名图书"
    return _save_book(name, content)
