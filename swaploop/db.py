"""SQLite schema and repository. The only module that runs SQL."""

import json
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone

from swaploop.models import (
    Answer,
    Channel,
    FreeWindow,
    HaveItem,
    LoggedMessage,
    Loop,
    LoopLeg,
    LoopStatus,
    MessageKind,
    NeedItem,
    Student,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    discord_id    TEXT UNIQUE,
    is_simulated  INTEGER NOT NULL DEFAULT 0,
    campus        TEXT,
    agent_label   TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS loops (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    status        TEXT NOT NULL,
    signature     TEXT NOT NULL,
    meeting_day   TEXT,
    meeting_min   INTEGER,
    meeting_place TEXT,
    conflicts     TEXT NOT NULL DEFAULT '{}',
    released_by   INTEGER REFERENCES students(id),
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS have_items (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id),
    name       TEXT NOT NULL,
    canonical  TEXT NOT NULL,
    condition  TEXT NOT NULL,
    value_usd  INTEGER NOT NULL,
    loop_id    INTEGER REFERENCES loops(id)
);
CREATE TABLE IF NOT EXISTS need_items (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id),
    name       TEXT NOT NULL,
    canonical  TEXT NOT NULL,
    loop_id    INTEGER REFERENCES loops(id)
);
CREATE TABLE IF NOT EXISTS free_windows (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id),
    day        TEXT NOT NULL,
    start_min  INTEGER NOT NULL,
    end_min    INTEGER NOT NULL,
    CHECK (start_min < end_min)
);
CREATE TABLE IF NOT EXISTS loop_legs (
    loop_id      INTEGER NOT NULL REFERENCES loops(id),
    position     INTEGER NOT NULL,
    giver_id     INTEGER NOT NULL REFERENCES students(id),
    receiver_id  INTEGER NOT NULL REFERENCES students(id),
    have_item_id INTEGER NOT NULL REFERENCES have_items(id),
    need_item_id INTEGER NOT NULL REFERENCES need_items(id),
    PRIMARY KEY (loop_id, position)
);
CREATE TABLE IF NOT EXISTS confirmations (
    loop_id    INTEGER NOT NULL REFERENCES loops(id),
    student_id INTEGER NOT NULL REFERENCES students(id),
    answer     TEXT NOT NULL DEFAULT 'PENDING',
    PRIMARY KEY (loop_id, student_id)
);
CREATE TABLE IF NOT EXISTS message_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at   TEXT NOT NULL,
    channel      TEXT NOT NULL,
    recipient_id INTEGER,
    kind         TEXT NOT NULL,
    body         TEXT NOT NULL
);
"""

_TABLES_IN_DELETE_ORDER = (
    "message_log", "confirmations", "loop_legs", "have_items",
    "need_items", "free_windows", "loops", "students",
)


def agent_label_for(student_id: int) -> str:
    """Agent A..Z, then Agent AA, AB, ... (stable because ids are never reused)."""
    letters = ""
    number = student_id
    while number > 0:
        number, remainder = divmod(number - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return f"Agent {letters}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: str = ":memory:"):
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(SCHEMA)

    def close(self) -> None:
        self._conn.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._conn:
            yield

    # students

    @staticmethod
    def _student(row: sqlite3.Row) -> Student:
        return Student(
            id=row["id"], name=row["name"], discord_id=row["discord_id"],
            is_simulated=bool(row["is_simulated"]), campus=row["campus"],
            agent_label=row["agent_label"],
        )

    def add_student(
        self, name: str, discord_id: str | None = None,
        is_simulated: bool = False, campus: str | None = None,
    ) -> Student:
        with self._conn:
            cursor = self._conn.execute(
                "INSERT INTO students (name, discord_id, is_simulated, campus) VALUES (?, ?, ?, ?)",
                (name, discord_id, int(is_simulated), campus),
            )
            student_id = cursor.lastrowid
            self._conn.execute(
                "UPDATE students SET agent_label = ? WHERE id = ?",
                (agent_label_for(student_id), student_id),
            )
        return self.get_student(student_id)

    def get_student(self, student_id: int) -> Student:
        row = self._conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
        if row is None:
            raise KeyError(f"No student with id {student_id}")
        return self._student(row)

    def find_student_by_discord_id(self, discord_id: str) -> Student | None:
        row = self._conn.execute(
            "SELECT * FROM students WHERE discord_id = ?", (discord_id,)
        ).fetchone()
        return self._student(row) if row else None

    def list_students(self) -> list[Student]:
        rows = self._conn.execute("SELECT * FROM students ORDER BY id").fetchall()
        return [self._student(row) for row in rows]

    def set_campus(self, student_id: int, campus: str) -> None:
        with self._conn:
            self._conn.execute("UPDATE students SET campus = ? WHERE id = ?", (campus, student_id))

    def delete_simulated_students(self) -> None:
        """Remove simulated students and any loop they were part of."""
        ids = [row["id"] for row in self._conn.execute(
            "SELECT id FROM students WHERE is_simulated = 1")]
        if not ids:
            return
        marks = ",".join("?" * len(ids))
        with self._conn:
            loop_ids = [row["loop_id"] for row in self._conn.execute(
                f"SELECT DISTINCT loop_id FROM loop_legs "
                f"WHERE giver_id IN ({marks}) OR receiver_id IN ({marks})", ids + ids)]
            for loop_id in loop_ids:
                self._conn.execute("UPDATE have_items SET loop_id = NULL WHERE loop_id = ?", (loop_id,))
                self._conn.execute("UPDATE need_items SET loop_id = NULL WHERE loop_id = ?", (loop_id,))
                self._conn.execute("DELETE FROM confirmations WHERE loop_id = ?", (loop_id,))
                self._conn.execute("DELETE FROM loop_legs WHERE loop_id = ?", (loop_id,))
                self._conn.execute("DELETE FROM loops WHERE id = ?", (loop_id,))
            for table in ("have_items", "need_items", "free_windows", "confirmations", "message_log"):
                column = "recipient_id" if table == "message_log" else "student_id"
                self._conn.execute(f"DELETE FROM {table} WHERE {column} IN ({marks})", ids)
            self._conn.execute(f"DELETE FROM students WHERE id IN ({marks})", ids)

    # items and windows

    @staticmethod
    def _have(row: sqlite3.Row) -> HaveItem:
        return HaveItem(
            id=row["id"], student_id=row["student_id"], name=row["name"],
            canonical=row["canonical"], condition=row["condition"],
            value_usd=row["value_usd"], loop_id=row["loop_id"],
        )

    @staticmethod
    def _need(row: sqlite3.Row) -> NeedItem:
        return NeedItem(
            id=row["id"], student_id=row["student_id"], name=row["name"],
            canonical=row["canonical"], loop_id=row["loop_id"],
        )

    def add_have(
        self, student_id: int, name: str, canonical: str, condition: str, value_usd: int
    ) -> HaveItem:
        with self._conn:
            cursor = self._conn.execute(
                "INSERT INTO have_items (student_id, name, canonical, condition, value_usd) "
                "VALUES (?, ?, ?, ?, ?)",
                (student_id, name, canonical, condition, value_usd),
            )
        return self.get_have(cursor.lastrowid)

    def add_need(self, student_id: int, name: str, canonical: str) -> NeedItem:
        with self._conn:
            cursor = self._conn.execute(
                "INSERT INTO need_items (student_id, name, canonical) VALUES (?, ?, ?)",
                (student_id, name, canonical),
            )
        return self.get_need(cursor.lastrowid)

    def get_have(self, item_id: int) -> HaveItem:
        row = self._conn.execute("SELECT * FROM have_items WHERE id = ?", (item_id,)).fetchone()
        if row is None:
            raise KeyError(f"No have item with id {item_id}")
        return self._have(row)

    def get_need(self, item_id: int) -> NeedItem:
        row = self._conn.execute("SELECT * FROM need_items WHERE id = ?", (item_id,)).fetchone()
        if row is None:
            raise KeyError(f"No need item with id {item_id}")
        return self._need(row)

    def list_haves(self, student_id: int | None = None, unreserved_only: bool = False) -> list[HaveItem]:
        return [self._have(row) for row in self._select_items("have_items", student_id, unreserved_only)]

    def list_needs(self, student_id: int | None = None, unreserved_only: bool = False) -> list[NeedItem]:
        return [self._need(row) for row in self._select_items("need_items", student_id, unreserved_only)]

    def _select_items(self, table: str, student_id: int | None, unreserved_only: bool):
        clauses, params = [], []
        if student_id is not None:
            clauses.append("student_id = ?")
            params.append(student_id)
        if unreserved_only:
            clauses.append("loop_id IS NULL")
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        return self._conn.execute(f"SELECT * FROM {table}{where} ORDER BY id", params).fetchall()

    def add_free_window(self, student_id: int, day: str, start_min: int, end_min: int) -> FreeWindow:
        if start_min >= end_min:
            raise ValueError("A free window must start before it ends.")
        with self._conn:
            cursor = self._conn.execute(
                "INSERT INTO free_windows (student_id, day, start_min, end_min) VALUES (?, ?, ?, ?)",
                (student_id, day, start_min, end_min),
            )
        return FreeWindow(cursor.lastrowid, student_id, day, start_min, end_min)

    def list_free_windows(self, student_id: int | None = None) -> list[FreeWindow]:
        if student_id is None:
            rows = self._conn.execute("SELECT * FROM free_windows ORDER BY id").fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM free_windows WHERE student_id = ? ORDER BY id", (student_id,)
            ).fetchall()
        return [
            FreeWindow(r["id"], r["student_id"], r["day"], r["start_min"], r["end_min"])
            for r in rows
        ]

    # loops

    @staticmethod
    def _loop(row: sqlite3.Row) -> Loop:
        return Loop(
            id=row["id"], status=LoopStatus(row["status"]), signature=row["signature"],
            meeting_day=row["meeting_day"], meeting_min=row["meeting_min"],
            meeting_place=row["meeting_place"], conflicts=json.loads(row["conflicts"]),
            released_by=row["released_by"], created_at=row["created_at"],
        )

    def create_loop(
        self,
        legs: Iterable[LoopLeg],
        meeting_day: str | None,
        meeting_min: int | None,
        meeting_place: str | None,
        conflicts: dict,
    ) -> Loop:
        """Insert a PENDING loop and reserve its items; fails if any is already reserved."""
        legs = list(legs)
        signature = ",".join(str(i) for i in sorted(leg.have_item_id for leg in legs))
        with self._conn:
            cursor = self._conn.execute(
                "INSERT INTO loops (status, signature, meeting_day, meeting_min, meeting_place, "
                "conflicts, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (LoopStatus.PENDING.value, signature, meeting_day, meeting_min, meeting_place,
                 json.dumps(conflicts), _now()),
            )
            loop_id = cursor.lastrowid
            for leg in legs:
                for table, item_id in (("have_items", leg.have_item_id), ("need_items", leg.need_item_id)):
                    reserved = self._conn.execute(
                        f"UPDATE {table} SET loop_id = ? WHERE id = ? AND loop_id IS NULL",
                        (loop_id, item_id),
                    )
                    if reserved.rowcount != 1:
                        raise ValueError(f"Item {item_id} in {table} is already in another loop.")
                self._conn.execute(
                    "INSERT INTO loop_legs (loop_id, position, giver_id, receiver_id, have_item_id, "
                    "need_item_id) VALUES (?, ?, ?, ?, ?, ?)",
                    (loop_id, leg.position, leg.giver_id, leg.receiver_id,
                     leg.have_item_id, leg.need_item_id),
                )
                self._conn.execute(
                    "INSERT OR IGNORE INTO confirmations (loop_id, student_id) VALUES (?, ?)",
                    (loop_id, leg.giver_id),
                )
        return self.get_loop(loop_id)

    def get_loop(self, loop_id: int) -> Loop:
        row = self._conn.execute("SELECT * FROM loops WHERE id = ?", (loop_id,)).fetchone()
        if row is None:
            raise KeyError(f"No loop with id {loop_id}")
        return self._loop(row)

    def list_loops(self, status: LoopStatus | None = None) -> list[Loop]:
        if status is None:
            rows = self._conn.execute("SELECT * FROM loops ORDER BY id").fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM loops WHERE status = ? ORDER BY id", (status.value,)
            ).fetchall()
        return [self._loop(row) for row in rows]

    def get_legs(self, loop_id: int) -> list[LoopLeg]:
        rows = self._conn.execute(
            "SELECT * FROM loop_legs WHERE loop_id = ? ORDER BY position", (loop_id,)
        ).fetchall()
        return [
            LoopLeg(r["position"], r["giver_id"], r["receiver_id"], r["have_item_id"], r["need_item_id"])
            for r in rows
        ]

    def released_signatures(self) -> set[str]:
        rows = self._conn.execute(
            "SELECT signature FROM loops WHERE status = ?", (LoopStatus.RELEASED.value,)
        ).fetchall()
        return {row["signature"] for row in rows}

    def get_confirmations(self, loop_id: int) -> dict[int, Answer]:
        rows = self._conn.execute(
            "SELECT student_id, answer FROM confirmations WHERE loop_id = ? ORDER BY student_id",
            (loop_id,),
        ).fetchall()
        return {row["student_id"]: Answer(row["answer"]) for row in rows}

    def record_answer(self, loop_id: int, student_id: int, answer: Answer) -> bool:
        """Store an answer only if the student has not answered yet. Returns whether it counted."""
        with self._conn:
            updated = self._conn.execute(
                "UPDATE confirmations SET answer = ? "
                "WHERE loop_id = ? AND student_id = ? AND answer = ?",
                (answer.value, loop_id, student_id, Answer.PENDING.value),
            )
        return updated.rowcount == 1

    def lock_loop(self, loop_id: int) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE loops SET status = ? WHERE id = ?", (LoopStatus.LOCKED.value, loop_id)
            )

    def release_loop(self, loop_id: int, released_by: int | None = None) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE loops SET status = ?, released_by = ? WHERE id = ?",
                (LoopStatus.RELEASED.value, released_by, loop_id),
            )
            self._conn.execute("UPDATE have_items SET loop_id = NULL WHERE loop_id = ?", (loop_id,))
            self._conn.execute("UPDATE need_items SET loop_id = NULL WHERE loop_id = ?", (loop_id,))

    # message log

    def log_message(
        self, channel: Channel, recipient_id: int | None, kind: MessageKind, body: str
    ) -> LoggedMessage:
        created_at = _now()
        with self._conn:
            cursor = self._conn.execute(
                "INSERT INTO message_log (created_at, channel, recipient_id, kind, body) "
                "VALUES (?, ?, ?, ?, ?)",
                (created_at, channel.value, recipient_id, kind.value, body),
            )
        return LoggedMessage(cursor.lastrowid, created_at, channel, recipient_id, kind, body)

    def list_messages(self) -> list[LoggedMessage]:
        rows = self._conn.execute("SELECT * FROM message_log ORDER BY id").fetchall()
        return [
            LoggedMessage(r["id"], r["created_at"], Channel(r["channel"]), r["recipient_id"],
                          MessageKind(r["kind"]), r["body"])
            for r in rows
        ]

    # reset

    def reset_all(self) -> None:
        with self._conn:
            for table in _TABLES_IN_DELETE_ORDER:
                self._conn.execute(f"DELETE FROM {table}")
            self._conn.execute("DELETE FROM sqlite_sequence")
