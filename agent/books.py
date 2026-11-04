"""图书搜索与下载:对接 Z-Library 镜像站,支持镜像入口回退。

- 搜索:抓取镜像站 /s/<关键词> 的结果页,解析书名与书籍页链接。
- 下载:进入书籍页找到 /dl/<token> 下载链接,下载 PDF 存入 data/books。
- 回退:若默认镜像不可用,从 znew.pages.dev 按“镜像入口”逐层查找新站点。
"""

import base64
import html as html_mod
import json
import os
import re
import shutil
import tempfile
import time
from urllib.parse import quote, urljoin, urlparse

import requests
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding as sym_padding

from .config import load_dotenv
from .tools import _launch_browser, _render_dom, _wait_for_network

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOOKS_DIR = os.path.join(BASE_DIR, "data", "books")
ZBOOK_BASE_URL = os.environ.get("ZBOOK_BASE_URL", "https://zh.101k.by").rstrip("/")
MIRROR_INDEX_URL = os.environ.get("ZBOOK_INDEX_URL", "https://znew.pages.dev/").rstrip("/")
BOOK_SEARCH_MODEL = os.environ.get("BOOK_SEARCH_MODEL", "deepseek-flash")
BOOK_TIMEOUT = int(os.environ.get("BOOK_TIMEOUT", "25"))
DEBUG_DIR = os.path.join(BASE_DIR, "data")
READZN_ACCOUNT_URL = os.environ.get(
    "ZBOOK_SHARED_ACCOUNT_URL", "https://readzn.com/zlibrary-shared-account"
).rstrip("/")
_DEFAULT_BROWSER_CHANNEL = "msedge" if os.name == "nt" else "chromium"
BOOK_BROWSER_CHANNEL = os.environ.get("BOOK_BROWSER_CHANNEL", _DEFAULT_BROWSER_CHANNEL).strip() or _DEFAULT_BROWSER_CHANNEL

_MIRROR_CACHE = {"t": 0.0, "list": None}

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def _ensure_dir():
    os.makedirs(BOOKS_DIR, exist_ok=True)


def _get(url, timeout=None, referer=None):
    headers = {"User-Agent": UA}
    if referer:
        headers["Referer"] = referer
    return requests.get(
        url, headers=headers, timeout=timeout or BOOK_TIMEOUT,
        allow_redirects=True,
    )


def _fetch_html(url, render=True, wait_ms=15000):
    """优先用无头浏览器渲染(可执行 JS 通过反爬挑战),失败再退回 requests。"""
    if render:
        try:
            return _render_dom(url, wait_ms=wait_ms, timeout=60)
        except Exception:
            pass
    return _get(url).text


_RATE_LIMIT_MARKERS = ("try again later", "support@z-lib", "checking your browser", "cookies are required")
_NET_ERROR_MARKERS = (
    "err_connection_timed_out", "err_name_not_resolved", "dns_probe",
    "无法访问此网站", "响应时间过长", "err_connection_reset",
    "err_connection_refused", "err_ssl_protocol_error", "err_proxy_connection_failed",
)


def _ensure_not_blocked(html):
    low = (html or "").lower()
    for marker in _RATE_LIMIT_MARKERS:
        if marker in low:
            if "try again later" in low or "support@z-lib" in low:
                raise RuntimeError("镜像站暂时限流,请稍后再试")
            raise RuntimeError("镜像站要求通过浏览器验证,当前仍未能通过")
    if any(k in low for k in _NET_ERROR_MARKERS):
        raise RuntimeError("无法访问该镜像(连接超时或被阻断),建议配置代理或更换网络")


def _clean(text):
    return re.sub(r"\s+", " ", html_mod.unescape(text or "")).strip()


def _parse_title(html):
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    if not m:
        return ""
    title = _clean(re.sub(r"<[^>]+>", "", m.group(1)))
    for suffix in ("| Z-Library", "- Z-Library", "_Z-Library", "Z-Library"):
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
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def _is_mirror_domain(origin):
    host = urlparse(origin).netloc.lower()
    return any(k in host for k in ("z-lib", "zlib", "1lib", "libgen"))


