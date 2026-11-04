"""PDF 文本抽取。

⚠️ 暂时下架:利用本机 MinerU 扫描 PDF 书籍 / “我的书籍”识别功能已暂时下架。
原实现(优先本机 PyMuPDF 直取纯文本,扫描件/复杂排版自动交给本机完整版 MinerU CLI)
已在下方整体注释保留;需要恢复时取消注释即可。
"""


def extract_pdf(query, progress_cb=None, log_cb=None):
    """(暂时下架)按“我的书籍”里的书名/文件名解析 PDF,返回提取到的文本。"""
    raise RuntimeError("PDF 识别功能已暂时下架")


# ============================================================ 暂时下架
# 以下为原“利用本机 MinerU 扫描 PDF 书籍”功能的完整实现,已全部注释保留。
# ============================================================ 暂时下架
# import os
# import re
# import shutil
# import subprocess
# import sys
# import tempfile
# import time
# from pathlib import Path
#
# BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# BOOKS_DIR = os.path.join(BASE_DIR, "data", "books")
# MINERU_TIMEOUT = int(os.environ.get("MINERU_TIMEOUT", "1200"))
#
#
# def _list_books():
#     """返回“我的书籍”目录下所有文件名。"""
#     if not os.path.isdir(BOOKS_DIR):
#         return []
#     return [f for f in os.listdir(BOOKS_DIR) if os.path.isfile(os.path.join(BOOKS_DIR, f))]
#
#
# def _resolve_book(query):
#     """按书名(或文件名)模糊匹配“我的书籍”里的一本书,返回绝对路径。"""
#     q = (query or "").strip()
#     if not q:
#         return None
#     q = q.lower()
#     for suffix in (".pdf", ".PDF"):
#         if q.endswith(suffix):
#             q = q[: -len(suffix)]
#     books = _list_books()
#     for f in books:
#         if os.path.basename(f).lower().replace(".pdf", "") == q:
#             return os.path.join(BOOKS_DIR, f)
#     for f in books:
#         if q in os.path.basename(f).lower().replace(".pdf", ""):
#             return os.path.join(BOOKS_DIR, f)
#     return None
#
#
# def _analyze_pdf(path):
#     """用 PyMuPDF 分析 PDF:返回 (抽取到的文本, 统计信息)。
#
#     统计信息包含:pages、blank(空白页)、images(图片张数)、noise(噪声字符数,
#     即数学字体常见的私有区字符与控制字符)。用于判断是否应改走 MinerU。
#     若文本过短/密度过低(扫描件或隐藏垃圾文本)则 text 返回 None。
#     """
#     try:
#         import fitz  # PyMuPDF
#     except Exception:
#         return None, {}
#     try:
#         doc = fitz.open(path)
#         pages = doc.page_count
#         parts = []
#         noise = 0
#         images = 0
#         blank = 0
#         for page in doc:
#             t = page.get_text()
#             parts.append(t)
#             if not t.strip():
#                 blank += 1
#             images += len(page.get_images())
#             for c in t:
#                 o = ord(c)
#                 if o < 32 and c not in "\n\r\t":
#                     noise += 1
#                 elif 0xE000 <= o <= 0xF8FF:
#                     noise += 1
#         doc.close()
#     except Exception:
#         return None, {}
#     text = "\n".join(parts).strip()
#     if not text:
#         return None, {"pages": pages, "blank": blank, "images": images, "noise": noise}
#     # 隐藏垃圾文本(如 vldano_x)或每页字符过少(扫描件) -> 视为无有效正文
#     if len(text) < 40 or len(text) / max(1, pages) < 20:
#         return None, {"pages": pages, "blank": blank, "images": images, "noise": noise}
#     return text, {"pages": pages, "blank": blank, "images": images, "noise": noise}
#
#
# def _looks_untrustworthy(text):
#     """判断抽取到的文字层是否“不可信”(字符映射损坏/碎片化)。
#
#     典型症状:中文书却抽不出汉字、全是 ASCII 标点/符号、且几乎每字一行。
#     这类书的文字层是坏的,必须强制 OCR 重建,不能沿用文字层。
#     """
#     total = len(text or "")
#     if total <= 0:
#         return True
#     lines = [l for l in (text or "").splitlines() if l.strip()]
#     avg_line = total / max(1, len(lines))
#     han = sum(1 for c in text or "" if "\u4e00" <= c <= "\u9fff")
#     cjk_ratio = han / total
#     punct = sum(
#         1 for c in text or ""
#         if c in "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"
#     )
#     punct_ratio = punct / total
#     # 同时满足“碎片化 + 汉字占比过低 + 标点占比异常高”才判定为损坏
#     return avg_line < 6 and cjk_ratio < 0.30 and punct_ratio > 0.20
#
#
# def _decide_mode(data, text):
#     """决定抽取方式:返回 'text' | 'mineru_auto' | 'mineru_ocr'。"""
#     if not text:
#         return "mineru_ocr"  # 无可用文字层(扫描/隐藏垃圾) -> 强制 OCR
#     if _looks_untrustworthy(text):
#         return "mineru_ocr"  # 文字层损坏(坏映射/碎片化) -> 强制 OCR
#     pages = max(1, data.get("pages", 1))
#     total = len(text)
#     noise_ratio = data.get("noise", 0) / total
#     images_per_page = data.get("images", 0) / pages
#     if noise_ratio > 0.015 or images_per_page > 0.3:
#         return "mineru_auto"  # 公式/表格/图密集但文字层可信 -> MinerU 重建
#     return "text"
#
#
# def _kill_tree(pid):
#     """在 Windows 上强制结束某进程及其子进程树。
#
#     `mineru` CLI 正常出结果后,其托管 mineru-api 子进程偶发不退出,
#     导致命令行挂起;这里用 taskkill /T 结束整棵进程树,避免卡住。
#     """
#     if not pid:
#         return
#     try:
#         subprocess.run(
#             ["taskkill", "/F", "/T", "/PID", str(pid)],
#             capture_output=True,
#             timeout=15,
#             check=False,
#         )
#     except Exception:
#         pass
#
#
# def _read_output_md(out):
#     """返回输出目录里体积最大的 .md 文件(没有则返回 None)。"""
#     md_files = sorted(Path(out).rglob("*.md"), key=lambda p: p.stat().st_size, reverse=True)
#     return md_files[0] if md_files else None
#
#
# def _extract_local_mineru(path, method="auto", progress_cb=None, log_cb=None):
#     """调用本机完整版 MinerU CLI 识别 PDF,返回 Markdown 文本。
#
#     使用 `pipeline` 后端 + 指定方法(method: 'auto' 或 'ocr')。
#     - auto: 自动判断(有文字层走 txt,无文字层/扫描走 ocr)。
#     - ocr: 强制 OCR,用于“文字层不可信”的书(忽略坏掉的文字层)。
#     以异步方式启动:由于 `mineru` CLI 收尾时托管 mineru-api 偶发不退出,
#     这里不等待命令行退出,而是轮询到输出 .md 出现后读取,再结束进程树。
#     """
#     exe = shutil.which("mineru") or shutil.which("mineru.exe")
#     if not exe:
#         raise RuntimeError(
#             "未找到本机 MinerU 命令行工具。请确认已安装完整版 MinerU "
#             "并确保 mineru 在 PATH 中。"
#         )
#     with tempfile.TemporaryDirectory(prefix="mineru_out_") as out:
#         log_file = tempfile.NamedTemporaryFile(
#             prefix="mineru_log_", suffix=".txt", delete=False
#         )
#         log_path = log_file.name
#         log_file.close()
#         proc = None
#         last_pos = 0
#         last_log = ""
#         last_progress = -1
#         try:
#             with open(os.devnull, "wb") as devnull, open(log_path, "wb") as logfp:
#                 proc = subprocess.Popen(
#                     [
#                         exe,
#                         "-p", path,
#                         "-o", out,
#                         "-b", "pipeline",
#                         "-m", method,
#                         "-l", "ch",
#                     ],
#                     stdout=devnull,
#                     stderr=logfp,
#                 )
#                 deadline = time.time() + MINERU_TIMEOUT
#                 md = None
#                 while time.time() < deadline:
#                     md = _read_output_md(out)
#                     if md:
#                         break
#                     if proc.poll() is not None:
#                         break
#                     try:
#                         if log_cb or progress_cb:
#                             with open(log_path, encoding="utf-8", errors="replace") as lf:
#                                 content = lf.read()
#                             # 进度:取最新的 “Processing pages: X%”
#                             pm = re.search(r"Processing pages:\s*(\d+)%", content)
#                             if pm:
#                                 pct = int(pm.group(1))
#                                 if pct != last_progress:
#                                     last_progress = pct
#                                     if progress_cb:
#                                         progress_cb(pct)
#                             # 日志:发送关键步骤行
#                             for line in re.split(r"[\r\n]+", content[last_pos:]):
#                                 line = line.strip()
#                                 if not line:
#                                     continue
#                                 if any(k in line for k in (
#                                     "Submitting batch", "Completed batch",
#                                     "Processing pages", "Layout Predict",
#                                     "OCR-det", "OCR-rec", "Table", "DocAnalysis init",
#                                     "Started local mineru-api", "error", "Error",
#                                     "failed", "batch",
#                                 )):
#                                     if line != last_log and log_cb:
#                                         last_log = line
#                                         log_cb(line)
#                             last_pos = len(content)
#                     except Exception:
#                         pass
#                     time.sleep(1.0)
#             if md is None:
#                 tail = ""
#                 try:
#                     tail = open(log_path, encoding="utf-8", errors="replace").read()[-300:].strip()
#                 except Exception:
#                     pass
#                 raise RuntimeError("本地 MinerU 未输出 Markdown 文件: " + tail[:200])
#             # 出结果后不要等 CLI 收尾挂起,直接结束进程树
#             if proc.poll() is None:
#                 _kill_tree(proc.pid)
#             text = md.read_text(encoding="utf-8", errors="replace").strip()
#             if not text:
#                 raise RuntimeError("本地 MinerU 未能提取到文本")
#             return text
#         finally:
#             if proc and proc.poll() is None:
#                 _kill_tree(proc.pid)
#             try:
#                 os.remove(log_path)
#             except Exception:
#                 pass
#
#
# def extract_pdf(query, progress_cb=None, log_cb=None):
#     """按“我的书籍”里的书名/文件名解析 PDF,返回提取到的文本。"""
#     path = _resolve_book(query)
#     if not path:
#         raise FileNotFoundError(f"没有找到书籍:{query}")
#     text, data = _analyze_pdf(path)
#     mode = _decide_mode(data, text)
#     if mode == "text":
#         if progress_cb:
#             progress_cb(100)
#         if log_cb:
#             log_cb("纯文字书,直接读取文本层完成")
#         return text
#     method = "ocr" if mode == "mineru_ocr" else "auto"
#     return _extract_local_mineru(path, method=method, progress_cb=progress_cb, log_cb=log_cb)
