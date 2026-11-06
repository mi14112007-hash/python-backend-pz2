"""Asynchronous Bzip2 jobs, XML HTTP handlers and Flask server."""

import argparse
import atexit
import base64
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic, time
from xml.etree.ElementTree import ParseError

from flask import Flask, Response, request

from src.db import SCHEMAS, MemoryStore, SQLiteStore
from src.xmlio import decode, encode

CLI_PATH = Path(__file__).with_name("compress.py")
TIMEOUT_SECONDS = 30
MILLISECONDS = 1000
FILTER_VALUE_COUNT = 1


class JobQueue:
    """Run one compression at a time without blocking HTTP responses."""

    def __init__(self, store, fake=False):
        self.store = store
        self.fake = fake
        self.executor = ThreadPoolExecutor(max_workers=1)

    def submit(self, query):
        """Persist a queued result before scheduling a task snapshot."""
        result = self.store.add(
            "result",
            dict(
                time=int(time()),
                output="",
                state="queued",
                failure="",
                query=query["identifier"],
                duration=0,
            ),
        )
        self.executor.submit(self._run, query, result["identifier"])
        return result

    def _run(self, query, identifier):
        started = monotonic()
        self.store.adjust("result", identifier, {"state": "running"})
        try:
            output = "" if self.fake else self._compress(query["content"])
            changes = dict(state="done", output=output, failure="")
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            changes = dict(state="failed", output="", failure=str(error))
        changes["duration"] = int((monotonic() - started) * MILLISECONDS)
        changes["time"] = int(time())
        self.store.adjust("result", identifier, changes)

    def _compress(self, content):
        with TemporaryDirectory() as folder:
            source = Path(folder) / "input"
            source.write_bytes(base64.b64decode(content, validate=True))
            process = subprocess.run(
                [sys.executable, str(CLI_PATH), str(source)],
                capture_output=True,
                timeout=TIMEOUT_SECONDS,
                check=True,
            )
            return base64.b64encode(process.stdout).decode("ascii")

    def drain(self):
        """Wait for all already submitted tasks, keeping the queue open."""
        self.executor.submit(lambda: None).result()

    def close(self):
        """Finish pending tasks before closing the data layer."""
        self.executor.shutdown(wait=True)
        self.store.close()


HEADERS = {"Accept": "text/xml", "Accept-Language": "ru-RU"}


def response(tag, data, status=200):
    """Return UTF-8 XML, including application-level errors."""
    return Response(
        encode(tag, data),
        status=status,
        content_type="text/xml; charset=utf-8",
    )


def create_app(store=None, fake=False, clock=time):
    """Assemble routes with either memory or SQLite persistence."""
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
    store = store if store is not None else MemoryStore()
    jobs = JobQueue(store, fake)
    app.extensions.update(store=store, jobs=jobs)
    app.before_request(check_headers)
    app.register_error_handler(ValueError, application_error)
    app.register_error_handler(ParseError, application_error)
    register_people(app, store, clock)
    register_queries(app, store, jobs, clock)
    register_results(app, store, clock)
    return app


def check_headers():
    """Check required header values in the order of the assignment."""
    for name, value in HEADERS.items():
        if request.headers.get(name) != value:
            return response(
                "error",
                {"message": f"Required: {name}"},
                HTTPStatus.NOT_ACCEPTABLE,
            )
    return None


def application_error(error):
    """Keep status 200 when headers are valid, per the specification."""
    return response("error", {"message": str(error)})


def filters(entity, fixed=None):
    """Convert query-string filters using the entity field types."""
    values = {}
    for key in request.args:
        if (
            key not in SCHEMAS[entity]
            or len(request.args.getlist(key)) != FILTER_VALUE_COUNT
        ):
            raise ValueError("Unknown or repeated search field")
        values[key] = SCHEMAS[entity][key](request.args[key])
    if fixed:
        values.update(fixed)
    return values


def register_people(app, store, clock):
    """Bind all handlers without runtime route construction."""

    @app.post("/api/register/person")
    def person_register():
        values = decode(request.data, "person")
        values.setdefault("time", int(clock()))
        return response("person", store.add("person", values))

    @app.get("/api/browse/person")
    def person_browse():
        return response("people", store.browse("person", filters("person")))

    @app.post("/api/adjust/person")
    def person_adjust():
        return adjust(store, "person")


def register_queries(app, store, jobs, clock):
    """Register creation, lookup and modification of queries."""

    @app.post("/api/register/query")
    def query_register():
        values = decode(request.data, "query")
        values.setdefault("time", int(clock()))
        query = store.add("query", values)
        jobs.submit(query)
        return response("query", query)

    @app.get("/api/browse/query/<int:person>")
    def query_browse(person):
        return response(
            "queries",
            store.browse("query", filters("query", {"person": person})),
        )

    @app.post("/api/adjust/query")
    def query_adjust():
        return adjust(store, "query")


def register_results(app, store, clock):
    """Register result lookup and the relational report."""

    @app.get("/api/browse/result/<int:query>")
    def result_browse(query):
        return response(
            "results",
            store.browse("result", filters("result", {"query": query})),
        )

    @app.get("/api/browse/report")
    def report_browse():
        return response("report", store.report(int(clock())))


def adjust(store, entity):
    """Extract the immutable identifier from the XML update."""
    values = decode(request.data, entity)
    if "identifier" not in values:
        raise ValueError("Identifier is required")
    identifier = values.pop("identifier")
    return response(entity, store.adjust(entity, identifier, values))


def main():
    """Start a local server with an explicitly selected persistence mode."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--backend", choices=["memory", "sqlite"], default="sqlite"
    )
    parser.add_argument("--database", default="data.sqlite")
    parser.add_argument("--port", type=int, default=5005)
    parser.add_argument("--fake", action="store_true")
    args = parser.parse_args()
    store = SQLiteStore(args.database) if args.backend == "sqlite" else None
    app = create_app(store, args.fake)
    atexit.register(app.extensions["jobs"].close)
    app.run(host="127.0.0.1", port=args.port, use_reloader=False)


if __name__ == "__main__":
    main()
