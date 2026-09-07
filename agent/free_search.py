"""free-search-mcp 桥接模块。

free-search-mcp(https://github.com/sweetcornna/free-search-mcp)是一个本地优先、
免 API Key 的多引擎搜索 MCP。为了不污染机电助手现有依赖(它会升级 pydantic/lxml 等
共享包),我们把 free-search-mcp 及其依赖安装到一个隔离虚拟环境 ``.venv-search``,
通过子进程调用其 ``aggregate_search``,返回统一的 {title,url,snippet} 列表。

这样做的好处:当默认联网搜索插件(web_search)对某些公司/岗位/证书查询返回失效或
伪造链接时,可以用 free-search-mcp 的多引擎 RRF 合并结果作为第二个独立搜索源,
再配合审查逻辑给出更可靠的候选链接。
"""

import json
import os
import subprocess

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_IS_WIN = os.name == "nt"
# venv 的解释器/入口随系统不同:Windows 用 Scripts\python.exe,Linux/macOS 用 bin/python
_VENV_PY = os.path.join(
    _BASE_DIR, ".venv-search", "Scripts" if _IS_WIN else "bin",
    "python.exe" if _IS_WIN else "python",
)
_VENV_PIP_CMD = ".venv-search\\Scripts\\pip" if _IS_WIN else ".venv-search/bin/pip"
_DEFAULT_ENGINES = os.environ.get("FREE_SEARCH_ENGINES", "baidu,bing,duckduckgo").strip()

# 传给 .venv-search 的解释器执行的胶水脚本:调用 aggregate_search 并把结果打印为 JSON。
# 注意:该脚本运行在隔离 venv 中,只依赖 free-search-mcp,不依赖机电助手本身。
# 用 UTF-8 字节写 stdout,避免 Windows 默认 GBK 编码导致乱码。
_RUNNER = r'''
import asyncio, json, sys

async def _main():
    from search_mcp.aggregator import aggregate_search
    query = sys.argv[1]
    max_results = int(sys.argv[2])
    engines = [e for e in (sys.argv[3] or "").split(",") if e] if len(sys.argv) > 3 else None
    payload = await aggregate_search(
        query,
        engines=engines,
        max_results=max_results,
        use_cache=True,
    )
    out = []
    for r in (payload.get("results") or []):
        d = r.to_dict() if hasattr(r, "to_dict") else dict(r)
        out.append({
            "title": (d.get("title") or "").strip()[:120],
            "url": (d.get("url") or "").strip(),
            "snippet": (d.get("snippet") or "").strip()[:300],
        })
    payload_out = {
        "results": out,
        "engines": payload.get("engines"),
        "cached": payload.get("cached"),
        "lead_snippet": payload.get("lead_snippet"),
        "errors": payload.get("errors"),
        "rescued_via": payload.get("rescued_via"),
    }
    sys.stdout.buffer.write(json.dumps(payload_out, ensure_ascii=False).encode("utf-8"))

asyncio.run(_main())
'''


def _venv_available():
    return os.path.isfile(_VENV_PY)


def free_search(query, max_results=8, engines=None, timeout=50):
    """用 free-search-mcp 搜索,返回统一的 {title,url,snippet} 列表。

    engines 可传入逗号分隔的引擎名(如 "baidu,bing,duckduckgo");None 时使用
    FREE_SEARCH_ENGINES(默认 baidu,bing,duckduckgo,兼顾国内可访问性)。
    失败时抛出 RuntimeError,由 verified_search 捕获并进入下一级回退。
    """
    query = (query or "").strip()
    if not query:
        raise RuntimeError("free-search-mcp: 缺少查询关键词")
    if not _venv_available():
        raise RuntimeError(
            "free-search-mcp 未安装(缺少 .venv-search)。"
            "请运行:python -m venv .venv-search && " + _VENV_PIP_CMD + " install free-search-mcp"
        )
    engine_str = ",".join(e.strip() for e in (engines or _DEFAULT_ENGINES).split(",") if e.strip())
    cmd = [_VENV_PY, "-c", _RUNNER, query, str(int(max_results)), engine_str]
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout, cwd=_BASE_DIR, env=env)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"free-search-mcp 搜索超时({timeout}s)") from None
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace")[:400]
        raise RuntimeError(f"free-search-mcp 执行失败: {err}")
    try:
        data = json.loads(proc.stdout.decode("utf-8", "replace"))
    except ValueError as exc:
        raise RuntimeError("free-search-mcp 返回结果解析失败") from exc
    results = data.get("results") or []
    if not results:
        raise RuntimeError("free-search-mcp 无结果")
    # 截断为请求数量
    return results[: max_results] if max_results else results


if __name__ == "__main__":
    import sys

    q = sys.argv[1] if len(sys.argv) > 1 else "三一重工 校园招聘 机械工程师"
    print(json.dumps(free_search(q), ensure_ascii=False, indent=2)[:2000])
