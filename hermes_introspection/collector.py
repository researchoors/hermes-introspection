"""Reads Hermes session data from ~/.hermes/sessions/"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .models import SessionData, SessionMessage, ToolCallInfo


DEFAULT_SESSIONS_DIR = os.path.expanduser("~/.hermes/sessions")


class SessionCollector:
    """Collects and parses Hermes session JSONL files."""

    def __init__(self, sessions_dir: str | None = None):
        self.sessions_dir = Path(sessions_dir or DEFAULT_SESSIONS_DIR)

    def find_sessions(self) -> list[Path]:
        """Glob all session JSONL files."""
        if not self.sessions_dir.exists():
            return []
        return sorted(self.sessions_dir.glob("*.jsonl"))

    def collect(self) -> list[SessionData]:
        """Collect and parse all available sessions."""
        sessions = []
        for path in self.find_sessions():
            try:
                session = self._parse_session(path)
                if session is not None:
                    sessions.append(session)
            except Exception as e:
                print(f"Warning: Failed to parse {path}: {e}")
        return sessions

    def _parse_session(self, filepath: Path) -> SessionData | None:
        """Parse a single session JSONL file into SessionData."""
        session_id = filepath.stem
        messages: list[SessionMessage] = []
        start_time = ""
        end_time = ""

        with open(filepath, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    continue

                msg = self._parse_message(raw)
                if msg is not None:
                    messages.append(msg)
                    # Track time bounds
                    ts = raw.get("timestamp", "")
                    if ts:
                        if not start_time or ts < start_time:
                            start_time = ts
                        if not end_time or ts > end_time:
                            end_time = ts

        if not messages:
            return None

        return SessionData(
            session_id=session_id,
            filepath=str(filepath),
            messages=messages,
            start_time=start_time,
            end_time=end_time,
        )

    def _parse_message(self, raw: dict[str, Any]) -> SessionMessage | None:
        """Parse a raw message dict into a SessionMessage."""
        role = raw.get("role", "")
        content = raw.get("content", "")
        timestamp = raw.get("timestamp", "")

        # Handle content that might be a list (Anthropic/OpenAI style)
        if isinstance(content, list):
            # Extract text from content blocks
            text_parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_use":
                        pass  # handled via tool_calls below
                elif isinstance(block, str):
                    text_parts.append(block)
            content = "\n".join(text_parts)

        # Parse tool calls from assistant messages
        tool_calls: list[ToolCallInfo] = []
        tool_name = ""
        tool_call_id = raw.get("tool_call_id", "")
        is_error = False

        if role == "assistant":
            # OpenAI-style tool_calls
            raw_tool_calls = raw.get("tool_calls", [])
            for tc in raw_tool_calls:
                if isinstance(tc, dict):
                    func = tc.get("function", tc)
                    name = tc.get("name", func.get("name", ""))
                    arguments = func.get("arguments", {})
                    if isinstance(arguments, str):
                        try:
                            arguments = json.loads(arguments)
                        except json.JSONDecodeError:
                            arguments = {}
                    tc_id = tc.get("id", "")
                    tool_calls.append(ToolCallInfo(
                        name=name,
                        arguments=arguments,
                        tool_call_id=tc_id,
                    ))

            # Anthropic-style content blocks with tool_use
            if isinstance(raw.get("content"), list):
                for block in raw["content"]:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_calls.append(ToolCallInfo(
                            name=block.get("name", ""),
                            arguments=block.get("input", {}),
                            tool_call_id=block.get("id", ""),
                        ))

        elif role == "tool":
            tool_name = raw.get("name", raw.get("tool_name", ""))
            # Check if tool result indicates error
            is_error = raw.get("is_error", False)
            # Also heuristically detect errors in content
            if isinstance(content, str) and not is_error:
                content_lower = content.lower()
                error_indicators = ["error:", "exception", "traceback", "failed", "command not found"]
                is_error = any(ind in content_lower for ind in error_indicators)

        return SessionMessage(
            role=role,
            content=content if isinstance(content, str) else str(content),
            timestamp=timestamp,
            tool_calls=tool_calls,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            is_error=is_error,
            raw=raw,
        )