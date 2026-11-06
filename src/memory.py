"""Thread-safe in-memory data layer used at stage two."""

from copy import deepcopy
from threading import RLock

from src.schema import SCHEMAS, WINDOW_SECONDS, validate


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