def _links(html, base):
    out = []
    for m in re.finditer(
        r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.S | re.I,
    ):
        href = html_mod.unescape(m.group(1))
        text = _clean(re.sub(r"<[^>]+>", "", m.group(2)))
        url = urljoin(base, href)
        if url.startswith(("http://", "https://")):
            out.append((text, url))
    return out


def _is_book_url(url):
    """判断某个链接是否为真正的书籍详情页。

    zlibrary 搜索结果里常混有导航/分类/客户端下载/广告卡片,它们的 href 不是
    `/book/<id>/...`。这里只认真正的书籍详情链接,避免把非书条目当成书。
    """
    p = urlparse(url)
    path = (p.path or "").lower()
    if not path.startswith("/book/"):
        return False
    # 排除客户端/应用/文件下载
    if path.endswith((".dmg", ".exe", ".zip", ".apk", ".7z", ".tar.gz")):
        return False
    return True


def _discover_mirrors(max_found=12):
    """从 znew.pages.dev 提取“官网入口 / 镜像入口”,并进入导航页再挖一层。"""
    mirrors = []
    nav_pages = []
    try:
        html = _get(MIRROR_INDEX_URL, timeout=15).text
    except Exception:
        return mirrors

    for text, url in _links(html, MIRROR_INDEX_URL):
        low = (text + " " + url).lower()
        if "官网入口" in text:
            mirrors.append(_origin(url))
        elif "镜像入口" in text or "镜像网站入口" in text:
            nav_pages.append(url)
        elif any(k in low for k in ("z-library", "z-lib", "zlib", "zlibrary")):
            mirrors.append(_origin(url))

    for page in list(dict.fromkeys(nav_pages)):
        try:
            html2 = _get(page, timeout=12).text
        except Exception:
            continue
        for text, url in _links(html2, page):
            if any(k in text for k in ("镜像入口", "官网入口", "入口", "z-lib")) or any(
                k in url.lower() for k in ("z-library", "z-lib", "zlib", "zlibrary")
            ):
                mirrors.append(_origin(url))
        if len(mirrors) >= max_found:
            break
    return [m for m in dict.fromkeys(mirrors) if _is_mirror_domain(m)][:max_found]


def _candidate_bases():
    bases = [ZBOOK_BASE_URL.rstrip("/")] if ZBOOK_BASE_URL else []
    now = time.time()
    if now - _MIRROR_CACHE["t"] < 1800 and _MIRROR_CACHE["list"] is not None:
        discovered = _MIRROR_CACHE["list"]
    else:
        try:
            discovered = _discover_mirrors()
            _MIRROR_CACHE["list"] = discovered
            _MIRROR_CACHE["t"] = now
        except Exception:
            discovered = []
    try:
        for d in discovered:
            if d not in bases:
                bases.append(d)
    except Exception:
        pass
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
            mm = re.search(r'\b' + re.escape(name) + r'\s*=\s*"([^"]*)"', attrs, re.I)
            return html_mod.unescape(mm.group(1)) if mm else ""

        def slot(name):
            sm = re.search(r'<div\s+slot="' + re.escape(name) + r'"[^>]*>(.*?)</div>', inner, re.S | re.I)
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


