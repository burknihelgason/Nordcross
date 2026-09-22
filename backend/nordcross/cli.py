import argparse

from nordcross.db.models import Base
from nordcross.db.seed import seed_reference_data
from nordcross.db.session import get_engine


def init_db() -> None:
    Base.metadata.create_all(get_engine())
    seed_reference_data()
    print("Database schema created and reference data seeded.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="nordcross")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-db", help="Create tables and seed reference data")

    args = parser.parse_args()
    if args.command == "init-db":
        init_db()


if __name__ == "__main__":
    main()
