"""机电学习助手 Web 服务入口。"""

import json
import os
import queue
import re
import threading
import time
import traceback

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

from agent.config import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

# 暂时下架:原导入 books_md / pdf_extract 用于“利用本机 MinerU 扫描 PDF”的书籍识别功能
from agent import anspire, books, graph_store, store, tasks, tools, workflow  # noqa: E402  加载 .env 后再导入

app = FastAPI(title="机电学习助手")
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


@app.middleware("http")
async def no_cache_static(request, call_next):
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


# ---------- 在线人数(进程内内存版:单进程部署即可,无需加库/服务) ----------
_presence_lock = threading.Lock()
_presence = {}  # client_id -> {"nick": str, "last_seen": float}
PRESENCE_WINDOW = 35.0  # 秒:超过该时间无心跳视为离线


def _presence_count():
    """返回窗口内的去重在线人数,并顺带清理过期记录。"""
    now = time.time()
    with _presence_lock:
        stale = [k for k, v in _presence.items() if now - (v.get("last_seen") or 0) > PRESENCE_WINDOW]
        for k in stale:
            _presence.pop(k, None)
        return len(_presence)


class ChatIn(BaseModel):
    message: str
    session_id: str = "default"
    client_id: str = ""
    mode: str = "plan"


class RetryIn(BaseModel):
    """一键重试请求体：仅需会话信息，无需新的用户消息(message)。"""
    session_id: str = "default"
    client_id: str = ""
    mode: str = "plan"


class ResetIn(BaseModel):
    session_id: str = "default"


class GraphImportIn(BaseModel):
    session_id: str = "default"
    graph: dict
    name: str = ""


class GraphSaveIn(BaseModel):
    name: str = ""
    nodes: list = []
    edges: list = []
    importHistory: list = []


class GraphRenameIn(BaseModel):
    name: str


class BookSearchIn(BaseModel):
    query: str


class BookDownloadIn(BaseModel):
    url: str
    download_url: str = ""
    title: str = ""


class AnspireSearchIn(BaseModel):
    query: str
    top_k: int = 10


class CourseVideoIn(BaseModel):
    query: str = ""


class CompanyWebsiteIn(BaseModel):
    company: str = ""


class PresencePingIn(BaseModel):
    """在线心跳请求体：携带客户端标识与昵称。"""
    client_id: str = ""
    nickname: str = ""


class LoginIn(BaseModel):
    """登录/首次注册请求体。"""
    client_id: str = ""
    nickname: str = ""
    password: str = ""


class LogoutIn(BaseModel):
    token: str = ""


# 暂时下架:原“PDF 识别”请求体,配合已下架的 /api/pdf/parse 使用
# class PdfParseIn(BaseModel):
#     filename: str
#     max_chars: int = 12000


@app.get("/")
def index():
    return FileResponse(os.path.join(BASE_DIR, "static", "index.html"))


@app.api_route("/favicon.ico", methods=["GET", "HEAD"], include_in_schema=False)
def favicon_ico():
    # 浏览器默认会请求 /favicon.ico;重定向到已有的 SVG 图标,避免 404
    return RedirectResponse("/static/favicon.svg", status_code=307)


@app.post("/api/chat")
def chat(body: ChatIn):
    try:
        reply, profile = workflow.handle_message(body.session_id, body.message, mode=body.mode)
        store.set_conversation_client(body.session_id, body.client_id)
        return {"reply": reply, "profile": profile}
    except Exception as exc:
        print("=" * 60)
        traceback.print_exc()
        print("=" * 60)
        return JSONResponse(status_code=500, content={"error": f"{type(exc).__name__}: {exc}"})


