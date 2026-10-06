"""`chesscoach-serve`: run the web app."""

from __future__ import annotations

import argparse

import uvicorn

from .api import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Chess Varsity web app")
    parser.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 to accept outside connections")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
