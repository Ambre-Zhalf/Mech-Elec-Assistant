"""Agent 可调用的工具:联网搜索、网页读取、B站视频搜索。"""

import base64
import codecs
import functools
import html as html_mod
import json
import locale
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import tempfile
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from urllib.parse import parse_qs, quote, unquote, urljoin, urlparse

import requests

from .llm import register_tool
from .free_search import free_search

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
SEARCH_ENGINE = os.environ.get("SEARCH_ENGINE", "baidu").lower()

# 动态渲染/浏览器通道默认值:Windows 用系统 Edge,Linux 用 Playwright 自带 Chromium
_DEFAULT_BROWSER_CHANNEL = "msedge" if os.name == "nt" else "chromium"


def _headers(**extra):
    headers = {"User-Agent": UA}
    headers.update(extra)
    return headers


def _clean_text(text):
    return re.sub(r"\s+", " ", text or "").strip()


def _resolve_link(href):
    """还原搜索引擎跳转链接为真实地址。"""
    href = html_mod.unescape(href or "")
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        uddg = parse_qs(parsed.query).get("uddg", [""])[0]
        if uddg:
            href = unquote(uddg)
    elif "bing.com" in parsed.netloc and parsed.path.startswith("/ck/a"):
        u = parse_qs(parsed.query).get("u", [""])[0]
        if u:
            try:
                href = unquote(base64.urlsafe_b64decode(u + "=" * (-len(u) % 4)).decode("utf-8"))
            except Exception:
                pass
    return href


def _duckduckgo_search(query, max_results=8, timeout=20):
    resp = requests.get(
        "https://html.duckduckgo.com/html/",
        params={"q": query, "kl": "cn-zh"},
        headers=_headers(),
        timeout=timeout,
    )
    resp.raise_for_status()
    raw = resp.text
    results = []
    for href, title_html in re.findall(
        r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', raw, re.S
    ):
        title = _clean_text(re.sub(r"<[^>]+>", "", title_html))
        results.append({"title": title, "url": _resolve_link(href)})
        if len(results) >= max_results:
            break
    snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', raw, re.S)
    for i, snip in enumerate(snippets):
        if i < len(results):
            results[i]["snippet"] = _clean_text(re.sub(r"<[^>]+>", "", snip))[:200]
    return results


def _bing_search(query, max_results=8, timeout=20):
    resp = requests.get(
        "https://cn.bing.com/search",
        params={"q": query, "setlang": "zh-cn", "mkt": "zh-CN"},
        headers=_headers(),
        timeout=timeout,
    )
    resp.raise_for_status()
    raw = resp.text
    results = []
    for block in re.findall(r'<li class="b_algo".*?</li>', raw, re.S):
        link = re.search(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not link:
            continue
        title = _clean_text(re.sub(r"<[^>]+>", "", link.group(2)))
        if not title:
            continue
        url = _resolve_link(link.group(1))
        if url.startswith("javascript:") or url.startswith("#"):
            continue
        snip_match = re.search(r"<p[^>]*>(.*?)</p>", block, re.S)
        snippet = _clean_text(re.sub(r"<[^>]+>", "", snip_match.group(1)))[:200] if snip_match else ""
        results.append({"title": title, "url": url, "snippet": snippet})
        if len(results) >= max_results:
            break
    return results


def _baidu_search(query, max_results=8, timeout=15):
    """百度搜索:国内可访问,对中文公司官网定位最准。

    先用会话访问百度首页拿到 Cookie(否则常返回极短的验证页),再请求 SERP;
    从每个结果块的 mu=<真实网址> 属性还原目标地址,绕开损坏的 /link?url= 跳转链接。
    """
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": UA,
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
    )
    try:
        session.get("https://www.baidu.com/", timeout=timeout)
    except Exception:
        pass

    raw = ""
    for attempt in range(3):
        try:
            resp = session.get(
                "https://www.baidu.com/s",
                params={"wd": query, "ie": "utf-8", "rn": "30"},
                timeout=timeout,
            )
            raw = resp.content.decode("utf-8", "replace")
            if len(raw) > 5000:
                break
        except requests.RequestException:
            raw = ""
        # 百度偶发返回极短验证页,稍等一下再试
        if attempt < 2:
            time.sleep(0.6)
    if not raw or len(raw) < 5000:
        raise RuntimeError("百度搜索无返回")

    results = []
    seen = set()
    # 把结果块按顶层 <div class="result ..."> 切开(百度块内 mu= 属性即真实地址)
    parts = re.split(r'(?=<div[^>]+class="[^"]*result[^"]*")', raw)
    for part in parts[1:]:
        h3 = re.search(r'<h3[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', part, re.S)
        if not h3:
            continue
        title = _clean_text(re.sub(r"<[^>]+>", "", h3.group(2)))
        if not title:
            continue
        mu = re.search(r'mu="([^"]+)"', part) or re.search(r'data-mdurl="([^"]+)"', part)
        url = html_mod.unescape((mu.group(1) if mu else h3.group(1)) or "").strip()
        if url.startswith("//"):
            url = "https:" + url
        if not url.startswith(("http://", "https://")):
            continue
        snippet = ""
        sm = re.search(r'class="[^"]*(?:content-right|c-abstract)[^"]*"[^>]*>(.*?)</(?:span|div)>', part, re.S)
        if sm:
            snippet = _clean_text(re.sub(r"<[^>]+>", "", sm.group(1)))[:200]
        if not snippet:
            block_text = _clean_text(re.sub(r"<[^>]+>", " ", part))
            snippet = block_text[:200]
        if url in seen:
            continue
        seen.add(url)
        results.append({"title": title[:80], "url": url, "snippet": snippet})
        if len(results) >= max_results:
            break
    return results


class _TextExtractor(HTMLParser):
    """把网页 HTML 粗略转换为纯文本。"""

    _SKIP_TAGS = {"script", "style", "noscript", "svg", "template"}
    _BREAK_TAGS = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr", "section", "article"}

    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP_TAGS:
            self.skip_depth += 1
        elif tag in self._BREAK_TAGS:
            self.parts.append("\n")
        elif tag in ("td", "th"):
            self.parts.append("\t")

    def handle_endtag(self, tag):
        if tag in self._SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1
        elif tag in self._BREAK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip_depth:
            self.parts.append(data)


def _html_to_text(raw_html):
    parser = _TextExtractor()
    try:
        parser.feed(raw_html)
    except Exception:
        pass
    text = "".join(parser.parts)
    return re.sub(r"[ \t]+", " ", text)


def _fetch_html(url, timeout=20):
    """按真实 charset 抓取网页原始 HTML,用于提取导航链接。"""
    resp = requests.get(url, headers=_headers(), timeout=timeout, allow_redirects=True)
    resp.raise_for_status()
    raw = resp.content
    enc = (resp.encoding or "").lower()
    if enc in ("iso-8859-1", "ascii", ""):
        m = re.search(rb"charset=[\"']?([\w-]+)", raw[:4096], re.I)
        enc = m.group(1).decode("ascii", "ignore").lower() if m else "utf-8"
        try:
            return raw.decode(enc, "replace")
        except LookupError:
            return raw.decode("utf-8", "replace")
    return raw.decode(enc, "replace")


# 招聘入口关键词:匹配招聘/网申/求职平台类链接
RECRUIT_KEYWORDS = (
    "招聘", "人才", "加入我们", "人才招聘", "校园招聘", "网申", "职位",
    "career", "campus", "campus-recruitment", "mokahr", "hotjob", "recruit",
    "talent", "zhaopin", "joinus", "join-us", "jobs", "job",
)
# 明显与招聘无关的页面段,用于过滤搜索噪声
NON_RECRUIT_SEGMENTS = (
    "/about", "/news", "/product", "/contact", "/privacy",
    "/login", "/register", "/terms", "/help", "/download",
)


def _looks_like_recruitment(url, title="", snippet=""):
    """判断一个链接是否像招聘/网申页面。"""
    if not url or not url.startswith(("http://", "https://")):
        return False
    low = url.lower()
    blob = (title or "").lower() + " " + (snippet or "").lower() + " " + low
    if not any(k in blob for k in RECRUIT_KEYWORDS):
        return False
    # 若路径是明显无关页,且 URL 本身又没有招聘标识,则排除
    if any(seg in low for seg in NON_RECRUIT_SEGMENTS) and not any(
        k in low for k in ("campus", "recruit", "job", "talent", "zhaopin", "hotjob", "mokahr")
    ):
        return False
    return True


def _extract_homepage_recruit(homepage):
    """抓取官网主页,提取导航中与招聘相关的真实链接。"""
    try:
        html = _fetch_html(homepage)
    except Exception:
        return []
    urls = []
    for href, text in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.S):
        label = _clean_text(re.sub(r"<[^>]+>", "", text))
        href = href.strip()
        if href.startswith("//"):
            href = "https:" + href
        elif href.startswith("/"):
            href = urljoin(homepage, href)
        if _looks_like_recruitment(href, label, ""):
            urls.append(href)
    return urls


def _url_host(url):
    """从 URL 提取小写主机名(去掉端口)。"""
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _base_domain(host):
    """粗提取“可注册域”:
    aaa.sany.com.cn -> sany.com.cn,www.weichai.com -> weichai.com。
    仅用于官方主页探测,非严格 eTLD+1,但覆盖常见 .com/.cn/.com.cn 等。
    """
    host = (host or "").strip(".").lower()
    if not host:
        return ""
    for suf in (".com.cn", ".net.cn", ".org.cn", ".edu.cn", ".gov.cn", ".co.uk", ".com.hk"):
        if host.endswith(suf):
            root = host[: -len(suf)]
            parts = [p for p in root.split(".") if p]
            return (parts[-1] + suf) if parts else host
    parts = [p for p in host.split(".") if p]
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host