@app.post("/api/chat/stream")
def chat_stream(body: ChatIn):
    """以 Server-Sent Events 返回思考过程和正文流。"""
    def gen():
        events = queue.Queue()

        def emit(event, data):
            events.put((event, data))

        def worker():
            try:
                workflow.run(body.session_id, body.message, emit=emit, stream=True, mode=body.mode)
                store.set_conversation_client(body.session_id, body.client_id)
                events.put(("done", {"profile": store.get_profile()}))
            except Exception as exc:
                print("=" * 60)
                traceback.print_exc()
                print("=" * 60)
                events.put(("error", {"error": f"{type(exc).__name__}: {exc}"}))

        threading.Thread(target=worker, daemon=True).start()
        while True:
            event, data = events.get()
            yield f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
            if event in ("done", "error"):
                break

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/chat/retry")
def chat_retry(body: RetryIn):
    """一键重试:重新生成上一条助手回复(公司推荐/岗位检索等自动环节)。"""
    def gen():
        events = queue.Queue()

        def emit(event, data):
            events.put((event, data))

        def worker():
            try:
                workflow.retry_last(body.session_id, emit=emit, stream=True, mode=body.mode)
                store.set_conversation_client(body.session_id, body.client_id)
                events.put(("done", {"profile": store.get_profile()}))
            except Exception as exc:
                print("=" * 60)
                traceback.print_exc()
                print("=" * 60)
                events.put(("error", {"error": f"{type(exc).__name__}: {exc}"}))

        threading.Thread(target=worker, daemon=True).start()
        while True:
            event, data = events.get()
            yield f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
            if event in ("done", "error"):
                break

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/profile")
def profile(session_id: str = "default"):
    return store.get_profile(session_id)


# ---------- 知识图谱(移植自 zstp 后端 API) ----------

@app.get("/api/graphs")
def graphs_list():
    return graph_store.list_graphs()


@app.get("/api/graphs/{graph_id}")
def graphs_get(graph_id: str):
    graph = graph_store.get_graph(graph_id)
    if not graph:
        return JSONResponse(status_code=404, content={"error": "图谱不存在"})
    return graph


@app.put("/api/graphs/{graph_id}")
def graphs_put(graph_id: str, body: GraphSaveIn):
    graph_store.save_graph(
        graph_id,
        name=body.name or None,
        nodes=body.nodes,
        edges=body.edges,
        import_history=body.importHistory,
    )
    return {"ok": True}


@app.patch("/api/graphs/{graph_id}")
def graphs_patch(graph_id: str, body: GraphRenameIn):
    name = (body.name or "").strip()
    if not name:
        return JSONResponse(status_code=400, content={"error": "name 不能为空"})
    graph_store.rename_graph(graph_id, name)
    return {"ok": True}


@app.delete("/api/graphs/{graph_id}")
def graphs_delete(graph_id: str):
    graph_store.delete_graph(graph_id)
    return {"ok": True}


@app.delete("/api/graphs/{graph_id}/imports/{import_id}")
def graphs_remove_import(graph_id: str, import_id: str):
    ok = graph_store.remove_import(graph_id, import_id)
    if not ok:
        return JSONResponse(status_code=404, content={"error": "导入记录不存在"})
    return {"ok": True}


@app.post("/api/graph/import")
def graph_import(body: GraphImportIn):
    """一键导入:把大模型生成的学习计划知识图谱 JSON 建成本地新图谱。"""
    try:
        name = (body.name or "").strip()
        if not name:
            major = (store.get_profile(body.session_id) or {}).get("user_major")
            name = f"{major}·四年学习计划" if major else ""
        graph_id = graph_store.create_graph_from_json(body.graph, name=name or None)
        return {"ok": True, "graph_id": graph_id}
    except Exception as exc:
        print("=" * 60)
        traceback.print_exc()
        print("=" * 60)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": f"{type(exc).__name__}: {exc}"},
        )


# ---------- 图书:搜索 / 下载 / 我的书籍 ----------

@app.post("/api/books/search")
def books_search(body: BookSearchIn):
    query = (body.query or "").strip()
    if not query:
        return JSONResponse(status_code=400, content={"ok": False, "error": "请输入书籍名称"})
    running = tasks.get_running_task("search", query)
    if running:
        return {"ok": True, "task_id": running["id"], "already_running": True}
    tid = tasks.create_task("search", query)

    def worker():
        def lc(line):
            tasks.append_log(tid, line)

        try:
            results = books.search_books(query, log_cb=lc)
            tasks.finish_task(tid, result={"results": results})
        except Exception as exc:
            print("=" * 60)
            traceback.print_exc()
            print("=" * 60)
            tasks.finish_task(tid, error=f"{type(exc).__name__}: {exc}")

    tasks.spawn_worker(worker)
    return {"ok": True, "task_id": tid, "already_running": False}


