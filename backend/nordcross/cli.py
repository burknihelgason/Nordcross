import argparse

from nordcross.db.models import Base
from nordcross.db.seed import seed_reference_data
from nordcross.db.session import get_engine
from nordcross.ingest import store_championship_results
from nordcross.matching import match_athletes
from nordcross.sources import SOURCES


def init_db() -> None:
    Base.metadata.create_all(get_engine())
    seed_reference_data()
    print("Database schema created and reference data seeded.")


def ingest(year: int) -> None:
    source = SOURCES[year]
    print(f"Scraping {year} from {source['url']} ...")
    scraped = source["scraper"](source["url"])
    for category_code, (race, results) in scraped.items():
        print(f"  {category_code}: {len(results)} results ({race.name})")
    store_championship_results(year=year, name=source["name"], source_url=source["url"], scraped=scraped)
    print(f"Stored {year} results.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="nordcross")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-db", help="Create tables and seed reference data")
    ingest_parser = sub.add_parser("ingest", help="Scrape and store one year's results")
    ingest_parser.add_argument("year", type=int, choices=sorted(SOURCES.keys()))
    sub.add_parser("match-athletes", help="Group results into athlete identities")

    args = parser.parse_args()
    if args.command == "init-db":
        init_db()
    elif args.command == "ingest":
        ingest(args.year)
    elif args.command == "match-athletes":
        match_athletes()
        print("Matched athletes.")


if __name__ == "__main__":
    main()