def _probe_home_domain(base, query, timeout=6, use_browser=True):
    """探测某个公司域名根(www.域名 / 域名)是否为可访问的官网主页。

    use_browser=False 时只用严格 https 的 requests(优先官网主域名,避免误抓证书有问题/
    跳转的别名域名);True 时才允许用无头浏览器兜底(应对 WAF/JS,但也可能命中别名/旧站)。
    """
    for probe in (f"https://www.{base}", f"https://{base}"):
        try:
            # 严格模式:要求该域名根与公司相关(标题/正文含关键词),否则宁可放弃,避免误抓深交所/财经门户
            ok, _reason = _quick_url_state(
                probe, query, timeout=timeout, require_relevant=True, allow_browser=use_browser
            )
            if ok:
                return probe
        except Exception:
            continue
    return ""


_REGION_PREFIXES = (
    "北京", "上海", "天津", "重庆", "武汉", "广州", "深圳", "南京", "杭州", "西安",
    "苏州", "成都", "长沙", "青岛", "大连", "宁波", "郑州", "佛山", "东莞", "合肥",
    "福州", "厦门", "南昌", "昆明", "贵阳", "南宁", "兰州", "石家庄", "太原", "沈阳",
    "长春", "哈尔滨", "济南", "呼和浩特", "乌鲁木齐", "银川", "西宁", "拉萨", "海口",
    "广东", "江苏", "浙江", "山东", "湖北", "湖南", "河南", "河北", "四川", "陕西",
    "山西", "辽宁", "吉林", "黑龙江", "安徽", "福建", "江西", "云南", "贵州", "广西",
)
_CORP_SUFFIXES = (
    "股份有限公司", "有限责任公司", "有限公司", "集团公司", "集团", "公司", "股份", "有限责任",
)


def _brand_name(company):
    """从公司全称里粗提取“品牌名”(去掉城市前缀与公司后缀,取前几字)。
    例:武汉锐科光纤激光技术股份有限公司 -> 锐科光纤激光技术 -> 锐科
    """
    s = (company or "").strip()
    for suf in _CORP_SUFFIXES:
        s = s.replace(suf, "")
    for p in _REGION_PREFIXES:
        if s.startswith(p):
            s = s[len(p):]
            break
    s = s.strip(" 公司")
    return s


def _brand_queries(company):
    """返回用于搜官网的候选查询:优先短品牌名,再补全称,提高官方站被搜到的概率。"""
    brand = _brand_name(company)
    qs = []
    if len(brand) >= 2:
        qs.append('"%s"' % brand)  # 完整品牌(如“埃斯顿自动化”),加引号做精确短语
        for extra in (brand[:4], brand[:2]):
            q = '"%s"' % extra
            if extra and extra != brand and q not in qs:
                qs.append(q)
    qs.append('"%s"' % company)
    return qs


def _clean_company(query):
    """去掉查询里附带的“官网/招聘”等尾部词,还原成公司名,便于提取品牌名。"""
    q = re.sub(r"(官网|官方网站|招聘信息|校园招聘|人才招聘|招聘|官网)\s*$", "", query or "").strip()
    return q


def _companyish(query):
    """判断查询是否像“公司全称”(含公司后缀或城市前缀),用于触发品牌名补充搜索。"""
    q = _clean_company(query)
    return bool(q) and (any(s in q for s in _CORP_SUFFIXES) or any(q.startswith(p) for p in _REGION_PREFIXES))


def _primary_search_with_brand(query, max_results=12):
    """主搜;若查询是公司全称,再补短品牌名查询并合并结果,提高官方站被搜到的概率。"""
    out, seen = [], set()

    def add(res):
        for it in res:
            u = it.get("url", "") or ""
            if u and u not in seen:
                seen.add(u)
                out.append(it)

    # 若像公司全称/地区前缀,先搜“短品牌名 + 官网”更容易命中官网;
    # 再补原词,避免“武汉/南京”这类城市前缀把官网结果挤到后面、被城市页淹没。
    if _companyish(query):
        company = _clean_company(query)
        for b in _brand_queries(company):
            try:
                add(web_search(b + " 官网", max_results=max_results))
            except Exception:
                continue
            if len(out) >= max_results:
                return out[:max_results]
    exact = ('"%s" 官网' % _clean_company(query)) if _companyish(query) else query
    try:
        add(web_search(exact, max_results=max_results))
    except Exception:
        pass
    return out or web_search(exact, max_results=max_results)


_HOMEPAGE_CACHE = {}


def _homepage_cached(fn):
    """按公司名缓存官网主页探测结果,避免同会话/同公司重复探测。"""
    @functools.wraps(fn)
    def wrapper(company, *args, **kwargs):
        key = (company or "").strip()
        if key and key in _HOMEPAGE_CACHE:
            return _HOMEPAGE_CACHE[key]
        r = fn(company, *args, **kwargs)
        if key and r:
            _HOMEPAGE_CACHE[key] = r
        return r
    return wrapper


