"""Anspire AI Search 增强搜索客户端。

作为默认联网搜索(web_search)之外的“增强搜索”选项:
- 默认搜索仍由 Bing/DDG 的 web_search 承担;
- 用户对结果不满意时,点击前端“对搜索结果不满意?使用增强搜索”,
  再通过 POST /api/search/anspire 调用本模块进行二次检索。
"""

import os

import requests

from .config import load_dotenv

load_dotenv()

API_URL = os.environ.get(
    "ANSPIRE_API_URL",
    "https://plugin.anspire.cn/api/ntsearch/search",
).strip()
API_KEY = os.environ.get("ANSPIRE_API_KEY", "").strip()
TIMEOUT = int(os.environ.get("ANSPIRE_TIMEOUT", "30"))

VALID_TOP_K = {10, 20, 30, 40, 50}


class AnspireError(RuntimeError):
    pass


def _clamp_top_k(top_k):
    """把无效的条数规整到 API 允许的值(10/20/30/40/50)。"""
    try:
        n = int(top_k)
    except (TypeError, ValueError):
        return 10
    if n in VALID_TOP_K:
        return n
    return min(VALID_TOP_K, key=lambda x: abs(x - n))


def anspire_search(query, top_k=10):
    """调用 Anspire AI Search,返回标准化结果列表。

    每个元素包含:title / url / content / score / date。
    """
    query = (query or "").strip()
    if not query:
        raise AnspireError("缺少搜索关键词")
    if not API_KEY:
        raise AnspireError("未配置 ANSPIRE_API_KEY,请在项目根目录 .env 中填写")

    params = {"query": query, "top_k": str(_clamp_top_k(top_k))}
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    try:
        resp = requests.get(API_URL, params=params, headers=headers, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise AnspireError(f"无法连接 Anspire API: {exc}") from exc

    if resp.status_code != 200:
        raise AnspireError(f"Anspire API 返回错误 {resp.status_code}: {resp.text[:300]}")

    try:
        data = resp.json()
    except ValueError as exc:
        raise AnspireError("Anspire API 返回的不是合法 JSON") from exc

    raw_results = data.get("results") or []
    results = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        results.append(
            {
                "title": (item.get("title") or "").strip(),
                "url": (item.get("url") or "").strip(),
                "content": (item.get("content") or "").strip()[:300],
                "score": item.get("score"),
                "date": (item.get("date") or "").strip(),
            }
        )
    if not results:
        raise AnspireError("Anspire 搜索未解析到结果,请更换关键词重试")
    return results
