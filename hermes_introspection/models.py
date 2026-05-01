"""Data classes for session metrics."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class Outcome(str, Enum):
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    IN_PROGRESS = "in_progress"


@dataclass
class ToolCallInfo:
    """Parsed tool call from an assistant message."""
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    tool_call_id: str = ""


@dataclass
class SessionMessage:
    """A single message in a session transcript."""
    role: str
    content: str
    timestamp: str = ""
    tool_calls: list[ToolCallInfo] = field(default_factory=list)
    tool_call_id: str = ""
    tool_name: str = ""
    is_error: bool = False
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionData:
    """Parsed session data from a JSONL file."""
    session_id: str
    filepath: str
    messages: list[SessionMessage] = field(default_factory=list)
    start_time: str = ""
    end_time: str = ""


@dataclass
class SessionMetrics:
    """Computed metrics for a single session."""
    session_id: str
    timestamp: str
    tool_call_count: int = 0
    iterations_to_success: int = 0
    human_intervention_count: int = 0
    error_repeat_count: int = 0
    information_seeking_ratio: float = 0.0
    wall_time_seconds: float = 0.0
    outcome: str = Outcome.IN_PROGRESS.value

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)


@dataclass
class DailyReport:
    """Aggregated daily report across all sessions."""
    date: str
    session_count: int = 0
    total_tool_calls: int = 0
    avg_iterations_to_success: float = 0.0
    total_human_interventions: int = 0
    total_error_repeats: int = 0
    avg_information_seeking_ratio: float = 0.0
    avg_wall_time_seconds: float = 0.0
    outcomes: dict[str, int] = field(default_factory=dict)
    sessions: list[SessionMetrics] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["sessions"] = [s.to_dict() if isinstance(s, SessionMetrics) else s for s in self.sessions]
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)