@_homepage_cached
def _guess_homepage(company):
    """从搜索结果猜测公司官网主页,优先探测“公司域名根”以拿到真正的首页,而非产品页/子品牌页。"""
    results = []
    seen_urls = set()
    # 同时用“短品牌名”与“全称”搜索并合并,提高官方站(常在品牌名下)被搜到的概率
    for q in _brand_queries(company):
        try:
            for it in _recruit_search(q + " 官网", max_results=8):
                u = (it.get("url") or "").strip()
                if u and u not in seen_urls:
                    seen_urls.add(u)
                    results.append(it)
        except Exception:
            continue
        if len(results) >= 14:
            break
    if not results:
        try:
            results = _recruit_search(f"{company} 官网", max_results=10)
        except Exception:
            results = []
    bases = []
    seen = set()
    for item in results:
        url = (item.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            continue
        if _is_not_official_site(url.lower()):
            continue
        base = _base_domain(_url_host(url))
        if base and base not in seen:
            seen.add(base)
            bases.append(base)
    # 优先探测“公司自己的域名”;招聘平台/品牌目录/行业门户降为兜底
    bases.sort(key=lambda b: _homepage_priority(b))
    # Pass1:只用严格 requests,优先“干净可达”的公司官网(避开证书有问题/跳转的别名域名)
    for base in bases[:3]:
        home = _probe_home_domain(base, f"{company} 官网", use_browser=False)
        if home:
            return home
    # Pass2:Pass1 没命中才用浏览器兜底(应对 WAF/JS,但可能命中别名/旧站),只试最高优先级那一个,避免多开浏览器
    for base in bases[:1]:
        home = _probe_home_domain(base, f"{company} 官网", use_browser=True)
        if home:
            return home
    # 兜底:返回第一个非黑名单候选 URL
    for item in results:
        url = (item.get("url") or "").strip()
        if url.startswith(("http://", "https://")) and not _is_not_official_site(url.lower()):
            base = _base_domain(_url_host(url))
            # 跳过平台/名录/门户/交易所等低优先级域名,避免把 chinapp/szse/ce.cn 当官网
            if base and _homepage_priority(base) == 1:
                continue
            return url
    return ""


# 官网主页探测时的低优先级域名片段:命中说明大概率不是公司自己的官网,应后置探测。
_HOME_LOW_PRIORITY_HOSTS = (
    "jobui.com", "liepin.com", "zhaopin.com", "51job.com", "mokahr.com", "hotjob.com",
    "bosszhipin.com", "zhipin.com", "58.com", "ganji.com", "chinapp.com", "maigoo.com",
    "lmjx.net", "zhuangbei.cn", "d1cm.com", "hc360.com", "made-in-china.com", "1688.com",
    "alibaba.com", "nowcoder.com", "gaodun.com", "beisen.com",
    # 交易所 / 财经 / 新闻门户(非公司官网)
    "szse.cn", "sse.com.cn", "ce.cn", "cnstock.com", "eastmoney.com", "cs.com.cn",
    "stcn.com", "cls.cn", "10jqka.com.cn", "hexun.com",
    # 展会 / 组织 / 工业门户(会在页面上列公司名,但并非公司官网)
    "tctasia.cn", "chinaepu.com", "cehome.com", "d1cm.com", "zhuangbei.cn",
    "made-in-china.com", "c-cnc.com", "china-cc.org", "myzaker.com", "cnfol.com",
)


def _homepage_priority(base):
    """越小越优先。含平台/名录/门户片段则给高优先级值(靠后探测)。"""
    base = (base or "").lower()
    return 1 if any(h in base for h in _HOME_LOW_PRIORITY_HOSTS) else 0


def _search_results_hit(results, query):
    """判断快速搜索结果是否“够用”,用于决定要不要再升级到 verified_search。

    命中条件(宽松):是合法 http(s) 链接 + 不在 _is_not_official_site 黑名单
    (百科/企业信息聚合/资讯/问答等,这些不是可用的招聘/官网候选) + 标题/摘要非空且与查询相关。
    招聘平台(mokahr/hotjob/51job)、品牌目录站(chinapp/maigoo)、行业门户(lmjx.net)等
    都允许作为候选,不再当作“非公司官网”而排除。
    """
    tokens = [t for t in re.split(r"[^\w\u4e00-\u9fff]+", query or "") if len(t) >= 2]
    for item in results or []:
        url = (item.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            continue
        low = url.lower()
        if _is_not_official_site(low):
            continue
        title = (item.get("title") or "").strip()
        snippet = (item.get("snippet") or "").strip()
        if not (title or snippet):
            continue
        if not tokens:
            return True
        blob = (url + " " + title + " " + snippet).lower()
        if any(t.lower() in blob for t in tokens):
            return True
    return False


def _recruit_search(query, max_results=8):
    """find_recruitment_links 内部统一搜索入口(默认“快速搜,命中不了再自动升级”)。

    - 先用 web_search 快速搜;若返回了至少一条“非百科/信息聚合/问答站且与查询相关”的结果即直接采用(快)。
      招聘平台、品牌目录站、行业门户等都可作为候选,不再排除。
    - 若快速结果不达标(全是百科/信息聚合/无关/空标题),自动升级到 verified_search 做真实性链
      (主搜→审查→free-search-mcp→再审查),拿更可信的候选链接。
    - 可用 FIND_RECRUIT_USE_VERIFIED 控制:1/on/always 强制走 verified;0/off/never 强制只用 web_search。
    """
    mode = os.environ.get("FIND_RECRUIT_USE_VERIFIED", "").strip().lower()
    always_verify = mode in ("1", "true", "on", "yes", "always")
    never_verify = mode in ("0", "false", "off", "no", "never")

    fast = None
    if not always_verify:
        try:
            fast = web_search(query, max_results=max_results) or []
        except Exception:
            fast = None
        if fast and _search_results_hit(fast, query):
            return fast  # 快速命中,直接返回,不死磕
        if never_verify:
            return fast or []

    # 自动升级 / 强制 verified:解包 verified_search 返回的 {results,...}
    try:
        data = verified_search(query, max_results=max_results)
        results = data.get("results") if isinstance(data, dict) else (list(data) or [])
        return results or []
    except Exception:
        # 升级失败时退回快速结果(若有),避免无谓报错
        return fast or []


def _is_not_official_site(low_url):
    """判断一个 URL 是否“只是描述公司/企业的页面”,而非官网/招聘候选。

    改为按域名(host)做后缀匹配,避免旧版把 `news`/`wenshu`/`sipo` 等宽泛子串用于整条
    URL 匹配而误杀官网站点(如 /home/news/ 路径)。这里只排除“百科/企业信息聚合/资讯/问答/
    描述性平台”这类会替公司代言的站;招聘平台(mokahr/hotjob/51job)、品牌目录站、行业门户
    都不在此列(它们可作为招聘候选输出)。
    """
    host = _url_host(low_url)
    if not host:
        return False
    for b in _NOT_INFORMATIONAL_HOSTS:
        if host == b or host.endswith("." + b):
            return True
    return False


# 只描述公司、替公司代言的“信息型”站域名(按 host 后缀匹配):
# 百科/问答/资讯/企业信息聚合/社交视频等,不是公司官网,也不是可用招聘候选。
_NOT_INFORMATIONAL_HOSTS = (
    # 百科 / 问答 / 社区
    "baike.baidu.com", "zh.wikipedia.org", "wikipedia.org", "zhihu.com",
    "baike.sogou.com", "douban.com", "360doc.com", "tieba.baidu.com",
    "wenku.baidu.com",
    # 企业信息 / 数据聚合 / 资讯
    "baidu.com", "qcc.com", "tianyancha.com", "qixin.com", "aiqicha.baidu.com",
    "aiqicha.com", "11467.com", "askci.com", "pedaily.cn", "36kr.com",
    "plfrog.com", "sina.com.cn", "cnr.cn", "news.cn", "xinhuanet.com",
    # 其他描述性平台 / 搜索引擎
    "autohome.com", "xueqiu.com", "bilibili.com", "weibo.com", "linkedin.com",
    "sogou.com", "so.com", "cjoblist.com", "chinagazelle.cn", "ccpc360.com",
)


_RECRUIT_CACHE = {}


def _recruit_cached(fn):
    """按公司名缓存招聘入口挖掘结果,避免同会话/同公司重复搜索。"""
    # 必须保留原函数名:注册工具时按 __name__ 入表,少了这行会把工具注册成 wrapper,
    # 导致大模型调用 find_recruitment_links 时收到“未知工具”,招聘入口发现整条链路失效。
    @functools.wraps(fn)
    def wrapper(company, homepage="", *args, **kwargs):
        key = (company or "").strip()
        if key and key in _RECRUIT_CACHE:
            return _RECRUIT_CACHE[key]
        r = fn(company, homepage, *args, **kwargs)
        if key and r and not isinstance(r, dict):
            _RECRUIT_CACHE[key] = r
        return r
    return wrapper


@register_tool
@_recruit_cached
def find_recruitment_links(company, homepage=""):
    """发掘公司真实的招聘官网/网申入口链接,返回候选链接列表。

    优先抓取公司官网主页(通过 homepage 参数或 web_search 自动推断),提取导航
    中\"招聘/加入我们/Careers\"的真实链接(如 mokahr、hotjob 等招聘平台);
    再用 web_search 搜\"校园招聘 网申 官网\",从结果正文里筛出真实网申地址。
    全部候选均来自真实页面或搜索结果,避免在官网下乱猜子路径。

    返回顺序即优先级(官网导航里挖到的最可信,排第一),并已剔除域名解析失败的
    死链(企业旧招聘子域常见);每项带 priority 字段(1 = 最优先渲染)。
    """
    company = (company or "").strip()
    if not company:
        return {"error": "缺少公司名称"}
    candidates = []
    seen = set()

    def add(url, title="", source="搜索"):
        url = (url or "").strip()
        # 去掉搜索引擎在链接后拼接的括号/全角标点
        url = url.rstrip(")}]，。；、）〕》")
        if not url.startswith(("http://", "https://")):
            return
        if url in seen:
            return
        if not _looks_like_recruitment(url, title, ""):
            return
        # 域名都解析不了的直接剔除(如企业已下线的旧网申子域),不占用抓取额度
        if not _url_resolves(url):
            return
        seen.add(url)
        candidates.append({"title": title[:80], "url": url, "source": source})

    # 1) 官网主页导航里的招聘入口(最权威)
    if not homepage:
        homepage = _guess_homepage(company)
    if homepage:
        for u in _extract_homepage_recruit(homepage):
            add(u, "", "官网主页")

    # 2) 搜索\"校园招聘 网申 官网\"补充真实网申地址
    for q in (
        f"{company} 校园招聘 网申 官网",
        f"{company} 招聘官网",
        f"{company} 校招 网申入口",
    ):
        if len(candidates) >= 8:
            break
        try:
            results = _recruit_search(q, max_results=8)
        except Exception:
            continue
        for item in results:
            add(item.get("url", ""), item.get("title", ""))
            # 搜索摘要里常直接写出真实网申地址,一并抓出来
            for u in re.findall(r"https?://[^\s<>\"'、）)]+", item.get("snippet", "")):
                add(u, item.get("title", ""))
            if len(candidates) >= 8:
                break

    # 3) 主页明明能访问却未挖到招聘入口:把官网本身作为兜底,让 Agent 进去人工找
    if not candidates and homepage:
        return [
            {
                "title": "官网主页(首页导航未直接发现招聘入口,请进入后自行查找)",
                "url": homepage,
                "source": "官网主页",
                "priority": 1,
            }
        ]

    if not candidates:
        return {"error": f"未能找到 {company} 的招聘入口,请核对公司全称或改用其他关键词"}
    top = candidates[:10]
    for i, c in enumerate(top, 1):
        c["priority"] = i
    return top


@register_tool
def web_search(query, max_results=8):
    """联网搜索,返回标题/链接/摘要列表。默认优先百度(国内可访问,对中文公司官网
    定位最准),失败后依次回退 Bing、Anspire。"""
    errors = []
    for engine in _search_engines():
        try:
            if engine == "baidu":
                results = _baidu_search(query, max_results=max_results)
            elif engine == "bing":
                results = _bing_search(query, max_results=max_results)
            elif engine == "duckduckgo":
                results = _duckduckgo_search(query, max_results=max_results, timeout=8)
            elif engine == "anspire":
                results = _anspire_search(query, max_results=max_results)
            else:
                continue
            if results:
                return results
            errors.append(f"{engine}: 无结果")
        except Exception as exc:
            errors.append(f"{engine}: {exc}")
    raise RuntimeError("联网搜索失败(" + "; ".join(errors) + "),请稍后重试")


def _search_engines():
    """按 SEARCH_ENGINE 决定回退顺序,默认百度优先,最后才用 Anspire(付费)。
    把 Anspire 放在最后,尊重“默认联网搜索优先于 Anspire”的设定。"""
    eng = SEARCH_ENGINE
    has_anspire = bool(os.environ.get("ANSPIRE_API_KEY", "").strip())
    if eng == "duckduckgo":
        order = ["duckduckgo", "bing", "baidu"]
        return order if not has_anspire else order + ["anspire"]
    if eng == "bing":
        order = ["bing", "baidu"]
        return order if not has_anspire else order + ["anspire"]
    if eng == "anspire":
        return ["anspire", "baidu", "bing"] if has_anspire else ["baidu", "bing"]
    # 默认:baidu。百度对中文公司官网最准,但偶被反爬;此时直接回退到 Anspire(可靠),
    # 再才是 Bing(对小众中文公司常返回无关结果,故放在 Anspire 之后)。
    order = ["baidu", "bing"]
    return order if not has_anspire else ["baidu", "anspire", "bing"]


def _anspire_search(query, max_results=8):
    """调用 Anspire AI Search,并把结果统一成 {title,url,snippet} 结构。"""
    from .anspire import anspire_search

    raw = anspire_search(query, top_k=max_results)
    results = []
    for item in raw:
        results.append(
            {
                "title": (item.get("title") or "").strip()[:80],
                "url": (item.get("url") or "").strip(),
                "snippet": (item.get("content") or "").strip()[:200],
            }
        )
    if not results:
        raise RuntimeError("Anspire 无结果")
    return results[:max_results] if max_results else results


# ---------------- 搜索审查 + 回退链(verified_search) ----------------


def _deepseek_web_enabled():
    """DeepSeek 自带联网搜索是否启用(DEEPSEEK_WEB_SEARCH=1/auto)。"""
    return os.environ.get("DEEPSEEK_WEB_SEARCH", "").strip().lower() in ("1", "true", "on", "yes", "auto")


def _browser_available():
    """是否可用 Chrome/Edge 做无头渲染兜底(用于 requests 打不开时二次确认)。"""
    return bool(_find_browser())


def _render_reachability(url, query, wait_ms=6000, timeout=25):
    """用 Playwright 无头浏览器渲染,确认页面是否真的能打开(应对 WAF/JS 挡掉的官网)。
    返回 (ok, reason)。在 requests 初测失败时才调用,作为“真浏览器兜底”。"""
    try:
        html = _render_dom_playwright(url, wait_ms=wait_ms, timeout=timeout)
    except Exception as exc:
        return False, f"浏览器渲染失败:{type(exc).__name__}"
    if not html or len(html) < 200:
        return False, "浏览器渲染无内容"
    t = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    title = _clean_text(re.sub(r"<[^>]+>", "", t.group(1))) if t else ""
    tokens = [tt for tt in re.split(r"[^\w\u4e00-\u9fff]+", query or "") if len(tt) >= 2]
    blob = (html.lower() + " " + title.lower())
    rel = (any(tt.lower() in blob for tt in tokens)) if tokens else True
    return True, ("浏览器可达(" + ("相关" if rel else "标题:" + (title[:20] or "无")) + ")")


def _quick_url_state(url, query, timeout=6, allow_browser=True, require_relevant=False):
    """快速连通性+相关度检查,返回 (ok, reason)。

    改为“非流式 GET + 状态码 + 有限正文”,避免旧版 iter_content 流式读正文触发部分官网
    后端连接重置(ConnectionError)而把可达官网误判为失效。requests 打不开(连接/超时/
    HTTP>=400)时,若允许则再用无头浏览器二次确认(应对 WAF/JS),进一步减少误判。
    """
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        return False, "非 http 链接"
    low = url.lower()
    if _is_not_official_site(low):
        return False, "疑似聚合/百科/平台站"
    text = ""
    try:
        with requests.get(url, headers=_headers(), timeout=timeout, allow_redirects=True) as resp:
            if resp.status_code >= 400:
                return False, f"HTTP {resp.status_code}"
            cl = resp.headers.get("Content-Length")
            if cl and cl.isdigit() and int(cl) > 2_000_000:
                return True, "可达(大文件,需浏览器处理)"
            # 只读有限大小正文,避免大页面/流式读取触发连接重置
            text = resp.content[:30000].decode("utf-8", "replace")
    except requests.RequestException as exc:
        if allow_browser and _browser_available():
            ok, reason = _render_reachability(url, query)
            if ok:
                return True, reason
        return False, f"打开失败:{type(exc).__name__}"
    title_match = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
    title = _clean_text(re.sub(r"<[^>]+>", "", title_match.group(1))) if title_match else ""
    tokens = [t for t in re.split(r"[^\w\u4e00-\u9fff]+", query or "") if len(t) >= 2]
    # 用“域名+标题”判断相关,而不是“正文里提及公司”,避免把展会/新闻等“提到公司”的页面当官网
    title_blob = (low + " " + title).lower()
    if tokens and any(t.lower() in title_blob for t in tokens):
        return True, "可达且相关"
    if require_relevant:
        # 严格模式(官网主页探测用):标题里没有公司关键词,说明是“提到公司”的非官网页(展会/新闻/聚合)则拒绝;
        # 无标题/疑似 JS 页则保留(可能是 SPA 官网,交给后续 browser 判断)。
        if not title:
            return True, "可达(无明确标题,疑似动态页)"
        return False, "可达但标题非公司官网(标题:" + (title[:24] or "无") + ")"
    if title or len(text) > 200:
        return True, ("可达(标题: " + title[:30] + ")") if title else "可达但未匹配关键词"
    return True, "可达但内容过少"


def _verify_candidate_rank(item):
    """越靠前越像“官网候选”:先排除信息型/聚合站,再排除政府/地图页,最后才是平台/名录/门户。

    用于 _verify_results 抽样时优先挑真正官网,避免“前两条恰是城市/聚合页”导致整组误判失败。
    """
    url = (item.get("url") or "").lower()
    host = _url_host(url)
    base = _base_domain(host)
    info = 2 if _is_not_official_site(url) else 0
    geo = 1 if (host.endswith(".gov.cn") or "map.baidu.com" in host) else 0
    low = 1 if _homepage_priority(base) else 0
    return (info, geo, low)


def _verify_results(query, results, sample=2, timeout=6):
    """对搜索结果做真实性初筛,返回 {ok, checked, pass_ratio, note}。"""
    if not results:
        return {"ok": False, "checked": [], "pass_ratio": 0.0, "note": "无结果"}
    # 优先挑“更像官网”的候选再探测,而非机械取前 2 条
    items = sorted(results, key=_verify_candidate_rank)[:sample]
    # 并发探测各候选 URL,显著缩短“多家公司/多个链接串行校验”的耗时
    with ThreadPoolExecutor(max_workers=min(len(items), 3)) as ex:
        futs = [ex.submit(_quick_url_state, it.get("url", ""), query, timeout=timeout) for it in items]
        states = []
        for f in futs:
            try:
                states.append(f.result())
            except Exception:
                states.append((False, "校验异常"))
    checked = []
    for it, (ok, reason) in zip(items, states):
        checked.append(
            {
                "url": it.get("url", ""),
                "ok": ok,
                "reason": reason,
                # 是否依赖“真浏览器兜底”才能打开(证书有问题/跳转/别名域名的信号,应排在官网主域名之后)
                "via_browser": reason.startswith("浏览器可达"),
            }
        )
    ok_count = sum(1 for c in checked if c["ok"])
    if checked and ok_count == 0:
        return {
            "ok": False,
            "checked": checked,
            "pass_ratio": 0.0,
            "note": "抽样结果均不可达或疑似无效,已触发回退",
        }
    return {
        "ok": ok_count >= 1,
        "checked": checked,
        "pass_ratio": round(ok_count / len(checked), 2) if checked else 0.0,
        "note": "抽样通过" if ok_count >= 1 else "",
    }


def _pack_results(results, stage, verify, trace, verified=True):
    return {
        "results": results,
        "stage": stage,
        "verified": verified,
        "verify": verify,
        "trace": trace,
        "note": (
            f"本组结果由 {stage} 提供,已做真实性初筛({'通过' if verified else '未完全通过'})。"
            "若某项官网/信息仍存疑,请将该子项单独作为关键词重新调用 verified_search,"
            "不要直接采用未核实链接。"
        ),
    }


def deepseek_web_search(query, max_results=8, timeout=15):
    """尝试 DeepSeek 自带联网搜索(OpenAI 兼容的 web_search 工具)。

    当 DeepSeek 端点和模型真正支持 web_search 工具时返回其抓取结果;否则抛出异常,
    由 verified_search 捕获并进入下一级(或标记为未验证)。仅在 DEEPSEEK_WEB_SEARCH=1
    时才会被调用,默认关闭以避免每次搜索都增加一段不确定时长的联网调用。
    """
    from .llm import API_KEY, BASE_URL, MODEL

    if not (API_KEY or "").strip():
        raise RuntimeError("未配置 DEEPSEEK_API_KEY,无法使用 DeepSeek 联网搜索")
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是网页搜索助手。请针对用户的查询进行实时搜索,只输出真实可访问、"
                    "且与企业/岗位/证书相关的官方或权威结果,严禁编造 URL。"
                    '以 JSON 数组返回,每项包含 title、url、snippet。'
                ),
            },
            {"role": "user", "content": query},
        ],
        "temperature": 0.2,
        "max_tokens": 384000,
        "tools": [{"type": "web_search"}],
        "tool_choice": "auto",
    }
    try:
        resp = requests.post(
            f"{BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json=payload,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"DeepSeek 联网搜索连接失败: {exc}") from exc
    if resp.status_code != 200:
        raise RuntimeError(f"DeepSeek 联网搜索返回错误 {resp.status_code}: {resp.text[:200]}")
    content = (resp.json().get("choices", [{}])[0].get("message", {}) or {}).get("content") or ""
    results = _parse_links_from_text(content)
    if results:
        return results[:max_results] if max_results else results
    raise RuntimeError("DeepSeek 联网搜索未返回可解析结果")


def _parse_links_from_text(text):
    """从模型文本中尽量解析出 {title,url,snippet} 列表;若整体是 JSON 数组则优先解析。"""
    text = (text or "").strip()
    if not text:
        return []
    # 优先尝试 JSON 数组
    t = text
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:].strip()
    for m in re.finditer(r"\[.*\]", t, re.S):
        try:
            arr = json.loads(m.group(0))
        except ValueError:
            continue
        if isinstance(arr, list):
            out = []
            for it in arr:
                if not isinstance(it, dict):
                    continue
                url = (it.get("url") or "").strip()
                if not url.startswith(("http://", "https://")):
                    continue
                out.append(
                    {
                        "title": (it.get("title") or "").strip()[:100],
                        "url": url,
                        "snippet": (it.get("snippet") or "").strip()[:200],
                    }
                )
            if out:
                return out
    # 退化为 regex 抓 URL
    out = []
    for u in re.findall(r"https?://[^\s<>\"'）)]+", t):
        out.append({"title": "", "url": u, "snippet": ""})
        if len(out) >= 12:
            break
    return out


