"""Run the CLI on four reproducible files and verify decompression."""

import bz2
import subprocess
import sys
from pathlib import Path


def main():
    """Create output artifacts outside version control."""
    destination = Path("results")
    destination.mkdir(exist_ok=True)
    for source in sorted(Path("examples").iterdir()):
        process = subprocess.run(
            [sys.executable, "-m", "src.compress", str(source)],
            capture_output=True,
            check=True,
        )
        original = source.read_bytes()
        assert bz2.decompress(process.stdout) == original
        (destination / (source.name + ".bz2")).write_bytes(process.stdout)
        print(f"{source.name}: {len(original)} -> {len(process.stdout)} bytes")


if __name__ == "__main__":
    main()
