"""check:ci-windows-image-expiry -- the shared Windows evaluation image is re-baked before its evaluation period ends (agent/plans/PLAN-windows-lane.md D12).

The Windows lane runs on a Windows 11 Enterprise Evaluation image baked once and shared from a private bucket. The evaluation expires about 90 days after install, and an image past its end fails every Windows step at once. This gate reads only `.ci/config/windows-image.json` and the clock (`rediacc_ci.core.gate_clock`, so a test can plant the day):

  * `image` null: prints `NO WINDOWS IMAGE RECORDED` and exits 0; nothing is shared yet.
  * the file missing or unparseable, or not a schema 1 record: red.
  * `warn_days` or fewer whole days left before `expires_at` (expired included): red, naming the days left, `expires_at` and the record's `rebake` command, which needs no human because the ISO comes from the bucket.
  * an image whose `iso_sha256` or `virtio_iso_sha256` differs from `inputs`: red; an image always names the inputs it was baked from.

It is a clock gate: a pass today turns red on a later day with no tracked input changed (`.ci/policy/carry-exempt.json` says so), and `scripts/ci-runner/local-warn.ts` turns its red into a local advisory in `ci:quick` while it stays blocking in CI. The remedy is the printed command plus the commit of the new record.

Exit 0 green, 1 red.

---- gate ----
step: Windows evaluation image expiry
needs: none
lane: quality-static
why: the shared Windows evaluation image expires about 90 days after install; this
     turns red warn_days ahead and prints the one-command re-bake, so the lane never
     discovers the expiry by every Windows step failing at once.
---- end gate ----
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys

from rediacc_ci import paths
from rediacc_ci.core import gate_clock

RECORD_REL = ".ci/config/windows-image.json"
SCHEMA = 1


def _instant(value: object, field: str) -> dt.datetime:
    try:
        moment = dt.datetime.fromisoformat(value if isinstance(value, str) else "")
    except ValueError as exc:
        raise ValueError("image.%s %r is not an ISO 8601 instant" % (field, value)) from exc
    if moment.tzinfo is None:
        raise ValueError("image.%s %r carries no UTC offset" % (field, value))
    return moment.astimezone(dt.UTC)


def evaluate(path: pathlib.Path, now: dt.datetime) -> tuple[int, list[str]]:
    """(exit code, lines) for the record at `path` judged at `now`."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return 1, ["RED: cannot read %s (%s)" % (RECORD_REL, exc)]
    except ValueError as exc:
        return 1, ["RED: %s is not JSON (%s)" % (RECORD_REL, exc)]
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
        return 1, ["RED: %s is not a schema %d record" % (RECORD_REL, SCHEMA)]
    image = doc.get("image")
    if image is None:
        return 0, ["NO WINDOWS IMAGE RECORDED in %s; nothing to expire" % RECORD_REL]
    rebake = str(doc.get("rebake", "")).strip() or "(the record names no rebake command)"
    warn = doc.get("warn_days")
    if not isinstance(image, dict) or not isinstance(warn, int) or isinstance(warn, bool):
        return 1, ["RED: %s needs an `image` object and an integer `warn_days`" % RECORD_REL]
    try:
        expires = _instant(image.get("expires_at"), "expires_at")
    except ValueError as exc:
        return 1, ["RED: %s: %s" % (RECORD_REL, exc)]
    lines: list[str] = []
    raw_inputs = doc.get("inputs")
    inputs: dict = raw_inputs if isinstance(raw_inputs, dict) else {}
    for label, field in (("iso", "iso_sha256"), ("virtio", "virtio_iso_sha256")):
        want = (inputs.get(label) or {}).get("sha256")
        have = image.get(field)
        if not want or have != want:
            lines.append(
                "RED: image.%s %s differs from inputs.%s.sha256 %s; an image names the inputs it was baked from"
                % (field, have, label, want)
            )
    days = (expires - now).days
    if days <= warn:
        state = "EXPIRED %d day(s) ago" % -days if days < 0 else "%d day(s) left" % days
        lines.append(
            "RED: the Windows evaluation image %s expires at %s: %s, inside the %d-day window. Re-bake: %s, then commit %s"
            % (image.get("key", "?"), image.get("expires_at"), state, warn, rebake, RECORD_REL)
        )
    if lines:
        return 1, lines
    return 0, [
        "OK: the Windows evaluation image %s expires at %s: %d day(s) left (warns at %d)"
        % (image.get("key", "?"), image.get("expires_at"), days, warn)
    ]


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    path = pathlib.Path(args[0]) if args else paths.repo_root() / RECORD_REL
    try:
        now = gate_clock.now()
    except gate_clock.GateClockError as exc:
        print("RED: %s" % exc, file=sys.stderr)
        return 1
    rc, lines = evaluate(path, now)
    for line in lines:
        print(line, file=sys.stderr if rc else sys.stdout)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