@register_tool
def verified_search(query, max_results=12):
    """按“主搜→审查→free-search-mcp→再审查→DeepSeek→局部重搜”链式搜索。

    先使用默认联网搜索插件(web_search)并抽样做真实性审查;若审查不通过(网站失效、
    官网搜不到、疑似编造等),改用 free-search-mcp 的多引擎搜索结果并再次审查;仍失败
    再尝试 DeepSeek 自带联网搜索。返回的 results 附带 stage/verified/verify/trace 供判断:
    - verified=true 表示某一级搜索已通过初筛;
    - verified=false 表示各级都未通过初筛,只返回了相对最好的一组,需要模型把仍有疑问
      的子项(如某家公司官网)单独作为关键词再次调用 verified_search,不要直接采用。
    适用于查找企业官网、招聘岗位、证书学习资源等对链接真实性要求较高的场景。
    """
    query = (query or "").strip()
    if not query:
        raise RuntimeError("verified_search 缺少查询关键词")
    trace = []
    primary = []

    # 1) 主搜 + 真实性初筛
    try:
        primary = _primary_search_with_brand(query, max_results=max_results)
        v = _verify_results(query, primary)
        trace.append({"stage": "web_search", "count": len(primary), "pass": v["ok"], "detail": v.get("note", "")})
        if v["ok"]:
            return _pack_results(primary, "web_search", v, trace, verified=True)
        # 主搜有结果但初筛未全过:不立即丢弃,先尝试 free-search-mcp 多引擎回退,避免被单一引擎切词带偏
        try:
            alt = free_search(query, max_results=max_results)
            v2 = _verify_results(query, alt)
            trace.append({"stage": "free_search_mcp", "count": len(alt), "pass": v2["ok"], "detail": v2.get("note", "")})
            if v2["ok"]:
                return _pack_results(alt, "free_search_mcp", v2, trace, verified=True)
            if alt:
                return _pack_results(alt, "free_search_mcp", v2, trace, verified=False)
        except Exception as exc:
            trace.append({"stage": "free_search_mcp", "count": 0, "pass": False, "detail": str(exc)[:160]})
        return _pack_results(primary, "web_search", v, trace, verified=False)
    except Exception as exc:
        trace.append({"stage": "web_search", "count": 0, "pass": False, "detail": str(exc)[:160]})

    # 2) 主搜完全无结果时,才启用 free-search-mcp 回退
    try:
        alt = free_search(query, max_results=max_results)
        v2 = _verify_results(query, alt)
        trace.append({"stage": "free_search_mcp", "count": len(alt), "pass": v2["ok"], "detail": v2.get("note", "")})
        if v2["ok"]:
            return _pack_results(alt, "free_search_mcp", v2, trace, verified=True)
        if alt:
            return _pack_results(alt, "free_search_mcp", v2, trace, verified=False)
    except Exception as exc:
        trace.append({"stage": "free_search_mcp", "count": 0, "pass": False, "detail": str(exc)[:160]})

    # 3) 仍无结果且开启 DeepSeek 联网时才尝试
    if _deepseek_web_enabled():
        try:
            ds = deepseek_web_search(query, max_results=max_results)
            v3 = _verify_results(query, ds)
            trace.append({"stage": "deepseek_web", "count": len(ds), "pass": v3["ok"], "detail": v3.get("note", "")})
            if v3["ok"]:
                return _pack_results(ds, "deepseek_web", v3, trace, verified=True)
            if ds:
                return _pack_results(ds, "deepseek_web", v3, trace, verified=False)
        except Exception as exc:
            trace.append({"stage": "deepseek_web", "count": 0, "pass": False, "detail": str(exc)[:160]})

    raise RuntimeError(
        "联网搜索未获可用结果(主搜无结果,且 free-search-mcp/DeepSeek 回退也未提供可用结果)。"
        "请更换关键词,或针对某一具体子项(如某家公司/某个证书)单独搜索。"
    )


