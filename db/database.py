import os
import time

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
    user_id    INTEGER PRIMARY KEY,
    username   TEXT,
    full_name  TEXT,
    joined_at  INTEGER NOT NULL,
    last_seen  INTEGER NOT NULL,
    mode       TEXT    NOT NULL DEFAULT 'detailed',
    task       TEXT    NOT NULL DEFAULT 'auto',
    vip_until  INTEGER NOT NULL DEFAULT 0,
    banned     INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS usage(
    user_id INTEGER NOT NULL,
    day     TEXT    NOT NULL,
    count   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(user_id, day)
);
CREATE TABLE IF NOT EXISTS history(
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    role       TEXT    NOT NULL,
    content    TEXT    NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_history_user ON history(user_id, id);
CREATE TABLE IF NOT EXISTS requests(
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    task       TEXT,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS saved(
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    title      TEXT    NOT NULL,
    content    TEXT    NOT NULL,
    created_at INTEGER NOT NULL
);
"""

KEEP_HISTORY_ROWS = 20
STORED_CONTENT_LIMIT = 3000
EDITABLE_FIELDS = {"mode", "task"}


class Database:
    def __init__(self, path: str):
        self.path = path
        self.conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        folder = os.path.dirname(self.path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.execute("PRAGMA journal_mode=WAL")
        await self.conn.executescript(SCHEMA)
        await self.conn.commit()

    async def close(self) -> None:
        if self.conn:
            await self.conn.close()
            self.conn = None

    # ---------- users ----------
    async def upsert_user(self, user_id: int, username: str | None, full_name: str):
        now = int(time.time())
        await self.conn.execute(
            """INSERT INTO users(user_id, username, full_name, joined_at, last_seen)
               VALUES(?,?,?,?,?)
               ON CONFLICT(user_id) DO UPDATE SET
                 username=excluded.username,
                 full_name=excluded.full_name,
                 last_seen=excluded.last_seen""",
            (user_id, username, full_name, now, now),
        )
        await self.conn.commit()
        return await self.get_user(user_id)

    async def get_user(self, user_id: int):
        cur = await self.conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        return await cur.fetchone()

    async def set_field(self, user_id: int, field: str, value) -> None:
        if field not in EDITABLE_FIELDS:
            raise ValueError(f"field not editable: {field}")
        await self.conn.execute(f"UPDATE users SET {field}=? WHERE user_id=?", (value, user_id))
        await self.conn.commit()

    async def set_banned(self, user_id: int, banned: bool) -> bool:
        cur = await self.conn.execute(
            "UPDATE users SET banned=? WHERE user_id=?", (1 if banned else 0, user_id)
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def add_vip(self, user_id: int, days: int) -> int | None:
        """Extend VIP by `days`. Returns new expiry timestamp, or None if user unknown."""
        row = await self.get_user(user_id)
        if row is None:
            return None
        start = max(int(time.time()), row["vip_until"])
        until = start + days * 86400
        await self.conn.execute("UPDATE users SET vip_until=? WHERE user_id=?", (until, user_id))
        await self.conn.commit()
        return until

    async def remove_vip(self, user_id: int) -> bool:
        cur = await self.conn.execute("UPDATE users SET vip_until=0 WHERE user_id=?", (user_id,))
        await self.conn.commit()
        return cur.rowcount > 0

    async def all_user_ids(self) -> list[int]:
        cur = await self.conn.execute("SELECT user_id FROM users WHERE banned=0")
        return [r["user_id"] for r in await cur.fetchall()]

    # ---------- usage ----------
    async def usage_today(self, user_id: int, day: str) -> int:
        cur = await self.conn.execute(
            "SELECT count FROM usage WHERE user_id=? AND day=?", (user_id, day)
        )
        row = await cur.fetchone()
        return row["count"] if row else 0

    async def add_usage(self, user_id: int, day: str) -> None:
        await self.conn.execute(
            """INSERT INTO usage(user_id, day, count) VALUES(?,?,1)
               ON CONFLICT(user_id, day) DO UPDATE SET count=count+1""",
            (user_id, day),
        )
        await self.conn.commit()

    async def log_request(self, user_id: int, task: str) -> None:
        await self.conn.execute(
            "INSERT INTO requests(user_id, task, created_at) VALUES(?,?,?)",
            (user_id, task, int(time.time())),
        )
        await self.conn.commit()

    # ---------- history (conversation memory) ----------
    async def add_history(self, user_id: int, role: str, content: str) -> None:
        content = content[:STORED_CONTENT_LIMIT]
        await self.conn.execute(
            "INSERT INTO history(user_id, role, content, created_at) VALUES(?,?,?,?)",
            (user_id, role, content, int(time.time())),
        )
        await self.conn.execute(
            """DELETE FROM history WHERE user_id=? AND id NOT IN
               (SELECT id FROM history WHERE user_id=? ORDER BY id DESC LIMIT ?)""",
            (user_id, user_id, KEEP_HISTORY_ROWS),
        )
        await self.conn.commit()

    async def get_history(self, user_id: int, limit: int) -> list[tuple[str, str]]:
        cur = await self.conn.execute(
            "SELECT role, content FROM history WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        )
        rows = await cur.fetchall()
        return [(r["role"], r["content"]) for r in reversed(rows)]

    async def last_history(self, user_id: int, role: str) -> str | None:
        cur = await self.conn.execute(
            "SELECT content FROM history WHERE user_id=? AND role=? ORDER BY id DESC LIMIT 1",
            (user_id, role),
        )
        row = await cur.fetchone()
        return row["content"] if row else None

    async def clear_history(self, user_id: int) -> None:
        await self.conn.execute("DELETE FROM history WHERE user_id=?", (user_id,))
        await self.conn.commit()

    # ---------- saved solutions ----------
    async def add_saved(self, user_id: int, title: str, content: str) -> int:
        cur = await self.conn.execute(
            "INSERT INTO saved(user_id, title, content, created_at) VALUES(?,?,?,?)",
            (user_id, title[:60], content, int(time.time())),
        )
        await self.conn.commit()
        return cur.lastrowid

    async def list_saved(self, user_id: int, limit: int = 10):
        cur = await self.conn.execute(
            "SELECT id, title FROM saved WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        )
        return await cur.fetchall()

    async def get_saved(self, user_id: int, saved_id: int):
        cur = await self.conn.execute(
            "SELECT id, title, content FROM saved WHERE user_id=? AND id=?",
            (user_id, saved_id),
        )
        return await cur.fetchone()

    async def delete_saved(self, user_id: int, saved_id: int) -> bool:
        cur = await self.conn.execute(
            "DELETE FROM saved WHERE user_id=? AND id=?", (user_id, saved_id)
        )
        await self.conn.commit()
        return cur.rowcount > 0

    # ---------- stats ----------
    async def stats(self, day_start_ts: int) -> dict:
        async def one(sql, args=()):
            cur = await self.conn.execute(sql, args)
            return (await cur.fetchone())[0]

        now = int(time.time())
        return {
            "users": await one("SELECT COUNT(*) FROM users"),
            "active_today": await one(
                "SELECT COUNT(*) FROM users WHERE last_seen>=?", (day_start_ts,)
            ),
            "vip": await one("SELECT COUNT(*) FROM users WHERE vip_until>?", (now,)),
            "banned": await one("SELECT COUNT(*) FROM users WHERE banned=1"),
            "requests_today": await one(
                "SELECT COUNT(*) FROM requests WHERE created_at>=?", (day_start_ts,)
            ),
            "requests_total": await one("SELECT COUNT(*) FROM requests"),
        }