@app.get("/api/books/search/status/{task_id}")
def books_search_status(task_id: str):
    t = tasks.get_task(task_id)
    if not t:
        return JSONResponse(status_code=404, content={"ok": False, "error": "任务不存在"})
    return t


@app.post("/api/books/download")
def books_download(body: BookDownloadIn):
    url = (body.url or "").strip()
    if not url:
        return JSONResponse(status_code=400, content={"ok": False, "error": "缺少书籍链接"})
    running = tasks.get_running_task("download", url)
    if running:
        return {"ok": True, "task_id": running["id"], "already_running": True}
    tid = tasks.create_task("download", url)

    def worker():
        def pc(p):
            tasks.update_task(tid, progress=p)

        try:
            info = books.download_book(
                body.url,
                download_url=body.download_url,
                title=body.title,
                progress_cb=pc,
            )
            tasks.finish_task(tid, result=info)
        except Exception as exc:
            print("=" * 60)
            traceback.print_exc()
            print("=" * 60)
            tasks.finish_task(tid, error=f"{type(exc).__name__}: {exc}")

    tasks.spawn_worker(worker)
    return {"ok": True, "task_id": tid, "already_running": False}


@app.get("/api/books/download/status/{task_id}")
def books_download_status(task_id: str):
    t = tasks.get_task(task_id)
    if not t:
        return JSONResponse(status_code=404, content={"ok": False, "error": "任务不存在"})
    return t


@app.post("/api/books/upload")
async def books_upload(request: Request, title: str = ""):
    """用户本地上传 PDF 到“我的书籍”(body 为 PDF 原始字节,name 由 query 传入)。"""
    try:
        content = await request.body()
        info = books.upload_book(title, content)
        return {"ok": True, **info}
    except Exception as exc:
        print("=" * 60)
        traceback.print_exc()
        print("=" * 60)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": f"{type(exc).__name__}: {exc}"},
        )


# ---------- 增强搜索:Anspire AI Search ----------

@app.post("/api/search/anspire")
def anspire_search_api(body: AnspireSearchIn):
    """用户点击“增强搜索”后,用 Anspire AI Search 对关键词再次检索。"""
    try:
        results = anspire.anspire_search(body.query, top_k=body.top_k)
        return {"ok": True, "results": results}
    except Exception as exc:
        print("=" * 60)
        traceback.print_exc()
        print("=" * 60)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": f"{type(exc).__name__}: {exc}"},
        )


# 课程视频查询任务:query -> task_id(同一课程复用同一任务,完成后再点可查看结果)
_COURSE_TASK = {}


@app.post("/api/course/video")
def course_video_api(body: CourseVideoIn):
    """点击某门课程的“查询”后,创建后台任务,由大模型调用 B站搜索工具检索视频;
    返回 task_id,前端轮询 /status 获取工具调用进度与最终结果。关闭弹窗不代表取消任务。"""
    query = (body.query or "").strip()
    if not query:
        return JSONResponse(status_code=400, content={"ok": False, "error": "请提供课程名称"})
    tid = _COURSE_TASK.get(query)
    if tid and tasks.get_task(tid):
        return {"ok": True, "task_id": tid, "reuse": True}
    tid = tasks.create_task("course_video", query)
    _COURSE_TASK[query] = tid

    def job():
        try:
            text = workflow.search_course_videos(
                query,
                on_process=lambda line: tasks.append_log(tid, line),
            )
            tasks.finish_task(tid, result=text)
        except Exception as exc:
            tasks.finish_task(tid, error=f"{type(exc).__name__}: {exc}")

    tasks.spawn_worker(job)
    return {"ok": True, "task_id": tid}


@app.get("/api/course/video/status/{task_id}")
def course_video_status_api(task_id: str):
    """查询某课程视频搜索任务的进度(工具调用/思考日志)与最终结果。"""
    t = tasks.get_task(task_id)
    if not t:
        return JSONResponse(status_code=404, content={"ok": False, "error": "任务不存在或已过期"})
    return {
        "ok": True,
        "status": t["status"],   # running | done | error
        "logs": t["logs"],
        "text": t["result"] or "",
        "error": t["error"],
    }


