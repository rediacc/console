"""wl_judge: the stop-legitimacy judge call and its v10 verdict cache.

Fail CLOSED by contract: every error path returns an error string, and the
caller turns that into a block. See "NO ESCAPE HATCH" in worklist.py.
"""

import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import time

import worklist_messages as M

# v5: no cap. Kept as a name so the counter file (used only to TELL the judge
# it is repeating itself) reads clearly.
JUDGE_MODEL = os.environ.get("WORKLIST_JUDGE_MODEL", "claude-haiku-4-5-20251001")
# Measured on 2026-07-29 with --json-schema: haiku warm $0.011-$0.026 per call
# at 4.9-20.0s; sonnet $0.231 at 12.1s for the same judgement. Haiku it is.
JUDGE_BUDGET_USD = os.environ.get("WORKLIST_JUDGE_BUDGET_USD", "0.10")
JUDGE_TIMEOUT_S = int(os.environ.get("WORKLIST_JUDGE_TIMEOUT_S", "120"))
JUDGE_DISABLED = os.environ.get("WORKLIST_JUDGE") == "off"

# v10 VERDICT CACHE. The judge is the dominant cost of a quiet-but-tracked
# stop (5-20s and $0.01-0.03, measured), and its question is a function of
# the WORLD and the MESSAGE. An identical world signature and an identical
# message within the TTL is the same question about the same facts, so a
# cached "stop" answers it for free -- the v9 fast-path argument, one level
# up. Fails toward calling the judge: only clean "stop" verdicts with no
# regression signals are ever cached, and any mismatch or corruption is a
# miss.
JUDGE_CACHE_MIN = int(os.environ.get("WORKLIST_JUDGE_CACHE_MIN", "30"))

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["stop", "continue"]},
        "reason": {"type": "string", "maxLength": 300},
        "next_action": {"type": "string", "maxLength": 200},
        # v7: OPTIONAL at the top level (verified: --json-schema accepts a
        # conditionally-required object and returns cleanly with it omitted,
        # so ONE schema, no variants), but its own properties are all
        # required. On a fix-signal stop a missing or malformed object is a
        # judge error and fails closed, same as an invalid verdict.
        "regression_gate": {
            "type": "object",
            "properties": {
                "applicable": {"type": "boolean"},
                "blind_spot": {"type": "string", "maxLength": 300},
                "existing_gate": {"type": "string", "maxLength": 100},
                "recurring": {"type": "boolean"},
                "gate_needed": {"type": "boolean"},
                "gate_proven": {"type": "boolean"},
                "instruction": {"type": "string", "maxLength": 300},
            },
            "required": [
                "applicable", "blind_spot", "existing_gate", "recurring",
                "gate_needed", "gate_proven", "instruction",
            ],
            "additionalProperties": False,
        },
        # v12: OPTIONAL at the top level, same contract as regression_gate:
        # one schema, and on a stop that REQUESTED an audit a missing or
        # malformed array is a judge error that fails closed at the caller
        # (apply_defer_audit + R_AUDIT_MALFORMED).
        "defer_audit": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "maxLength": 16},
                    "verdict": {"type": "string", "enum": ["valid", "do_now"]},
                    "reason": {"type": "string", "maxLength": 200},
                    "order": {"type": "string", "maxLength": 200},
                },
                "required": ["id", "verdict", "reason", "order"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["verdict", "reason", "next_action"],
    "additionalProperties": False,
}


# v16 TRIAGE. Same shape as JUDGE_SCHEMA (flat object, string enum) and the
# same transport, but DELIBERATELY the opposite failure semantics: the stop
# judge fails closed because it gates an exit, while triage is a decision aid
# on a CLI path, so an error degrades to the self-assessment printout and
# exit 0. See run_triage.
TRIAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["inline", "plan-subagent", "operator-only"],
        },
        "reason": {"type": "string", "maxLength": 300},
        "plan_slug": {"type": "string", "maxLength": 60},
    },
    "required": ["verdict", "reason", "plan_slug"],
    "additionalProperties": False,
}

TRIAGE_VERDICTS = ("inline", "plan-subagent", "operator-only")


