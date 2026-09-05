"""为竞赛知识库补齐官网链接:逐个搜索候选 → 用 render_page(真浏览器)试访问 → 保存可用链接。

运行:python -m agent.competition_links [--limit N] [--force]
结果写入 data/competitions_links.json,格式:{"links": {竞赛名: 官网url}, "unresolved": [...], "errors": {...}}
"""

import argparse
import json
import os
import re
import sys
import time

from .competitions import all_competitions
from .tools import _is_not_official_site, render_page, web_search
from . import llm

_OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "competitions_links.json")
_NON_OFFICIAL_SUB = ("www", "m", "jwc", "cxcy", "news", "info", "jiaowu", "jw", "yjsy", "youth", "scc", "scce", "iec", "sczx", "cs", "jsgl", "cxcyzx", "cxglpt", "chuangxin", "today", "jxb")
_AGG_HOSTS = ("baike", "zhihu", "sohu", "163.com", "sina", "jianshu", "cnblogs", "docin", "renrendoc", "moocollege", "course", "toutiao", "okaoyan", "maimai", "xuexi", "peixun", "gaodun", "nowcoder", "youkaoyan")
_GENERIC_HOSTS = (
    "www.gov.cn", "data.stats.gov.cn", "stats.gov.cn", "2345.com", "www.2345.com",
    "baidu.com", "sogou.com", "m.2345.com",
    "people.com.cn", "www.people.com.cn", "ncss.cn", "cy.ncss.cn", "xinhuanet.com",
    "cnr.cn", "gmw.cn", "china.com.cn", "youth.cn", "eol.cn", "ce.cn", "cnfol.com",
    "12371.cn", "chinanews.com", "cctv.com", "workercn.cn", "news.cn",
    "dili360.com", "gfbzb.gov.cn", "huanqiu.com", "thepaper.cn", "cctv.com",
)


def _host(url):
    try:
        from urllib.parse import urlparse

        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _generic_portal(url):
    """是否为“高权威但与本赛事无关”的通用门户(国家门户/数据门户/导航站/IP直连)。"""
    lu = (url or "").lower()
    import re as _re
    if _re.match(r"https?://\d{1,3}(\.\d{1,3}){3}", url):
        return True
    return any(h in lu for h in _GENERIC_HOSTS)


def _portal_score(url):
    """给“官方门户”打分:专属子域 + 根/浅路径加分;深内容/通知页、聚合平台强降权。"""
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        path = parsed.path or "/"
    except Exception:
        return 0
    seg = [s for s in path.split("/") if s]
    score = 0
    if not seg:
        score += 4  # 根路径,最像主站
    elif len(seg) <= 1:
        score += 2
    sub = host.split(".")[0] if host else ""
    if sub and sub not in _NON_OFFICIAL_SUB:
        score += 2  # 专属子域(如 iche.、nuedc.)更像是赛事主站
    if any(x in host for x in ("ac.cn", "org.cn", ".org", ".edu.cn")):
        score += 1
    if re.search(r"/(info|site|term|content|article|news|show|detail|read|page|list|n|a)/", "/" + "/".join(seg) + "/", re.I) \
       or path.lower().endswith((".html", ".htm", ".pdf")):
        score -= 3  # 深内容/通知页/附件
    if any(x in host for x in _AGG_HOSTS):
        score -= 4
    return score


def _tokens(name):
    """从竞赛名里提取用于相关度判断的关键词(去掉常见前缀/后缀)。"""
    tokens = []
    for w in re.split(r"[^\w\u4e00-\u9fff]+", name or ""):
        w = w.strip()
        if len(w) >= 2:
            tokens.append(w)
    return tokens


def _rank(name, title, url):
    """给候选打分:标题/URL 含竞赛名关键词加分,官方后缀加分,聚合/内容站降权。"""
    low = (title + " " + url).lower()
    score = 0
    for t in _tokens(name):
        if t.lower() in low:
            score += 2
    host = _host(url)
    if any(h in host for h in ("edu.cn", "ac.cn", "org.cn", ".org", ".gov", "icpc", "jingsai", "competition", "contest")):
        score += 1
    # 常见聚合/内容站降权
    if any(h in host for h in ("baike", "zhihu", "sohu", "163.com", "sina", "jianshu", "cnblogs", "docin", "renrendoc")):
        score -= 3
    return score


def _usable(text, title):
    return bool((title or "").strip()) and len(text or "") >= 100 or len(text or "") >= 300


def _llm_pick_official(name, category, candidates):
    """让大模型从候选 URL 里挑出该竞赛的“官方门户/主站”,返回 url 或 ''。

    大模型比纯启发式更能区分“官网主站”和“承办高校的通知/资讯页”。
    """
    if not candidates:
        return ""
    cand_text = "\n".join(
        f"- [{i}] {u}  ({t[:60]})" for i, (u, t) in enumerate(candidates[:12])
    )
    system = (
        "你是“竞赛官网识别助手”。下面是一个大学生竞赛,以及若干候选网址。"
        "请挑出该竞赛的【官方门户/官方网站】(即主办方/组委会运营的独立主站,通常域名简洁且位于首页/根路径,"
        "而不是某高校官网下的通知/资讯详情页,也不是第三方平台/报名代理页)。"
        "【不要选】国家部委/政府门户首页(如 www.gov.cn、data.stats.gov.cn)、导航站(如 2345)、"
        "用 IP 直接访问的页面、以及虽然权威但与本赛事无关的数据类/新闻门户。"
        "若某候选就是官方主站,输出它的完整 url;若候选里没有官方主站,输出空字符串。"
        '只输出一个 JSON:{"url":"..."}。'
    )
    user = f"竞赛名称:{name}\n类型:{category}\n候选网址:\n{cand_text}"
    try:
        data = llm.chat_json(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0,
            max_tokens=120,
        )
        url = (data.get("url") or "").strip()
        return url if url.startswith(("http://", "https://")) else ""
    except Exception:
        return ""


