"""Measure stalled model waits in Claude agent transcripts.

Reads the lead transcript `<project>/<session>.jsonl` and the writer transcripts `<project>/<session>/subagents/*.jsonl`, and reports per role and model the request count, the user-to-assistant waits in the first-byte timeout band, wait hours against active hours, and the stall rate bucketed by concurrent writers and by context size.

Usage: PYTHONPATH=.ci python3 -m rediacc_ci.ops.agent_stalls --since <ISO> --until <ISO> [--session <id>] [--project <dir>] [--json]

Definitions:
- request: one assistant message id (the streamed rows of one message count once).
- wait: seconds from the preceding user row to the first assistant row of the request; a request that does not directly follow a user row has no wait.
- band wait: a wait of 175 to 400 seconds, a first-byte timeout plus a retry.
- active time: first to last user/assistant row of a transcript, clipped to the window.
- death: a transcript whose last row is a user row that no assistant row answered.
- concurrent writers: writer transcripts whose active span covers the request.
- context: input plus cache-creation plus cache-read tokens of the request.
"""

from __future__ import annotations

import argparse
import bisect
import json
import statistics
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

BAND_LOW = 175.0
BAND_HIGH = 400.0
CONCURRENCY_BUCKETS = (("1", 1, 1), ("2-3", 2, 3), ("4-7", 4, 7), ("8+", 8, 10**9))
CONTEXT_BUCKETS = (("<40k", 0, 40_000), ("40k-100k", 40_000, 100_000), (">=100k", 100_000, 10**12))


def parse_ts(text: str) -> datetime:
    parsed = datetime.fromisoformat(text.strip())
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


@dataclass
class Request:
    role: str
    model: str
    at: float
    wait: float | None
    context: int
    concurrent: int = 1


@dataclass
class Transcript:
    role: str
    path: Path
    first: float | None = None
    last: float | None = None
    died: bool = False
    model: str = "unknown"
    requests: list[Request] = field(default_factory=list)


def _context_tokens(usage: dict) -> int:
    keys = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
    return sum(usage[k] for k in keys if isinstance(usage.get(k), int))


def read_transcript(path: Path, role: str, since: float, until: float) -> Transcript:
    """Parse one transcript; the span covers every row, the requests only those inside the window."""
    transcript = Transcript(role=role, path=path)
    prev_type: str | None = None
    prev_at = 0.0
    seen: set[str] = set()
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            kind = row.get("type")
            stamp = row.get("timestamp")
            if kind not in ("user", "assistant") or not isinstance(stamp, str):
                continue
            try:
                at = parse_ts(stamp).timestamp()
            except ValueError:
                continue
            if transcript.first is None:
                transcript.first = at
            transcript.last = at
            message = row.get("message") if isinstance(row.get("message"), dict) else {}
            if kind == "assistant":
                model = message.get("model") or "unknown"
                if model != "unknown" and transcript.model == "unknown":
                    transcript.model = model
                key = message.get("id") or f"row-{at}"
                if key not in seen:
                    seen.add(key)
                    usage = message.get("usage") if isinstance(message.get("usage"), dict) else {}
                    wait = at - prev_at if prev_type == "user" else None
                    if since <= at <= until:
                        transcript.requests.append(
                            Request(role, model, at, wait, _context_tokens(usage))
                        )
            prev_type, prev_at = kind, at
    transcript.died = prev_type == "user"
    return transcript


def _context_bucket(value: int) -> str:
    for name, low, high in CONTEXT_BUCKETS:
        if low <= value < high:
            return name
    return CONTEXT_BUCKETS[-1][0]


def _concurrency_bucket(value: int) -> str:
    for name, low, high in CONCURRENCY_BUCKETS:
        if low <= value <= high:
            return name
    return CONCURRENCY_BUCKETS[-1][0]


def _summarize(requests: list[Request]) -> dict:
    waits = [r.wait for r in requests if r.wait is not None]
    band = [w for w in waits if BAND_LOW <= w <= BAND_HIGH]
    return {
        "requests": len(requests),
        "waits": len(waits),
        "band_waits": len(band),
        "band_hours": round(sum(band) / 3600, 2),
        "band_median_s": round(statistics.median(band), 1) if band else None,
        "wait_hours": round(sum(waits) / 3600, 2),
        "stall_rate": round(len(band) / len(requests), 4) if requests else 0.0,
    }


def _buckets(requests: list[Request], key, order: list[str]) -> dict:
    grouped: dict[str, list[Request]] = {name: [] for name in order}
    for request in requests:
        grouped[key(request)].append(request)
    return {name: _summarize(items) for name, items in grouped.items() if items}


