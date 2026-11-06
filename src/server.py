"""Server entry point and command-line configuration."""

import argparse
import atexit

from src.app import create_app
from src.database import SQLiteStore


def main():
    """Start a local server with an explicitly selected persistence mode."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--backend", choices=["memory", "sqlite"], default="sqlite"
    )
    parser.add_argument("--database", default="data.sqlite")
    parser.add_argument("--port", type=int, default=5005)
    parser.add_argument("--fake", action="store_true")
    args = parser.parse_args()
    store = SQLiteStore(args.database) if args.backend == "sqlite" else None
    app = create_app(store, args.fake)
    atexit.register(app.extensions["jobs"].close)
    app.run(host="127.0.0.1", port=args.port, use_reloader=False)


if __name__ == "__main__":
    main()
