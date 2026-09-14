import sqlite3
from datetime import datetime


class MemoryDatabase:

    def __init__(self, db_path="data/arven_memory.db"):
        self.db_path = db_path
        self._initialize()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _initialize(self):

        connection = self._connect()
        cursor = connection.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                category TEXT DEFAULT 'other',
                memory_type TEXT DEFAULT 'fact',
                value TEXT,
                importance INTEGER DEFAULT 5,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        # Migrate older databases that predate memory_type/value columns.
        columns = {row[1] for row in cursor.execute("PRAGMA table_info(memories)")}
        if "memory_type" not in columns:
            cursor.execute(
                "ALTER TABLE memories ADD COLUMN memory_type TEXT DEFAULT 'fact'"
            )
        if "value" not in columns:
            cursor.execute("ALTER TABLE memories ADD COLUMN value TEXT")

        connection.commit()
        connection.close()

    def add(
        self,
        content,
        category="other",
        importance=5,
        memory_type="fact",
        value=None
    ):

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        connection = self._connect()
        cursor = connection.cursor()

        cursor.execute("""
            INSERT INTO memories
            (content, category, memory_type, value,
             importance, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            content,
            category,
            memory_type,
            value,
            importance,
            now,
            now
        ))

        memory_id = cursor.lastrowid

        connection.commit()
        connection.close()

        return memory_id

    def get_all(self):

        connection = self._connect()
        cursor = connection.cursor()

        cursor.execute("""
            SELECT
                id,
                content,
                category,
                memory_type,
                value,
                importance,
                created_at,
                updated_at
            FROM memories
            ORDER BY importance DESC, updated_at DESC
        """)

        memories = cursor.fetchall()

        connection.close()

        return memories

    def get_by_id(self, memory_id):

        connection = self._connect()
        cursor = connection.cursor()

        cursor.execute("""
            SELECT
                id,
                content,
                category,
                memory_type,
                value,
                importance,
                created_at,
                updated_at
            FROM memories
            WHERE id = ?
        """, (memory_id,))

        memory = cursor.fetchone()

        connection.close()

        return memory

    def update(
        self,
        memory_id,
        content,
        category=None,
        importance=None,
        memory_type=None,
        value=None
    ):

        existing = self.get_by_id(memory_id)

        if existing is None:
            return False

        if category is None:
            category = existing[2]

        if memory_type is None:
            memory_type = existing[3]

        if value is None:
            value = existing[4]

        if importance is None:
            importance = existing[5]

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        connection = self._connect()
        cursor = connection.cursor()

        cursor.execute("""
            UPDATE memories
            SET
                content = ?,
                category = ?,
                memory_type = ?,
                value = ?,
                importance = ?,
                updated_at = ?
            WHERE id = ?
        """, (
            content,
            category,
            memory_type,
            value,
            importance,
            now,
            memory_id
        ))

        connection.commit()
        connection.close()

        return True

    def delete(self, memory_id):

        connection = self._connect()
        cursor = connection.cursor()

        cursor.execute(
            "DELETE FROM memories WHERE id = ?",
            (memory_id,)
        )

        deleted = cursor.rowcount > 0

        connection.commit()
        connection.close()

        return deleted
