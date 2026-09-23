import argparse

from nordcross.db.models import Base
from nordcross.db.seed import seed_reference_data
from nordcross.db.session import get_engine
from nordcross.ingest import store_championship_results
from nordcross.lookup_queue import queue_summary, seed_lookup_queue
from nordcross.lookup_runner import run_tilastopaja, run_worldathletics
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
    sub.add_parser("seed-lookup-queue", help="Queue athletes for external progression lookup")
    sub.add_parser("lookup-status", help="Show external lookup queue counts by source/status")
    lookup_run_parser = sub.add_parser("lookup-run", help="Process a small batch of the lookup queue")
    lookup_run_parser.add_argument("source", choices=["tilastopaja", "worldathletics"])
    lookup_run_parser.add_argument("--limit", type=int, default=5)
    lookup_run_parser.add_argument("--headed", action="store_true", help="Show the browser window")

    args = parser.parse_args()
    if args.command == "init-db":
        init_db()
    elif args.command == "ingest":
        ingest(args.year)
    elif args.command == "match-athletes":
        match_athletes()
        print("Matched athletes.")
    elif args.command == "seed-lookup-queue":
        created = seed_lookup_queue()
        print(f"Queued {created} new athlete/source lookups.")
    elif args.command == "lookup-status":
        for (source, status), count in sorted(queue_summary().items()):
            print(f"  {source:15s} {status:10s} {count}")
    elif args.command == "lookup-run":
        runner = run_tilastopaja if args.source == "tilastopaja" else run_worldathletics
        runner(limit=args.limit, headless=not args.headed)


if __name__ == "__main__":
    main()
