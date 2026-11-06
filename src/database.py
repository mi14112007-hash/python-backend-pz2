"""SQLite data layer using explicit SQL and bound parameters."""

import sqlite3
from threading import RLock

from src.schema import WINDOW_SECONDS, validate


class SQLiteStore:
    """Serialize operations on one connection shared with the worker."""

    def __init__(self, path):
        self.lock = RLock()
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.executescript(
            "CREATE TABLE IF NOT EXISTS person ("
            "identifier INTEGER PRIMARY KEY, time INTEGER NOT NULL, "
            "locale TEXT NOT NULL, user_agent TEXT NOT NULL);"
            'CREATE TABLE IF NOT EXISTS "query" ('
            "identifier INTEGER PRIMARY KEY, time INTEGER NOT NULL, "
            "content TEXT NOT NULL, person INTEGER NOT NULL "
            "REFERENCES person(identifier));"
            "CREATE TABLE IF NOT EXISTS result ("
            "identifier INTEGER PRIMARY KEY, time INTEGER NOT NULL, "
            "output TEXT NOT NULL, state TEXT NOT NULL, "
            'failure TEXT NOT NULL, "query" INTEGER NOT NULL '
            'REFERENCES "query"(identifier), duration INTEGER NOT NULL);'
        )

    def add(self, entity, values):
        """Insert a validated record with an automatically assigned ID."""
        if "identifier" in values:
            raise ValueError("Identifier is assigned by the server")
        validate(entity, {**values, "identifier": 0})
        fields = ", ".join(f'"{name}"' for name in values)
        placeholders = ", ".join("?" for _ in values)
        with self.lock, self.connection:
            try:
                cursor = self.connection.execute(
                    f'INSERT INTO "{entity}" ({fields}) '
                    f"VALUES ({placeholders})",
                    tuple(values.values()),
                )
            except sqlite3.IntegrityError as error:
                raise ValueError("Related record does not exist") from error
            return {**values, "identifier": cursor.lastrowid}

    def browse(self, entity, filters):
        """Return records using an equality conjunction and stable order."""
        if filters:
            validate(entity, filters, partial=True)
        fields = " AND ".join(f'"{key}" = ?' for key in filters)
        clause = f" WHERE {fields}" if fields else ""
        with self.lock:
            rows = self.connection.execute(
                f'SELECT * FROM "{entity}"{clause} ORDER BY identifier',
                tuple(filters.values()),
            ).fetchall()
            return [dict(row) for row in rows]

    def adjust(self, entity, identifier, changes):
        """Update allowed columns; rollback on a foreign-key violation."""
        validate(entity, changes, partial=True)
        if "identifier" in changes:
            raise ValueError("Identifier cannot be changed")
        fields = ", ".join(f'"{key}" = ?' for key in changes)
        with self.lock, self.connection:
            try:
                cursor = self.connection.execute(
                    f'UPDATE "{entity}" SET {fields} WHERE identifier = ?',
                    (*changes.values(), identifier),
                )
            except sqlite3.IntegrityError as error:
                raise ValueError("Related record does not exist") from error
            if not cursor.rowcount:
                raise ValueError("Record does not exist")
            return self.browse(entity, {"identifier": identifier})[0]

    def report(self, now):
        """Reverse the right join for compatibility with older SQLite."""
        with self.lock:
            rows = self.connection.execute(
                'SELECT DISTINCT p.locale, q.content FROM "query" AS q '
                "LEFT JOIN person AS p ON p.identifier = q.person "
                "WHERE q.time > ? ORDER BY p.locale, q.content",
                (now - WINDOW_SECONDS,),
            ).fetchall()
            return [dict(row) for row in rows]

    def close(self):
        """Close the connection after pending jobs finish."""
        self.connection.close()
