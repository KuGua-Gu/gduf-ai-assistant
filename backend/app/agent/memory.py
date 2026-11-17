"""Agent 会话记忆存储。

只维护 Agent 自己的两张表（``agent_sessions`` / ``agent_messages``），不触碰业务表。
每次操作独立建立 ``sqlite3`` 连接并在事务中提交；长会话按窗口自动压缩摘要，
不额外调用大模型。
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

_ROLE_LABELS: dict[str, str] = {"user": "用户", "assistant": "助手", "system": "系统"}
_VALID_ROLES = frozenset(_ROLE_LABELS)
_SNIPPET_LIMIT = 120
_SUMMARY_LIMIT = 800


class MemoryStore:
    """基于 SQLite 的 Agent 会话记忆存储。"""

    def __init__(
        self,
        db_path: str | Path,
        window: int = 8,
        *,
        timezone: str = "Asia/Shanghai",
    ) -> None:
        """记录数据库路径与窗口大小，并创建目录、表结构与索引。"""
        self._db_path = Path(db_path).expanduser()
        self._window = max(1, int(window))
        self._timezone = timezone
        self._init_schema()

    # ---------- 内部工具 ----------

    def _now(self) -> str:
        """返回当前时间（带时区的 ISO 字符串，精确到秒）。"""
        return datetime.now(ZoneInfo(self._timezone)).isoformat(timespec="seconds")

    def _connect(self) -> sqlite3.Connection:
        """建立新连接，开启 WAL 与 busy_timeout，并设置 Row 工厂。"""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL").fetchone()
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init_schema(self) -> None:
        """创建 Agent 自己的表与索引（IF NOT EXISTS）。"""
        conn = self._connect()
        try:
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS agent_sessions (
                        id TEXT PRIMARY KEY,
                        summary TEXT DEFAULT '',
                        state_json TEXT DEFAULT '{}',
                        created_at TEXT,
                        updated_at TEXT
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS agent_messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        created_at TEXT
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_agent_messages_session_id "
                    "ON agent_messages(session_id)"
                )
        finally:
            conn.close()

    @staticmethod
    def _ensure_session(conn: sqlite3.Connection, session_id: str, now: str) -> None:
        """在当前事务内保证会话行存在。"""
        conn.execute(
            "INSERT OR IGNORE INTO agent_sessions "
            "(id, summary, state_json, created_at, updated_at) "
            "VALUES (?, '', '{}', ?, ?)",
            (session_id, now, now),
        )

    @staticmethod
    def _build_summary(rows: list[sqlite3.Row]) -> str:
        """把旧消息拼成摘要文本：单条最多 120 字，整体最多 800 字。"""
        lines: list[str] = []
        for row in rows:
            label = _ROLE_LABELS.get(row["role"], row["role"])
            text = " ".join(str(row["content"]).split())
            if len(text) > _SNIPPET_LIMIT:
                text = text[:_SNIPPET_LIMIT] + "…"
            lines.append(f"{label}: {text}")
        summary = " / ".join(lines)
        if len(summary) > _SUMMARY_LIMIT:
            summary = "…" + summary[-(_SUMMARY_LIMIT - 1):]
        return summary

    def _maybe_compress(self, conn: sqlite3.Connection, session_id: str) -> None:
        """消息总数超过 ``window * 2`` 时，把最近 window 条之外的旧消息压成摘要。"""
        total = conn.execute(
            "SELECT COUNT(*) FROM agent_messages WHERE session_id = ?",
            (session_id,),
        ).fetchone()[0]
        if total <= self._window * 2:
            return
        rows = conn.execute(
            "SELECT role, content FROM agent_messages WHERE session_id = ? "
            "ORDER BY id DESC LIMIT -1 OFFSET ?",
            (session_id, self._window),
        ).fetchall()
        summary = self._build_summary(list(reversed(rows)))
        conn.execute(
            "UPDATE agent_sessions SET summary = ?, updated_at = ? WHERE id = ?",
            (summary, self._now(), session_id),
        )

    # ---------- 对外接口 ----------

    def get_or_create(self, session_id: str | None = None) -> str:
        """返回已有会话 id；不存在时创建，未传 id 时用 ``uuid4().hex`` 生成。"""
        sid = session_id or uuid.uuid4().hex
        conn = self._connect()
        try:
            with conn:
                self._ensure_session(conn, sid, self._now())
        finally:
            conn.close()
        return sid

    def exists(self, session_id: str) -> bool:
        """判断会话是否存在。"""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT 1 FROM agent_sessions WHERE id = ?", (session_id,)
            ).fetchone()
            return row is not None
        finally:
            conn.close()

    def append(self, session_id: str, role: str, content: str) -> None:
        """追加一条消息；会话不存在时自动创建，消息过多时触发摘要压缩。"""
        if role not in _VALID_ROLES:
            raise ValueError(f"不支持的消息角色：{role}")
        conn = self._connect()
        try:
            with conn:
                now = self._now()
                self._ensure_session(conn, session_id, now)
                conn.execute(
                    "INSERT INTO agent_messages "
                    "(session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                    (session_id, role, content, now),
                )
                conn.execute(
                    "UPDATE agent_sessions SET updated_at = ? WHERE id = ?",
                    (now, session_id),
                )
                self._maybe_compress(conn, session_id)
        finally:
            conn.close()

    def history(self, session_id: str, limit: int | None = None) -> list[dict[str, str]]:
        """按时间正序返回历史消息；会话不存在时返回空列表。"""
        conn = self._connect()
        try:
            if limit is None:
                rows = conn.execute(
                    "SELECT role, content FROM agent_messages "
                    "WHERE session_id = ? ORDER BY id",
                    (session_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT role, content FROM agent_messages "
                    "WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                    (session_id, max(0, int(limit))),
                ).fetchall()
                rows = list(reversed(rows))
        finally:
            conn.close()
        return [{"role": row["role"], "content": row["content"]} for row in rows]

    def context(self, session_id: str) -> list[dict[str, str]]:
        """返回给 LLM 的上下文：可选历史摘要 + 最近 ``window`` 条原文。"""
        conn = self._connect()
        try:
            session = conn.execute(
                "SELECT summary FROM agent_sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if session is None:
                return []
            summary = (session["summary"] or "").strip()
            rows = conn.execute(
                "SELECT role, content FROM agent_messages "
                "WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, self._window),
            ).fetchall()
        finally:
            conn.close()
        messages = [
            {"role": row["role"], "content": row["content"]}
            for row in reversed(rows)
        ]
        if summary:
            messages.insert(0, {"role": "system", "content": f"[历史摘要] {summary}"})
        return messages

    def get_state(self, session_id: str) -> dict:
        """读取会话临时状态（如待补齐草稿）；无会话或数据异常时返回空字典。"""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT state_json FROM agent_sessions WHERE id = ?", (session_id,)
            ).fetchone()
        finally:
            conn.close()
        if row is None or not row["state_json"]:
            return {}
        try:
            state: Any = json.loads(row["state_json"])
        except (TypeError, json.JSONDecodeError):
            return {}
        return state if isinstance(state, dict) else {}

    def set_state(self, session_id: str, state: dict) -> None:
        """覆盖写入会话临时状态；会话不存在时自动创建。"""
        payload = json.dumps(state or {}, ensure_ascii=False)
        conn = self._connect()
        try:
            with conn:
                now = self._now()
                self._ensure_session(conn, session_id, now)
                conn.execute(
                    "UPDATE agent_sessions SET state_json = ?, updated_at = ? WHERE id = ?",
                    (payload, now, session_id),
                )
        finally:
            conn.close()

    def clear(self, session_id: str) -> None:
        """删除会话及其全部消息。"""
        conn = self._connect()
        try:
            with conn:
                conn.execute(
                    "DELETE FROM agent_messages WHERE session_id = ?", (session_id,)
                )
                conn.execute("DELETE FROM agent_sessions WHERE id = ?", (session_id,))
        finally:
            conn.close()

    def close(self) -> None:
        """兼容接口：本实现不持有长连接，无需释放资源。"""
