#!/usr/bin/env python3
"""PostToolUse(Bash): name the fix when a bench request meets the bench IP allowlist or the eu-bench IP-changed login refusal. Wired as a member of the `post-bash` pattern in `.claude/rediacc_hooks/lifecycle.py`.

THE FAILURE THIS PREVENTS (2026-11-10). Bench (the `BENCH_ORIGIN` and `PROXY_BENCH_HOST` hosts) sits behind ONE Cloudflare WAF custom rule allowing a short IP list (`.ci/rediacc_ci/ops/bench_access.py`: entries expire after 7 days, and this machine's egress IP rotates nightly). An IP off the list gets Cloudflare's own 403 page, and the CLI against `--config eu-bench` prints `{"errors":[{"code":"GENERAL_ERROR","message":"HTTP 403"}]}` on stdout with only progress lines on stderr. A session read that 403 as a rate limit, wrote "bench rate-limits this IP until 2026-11-12" onto worklist items, and left bench work idle for hours. The fix was one command, `bench_access.COMMAND`. Once the IP is allowed, the next refusal is the eu-bench login tied to the old IP, fixed by `login_bench.REMEDY` (`npm run login:bench`).

WHAT FIRES, AND WHAT MUST NOT. Both notes need a BENCH COMMAND: one naming `--config eu-bench`, `--config bench` (either spelling, or a `REDIACC_CONFIG=` prefix), or a bench host. The context is read off the command and never off the output, so reading a document that quotes a 403 is silent. Then:
  - the allowlist note needs a 403 SHAPE in the output (`WAF_SIGNALS`): Cloudflare's block page, a `cf-mitigated` header, an HTTP status line or envelope message of 403, `403 Forbidden`. A bare `403` in other text is not one;
  - the login note needs one of `login_bench.LOGIN_NEEDED_MARKERS` in the output.
An eu-remote 403, a GitHub 403 and a bench command printing an unrelated 403 are all silent. Each note is skipped when the output already names its own fix (`bench_access` preflight, deploy_bench's HINT, ops_health's hint, a login_bench run), so a command that told the reader is not told twice.

ONCE PER OUTPUT, NOT ONCE PER SESSION. The IP rotates nightly, so one long session meets the block more than once, and a note shown only the first time is absent the second. `trapguard[bench-login-is-the-agents-step]` (`.claude/hooks/trapguard/dispatch.py`) says the login half once per session; this says it every time the refusal appears.

THE FIX TEXTS ARE IMPORTED, NOT COPIED. `bench_access.COMMAND`, `login_bench.REMEDY` and `login_bench.LOGIN_NEEDED_MARKERS` come through `rediacc_hooks.syspath.import_from_ci`, and the hosts through `rediacc_hooks.wellknown`, so a renamed command cannot leave this hint naming the old one. The import runs only after the cheap prefilter (`_maybe`) passes, so the ordinary Bash call costs a substring test. A failed import is SAID in the context, never swallowed: a hint that silently stopped speaking is the failure this file exists for.

Advisory: always exits 0 and never blocks the tool call that already ran.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import sys
import urllib.parse

HERE = pathlib.Path(__file__).resolve().parent

# `--config eu-bench`, `--config=bench`, `REDIACC_CONFIG=eu-bench`, optionally quoted. `eu-bench-old` and `bench2` are other configs and do not match.
BENCH_CONFIG = re.compile(
    r"(?:^|[\s;&|(`])(?:--config[= ]\s*|REDIACC_CONFIG=)[\"']?(?:eu-)?bench(?![\w.-])",
    re.MULTILINE,
)

# A 403 as a block reads, never a bare number: Cloudflare's own page title and body line, the `cf-mitigated` response header, an HTTP status line (`HTTP/2 403`, `HTTP 403`, the CLI's envelope message), `403 Forbidden`, and a `status: 403` field.
WAF_SIGNALS = re.compile(
    r"Attention Required! \| Cloudflare"
    r"|Sorry, you have been blocked"
    r"|^\s*cf-mitigated\s*:"
    r"|\bHTTP(?:/[0-9.]+)?\s+403\b"
    r"|\"message\"\s*:\s*\"HTTP 403\""
    r"|\b403 Forbidden\b"
    r"|\bstatus(?:[ _]?code)?[\"']?\s*[:=]\s*403\b",
    re.IGNORECASE | re.MULTILINE,
)

# What the output says when it already names a fix, so the note would repeat it.
ALLOWLIST_TOLD = "bench_access add-current"
LOGIN_TOLD = "login:bench"


def _load_syspath():
    """The canonical `.claude` hop, loaded BY FILE: this module lives outside the `rediacc_hooks` package."""
    hop = HERE.parents[1] / "rediacc_hooks" / "syspath.py"
    spec = importlib.util.spec_from_file_location("rediacc_hooks_syspath", hop)
    if spec is None or spec.loader is None:
        raise ImportError("no loadable %s" % hop)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sources():
    """(allowlist command, login remedy, login markers, bench hosts), each read from its owner."""
    syspath = _load_syspath()
    syspath.on_sys_path(syspath.CLAUDE_DIR)
    from rediacc_hooks import wellknown

    bench_access = syspath.import_from_ci("rediacc_ci.ops.bench_access")
    login_bench = syspath.import_from_ci("rediacc_ci.ops.login_bench")
    hosts = (
        urllib.parse.urlsplit(wellknown.BENCH_ORIGIN).hostname or "",
        wellknown.PROXY_BENCH_HOST,
    )
    return (
        bench_access.COMMAND,
        login_bench.REMEDY,
        tuple(login_bench.LOGIN_NEEDED_MARKERS),
        tuple(h for h in hosts if h),
    )


def is_bench_command(cmd, hosts):
    """True when the command line names a bench config or a bench host."""
    if BENCH_CONFIG.search(cmd or ""):
        return True
    return any(re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(h), cmd or "") for h in hosts)


def notes(cmd, out, src):
    """The note lines this (command, output) earns: [] for anything that is not a bench refusal."""
    command, remedy, markers, hosts = src
    if not is_bench_command(cmd, hosts):
        return []
    lines = []
    if WAF_SIGNALS.search(out) and ALLOWLIST_TOLD not in out:
        lines.append(
            "bench-block: this 403 is the bench IP allowlist (one Cloudflare WAF rule; entries "
            "expire after 7 days and this machine's egress IP rotates nightly), NOT a rate limit, "
            "and waiting does not clear it."
        )
        lines.append("  fix, then rerun: %s" % command)
    if any(m in out for m in markers) and LOGIN_TOLD not in out:
        lines.append(
            "bench-login: the eu-bench login is tied to the old IP address. Moving it is the "
            "agent's own step, never an authenticator-code request: run `%s` (headless), then "
            "rerun." % remedy
        )
    return lines


# Fragments of every signal `notes` reads, one of which must be in the raw payload. Cloudflare's page body carries no `403` of its own, so the page and header words are here too.
PREFILTER = (
    "403",
    "Attention Required",
    "you have been blocked",
    "cf-mitigated",
    "address changed",
    "network address",
    "login only works",
    "Not logged in",
)


def _maybe(raw):
    """The prefilter on the raw payload: a bench word plus a fragment of some signal. Most Bash calls fail it before any parse or import."""
    return "bench" in raw and any(f in raw for f in PREFILTER)


def response_text(resp):
    """stdout and stderr as one string; a string response is itself (the shape trapguard's probe recorded, read tolerantly)."""
    if isinstance(resp, str):
        return resp
    if isinstance(resp, dict):
        return "\n".join(str(resp.get(k) or "") for k in ("stdout", "stderr"))
    return ""


def render(text):
    return (
        json.dumps(
            {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text}}
        )
        + "\n"
    )


def main(stdin=None, stdout=None, src=None):
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    try:
        raw = stdin.read()
        if not _maybe(raw):
            return 0
        try:
            doc = json.loads(raw)
        except ValueError:
            return 0
        if not isinstance(doc, dict) or doc.get("tool_name") not in (None, "Bash"):
            return 0
        tool_input = doc.get("tool_input") if isinstance(doc.get("tool_input"), dict) else {}
        cmd = str(tool_input.get("command") or "")
        out = response_text(doc.get("tool_response"))
        try:
            src = src or sources()
        except Exception as exc:
            stdout.write(
                render(
                    "bench-block: a bench refusal may be in this output, but the hint could not "
                    "load its fix commands (%s: %s). The bench 403 is the IP allowlist, never a "
                    "rate limit; see .ci/rediacc_ci/ops/bench_access.py."
                    % (type(exc).__name__, exc)
                )
            )
            return 0
        lines = notes(cmd, out, src)
        if lines:
            stdout.write(render("\n".join(lines)))
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
