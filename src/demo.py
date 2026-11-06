"""Call all eight API handlers and save an asynchronously built archive."""

import base64
import bz2
from pathlib import Path
from time import monotonic, sleep

from src.client import ApiClient

POLL_SECONDS = 0.1
WAIT_SECONDS = 35


def display(label, data):
    """Print API records with binary payload lengths instead of Base64."""
    rows = data if isinstance(data, list) else [data]
    compact = [
        {
            key: f"{len(value)} Base64 characters"
            if key in {"content", "output"}
            else value
            for key, value in row.items()
        }
        for row in rows
    ]
    print(label, compact)


def main():
    """Submit a file, poll its status and verify restored contents."""
    api = ApiClient()
    person = api.person_register(locale="ru-RU", user_agent="demo")
    person_id = person["identifier"]
    display("person_browse:", api.person_browse(identifier=person_id))
    display(
        "person_adjust:",
        api.person_adjust(person_id, user_agent="Python client"),
    )
    source = Path("examples/text.txt")
    query = api.submit_file(person_id, source)
    query_id = query["identifier"]
    display("query_browse:", api.query_browse(person_id, identifier=query_id))
    display("query_adjust:", api.query_adjust(query_id, time=query["time"]))
    deadline = monotonic() + WAIT_SECONDS
    while monotonic() < deadline:
        result = api.result_browse(query_id)[0]
        if result["state"] in {"done", "failed"}:
            break
        sleep(POLL_SECONDS)
    else:
        raise TimeoutError("Compression did not finish")
    if result["state"] != "done":
        raise RuntimeError(result["failure"])
    archive = base64.b64decode(result["output"])
    assert bz2.decompress(archive) == source.read_bytes()
    Path("results").mkdir(exist_ok=True)
    Path("results/demo.bz2").write_bytes(archive)
    display("result_browse:", result)
    display("report_browse:", api.report_browse())
    print("Saved results/demo.bz2; decompression verified")


if __name__ == "__main__":
    main()
