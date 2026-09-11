"""Consistent SQLite online backup; refuses to overwrite an existing destination."""

import argparse
import sqlite3
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    # Read-only source URI avoids silently creating an empty database on a typo.
    source = sqlite3.connect(args.source.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        with args.destination.open("xb"):
            pass
        destination = sqlite3.connect(args.destination)
        try:
            source.backup(destination)
            if destination.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Backup integrity check failed")
        finally:
            destination.close()
    finally:
        source.close()
    print("Backup created and integrity checked")


if __name__ == "__main__":
    main()
