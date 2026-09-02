#!/usr/bin/env python3
"""check:ci-bws-map -- every secret a workflow requests from Bitwarden must be
one the committed map can resolve, and the map must be fresh.

THE GATE THIS REPLACES. check-workflow-gates.sh CHECK 2 proves that a reusable
workflow reads only secrets its caller passes, by comparing `secrets.X` reads
against `secrets:` declarations. It exists because OTLP_CLIENT_CREDENTIALS once
shipped EMPTY to every account Worker and nothing caught it. The moment secrets
arrive as $GITHUB_ENV injections from bitwarden/sm-action, there is no
`secrets.X` left to read, CHECK 2's USE_RE matches nothing, and it goes green
asserting nothing. This gate is its replacement on the Bitwarden side, and it
must be in place BEFORE the first workflow flips.

WHAT IS ASSERTED
  1. every NAME requested through .github/actions/bws-secrets exists in
     .ci/config/bws-secret-map.json  -- a name the map lacks fails the job at
     run time, but only at run time, in whatever job first needs it;
  2. every env name produced is a legal shell identifier;
  3. the map is not stale (refreshed within MAX_MAP_AGE_DAYS);
  4. the map is not vacuous (a floor on entries, and a per-entry UUID shape).

DELIBERATELY NOT ASSERTED
  - that a UUID is live in Bitwarden. That needs the machine-account token,
    and a gate that needs a token is a gate that silently degrades to "passed"
    wherever the token is absent -- the same reasoning check_secret_reachability
    records at its own top. Liveness is proven at run time, where a missing
    UUID fails the whole fetch (verified 2026-09-02: /secrets/get-by-ids returns
    404 for the entire request if ANY id is missing).
  - that a value is non-empty. sm-action exports "" without complaint and zod
    normalises "" to undefined; that is the deploy scripts' non-empty guards.

CALLER FLOOR. The shadow-run wired 20 workflow files to the composite on
2026-09-02, so MIN_CALLERS is 20: an edit that silently drops the wiring from a
file now fails here instead of quietly narrowing what the shadow compares.
Raise it when a new workflow gains the composite; never lower it to get past
a red.

COVERAGE, ADDED 2026-09-02, AND WHY ONE DIRECTION WAS NEVER ENOUGH.
Assertion 1 is `requested SUBSET-OF map`. Measured on the real tree, 53 secrets
were mapped and 35 requested, and the 18-name gap was an EXACT BIJECTION with
"has no GitHub secret of that name" -- the shadow's left operand is a GitHub
secret, so a name with no twin has nothing to compare against. That is one
mechanical consequence, not eighteen decisions. But nothing said so, and nothing
would have noticed a nineteenth that was a real omission. Three more assertions,
each the converse of something already checked:

  5. COVERAGE. Every name in the map is requested by some call site, or carries
     an entry in .ci/config/bws-unrequested.json whose `kind` this gate
     RE-DERIVES. An allowlist nobody re-derives rots into a lie; `no-github-twin`
     goes red the moment the org secret is created, and `deferred` goes red on
     its own stated date.
  6. PER-JOB. Every `secrets.X` a job reads DIRECTLY must be requested by that
     job's own bws step. Counting names hides this: CLOUDFLARE_API_TOKEN was
     shadow-compared in 2 of the 12 jobs that spend it, so a name-level count
     showed it covered. Passthrough jobs -- those calling a reusable workflow,
     which requests inside -- are computed and excluded, not exempted; a
     file-level version of this rule opens with 48 false positives.
  7. SUFFIX EXPANSION. `VAR="PREFIX_${SUFFIX}"` followed by `${!VAR}` in a deploy
     script demands names that appear as a literal NOWHERE, so no scan on either
     side can see them. This is not hypothetical: OBS_OTLP_CREDENTIALS_{EU,US,
     ASIA} are built that way at set-account-worker-secrets.sh:134 and none of
     the three was in the map -- the founding OTLP incident, reproduced by the
     migration built to prevent it.

  9. REVERSE. Every org secret a workflow READS must be mapped, exempt, or
     carry a pre-image row. Assertion 6 skips names the map lacks, so a workflow
     that starts reading a brand-new org secret is invisible to 5, 6 and 7.
 10. THE SCAFFOLD DOES NOT ROT. The migration could not rename the secrets on
     GitHub -- `gh secret set` cannot re-supply a value it is forbidden to read,
     and two of the chosen names are illegal there outright (`gh secret set
     GITHUB_ZZ_PROBE` -> `HTTP 422: Secret names must not start with GITHUB_.`,
     probed 2026-09-02). So `${{ secrets.X }}`, and only there, keeps the old
     spelling, and .ci/config/github-secret-preimage.json is the dictionary.
     That file is a second escape hatch and a more dangerous one than the
     allowlist: an allowlist entry says "do not look", a pre-image row says
     "look somewhere ELSE", so a wrong row makes 9 report a clean resolution for
     a read that resolves to nothing. Hence both legs: a row whose STORE name is
     unmapped is refused, and so is a row whose GITHUB name nothing reads any
     more. The file is temporary and is deleted with the org secrets, after
     which 9 goes back to demanding an exact match.

     It is here because it was NOT here: secret-rename.py rewrote both sides of
     `NEW: ${{ secrets.OLD }}` across 267 expressions, GitHub substituted "" for
     every one of them, and nothing said so. secret-rename.py now refuses a
     `secrets.` context the way it already refused a `vars.` one.

Control-first: the parser is proven on synthetic input in both directions
before any verdict, and the failure direction is proven by a planted name.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# Overridable so a gate-test can drive the REAL scan against a fixture tree
# instead of only the pure-logic selftest. This is not an escape hatch: every
# anti-vacuity clause below (MIN_MAP_ENTRIES, MIN_CALLERS, the blind-corpus and
# blind-suffix refusals) FAILS on a tree that holds nothing, so pointing this at
# an empty directory reds rather than passes.
ROOT = Path(os.environ.get("BWS_MAP_ROOT") or Path(__file__).resolve().parents[3])
MAP = ROOT / ".ci" / "config" / "bws-secret-map.json"
ACTION_REF = "./.github/actions/bws-secrets"

EXEMPT = ROOT / ".ci" / "config" / "bws-unrequested.json"
REACH = ROOT / ".ci" / "config" / "secret-reachability.json"
PREIMAGE = ROOT / ".ci" / "config" / "github-secret-preimage.json"
RENAME_TABLE = ROOT / "scripts" / "dev" / "secret-rename.py"
REGIONS = ROOT / "regions.json"
DEPLOY_DIR = ROOT / ".ci" / "scripts" / "deploy"

# Call sites live in two places. .ci/breakpoint/workflow/ is a REAL bws-secrets
# caller that this gate used to miss entirely, because it globbed .github only
# (recorded as a blind spot in the migration plan's Part 16).
EXTRA_WORKFLOW_DIRS = [ROOT / ".ci" / "breakpoint" / "workflow"]

# Own-git repositories console's index cannot see. Same list secret-rename.py
# carries, and for the same reason.
SIBLING_REPOS = ("private/growth", "private/generative")

MAX_MAP_AGE_DAYS = 45

# The two population floors are env-overridable ONLY so the gate-test can judge a
# small fixture tree. Lowering them against the REAL tree would be suppressing a
# finding, which is why the defaults live here and the test sets them explicitly.
MIN_MAP_ENTRIES = int(os.environ.get("BWS_MIN_MAP_ENTRIES", "30"))
MIN_CALLERS = int(os.environ.get("BWS_MIN_CALLERS", "22"))  # files, not jobs; see the docstring

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def parse_requests(yaml_text: str) -> list[tuple[int, str, str]]:
    """[(line_no, name, env_name)] for every `secrets:` block under a
    `uses: ./.github/actions/bws-secrets` step. A hand parser on purpose: the
    shape is fixed and pulling in a YAML dependency for it would add a way for
    this gate to go stale."""
    out: list[tuple[int, str, str]] = []
    lines = yaml_text.split("\n")
    i = 0
    while i < len(lines):
        if re.search(r"^\s*-?\s*uses:\s*" + re.escape(ACTION_REF) + r"\b", lines[i]):
            # find the `secrets: |` under this step's `with:`
            j = i + 1
            while j < len(lines) and not re.match(r"^\s*-\s+(name|uses):", lines[j]):
                m = re.match(r"^(\s*)secrets:\s*\|\s*$", lines[j])
                if m:
                    base = len(m.group(1))
                    k = j + 1
                    while k < len(lines):
                        raw = lines[k]
                        if raw.strip() == "":
                            k += 1
                            continue
                        ind = len(raw) - len(raw.lstrip(" "))
                        if ind <= base:
                            break
                        text = re.sub(r"#.*$", "", raw).strip()
                        if text:
                            if ">" in text:
                                name, env = (p.strip() for p in text.split(">", 1))
                            else:
                                name = env = text
                            out.append((k + 1, name, env))
                        k += 1
                    break
                j += 1
        i += 1
    return out


# ---------------------------------------------------------------------------
# Coverage helpers (assertions 5-7). Each RE-DERIVES what an allowlist would
# otherwise be trusted for.
# ---------------------------------------------------------------------------

JOB_RE = re.compile(r"^  ([A-Za-z0-9_-]+):\s*$")
USE_RE = re.compile(r"(?<![\w./-])secrets\.([A-Za-z_][A-Za-z0-9_]*)")
CALLS_REUSABLE_RE = re.compile(r"^\s*uses: \./\.github/workflows/")
SUFFIX_RE = re.compile(r'^\s*[A-Za-z_][A-Za-z0-9_]*="([A-Z0-9_]+)_\$\{SUFFIX\}"', re.MULTILINE)
# Never compared, never fetched: the bootstrap token and the implicit one.
NOT_SHADOWED = {"GITHUB_TOKEN", "BWS_ACCESS_TOKEN"}


def call_sites() -> list[Path]:
    """Every file that may carry a bws-secrets request block."""
    out = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    out += sorted((ROOT / ".github" / "actions").glob("*/action.yml"))
    for d in EXTRA_WORKFLOW_DIRS:
        out += sorted(d.glob("*.yml"))
    return out


def rename_pairs() -> list[tuple[str, str]]:
    """(old, new) from secret-rename.py's RENAMES, read as data.

    Imported by exec rather than by parsing, because a second copy of the table
    is a second thing to get wrong -- and this gate's whole subject is two
    records disagreeing about a name."""
    ns: dict = {}
    text = RENAME_TABLE.read_text(encoding="utf-8")
    m = re.search(r"^RENAMES: list\[tuple\[str, str\]\] = \[.*?^\]", text, re.DOTALL | re.MULTILINE)
    if not m:
        return []
    exec(compile(m.group(0), str(RENAME_TABLE), "exec"), ns)  # noqa: S102
    return list(ns.get("RENAMES", []))


def job_index(lines: list[str]) -> list[tuple[int, str]]:
    return [(i, m.group(1)) for i, line in enumerate(lines) if (m := JOB_RE.match(line))]


def job_at(index: list[tuple[int, str]], i: int) -> str | None:
    cur = None
    for start, name in index:
        if start <= i:
            cur = name
        else:
            break
    return cur


def superseded_problems(name: str, rec: dict, suffixes: list[str]) -> list[str]:
    """Re-derive a `superseded-at-runtime` claim against the ACTUAL branch.

    The first version of this asked whether `== "ASIA"` and `${PREFIX_EU`
    appeared ANYWHERE in the script, which an audit defeated three ways in one
    sitting: invert the condition so the substitution applies to the other
    regions, comment the assignments out, or delete the whole block and leave a
    comment naming both strings. All three kept the exemption. A substring test
    over a whole file is not a re-derivation, it is a coincidence detector.

    So: find the branch that tests this suffix, take its BODY up to the matching
    `fi`, strip comments, and require the reassignment to be in there.
    """
    other = str(rec.get("superseded_by", ""))
    if not other:
        return [f"superseded-at-runtime exemption {name!r} names no superseded_by"]
    suffix = next((sfx for sfx in suffixes if name.endswith(f"_{sfx}")), "")
    if not suffix:
        return [
            (
                f"superseded-at-runtime exemption {name!r} does not end in a region suffix "
                f"({', '.join(suffixes)}), so nothing can locate the branch that supersedes it"
            )
        ]
    prefix = name[: -(len(suffix) + 1)]
    target = f"{prefix}_{other}"
    found = []
    for script in sorted(DEPLOY_DIR.glob("*.sh")):
        text = script.read_text(encoding="utf-8")
        for m in re.finditer(
            r"^([ \t]*)if\s+\[\[[^\n]*==\s*\"%s\"[^\n]*\]\][^\n]*$" % re.escape(suffix),
            text,
            re.MULTILINE,
        ):
            if "!" in text[m.start() : m.end()].split("==")[0]:
                continue  # an inverted test supersedes the OTHER regions
            rest = text[m.end() :]
            end = re.search(r"^%s(fi|else|elif)\b" % re.escape(m.group(1)), rest, re.MULTILINE)
            body = rest[: end.start()] if end else rest
            live = "\n".join(ln for ln in body.split("\n") if not ln.lstrip().startswith("#"))
            if f"${{{target}" in live or f"${{{target}:" in live:
                found.append(f"{script.name}:{text.count(chr(10), 0, m.start()) + 1}")
    if not found:
        return [
            (
                f"exemption {name!r} claims {suffix} is superseded by {other} at runtime, but no "
                f'deploy script has a live `if [[ ... == "{suffix}" ]]` branch whose body '
                f"reassigns from {target} -- an inverted condition, a commented-out assignment or "
                f"a deleted block all mean the secret is needed again"
            )
        ]
    return []


def represented_problems(secrets: dict, exemptions: dict) -> tuple[list[str], tuple[int, int]]:
    """Assertion 8: every stored name must APPEAR IN THE CODE.

    Operator, 2026-09-02: "we should always have what we have at bitwarden side
    in the code. That way we can also do proper renaming." Assertions 1 and 5
    only reach names a WORKFLOW requests. A secret consumed by a deploy script,
    a submodule, or a sibling repo can sit in the store while nothing in the tree
    ever spells it -- which is precisely the state that makes a rename unsafe,
    because a rename tool can only move a name it can see.

    Two exclusions, both deliberate:
      * a name beginning with `_` is skipped. That is the operator's marker for
        an entry parked on purpose; there are none today.
      * the map and this gate's own allowlist do not count as an appearance, or
        every name would satisfy the rule by being written down in the file that
        lists it. Neither does `agent/`: a plan discussing a name is not the code
        using it.

    Submodules are IN, via --recurse-submodules, and so are the gitignored
    sibling repos, which have their own git and are invisible to console's index
    -- the blindness that let a rename break private/growth's publish pipeline.
    """
    names = sorted(n for n in secrets if not n.startswith("_"))
    if not names:
        return (["the map holds no non-underscore names; refusing to pass vacuously"], (0, 0))

    seen: set[str] = set()
    pat = "\n".join(names)
    cmds = [
        [
            "git",
            "grep",
            "-h",
            "-o",
            "-F",
            "--recurse-submodules",
            "-f",
            "-",
            "--",
            ".",
            ":(exclude).ci/config/bws-secret-map.json",
            ":(exclude).ci/config/bws-unrequested.json",
            ":(exclude)agent/",
        ]
    ]
    cmds.extend(
        ["git", "-C", str(ROOT / repo), "grep", "-h", "-o", "-F", "-f", "-"]
        for repo in SIBLING_REPOS
        if (ROOT / repo / ".git").exists()
    )
    ran = 0
    for cmd in cmds:
        try:
            out = subprocess.run(
                cmd, cwd=ROOT, input=pat, capture_output=True, text=True, check=False
            )
        except OSError:
            continue
        ran += 1
        seen.update(line.strip() for line in out.stdout.split("\n") if line.strip())
    if ran == 0:
        return (["no corpus could be searched; refusing to pass vacuously"], (0, len(names)))

    problems = [
        f"Bitwarden holds {n!r} but NOTHING in the tree spells it -- not console, not a "
        f"submodule, not a sibling repo. A name the code never mentions cannot be renamed "
        f"safely, and nothing proves the stored value is still wanted. Wire it, delete it, "
        f"or exempt it in {EXEMPT.relative_to(ROOT)}"
        for n in names
        if n not in seen and n not in exemptions
    ]
    return problems, (len(seen & set(names)), len(names))


def load_preimage(path: Path | None = None) -> tuple[dict[str, str], list[str]]:
    """{github name it is READ under} -> {name the store holds}, plus problems.

    WHY THIS RELATION EXISTS AT ALL. The migration gave every credential one
    name at every layer it controls. It does not control GitHub: the operator
    ruled the org secrets are being DELETED, not renamed, and `gh secret set`
    cannot re-supply a value it is forbidden to read, so renaming there means
    retyping 45 values by hand. So `${{ secrets.X }}` -- and only there -- keeps
    the old spelling, and this file is the dictionary.

    It is SCAFFOLD, and the assertions below are what stop it becoming a second
    exemption list. Every entry must earn its place twice: the store side must
    be a name the map really holds, and the GitHub side must really be read by
    a workflow. An entry that fails either is dead weight to be deleted, not a
    licence. When the org secrets go, so does the file, and assertion 9 goes
    back to demanding an exact match.
    """
    src = path or PREIMAGE
    try:
        doc = json.loads(src.read_text(encoding="utf-8"))
    except FileNotFoundError:
        # ABSENT IS LEGAL, and it is the END STATE. Once the org secrets are
        # deleted every read is an exact match and there is nothing to alias.
        return {}, []
    except (OSError, ValueError) as exc:
        return {}, [f"cannot read {src} ({exc}); assertion 9 is blind"]

    alias: dict[str, str] = {}
    problems: list[str] = []

    def bind(github_name: str, store_name: str, where: str) -> None:
        if github_name == store_name:
            problems.append(
                f"{where}: {github_name!r} maps to itself. An identity entry documents "
                f"nothing and silently widens assertion 9 by one name -- delete the row"
            )
            return
        if github_name in alias and alias[github_name] != store_name:
            problems.append(
                f"{where}: {github_name!r} is claimed by both {alias[github_name]!r} and "
                f"{store_name!r}; one GitHub name cannot stand for two stored secrets"
            )
            return
        alias[github_name] = store_name

    for store_name, github_name in (doc.get("preimage") or {}).items():
        if store_name.startswith("$"):
            continue
        bind(github_name, store_name, "preimage")
    # renamed_away is the reverse shape: the STORE keeps the illegal name and
    # the workflow layer uses GitHub's. `gh secret set GITHUB_ZZ_PROBE` answers
    # HTTP 422 "Secret names must not start with GITHUB_." (probed 2026-09-02),
    # so these are not deferred renames, they are impossible ones.
    for store_name, github_name in (doc.get("renamed_away") or {}).items():
        if store_name.startswith("$"):
            continue
        bind(github_name, store_name, "renamed_away")
    for store_name, rec in (doc.get("regional_preimage") or {}).items():
        if store_name.startswith("$") or not isinstance(rec, dict):
            continue
        bind(rec.get("github_name", ""), store_name, "regional_preimage")
    return alias, problems


def preimage_problems(alias: dict[str, str], secrets: dict, read: set[str]) -> list[str]:
    """Assertion 10: no row of the pre-image file may be dead scaffold.

    Both directions, because each hides a different mistake. A row whose STORE
    name is not in the map is a typo that would make assertion 9 forgive a read
    resolving to nothing -- the precise failure this whole file exists to stop.
    A row whose GITHUB name nothing reads is a rename that already finished, and
    leaving it behind is how a temporary list becomes permanent.
    """
    out = []
    for github_name, store_name in sorted(alias.items()):
        if store_name not in secrets:
            out.append(
                f"{PREIMAGE.relative_to(ROOT)} says GitHub's {github_name!r} stands for "
                f"{store_name!r}, but the map holds no {store_name!r}. Either the store "
                f"name is misspelled or the secret was never seeded -- as written, this "
                f"row makes assertion 9 forgive a read that resolves to nothing"
            )
        if github_name not in read:
            out.append(
                f"{PREIMAGE.relative_to(ROOT)} carries {github_name!r}, but no workflow "
                f"reads secrets.{github_name} any more. The rename it describes is done; "
                f"delete the row so the file keeps naming only live scaffold"
            )
    return out


def unmapped_read_problems(
    secrets: dict, exemptions: dict, alias: dict[str, str]
) -> tuple[list[str], int, set[str]]:
    """Assertion 9: an org secret a workflow READS must be in the map, or exempt.

    Assertion 6 checks the other direction and, by construction, only reaches names
    the map ALREADY holds (`if bw_name not in secrets ... continue`). So a workflow
    that starts reading a brand-new org secret nobody put in the store is invisible
    to 5 (map -> requested), 6 (skips unmapped) and 7 (only SUFFIX literals under
    .ci/scripts/deploy). That is the cutover-ships-blank shape with no scan on it.

    Scoped to secrets the reachability record says console can actually READ, so a
    typo'd `secrets.FOO` is left to actionlint rather than reported twice here.

    `alias` is the pre-image relation (see load_preimage): during the cutover a
    workflow reads GitHub's older spelling while the store holds the new one, so
    a read is satisfied by EITHER. Aliasing is the one thing this gate must not
    do generously -- every row is itself asserted by assertion 10, in both
    directions, so a typo here cannot quietly forgive a read that resolves to
    nothing.
    """
    read: set[str] = set()
    for f in call_sites():
        read |= set(USE_RE.findall(f.read_text(encoding="utf-8")))
    read -= NOT_SHADOWED
    try:
        rows = json.loads(REACH.read_text(encoding="utf-8"))["repos"]["console"]
    except (OSError, ValueError, KeyError) as exc:
        return ([f"cannot read {REACH.relative_to(ROOT)} ({exc}); assertion 9 is blind"], 0, read)
    org = {k for k, v in rows.items() if isinstance(v, dict) and v.get("reachable")}
    if not org:
        return ([f"{REACH.relative_to(ROOT)} lists no reachable console secret; blind"], 0, read)
    resolved = set(secrets) | set(exemptions) | {n for n in read if alias.get(n) in secrets}
    gap = sorted((read & org) - resolved)
    problems = [
        f"a workflow reads secrets.{n}, an org secret console can reach, but the map does "
        f"not hold it, it carries no exemption, and {PREIMAGE.name} does not say which "
        f"stored name it stands for -- at cutover the fetch resolves nothing "
        f"and the value ships EMPTY"
        for n in gap
    ]
    return problems, len(read & org), read


def load_exemptions(path: Path | None = None) -> tuple[dict, list[str]]:
    """The only escape hatch, and it is re-derived rather than believed.

    `path` is injectable so selftest() can drive every refusal against a fixture
    instead of against the real allowlist."""
    src = path or EXEMPT
    label = src.relative_to(ROOT) if src.is_relative_to(ROOT) else src
    problems: list[str] = []
    if not src.exists():
        return {}, [f"{label} is missing; refusing to pass vacuously"]
    try:
        doc = json.loads(src.read_text(encoding="utf-8"))
    except ValueError as exc:
        return {}, [f"{label} is unparseable: {exc}"]
    ex = doc.get("exemptions") or {}
    if not ex:
        problems.append(
            f"{label} declares no exemptions -- an empty allowlist and a "
            f"missing one look identical to a naive check, so both fail here"
        )
    today = dt.datetime.now(dt.UTC).date()
    for name, rec in sorted(ex.items()):
        kind = rec.get("kind")
        if kind not in ("no-github-twin", "deferred", "superseded-at-runtime"):
            problems.append(
                f"exemption {name!r} has kind {kind!r}; expected no-github-twin, deferred "
                f"or superseded-at-runtime"
            )
            continue
        if kind == "superseded-at-runtime" and not str(rec.get("superseded_by", "")).strip():
            problems.append(
                f"superseded-at-runtime exemption {name!r} does not name the region that "
                f"replaces it (`superseded_by`), so nothing can re-derive the claim"
            )
        if not str(rec.get("reason", "")).strip():
            problems.append(f"exemption {name!r} carries no reason")
        if kind == "deferred":
            if not str(rec.get("worklist", "")).strip():
                problems.append(f"deferred exemption {name!r} names no worklist id")
            try:
                expires = dt.date.fromisoformat(str(rec.get("expires", "")))
            except ValueError:
                problems.append(
                    f"deferred exemption {name!r} has no parseable `expires` (YYYY-MM-DD)"
                )
                continue
            if expires < today:
                problems.append(
                    f"deferred exemption {name!r} EXPIRED on {expires} -- it was a real gap with a "
                    f"real fix, and the date was the whole point of writing it down"
                )
    return ex, problems


def coverage_problems(secrets: dict, exemptions: dict) -> list[str]:
    """Assertions 5, 6 and 7. Every one is the converse of assertion 1."""
    problems: list[str] = []
    renames = dict(rename_pairs())
    pre_images: dict[str, list[str]] = {}
    for old, new in renames.items():
        pre_images.setdefault(new, []).append(old)

    try:
        reach = json.loads(REACH.read_text(encoding="utf-8"))["repos"]["console"]
        reachable = {k for k, v in reach.items() if isinstance(v, dict) and v.get("reachable")}
    except (OSError, ValueError, KeyError) as exc:
        return [f"cannot read {REACH.relative_to(ROOT)} ({exc}); coverage cannot be re-derived"]
    if not reachable:
        return [
            f"{REACH.relative_to(ROOT)} lists no reachable console secret; refusing to pass vacuously"
        ]

    # ---- gather every request and every DIRECT read, per job -----------------
    requested: set[str] = set()
    direct_reads = 0
    for f in call_sites():
        text = f.read_text(encoding="utf-8")
        lines = text.split("\n")
        index = job_index(lines)
        reqs_by_job: dict[str | None, set[str]] = {}
        for line_no, name, _env in parse_requests(text):
            requested.add(name)
            reqs_by_job.setdefault(job_at(index, line_no - 1), set()).add(name)
        if not index:
            continue
        # A job that CALLS a reusable workflow declares `secrets:` to pass down;
        # the callee requests them itself. Computed, never exempted -- the
        # file-level version of this rule opens with 48 false positives.
        passthrough = {
            job_at(index, i) for i, line in enumerate(lines) if CALLS_REUSABLE_RE.match(line)
        }
        reads_by_job: dict[str | None, dict[str, int]] = {}
        for i, line in enumerate(lines):
            if line.lstrip().startswith("#"):
                continue
            for gh_name in USE_RE.findall(line):
                if gh_name in NOT_SHADOWED:
                    continue
                bw_name = renames.get(gh_name, gh_name)
                if bw_name not in secrets and gh_name not in renames:
                    continue
                reads_by_job.setdefault(job_at(index, i), {}).setdefault(bw_name, i + 1)
        for job, reads in sorted(reads_by_job.items(), key=lambda kv: kv[0] or ""):
            if job in passthrough:
                continue
            direct_reads += len(reads)
            for bw_name in sorted(set(reads) - reqs_by_job.get(job, set())):
                if exemptions.get(bw_name, {}).get("kind") == "deferred":
                    continue
                problems.append(
                    f"{f.relative_to(ROOT)}:{reads[bw_name]} job {job!r} reads a secret it never "
                    f"requests ({bw_name}); at cutover that job fetches nothing for it"
                )
    if direct_reads == 0:
        problems.append(
            "no job reads any mapped secret directly; the per-job scan lost its subject"
        )

    # ---- 5. every mapped name is requested or exempt -------------------------
    for name in sorted(set(secrets) - requested):
        rec = exemptions.get(name)
        if rec is None:
            problems.append(
                f"map holds {name!r} but no call site requests it, and it carries no entry in "
                f"{EXEMPT.relative_to(ROOT)} -- the shadow proves nothing about it"
            )
            continue
        if rec.get("kind") == "no-github-twin":
            twins = [g for g in [name, *pre_images.get(name, [])] if g in reachable]
            if twins:
                problems.append(
                    f"exemption {name!r} claims no GitHub twin, but {', '.join(twins)} IS a "
                    f"console-reachable org secret -- the shadow is possible now, so add a "
                    f"request line and drop the exemption"
                )

    # ---- 7. names built at runtime by SUFFIX expansion -----------------------
    try:
        suffixes = [
            r["secretSuffix"] for r in json.loads(REGIONS.read_text(encoding="utf-8"))["regions"]
        ]
    except (OSError, ValueError, KeyError) as exc:
        return [*problems, f"cannot read region suffixes from {REGIONS.name} ({exc})"]
    constructions = 0
    for script in sorted(DEPLOY_DIR.glob("*.sh")):
        for prefix in SUFFIX_RE.findall(script.read_text(encoding="utf-8")):
            constructions += 1
            for suffix in suffixes:
                built = f"{prefix}_{suffix}"
                if built in secrets or built in exemptions:
                    continue
                problems.append(
                    f'{script.relative_to(ROOT)} builds {built!r} at runtime ("{prefix}_${{SUFFIX}}") '
                    f"and the map does not hold it -- the name appears as a literal nowhere, so "
                    f"nothing else can see this"
                )
    if constructions == 0:
        problems.append(
            f"no PREFIX_${{SUFFIX}} construction found under {DEPLOY_DIR.relative_to(ROOT)}; "
            f"the runtime-name scan lost its subject"
        )

    # ---- an exemption that no longer describes anything ----------------------
    built_names = {
        f"{prefix}_{suffix}"
        for script in sorted(DEPLOY_DIR.glob("*.sh"))
        for prefix in SUFFIX_RE.findall(script.read_text(encoding="utf-8"))
        for suffix in suffixes
    }
    # Re-derived for EVERY such exemption, mapped or not. Assertion 7 used to be
    # the only caller, and it short-circuits on `built in secrets` -- so the same
    # kind applied to a MAPPED name was accepted on nothing but a non-empty
    # string, making the weakest-checked kind also the one with no expiry and no
    # worklist id. Found by audit, not by design.
    for name, rec in sorted(exemptions.items()):
        if rec.get("kind") == "superseded-at-runtime":
            problems.extend(superseded_problems(name, rec, suffixes))

    problems.extend(
        f"exemption {name!r} names nothing: it is not in the map and no deploy script builds "
        f"it. Delete it -- a stale exemption is how an allowlist stops meaning anything"
        for name in sorted(set(exemptions) - set(secrets) - built_names)
    )
    problems.extend(
        f"exemption {name!r} is unnecessary: a call site requests it, so it IS shadowed. "
        f"Delete the exemption"
        for name in sorted(set(exemptions) & requested)
    )
    return problems


def selftest() -> int:
    fixture = """\
