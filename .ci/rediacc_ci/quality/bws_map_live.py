"""check:ci-bws-map-live -- every name the committed Bitwarden map holds is still a secret in the live store.

WHY THIS EXISTS. `.ci/config/bws-secret-map.json` translates a NAME to the UUID bitwarden/sm-action fetches, and `check:ci-bws-map` proves everything about it that can be proven offline. It deliberately does not ask the store (its docstring, "DELIBERATELY NOT ASSERTED"), so a secret deleted from Bitwarden lingers in the map until a job that requests it fails at run time. R2_TOKEN_AUTH_API was exactly that until fb66caff3 removed it by hand. The operator's ask (#9b35d60c): "a check that compares the names in bws-secret-map.json with the live store, using bws names only and never values, so a deleted secret can't linger in the maps. It's advisory when no BWS token is present."

WHAT IS COMPARED, by NAME and by the UUID the map holds for it (an id is a pointer, never a credential, which is why the map may carry it in a public repository):

  LINGERING   a mapped name the project no longer has. Refused.
  MOVED       a mapped name whose live UUID is not the mapped one: the secret was
              deleted and re-created, and the map points at the dead UUID. Refused.
  EXEMPT      a `.ci/config/bws-unrequested.json` exemption naming a secret the
              project no longer has, for every kind that claims a stored secret.
              Refused, because an exemption for nothing is a reason nobody re-reads.
              `superseded-at-runtime` names a SUFFIX-built name the deploy script
              throws away, which the store need not hold, so it is skipped and counted.
  STORE-ONLY  a live name the map lacks. Reported, not refused: the map is the
              set CI may request, and a stored secret no workflow asks for yet is
              `bws-map-refresh.py`'s to add, not a defect.
  ARCHIVE     a live `__ROTATED_<stamp>` clone. Reported with the command that
              deletes it, exactly as the refresh reports it.

NEVER A VALUE. `bws secret list` returns each secret's decrypted value beside its id and key. The listing is `scripts/ops/bws-map-refresh.py`'s own `list_live`, loaded BY PATH (that file cannot import `rediacc_ci` and this one must not hop `sys.path` into `scripts/ops`; `spec_from_file_location` is the tree's by-file load), and its first act on a row is the projection to {id, key, projectId}. One listing function serves the refresh and this gate, so the projection cannot drift between them. The controls plant a sentinel value into a fake `bws`'s output and assert it appears nowhere in what `list_live` returns, nor in the error a failing `bws` raises.

WHERE IT RUNS, AND WHY NOT IN CI. The token is present in CI (`secrets.BWS_ACCESS_TOKEN`, which the bws-secrets action hands to bitwarden/sm-action), but the `bws` CLI is not: sm-action fetches by UUID through its own client and no CI job installs the CLI. A CI step would therefore SKIP on every run, a step that cannot fail. So the gate is `local-only` and runs in `npm run ci` and `npm run ci:quick` on a developer machine, where `bws_env.read_token` finds `~/.config/rediacc/bws-access-token` and the CLI sits on PATH or at `~/.local/bin/bws`. That puts it in the pre-push receipt of every push made from such a machine.

NO TOKEN OR NO CLI IS CANNOT RUN, NOT GREEN. The operator asked for it to be advisory without a token, and the runner already has the shape for that: exit 77 is `blocked` in `scripts/ci-runner/pool.ts`, which does not redden the run or the push and IS counted in the footer and recorded in the receipt. Exit 0 would record "the live store agrees" for a comparison that never happened. A token that IS present and a listing that fails (expired credential, rate limit, network) is a FAILURE: the comparison was possible and did not happen, and the rotation notice the refresh prints says which.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import pathlib
import sys
import tempfile
from typing import TYPE_CHECKING

from rediacc_ci import log, paths
from rediacc_ci.controls import Checker, controls_first
from rediacc_ci.core import bws_env

if TYPE_CHECKING:
    import types

MAP_REL = ".ci/config/bws-secret-map.json"
UNREQUESTED_REL = ".ci/config/bws-unrequested.json"
REFRESH_REL = "scripts/ops/bws-map-refresh.py"

#: `bws-unrequested.json` kinds whose name is a SUFFIX-built read the store need not hold. Every other kind claims a stored secret.
NOT_STORED_KINDS = frozenset({"superseded-at-runtime"})

#: Where the CLI lives when it is not on PATH: the operator's install, then the devcontainer's.
BWS_FALLBACKS = ("~/.local/bin/bws", "/usr/local/bin/bws")

CANNOT_RUN = 77


class CannotRunError(Exception):
    """The instrument cannot produce a verdict here."""


def load_refresh(root: pathlib.Path) -> types.ModuleType:
    """`scripts/ops/bws-map-refresh.py`, loaded by path. Its listing is the one this gate uses."""
    path = root / REFRESH_REL
    spec = importlib.util.spec_from_file_location("bws_map_refresh", path)
    if spec is None or spec.loader is None:
        raise CannotRunError("cannot load %s" % path)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except (OSError, SyntaxError) as exc:
        raise CannotRunError("cannot load %s (%s)" % (path, exc)) from exc
    for name in (
        "list_live",
        "project_listing",
        "split_archives",
        "listing_problems",
        "ListingError",
    ):
        if not hasattr(module, name):
            raise CannotRunError(
                "%s no longer defines %s, so the shared listing is gone" % (REFRESH_REL, name)
            )
    return module


def find_bws(env: dict[str, str] | None = None, fallbacks: tuple[str, ...] = BWS_FALLBACKS) -> str:
    found = bws_env.binary(env)
    if found:
        return found
    for candidate in fallbacks:
        path = os.path.expanduser(candidate)
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return ""


def compare(
    map_ids: dict[str, str],
    exemptions: dict[str, str],
    live_ids: dict[str, str],
) -> dict[str, list[str]]:
    """The comparison, by name, pure. `exemptions` is name -> kind; ids are compared, never printed."""
    expected_exempt = {n for n, kind in exemptions.items() if kind not in NOT_STORED_KINDS}
    return {
        "lingering": sorted(set(map_ids) - set(live_ids)),
        "moved": sorted(n for n in set(map_ids) & set(live_ids) if map_ids[n] != live_ids[n]),
        "exempt_lingering": sorted(expected_exempt - set(live_ids)),
        "store_only": sorted(set(live_ids) - set(map_ids)),
        "not_stored": sorted(set(exemptions) - expected_exempt),
    }


def read_map(root: pathlib.Path) -> tuple[str, dict[str, str], dict[str, str]]:
    try:
        doc = json.loads((root / MAP_REL).read_text(encoding="utf-8"))
        unrequested = json.loads((root / UNREQUESTED_REL).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CannotRunError("cannot read the map (%s)" % exc) from exc
    project = str(doc.get("project") or "")
    secrets = doc.get("secrets") or {}
    map_ids = {str(k): str((v or {}).get("id") or "") for k, v in secrets.items()}
    exemptions = {
        str(k): str((v or {}).get("kind") or "")
        for k, v in (unrequested.get("exemptions") or {}).items()
    }
    if not project or not map_ids:
        raise CannotRunError(
            "%s has no project or no secrets; there is nothing to compare" % MAP_REL
        )
    return project, map_ids, exemptions


def run(
    root: pathlib.Path,
    env: dict[str, str] | None = None,
    fallbacks: tuple[str, ...] = BWS_FALLBACKS,
) -> int:
    environ = dict(os.environ if env is None else env)
    project, map_ids, exemptions = read_map(root)
    bws = find_bws(environ, fallbacks)
    try:
        token = bws_env.read_token(environ)
    except bws_env.RefusalError as exc:
        for line in exc.lines:
            log.error(line)
        return 1
    if not token or not bws:
        missing = [
            what for what, have in (("a BWS token", token), ("the bws CLI", bws)) if not have
        ]
        log.warn(
            "bws map live: SKIP, CANNOT RUN here: missing %s. The %d mapped name(s) were NOT compared "
            "with the live store. Install the token at %s (mode 0600) and bws as "
            ".devcontainer/Dockerfile does (or at ~/.local/bin/bws), then rerun "
            "`npm run check:ci-bws-map-live`."
            % (" and ".join(missing), len(map_ids), bws_env.token_path(environ))
        )
        return CANNOT_RUN
    refresh = load_refresh(root)
    environ[bws_env.ACCESS_ENV] = token
    try:
        entries = refresh.list_live(bws, project, env=environ)
    except refresh.ListingError as exc:
        for line in exc.notice:
            log.error(line)
        log.error(
            "bws map live: the live store could not be listed, so nothing was compared: %s"
            % exc.message
        )
        return 1
    del token, environ
    entries, archives = refresh.split_archives(entries)
    problems = refresh.listing_problems(entries, project)
    if problems:
        for p in problems:
            log.error("bws map live: %s" % p)
        return 1
    live_ids = {e["key"]: e["id"] for e in entries}
    got = compare(map_ids, exemptions, live_ids)
    log.info(
        "  %d mapped name(s), %d live in project %s, %d unrequested exemption(s) (%d not expected "
        "in the store); %d lingering, %d moved, %d exemption(s) lingering, %d store-only, %d archive clone(s)"
        % (
            len(map_ids),
            len(live_ids),
            project,
            len(exemptions),
            len(got["not_stored"]),
            len(got["lingering"]),
            len(got["moved"]),
            len(got["exempt_lingering"]),
            len(got["store_only"]),
            len(archives),
        )
    )
    for name in got["store_only"]:
        log.warn(
            "  STORE-ONLY %s is live but not mapped; add it with scripts/ops/bws-map-refresh.py"
            % name
        )
    for name in archives:
        log.warn(
            "  ARCHIVE %s is a rotation clone; delete it: ./run.sh rotation bws-gc --apply" % name
        )
    for name in got["lingering"]:
        log.error(
            "  LINGERING %s is in %s but not in the live store: remove every request for it, then "
            "run scripts/ops/bws-map-refresh.py" % (name, MAP_REL)
        )
    for name in got["moved"]:
        log.error(
            "  MOVED %s resolves to a different UUID in the live store than in %s (deleted and "
            "re-created): run scripts/ops/bws-map-refresh.py" % (name, MAP_REL)
        )
    for name in got["exempt_lingering"]:
        log.error(
            "  EXEMPT %s is exempted in %s but is not in the live store: delete the exemption"
            % (name, UNREQUESTED_REL)
        )
    refused = len(got["lingering"]) + len(got["moved"]) + len(got["exempt_lingering"])
    if refused:
        log.error(
            "bws map live: %d name(s) in the maps that the live store does not back" % refused
        )
        return 1
    log.success(
        "bws map live: every one of the %d mapped name(s) is live, at its mapped UUID"
        % len(map_ids)
    )
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--selftest" in argv:
        return 1 if selftest() else 0
    rc = controls_first("bws map live", selftest)
    if rc:
        return rc
    try:
        return run(pathlib.Path(paths.repo_root()))
    except CannotRunError as exc:
        log.error("bws map live: CANNOT RUN: %s" % exc)
        return 2


# --------------------------------------------------------------------------- controls

SENTINEL = "SENTINEL-VALUE-must-never-survive-7f3a"
PROJECT = "11111111-2222-3333-4444-555555555555"

_FAKE_BWS = """#!%(python)s
import json, sys
argv = sys.argv[1:]
if argv[:2] != ["--color", "no"]:
    sys.stderr.write("fake bws: --color no is load-bearing and was not passed\\n")
    sys.exit(3)
