"""Compress input files to Bzip2 stdout and demonstrate four examples."""

import argparse
import bz2
import subprocess
import sys
from pathlib import Path

CHUNK_SIZE = 65536


def compress_file(path, output):
    """Read a file in chunks without loading its entire contents."""
    compressor = bz2.BZ2Compressor()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(CHUNK_SIZE), b""):
            output.write(compressor.compress(chunk))
    output.write(compressor.flush())


def main():
    """Parse the input path and keep diagnostics outside binary stdout."""
    parser = argparse.ArgumentParser(description="Compress a file to Bzip2")
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    try:
        compress_file(args.input, sys.stdout.buffer)
    except OSError as error:
        parser.exit(1, f"{error}\n")


def examples():
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