jobs:
  x:
    steps:
      - uses: ./.github/actions/bws-secrets
        with:
          access-token: ${{ secrets.BWS_ACCESS_TOKEN }}
          secrets: |
            SELFTEST_PLAIN_NAME
            SELFTEST_ALIASED > SELFTEST_ENV_NAME   # alias

            SELFTEST_AFTER_BLANK
      - name: next step
        run: echo hi
      - uses: actions/checkout@abc
        with:
          secrets: |
            DECOY_NOT_OURS"""
    got = parse_requests(fixture)
    # SYNTHETIC names on purpose. This fixture used real ones, and
    # secret-rename.py's table collapsed the aliased line -- the old name and its
    # replacement are the SAME token once a collapse row applies, so the one case
    # proving aliases parse became name-equals-env, while every assertion still
    # passed because the `want` list was rewritten in lockstep. A control whose
    # point survives only until a find-and-replace runs is not a control. (Write
    # a retiring name in braced form, FOO_{EU,US,ASIA}, or this comment gets
    # rewritten by the rename it is describing -- which is how it read at first.)
    want = [
        (8, "SELFTEST_PLAIN_NAME", "SELFTEST_PLAIN_NAME"),
        (9, "SELFTEST_ALIASED", "SELFTEST_ENV_NAME"),
        (11, "SELFTEST_AFTER_BLANK", "SELFTEST_AFTER_BLANK"),
    ]
    ok = got == want
    print(
        f"  {'PASS' if ok else 'FAIL'}  parser reads names, aliases, skips comments/blank, ignores other actions"
    )
    if not ok:
        print(f"        got  {got}\n        want {want}")
        return 1
    # the failure direction must be detectable
    fake = {"secrets": {"SELFTEST_PLAIN_NAME": {"id": "x"}}}
    missing = [n for _, n, _ in got if n not in fake["secrets"]]
    ok2 = missing == ["SELFTEST_ALIASED", "SELFTEST_AFTER_BLANK"]
    print(f"  {'PASS' if ok2 else 'FAIL'}  a requested name absent from the map is reported")
    if not ok2:
        return 1

    # ---- the escape hatch's own integrity, both directions -------------------
    # The allowlist is the one place this gate can be talked out of a finding, so
    # every way of writing a bad entry is planted here and required to red WITH
    # the matching message. The clean case is required to stay silent, because
    # "every fixture reds" is a check that cannot pass.
    def probe(doc: object) -> list[str]:
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "ex.json"
            f.write_text(json.dumps(doc), encoding="utf-8")
            return load_exemptions(f)[1]

    clean = {
        "exemptions": {
            "A": {"kind": "no-github-twin", "reason": "r"},
            "B": {"kind": "deferred", "worklist": "abc123", "expires": "2999-01-01", "reason": "r"},
            "C": {"kind": "superseded-at-runtime", "superseded_by": "EU", "reason": "r"},
        }
    }
    cases: list[tuple[str, object, str]] = [
        (
            "an unknown kind",
            {"exemptions": {"A": {"kind": "because-i-said-so", "reason": "r"}}},
            "expected no-github-twin",
        ),
        (
            "an entry with no reason",
            {"exemptions": {"A": {"kind": "no-github-twin", "reason": "  "}}},
            "carries no reason",
        ),
        (
            "a deferral naming no worklist item",
            {"exemptions": {"A": {"kind": "deferred", "expires": "2999-01-01", "reason": "r"}}},
            "names no worklist id",
        ),
        (
            "a deferral with no expiry",
            {"exemptions": {"A": {"kind": "deferred", "worklist": "x", "reason": "r"}}},
            "no parseable `expires`",
        ),
        (
            "a deferral past its own date",
            {
                "exemptions": {
                    "A": {
                        "kind": "deferred",
                        "worklist": "x",
                        "expires": "2020-01-01",
                        "reason": "r",
                    }
                }
            },
            "EXPIRED",
        ),
        (
            "a superseded claim naming no region",
            {"exemptions": {"A": {"kind": "superseded-at-runtime", "reason": "r"}}},
            "`superseded_by`",
        ),
        ("an emptied allowlist", {"exemptions": {}}, "declares no exemptions"),
    ]
    bad = 0
    for label, doc, needle in cases:
        got = probe(doc)
        hit = any(needle in g for g in got)
        print(f"  {'PASS' if hit else 'FAIL'}  {label} is refused")
        if not hit:
            bad += 1
            print(f"        got {got}")
    got = probe(clean)
    ok3 = got == []
    print(f"  {'PASS' if ok3 else 'FAIL'}  CONTROL: a well-formed allowlist is silent")
    if not ok3:
        print(f"        got {got}")
        bad += 1

    # ---- the pre-image relation, in BOTH directions --------------------------
    # This is the second escape hatch, and it is younger and more dangerous than
    # the allowlist: an allowlist entry says "do not look", while a pre-image row
    # says "look somewhere ELSE", so a wrong row makes assertion 9 report a clean
    # resolution for a read that resolves to nothing. Every way of writing one
    # badly is planted, and the clean case is required to stay silent.
    def probe_pre(doc: object) -> list[str]:
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "pre.json"
            f.write_text(json.dumps(doc), encoding="utf-8")
            return load_preimage(f)[1]

    pre_cases: list[tuple[str, object, str]] = [
        (
            "a pre-image row that maps a name to itself",
            {"preimage": {"SAME_NAME": "SAME_NAME"}},
            "maps to itself",
        ),
        (
            "one GitHub name standing for two stored secrets",
            {"preimage": {"STORE_A": "GH_SHARED", "STORE_B": "GH_SHARED"}},
            "cannot stand for two",
        ),
    ]
    for label, doc, needle in pre_cases:
        got = probe_pre(doc)
        hit = any(needle in g for g in got)
        print(f"  {'PASS' if hit else 'FAIL'}  {label} is refused")
        if not hit:
            bad += 1
            print(f"        got {got}")
    ok_pre_clean = probe_pre({"preimage": {"STORE_A": "GH_OLD_A"}}) == []
    print(f"  {'PASS' if ok_pre_clean else 'FAIL'}  CONTROL: a well-formed pre-image is silent")
    if not ok_pre_clean:
        bad += 1

    # Assertion 10, both legs. A row is dead scaffold if its STORE side is not in
    # the map (which would forgive a read resolving to nothing) or if its GITHUB
    # side is no longer read (a finished rename left behind). Neither leg is
    # visible to assertion 9, which is exactly why they are planted separately.
    ok10a = any(
        "the map holds no" in m
        for m in preimage_problems({"GH_OLD": "STORE_TYPO"}, {"STORE_REAL": {}}, {"GH_OLD"})
    )
    print(f"  {'PASS' if ok10a else 'FAIL'}  a pre-image row naming an unmapped secret is refused")
    if not ok10a:
        bad += 1
    ok10b = any(
        "no workflow reads" in m
        for m in preimage_problems({"GH_OLD": "STORE_REAL"}, {"STORE_REAL": {}}, set())
    )
    print(f"  {'PASS' if ok10b else 'FAIL'}  a pre-image row nothing reads any more is refused")
    if not ok10b:
        bad += 1
    ok10c = preimage_problems({"GH_OLD": "STORE_REAL"}, {"STORE_REAL": {}}, {"GH_OLD"}) == []
    print(f"  {'PASS' if ok10c else 'FAIL'}  CONTROL: a live pre-image row is silent")
    if not ok10c:
        bad += 1

    # Assertion 8's two pure-logic edges. The corpus scan itself shells out to
    # git and is exercised against the real tree; what is pinned here is the
    # underscore skip and the refusal to judge an empty name set -- together they
    # are the only ways this assertion can go quiet without looking.
    only_underscore = represented_problems({"_PARKED_ON_PURPOSE": {"id": "x"}}, {})[0]
    ok5 = any("refusing to pass vacuously" in m for m in only_underscore)
    print(
        f"  {'PASS' if ok5 else 'FAIL'}  a map of only underscore names refuses rather than passing"
    )
    if not ok5:
        bad += 1

    missing_file = load_exemptions(Path("/nonexistent/ex.json"))[1]
    ok4 = any("refusing to pass vacuously" in m for m in missing_file)
    print(f"  {'PASS' if ok4 else 'FAIL'}  a missing allowlist refuses rather than passing")
    if not ok4:
        bad += 1
    return 1 if bad else 0


def main() -> int:
    if "--selftest" in sys.argv[1:]:
        return selftest()
    if selftest() != 0:
        print(
            "✗ instrument control failed; every verdict below would be meaningless", file=sys.stderr
        )
        return 1

    if not MAP.exists():
        print(f"✗ {MAP.relative_to(ROOT)} is missing; refusing to pass vacuously", file=sys.stderr)
        return 1
    doc = json.loads(MAP.read_text(encoding="utf-8"))
    secrets = doc.get("secrets") or {}
    problems: list[str] = []

    # 4. not vacuous
    if len(secrets) < MIN_MAP_ENTRIES:
        problems.append(
            f"map holds {len(secrets)} entries, floor is {MIN_MAP_ENTRIES} -- regenerate it, or the scan lost the file"
        )
    for name, rec in secrets.items():
        if not UUID_RE.match(str(rec.get("id", ""))):
            problems.append(f"map entry {name!r} has a malformed id {rec.get('id')!r}")

    # 3. not stale
    try:
        refreshed = dt.datetime.strptime(doc["refreshed_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=dt.UTC
        )
        age = (dt.datetime.now(dt.UTC) - refreshed).days
        if age > MAX_MAP_AGE_DAYS:
            problems.append(
                f"map refreshed_at is {age} days old (limit {MAX_MAP_AGE_DAYS}); regenerate from ci-shared"
            )
    except (KeyError, ValueError) as e:
        problems.append(f"map has no parseable refreshed_at: {e}")

    # 1 + 2. every request resolves
    callers = 0
    workflows = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    if not workflows:
        # ZERO FILES is not "zero callers". Zero callers among real workflows is
        # the pre-cutover state and passes with a note below; zero workflow files
        # means the scan lost its subject entirely, and a gate that passes over
        # an empty set is the failure mode this repo names most often.
        # test-gate-anti-vacuity.sh caught exactly this on the first run: the
        # map is copied into its empty tree, so without this clause the gate
        # exited 0 there asserting nothing.
        print(
            "✗ no workflow files under .github/workflows; refusing to pass vacuously",
            file=sys.stderr,
        )
        return 1
    # call_sites() rather than a second hand-built list: assertions 1 and 2 used
    # to glob .github only, so .ci/breakpoint/workflow/breakpoint.yml was covered
    # by assertion 5 and invisible to the two that check map membership and
    # env-name shape. A gate keeping two lists of its own inputs will drift
    # between them, which is the same defect it exists to find elsewhere.
    files = call_sites()
    for f in files:
        reqs = parse_requests(f.read_text(encoding="utf-8"))
        if reqs:
            callers += 1
        for line, name, env in reqs:
            rel = f.relative_to(ROOT)
            if name not in secrets:
                problems.append(
                    f"{rel}:{line} requests {name!r}, which the map does not hold -- the job would fail at run time"
                )
            if not ENV_NAME_RE.match(env):
                problems.append(f"{rel}:{line} exports to {env!r}, not a legal shell identifier")
    if callers < MIN_CALLERS:
        problems.append(f"only {callers} workflow(s) use {ACTION_REF}; floor is {MIN_CALLERS}")

    # 5, 6, 7. Coverage -- the converse direction. See the docstring.
    exemptions, ex_problems = load_exemptions()
    problems += ex_problems
    alias, alias_problems = load_preimage()
    problems += alias_problems
    if not ex_problems:
        problems += coverage_problems(secrets, exemptions)
        rep_problems, represented = represented_problems(secrets, exemptions)
        problems += rep_problems
        read_problems, n_read, read = unmapped_read_problems(secrets, exemptions, alias)
        problems += read_problems
        # 10. The scaffold does not rot. Run even when 9 found nothing: a dead
        # row is invisible to 9 by construction (it only widens what 9 forgives).
        if not alias_problems:
            problems += preimage_problems(alias, secrets, read)

    if problems:
        print(f"✗ bws map check ({len(problems)} problem(s)):", file=sys.stderr)
        for p in problems:
            print(f"    {p}", file=sys.stderr)
        return 1

    exemptions, _ = load_exemptions()
    print(
        f"✓ bws map: {len(secrets)} secret(s) mapped, {callers} caller file(s) all resolve (floor {MIN_CALLERS})"
    )
    print(
        f"✓ coverage: every mapped name is requested or exempt ({len(exemptions)} exemption(s), "
        f"each kind re-derived), every job requests every ALREADY-MAPPED secret it "
        f"reads, and every "
        f"PREFIX_${{SUFFIX}} name a deploy script builds is mapped"
    )
    print(
        f"✓ represented: {represented[0]} of {represented[1]} stored name(s) appear in the "
        f"tree (console + submodules + sibling repos); the rest carry an exemption"
    )
    print(
        f"✓ reverse: all {n_read} org secret(s) a workflow reads are mapped, exempt, or "
        f"carry a pre-image row ({len(alias)} row(s)); the direction assertion 6 cannot "
        f"see, because it skips unmapped names"
    )
    if alias:
        print(
            f"✓ pre-image: all {len(alias)} row(s) name a mapped secret AND a name some "
            f"workflow still reads -- none is dead scaffold. This file is temporary: it "
            f"is deleted with the org secrets."
        )
    print("  Blind spot: this proves NAMES resolve. Liveness in Bitwarden is proven at run time,")
    print(
        "  where a missing UUID fails the whole fetch; an EMPTY value is the deploy scripts' job."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
