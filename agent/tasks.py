"""轻量级后台任务管理器:用于 PDF 识别 / 图书搜索 / 下载等耗时操作的状态与进度。"""

import threading
import time
import uuid

TASKS = {}
_LOCK = threading.Lock()
MAX_LOGS = 250


def create_task(kind, label=""):
    tid = uuid.uuid4().hex[:12]
    with _LOCK:
        TASKS[tid] = {
            "id": tid,
            "kind": kind,
            "label": label,
            "status": "running",  # running | done | error
            "progress": 0.0,
            "logs": [],
            "error": "",
            "result": None,
            "created": time.time(),
        }
    return tid


def get_task(tid):
    with _LOCK:
        t = TASKS.get(tid)
        return dict(t) if t else None


def get_running_task(kind, label):
    """返回同一类型、同一标识且仍在运行的任务(用于去重)。"""
    with _LOCK:
        for t in TASKS.values():
            if t["kind"] == kind and t["label"] == label and t["status"] == "running":
                return dict(t)
    return None


def update_task(tid, **kw):
    with _LOCK:
        if tid in TASKS:
            TASKS[tid].update(kw)


def append_log(tid, line):
    if not line:
        return
    with _LOCK:
        t = TASKS.get(tid)
        if t:
            if len(t["logs"]) >= MAX_LOGS:
                t["logs"] = t["logs"][-(MAX_LOGS - 1):]
            t["logs"].append(line)


def finish_task(tid, result=None, error=None):
    with _LOCK:
        t = TASKS.get(tid)
        if not t:
            return
        t["result"] = result
        t["error"] = error or ""
        t["status"] = "error" if error else "done"
        if not error:
            t["progress"] = 100.0


def spawn_worker(job):
    """在后台守护线程运行 job(),异常由 job 内部处理。"""
    threading.Thread(target=job, daemon=True).start()