@register_tool
def fetch_page(url, max_chars=6000):
    """读取网页正文文本,用于查看官网招聘页等内容。"""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    resp = requests.get(url, headers=_headers(), timeout=20, allow_redirects=True)
    resp.raise_for_status()

    ctype = resp.headers.get("Content-Type", "")
    if "pdf" in ctype.lower():
        return {"url": resp.url, "title": url, "text": "[PDF 文件,建议下载后查看]"}

    # 手动按真实 charset 解码,避免 requests 误判编码导致乱码
    raw = resp.content
    enc = (resp.encoding or "").lower()
    if enc in ("iso-8859-1", "ascii", ""):
        m = re.search(rb"charset=[\"']?([\w-]+)", raw[:4096], re.I)
        enc = m.group(1).decode("ascii", "ignore").lower() if m else "utf-8"
        try:
            text = raw.decode(enc, "replace")
        except LookupError:
            text = raw.decode("utf-8", "replace")
    else:
        text = raw.decode(enc, "replace")

    title_match = re.search(r"<title[^>]*>(.*?)</title>", text, re.S | re.I)
    title = _clean_text(re.sub(r"<[^>]+>", "", title_match.group(1))) if title_match else ""
    text = _html_to_text(text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return {"url": resp.url, "title": title[:200], "text": text[:max_chars]}


def _find_browser():
    """定位本机可用的 Chrome / Edge,用于无头渲染动态网页。"""
    candidates = [
        os.environ.get("AGENT_BROWSER_PATH", "").strip(),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    for name in (
        "google-chrome", "google-chrome-stable", "chromium",
        "chromium-browser", "microsoft-edge", "msedge",
    ):
        path = shutil.which(name)
        if path:
            return path
    return None


def _render_dom(url, wait_ms=12000, timeout=50, profile=None):
    """用无头 Chrome/Edge 渲染页面并返回渲染后的 HTML。"""
    browser = _find_browser()
    if not browser:
        raise RuntimeError("未找到 Chrome/Edge 浏览器,无法渲染动态网页")

    own_profile = not profile
    for headless_flag in ("--headless=new", "--headless"):
        prof = profile or tempfile.mkdtemp(prefix="agent_render_")
        cmd = [
            browser,
            headless_flag,
            "--disable-gpu",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--disable-features=TranslateUI,IsolateOrigins,site-per-process",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-infobars",
            "--disable-background-networking",
            "--hide-scrollbars",
            "--mute-audio",
            "--lang=zh-CN",
            "--window-size=1920,1080",
            f"--user-agent={UA}",
            "--run-all-compositor-stages-before-draw",
            f"--virtual-time-budget={wait_ms}",
            f"--user-data-dir={prof}",
            "--dump-dom",
            url,
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
            out = proc.stdout or b""
            if not out and proc.stderr:
                out = proc.stderr
        except subprocess.TimeoutExpired:
            out = b""
        finally:
            if own_profile:
                shutil.rmtree(prof, ignore_errors=True)

        html = out.decode("utf-8", "replace")
        if html.strip() and ("<html" in html.lower() or "<body" in html.lower()):
            return html
    raise RuntimeError("浏览器未能返回页面内容,请稍后重试")


def _render_dom_playwright(url, wait_ms=12000, timeout=50):
    """用 Playwright 驱动 Edge/Chrome 渲染页面,返回渲染后的 HTML。

    专用于 render_page;图书搜索使用的 _render_dom 保持原样,不受影响。
    Playwright 能等待异步 XHR、支持 SPA hash 路由,从而抓到动态加载的正文。
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("未安装 Playwright,请先 pip install playwright") from exc

    channel = os.environ.get("AGENT_BROWSER_CHANNEL", _DEFAULT_BROWSER_CHANNEL).strip() or _DEFAULT_BROWSER_CHANNEL
    html = ""
    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel=channel,
            headless=True,
            args=[
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-infobars",
                "--disable-background-networking",
                "--lang=zh-CN",
                "--window-size=1920,1080",
            ],
        )
        context = browser.new_context(
            user_agent=UA,
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            ignore_https_errors=True,
        )
        # 隐藏 webdriver 痕迹,缓解部分反爬(方案4)
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=int(timeout * 1000))
            try:
                page.wait_for_load_state("networkidle", timeout=int(wait_ms))
            except Exception:
                pass
            page.wait_for_timeout(1500)
            html = page.content()
        except Exception:
            html = ""
        finally:
            try:
                context.close()
            except Exception:
                pass
            try:
                browser.close()
            except Exception:
                pass
    return html


def _render_dom_playwright_search(url, keyword, wait_ms=12000, timeout=50):
    """用 Playwright 打开招聘页,若存在搜索框则自动输入 keyword 并回车,等结果渲染后返回 HTML。

    针对“只能通过搜索框定向查询岗位”的 SPA 招聘页(方案1)。定位不到搜索框时返回原始渲染 HTML。
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("未安装 Playwright,请先 pip install playwright") from exc

    channel = os.environ.get("AGENT_BROWSER_CHANNEL", _DEFAULT_BROWSER_CHANNEL).strip() or _DEFAULT_BROWSER_CHANNEL
    html = ""
    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel=channel,
            headless=True,
            args=[
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-infobars",
                "--disable-background-networking",
                "--lang=zh-CN",
                "--window-size=1920,1080",
            ],
        )
        context = browser.new_context(
            user_agent=UA,
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            ignore_https_errors=True,
        )
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=int(timeout * 1000))
            try:
                page.wait_for_load_state("networkidle", timeout=int(min(wait_ms, 8000)))
            except Exception:
                pass
            page.wait_for_timeout(1000)
            # 尝试定位岗位搜索框(招聘站常用 placeholder/name)
            searcher = None
            for sel in (
                'input[type="search"]',
                'input[placeholder*="搜索"]',
                'input[placeholder*="岗位"]',
                'input[placeholder*="职位"]',
                'input[placeholder*="关键词"]',
                'input[placeholder*="keyword" i]',
                'input[placeholder*="job" i]',
            ):
                try:
                    if page.locator(sel).count() > 0:
                        searcher = page.locator(sel).first
                        break
                except Exception:
                    continue
            if searcher is not None:
                try:
                    searcher.fill(keyword)
                    searcher.press("Enter")
                    try:
                        page.wait_for_load_state("networkidle", timeout=int(wait_ms))
                    except Exception:
                        pass
                    page.wait_for_timeout(1500)
                except Exception:
                    pass
            html = page.content()
        except Exception:
            html = ""
        finally:
            try:
                context.close()
            except Exception:
                pass
            try:
                browser.close()
            except Exception:
                pass
    return html


def _collect_jobs(html, url):
    """从渲染后的列表页提取“职位标题 + 详情链接”对,供 Agent 逐个打开抓 JD。

    除通用特征外,命中招聘平台适配表时还会补上该平台自己的职位链接特征
    (如 mokahr 的 `#/job/`),避免因各站点 URL 形态不同而漏掉岗位。
    """
    keys = ["jobid=", "/jobs", "#/job", "positionid", "job-detail"]
    platform = _recruit_platform(url)
    if platform:
        keys += [k for k in platform.get("job_patterns", ()) if k not in keys]
    jobs = []
    seen = set()
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    for match in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.S):
        href = html_mod.unescape(match.group(1)).strip()
        low = href.lower()
        if low.startswith(("javascript", "mailto:", "tel:")):
            continue
        if not any(k in low for k in keys):
            continue
        if href in seen:
            continue
        seen.add(href)
        title = _clean_text(re.sub(r"<[^>]+>", "", match.group(2)))
        if href.startswith("//"):
            href = "https:" + href
        elif href.startswith("/"):
            href = urljoin(origin, href)
        elif href.startswith("#"):
            href = urljoin(url, href)
        jobs.append({"title": title[:80], "url": href})
    return jobs[:20]


_JOB_SEARCH_MEMO = {}


