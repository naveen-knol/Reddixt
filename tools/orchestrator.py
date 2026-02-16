"""
Orchestrator for the AI Intelligence System.
Coordinates the full pipeline: collect -> process -> score -> brief -> export -> email.
CLI interface for running individual phases, full pipeline, or daily automated run.
"""

import argparse
import sys
from datetime import datetime

from database import Database
from reddit_collector import collect_all
from llm_processor import process_batch
from scoring_engine import run_scoring
from briefing_generator import generate_briefing
from excel_exporter import export_to_excel
from email_sender import send_daily_report


class Orchestrator:
    def __init__(self):
        # Seed defaults then close — don't hold the connection during pipeline runs
        db = Database()
        db.seed_defaults()
        db.close()

    def collect(self, limit=100, sort="hot", max_age_hours=None):
        print("\n=== Phase 1: Collection ===")
        return collect_all(limit=limit, sort=sort, max_age_hours=max_age_hours)

    def process(self, batch_size=50):
        print("\n=== Phase 2: LLM Processing ===")
        return process_batch(batch_size=batch_size)

    def score(self, days=7):
        print("\n=== Phase 3: Scoring & Clustering ===")
        return run_scoring(days=days)

    def brief(self):
        print("\n=== Phase 4: Briefing Generation ===")
        return generate_briefing()

    def export(self):
        print("\n=== Phase 5: Excel Export ===")
        return export_to_excel()

    def email(self, briefing_path=None, excel_path=None):
        print("\n=== Phase 6: Email Delivery ===")
        return send_daily_report(briefing_path=briefing_path, excel_path=excel_path)

    def run_full_pipeline(self, limit=100, batch_size=50, days=7):
        print(f"{'='*60}")
        print(f"  AI Intelligence System -- Full Pipeline")
        print(f"  Started at: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"{'='*60}")

        collected = self.collect(limit=limit)
        if collected == 0:
            print("\nNo new posts collected. Pipeline may still process existing data.")

        processed = self.process(batch_size=batch_size)
        ideas = self.score(days=days)
        briefing_path = self.brief()

        print(f"\n{'='*60}")
        print(f"  Pipeline Complete")
        print(f"  Posts collected: {collected}")
        print(f"  Insights extracted: {processed}")
        print(f"  Ideas created: {ideas}")
        if briefing_path:
            print(f"  Briefing: {briefing_path}")
        print(f"{'='*60}")

    def run_weekly_pipeline(self, limit=100, batch_size=100):
        """Weekly automated run: collect last 7 days -> process -> score -> brief -> export -> email."""
        print(f"{'='*60}")
        print(f"  AI Intelligence System -- Weekly Pipeline")
        print(f"  Started at: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"{'='*60}")

        # Collect posts from the last 7 days
        collected = self.collect(limit=limit, sort="new", max_age_hours=168)
        if collected == 0:
            print("\nNo new posts in the last 7 days. Skipping remaining phases.")
            return

        processed = self.process(batch_size=batch_size)
        ideas = self.score(days=7)
        briefing_path = self.brief()
        excel_path = self.export()
        email_sent = self.email(briefing_path=briefing_path, excel_path=excel_path)

        print(f"\n{'='*60}")
        print(f"  Weekly Pipeline Complete")
        print(f"  Posts collected (7 days): {collected}")
        print(f"  Insights extracted: {processed}")
        print(f"  Ideas created: {ideas}")
        if briefing_path:
            print(f"  Briefing: {briefing_path}")
        if excel_path:
            print(f"  Excel: {excel_path}")
        print(f"  Email: {'sent' if email_sent else 'FAILED'}")
        print(f"{'='*60}")

    def status(self):
        db = Database()
        stats = db.get_stats()
        sources = db.get_sources()
        db.close()

        print(f"\n{'='*60}")
        print(f"  AI Intelligence System -- Status")
        print(f"{'='*60}")
        print(f"\n  Database Counts:")
        print(f"    Sources:      {stats['sources']}")
        print(f"    Content:      {stats['content']} ({stats['unprocessed_content']} unprocessed)")
        print(f"    Insights:     {stats['insights']}")
        print(f"    Ideas:        {stats['ideas']}")
        print(f"    Feedback:     {stats['feedback']}")
        print(f"    Predictions:  {stats['predictions']}")

        print(f"\n  Tracked Subreddits:")
        for src in sources:
            last = src["last_collected_at"] or "never"
            print(f"    {src['name']:30s} authority: {src['authority_score']:.1f}  last collected: {last}")

        print()


def main():
    parser = argparse.ArgumentParser(
        description="AI Intelligence System -- Pipeline Orchestrator"
    )
    subparsers = parser.add_subparsers(dest="command", help="Pipeline phase to run")

    # Full pipeline
    full_parser = subparsers.add_parser("full", help="Run the complete pipeline")
    full_parser.add_argument("--limit", type=int, default=100, help="Posts per subreddit (default: 100)")
    full_parser.add_argument("--batch", type=int, default=50, help="LLM processing batch size (default: 50)")
    full_parser.add_argument("--days", type=int, default=7, help="Days back for scoring (default: 7)")

    # Weekly pipeline
    weekly_parser = subparsers.add_parser("weekly", help="Run weekly pipeline (7-day collection + email with Excel)")
    weekly_parser.add_argument("--limit", type=int, default=100, help="Posts per subreddit (default: 100)")
    weekly_parser.add_argument("--batch", type=int, default=100, help="LLM processing batch size (default: 100)")

    # Individual phases
    collect_parser = subparsers.add_parser("collect", help="Collect posts from Reddit")
    collect_parser.add_argument("--limit", type=int, default=100, help="Posts per subreddit")

    process_parser = subparsers.add_parser("process", help="Process content through Claude")
    process_parser.add_argument("--batch", type=int, default=50, help="Batch size")

    score_parser = subparsers.add_parser("score", help="Score and cluster insights")
    score_parser.add_argument("--days", type=int, default=7, help="Days back")

    subparsers.add_parser("brief", help="Generate briefing report")
    subparsers.add_parser("export", help="Export findings to Excel")
    subparsers.add_parser("status", help="Show system status")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    orchestrator = Orchestrator()

    if args.command == "full":
        orchestrator.run_full_pipeline(
            limit=args.limit, batch_size=args.batch, days=args.days
        )
    elif args.command == "weekly":
        orchestrator.run_weekly_pipeline(
            limit=args.limit, batch_size=args.batch
        )
    elif args.command == "collect":
        orchestrator.collect(limit=args.limit)
    elif args.command == "process":
        orchestrator.process(batch_size=args.batch)
    elif args.command == "score":
        orchestrator.score(days=args.days)
    elif args.command == "brief":
        orchestrator.brief()
    elif args.command == "export":
        orchestrator.export()
    elif args.command == "status":
        orchestrator.status()


if __name__ == "__main__":
    main()
