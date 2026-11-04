import importlib.util
from contextlib import closing
import pathlib
import secrets
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch


class ConversationTitleTests(unittest.TestCase):
    def setUp(self):
        self.directory = pathlib.Path(tempfile.mkdtemp(prefix="agent-title-test-")).resolve()
        self.assertEqual(self.directory.parent, pathlib.Path(tempfile.gettempdir()).resolve())
        target = self.directory / "agent" / "store.py"
        target.parent.mkdir()
        shutil.copy2(pathlib.Path(__file__).resolve().parents[1] / "agent" / "store.py", target)
        spec = importlib.util.spec_from_file_location("title_test_store", target)
        self.store = importlib.util.module_from_spec(spec)
        with patch.dict("os.environ", {"ADMIN_PASSWORD": secrets.token_urlsafe(20)}):
            spec.loader.exec_module(self.store)

    def tearDown(self):
        self.assertTrue(self.directory.name.startswith("agent-title-test-"))
        self.assertEqual(self.directory.parent, pathlib.Path(tempfile.gettempdir()).resolve())
        shutil.rmtree(self.directory)

    def conversation(self, session_id):
        return next(row for row in self.store.list_conversations() if row["id"] == session_id)

    def legacy(self, session_id, state=None, client="client-a"):
        self.store.add_message(session_id, "user", "开始")
        self.store.set_session(session_id, state or {})
        self.store.set_conversation_client(session_id, client)
        with closing(sqlite3.connect(self.store.DB_PATH)) as conn, conn:
            conn.execute("UPDATE conversations SET title='开始' WHERE session_id=?", (session_id,))

    def test_title_follows_planning_progress(self):
        self.store.add_message("plan", "user", "开始")
        self.assertEqual(self.conversation("plan")["title"], "新学习规划")
        for state, expected in [
            ({"school": "武汉工程大学"}, "武汉工程大学 · 学习规划"),
            ({"major": "机械设计"}, "机械设计 · 职业规划"),
            ({"company": "西门子"}, "西门子 · 求职规划"),
            ({"company": "西门子", "job": "机械设计工程师"}, "西门子 · 机械设计工程师"),
        ]:
            self.store.set_session("plan", state)
            self.store.add_message("plan", "assistant", "下一步")
            self.assertEqual(self.conversation("plan")["title"], expected)

    def test_manual_title_survives_later_messages(self):
        self.store.add_message("manual", "user", "开始")
        self.store.set_conversation_client("manual", "client-a")
        self.store.rename_conversation("manual", "我的秋招准备", "client-a")
        self.store.set_session("manual", {"company": "西门子", "job": "工程师"})
        self.store.add_message("manual", "assistant", "新的回复")
        row = self.conversation("manual")
        self.assertEqual(row["title"], "我的秋招准备")
        self.assertTrue(row["title_locked"])

    def test_general_question_skips_generic_messages(self):
        for text in ("开始", "确认", "好的", "请解释 PID 控制"):
            self.store.add_message("question", "user", text)
        self.assertEqual(self.conversation("question")["title"], "请解释 PID 控制")

    def test_example_profile_in_answer_does_not_rename_general_question(self):
        self.store.add_message("question", "user", "请解释 PID 控制")
        self.store.add_message("question", "assistant", "例如 **专业**:自动化\n可以学习 PID 控制。")
        self.assertEqual(self.conversation("question")["title"], "请解释 PID 控制")

    def test_preview_is_read_only_and_backfill_preserves_order(self):
        self.legacy("old", {"school": "武汉工程大学"})
        before = self.conversation("old")
        changes = self.store.preview_title_backfill("client-a")
        self.assertEqual(self.conversation("old"), before)
        self.assertEqual(changes[0]["title"], "武汉工程大学 · 学习规划")
        self.assertEqual(self.store.apply_title_backfill(changes, "client-a"), {"updated": 1, "skipped": 0})
        after = self.conversation("old")
        self.assertEqual(after["updated_at"], before["updated_at"])
        self.assertEqual(after["count"], before["count"])
        self.assertEqual(self.store.apply_title_backfill(changes, "client-a"), {"updated": 0, "skipped": 1})

    def test_stale_preview_cannot_overwrite_manual_title(self):
        self.legacy("old", {"major": "自动化"})
        changes = self.store.preview_title_backfill("client-a")
        self.store.rename_conversation("old", "手动标题", "client-a")
        self.assertEqual(self.store.apply_title_backfill(changes, "client-a")["updated"], 0)
        self.assertEqual(self.conversation("old")["title"], "手动标题")

    def test_client_scope_rejects_other_clients(self):
        self.legacy("other", {"major": "自动化"}, client="client-b")
        changes = self.store.preview_title_backfill("client-b")
        self.assertEqual(self.store.preview_title_backfill("client-a"), [])
        self.assertIsNone(self.store.rename_conversation("other", "越权标题", "client-a"))
        self.assertEqual(self.store.apply_title_backfill(changes, "client-a")["updated"], 0)

    def test_legacy_summary_and_date_fallback(self):
        self.legacy("summary")
        self.store.add_message("summary", "assistant", "**学校**:武汉工程大学 **学历**:本科\n**专业**:自动化")
        with closing(sqlite3.connect(self.store.DB_PATH)) as conn, conn:
            conn.execute("UPDATE conversations SET title='开始' WHERE session_id='summary'")
        self.legacy("empty")
        changes = {row["id"]: row["title"] for row in self.store.preview_title_backfill("client-a")}
        self.assertEqual(changes["summary"], "自动化 · 职业规划")
        self.assertTrue(changes["empty"].startswith("学习规划 · "))

    def test_old_schema_keeps_existing_meaningful_titles(self):
        path = self.directory / "legacy.db"
        with closing(sqlite3.connect(path)) as conn, conn:
            conn.execute("CREATE TABLE conversations(session_id TEXT PRIMARY KEY,title TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)")
            conn.executemany("INSERT INTO conversations VALUES(?,?,?,?)", [
                ("custom", "已有有效名称", "2026-01-01", "2026-01-01"),
                ("default", "开始", "2026-01-01", "2026-01-01"),
            ])
        self.store.DB_PATH = str(path)
        rows = {row["id"]: row for row in self.store.list_conversations()}
        self.assertTrue(rows["custom"]["title_locked"])
        self.assertFalse(rows["default"]["title_locked"])

    def test_invalid_manual_title_is_rejected(self):
        self.legacy("old")
        for title in ("   ", "字" * 61, "\x00\n"):
            with self.assertRaises(ValueError):
                self.store.rename_conversation("old", title, "client-a")


if __name__ == "__main__":
    unittest.main()