# 常见网申/招聘平台适配表:命中后按已知形态处理,不必每次靠通用规则猜。
# public=True 表示“职位列表公开可看”(登录只用于投递),不能预判成登录墙。
_RECRUIT_PLATFORMS = (
    {
        "key": "mokahr",
        "name": "Moka(mokahr)",
        "hosts": ("mokahr.com",),
        "public": True,
        "job_patterns": ("#/job/",),
        "campus_keys": ("校园招聘", "校招"),
    },
    {
        "key": "hotjob",
        "name": "HotJob",
        "hosts": ("hotjob.cn",),
        "public": True,
        "job_patterns": ("jobid=", "/job/"),
        "campus_keys": ("校园招聘", "校招"),
    },
    {
        "key": "beisen",
        "name": "北森网申",
        "hosts": ("zhiye.com",),
        "public": False,          # 该平台职位列表常需登录后才加载
        "job_patterns": ("jobid=", "positionid", "/job/"),
        "campus_keys": ("校园招聘", "校招"),
    },
)


def _recruit_platform(url):
    """按域名匹配招聘平台适配表,命中返回该平台配置,否则返回 None。"""
    host = _url_host(url or "")
    if not host:
        return None
    for p in _RECRUIT_PLATFORMS:
        for h in p["hosts"]:
            if host == h or host.endswith("." + h):
                return p
    return None


_HOST_DNS_CACHE = {}


def _host_resolves(host):
    """域名能否解析(带缓存)。用于在浪费一次渲染前剔除已下线的招聘子域。"""
    host = (host or "").strip().lower()
    if not host:
        return False
    if _HOST_DNS_CACHE.get(host):
        return True
    try:
        socket.getaddrinfo(host, None)
    except Exception:
        # 只缓存“能解析”的结果:偶发解析抖动不会把正常站点长期误判为死链
        return False
    _HOST_DNS_CACHE[host] = True
    return True


def _url_resolves(url):
    """URL 的主机名能否解析。"""
    return _host_resolves(_url_host(url or ""))


_LOGIN_WALL_HOSTS = (
    "hr.hgtech.com.cn",
    "redsea",
    "zhiye.com",
    "ssp",
)


def _is_login_wall(url):
    """判断是否为需登录的招聘系统(企业自研/网申平台),命中则不应反复渲染。

    适配表里 public=True 的平台(如 mokahr)职位列表是公开可看的,登录只用于投递,
    不能预判成登录墙——否则一旦渲染慢或页面结构变化,官方可抓的岗位会被误判成“需登录”。
    """
    platform = _recruit_platform(url)
    if platform:
        return not platform.get("public", True)
    low = (url or "").lower()
    return any(h in low for h in _LOGIN_WALL_HOSTS)


def _find_campus_url(html, url, platform=None):
    """从页面导航里找出“校园招聘”入口链接(校招岗位对在校生才有意义)。"""
    keys = (platform or {}).get("campus_keys", ("校园招聘", "校招"))
    for m in re.finditer(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S | re.I):
        text = _clean_text(re.sub(r"<[^>]+>", "", m.group(2)))
        if not text or not any(k in text for k in keys):
            continue
        href = html_mod.unescape(m.group(1)).strip()
        if href.startswith(("#", "/")):
            href = urljoin(url, href)
        if href.startswith(("http://", "https://")):
            return href
    return ""


@register_tool
def render_page(url, max_chars=9000, wait_ms=12000, keyword=""):
    """用 Playwright 无头浏览器渲染网页(执行 JS、等待 XHR)后抓取正文,
    专用于前端动态渲染的招聘页。返回 {url,title,text};
    若页面含职位详情链接则附 jobs;若职位失效则附 expired=true;
    若页面为“只能通过搜索框定向查询”的 SPA 招聘页,附 needs_keyword=true;
    若域名无法解析或页面没有正文,附 unreachable=true(表示该地址已失效,应改用其他入口);
    命中招聘平台适配表时附 platform,页面存在校园招聘入口时附 campus_url。
    keyword 非空时会自动在页面搜索框输入岗位关键词并回车(方案1/2),等待结果渲染再返回。
    Playwright 不可用时回退到旧渲染方式。
    """
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    # 先做域名解析校验:已下线的招聘子域直接判定不可用,既省掉一次渲染,
    # 也避免空壳页被误判成“需登录”而让 Agent 放弃官方渠道。
    if not _url_resolves(url):
        return {
            "url": url,
            "title": "",
            "text": "",
            "unreachable": True,
            "note": "该域名无法解析(地址有误或站点已下线),请改用 find_recruitment_links 返回的其他候选入口,不要据此判断该公司没有岗位。",
        }
    kw = (keyword or "").strip()
    try:
        if kw:
            html = _render_dom_playwright_search(url, kw, wait_ms=wait_ms)
            if len(html) < 200:
                html = _render_dom_playwright(url, wait_ms=wait_ms)
        else:
            html = _render_dom_playwright(url, wait_ms=wait_ms)
    except Exception as exc:
        print(f"[tools] render_page Playwright 失败,回退到 _render_dom: {exc}")
        html = _render_dom(url, wait_ms=wait_ms)
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    title = _clean_text(re.sub(r"<[^>]+>", "", title_match.group(1))) if title_match else ""
    text = _html_to_text(html)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    result = {"url": url, "title": title[:200], "text": text[:max_chars]}
    platform = _recruit_platform(url)
    if platform:
        result["platform"] = platform["name"]
    if len(text.strip()) < 40:
        # 空壳页:多为站点已下线或内容未渲染出来,与“需登录”是两回事,必须区分开
        result["unreachable"] = True
        result["note"] = "该页面没有正文内容(站点可能已下线或未渲染出内容),请改用其他候选入口,不要据此判断该公司没有岗位。"
        return result
    campus = _find_campus_url(html, url, platform)
    if campus:
        result["campus_url"] = campus
    # 方案3:失效职位检测
    if re.search(
        r"(该职位已失效|职位已失效|该岗位已失效|岗位已失效|职位已过期|已失效|已下线|"
        r"该职位已停止招聘|已停止招聘|该职位已不存在|已不存在|"
        r"获取职位详情失败|请浏览其他职位|抱歉，该职位)",
        text,
    ):
        result["expired"] = True
    # 方案1:把列表页里的“职位标题+详情链接”一并返回,便于 Agent 逐个打开抓 JD
    jobs = _collect_jobs(html, url)
    if jobs:
        result["jobs"] = jobs
    else:
        # 登录墙检测:特征库命中,或页面正文出现“请登录/登录后/会话过期”等 → 返回 need_login,提示走第三方
        if _is_login_wall(url) or re.search(
            r"(请先登录|请登录|登录后|会话过期|需登录|用户登录|登录注册|登录/注册|暂未登录)",
            text,
            re.I,
        ):
            result["need_login"] = True
            host = _url_host(url)
            if host:
                _JOB_SEARCH_MEMO[host] = True
        # 壳层检测:没有职位列表但存在搜索框 → 提示需 keyword 定向搜索,并记忆该站点(方案4)
        elif re.search(r'<input[^>]+(?:placeholder|name)=[^>]*(?:搜索|岗位|职位|关键词|job|keyword)', html, re.I | re.S):
            result["needs_keyword"] = True
            host = _url_host(url)
            if host:
                _JOB_SEARCH_MEMO[host] = True
    return result


def _bilibili_page_info(bvid):
    """抓取 B 站视频页,提取标题与播放量(风控失败时返回空)。"""
    try:
        resp = requests.get(
            f"https://www.bilibili.com/video/{bvid}/",
            headers=_headers(Referer="https://www.bilibili.com/"),
            timeout=15,
        )
        if resp.status_code != 200:
            return {}
        text = resp.content.decode("utf-8", "replace")
        view_match = re.search(
            r"[\x22]videoData[\x22]:\s*\{.{0,3000}?[\x22]stat[\x22]:\s*\{[^}]*?[\x22]view[\x22]:\s*(\d+)",
            text,
            re.S,
        )
        title_match = re.search(r"<title[^>]*>(.*?)</title>", text, re.S)
        title = _clean_text(re.sub(r"<[^>]+>", "", title_match.group(1))) if title_match else ""
        if title.endswith("_哔哩哔哩_bilibili"):
            title = title[: -len("_哔哩哔哩_bilibili")]
        return {
            "title": title[:200],
            "view": int(view_match.group(1)) if view_match else None,
        }
    except Exception:
        return {}


def _collect_bilibili_links(query, max_candidates=6):
    """通过搜索引擎收集 B 站视频链接,去重返回 BV 列表。"""
    bvs = []
    for q in (f"{query} bilibili 视频", f"site:bilibili.com {query}"):
        if len(bvs) >= max_candidates:
            break
        try:
            results = web_search(q, max_results=8)
        except Exception:
            continue
        for item in results:
            url = item.get("url", "")
            if "bilibili.com" not in url:
                continue
            bv_match = re.search(r"(BV[0-9A-Za-z]+)", url)
            if not bv_match:
                bv_match = re.search(r"(BV[0-9A-Za-z]+)", item.get("title", ""))
            if bv_match and bv_match.group(1) not in bvs:
                bvs.append(bv_match.group(1))
            if len(bvs) >= max_candidates:
                break
    return bvs


def _find_bili():
    """定位 bilibili-cli 的 `bili` 可执行文件:优先查 PATH,再回退到当前解释器同目录。

    当 app 由 systemd/非激活方式启动、venv 的 bin/Scripts 未加入 PATH 时,`shutil.which`
    找不到 `bili`;此时退而求其次,在当前解释器(sys.executable)所在目录找,即可覆盖绝大多数场景。
    """
    path = shutil.which("bili")
    if path:
        return path
    exe = "bili.exe" if os.name == "nt" else "bili"
    cand = os.path.join(os.path.dirname(sys.executable), exe)
    return cand if os.path.isfile(cand) else None


_CLI_ENCODINGS_CACHE = None