def _best_url(name, category=""):
    """搜索竞赛官网候选,让大模型挑官方门户,再用 render_page 验证可用性,返回 (url, note)。"""
    queries = [f"{name} 官网", f"{name} 官方网站"] if len(name) <= 26 else [f"{name} 官网"]
    cands = []
    for q in queries:
        try:
            results = web_search(q, max_results=8)
        except Exception as exc:
            return "", f"search:{type(exc).__name__}"
        for it in results or []:
            url = (it.get("url") or "").strip()
            if not url.startswith(("http://", "https://")):
                continue
            if _is_not_official_site(url.lower()):
                continue
            if _generic_portal(url):
                continue
            if url in {u for _, u in cands}:
                continue
            cands.append((it.get("title", ""), url))
    # 大模型挑官方门户
    picked = _llm_pick_official(name, category, [(u, t) for t, u in cands])
    # 以“官方门户分数”为主(专属子域+根路径优先),大模型点名作为小幅加成
    order = []
    for _t, u in sorted(cands, key=lambda cu: -(_portal_score(cu[1]) + (3 if cu[1] == picked else 0))):
        order.append(u)
    # 若大模型点名的网址不在候选里(模型凭知识补充),放最前尝试
    if picked and picked not in order and picked.startswith(("http://", "https://")):
        order.insert(0, picked)
    for url in order[:5]:
        if _generic_portal(url):
            continue
        try:
            res = render_page(url, max_chars=4000, wait_ms=7000)
            if _usable(res.get("text") or "", res.get("title") or ""):
                return url, ""
        except Exception:
            continue
    # 兜底:按启发式排名,返回最高分(未验证)
    cands.sort(key=lambda x: -_rank(name, x[0], x[1]))
    if cands:
        return cands[0][1], "unverified"
    return "", "no_result"


def build(limit=None, force=False):
    os.makedirs(os.path.dirname(_OUT), exist_ok=True)
    links = {}
    unresolved = []
    errors = {}
    if os.path.exists(_OUT) and not force:
        try:
            with open(_OUT, encoding="utf-8") as f:
                prev = json.load(f)
            links = dict(prev.get("links") or {})
            errors = dict(prev.get("errors") or {})
        except Exception:
            pass

    comps = all_competitions()
    if limit:
        comps = comps[:limit]
    print(f"共 {len(all_competitions())} 个赛事,本次处理 {len(comps)} 个")
    for i, comp in enumerate(comps, 1):
        name = comp["name"]
        if name in links and links[name] and not force:
            print(f"[{i}/{len(comps)}] 已有链接,跳过: {name}")
            continue
        print(f"[{i}/{len(comps)}] 检索并访问: {name}")
        t = time.time()
        url, note = _best_url(name, comp.get("category", ""))
        if url:
            links[name] = url
            print(f"     -> {url} ({note or 'verified'}) {time.time()-t:.1f}s")
        else:
            errors[name] = note
            print(f"     -> 未找到({note}) {time.time()-t:.1f}s")
        # 每次写盘,便于中断后恢复
        with open(_OUT, "w", encoding="utf-8") as f:
            json.dump({"links": links, "unresolved": unresolved, "errors": errors}, f, ensure_ascii=False, indent=1)
    with open(_OUT, "w", encoding="utf-8") as f:
        json.dump({"links": links, "unresolved": unresolved, "errors": errors}, f, ensure_ascii=False, indent=1)
    print(f"\n完成: 成功 {len(links)} 个;未找到 {len(errors)} 个")
    return links, errors


def refix_generic():
    """只重跑“当前链接是通用门户(gov/stats/导航/IP)”的赛事,修复误选。"""
    if not os.path.exists(_OUT):
        return
    with open(_OUT, encoding="utf-8") as f:
        d = json.load(f)
    links = dict(d.get("links") or {})
    errors = dict(d.get("errors") or {})
    comps = {c["name"]: c for c in all_competitions()}
    bad = [k for k, v in links.items() if _generic_portal(v)]
    print(f"需修复的通用门户链接: {len(bad)} 个")
    for k in bad:
        comp = comps.get(k, {})
        url, note = _best_url(k, comp.get("category", ""))
        if url and not _generic_portal(url):
            links[k] = url
            print(f"  修复: {k[:20]} -> {url} [{note}]")
        else:
            print(f"  仍未找到合适链接: {k[:20]} ({url or note})")
    with open(_OUT, "w", encoding="utf-8") as f:
        json.dump({"links": links, "unresolved": d.get("unresolved", []), "errors": errors}, f, ensure_ascii=False, indent=1)
    print(f"完成,现有链接 {len(links)} 个")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--refix", action="store_true")
    args = ap.parse_args()
    if args.refix:
        refix_generic()
    else:
        build(limit=args.limit, force=args.force)
