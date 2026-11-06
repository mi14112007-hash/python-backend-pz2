"""HTTP client with table_action method names and injectable transport."""

import base64
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from src.app import HEADERS
from src.xmlio import encode, unpack


def network(method, url, data, headers):
    """Send an HTTP request and return status and response bytes."""
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=10) as reply:
            return reply.status, reply.read()
    except HTTPError as error:
        return error.code, error.read()


class ApiClient:
    """Use the same client in production and model-based tests."""

    def __init__(self, url="http://127.0.0.1:5005", transport=network):
        self.url = url.rstrip("/")
        self.transport = transport
        self.headers = {**HEADERS, "Content-Type": "text/xml"}

    def call(self, method, path, values=None, entity=None):
        """Encode parameters and reject HTTP or XML application errors."""
        data = None
        if entity:
            data = encode(entity, values)
        elif values:
            path += "?" + urlencode(values)
        status, body = self.transport(
            method, self.url + path, data, self.headers
        )
        if status != 200:
            raise ValueError(f"HTTP {status}: {body.decode('utf-8')}")
        return unpack(body)

    def person_register(self, **values):
        """Create a person."""
        return self.call("POST", "/api/register/person", values, "person")

    def person_browse(self, **values):
        """Find people by field values."""
        return self.call("GET", "/api/browse/person", values)

    def person_adjust(self, identifier, **changes):
        """Change the supplied person fields."""
        return self.call(
            "POST",
            "/api/adjust/person",
            dict(identifier=identifier, **changes),
            "person",
        )

    def query_register(self, **values):
        """Create and schedule a query whose content is base64."""
        return self.call("POST", "/api/register/query", values, "query")

    def query_browse(self, person, **values):
        """Find queries belonging to a person."""
        return self.call("GET", f"/api/browse/query/{person}", values)

    def query_adjust(self, identifier, **changes):
        """Edit query metadata without rerunning a submitted task."""
        return self.call(
            "POST",
            "/api/adjust/query",
            dict(identifier=identifier, **changes),
            "query",
        )

    def result_browse(self, query, **values):
        """Read execution state and base64-encoded Bzip2 output."""
        return self.call("GET", f"/api/browse/result/{query}", values)

    def report_browse(self):
        """Read distinct locale/content pairs for the last nine minutes."""
        return self.call("GET", "/api/browse/report")

    def submit_file(self, person, path):
        """Read a local binary file and submit it as an XML-safe string."""
        content = base64.b64encode(Path(path).read_bytes()).decode("ascii")
        return self.query_register(person=person, content=content)
