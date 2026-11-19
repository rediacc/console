"""The account side of feedback triage: the admin export, the verdict batch, the per-region session and the export cursor (PLAN-rdc-feedback D3, D5).

ROUTES. `GET /admin/feedback/export?since=<iso>&status=<list>` answers `{items: [...]}`, one item per fingerprint with its aggregate counts and the redacted fields of its newest report (no owner id, org id or config fingerprint). `POST /admin/feedback/verdicts` takes `{verdicts: [...]}`, at most VERDICT_BATCH_MAX per call, and answers `{fingerprints, reports, missing}`. Both sit under `/account/api/v1`.

SESSIONS. eu, us and asia open a root API token session through `rediacc_ci.ops.root_login.open_token_session` (the `root-login` Bitwarden profile; the token session counts as elevated, so it writes verdicts too). `bench` is the eu bench, which has no root API token: the bench root signs in with its password and TOTP seed (the `bench-login-eu` profile), and a write is elevated through the reauth mail first (`login_bench.elevate`), the way `rediacc_ci.ops.root_grants` posts to bench. The HTTP layer is a `Transport` (`get`, `post`, routes relative to `/account/api/v1`), so a test hands in a stub and no test touches the network.

CURSOR. `.ci/cache/feedback/last-run.json` holds, per region, the newest `lastSeenAt` the last written run exported (`since`) and when it ran (`ranAt`). The next export asks `since` it; the account filters `last_seen_at >= since`, so the boundary item can come back, and a verdict on it is idempotent. A dry run advances no cursor.

SECRETS. Tokens, passwords, seeds and session cookies stay inside the session objects; an error quotes the server's code and message only after `root_login._describe` has masked the secret values out of it.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol
from urllib.parse import urlencode

from rediacc_ci import paths
from rediacc_ci.ops import bench_preflight, login_bench, root_grants, root_login

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence
    from pathlib import Path

PRODUCTION_REGIONS: tuple[str, ...] = tuple(root_login.REGIONS)
BENCH = "bench"
BENCH_REGION = bench_preflight.DEFAULT_REGION
REGIONS: tuple[str, ...] = (*PRODUCTION_REGIONS, BENCH)
EXPORT_ROUTE = "/admin/feedback/export"
VERDICT_ROUTE = "/admin/feedback/verdicts"
VERDICT_BATCH_MAX = 100
TRIAGE_NOTE_MAX = 1024
# PLAN-rdc-feedback R12; the account's FEEDBACK_STATUSES (packages/shared/src/feedback/schema.ts).
STATUSES = ("new", "screening", "quarantined", "confirmed", "planned", "fixed", "rejected")
VERDICT_KEYS = ("status", "fixedIn", "planRef", "category", "triageNote")
FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")
# The `since` the account accepts (zod `datetime()`: UTC, `Z`, optional fraction).
ISO_INSTANT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
CURSOR_VERSION = 1
CURSOR_PARTS = (".ci", "cache", "feedback", "last-run.json")


class FeedbackError(RuntimeError):
    """A refusal or a failed step; `rc` is the exit status (2: refused before any request)."""

    def __init__(self, message: str, rc: int = 1):
        super().__init__(message)
        self.rc = rc


class Transport(Protocol):
    def get(self, route: str) -> tuple[int, dict]: ...

    def post(self, route: str, body: dict) -> tuple[int, dict]: ...


def _describe(status: int, answer: Mapping[str, Any]) -> str:
    return root_login._describe(status, dict(answer))


def export(
    transport: Transport, since: str | None = None, statuses: Sequence[str] = ()
) -> list[dict[str, Any]]:
    """The export items reported since `since` with a status in `statuses` (empty: every status). A non-200 answer, or an item without a 64-hex fingerprint, a known status and an ISO `lastSeenAt`, is a FeedbackError: a malformed export is contract drift, not data to guess at."""
    unknown = [s for s in statuses if s not in STATUSES]
    if unknown:
        raise FeedbackError("unknown feedback status %s" % ", ".join(unknown), rc=2)
    if since is not None and not ISO_INSTANT.match(since):
        raise FeedbackError("since %r is not a UTC ISO instant" % since, rc=2)
    query: dict[str, str] = {}
    if since:
        query["since"] = since
    if statuses:
        query["status"] = ",".join(statuses)
    route = EXPORT_ROUTE + ("?" + urlencode(query) if query else "")
    status, answer = transport.get(route)
    if status != 200:
        raise FeedbackError("GET %s answered %s" % (EXPORT_ROUTE, _describe(status, answer)))
    items = answer.get("items")
    if not isinstance(items, list):
        raise FeedbackError("GET %s answered 200 with no items list" % EXPORT_ROUTE)
    bad = 0
    for item in items:
        if not (
            isinstance(item, dict)
            and isinstance(item.get("fingerprint"), str)
            and FINGERPRINT.match(item["fingerprint"])
            and item.get("status") in STATUSES
            and isinstance(item.get("lastSeenAt"), str)
            and ISO_INSTANT.match(item["lastSeenAt"])
        ):
            bad += 1
    if bad:
        raise FeedbackError(
            "GET %s answered %d malformed item(s) of %d: no fingerprint, status or lastSeenAt "
            "of the expected shape" % (EXPORT_ROUTE, bad, len(items))
        )
    return items


def verdict(fingerprint: str, **fields: Any) -> dict[str, Any]:
    """One verdict body: the fingerprint and the fields set on every report of it. Unknown keys, an unknown status and an over-long triage note are refused before any request."""
    if not FINGERPRINT.match(fingerprint):
        raise FeedbackError("verdict fingerprint %r is not 64 hex" % fingerprint, rc=2)
    extra = sorted(set(fields) - set(VERDICT_KEYS))
    if extra:
        raise FeedbackError("verdict carries unknown field(s) %s" % ", ".join(extra), rc=2)
    if "status" in fields and fields["status"] not in STATUSES:
        raise FeedbackError("verdict status %r is not a feedback status" % fields["status"], rc=2)
    note = fields.get("triageNote")
    if isinstance(note, str) and len(note) > TRIAGE_NOTE_MAX:
        raise FeedbackError("verdict triage note exceeds %d characters" % TRIAGE_NOTE_MAX, rc=2)
    return {"fingerprint": fingerprint, **fields}


@dataclass
class VerdictResult:
    fingerprints: int = 0
    reports: int = 0
    missing: list[str] = field(default_factory=list)


def write_verdicts(transport: Transport, verdicts: Sequence[Mapping[str, Any]]) -> VerdictResult:
    """Post the verdicts in batches of VERDICT_BATCH_MAX; the totals of every batch. A non-200 batch is a FeedbackError naming how many batches had landed."""
    result = VerdictResult()
    batches = [
        list(verdicts[i : i + VERDICT_BATCH_MAX])
        for i in range(0, len(verdicts), VERDICT_BATCH_MAX)
    ]
    for done, batch in enumerate(batches):
        status, answer = transport.post(VERDICT_ROUTE, {"verdicts": [dict(v) for v in batch]})
        if status != 200:
            raise FeedbackError(
                "POST %s answered %s (%d of %d batch(es) written before it)"
                % (VERDICT_ROUTE, _describe(status, answer), done, len(batches))
            )
        result.fingerprints += int(answer.get("fingerprints") or 0)
        result.reports += int(answer.get("reports") or 0)
        missing = answer.get("missing")
        if isinstance(missing, list):
            result.missing += [str(m) for m in missing]
    return result


# ---- sessions ------------------------------------------------------------------------------------


class BenchTransport:
    """A signed-in bench `AccountApi` behind the `Transport` routes: it takes absolute API paths, so each route is put under `/account/api/v1`."""

    def __init__(self, api: Any):
        self._api = api

    def get(self, route: str) -> tuple[int, dict]:
        return self._api.get(root_login.API_ROOT + route)

    def post(self, route: str, body: dict) -> tuple[int, dict]:
        return self._api.post(root_login.API_ROOT + route, body)


@dataclass
class SessionDeps:
    """The seams `open_region` calls through; a test replaces them."""

    open_token_session: Callable[..., Any] = root_login.open_token_session
    account_api: Callable[[str], Any] = login_bench.AccountApi
    sign_in: Callable[[Any, Mapping[str, str], Any], None] = root_grants._bench_sign_in
    elevate: Callable[..., None] = login_bench.elevate
    capture: Callable[[Sequence[str], Mapping[str, str]], tuple[int, str]] = (
        login_bench._subprocess_capture
    )
    grant_deps: Any = field(default_factory=root_grants.Deps)


def profile_for(region: str) -> str:
    """The Bitwarden profile a region's session reads its credentials from."""
    if region == BENCH:
        return bench_preflight.profile_for(login_bench.PROFILE_ROLE, BENCH_REGION)
    if region in PRODUCTION_REGIONS:
        return root_login.PROFILE
    raise FeedbackError("unknown region %r: one of %s" % (region, ", ".join(REGIONS)), rc=2)