rows = [
    {"id": "%(uuid)s", "key": "ALPHA", "projectId": "%(project)s",
     "value": "%(sentinel)s", "note": "%(sentinel)s", "organizationId": "o"},
]
if "%(mode)s" == "fail":
    sys.stdout.write(json.dumps(rows))
    sys.stderr.write("Error: [401 Unauthorized] invalid token\\n")
    sys.exit(1)
sys.stdout.write(json.dumps(rows))
"""


def _fake_bws(directory: pathlib.Path, mode: str) -> str:
    path = directory / ("bws-%s" % mode)
    path.write_text(
        _FAKE_BWS
        % {
            "python": sys.executable,
            "uuid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "project": PROJECT,
            "sentinel": SENTINEL,
            "mode": mode,
        },
        encoding="utf-8",
    )
    path.chmod(0o700)
    return str(path)


def selftest() -> bool:
    """True when a control failed, which is what `controls_first` expects."""
    check = Checker()
    root = pathlib.Path(paths.repo_root())
    try:
        refresh = load_refresh(root)
    except CannotRunError as exc:
        check("CONTROL: the refresh's shared listing loads by path (%s)" % exc, False)
        return True

    raw = [
        {
            "id": "i",
            "key": "K",
            "projectId": "p",
            "value": SENTINEL,
            "note": SENTINEL,
            "extra": SENTINEL,
        }
    ]
    projected = refresh.project_listing(raw)
    check(
        "CONTROL: the projection keeps exactly {id, key, projectId}",
        [sorted(r) for r in projected] == [["id", "key", "projectId"]],
    )
    check("CONTROL: no planted value survives the projection", SENTINEL not in repr(projected))

    with tempfile.TemporaryDirectory(prefix="bws-map-live-") as tmp:
        base = pathlib.Path(tmp)
        env = {**os.environ, bws_env.ACCESS_ENV: "fake-token"}
        good = _fake_bws(base, "ok")
        try:
            entries = refresh.list_live(good, PROJECT, env=env)
        except refresh.ListingError as exc:
            entries = []
            check("CONTROL: the fake bws lists (%s)" % exc.message, False)
        check(
            "CONTROL: through the real subprocess path, list_live returns the name and id",
            [(e["key"], e["id"]) for e in entries]
            == [("ALPHA", "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")],
        )
        check(
            "CONTROL: through the real subprocess path, no value survives list_live",
            SENTINEL not in repr(entries),
        )
        bad = _fake_bws(base, "fail")
        raised = None
        try:
            refresh.list_live(bad, PROJECT, env=env)
        except refresh.ListingError as exc:
            raised = exc
        check("PLANT: a failing bws raises ListingError", raised is not None)
        check(
            "CONTROL: a failing bws's stdout (which may carry values) is in neither the error nor the notice",
            raised is not None
            and SENTINEL not in raised.message
            and SENTINEL not in "\n".join(raised.notice),
        )

    clean = compare({"A": "1", "B": "2"}, {"B": "no-github-twin"}, {"A": "1", "B": "2"})
    check(
        "CONTROL: a map the store backs exactly has no finding",
        not (
            clean["lingering"] or clean["moved"] or clean["exempt_lingering"] or clean["store_only"]
        ),
    )
    gone = compare({"A": "1", "R2_TOKEN_AUTH_API": "9"}, {}, {"A": "1"})
    check(
        "PLANT: a mapped name deleted from the store is LINGERING",
        gone["lingering"] == ["R2_TOKEN_AUTH_API"],
    )
    moved = compare({"A": "1"}, {}, {"A": "2"})
    check("PLANT: a name re-created under a new UUID is MOVED", moved["moved"] == ["A"])
    exempt = compare({"A": "1"}, {"B": "no-github-twin"}, {"A": "1"})
    check(
        "PLANT: an exemption naming no live secret is refused", exempt["exempt_lingering"] == ["B"]
    )
    runtime = compare({"A": "1"}, {"A_ASIA": "superseded-at-runtime"}, {"A": "1"})
    check(
        "CONTROL: a superseded-at-runtime name need not be stored",
        runtime["exempt_lingering"] == [] and runtime["not_stored"] == ["A_ASIA"],
    )
    extra = compare({"A": "1"}, {}, {"A": "1", "NEW": "3"})
    check(
        "CONTROL: a live name the map lacks is STORE-ONLY, reported",
        extra["store_only"] == ["NEW"] and not extra["lingering"],
    )

    with tempfile.TemporaryDirectory(prefix="bws-map-live-") as tmp:
        bare = {"HOME": tmp, "PATH": tmp}
        buf = io.StringIO()
        log.reset(stream=buf, colour=False)
        try:
            rc = run(root, bare, fallbacks=())
        finally:
            log.reset()
        check(
            "PLANT: with no token and no CLI the gate CANNOT RUN (77), it does not pass",
            rc == CANNOT_RUN,
        )
        check(
            "CONTROL: the skip is loud: it says SKIP and that the names were NOT compared",
            "SKIP" in buf.getvalue() and "NOT compared" in buf.getvalue(),
        )
    print("  %d control(s) ran" % check.count)
    return not check.ok


__all__ = ["compare", "find_bws", "load_refresh", "main", "run", "selftest"]
