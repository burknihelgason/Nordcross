import argparse
import datetime

from nordcross.db.models import Base
from nordcross.db.seed import seed_reference_data
from nordcross.db.session import get_engine
from nordcross.ingest import store_championship_results
from nordcross.lookup_queue import export_for_review, queue_summary, resolve_manually, seed_lookup_queue
from nordcross.lookup_runner import run_tilastopaja, run_worldathletics
from nordcross.matching import match_athletes
from nordcross.progression_matching import add_manual_progression, match_wa_points
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
    store_championship_results(
        year=year, name=source["name"], source_url=source["url"], scraped=scraped, date=source.get("date"),
    )
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

    export_parser = sub.add_parser("lookup-export", help="Export ambiguous/not-found lookups to CSV for manual review")
    export_parser.add_argument("source", choices=["tilastopaja", "worldathletics"])
    export_parser.add_argument("--out", default="lookup_review.csv")
    export_parser.add_argument("--status", default="ambiguous,not_found", help="Comma-separated statuses to include")

    resolve_parser = sub.add_parser("lookup-resolve", help="Feed back a manually-found profile for one athlete")
    resolve_parser.add_argument("athlete_id", type=int)
    resolve_parser.add_argument("source", choices=["tilastopaja", "worldathletics"])
    resolve_parser.add_argument("url_or_id", help="Full profile URL (worldathletics) or numeric athleteId (tilastopaja)")

    add_prog_parser = sub.add_parser("add-progression", help="Manually record a PR a human found by hand")
    add_prog_parser.add_argument("athlete_id", type=int)
    add_prog_parser.add_argument("event_code", help="e.g. 800m, 5000m, 10km_road, HM, Marathon")
    add_prog_parser.add_argument("mark", help="e.g. 14:32.10")
    add_prog_parser.add_argument("date", help="YYYY-MM-DD")
    add_prog_parser.add_argument("--venue", default=None)

    sub.add_parser("match-progression", help="Step 3: set each result's wa_points from progression before its race date")

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
    elif args.command == "lookup-export":
        statuses = tuple(s.strip() for s in args.status.split(","))
        count = export_for_review(args.source, args.out, statuses)
        print(f"Wrote {count} row(s) to {args.out}")
    elif args.command == "lookup-resolve":
        resolve_manually(args.athlete_id, args.source, args.url_or_id)
        print(f"Athlete {args.athlete_id} ({args.source}) queued for re-fetch using the provided profile.")
    elif args.command == "add-progression":
        date = datetime.datetime.strptime(args.date, "%Y-%m-%d").date()
        add_manual_progression(args.athlete_id, args.event_code, args.mark, date, args.venue)
        print(f"Recorded {args.mark} ({args.event_code}, {date}) for athlete {args.athlete_id}.")
    elif args.command == "match-progression":
        stats = match_wa_points()
        print(f"Matched {stats['matched']} result(s) to a progression PR.")
        print(f"  {stats['no_progression_before_race']} result(s) had no qualifying progression before the race date.")
        print(f"  {stats['no_race_date']} result(s)' championship has no recorded date.")


if __name__ == "__main__":
    main()