def open_region(
    region: str,
    write: bool,
    env: Mapping[str, str] | None = None,
    deps: SessionDeps | None = None,
) -> Transport:
    """A transport on `region`'s account under a root session; for bench, `write` also elevates the session (the verdict route needs it). A missing credential is FeedbackError rc 2 naming its remedy."""
    env = os.environ if env is None else env
    deps = deps or SessionDeps()
    profile_for(region)
    if region in PRODUCTION_REGIONS:
        try:
            return deps.open_token_session("edge", region, env)
        except root_login.RootLoginError as exc:
            text = "%s: %s" % (region, root_login.masked(str(exc), env))
            if exc.rc == 2:
                text += "; remedy: mint the root API token for %s and store it as %s" % (
                    region,
                    root_login.token_entry(region),
                )
            raise FeedbackError(text, rc=exc.rc) from None
    try:
        values = login_bench.read_values(env, BENCH_REGION)
        api = deps.account_api(login_bench.target_for(BENCH_REGION).server)
        deps.sign_in(api, values, deps.grant_deps)
        if write:
            deps.elevate(
                api,
                values[login_bench.EMAIL_ENV],
                login_bench.base_env(env),
                deps.capture,
                deps.grant_deps.now,
                BENCH_REGION,
            )
    except login_bench.LoginError as exc:
        text = "%s: %s" % (BENCH, exc)
        if exc.rc == 2:
            text += "; remedy: %s" % login_bench.remedy_for(BENCH_REGION)[0]
        raise FeedbackError(text, rc=exc.rc) from None
    return BenchTransport(api)


