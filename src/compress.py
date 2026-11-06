"""Compress an input file and write Bzip2 bytes to standard output."""

import argparse
import bz2
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


if __name__ == "__main__":
    main()
