"""我的书籍(Markdown):保存每次“识别”生成的 Markdown 文件。"""

import os
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOOKS_MD_DIR = os.path.join(BASE_DIR, "data", "books_md")


def _ensure_dir():
    os.makedirs(BOOKS_MD_DIR, exist_ok=True)


def _safe_filename(title):
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", title or "markdown").strip(" ._")
    name = name[:120] or "markdown"
    return name


def save_markdown(title, content):
    """把识别出的 Markdown 保存为 `{书名}.md`,同名覆盖。返回 {title, filename, size}。"""
    _ensure_dir()
    title = re.sub(r"\.pdf$", "", (title or "").strip(), flags=re.I).strip()
    name = _safe_filename(title)
    filename = name + ".md"
    path = os.path.join(BOOKS_MD_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content or "")
    st = os.stat(path)
    return {"title": name, "filename": filename, "size": st.st_size}


def list_markdowns():
    _ensure_dir()
    items = []
    for name in os.listdir(BOOKS_MD_DIR):
        path = os.path.join(BOOKS_MD_DIR, name)
        if os.path.isfile(path) and name.lower().endswith(".md"):
            st = os.stat(path)
            items.append(
                {"filename": name, "size": st.st_size, "mtime": int(st.st_mtime * 1000)}
            )
    items.sort(key=lambda b: b["mtime"], reverse=True)
    return items


def markdown_file_path(filename):
    """安全解析 Markdown 文件名,阻止目录穿越。"""
    name = os.path.basename(filename or "")
    path = os.path.join(BOOKS_MD_DIR, name)
    if not os.path.isfile(path):
        return None
    return path


def delete_markdown(filename):
    path = markdown_file_path(filename)
    if path:
        os.remove(path)
        return True
    return False