def _dump_debug_html(html, tag="search"):
    try:
        os.makedirs(DEBUG_DIR, exist_ok=True)
        path = os.path.join(DEBUG_DIR, f"book_debug_{tag}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        return path
    except Exception:
        return None


# ---------------- readzn 共享账号(可进入 zh.101k.by) ----------------

def _readzn_crypto_config():
    for _ in range(2):
        try:
            html = _get(READZN_ACCOUNT_URL, timeout=30).text
            break
        except requests.RequestException:
            time.sleep(1)
    else:
        raise RuntimeError("无法连接 readzn.com,请稍后重试")
    secret = re.search(r'ENV_API_ENCRYPTION_SECRET_KEY\s*=\s*"([0-9a-fA-F]+)"', html).group(1)
    iv = re.search(r'ENV_API_ENCRYPTION_IV\s*=\s*"([0-9a-fA-F]+)"', html).group(1)
    return secret, iv


def _aes_decrypt(data_b64, secret, iv):
    key = secret.encode("utf-8")[:32]
    ivb = iv.encode("utf-8")[:16]
    cipher = Cipher(algorithms.AES(key), modes.CBC(ivb))
    dec = cipher.decryptor()
    padded = dec.update(base64.b64decode(data_b64)) + dec.finalize()
    unpadder = sym_padding.PKCS7(128).unpadder()
    return unpadder.update(padded) + unpadder.finalize()


def _readzn_api(path, method="GET", body=None, timeout=45, retries=2):
    secret, iv = _readzn_crypto_config()
    api = "https://readzn.com/api"
    last_exc = None
    for _ in range(retries + 1):
        try:
            if method == "GET":
                resp = requests.get(api + path, headers={"User-Agent": UA}, timeout=timeout)
            else:
                resp = requests.post(
                    api + path,
                    json=body,
                    headers={"User-Agent": UA, "Content-Type": "application/json"},
                    timeout=timeout,
                )
            resp.raise_for_status()
            data = resp.json()
            return json.loads(_aes_decrypt(data["data"], secret, iv))
        except requests.RequestException as exc:
            last_exc = exc
            time.sleep(1)
    raise RuntimeError(f"无法连接 readzn.com({path}): {type(last_exc).__name__}: {last_exc}") from last_exc


def get_readzn_session():
    """获取一个已登录的 Z-Library 会话信息,返回 (domain, search_path, full_url)。"""
    dom = _readzn_api("/zlibrary-domain")
    domain = (dom.get("domain") or "").rstrip("/")
    acc = _readzn_api("/zlibrary-account", "POST", {
        "domain": domain,
        "searchPath": "",
        "fullSearchUrl": domain,
        "useCustomAccount": False,
    })
    full_url = acc.get("fullUrl") or ""
    if not domain or not full_url:
        raise RuntimeError("readzn 未能返回可用的 Z-Library 会话")
    return domain, acc.get("searchPath") or "/s/{searchTerm}?", full_url


def _search_via_readzn(query, max_results=10):
    """通过 readzn 共享账号进入 zh.101k.by:先登录,再在同一浏览器会话里搜索。"""
    domain, _search_path, full_url = get_readzn_session()
    profile = tempfile.mkdtemp(prefix="agent_zlib_")
    try:
        # 第一步:访问登录 URL,通过反爬并建立登录态
        _render_dom(full_url, wait_ms=18000, timeout=70, profile=profile)
        # 第二步:复用同一 profile,直接搜索“书籍”分类
        search_url = f"{domain}/s/{quote(query)}?content_type=book"
        html = _render_dom(search_url, wait_ms=18000, timeout=70, profile=profile)
    finally:
        shutil.rmtree(profile, ignore_errors=True)

    _ensure_not_blocked(html)
    _dump_debug_html(html, tag="readzn_books")
    items = _parse_book_results(html, domain)
    if not items:
        raise RuntimeError("已进入书籍列表,但未能解析到书籍条目")
    return items[:max_results]


def search_books(query, max_results=10, log_cb=None):
    """按书名在镜像站检索,返回 [{title, url}]。log_cb 可选,用于输出过程日志。"""
    query = (query or "").strip()
    if not query:
        raise ValueError("请输入书籍名称")
    errors = []
    if log_cb:
        log_cb(f"开始搜索: “{query}”")
    # 优先走 readzn 共享账号(能拿到已登录会话,通过反爬概率更高)
    try:
        if log_cb:
            log_cb("优先尝试 readzn 共享账号(带登录态,反爬通过率高)…")
        items = _search_via_readzn(query, max_results)
        if log_cb:
            log_cb(f"readzn 共享账号搜索成功,找到 {len(items)} 本")
        return items
    except Exception as exc:
        errors.append(f"readzn共享账号: {exc}")
        if log_cb:
            log_cb(f"readzn 共享账号失败: {exc},开始回退镜像站…")
    for base in _candidate_bases():
        try:
            if log_cb:
                log_cb(f"尝试镜像站: {base}")
            url = f"{base}/s/{quote(query)}"
            html = _fetch_html(url, wait_ms=15000)
            _ensure_not_blocked(html)
            items = _parse_search_results(html, base)
            if not items:
                items = _parse_search_results_generic(html, base)
            if items:
                if log_cb:
                    log_cb(f"{base} 解析成功,找到 {len(items)} 本")
                return items[:max_results]
            debug_path = _dump_debug_html(html, tag=urlparse(base).netloc.replace(".", "_"))
            errors.append(f"{base}: 未解析到结果(调试:{debug_path or '未保存'})")
            if log_cb:
                log_cb(f"{base}: 未解析到结果")
        except Exception as exc:
            errors.append(f"{base}: {exc}")
            if log_cb:
                log_cb(f"{base}: {exc}")
    if log_cb and errors:
        log_cb("搜索结束,所有镜像源未成功")
    raise RuntimeError("图书搜索失败(" + "; ".join(errors[:4]) + "),请稍后重试或检查镜像站可用性")


# ---------------- 下载 ----------------

def _parse_download_url(html, base):
    for m in re.finditer(r'href=["\']([^"\']*/dl/[^"\']+)["\']', html, re.I):
        return urljoin(base, html_mod.unescape(m.group(1)))
    return None


# 识别“额度用完/被拦截”的页面关键字(兼中英文)
_LIMIT_KEYS = (
    "每日", "每天", "下载次数", "下载额度", "已达到", "限制", "quota", "daily",
    "limit", "too many", "request", "频率", "频繁", "稍后再试", "稍后重试",
    "try again", "请稍后", "checking your browser", "cloudflare", "验证码",
    "captcha", "please wait", "access denied",
)


def _looks_quota_or_blocked(content):
    """判断下载到的内容是否像“账号额度用完/被拦截”而不是 PDF。"""
    if not content or content[:5] == b"%PDF-":
        return False
    text = content[:200000].decode("utf-8", "replace").lower()
    return any(k in text for k in _LIMIT_KEYS)


def _browser_download(full_url, download_url, wait_ms=10000, timeout=90000, progress_cb=None):
    """用 Playwright 驱动浏览器:先登录,再用浏览器上下文直接请求下载,返回 (状态码, 字节)。

    优先用浏览器 cookie 走 requests 流式下载以报告字节进度;若被拦截则回退到
    浏览器上下文请求(此时无字节进度,结束时置 100)。
    """
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

    with sync_playwright() as p:
        browser = _launch_browser(
            p,
            os.environ.get("BOOK_BROWSER_CHANNEL", "").strip(),
            [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--lang=zh-CN",
            ],
        )
        try:
            ctx = browser.new_context(
                user_agent=UA,
                accept_downloads=True,
                viewport={"width": 1920, "height": 1080},
                locale="zh-CN",
            )
            page = ctx.new_page()
            page.goto(full_url, wait_until="domcontentloaded", timeout=timeout)
            _wait_for_network(page, wait_ms)
            # 如存在验证或登录跳转,等待提示消失,最多等待 wait_ms 毫秒。
            try:
                page.wait_for_function(
                    "() => !/checking your browser|just a moment|verify you are human|请稍候|正在验证/i.test("
                    "(document.title || '') + ' ' + (document.body ? document.body.innerText.slice(0, 1000) : ''))",
                    timeout=max(1, wait_ms),
                )
            except PlaywrightTimeoutError:
                pass
            cookies = {c["name"]: c["value"] for c in ctx.cookies()}
            # 先尝试 requests 流式下载(带 cookie + UA),可拿到真实的字节进度
            try:
                with requests.get(
                    download_url,
                    headers={"User-Agent": UA, "Referer": full_url},
                    cookies=cookies,
                    stream=True,
                    timeout=max(1, timeout / 1000),
                    allow_redirects=True,
                ) as resp:
                    if resp.status_code == 200:
                        total = int(resp.headers.get("Content-Length") or 0)
                        data = bytearray()
                        for chunk in resp.iter_content(chunk_size=65536):
                            if not chunk:
                                continue
                            data += chunk
                            if progress_cb and total:
                                progress_cb(min(100, int(len(data) * 100 / total)))
                        if progress_cb:
                            progress_cb(100)
                        return resp.status_code, bytes(data)
                # 响应不是 200,回退到浏览器上下文请求
            except Exception:
                pass
            # 回退:浏览器上下文的请求(自动携带登录 cookie),避免 wait_for_download 超时
            resp = ctx.request.get(download_url, timeout=timeout)
            if progress_cb:
                progress_cb(100)
            return resp.status, resp.body()
        finally:
            browser.close()


def _download_direct(download_url, book_url=None):
    """readzn 不可用时的回退:先过书页反爬建立会话,再直接下载链接(等价于“下载页”路径)。"""
    if book_url:
        try:
            _fetch_html(book_url, wait_ms=15000)
        except Exception:
            pass
    resp = _get(download_url, referer=book_url)
    content = resp.content
    if content and content[:5] == b"%PDF-":
        return content
    raise RuntimeError("下载内容不是 PDF 文件")


def _download_with_account_switch(download_url, book_url=None, max_switch=10, progress_cb=None):
    """带“共享账号自动切换”的下载:
    - 若某个账号额度用完(拿到的是非 PDF 且像额度/拦截页),自动换下一个共享账号重试,
      最多 max_switch(默认10)次;
    - 若 readzn 会话获取失败(超时/不可达),回退到直连下载,尽量保证仍能下载。"""
    session_errors = 0
    last_content = b""
    for attempt in range(max_switch):
        try:
            _domain, _search_path, full_url = get_readzn_session()
        except Exception as exc:
            session_errors += 1
            print(f"[books] 获取共享账号失败(第{attempt + 1}次): {exc}")
            # readzn 连续失败,回退直连下载
            if session_errors >= 2:
                return _download_direct(download_url, book_url)
            continue
        try:
            status, content = _browser_download(full_url, download_url, progress_cb=progress_cb)
        except Exception as exc:
            raise RuntimeError(f"下载失败:{type(exc).__name__}: {exc}") from exc
        if content and content[:5] == b"%PDF-":
            return content
        last_content = content
        # 不是“额度/拦截”类问题:不盲目换号,保持原有报错
        if not (status in (403, 429) or _looks_quota_or_blocked(content)):
            raise RuntimeError("下载内容不是 PDF 文件")
        if attempt < max_switch - 1:
            continue
    raise RuntimeError(
        "共享账号当日下载额度可能已用完,已自动尝试切换多个账号仍失败,"
        "请稍后重试,或到 readzn.com/zlibrary-shared-account 手动切换"
    )


def download_book(book_url, download_url=None, title=None, progress_cb=None):
    """进入书籍页找到下载链接并下载 PDF,返回 {title, filename, size}。"""
    book_url = (book_url or "").strip()
    if not book_url.startswith(("http://", "https://")):
        raise ValueError("书籍链接无效")
    _ensure_dir()
    resolved_title = (title or "").strip()

    if download_url and download_url.startswith(("http://", "https://")):
        # 用真实浏览器会话下载,自动带上登录 cookie;额度用完时自动切换共享账号重试
        content = _download_with_account_switch(download_url, book_url, progress_cb=progress_cb)
    else:
        html = _fetch_html(book_url, wait_ms=15000)
        _ensure_not_blocked(html)
        p = urlparse(book_url)
        base = f"{p.scheme}://{p.netloc}"
        dl_url = _parse_download_url(html, base)
        if not dl_url:
            raise RuntimeError("未找到该书籍的下载链接")
        resolved_title = resolved_title or _parse_title(html)
        data = _get(dl_url, referer=book_url)
        content = data.content
        if progress_cb:
            progress_cb(100)

    if not content or content[:5] != b"%PDF-":
        raise RuntimeError("下载内容不是 PDF 文件")

    name = resolved_title or "未命名图书"
    filename = _safe_filename(name) + ".pdf"
    path = _unique_path(os.path.join(BOOKS_DIR, filename))
    with open(path, "wb") as f:
        f.write(content)
    return {
        "title": name,
        "filename": os.path.basename(path),
        "size": len(content),
    }


# ---------------- 我的书籍 ----------------

def list_books():
    _ensure_dir()
    books = []
    for name in os.listdir(BOOKS_DIR):
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
    filename = _safe_filename(name) + ".pdf"
    path = _unique_path(os.path.join(BOOKS_DIR, filename))
    with open(path, "wb") as f:
        f.write(content)
    return {
        "title": name,
        "filename": os.path.basename(path),
        "size": len(content),
    }
