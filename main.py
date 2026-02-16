"""
Railway entry point for the AI Intelligence System.
Runs the daily pipeline once, then exits. Railway cron handles scheduling.
"""

import os
import sys
from datetime import datetime

# Add tools/ to path so imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "tools"))

from orchestrator import Orchestrator


def main():
    start = datetime.now()
    print(f"[{start.strftime('%Y-%m-%d %H:%M:%S')}] Daily pipeline starting...")

    try:
        orchestrator = Orchestrator()
        orchestrator.run_daily_pipeline()
        end = datetime.now()
        duration = (end - start).total_seconds()
        print(f"\n[{end.strftime('%Y-%m-%d %H:%M:%S')}] Pipeline completed in {duration:.0f}s")
    except Exception as e:
        print(f"\n[ERROR] Pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
