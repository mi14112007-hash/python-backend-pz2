"""Background compression through the previously implemented CLI."""

import base64
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic, time

CLI_PATH = Path(__file__).with_name("compress.py")
TIMEOUT_SECONDS = 30
MILLISECONDS = 1000


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
