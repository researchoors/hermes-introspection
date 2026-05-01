"""Computes metrics from session transcripts."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from datetime import datetime
from typing import Any

from .models import Outcome, SessionData, SessionMetrics


# Tool name classification
READ_TOOLS = {
    "read_file", "search_files", "search_files", "glob", "ls", "list_directory",
    "view", "cat", "head", "tail", "less", "more", "find", "which",
    "mcp_linear_get_issue", "mcp_linear_list_issues", "mcp_linear_list_teams",
    "mcp_linear_list_projects", "mcp_linear_search_issues",
    "mcp_linear_list_resources", "mcp_linear_read_resource",
    "process_poll", "process_log",
}

WRITE_TOOLS = {
    "write_file", "patch", "terminal", "bash", "shell", "exec",
    "mcp_linear_create_issue", "mcp_linear_update_issue",
    "process_submit", "process_write", "process_kill", "process_close",
}

# User message patterns that indicate human correction/guidance
CORRECTION_PATTERNS = [
    re.compile(r"\bno\b", re.IGNORECASE),
    re.compile(r"\bwrong\b", re.IGNORECASE),
    re.compile(r"\btry again\b", re.IGNORECASE),
    re.compile(r"\bthat'?s not\b", re.IGNORECASE),
    re.compile(r"\bstop\b", re.IGNORECASE),
    re.compile(r"\bread the error\b", re.IGNORECASE),
    re.compile(r"\bdon'?t do that\b", re.IGNORECASE),
    re.compile(r"\bnot what i (asked|wanted|meant)\b", re.IGNORECASE),
    re.compile(r"\byou (messed|screwed) up\b", re.IGNORECASE),
    re.compile(r"\bfix (that|it|this)\b", re.IGNORECASE),
    re.compile(r"\bincorrect\b", re.IGNORECASE),
    re.compile(r"\bdidn'?t work\b", re.IGNORECASE),
    re.compile(r"\bstill (failing|broken|wrong)\b", re.IGNORECASE),
    re.compile(r"\blook (at|again|more carefully)\b", re.IGNORECASE),
    re.compile(r"\bpay attention\b", re.IGNORECASE),
    re.compile(r"\bre-read\b", re.IGNORECASE),
    re.compile(r"\bcheck (again|the|your)\b", re.IGNORECASE),
    re.compile(r"\bthis is wrong\b", re.IGNORECASE),
]

# Error fingerprint patterns — extract the core error type, ignore variable parts
ERROR_NORMALIZE_PATTERNS = [
    (re.compile(r"line \d+"), "line N"),
    (re.compile(r"/[\w./\-]+\.py"), "/path/to/file.py"),
    (re.compile(r"/[\w./\-]+\.js"), "/path/to/file.js"),
    (re.compile(r"/[\w./\-]+\.ts"), "/path/to/file.ts"),
    (re.compile(r"0x[0-9a-fA-F]+"), "0xADDR"),
    (re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}"), "TIMESTAMP"),
    (re.compile(r"Error:.*"), "Error"),
]


def _normalize_error(content: str) -> str:
    """Normalize an error message for fingerprinting. Removes variable parts."""
    normalized = content
    for pattern, replacement in ERROR_NORMALIZE_PATTERNS:
        normalized = pattern.sub(replacement, normalized)
    # Take first 200 chars for fingerprinting
    return normalized[:200]


def _error_fingerprint(content: str) -> str:
    """Create a hash fingerprint of a normalized error message."""
    normalized = _normalize_error(content)
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


class MetricsComputer:
    """Computes session metrics from parsed session data."""

    def compute(self, session: SessionData) -> SessionMetrics:
        """Compute all metrics for a single session."""
        tool_call_count = self._compute_tool_call_count(session)
        iterations_to_success = self._compute_iterations_to_success(session)
        human_intervention_count = self._compute_human_intervention_count(session)
        error_repeat_count = self._compute_error_repeat_count(session)
        info_seeking_ratio = self._compute_information_seeking_ratio(session)
        wall_time = self._compute_wall_time(session)
        outcome = self._compute_outcome(session)

        return SessionMetrics(
            session_id=session.session_id,
            timestamp=session.start_time,
            tool_call_count=tool_call_count,
            iterations_to_success=iterations_to_success,
            human_intervention_count=human_intervention_count,
            error_repeat_count=error_repeat_count,
            information_seeking_ratio=info_seeking_ratio,
            wall_time_seconds=wall_time,
            outcome=outcome,
        )

    def _compute_tool_call_count(self, session: SessionData) -> int:
        """Count total tool calls made across all assistant messages."""
        count = 0
        for msg in session.messages:
            if msg.role == "assistant" and msg.tool_calls:
                count += len(msg.tool_calls)
            # Also count tool role messages as indicators of tool use
        return count

    def _compute_iterations_to_success(self, session: SessionData) -> int:
        """Count iterations (rounds of tool calls) until task completion.

        An iteration is a round of one or more tool calls followed by their results.
        The last iteration before the final assistant message (without tool calls)
        or session end counts.
        """
        iterations = 0
        in_tool_round = False

        for msg in session.messages:
            if msg.role == "assistant" and msg.tool_calls:
                if not in_tool_round:
                    iterations += 1
                    in_tool_round = True
            elif msg.role == "tool":
                # Continue current iteration
                pass
            elif msg.role == "user":
                # User message ends the current tool round
                in_tool_round = False

        return iterations

    def _compute_human_intervention_count(self, session: SessionData) -> int:
        """Count user messages that correct or guide the agent."""
        count = 0
        for msg in session.messages:
            if msg.role != "user":
                continue
            content = msg.content
            if not content:
                continue
            for pattern in CORRECTION_PATTERNS:
                if pattern.search(content):
                    count += 1
                    break  # One match per message is enough
        return count

    def _compute_error_repeat_count(self, session: SessionData) -> int:
        """Count repeated error patterns across iterations.

        Fingerprints error messages and counts how many times the same
        fingerprint appears more than once.
        """
        fingerprints: list[str] = []
        for msg in session.messages:
            if msg.role == "tool" and msg.is_error and msg.content:
                fp = _error_fingerprint(msg.content)
                fingerprints.append(fp)

        if not fingerprints:
            return 0

        counter = Counter(fingerprints)
        # Count total repeats: for each fingerprint with count > 1, add (count - 1)
        repeats = sum(count - 1 for count in counter.values() if count > 1)
        return repeats

    def _compute_information_seeking_ratio(self, session: SessionData) -> float:
        """Compute ratio of read/search/view tool calls vs write/patch/terminal calls
        after a failure.

        If there are no write-class calls after failure, returns 1.0 (all info-seeking).
        If there are no info-seeking calls after failure, returns 0.0.
        """
        # First, identify positions of failures (error tool results)
        failure_positions: set[int] = set()
        for i, msg in enumerate(session.messages):
            if msg.role == "tool" and msg.is_error:
                failure_positions.add(i)

        if not failure_positions:
            return 0.0

        # Collect tool calls that occur after any failure
        info_seeking = 0
        writing = 0

        for i, msg in enumerate(session.messages):
            if msg.role != "assistant" or not msg.tool_calls:
                continue
            # Check if this tool call round is after a failure
            # Look backwards for the nearest preceding failure
            has_prior_failure = any(fp < i for fp in failure_positions)
            if not has_prior_failure:
                continue

            for tc in msg.tool_calls:
                name = tc.name.lower()
                if name in READ_TOOLS or any(r in name for r in ["read", "search", "view", "list", "get"]):
                    info_seeking += 1
                elif name in WRITE_TOOLS or any(w in name for w in ["write", "patch", "terminal", "bash", "exec", "create", "update"]):
                    writing += 1

        total = info_seeking + writing
        if total == 0:
            return 0.0
        return info_seeking / total

    def _compute_wall_time(self, session: SessionData) -> float:
        """Compute total session duration in seconds."""
        if not session.start_time or not session.end_time:
            # Try to compute from message timestamps
            timestamps = []
            for msg in session.messages:
                if msg.timestamp:
                    timestamps.append(msg.timestamp)
            if len(timestamps) < 2:
                return 0.0
            timestamps.sort()
            start = timestamps[0]
            end = timestamps[-1]

        else:
            start = session.start_time
            end = session.end_time

        try:
            # Parse ISO timestamps
            start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
            return (end_dt - start_dt).total_seconds()
        except (ValueError, AttributeError):
            return 0.0

    def _compute_outcome(self, session: SessionData) -> str:
        """Determine session outcome.

        - 'completed': last assistant message has no tool calls (just a final answer)
        - 'abandoned': last message is from user (no assistant response)
        - 'in_progress': ends with tool calls or tool results (agent was mid-work)
        """
        if not session.messages:
            return Outcome.IN_PROGRESS.value

        # Look at the last few messages to determine outcome
        last_msg = session.messages[-1]

        if last_msg.role == "assistant":
            if last_msg.tool_calls:
                # Assistant was about to make tool calls — in progress
                return Outcome.IN_PROGRESS.value
            # Assistant gave a final text response — completed
            return Outcome.COMPLETED.value

        if last_msg.role == "tool":
            # Last message is a tool result — in progress
            return Outcome.IN_PROGRESS.value

        if last_msg.role == "user":
            # Last message is from user
            # If there's only one message (just the prompt), it's in progress
            # If user came back to correct, check if there was prior assistant activity
            assistant_msgs = [m for m in session.messages if m.role == "assistant"]
            if not assistant_msgs:
                return Outcome.IN_PROGRESS.value
            # User sent a correction but agent never responded — abandoned
            return Outcome.ABANDONED.value

        return Outcome.IN_PROGRESS.value