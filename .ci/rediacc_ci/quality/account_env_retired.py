r"""check:ci-account-env-retired -- `private/account/.env` and `.env.bench` stay retired.

WHAT RETIRED THEM. `agent/plans/PLAN-account-env-to-bws.md`: Bitwarden (project `ci-shared`) is the single source of truth. Every local secret reaches a process through `python3 -m rediacc_ci.core.bws_env exec --profile P` (profiles under `consumers` in `.ci/config/secret-supply.json`), the non-secret constants are the committed `private/account/dev.defaults.env`, and the one credential the store cannot hold, the machine-account token, lives in its own 0600 file outside the repository (`bws_env.token_path()`). This gate keeps the file from coming back through any of the doors it used to be opened by.

THE CLAUSES.

  1. NO NEW MENTION. No tracked file in console or its submodules names the
     account env files (`account/.env`, `$ACCOUNT_DIR/.env`, `.env.bench`) or a
     rotation `local:.env*` consumer, outside the EXCLUDED prefixes below. A
     mention is not always a reader, and that is deliberate: prose that tells a
     reader to put a value in the file is how the file comes back, so it is held
     to the same rule. THE MENTIONS THAT PREDATE THIS GATE are a SHRINK-ONLY
     BASELINE, `.ci/config/account-env-retired-baseline.json`, keyed by path with
     a count. A file whose count rises, or a file that is not in it, reds as NEW.
     A file whose count FELL reds as STALE until the baseline is lowered with
     `--write-baseline`, which only ever shrinks it: a baseline that keeps an
     entry nothing needs is how an allowance outlives its reason.
  2. EACH EXCLUSION IS RE-DERIVED. An excluded prefix must still name a tracked
     path; one that matches nothing is a dead exemption and reds.
  3. THE DOTENV TABLE ONLY SHRINKS. `dotenv.names` in secret-supply.json may hold
     no more names than the baseline's `dotenv_names`. At zero (the terminal
     state, T18) the table must be empty and `bootstrap_names` exactly
     `["BWS_ACCESS_TOKEN"]`.
  4. THE TOKEN IS OUTSIDE THE REPOSITORY. `bws_env.token_path()` for this
     process must not resolve under the repository root, where one `git add -A`
     would publish the credential that opens every other one.

ANTI-VACUITY. Zero tracked files is a REFUSAL (the instrument lost the tree). An EMPTY baseline beside an empty scan is the terminal state and passes, printing zero; no typed floor, because a floor on a number that is supposed to fall reds on success.

Exit 1 on a finding or refusal, 2 on a failed control.
"""

from __future__ import annotations

import collections
import json
import os
import pathlib
import re
import subprocess
import sys

from rediacc_ci import log, paths
from rediacc_ci.controls import Checker, controls_first, plant
from rediacc_ci.quality import shrink_only

BASELINE_REL = ".ci/config/account-env-retired-baseline.json"
SUPPLY_REL = ".ci/config/secret-supply.json"

# `account/.env` and `$ACCOUNT_DIR/.env` NOT followed by `.` or a word character, so `.env.example` of another package and `dev.defaults.env` never match; `.env.bench` anywhere; and the rotation consumer spelling `local:.env`.
MENTION_RE = re.compile(
    r"(?:account/|ACCOUNT_DIR/|ACCOUNT_DIR\}/)\.env(?![.\w])|\.env\.bench\b|local:\.env"
)

# Paths never scanned, each with its reason. Re-derived by clause 2.
EXCLUDED = {
    "agent/": "plans, ledgers and worklists: the record of the migration itself",
    ".ci/shadow/": "shadow-gate observation ledgers: recorded history, never edited",
    ".ci/rediacc_ci/tests/goldens/": "recorded bytes of deleted twins, compared, never edited",
    "packages/www/public/search-index": "generated from the docs corpus at build time",
    ".ci/rediacc_ci/quality/account_env_retired.py": "this gate: asserting a file has not come back requires naming it",
    ".ci/scripts/quality/check_account_env_retired.py": "this gate's entry point",
    ".ci/rediacc_ci/tests/test_quality_account_env_retired.py": "this gate's test",
    BASELINE_REL: "the baseline names the files it forgives",
    ".ci/rediacc_ci/tests/test_devbox_bws.py": "plants the retired file to prove the devbox hook never reads it",
    ".ci/rediacc_ci/tests/test_setup_account_bws.py": "plants the retired files to prove setup refuses to continue while either exists",
}


