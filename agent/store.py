"""SQLite 持久化:用户档案、长期记忆、会话状态。"""

import json
import os
import re
import sqlite3
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "agent.db")


def _conn():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    _init(conn)
    return conn


def _init(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS profile(
            session_id TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            PRIMARY KEY(session_id, key)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS memories(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions(
            session_id TEXT PRIMARY KEY,
            state TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS conversations(
            session_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    # 为“按客户端隔离历史”补充 client_id 列(旧库用 ALTER 补齐,不存在则创建)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(conversations)").fetchall()}
    if "client_id" not in cols:
        conn.execute("ALTER TABLE conversations ADD COLUMN client_id TEXT NOT NULL DEFAULT ''")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS messages(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            mode TEXT NOT NULL DEFAULT 'plan',
            think TEXT,
            think_time REAL,
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
        """
    )
    # 旧库补 mode 列(不存在则创建)
    mcols = {r["name"] for r in conn.execute("PRAGMA table_info(messages)").fetchall()}
    if "mode" not in mcols:
        conn.execute("ALTER TABLE messages ADD COLUMN mode TEXT NOT NULL DEFAULT 'plan'")
    if "think" not in mcols:
        conn.execute("ALTER TABLE messages ADD COLUMN think TEXT")
    if "think_time" not in mcols:
        conn.execute("ALTER TABLE messages ADD COLUMN think_time REAL")
    conn.commit()


# ---------- 用户档案 ----------

def get_profile(session_id="default"):
    conn = _conn()
    rows = conn.execute(
        "SELECT key, value FROM profile WHERE session_id=?", (session_id,)
    ).fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}


def set_profile(session_id, updates):
    """仅覆盖非空字段,避免误清空已有档案。"""
    conn = _conn()
    for key, value in (updates or {}).items():
        if value:
            conn.execute(
                "INSERT INTO profile(session_id, key, value) VALUES(?, ?, ?) "
                "ON CONFLICT(session_id, key) DO UPDATE SET value=excluded.value",
                (session_id, key, str(value)),
            )
    conn.commit()
    conn.close()


# ---------- 长期记忆 ----------

def add_memory(session_id, role, content):
    if not content:
        return
    conn = _conn()
    conn.execute(
        "INSERT INTO memories(session_id, role, content) VALUES(?, ?, ?)",
        (session_id, role, content),
    )
    conn.commit()
    conn.close()


def _keywords(text):
    """提取关键词:英文/数字词 + 中文双字组合,用于轻量语义检索。"""
    words = [w.lower() for w in re.findall(r"[A-Za-z0-9]{2,}", text or "")]
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", text or ""):
        words.extend(run[i : i + 2] for i in range(len(run) - 1))
    return list(set(words))


def search_memory(session_id, query, limit=20):
    """按关键词相关度返回历史记忆,不足时用最近记忆补齐。"""
    conn = _conn()
    rows = conn.execute(
        "SELECT id, role, content, created_at FROM memories "
        "WHERE session_id=? ORDER BY id DESC LIMIT 200",
        (session_id,),
    ).fetchall()
    conn.close()

    keys = _keywords(query)
    scored = []
    for r in rows:
        score = sum(r["content"].lower().count(k) for k in keys)
        scored.append((score, r))
    scored.sort(key=lambda x: (-x[0], -x[1]["id"]))

    picked = [r for s, r in scored if s > 0]
    seen = {r["id"] for r in picked}
    for _, r in scored:
        if len(picked) >= limit:
            break
        if r["id"] not in seen:
            picked.append(r)
            seen.add(r["id"])
    return [
        {"role": r["role"], "content": r["content"][:500], "date": r["created_at"]}
        for r in picked[:limit]
    ]


# ---------- 会话状态 ----------

def get_session(session_id):
    conn = _conn()
    row = conn.execute(
        "SELECT state FROM sessions WHERE session_id=?", (session_id,)
    ).fetchone()
    conn.close()
    if not row:
        return {}
    try:
        return json.loads(row["state"])
    except json.JSONDecodeError:
        return {}


def set_session(session_id, state):
    conn = _conn()
    conn.execute(
        "INSERT INTO sessions(session_id, state) VALUES(?, ?) "
        "ON CONFLICT(session_id) DO UPDATE SET state=excluded.state",
        (session_id, json.dumps(state, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()


def reset_session(session_id):
    conn = _conn()
    conn.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))
    conn.commit()
    conn.close()


def delete_conversation(session_id):
    """删除一个历史对话及其关联消息、记忆、档案与会话状态。"""
    conn = _conn()
    conn.execute("DELETE FROM conversations WHERE session_id=?", (session_id,))
    conn.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
    conn.execute("DELETE FROM memories WHERE session_id=?", (session_id,))
    conn.execute("DELETE FROM profile WHERE session_id=?", (session_id,))
    conn.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))
    conn.commit()
    conn.close()


# ---------- 历史对话 ----------

def add_message(session_id, role, content, mode="plan", think="", think_time=None):
    """记录一条对话消息(带模式标记与思考过程/用时),并维护会话标题与更新时间。"""
    if not content:
        return
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = _conn()
    row = conn.execute(
        "SELECT session_id FROM conversations WHERE session_id=?", (session_id,)
    ).fetchone()
    if row is None:
        title = content.strip().replace("\n", " ")[:20]
        conn.execute(
            "INSERT INTO conversations(session_id, title, created_at, updated_at) "
            "VALUES(?, ?, ?, ?)",
            (session_id, title or "新对话", now, now),
        )
    else:
        conn.execute(
            "UPDATE conversations SET updated_at=? WHERE session_id=?",
            (now, session_id),
        )
    conn.execute(
        "INSERT INTO messages(session_id, role, content, mode, think, think_time, created_at) VALUES(?, ?, ?, ?, ?, ?, ?)",
        (session_id, role, content, mode, think, think_time, now),
    )
    conn.commit()
    conn.close()


def set_conversation_client(session_id, client_id):
    """把未归属(空)的会话认领给某个客户端。已归属的不会被抢占。"""
    if not client_id or not session_id:
        return
    conn = _conn()
    conn.execute(
        "UPDATE conversations SET client_id=? WHERE session_id=? AND (client_id='' OR client_id IS NULL)",
        (client_id, session_id),
    )
    conn.commit()
    conn.close()


def get_conversation_client(session_id):
    """返回某个会话归属的 client_id,无归属时返回 '。"""
    conn = _conn()
    row = conn.execute(
        "SELECT client_id FROM conversations WHERE session_id=?", (session_id,)
    ).fetchone()
    conn.close()
    return (row["client_id"] if row else "") or ""


def list_conversations(q=None, client_id=None):
    """列出历史会话。传入 client_id 时只返回“该客户端的会话 + 尚未归属的旧会话”,
    未传则保持全量(兼容旧调用)。"""
    conn = _conn()
    params = []
    where = []
    if client_id:
        where.append("(c.client_id = ? OR c.client_id = '')")
        params.append(client_id)
    if q:
        where.append("c.title LIKE ?")
        params.append(f"%{q}%")
    sql = (
        "SELECT c.session_id, c.title, c.created_at, c.updated_at, "
        "(SELECT COUNT(*) FROM messages m WHERE m.session_id=c.session_id) AS count "
        "FROM conversations c"
    )
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY c.updated_at DESC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [
        {
            "id": r["session_id"],
            "title": r["title"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
            "count": r["count"],
        }
        for r in rows
    ]


def get_messages(session_id):
    conn = _conn()
    rows = conn.execute(
        "SELECT role, content, mode, think, think_time FROM messages WHERE session_id=? ORDER BY id ASC",
        (session_id,),
    ).fetchall()
    conn.close()
    return [
        {
            "role": r["role"],
            "content": r["content"],
            "mode": r["mode"] or "plan",
            "think": r["think"] or "",
            "think_time": r["think_time"],
        }
        for r in rows
    ]
