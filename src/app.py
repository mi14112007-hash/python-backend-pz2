"""The eight XML HTTP handlers required by variant five."""

from time import time
from xml.etree.ElementTree import ParseError

from flask import Flask, Response, request

from src.jobs import JobQueue
from src.memory import MemoryStore
from src.schema import SCHEMAS
from src.xmlio import decode, encode

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
            return response("error", {"message": f"Required: {name}"}, 406)
    return None


def application_error(error):
    """Keep status 200 when headers are valid, per the specification."""
    return response("error", {"message": str(error)})


def filters(entity, fixed=None):
    """Convert query-string filters using the entity field types."""
    values = {}
    for key in request.args:
        if key not in SCHEMAS[entity] or len(request.args.getlist(key)) != 1:
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
