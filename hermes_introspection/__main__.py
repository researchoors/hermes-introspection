"""CLI entry point: python -m hermes_introspection"""

from .collector import SessionCollector
from .metrics import MetricsComputer
from .reporter import Reporter


def main() -> None:
    """Run the full introspection pipeline: collect → compute → report."""
    print("=== Hermes Introspection ===")
    print()

    # 1. Collect sessions
    print("Collecting sessions...")
    collector = SessionCollector()
    sessions = collector.collect()
    print(f"  Found {len(sessions)} session(s)")

    if not sessions:
        print("  No sessions found. Nothing to do.")
        return

    # 2. Compute metrics
    print("Computing metrics...")
    computer = MetricsComputer()
    metrics = []
    for session in sessions:
        m = computer.compute(session)
        metrics.append(m)
        print(f"  {m.session_id}: {m.tool_call_count} tool calls, "
              f"{m.iterations_to_success} iterations, "
              f"outcome={m.outcome}")

    # 3. Generate and write daily report
    print("Writing daily report...")
    reporter = Reporter()
    filepath = reporter.write_daily(metrics)
    print(f"  Written to {filepath}")

    # 4. Compute deltas if previous day's data exists
    from datetime import datetime, timedelta, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    previous = reporter.read_daily(yesterday)
    if previous:
        current = reporter.generate_report(metrics, today)
        deltas = reporter.compute_deltas(current, previous)
        print("  Day-over-day deltas:")
        for field, delta in deltas.items():
            direction = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
            print(f"    {field}: {direction} {delta:+.1f}%")
    else:
        print("  No previous day data for delta comparison.")

    # 5. Git commit and push
    print("Committing and pushing...")
    success = reporter.git_commit_and_push(filepath)
    if success:
        print("  Pushed to remote.")
    else:
        print("  Git push skipped or failed.")

    print()
    print("Done.")


if __name__ == "__main__":
    main()
