"""Generated inputs verify the real CLI and asynchronous HTTP lifecycle."""

import base64
import bz2
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest.mock import patch
from urllib.parse import urlsplit

from hypothesis import given, settings
from hypothesis import strategies as st

from src.app import create_app
from src.client import ApiClient
from src.database import SQLiteStore
from src.memory import MemoryStore


def local_client(app):
    """Adapt a Flask transport while keeping serialization in ApiClient."""
    http = app.test_client()

    def transport(method, url, data, headers):
        parts = urlsplit(url)
        reply = http.open(
            parts.path, method=method, data=data, headers=headers
        )
        return reply.status_code, reply.data

    return ApiClient(transport=transport)


@given(data=st.binary(max_size=1000), sql=st.booleans(), bad=st.booleans())
@settings(max_examples=12, deadline=None)
def test_background_and_persistence(data, sql, bad):
    with TemporaryDirectory() as folder:
        path = str(Path(folder) / "data.sqlite")
        store = SQLiteStore(path) if sql else MemoryStore()
        app = create_app(store)
        api = local_client(app)
        person = api.person_register(locale="ru-RU", user_agent="test")
        content = "!" if bad else base64.b64encode(data).decode("ascii")
        query = api.query_register(
            person=person["identifier"], content=content
        )
        app.extensions["jobs"].drain()
        result = api.result_browse(query["identifier"])[0]
        if bad:
            assert result["state"] == "failed" and result["failure"]
        else:
            assert result["state"] == "done"
            assert bz2.decompress(base64.b64decode(result["output"])) == data
        app.extensions["jobs"].close()
        if sql:
            restored = SQLiteStore(path)
            assert restored.browse("result", {}) == [result]
            restored.close()


@given(st.binary(max_size=100))
@settings(max_examples=5, deadline=None)
def test_http_returns_before_compression_finishes(data):
    app = create_app()
    api = local_client(app)
    jobs = app.extensions["jobs"]
    release = Event()
    entered = Event()
    compress = jobs._compress

    def delayed(content):
        entered.set()
        if not release.wait(timeout=5):
            raise TimeoutError("HTTP request waited for the job")
        return compress(content)

    try:
        with patch.object(jobs, "_compress", delayed):
            person = api.person_register(locale="ru-RU", user_agent="test")
            content = base64.b64encode(data).decode("ascii")
            query = api.query_register(
                person=person["identifier"], content=content
            )
            assert entered.wait(timeout=2)
            assert api.result_browse(query["identifier"])[0]["state"] == (
                "running"
            )
            release.set()
            jobs.drain()
            result = api.result_browse(query["identifier"])[0]
            assert bz2.decompress(base64.b64decode(result["output"])) == data
    finally:
        release.set()
        jobs.close()
