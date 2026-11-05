"""Add sample open files to the local demo database, for the Open files tab.

    .venv/bin/python scripts/seed_open_files.py

Synthetic packages only. Writes to data/loanready.db, which git ignores.
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from loanready import agent, store  # noqa: E402

# Package, visit date. Spread out so some follow-ups are already due.
SEED = [("pkg01", date(2026, 11, 4)), ("pkg05", date(2026, 10, 28)), ("pkg06", date(2026, 11, 2)),
        ("pkg11", date(2026, 11, 3)), ("pkg20", date(2026, 11, 4))]


def main():
    for package, visit in SEED:
        store.save_review(agent.review(package, visit), visit)
    print(f"added {len(SEED)} open files to {store.DB_PATH}")


if __name__ == "__main__":
    main()
