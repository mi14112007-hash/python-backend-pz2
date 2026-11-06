"""Record schema, in-memory storage and explicit SQLite queries."""

import sqlite3
from copy import deepcopy
from threading import RLock

SCHEMAS = {
    "person": dict(identifier=int, time=int, locale=str, user_agent=str),
    "query": dict(identifier=int, time=int, content=str, person=int),
    "result": dict(
        identifier=int,
        time=int,
        output=str,
        state=str,
        failure=str,
        query=int,
        duration=int,
    ),
}
WINDOW_SECONDS = 9 * 60


def validate(entity, values, partial=False):
    """Validate field names and exact Python types."""
    schema = SCHEMAS[entity]
    if not values or not set(values) <= set(schema):
        raise ValueError("Unknown fields or empty record")
    if not partial and set(values) != set(schema):
        raise ValueError("Required fields are missing")
    for name, value in values.items():
        if type(value) is not schema[name]:
            raise ValueError(f"Invalid type: {name}")


class MemoryStore:
    """Store records in dictionaries and return detached copies."""

    def __init__(self):
        self.tables = {name: {} for name in SCHEMAS}
        self.lock = RLock()

    def _references(self, entity, values):
        links = {"query": ("person", "person"), "result": ("query", "query")}
        if entity in links:
            parent, field = links[entity]
            if values[field] not in self.tables[parent]:
                raise ValueError("Related record does not exist")

    def add(self, entity, values):
        """Generate an identifier and insert one complete record."""
        if "identifier" in values:
            raise ValueError("Identifier is assigned by the server")
        with self.lock:
            record = dict(values)
            record["identifier"] = max(self.tables[entity], default=0) + 1
            validate(entity, record)
            self._references(entity, record)
            self.tables[entity][record["identifier"]] = record
            return deepcopy(record)

    def browse(self, entity, filters):
        """Match every supplied field exactly."""
        if filters:
            validate(entity, filters, partial=True)
        with self.lock:
            return deepcopy(
                [
                    row
                    for row in self.tables[entity].values()
                    if all(row[key] == value for key, value in filters.items())
                ]
            )

    def adjust(self, entity, identifier, changes):
        """Atomically change editable fields of an existing record."""
        validate(entity, changes, partial=True)
        if "identifier" in changes:
            raise ValueError("Identifier cannot be changed")
        with self.lock:
            if identifier not in self.tables[entity]:
                raise ValueError("Record does not exist")
            record = {**self.tables[entity][identifier], **changes}
            self._references(entity, record)
            self.tables[entity][identifier] = record
            return deepcopy(record)

    def report(self, now):
        """Project distinct locale/content pairs of recent queries."""
        with self.lock:
            pairs = {
                (
                    self.tables["person"].get(row["person"], {}).get("locale"),
                    row["content"],
                )
                for row in self.tables["query"].values()
                if row["time"] > now - WINDOW_SECONDS
            }
            return [
                dict(locale=locale, content=content)
                for locale, content in sorted(pairs)
            ]

    def close(self):
        """Provide the same lifecycle interface as SQLiteStore."""


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