def run_triage(finding, context):
    """(verdict_dict, error_string). Exactly one is non-None.

    Modeled on run_judge down to the recursion guard and the workdir, because
    the transport is the same and a second copy that drifts is a second bug.
    The CALLER decides what an error means; here every failure is simply
    reported, never swallowed, so a degraded triage can name what broke.
    """
    exe = resolve_claude()
    if not exe or not os.path.exists(exe):
        return None, "claude CLI not found (looked at PATH and ~/.local/bin/claude)"
    workdir = pathlib.Path(os.environ.get("TMPDIR", "/tmp")) / "claude-worklist" / ".judge"
    try:
        workdir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return None, "triage workdir unusable: %s" % exc
    prompt = M.TRIAGE_PROMPT % {"finding": finding[-4000:], "context": context}
    env = dict(os.environ)
    # THE RECURSION GUARD, same as run_judge: `claude -p` fires the Stop hook.
    env["STOPHOOK_CHILD"] = "1"
    try:
        proc = subprocess.run(
            [
                exe, "-p", prompt,
                "--output-format", "json",
                "--json-schema", json.dumps(TRIAGE_SCHEMA),
                "--model", JUDGE_MODEL,
                "--max-budget-usd", JUDGE_BUDGET_USD,
            ],
            capture_output=True,
            text=True,
            timeout=JUDGE_TIMEOUT_S,
            env=env,
            cwd=str(workdir),
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return None, "triage timed out after %ds" % JUDGE_TIMEOUT_S
    except OSError as exc:
        return None, "triage could not be launched: %s" % exc
    if proc.returncode != 0:
        return None, "triage exited %d: %s" % (proc.returncode, (proc.stderr or "")[-300:])
    try:
        env_out = json.loads(proc.stdout)
    except ValueError:
        return None, "triage returned unparseable stdout: %s" % (proc.stdout or "")[-300:]
    if env_out.get("is_error"):
        return None, "triage reported is_error (subtype=%s, api=%s)" % (
            env_out.get("subtype"),
            env_out.get("api_error_status"),
        )
    out = env_out.get("structured_output")
    if not isinstance(out, dict) or out.get("verdict") not in TRIAGE_VERDICTS:
        return None, "triage produced no usable structured_output: %s" % repr(out)[:300]
    return out, None


def apply_defer_audit(rows, batch):
    """(kind, valids, orders) from the judge's defer_audit answer.

    kind is 'ok' or 'malformed'; valids is [(id, upd_stamp, reason)] to bank,
    orders is [(id, order_text)] to enforce. STRICT by contract: every
    audited item must come back with a usable verdict, and anything else --
    no array, a non-dict entry, an invalid verdict, a batch id missing --
    is 'malformed', which the caller turns into a fail-closed block. An id
    the judge invented is ignored rather than acted on: reopening an item
    nobody audited would let a hallucination edit the store.
    """
    if not isinstance(rows, list):
        return "malformed", [], []
    by_id = {}
    for e in rows:
        if not isinstance(e, dict) or e.get("verdict") not in ("valid", "do_now"):
            return "malformed", [], []
        by_id[str(e.get("id", ""))] = e
    valids, orders = [], []
    for rec in batch:
        e = by_id.get(rec["id"])
        if e is None:
            return "malformed", [], []
        if e["verdict"] == "valid":
            valids.append((rec["id"], rec.get("upd", ""), str(e.get("reason", ""))))
        else:
            orders.append((rec["id"], str(e.get("order", "")) or str(e.get("reason", ""))))
    return "ok", valids, orders


def resolve_claude():
    return shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")


def msg_hash(message):
    return hashlib.sha1((message or "").encode("utf-8", "replace")).hexdigest()[:16]


def cached_stop_verdict(state_doc, sig, message):
    """A previously banked 'stop' verdict for this exact world+message, or
    None. Any doubt is a miss."""
    c = state_doc.get("judge_cache")
    if not isinstance(c, dict):
        return None
    try:
        fresh = time.time() - float(c.get("at", 0)) <= JUDGE_CACHE_MIN * 60
    except (TypeError, ValueError):
        return None
    if not fresh or c.get("sig") != sig or c.get("msg") != msg_hash(message):
        return None
    if c.get("verdict") != "stop":
        return None
    return {"verdict": "stop", "reason": str(c.get("reason", "cached")), "next_action": ""}


def bank_stop_verdict(state_doc, sig, message, reason):
    state_doc["judge_cache"] = {
        "sig": sig,
        "msg": msg_hash(message),
        "verdict": "stop",
        "reason": reason[:200],
        "at": time.time(),
    }


def run_judge(remaining_lines, leases, message, streak, loop_desc, citations=None, extra="", traps=None):
    """(verdict_dict, error_string). Exactly one is non-None."""
    exe = resolve_claude()
    if not exe or not os.path.exists(exe):
        return None, "claude CLI not found (looked at PATH and ~/.local/bin/claude)"
    workdir = pathlib.Path(os.environ.get("TMPDIR", "/tmp")) / "claude-worklist" / ".judge"
    try:
        workdir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return None, "judge workdir unusable: %s" % exc
    prompt = M.JUDGE_PROMPT % {
        "streak": streak,
        "remaining": "\n".join("  " + r for r in remaining_lines[:20]) or "  (none tracked)",
        "leases": leases,
        "loop": loop_desc,
        "message": (message or "(the session produced no text)")[-6000:],
        "citations": citations or "  (none cited)",
        "traps": "\n".join("  - " + h for h in (traps or [])) or "  (none recorded)",
    } + (extra or "")
    env = dict(os.environ)
    # THE RECURSION GUARD. `claude -p` fires this very hook; --settings does not
    # suppress it. Without this line the hook forks itself forever.
    env["STOPHOOK_CHILD"] = "1"
    try:
        proc = subprocess.run(
            [
                exe, "-p", prompt,
                "--output-format", "json",
                "--json-schema", json.dumps(JUDGE_SCHEMA),
                "--model", JUDGE_MODEL,
                "--max-budget-usd", JUDGE_BUDGET_USD,
            ],
            capture_output=True,
            text=True,
            timeout=JUDGE_TIMEOUT_S,
            env=env,
            cwd=str(workdir),
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return None, "judge timed out after %ds" % JUDGE_TIMEOUT_S
    except OSError as exc:
        return None, "judge could not be launched: %s" % exc
    if proc.returncode != 0:
        return None, "judge exited %d: %s" % (proc.returncode, (proc.stderr or "")[-300:])
    try:
        env_out = json.loads(proc.stdout)
    except ValueError:
        return None, "judge returned unparseable stdout: %s" % (proc.stdout or "")[-300:]
    if env_out.get("is_error"):
        return None, "judge reported is_error (subtype=%s, api=%s)" % (
            env_out.get("subtype"),
            env_out.get("api_error_status"),
        )
    out = env_out.get("structured_output")
    if not isinstance(out, dict) or out.get("verdict") not in ("stop", "continue"):
        return None, "judge produced no usable structured_output: %s" % repr(out)[:300]
    return out, None
