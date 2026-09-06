"""竞赛知识库:读取《大学生工科竞赛榜单.xlsx》,并按用户专业/目标岗位推荐适合的竞赛。

表格结构(4 列):序号 | 竞赛名称(主) | 竞赛名称(副) | 类别。
存在“一个主竞赛含多个子赛事”的合并单元格(主名列空、副名是各子赛事),这里统一取“副名”
作为单个赛事名称,类别取各自行。类别为:计算机类 / 电子信息类 / 其他工学类 / 机器人类 / 职业技能类。
"""

import json
import os
import threading

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_XLSX = os.path.join(_BASE_DIR, "data", "gb", "大学生工科竞赛榜单.xlsx")
_LINKS_JSON = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "competitions_links.json")
_lock = threading.Lock()
_cache = None
_links_cache = None

# 方向关键词 -> 倾向的竞赛类别(大类,可多个)
_KEYWORD_CATEGORY = {
    "机械": ("其他工学类",),
    "机电": ("其他工学类", "机器人类", "机器人/机电类"),
    "车辆": ("其他工学类",),
    "汽车": ("其他工学类",),
    "制造": ("其他工学类",),
    "结构": ("其他工学类",),
    "工程": ("其他工学类",),
    "自动化": ("机器人类", "机器人/机电类"),
    "电气": ("机器人类", "机器人/机电类"),
    "控制": ("机器人类", "机器人/机电类"),
    "机器人": ("机器人类", "机器人/机电类"),
    "机甲": ("机器人/机电类", "机器人类"),
    "测控": ("电子信息类",),
    "电子": ("电子信息类",),
    "通信": ("电子信息类",),
    "集成电路": ("电子信息类",),
    "微电子": ("电子信息类",),
    "光电": ("电子信息类",),
    "计算机": ("计算机类",),
    "软件": ("计算机类",),
    "人工智能": ("计算机类",),
    "算法": ("计算机类",),
    "数据": ("计算机类",),
    "信息安全": ("计算机类",),
}

# 用于对竞赛名/类别做精确打分的“方向词”
_DIRECTION_WORDS = (
    "机械", "机电", "车辆", "汽车", "制造", "结构", "工程", "自动化", "电气", "控制",
    "机器人", "测控", "电子", "通信", "集成电路", "微电子", "光电", "计算机", "软件",
    "人工智能", "算法", "数据", "信息", "智能", "嵌入式", "芯片", "半导体", "机甲",
)

# 额外手工补充的竞赛(不在 Excel 里),类别按用户指定
_EXTRA_COMPETITIONS = [
    {"name": "RoboMaster机甲大师赛", "category": "机器人/机电类"},
]


def _load():
    global _cache
    if _cache is not None:
        return _cache
    with _lock:
        if _cache is not None:
            return _cache
        try:
            import pandas as pd

            df = pd.read_excel(_XLSX, header=0).fillna("")
        except Exception as exc:
            raise RuntimeError(f"无法读取竞赛知识库({_XLSX}): {exc}") from exc
        items = []
        seen = set()
        for _, row in df.iterrows():
            main = str(row.iloc[1]).strip() if df.shape[1] >= 2 else ""
            sub = str(row.iloc[2]).strip() if df.shape[1] >= 3 else ""
            cat = str(row.iloc[3]).strip() if df.shape[1] >= 4 else ""
            name = (sub or main).strip()
            if not name or name in seen:
                continue
            seen.add(name)
            items.append({"name": name, "category": cat or "其他工学类"})
        for extra in _EXTRA_COMPETITIONS:
            n = (extra.get("name") or "").strip()
            if n and n not in seen:
                seen.add(n)
                items.append({"name": n, "category": extra.get("category") or "其他工学类"})
        _cache = items
        return _cache


def _load_links():
    """从 data/competitions_links.json 读取已补全的官网链接 {name: url}。"""
    global _links_cache
    if _links_cache is not None:
        return _links_cache
    with _lock:
        if _links_cache is not None:
            return _links_cache
        links = {}
        try:
            with open(_LINKS_JSON, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                links = data.get("links") or data
        except Exception:
            links = {}
        _links_cache = links
        return _links_cache


def all_competitions():
    """返回全部赛事 list[{name, category}](与 Excel 一致)。"""
    return _load()


def _categories_for(major, job):
    text = (major or "") + " " + (job or "")
    cats = set()
    for kw, cat in _KEYWORD_CATEGORY.items():
        if kw in text:
            cats.update(cat)
    return cats or {"其他工学类"}


def recommend_competitions(major, job, top_n=8):
    """根据专业/岗位关键词,给竞赛打分并返回排名靠前的 list[{name, category, url?}]。

    用户方向命中某类别 +3 分;竞赛名/类别中出现用户方向词则累计加分;按总分降序取前 top_n。
    若方向无法提取,退回“其他工学类/机器人类”,再退回全量。
    """
    try:
        items = _load()
    except RuntimeError:
        return [{"name": "（竞赛知识库暂不可用，请检查 " + _XLSX + "）", "category": ""}]
    text = (major or "") + " " + (job or "")
    dirs = [k for k in _DIRECTION_WORDS if k in text]
    user_cats = _categories_for(major, job)
    scored = []
    for it in items:
        blob = (it["name"] + " " + it["category"])
        s = sum(1 for k in dirs if k in blob)
        if it["category"] in user_cats:
            s += 3
        if s > 0:
            scored.append((s, it))
    scored.sort(key=lambda x: (-x[0], x[1]["name"]))
    if not scored:
        scored = [(1, it) for it in items if it["category"] in ("其他工学类", "机器人类")]
    if not scored:
        scored = [(1, it) for it in items]
    links = _load_links()
    out = []
    for _, it in scored[:top_n]:
        item = dict(it)
        url = links.get(item["name"]) or ""
        if url:
            item["url"] = url
        out.append(item)
    return out


if __name__ == "__main__":
    import json

    print(json.dumps(recommend_competitions("机械设计制造及其自动化", "机械结构工程师", top_n=8), ensure_ascii=False, indent=1))