def discover(project: Path, session: str | None) -> list[tuple[str, Path]]:
    found: list[tuple[str, Path]] = []
    sessions = [session] if session else sorted(p.stem for p in project.glob("*.jsonl"))
    for name in sessions:
        lead = project / f"{name}.jsonl"
        if lead.is_file():
            found.append(("lead", lead))
        sub = project / name / "subagents"
        if sub.is_dir():
            found.extend(("writer", p) for p in sorted(sub.glob("*.jsonl")))
    return found


def analyze(files: list[tuple[str, Path]], since: datetime, until: datetime) -> dict:
    lo, hi = since.timestamp(), until.timestamp()
    transcripts = [read_transcript(path, role, lo, hi) for role, path in files]
    spans = sorted(
        (t.first, t.last) for t in transcripts if t.role == "writer" and t.first is not None
    )
    starts = [s for s, _ in spans]
    for transcript in transcripts:
        for request in transcript.requests:
            started = spans[: bisect.bisect_right(starts, request.at)]
            request.concurrent = max(sum(1 for _, end in started if end >= request.at), 1)

    report: dict = {"since": since.isoformat(), "until": until.isoformat(), "roles": {}}
    for role in ("writer", "lead"):
        group = [t for t in transcripts if t.role == role and t.first is not None]
        if not group:
            continue
        requests = [r for t in group for r in t.requests]
        active: dict[str, float] = {}
        for t in group:
            span = max(0.0, min(t.last, hi) - max(t.first, lo))
            counts: dict[str, int] = {}
            for r in t.requests:
                if r.model != "<synthetic>":
                    counts[r.model] = counts.get(r.model, 0) + 1
            owner = max(counts, key=counts.get) if counts else t.model
            active[owner] = active.get(owner, 0.0) + span
        models = {}
        for model in sorted({r.model for r in requests} | set(active)):
            entry = _summarize([r for r in requests if r.model == model])
            entry["active_hours"] = round(active.get(model, 0.0) / 3600, 2)
            models[model] = entry
        total = _summarize(requests)
        total["active_hours"] = round(sum(active.values()) / 3600, 2)
        total["transcripts"] = sum(1 for t in group if t.requests)
        total["deaths"] = sum(1 for t in group if t.died and lo <= t.last <= hi)
        report["roles"][role] = {
            "total": total,
            "models": models,
            "by_concurrent_writers": _buckets(
                requests,
                lambda r: _concurrency_bucket(r.concurrent),
                [b[0] for b in CONCURRENCY_BUCKETS],
            ),
            "by_context": _buckets(
                requests, lambda r: _context_bucket(r.context), [b[0] for b in CONTEXT_BUCKETS]
            ),
        }
    return report


def _line(label: str, entry: dict) -> str:
    median = entry["band_median_s"]
    active = entry.get("active_hours")
    tail = f" active_h={active}" if active is not None else ""
    return (
        f"  {label:<26} requests={entry['requests']:<6} band_waits={entry['band_waits']:<5} "
        f"band_h={entry['band_hours']:<6} median_s={median if median is not None else '-':<6} "
        f"wait_h={entry['wait_hours']:<6} stall_rate={entry['stall_rate']:.1%}{tail}"
    )


def render(report: dict) -> str:
    out = [f"window {report['since']} .. {report['until']}"]
    for role, body in report["roles"].items():
        total = body["total"]
        out.append(f"{role}: transcripts={total['transcripts']} deaths={total['deaths']}")
        out.append(_line("total", total))
        for model, entry in body["models"].items():
            out.append(_line(f"model {model}", entry))
        for name, entry in body["by_concurrent_writers"].items():
            out.append(_line(f"concurrent {name}", entry))
        for name, entry in body["by_context"].items():
            out.append(_line(f"context {name}", entry))
    return "\n".join(out)


def default_project() -> Path:
    base = Path.home() / ".claude" / "projects"
    preferred = base / "-home-developer-console"
    return preferred if preferred.is_dir() else base / str(Path.cwd()).replace("/", "-")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report stalled model waits in agent transcripts.")
    parser.add_argument("--since", required=True, help="window start, ISO 8601 (Z or offset)")
    parser.add_argument("--until", required=True, help="window end, ISO 8601")
    parser.add_argument("--session", help="one session id (default: every session in the project)")
    parser.add_argument("--project", type=Path, default=None, help="transcript directory")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args(argv)
    try:
        since, until = parse_ts(args.since), parse_ts(args.until)
    except ValueError as exc:
        print(f"agent_stalls: bad timestamp: {exc}", file=sys.stderr)
        return 2
    if until <= since:
        print("agent_stalls: --until must be after --since", file=sys.stderr)
        return 2
    project = args.project or default_project()
    if not project.is_dir():
        print(f"agent_stalls: no transcript directory at {project}", file=sys.stderr)
        return 2
    report = analyze(discover(project, args.session), since, until)
    print(json.dumps(report, indent=2) if args.json else render(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