class RefusalError(Exception):
    """No verdict can be reached. Exit 1, never a silent pass."""


def tracked(root: pathlib.Path) -> list[str]:
    """Every tracked path, submodules included, relative to `root`."""
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--recurse-submodules"],
        capture_output=True,
        check=False,
    )
    files = [p for p in out.stdout.decode("utf-8", "replace").split("\0") if p]
    if out.returncode != 0 or not files:
        raise RefusalError(
            "`git ls-files` returned %d file(s) (rc=%d) in %s. Zero tracked files is the "
            "instrument losing the tree, not a clean one." % (len(files), out.returncode, root)
        )
    return files


def excluded(rel: str) -> bool:
    return any(rel == p or rel.startswith(p) for p in EXCLUDED)


def scan(root: pathlib.Path, files: list[str]) -> dict[str, int]:
    """{path: mention count} over every tracked, non-excluded text file."""
    counts: dict[str, int] = collections.Counter()
    for rel in files:
        if excluded(rel):
            continue
        path = root / rel
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if b"\0" in data[:4096]:
            continue
        hits = len(MENTION_RE.findall(data.decode("utf-8", "replace")))
        if hits:
            counts[rel] = hits
    return dict(counts)


def load_baseline(root: pathlib.Path) -> dict:
    path = root / BASELINE_REL
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RefusalError(
            "%s is missing or unreadable (%s). Without it every mention reds as NEW; "
            "restore it from git rather than regenerating it wider." % (BASELINE_REL, exc)
        ) from exc
    if not isinstance(doc.get("mentions"), dict) or not isinstance(doc.get("dotenv_names"), int):
        raise RefusalError(
            "%s needs a `mentions` object and an integer `dotenv_names`." % BASELINE_REL
        )
    return doc


def evaluate_mentions(found: dict[str, int], allowed: dict[str, int]) -> list[str]:
    findings = []
    for rel in sorted(found):
        have, may = found[rel], allowed.get(rel, 0)
        if have > may:
            findings.append(
                "NEW %s: %d mention(s) of the retired account env files, baseline allows %d. "
                "Read the value through `bws_env exec --profile ...` (.ci/config/secret-supply.json "
                "`consumers`) instead of a file; do not widen the baseline." % (rel, have, may)
            )
    for rel in sorted(allowed):
        have = found.get(rel, 0)
        if have < allowed[rel]:
            findings.append(
                "STALE %s: baseline allows %d mention(s) and the file now has %d. The drain "
                "landed: lower the baseline with `%s --write-baseline`."
                % (rel, allowed[rel], have, ".ci/scripts/quality/check_account_env_retired.py")
            )
    return findings


def evaluate_exclusions(files: list[str], root: pathlib.Path | None = None) -> list[str]:
    """A prefix is live when a tracked path matches it or, for this gate's own files, it exists on disk (a new gate is untracked until its first commit)."""
    return [
        "DEAD EXCLUSION %s: no tracked path matches it any more (%s). Delete the entry."
        % (prefix, why)
        for prefix, why in sorted(EXCLUDED.items())
        if not any(f == prefix or f.startswith(prefix) for f in files)
        and not (root is not None and (root / prefix).is_file())
    ]


def evaluate_supply(spec: dict, ceiling: int) -> list[str]:
    names = (spec.get("dotenv") or {}).get("names") or {}
    findings = []
    if len(names) > ceiling:
        findings.append(
            "DOTENV GREW: %s routes %d name(s) out of private/account/.env, baseline ceiling %d. "
            "The table only shrinks; a new name belongs in a `consumers` profile."
            % (SUPPLY_REL, len(names), ceiling)
        )
    if ceiling == 0:
        if names:
            findings.append("DOTENV NOT EMPTY: the terminal state routes no name at all.")
        if spec.get("bootstrap_names") != ["BWS_ACCESS_TOKEN"]:
            findings.append(
                'BOOTSTRAP RULING: `bootstrap_names` must be exactly ["BWS_ACCESS_TOKEN"] in the '
                "terminal state, and it is %r." % (spec.get("bootstrap_names"),)
            )
    return findings


