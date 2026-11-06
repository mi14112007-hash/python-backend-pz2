"""Property-based verification of the standalone Bzip2 utility."""

import bz2
import io
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from hypothesis import given, settings
from hypothesis import strategies as st

from src.compress import compress_file


@given(st.binary(max_size=10000))
@settings(max_examples=20, deadline=None)
def test_cli_roundtrip(data):
    with TemporaryDirectory() as folder:
        source = Path(folder) / "source"
        source.write_bytes(data)
        output = io.BytesIO()
        compress_file(source, output)
        assert bz2.decompress(output.getvalue()) == data
        process = subprocess.run(
            [sys.executable, "-m", "src.compress", str(source)],
            capture_output=True,
            check=True,
        )
        assert process.stdout == output.getvalue()
        missing = subprocess.run(
            [sys.executable, "-m", "src.compress", str(source) + ".missing"],
            capture_output=True,
        )
        assert missing.returncode != 0 and missing.stderr
        assert missing.stdout == b""