@app.post("/api/company/website")
def company_website_api(body: CompanyWebsiteIn):
    """用户点击某公司的"点击搜索"后,用 Playwright 搜索该公司的官网(单次,超时上限 100s)。"""
    company = (body.company or "").strip()
    if not company:
        return JSONResponse(status_code=400, content={"ok": False, "error": "请提供公司名称"})
    try:
        r = tools.search_company_website(company)
        return {"ok": True, "found": r.get("ok", False), "url": r.get("url", ""), "error": r.get("error", "")}
    except Exception as exc:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"ok": False, "error": f"{type(exc).__name__}: {exc}"})


@app.get("/api/books")
def books_list():
    return {"ok": True, "books": books.list_books()}


@app.get("/api/books/file/{filename}")
def books_file(filename: str):
    path = books.book_file_path(filename)
    if not path:
        return JSONResponse(status_code=404, content={"error": "文件不存在"})
    return FileResponse(
        path, media_type="application/pdf", filename=os.path.basename(path)
    )


# ---------- 暂时下架:利用本机 MinerU 扫描 PDF 书籍 / “我的书籍”识别(含“我的书籍(Markdown)”) ----------
# @app.post("/api/pdf/parse")
# def pdf_parse(body: PdfParseIn):
#     """启动后台识别任务。同一本书正在识别时复用(去重),不重复执行。"""
#     filename = (body.filename or "").strip()
#     if not filename:
#         return JSONResponse(status_code=400, content={"ok": False, "error": "缺少文件名"})
#     running = tasks.get_running_task("parse", filename)
#     if running:
#         return {"ok": True, "task_id": running["id"], "already_running": True}
#     tid = tasks.create_task("parse", filename)
#
#     def worker():
#         def pc(p):
#             tasks.update_task(tid, progress=p)
#
#         def lc(line):
#             tasks.append_log(tid, line)
#
#         try:
#             text = pdf_extract.extract_pdf(filename, progress_cb=pc, log_cb=lc)
#         except Exception as exc:
#             print("=" * 60)
#             traceback.print_exc()
#             print("=" * 60)
#             tasks.finish_task(tid, error=f"{type(exc).__name__}: {exc}")
#             return
#         try:
#             info = books_md.save_markdown(filename, text)
#         except Exception as exc:
#             print("=" * 60)
#             traceback.print_exc()
#             print("=" * 60)
#             tasks.finish_task(tid, error=f"保存 Markdown 失败: {type(exc).__name__}: {exc}")
#             return
#         tasks.finish_task(tid, result={"md_filename": info["filename"], "text": text[: body.max_chars]})
#
#     tasks.spawn_worker(worker)
#     return {"ok": True, "task_id": tid, "already_running": False}
#
#
# @app.get("/api/pdf/parse/status/{task_id}")
# def pdf_parse_status(task_id: str):
#     t = tasks.get_task(task_id)
#     if not t:
#         return JSONResponse(status_code=404, content={"ok": False, "error": "任务不存在"})
#     return t
#
#
# @app.get("/api/books/md")
# def books_md_list():
#     return {"ok": True, "markdowns": books_md.list_markdowns()}
#
#
# @app.get("/api/books/md/file/{filename}")
# def books_md_file(filename: str):
#     path = books_md.markdown_file_path(filename)
#     if not path:
#         return JSONResponse(status_code=404, content={"error": "文件不存在"})
#     return FileResponse(
#         path,
#         media_type="text/markdown; charset=utf-8",
#         filename=os.path.basename(path),
#     )
#
#
# @app.delete("/api/books/md/{filename}")
# def books_md_delete(filename: str):
#     if books_md.delete_markdown(filename):
#         return {"ok": True}
#     return JSONResponse(status_code=404, content={"error": "文件不存在"})


@app.delete("/api/books/{filename}")
def books_delete(filename: str):
    if books.delete_book(filename):
        return {"ok": True}
    return JSONResponse(status_code=404, content={"error": "文件不存在"})


