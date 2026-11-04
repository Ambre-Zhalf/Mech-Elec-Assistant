"""SQLite 持久化:用户档案、长期记忆、会话状态。"""

import json
import os
import re
import hashlib
import hmac
import secrets
import sqlite3
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "agent.db")
TITLE_MAX_LENGTH = 60
_DEFAULT_TITLES = {"", "开始", "开始吧", "新对话", "新学习规划", "你好", "您好", "确认", "好的", "好", "嗯", "ok"}


def _default_title(title):
    return (title or "").strip().strip("。！!？?，,.").lower() in _DEFAULT_TITLES


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
    if "title_locked" not in cols:
        conn.execute("ALTER TABLE conversations ADD COLUMN title_locked INTEGER NOT NULL DEFAULT 0")
        # 旧版已有的有效标题保持原样,只将默认标题交给自动命名和回填。
        for row in conn.execute("SELECT session_id, title FROM conversations").fetchall():
            if not _default_title(row["title"]):
                conn.execute("UPDATE conversations SET title_locked=1 WHERE session_id=?", (row["session_id"],))
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
    # 登录/用户体系(首次运行自动建表,幂等)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users(
            nickname TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_clients(
            nickname TEXT NOT NULL,
            client_id TEXT NOT NULL,
            PRIMARY KEY(nickname, client_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_tokens(
            token TEXT PRIMARY KEY,
            nickname TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            expires_at TEXT NOT NULL
        )
        """
    )
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

def _conversation_title(conn, conversation, backfill=False):
    session_id = conversation["session_id"]
    row = conn.execute("SELECT state FROM sessions WHERE session_id=?", (session_id,)).fetchone()
    try:
        state = json.loads(row["state"]) if row else {}
    except (ValueError, TypeError):
        state = {}
    if not isinstance(state, dict):
        state = {}
    profile = dict(conn.execute("SELECT key, value FROM profile WHERE session_id=?", (session_id,)).fetchall())
    fields = {}
    for field, profile_key in (("school", "user_school"), ("major", "user_major"),
                               ("company", "target_company"), ("job", "target_job")):
        value = state.get(field) or profile.get(profile_key) or ""
        fields[field] = str(value).strip() if value else ""
    # 旧会话可能仅在助手回复中保存了档案摘要。
    if not all(fields.values()) and (state.get("step") or backfill or _default_title(conversation["title"])):
        summaries = conn.execute(
            "SELECT substr(content, 1, 2500) AS content FROM messages "
            "WHERE session_id=? AND role='assistant' ORDER BY id DESC LIMIT 30", (session_id,)
        ).fetchall()
        labels = {"school": "学校", "major": "专业", "company": "意向公司|目标公司", "job": "意向岗位|目标岗位"}
        for summary in summaries:
            for field, label in labels.items():
                if fields[field]:
                    continue
                match = re.search(r"(?:\*\*)?(?:" + label + r")(?:\*\*)?\s*[:：=]\s*([^\n|｜<>]+)", summary["content"])
                if match:
                    value = re.split(r"\s+(?:\*\*)?(?:学校|学历|专业|城市|意向公司|意向岗位)(?:\*\*)?\s*[:：=]", match[1])[0].strip(" *`。")
                    if value not in ("无", "暂无", "未记录", "XXX"):
                        fields[field] = value
    school, major, company, job = (fields[key] for key in ("school", "major", "company", "job"))
    if company and job:
        title = f"{company} · {job}"
    elif company:
        title = f"{company} · 求职规划"
    elif job:
        title = f"{job} · 学习规划"
    elif major:
        title = f"{major} · 职业规划"
    elif school:
        title = f"{school} · 学习规划"
    else:
        title = ""
        replies = conn.execute(
            "SELECT substr(content, 1, 500) AS content FROM messages "
            "WHERE session_id=? AND role='user' ORDER BY id", (session_id,)
        ).fetchall()
        short_answers = {"确认无误", "是", "是的", "对", "没错", "正确", "普通本科", "职业本科", "本科", "专科", "硕士", "博士"}
        for reply in replies:
            text = re.sub(r"\s+", " ", reply["content"]).strip()
            if _default_title(text) or text in short_answers or re.fullmatch(r"[0-9一二三四五六七八九十]+年?", text):
                continue
            title = text
            break
        if not title:
            title = "学习规划 · " + conversation["created_at"][5:16] if backfill else "新学习规划"
    return re.sub(r"\s+", " ", title).strip()[:TITLE_MAX_LENGTH]


def _title_scope(client_id, include_unowned):
    if client_id is None:
        return "1=1", []
    return ("(client_id=? OR client_id='')" if include_unowned else "client_id=?"), [client_id]


def preview_title_backfill(client_id=None, include_unowned=False):
    conn = _conn()
    try:
        scope, params = _title_scope(client_id, include_unowned)
        rows = conn.execute(f"SELECT * FROM conversations WHERE title_locked=0 AND {scope} ORDER BY created_at", params).fetchall()
        return [
            {"id": row["session_id"], "old_title": row["title"], "title": _conversation_title(conn, row, backfill=True)}
            for row in rows if _default_title(row["title"])
        ]
    finally:
        conn.close()


def apply_title_backfill(changes, client_id=None, include_unowned=False):
    conn = _conn()
    updated = 0
    try:
        scope, params = _title_scope(client_id, include_unowned)
        with conn:
            for change in changes:
                row = conn.execute(f"SELECT * FROM conversations WHERE session_id=? AND title_locked=0 AND {scope}",
                                   [change["id"], *params]).fetchone()
                if (not row or not _default_title(row["title"]) or row["title"] != change["old_title"]
                        or _conversation_title(conn, row, backfill=True) != change["title"]):
                    continue
                cursor = conn.execute(
                    f"UPDATE conversations SET title=? WHERE session_id=? AND title=? AND title_locked=0 AND {scope}",
                    [change["title"], change["id"], change["old_title"], *params],
                )
                updated += cursor.rowcount
        return {"updated": updated, "skipped": len(changes) - updated}
    finally:
        conn.close()


def rename_conversation(session_id, title, client_id, include_unowned=False):
    title = re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f]", " ", title or "")).strip()
    if not title or len(title) > TITLE_MAX_LENGTH:
        raise ValueError(f"标题需为 1～{TITLE_MAX_LENGTH} 个字符")
    conn = _conn()
    try:
        scope, params = _title_scope(client_id, include_unowned)
        with conn:
            cursor = conn.execute(
                f"UPDATE conversations SET title=?, title_locked=1 WHERE session_id=? AND {scope}",
                [title, session_id, *params],
            )
        return title if cursor.rowcount else None
    finally:
        conn.close()


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
    conversation = conn.execute("SELECT * FROM conversations WHERE session_id=?", (session_id,)).fetchone()
    if not conversation["title_locked"]:
        conn.execute("UPDATE conversations SET title=? WHERE session_id=? AND title_locked=0",
                     (_conversation_title(conn, conversation), session_id))
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
        "SELECT c.session_id, c.title, c.title_locked, c.created_at, c.updated_at, "
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
            "title_locked": bool(r["title_locked"]),
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


# ---------- 登录/用户体系 ----------

def _hash_password(pwd, salt=None):
    """返回 'salt$hash'(PBKDF2-SHA256),避免明文存储。"""
    salt = salt or secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac(
        "sha256", (pwd or "").encode("utf-8"), salt.encode("utf-8"), 100_000
    ).hex()
    return f"{salt}${hashed}"


def verify_password(pwd, stored):
    """校验明文密码与存储的 'salt$hash' 是否匹配。"""
    try:
        salt, hashed = (stored or "").split("$", 1)
    except ValueError:
        return False
    return hmac.compare_digest(_hash_password(pwd, salt).split("$", 1)[1], hashed)


def get_user(nickname):
    conn = _conn()
    row = conn.execute(
        "SELECT nickname, role FROM users WHERE nickname=?", (nickname,)
    ).fetchone()
    conn.close()
    return {"nickname": row["nickname"], "role": row["role"]} if row else None


def get_user_hash(nickname):
    """返回该昵称的密码哈希(salt$hash),不存在返回 None。"""
    conn = _conn()
    row = conn.execute(
        "SELECT password_hash FROM users WHERE nickname=?", (nickname,)
    ).fetchone()
    conn.close()
    return row["password_hash"] if row else None


def create_user(nickname, password, role="user"):
    conn = _conn()
    conn.execute(
        "INSERT INTO users(nickname, password_hash, role) VALUES(?, ?, ?)",
        (nickname, _hash_password(password), role),
    )
    conn.commit()
    conn.close()


def bind_user_client(nickname, client_id):
    """把某个浏览器(client_id)绑定到该昵称,用于管理员跨设备汇总记录。"""
    if not nickname or not client_id:
        return
    conn = _conn()
    conn.execute(
        "INSERT OR IGNORE INTO user_clients(nickname, client_id) VALUES(?, ?)",
        (nickname, client_id),
    )
    conn.commit()
    conn.close()


def get_user_clients(nickname):
    conn = _conn()
    rows = conn.execute(
        "SELECT client_id FROM user_clients WHERE nickname=?", (nickname,)
    ).fetchall()
    conn.close()
    return [r["client_id"] for r in rows]


def create_auth_token(nickname):
    token = secrets.token_urlsafe(32)
    expires = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    conn = _conn()
    conn.execute(
        "INSERT INTO auth_tokens(token, nickname, expires_at) VALUES(?, ?, ?)",
        (token, nickname, expires),
    )
    conn.commit()
    conn.close()
    return token


def get_auth_user(token):
    """返回有效且未过期的 token 对应的昵称;无效返回 None。"""
    if not token:
        return None
    conn = _conn()
    row = conn.execute(
        "SELECT nickname, expires_at FROM auth_tokens WHERE token=?", (token,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return row["nickname"] if row["expires_at"] >= now else None


def delete_auth_token(token):
    if not token:
        return
    conn = _conn()
    conn.execute("DELETE FROM auth_tokens WHERE token=?", (token,))
    conn.commit()
    conn.close()


def get_all_user_records():
    """按昵称聚合每个用户在“绑定设备”下的全部问答记录,按时间升序。"""
    conn = _conn()
    users = conn.execute(
        "SELECT nickname, role FROM users ORDER BY created_at DESC"
    ).fetchall()
    result = []
    for u in users:
        clients = [
            r["client_id"]
            for r in conn.execute(
                "SELECT client_id FROM user_clients WHERE nickname=?", (u["nickname"],)
            ).fetchall()
        ]
        if not clients:
            continue
        placeholders = ",".join("?" * len(clients))
        sessions = [
            r["session_id"]
            for r in conn.execute(
                f"SELECT session_id FROM conversations WHERE client_id IN ({placeholders})",
                clients,
            ).fetchall()
        ]
        if not sessions:
            continue
        sp = ",".join("?" * len(sessions))
        msgs = conn.execute(
            f"SELECT role, content, created_at FROM messages "
            f"WHERE session_id IN ({sp}) ORDER BY id ASC",
            sessions,
        ).fetchall()
        result.append(
            {
                "nickname": u["nickname"],
                "role": u["role"],
                "messages": [
                    {"role": m["role"], "content": m["content"], "time": m["created_at"]}
                    for m in msgs
                ],
            }
        )
    conn.close()
    return result


def _ensure_admin():
    """创建/更新管理员账号(密码取 .env 的 ADMIN_PASSWORD,缺省为 lvdiantuandui)。"""
    admin_pw = os.environ.get("ADMIN_PASSWORD", "lvdiantuandui")
    conn = _conn()  # 幂等建表
    row = conn.execute(
        "SELECT password_hash FROM users WHERE nickname='admin'"
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO users(nickname, password_hash, role) VALUES('admin', ?, 'admin')",
            (_hash_password(admin_pw),),
        )
    elif os.environ.get("ADMIN_PASSWORD") and not verify_password(admin_pw, row["password_hash"]):
        # 配置了 ADMIN_PASSWORD 则以它为准,更新到最新
        conn.execute(
            "UPDATE users SET password_hash=? WHERE nickname='admin'",
            (_hash_password(admin_pw),),
        )
    conn.commit()
    conn.close()


_ensure_admin()
