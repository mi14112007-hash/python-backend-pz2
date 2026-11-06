"""Independent dictionary oracle exercised exclusively by Hypothesis."""

import base64
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

import pytest
from hypothesis import settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

from src.app import create_app
from src.client import ApiClient
from src.memory import MemoryStore

NOW = 2000000
TEXT = st.sampled_from(["ru-RU", "en-US", '<&> quotes "', ""])


class ApiMachine(RuleBasedStateMachine):
    """Compare the HTTP state against a separately maintained oracle."""

    backend = "memory"

    def __init__(self):
        super().__init__()
        self.folder = TemporaryDirectory()
        store = MemoryStore()
        self.app = create_app(store, fake=True, clock=lambda: NOW)
        self.http = self.app.test_client()
        self.api = ApiClient(transport=self.transport)
        self.people = {}
        self.queries = {}

    def transport(self, method, url, data, headers):
        parts = urlsplit(url)
        path = parts.path + ("?" + parts.query if parts.query else "")
        reply = self.http.open(path, method=method, data=data, headers=headers)
        return reply.status_code, reply.data

    @rule(locale=TEXT, agent=TEXT)
    def register_person(self, locale, agent):
        record = self.api.person_register(locale=locale, user_agent=agent)
        expected = dict(
            identifier=len(self.people) + 1,
            time=NOW,
            locale=locale,
            user_agent=agent,
        )
        assert record == expected
        self.people[record["identifier"]] = expected

    @rule(index=st.integers(0, 100), locale=TEXT)
    def adjust_person(self, index, locale):
        if not self.people:
            return
        identifier = index % len(self.people) + 1
        result = self.api.person_adjust(identifier, locale=locale)
        self.people[identifier]["locale"] = locale
        assert result == self.people[identifier]

    @rule(
        index=st.integers(0, 100),
        data=st.binary(max_size=30),
        offset=st.sampled_from([-541, -540, -539, 0, 1]),
    )
    def register_query(self, index, data, offset):
        if not self.people:
            return
        person = index % len(self.people) + 1
        content = base64.b64encode(data).decode("ascii")
        record = self.api.query_register(
            person=person, content=content, time=NOW + offset
        )
        expected = dict(
            identifier=len(self.queries) + 1,
            person=person,
            time=NOW + offset,
            content=content,
        )
        assert record == expected
        self.queries[record["identifier"]] = expected
        self.app.extensions["jobs"].drain()
        result = self.api.result_browse(record["identifier"])[0]
        assert result["state"] == "done"
        assert result["output"] == result["failure"] == ""
        assert result["query"] == record["identifier"]
        assert result["duration"] >= 0

    @rule(index=st.integers(0, 100), offset=st.integers(-600, 5))
    def adjust_query(self, index, offset):
        if not self.queries:
            return
        identifier = index % len(self.queries) + 1
        result = self.api.query_adjust(identifier, time=NOW + offset)
        self.queries[identifier]["time"] = NOW + offset
        assert result == self.queries[identifier]

    @rule()
    def missing_references(self):
        with pytest.raises(ValueError):
            self.api.query_register(person=999999, content="")
        with pytest.raises(ValueError):
            self.api.person_adjust(999999, locale="ru-RU")
        with pytest.raises(ValueError):
            self.api.query_adjust(999999, content="")

    @rule(
        field=st.sampled_from(["Accept", "Accept-Language"]),
        wrong=st.booleans(),
    )
    def invalid_headers(self, field, wrong):
        original = self.api.headers.copy()
        if wrong:
            self.api.headers[field] = "invalid"
        else:
            self.api.headers.pop(field)
        with pytest.raises(ValueError, match="HTTP 406"):
            self.api.person_browse()
        self.api.headers = original

    @rule(
        payload=st.sampled_from(
            [
                b"<",
                b"<wrong/>",
                b"<person><bad>1</bad></person>",
                b"<person><time>abc</time></person>",
                b"<person><locale/><locale/></person>",
                b"<!DOCTYPE person><person/>",
                b"<person><locale x='y'/></person>",
                b"<person/>",
            ]
        )
    )
    def invalid_xml(self, payload):
        reply = self.http.post(
            "/api/register/person", data=payload, headers=self.api.headers
        )
        assert reply.status_code == 200
        assert b"<error>" in reply.data

    @rule()
    def invalid_filters_and_updates(self):
        for path in [
            "/api/browse/person?bad=1",
            "/api/browse/person?identifier=x",
            "/api/browse/person?time=1&time=2",
        ]:
            reply = self.http.get(path, headers=self.api.headers)
            assert b"<error>" in reply.data
        with pytest.raises(ValueError):
            self.api.person_register(identifier=1, locale="", user_agent="")
        with pytest.raises(ValueError):
            self.api.call("POST", "/api/adjust/person", {}, "person")
        if self.people:
            with pytest.raises(ValueError):
                self.api.person_adjust(1)
        if self.queries:
            with pytest.raises(ValueError):
                self.api.query_adjust(1, person=999999)

    @invariant()
    def compare_tables_and_report(self):
        assert self.api.person_browse() == list(self.people.values())
        for identifier, person in self.people.items():
            assert self.api.person_browse(identifier=identifier) == [person]
            expected = [
                q for q in self.queries.values() if q["person"] == identifier
            ]
            assert self.api.query_browse(identifier) == expected
        pairs = {
            (self.people[q["person"]]["locale"], q["content"])
            for q in self.queries.values()
            if q["time"] > NOW - 540
        }
        assert self.api.report_browse() == [
            dict(locale=locale, content=content)
            for locale, content in sorted(pairs)
        ]
        assert self.api.result_browse(999999) == []

    def teardown(self):
        self.app.extensions["jobs"].close()
        self.folder.cleanup()


TestMemory = ApiMachine.TestCase
TestMemory.settings = settings(max_examples=30, stateful_step_count=35, deadline=None)