# ---- the cursor ----------------------------------------------------------------------------------


def cursor_path() -> Path:
    return paths.from_root(*CURSOR_PARTS)


def read_cursor(path: Path) -> dict[str, dict[str, str]]:
    """The per-region cursor rows; an absent file is no cursor. An unreadable or foreign-shaped file is FeedbackError rc 2: it is never reset silently."""
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError as exc:
        raise FeedbackError("cannot read %s (%s)" % (path, type(exc).__name__), rc=2) from None
    try:
        doc = json.loads(raw)
    except ValueError:
        doc = None
    regions = doc.get("regions") if isinstance(doc, dict) else None
    if (
        not isinstance(doc, dict)
        or doc.get("version") != CURSOR_VERSION
        or not isinstance(regions, dict)
    ):
        raise FeedbackError(
            "%s is not a version %d feedback cursor; remove it to export from the start"
            % (path, CURSOR_VERSION),
            rc=2,
        )
    return {
        str(k): {kk: str(vv) for kk, vv in v.items()}
        for k, v in regions.items()
        if isinstance(v, dict)
    }


def cursor_since(rows: Mapping[str, Mapping[str, str]], region: str) -> str | None:
    """The `since` recorded for `region`, when it is an instant the account accepts."""
    since = (rows.get(region) or {}).get("since")
    return since if since and ISO_INSTANT.match(since) else None


def next_since(items: Sequence[Mapping[str, Any]], previous: str | None) -> str | None:
    """The newest `lastSeenAt` among the items, or `previous` when there is none newer."""
    seen = [str(i["lastSeenAt"]) for i in items if ISO_INSTANT.match(str(i.get("lastSeenAt")))]
    candidates = [s for s in (*seen, previous) if s]
    return max(candidates) if candidates else None


def write_cursor(path: Path, region: str, since: str | None, ran_at: str) -> None:
    """Record `region`'s cursor, keeping the other regions' rows; written through a sibling temp file and a rename."""
    rows = read_cursor(path)
    row = {"ranAt": ran_at}
    if since:
        row["since"] = since
    rows[region] = row
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps({"version": CURSOR_VERSION, "regions": rows}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)
