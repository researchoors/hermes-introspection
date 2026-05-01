"""Generates daily reports with deltas from historical data."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import DailyReport, Outcome, SessionMetrics


# Default path for metrics data within the repo
DEFAULT_DATA_DIR = Path(__file__).parent.parent / "data" / "metrics"


class Reporter:
    """Generates and writes daily metric reports."""

    def __init__(self, data_dir: str | Path | None = None, repo_path: str | Path | None = None):
        if data_dir is not None:
            self.data_dir = Path(data_dir)
        elif repo_path is not None:
            self.data_dir = Path(repo_path) / "data" / "metrics"
        else:
            # Walk up from this file to find repo root (looks for .git)
            current = Path(__file__).resolve().parent
            while current != current.parent:
                if (current / ".git").exists():
                    self.data_dir = current / "data" / "metrics"
                    break
                current = current.parent
            else:
                self.data_dir = DEFAULT_DATA_DIR

        self.data_dir.mkdir(parents=True, exist_ok=True)

    def generate_report(self, metrics: list[SessionMetrics], date: str | None = None) -> DailyReport:
        """Generate a DailyReport from a list of session metrics."""
        if date is None:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        if not metrics:
            return DailyReport(
                date=date,
                session_count=0,
                outcomes={o.value: 0 for o in Outcome},
            )

        outcomes: dict[str, int] = {o.value: 0 for o in Outcome}
        for m in metrics:
            outcomes[m.outcome] = outcomes.get(m.outcome, 0) + 1

        total_tool_calls = sum(m.tool_call_count for m in metrics)
        completed = [m for m in metrics if m.outcome == Outcome.COMPLETED.value]
        avg_iterations = (
            sum(m.iterations_to_success for m in completed) / len(completed)
            if completed else 0.0
        )
        total_interventions = sum(m.human_intervention_count for m in metrics)
        total_repeats = sum(m.error_repeat_count for m in metrics)
        avg_info_ratio = (
            sum(m.information_seeking_ratio for m in metrics) / len(metrics)
            if metrics else 0.0
        )
        avg_wall_time = (
            sum(m.wall_time_seconds for m in metrics) / len(metrics)
            if metrics else 0.0
        )

        return DailyReport(
            date=date,
            session_count=len(metrics),
            total_tool_calls=total_tool_calls,
            avg_iterations_to_success=avg_iterations,
            total_human_interventions=total_interventions,
            total_error_repeats=total_repeats,
            avg_information_seeking_ratio=avg_info_ratio,
            avg_wall_time_seconds=avg_wall_time,
            outcomes=outcomes,
            sessions=metrics,
        )

    def write_daily(self, metrics: list[SessionMetrics], date: str | None = None) -> Path:
        """Write daily metrics to JSON file and return the path."""
        report = self.generate_report(metrics, date)
        date = report.date
        filepath = self.data_dir / f"{date}.json"

        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w") as f:
            f.write(report.to_json())

        return filepath

    def read_daily(self, date: str) -> DailyReport | None:
        """Read a daily report from JSON file."""
        filepath = self.data_dir / f"{date}.json"
        if not filepath.exists():
            return None

        with open(filepath, "r") as f:
            data = json.load(f)

        sessions = [SessionMetrics(**s) for s in data.get("sessions", [])]
        return DailyReport(
            date=data["date"],
            session_count=data["session_count"],
            total_tool_calls=data["total_tool_calls"],
            avg_iterations_to_success=data["avg_iterations_to_success"],
            total_human_interventions=data["total_human_interventions"],
            total_error_repeats=data["total_error_repeats"],
            avg_information_seeking_ratio=data["avg_information_seeking_ratio"],
            avg_wall_time_seconds=data["avg_wall_time_seconds"],
            outcomes=data.get("outcomes", {}),
            sessions=sessions,
        )

    def compute_deltas(self, current: DailyReport, previous: DailyReport) -> dict[str, float]:
        """Compute delta changes between two daily reports."""
        deltas: dict[str, float] = {}
        fields = [
            "session_count", "total_tool_calls", "avg_iterations_to_success",
            "total_human_interventions", "total_error_repeats",
            "avg_information_seeking_ratio", "avg_wall_time_seconds",
        ]
        for field in fields:
            curr_val = getattr(current, field)
            prev_val = getattr(previous, field)
            if prev_val != 0:
                deltas[field] = ((curr_val - prev_val) / prev_val) * 100  # % change
            elif curr_val != 0:
                deltas[field] = float("inf")
            else:
                deltas[field] = 0.0
        return deltas

    def git_commit_and_push(self, filepath: Path, message: str | None = None) -> bool:
        """Git add, commit, and push a metrics file."""
        if message is None:
            message = f" Automated metrics update: {filepath.name}"

        repo_root = self._find_repo_root()
        if repo_root is None:
            print("Warning: Could not find git repo root. Skipping git operations.")
            return False

        try:
            # Stage the file
            subprocess.run(
                ["git", "add", str(filepath)],
                cwd=repo_root,
                check=True,
                capture_output=True,
            )
            # Commit with GPG signing
            subprocess.run(
                ["git", "commit", "-S", "-m", message],
                cwd=repo_root,
                check=True,
                capture_output=True,
            )
            # Push
            subprocess.run(
                ["git", "push"],
                cwd=repo_root,
                check=True,
                capture_output=True,
            )
            return True
        except subprocess.CalledProcessError as e:
            print(f"Git operation failed: {e}")
            print(f"stderr: {e.stderr.decode() if e.stderr else 'N/A'}")
            return False

    def _find_repo_root(self) -> Path | None:
        """Find the git repo root from the data directory."""
        current = self.data_dir
        while current != current.parent:
            if (current / ".git").exists():
                return current
            current = current.parent
        return None