def _cli_output_encodings():
    """解码外部命令行工具输出时,按优先级依次尝试的编码。

    两个系统的差异:
      - Linux / macOS:命令行程序统一输出 UTF-8;
      - Windows:程序默认按控制台代码页输出,且随区域变化(中文=GBK/cp936、
        繁体=Big5、日文=cp932、西欧=cp1252),写成固定一种会在别的区域出错。
    调用方已通过 PYTHONUTF8/PYTHONIOENCODING 尽量要求子进程输出 UTF-8,所以
    UTF-8 永远排第一;其后依次是“本机代码页 → 常见东亚编码”兜底。
    """
    global _CLI_ENCODINGS_CACHE
    if _CLI_ENCODINGS_CACHE is not None:
        return _CLI_ENCODINGS_CACHE
    cands = ["utf-8"]
    if os.name == "nt":
        cands.append(locale.getpreferredencoding(False))   # 本机控制台代码页,如 cp936
    cands += ["gbk", "cp936", "big5", "cp932", "cp1252"]
    if os.name != "nt":
        cands.append(locale.getpreferredencoding(False))
    result, seen = [], set()
    for enc in cands:
        name = (enc or "").strip()
        if not name or name.lower() in seen:
            continue
        try:
            codecs.lookup(name)
        except LookupError:
            continue
        seen.add(name.lower())
        result.append(name)
    _CLI_ENCODINGS_CACHE = result
    return result


def _decode_cli_output(raw):
    """把命令行工具的输出字节解码为文本,同时适配 Windows 与 Linux。

    Windows 上 bilibili-cli 可能按控制台代码页(中文系统是 GBK)输出,而 Linux 上
    是 UTF-8。这里按 _cli_output_encodings() 给出的顺序依次尝试:先严格按 UTF-8
    解码,失败再退回本机代码页,避免视频标题整片变成乱码。
    """
    if not raw:
        return ""
    if isinstance(raw, str):
        return raw
    for enc in _cli_output_encodings():
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", "replace")


def _bilibili_search_cli(query, max_candidates=10, timeout=30):
    """用 bilibili-cli(官方 API,无需登录)搜索视频,返回 {title,url,view} 列表。

    bilibili-cli 内部走 B 站 Web 搜索 API,比抓取 search.bilibili.com 更稳定,
    能直接拿到播放量与 BV 号。命令不存在或失败时会抛错,由 bilibili_search 捕获回退。
    """
    exe = _find_bili()
    if not exe:
        raise RuntimeError("未安装 bilibili-cli,请先 pip install bilibili-cli")
    cmd = [exe, "search", query, "--type", "video", "--max", str(max_candidates), "--json"]
    # 让子进程尽量输出 UTF-8(与 free_search 的做法一致);若它仍按系统代码页输出,下面会自动兼容
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        raise RuntimeError("bili 搜索超时") from None
    if proc.returncode != 0:
        raise RuntimeError("bili 搜索失败: " + _decode_cli_output(proc.stderr)[:200])
    try:
        data = json.loads(_decode_cli_output(proc.stdout))
    except ValueError as exc:
        raise RuntimeError("bili 搜索结果解析失败") from exc
    if not data.get("ok"):
        err = data.get("error") or {}
        raise RuntimeError("bili 搜索失败: " + str(err.get("message", ""))[:200])
    items = data.get("data") or []
    videos = []
    seen = set()
    for it in items:
        bvid = (it.get("bvid") or "").strip()
        if not bvid or bvid in seen:
            continue
        seen.add(bvid)
        videos.append(
            {
                "title": (it.get("title") or "").strip()[:200],
                "url": f"https://www.bilibili.com/video/{bvid}",
                "view": int(it.get("play") or 0),
            }
        )
        if len(videos) >= max_candidates:
            break
    return videos


@register_tool
def bilibili_search(query, top_n=3):
    """在哔哩哔哩搜索学习视频,按播放量取前 top_n 个。

    优先用 bilibili-cli(官方 API)搜索;不可用时依次回退到官方搜索页解析、
    搜索引擎收集 BV 号两种旧方案,保证有结果可用。返回 {title,url,view} 列表。
    """
    videos = []
    # 1) bilibili-cli 官方 API(最稳定)
    try:
        videos = _bilibili_search_cli(query, max_candidates=top_n * 4)
    except Exception as exc:
        print(f"[tools] bilibili-cli 搜索失败,回退到旧方案: {exc}")
        videos = []
    # 2) 官方搜索页服务端解析
    if not videos:
        videos = _bilibili_search_page(query)
    # 3) 搜索引擎收集 BV 号,再逐页解析播放量
    if not videos:
        bvs = _collect_bilibili_links(query)
        for bvid in bvs:
            info = _bilibili_page_info(bvid)
            videos.append(
                {
                    "title": info.get("title") or bvid,
                    "url": f"https://www.bilibili.com/video/{bvid}",
                    "view": info.get("view"),
                }
            )
    if not videos:
        raise RuntimeError("未找到哔哩哔哩视频结果,请更换关键词")
    videos.sort(key=lambda v: (v.get("view") or 0), reverse=True)
    return videos[:top_n]


# 公司官网搜索需排除的站(招聘平台/聚合站/搜索引擎/社交/技术站)
_BAD_COMPANY_HOSTS = (
    "mokahr.com", "hotjob.cn", "zhiye.com", "liepin", "zhipin", "51job", "chinahr",
    "baidu.com", "bing.com", "google.", "sogou", "weibo", "zhihu", "douyin",
    "xiaohongshu", "csdn", "gitee", "github", "bilibili", "ssp", "redsea", "jobbole",
)


def _pick_company_url(candidates, company):
    """从搜索结果中挑一个看上去是公司官网的链接。"""
    company = (company or "").strip()
    for it in candidates:
        href = (it.get("href") or "").strip()
        text = (it.get("text") or "").strip()
        low = (href or "").lower()
        if not href or "http" not in low or any(b in low for b in _BAD_COMPANY_HOSTS):
            continue
        if "官网" in text or "官方网站" in text or (company and company in text):
            return href
    for it in candidates:
        href = (it.get("href") or "").strip()
        low = (href or "").lower()
        if href and "http" in low and not any(b in low for b in _BAD_COMPANY_HOSTS):
            return href
    return ""


_COMPANY_WEB_SYSTEM = """你是公司官网检索专家。针对唯一目标公司，使用官网检索工具链(verified_search / fetch_page / render_page)
定位并核实该公司的官方网站。要求：
- 优先用 verified_search 搜索"公司名 官网"，从候选里挑出该公司自身域名(排除招聘平台、聚合站、社交站、搜索引擎站)。
- 若中文公司名搜索返回无关/字典结果，请改用该公司的**英文名、英文缩写或官网域名**再搜(例如 中冶南方 → WISDRI / wisdri.com)。
- 若不确定官网，可再用 fetch_page 或 render_page 打开候选链接核实是否为该公司官网。
- 若公司主域名/官网主页**访问超时或无法打开，一律视为无效**;请改用该公司的**招聘官网/人才招聘入口**(通常为 job.公司域名，或公司官网的招聘频道)，并确认其可访问。
- 最终输出的官网必须**真实可访问(HTTP 200)**;若未验证过，请先用 fetch_page 验证;凡不可访问的网址一律不要输出。
- 严格控制搜索轮次:最多调用 verified_search 3 次、fetch_page / render_page 各 1 次;**每次尽量只并行 1 个搜索**,避免反复空转。
- 最终只输出一行该公司的官方网址(以 http:// 或 https:// 开头)，不要输出任何其他文字、Markdown 或工具调用标签。
- 若达到次数上限仍无法确认官网，输出一行"未找到"。"""


def _url_reachable(url, timeout=8):
    """探测 URL 是否真的可访问(HTTP < 400)。"""
    try:
        resp = requests.get(url, headers=_headers(), timeout=timeout, allow_redirects=True)
        return resp.status_code < 400
    except Exception:
        return False


def _extract_company_url(text, timeout=8):
    """从大模型输出中提取所有候选 http(s) 链接,逐个做可达性验证,
    返回第一个真实可访问的官网(不可达/超时的跳过)。"""
    if not text:
        return ""
    urls = re.findall(r"https?://[^\s<>\"'）)]+", text)
    for raw in urls:
        url = raw.rstrip(".,;)]}，。；）】")
        low = url.lower()
        if not url or any(b in low for b in _BAD_COMPANY_HOSTS):
            continue
        if _url_reachable(url, timeout=timeout):
            return url
    return ""


@register_tool
def search_company_website(company, timeout=120):
    """用户点击"点击搜索"后,由大模型调用完整官网搜索工具链(verified_search / fetch_page / render_page)
    对唯一目标公司搜索官网。超时上限 timeout 秒(默认 120);超时/未找到返回 ok=False。"""
    query = (company or "").strip()
    if not query:
        return {"ok": False, "url": "", "error": "缺少公司名"}
    from .llm import run_agent
    tool_specs = [t for t in tools_spec() if t.get("function", {}).get("name") in ("verified_search", "fetch_page", "render_page")]
    user = f"请定位公司“{query}”的官方网站，输出其官方网址（一行，http/https 开头）。"

    def job():
        return run_agent(
            _COMPANY_WEB_SYSTEM,
            user,
            tools=tool_specs,
            max_steps=3,
            max_tokens=4096,
        )

    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
    ex = ThreadPoolExecutor(max_workers=1)
    fut = ex.submit(job)
    try:
        text = fut.result(timeout=int(timeout))
    except FutTimeout:
        ex.shutdown(wait=False)
        return {"ok": False, "url": "", "error": "搜索超时"}
    except Exception as exc:
        ex.shutdown(wait=False)
        return {"ok": False, "url": "", "error": f"{type(exc).__name__}: {exc}"}
    ex.shutdown(wait=False)
    url = _extract_company_url(text)
    if not url:
        return {"ok": False, "url": "", "error": "未找到目标公司官网"}
    return {"ok": True, "url": url}


def _parse_bili_count(text):
    """把 B站展示用的播放量文本(如 '1375.8万'、'1.2亿'、'890924')解析成整数。"""
    text = re.sub(r"<[^>]+>", "", text or "").strip()
    if not text:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)(万|亿)?", text)
    if not m:
        return None
    num = float(m.group(1))
    unit = m.group(2) or ""
    if unit == "万":
        num *= 1_0000
    elif unit == "亿":
        num *= 100_000_000
    return int(num)