@app.get("/api/sessions")
def sessions(q: str = "", client_id: str = ""):
    return store.list_conversations(q or None, client_id or None)


@app.get("/api/sessions/{session_id}/messages")
def session_messages(session_id: str, client_id: str = ""):
    owner = store.get_conversation_client(session_id)
    if client_id and owner and owner != client_id:
        return JSONResponse(status_code=404, content={"error": "会话不存在或无权访问"})
    return store.get_messages(session_id)


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str, client_id: str = ""):
    owner = store.get_conversation_client(session_id)
    if client_id and owner and owner != client_id:
        return JSONResponse(status_code=403, content={"error": "无权删除该会话"})
    store.delete_conversation(session_id)
    return {"ok": True}


@app.post("/api/reset")
def reset(body: ResetIn):
    store.reset_session(body.session_id)
    return {"ok": True}


# ---------- 在线人数 ----------

@app.post("/api/presence/ping")
def presence_ping(body: PresencePingIn):
    """前端按时上报心跳,用于统计在线人数。"""
    cid = (body.client_id or "").strip()
    if cid:
        with _presence_lock:
            _presence[cid] = {
                "nick": (body.nickname or "").strip(),
                "last_seen": time.time(),
            }
    return {"ok": True, "online": _presence_count()}


@app.get("/api/presence/online")
def presence_online():
    """返回近窗口内的在线人数。"""
    return {"ok": True, "online": _presence_count()}


# ---------- 登录 / 用户体系 ----------

def _clean_nickname(s):
    s = re.sub(r"[\u0000-\u001f\u007f]", "", (s or ""))
    s = re.sub(r"\s+", " ", s).strip()
    return s[:24]


@app.post("/api/auth/login")
def auth_login(body: LoginIn):
    """登录;昵称不存在且密码为标准密码(用户默认密码)时自动注册。"""
    nickname = _clean_nickname(body.nickname)
    password = (body.password or "")
    client_id = (body.client_id or "").strip()
    if not nickname or not password:
        return JSONResponse(status_code=400, content={"ok": False, "error": "昵称和密码不能为空"})
    default_pw = os.environ.get("USER_DEFAULT_PASSWORD", "123")
    user = store.get_user(nickname)
    if user:
        stored = store.get_user_hash(nickname)  # 获取存储哈希
        if not store.verify_password(password, stored):
            return JSONResponse(status_code=401, content={"ok": False, "error": "昵称已存在，密码错误"})
        role = user["role"]
    else:
        # 新用户仅允许使用标准密码注册(admin 由种子账号保留)
        if password != default_pw:
            return JSONResponse(status_code=400, content={"ok": False, "error": "新用户请使用默认密码注册"})
        store.create_user(nickname, password, role="user")
        role = "user"
    store.bind_user_client(nickname, client_id)
    token = store.create_auth_token(nickname)
    return {"ok": True, "nickname": nickname, "role": role, "token": token}


@app.post("/api/auth/logout")
def auth_logout(body: LogoutIn):
    store.delete_auth_token(body.token or "")
    return {"ok": True}


@app.get("/api/auth/me")
def auth_me(token: str = ""):
    """校验本地有效期内的 token,返回当前登录身份;用于刷新页面后免登录。"""
    nickname = store.get_auth_user(token or "")
    if not nickname:
        return JSONResponse(status_code=401, content={"ok": False, "error": "未登录或已过期"})
    user = store.get_user(nickname)
    return {"ok": True, "nickname": nickname, "role": (user or {}).get("role", "user")}


@app.get("/api/admin/records")
def admin_records(token: str = ""):
    """管理员专属:查看全部用户的提问与 AI 回复记录。"""
    nickname = store.get_auth_user(token or "")
    if not nickname:
        return JSONResponse(status_code=401, content={"ok": False, "error": "未登录或登录已过期"})
    user = store.get_user(nickname)
    if not user or user["role"] != "admin":
        return JSONResponse(status_code=403, content={"ok": False, "error": "无管理员权限"})
    return {"ok": True, "records": store.get_all_user_records()}


if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8000")),
        reload=False,
    )
