# hermes-introspection

Quantitative performance metrics for Hermes agent sessions. No vibes, no self-reflection slop — just hard numbers.

## What It Does

Analyzes Hermes session transcripts (`~/.hermes/sessions/*.jsonl`) and computes per-session metrics:

| Metric | Description |
|--------|-------------|
| `tool_call_count` | Total tool calls made in session |
| `iterations_to_success` | Tool call iterations before task completed or abandoned |
| `human_intervention_count` | User messages that correct/guide the agent (heuristic-based) |
| `error_repeat_count` | Repeated error patterns across iterations |
| `information_seeking_ratio` | Read/search/view calls vs write/patch/terminal calls after failure |
| `wall_time_seconds` | Total session duration |
| `outcome` | `completed`, `abandoned`, or `in_progress` |

## Why

Ungrounded self-reflection produces slop. Instrumented process outcome tracking with hard numbers is the antidote. This repo answers: *Is the agent actually getting better?* with data, not vibes.

## Installation

```bash
pip install -e .
```

Requires Python 3.11+.

## Usage

### CLI

```bash
# Run full collection + reporting pipeline
python -m hermes_introspection

# Or via entry point script
python scripts/introspect.py
```

### Programmatic

```python
from hermes_introspection.collector import SessionCollector
from hermes_introspection.metrics import MetricsComputer
from hermes_introspection.reporter import Reporter

collector = SessionCollector()
sessions = collector.collect()

computer = MetricsComputer()
metrics = [computer.compute(s) for s in sessions]

reporter = Reporter()
reporter.write_daily(metrics)
```

## Storage

Daily metrics are written as JSON to `data/metrics/YYYY-MM-DD.json` and auto-committed to the repo.

## Automation

- **Primary**: Hermes CRON task
- **Backup**: GitHub Actions workflow runs daily at 06:00 UTC (`.github/workflows/daily-introspect.yml`)

## Session Format

Expects JSONL files at `~/.hermes/sessions/*.jsonl`. Each line is a JSON object:

```jsonl
{"role": "user", "content": "...", "timestamp": "2026-05-01T10:00:00Z"}
{"role": "assistant", "content": "...", "tool_calls": [...], "timestamp": "2026-05-01T10:00:01Z"}
{"role": "tool", "content": "...", "tool_call_id": "...", "timestamp": "2026-05-01T10:00:02Z"}
```

## License

Private — Researchoors internal.