def _parse_bilibili_search_html(raw_html, max_candidates=10):
    """从 B 站搜索页 HTML(服务端渲染)中解析标题/BV号/播放量。"""
    videos = []
    seen = set()
    for title_match in re.finditer(r'info--tit" title="([^"]+)"', raw_html):
        start = title_match.start()
        seg = raw_html[max(0, start - 3500) : start + 150]
        bvs = re.findall(r"(BV[0-9A-Za-z]+)", seg)
        if not bvs:
            continue
        bvid = bvs[-1]
        if bvid in seen:
            continue
        seen.add(bvid)
        # 取第一项统计(播放量,可能带"万/亿")
        stats = re.findall(r'bili-video-card__stats--item[^>]*>(.*?)</div>', seg, re.S)
        view = _parse_bili_count(stats[0]) if stats else None
        videos.append(
            {
                "title": html_mod.unescape(title_match.group(1)),
                "url": f"https://www.bilibili.com/video/{bvid}",
                "view": view,
            }
        )
        if len(videos) >= max_candidates:
            break
    return videos


def _render_bilibili_search_pinia(search_url, wait_ms=12000, timeout=50):
    """用 Playwright 无头浏览器(拟人化,借鉴图书搜索)渲染 B 站搜索页,
    返回 window.__pinia 的 JSON 字符串(内含搜索结果数组)。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("未安装 Playwright,请先 pip install playwright") from exc

    channel = os.environ.get("AGENT_BROWSER_CHANNEL", _DEFAULT_BROWSER_CHANNEL).strip() or _DEFAULT_BROWSER_CHANNEL
    pinia = ""
    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel=channel,
            headless=True,
            args=[
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-infobars",
                "--disable-background-networking",
                "--lang=zh-CN",
                "--window-size=1920,1080",
            ],
        )
        context = browser.new_context(
            user_agent=UA,
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            ignore_https_errors=True,
        )
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        page = context.new_page()
        try:
            page.goto(search_url, wait_until="domcontentloaded", timeout=int(timeout * 1000))
            try:
                page.wait_for_load_state("networkidle", timeout=int(wait_ms))
            except Exception:
                pass
            page.wait_for_timeout(1500)
            pinia = page.evaluate(
                "() => { try { return JSON.stringify(window.__pinia); } catch(e){ return null; } }"
            ) or ""
        except Exception:
            pinia = ""
        finally:
            try:
                context.close()
            except Exception:
                pass
            try:
                browser.close()
            except Exception:
                pass
    return pinia


def _parse_bilibili_search_pinia(raw_pinia, max_candidates=10):
    """从渲染后的 window.__pinia(JSON)里,递归找出含 bvid+play 的结果数组并解析。"""
    try:
        data = json.loads(raw_pinia)
    except (ValueError, TypeError):
        return []
    items = []

    def walk(node):
        if isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            if node and isinstance(node[0], dict) and "bvid" in node[0] and "play" in node[0]:
                items.extend(node)
            else:
                for v in node:
                    walk(v)

    walk(data)
    videos = []
    seen = set()
    for it in items:
        bvid = (it.get("bvid") or "").strip()
        if not bvid or bvid in seen:
            continue
        seen.add(bvid)
        title = re.sub(r"<[^>]+>", "", it.get("title") or "")
        title = _clean_text(html_mod.unescape(title))[:200]
        videos.append(
            {
                "title": title,
                "url": f"https://www.bilibili.com/video/{bvid}",
                "view": int(it.get("play") or 0),
            }
        )
        if len(videos) >= max_candidates:
            break
    return videos


def _bilibili_search_page(query, max_candidates=10):
    """解析 B 站官方搜索页拿到标题/播放量/BV 号。

    先用 requests 直接请求(保留原方案,速度快);若被 JS 渲染或风控挡住拿不到结果,
    再退回到 Playwright 无头浏览器渲染(拟人化,借鉴图书搜索应对反爬),并从
    window.__pinia 提取权威结果数组。"""
    search_url = "https://search.bilibili.com/all"
    # 1) requests 直连(服务端渲染的旧方案)
    try:
        resp = requests.get(
            search_url,
            params={"keyword": query},
            headers=_headers(Referer="https://www.bilibili.com/"),
            timeout=20,
        )
        if resp.status_code == 200:
            raw = resp.content.decode("utf-8", "replace")
            videos = _parse_bilibili_search_html(raw, max_candidates)
            if videos:
                return videos
    except Exception:
        pass
    # 2) Playwright 渲染(JS 渲染 + 拟人化,应对风控)
    try:
        pinia = _render_bilibili_search_pinia(
            search_url + "?keyword=" + quote(query),
        )
        videos = _parse_bilibili_search_pinia(pinia, max_candidates)
        if videos:
            return videos
    except Exception as exc:
        print(f"[tools] B站搜索页 Playwright 渲染失败: {exc}")
    return []


# 暂时下架:原“parse_pdf”(PDF 识别)工具,配合“利用本机 MinerU 扫描 PDF”功能下架
# @register_tool
# def parse_pdf(filename, max_chars=12000):
#     """解析“我的书籍”中某本 PDF 的内容,用于大模型快速识别/总结书籍正文。
#     优先本地提取纯文本(不联网),扫描件/复杂排版走 MinerU 在线识别。
#     返回 {filename, text};text 为提取到的正文(可截断)。"""
#     from .pdf_extract import extract_pdf
#
#     try:
#         text = extract_pdf(filename)
#     except FileNotFoundError as exc:
#         return {"error": str(exc)}
#     except Exception as exc:
#         return {"error": f"{type(exc).__name__}: {exc}"}
#     return {"filename": filename, "text": text[:max_chars]}


def parse_pdf(filename, max_chars=12000):
    """(暂时下架)PDF 识别工具已下架,不再对模型开放。"""
    return {"error": "该功能已暂时下架"}


def tools_spec():
    """返回 OpenAI 风格的函数工具定义,供 run_agent 使用。"""
    return [
        {
            "type": "function",
            "function": {
                "name": "verified_search",
                "description": "带真实性审查的联网搜索:先用默认联网搜索插件并抽样审查(网站真实性/有效性);若审查不通过则改用 free-search-mcp 多引擎搜索并再次审查;仍失败再尝试 DeepSeek 联网搜索。返回 results 及 stage/verified/verify/trace 元信息。当查找公司官网、招聘岗位、证书学习资源等对链接真实性要求较高时优先用本工具;若返回 verified=false 或某项仍存疑,请把该子项作为关键词单独再次调用 verified_search,不要采用未核实链接。",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string", "description": "搜索关键词,尽量具体"}},
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "fetch_page",
                "description": "读取一个网页的正文文本,用于查看官网招聘页、新闻文章等。仅适用于服务端渲染的静态网页。",
                "parameters": {
                    "type": "object",
                    "properties": {"url": {"type": "string", "description": "网页完整链接"}},
                    "required": ["url"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "render_page",
                "description": "用 Playwright 无头浏览器渲染网页并抓取正文,专门用于 JavaScript 动态加载的页面(如公司官网招聘子页、mokahr/hotjob 等网申平台)。当 fetch_page 拿不到内容或页面为前端动态渲染时使用。返回的 jobs 是“职位标题+详情链接”对(可逐个再抓 JD),若职位已失效会带 expired=true。若该地址已失效(域名不存在或页面无正文)会带 unreachable=true,此时请换用其他候选入口,不要据此判断公司没有岗位、也不要当成“需登录”。命中招聘平台时附 platform;页面有校园招聘入口时附 campus_url(在校生优先渲染它)。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "网页完整链接"},
                        "wait_ms": {"type": "integer", "description": "等待页面渲染的毫秒数,默认 12000,动态内容多可适当增大"},
                        "max_chars": {"type": "integer", "description": "返回正文的最大字符数,默认 9000,JD 较长时可适当增大"},
                        "keyword": {"type": "string", "description": "可选。若招聘页只有搜索框、需输入岗位关键词才能出岗位,传此参数(如\"机械设计工程师\"),工具会自动搜索并等待结果渲染"},
                    },
                    "required": ["url"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "bilibili_search",
                "description": "在哔哩哔哩搜索学习视频,按播放量返回前3个视频链接与标题。优先用 bilibili-cli 官方 API;不可用时回退搜索页解析(含 Playwright 渲染应对动态/风控页面)。",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string", "description": "搜索关键词,如 SolidWorks 基础教程"}},
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "find_recruitment_links",
                "description": "发掘公司真实的招聘官网/网申入口链接。先搜索\"公司名 + 校园招聘 网申 官网\",再从结果正文与官网主页导航中筛出真实招聘平台地址(如 mokahr、hotjob、careers 等)。不要在官网主页下乱猜 /zhaopin/、/talent/ 等子路径。返回顺序即优先级(priority=1 最可信),已剔除打不开的死链;拿到结果后应先渲染 priority=1 的入口。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "company": {"type": "string", "description": "公司全称,如:东风汽车集团有限公司"},
                        "homepage": {"type": "string", "description": "可选的官网主页地址,用于提取导航中的招聘链接"},
                    },
                    "required": ["company"],
                },
            },
        },
        # 暂时下架:原“parse_pdf”(PDF 识别)工具定义,配合“利用本机 MinerU 扫描 PDF”功能下架
        # {
        #     "type": "function",
        #     "function": {
        #         "name": "parse_pdf",
        #         "description": "识别/解析“我的书籍”中某本 PDF 的正文。当用户让你总结、问答或快速识别某本已下载/上传到“我的书籍”的书籍时使用。返回该书的正文文本。若该书是扫描件或本地提取不到文本,会自动走 MinerU 在线识别。",
        #         "parameters": {
        #             "type": "object",
        #             "properties": {
        #                 "filename": {"type": "string", "description": "书名或文件名,如:高等数学 或 高等数学.pdf"},
        #                 "max_chars": {"type": "integer", "description": "返回正文的最大字符数,默认 12000"},
        #             },
        #             "required": ["filename"],
        #         },
        #     },
        # },
    ]


if __name__ == "__main__":
    # 简单自测
    import sys

    test = sys.argv[1] if len(sys.argv) > 1 else "search"
    if test == "search":
        print(json.dumps(web_search("三一重工 校园招聘 机械工程师"), ensure_ascii=False, indent=2)[:2000])
    elif test == "bili":
        print(json.dumps(bilibili_search("SolidWorks 基础教程"), ensure_ascii=False, indent=2)[:2000])
    else:
        print(json.dumps(fetch_page(sys.argv[2]), ensure_ascii=False, indent=2)[:2000])