def evaluate_token_path(token: str, root: pathlib.Path) -> list[str]:
    real_root = os.path.realpath(root)
    real_token = os.path.realpath(token)
    if real_token == real_root or real_token.startswith(real_root + os.sep):
        return [
            "TOKEN INSIDE THE REPOSITORY: the bootstrap token path %s resolves under %s, where "
            "`git add -A` would publish it." % (token, root)
        ]
    return []


def run(root=None, env=None):
    root = pathlib.Path(root or paths.repo_root())
    from rediacc_ci.core import bws_env  # noqa: PLC0415

    files = tracked(root)
    baseline = load_baseline(root)
    try:
        spec = json.loads((root / SUPPLY_REL).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RefusalError("%s is missing or unreadable (%s)." % (SUPPLY_REL, exc)) from exc
    found = scan(root, files)
    findings = evaluate_mentions(found, baseline["mentions"])
    findings += evaluate_exclusions(files, root)
    findings += evaluate_supply(spec, baseline["dotenv_names"])
    findings += evaluate_token_path(bws_env.token_path(env), root)
    stats = {
        "files": len(files),
        "mentions": sum(found.values()),
        "mention_files": len(found),
        "baseline_files": len(baseline["mentions"]),
        "dotenv": len((spec.get("dotenv") or {}).get("names") or {}),
        "ceiling": baseline["dotenv_names"],
    }
    return findings, stats, found, spec


def _mention_id(rel: str, k: int) -> str:
    return "%s#%d" % (rel, k)


def write_baseline(root: pathlib.Path) -> int:
    """Shrink the baseline to the tree. Never adds a file or raises a count."""
    files = tracked(root)
    old = load_baseline(root)
    found = scan(root, files)
    spec = json.loads((root / SUPPLY_REL).read_text(encoding="utf-8"))
    # THE ADD DECISION IS `shrink_only`'s, the one every Python shrink-only baseline shares. The baseline is a MULTISET (path -> count), so each mention becomes one id, `path#k`: a file new to the baseline and a file whose count rose both surface as additions, and a file that only fell does not.
    added = shrink_only.baseline_additions(
        [_mention_id(r, k) for r, n in old["mentions"].items() for k in range(n)],
        [_mention_id(r, k) for r, n in found.items() for k in range(n)],
    )
    grown = sorted({entry.rsplit("#", 1)[0] for entry in added})
    if shrink_only.write_verdict(baseline_exists=True, first_seed=False, additions=added):
        log.error(
            "refusing: %d file(s) would GROW the baseline: %s"
            % (len(grown), ", ".join(sorted(grown)))
        )
        return 1
    doc = dict(old)
    doc["mentions"] = {r: found[r] for r in sorted(found)}
    doc["dotenv_names"] = min(
        old["dotenv_names"], len((spec.get("dotenv") or {}).get("names") or {})
    )
    (root / BASELINE_REL).write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    log.success(
        "baseline shrunk to %d file(s), dotenv ceiling %d"
        % (len(doc["mentions"]), doc["dotenv_names"])
    )
    return 0


def main(argv=None) -> int:
    argv = list(argv or [])
    if "--selftest" in argv:
        return 1 if selftest() else 0
    if "--write-baseline" in argv:
        try:
            return write_baseline(pathlib.Path(paths.repo_root()))
        except RefusalError as exc:
            log.error("account env retired: %s" % exc)
            return 1
    rc = controls_first("account env retired", selftest)
    if rc:
        return rc
    try:
        findings, stats, _found, _spec = run()
    except RefusalError as exc:
        log.error("account env retired: %s" % exc)
        return 1
    log.info(
        "  %d tracked file(s) scanned; %d mention(s) in %d file(s) against a %d-file baseline; "
        "dotenv table %d name(s), ceiling %d"
        % (
            stats["files"],
            stats["mentions"],
            stats["mention_files"],
            stats["baseline_files"],
            stats["dotenv"],
            stats["ceiling"],
        )
    )
    if findings:
        for finding in findings:
            log.error("  %s" % finding)
        log.error("%d finding(s): the account env files must stay retired." % len(findings))
        return 1
    log.success(
        "account env retired: no new mention, no dead exclusion, token outside the repository"
    )
    return 0


# --------------------------------------------------------------------------- controls ---------------------------------------------------------------------------

_SUPPLY = {"bootstrap_names": ["BWS_ACCESS_TOKEN"], "dotenv": {"names": {}}}


def _fixture(tmp, files: dict[str, str], baseline: dict | None = None, supply: dict | None = None):
    root = pathlib.Path(tmp)
    body = dict(files)
    body.setdefault(SUPPLY_REL, json.dumps(supply if supply is not None else _SUPPLY))
    body.setdefault(BASELINE_REL, json.dumps(baseline or {"mentions": {}, "dotenv_names": 0}))
    for prefix in EXCLUDED:
        if prefix.endswith("/"):
            body.setdefault(prefix + "keep.txt", "excluded\n")
        elif prefix not in body:
            body[prefix] = "excluded\n"
    for rel, text in body.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    for args in (["init", "-q"], ["add", "-A", "-f", "."]):
        subprocess.run(["git", "-C", str(root), *args], check=False, capture_output=True)
    return root


def _findings(root, env=None) -> list[str]:
    return run(root, env or {"HOME": "/nonexistent-home"})[0]


def selftest() -> bool:
    """True when a control failed, which is what `controls_first` expects."""
    import tempfile  # noqa: PLC0415

    check = Checker()
    clean_script = "#!/bin/bash\nPYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile account-dev -- x\n"
    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp, {"scripts/run.sh": clean_script})
        check("CONTROL: a tree that reads the store is clean", _findings(root) == [])
    with tempfile.TemporaryDirectory() as tmp:
        planted = plant(
            clean_script,
            "exec --profile account-dev -- x",
            'sed -n "s/^K=//p" private/account/.env',
        )
        root = _fixture(tmp, {"scripts/run.sh": planted})
        check(
            "PLANT: a `sed` of private/account/.env in a script reds as NEW",
            any(f.startswith("NEW scripts/run.sh") for f in _findings(root)),
        )
    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp, {"rotation.json": '{"consumers": ["local:.env.bench"]}\n'})
        check(
            "PLANT: a `local:.env` rotation consumer reds",
            any(f.startswith("NEW rotation.json") for f in _findings(root)),
        )
    with tempfile.TemporaryDirectory() as tmp:
        grown = {
            "bootstrap_names": ["BWS_ACCESS_TOKEN"],
            "dotenv": {"names": {"ROOT_EMAIL": "ci-shared"}},
        }
        root = _fixture(tmp, {}, supply=grown)
        check(
            "PLANT: a re-added dotenv name reds against a zero ceiling",
            any(f.startswith("DOTENV GREW") for f in _findings(root)),
        )
    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp, {})
        inside = {"HOME": "/x", "BWS_ACCESS_TOKEN_FILE": str(root / "private" / "bws-access-token")}
        check(
            "PLANT: a token path moved under the repository reds",
            any(f.startswith("TOKEN INSIDE") for f in _findings(root, inside)),
        )
    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(
            tmp,
            {"docs/a.md": "put it in private/account/.env\n"},
            baseline={"mentions": {"docs/a.md": 2}, "dotenv_names": 0},
        )
        check(
            "CONTROL: a mention count that FELL reds as STALE, so the baseline drains",
            any(f.startswith("STALE docs/a.md") for f in _findings(root)),
        )
    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(
            tmp,
            {"docs/a.md": "put it in private/account/.env\n"},
            baseline={"mentions": {"docs/a.md": 1}, "dotenv_names": 0},
        )
        check(
            "ANTI-SILENCER: a baselined mention at its count is not a finding",
            _findings(root) == [],
        )
    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(
            tmp,
            {
                "x/dev.defaults.env": "PORT=1\n",
                "y.md": "see private/account/.env.example and dev.defaults.env\n",
            },
        )
        check(
            "ANTI-SILENCER: `.env.example` and `dev.defaults.env` are not the retired files",
            _findings(root) == [],
        )
    check(
        "ANTI-SILENCER: an exclusion that matches nothing is reported, not ignored",
        evaluate_exclusions(["other/file"]) != [],
    )
    check(
        "CONTROL: the terminal ruling on bootstrap_names is enforced at a zero ceiling",
        any(
            f.startswith("BOOTSTRAP RULING")
            for f in evaluate_supply({"bootstrap_names": ["A", "B"], "dotenv": {"names": {}}}, 0)
        ),
    )
    return not check.ok


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
