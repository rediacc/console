r"""check:ci-actions-vars -- the GitHub Actions `vars.*` namespace, and every `secrets.*` read, held against one tracked file.

THE QUESTION NO GATE ASKED. Measured 2026-09-22: twenty distinct `vars.NAME` reads across the workflows, and five of the names in no shard of `.ci/config/env-manifest.json` at all, because that gate's `workflow-key` reader collects ENV-shaped mapping KEYS, not expression references. `client-id: ${{ vars.APP_ID }}` contributed nothing to any gate. The GitHub-hosted configuration namespace had never been under an assertion here, which is how the retired autopilot App left ten orphaned
variables behind and how a GitLab move would have had to rediscover twenty-two names by hand. The operator's ruling (2026-09-24) is that nothing depends on GitHub variables or secrets, with the one exception of the credential that opens the store. `agent/plans/PLAN-github-actions-to-bitwarden.md` Decision 4 is this gate's design; the six clauses below are that list.

  1. FORWARD. Every `vars.NAME` read in the corpus has an entry in
     `.ci/config/actions-vars.json`, or the gate reds naming the file, the line,
     the job and the name.
  2. REVERSE. Every entry is still read somewhere. An entry whose reads have
     gone reds as RESOLVED, naming both readings: the migration landed and the
     entry should be drained, or the read moved and the entry now lies. Together
     with 1 the file is untrimmable in both directions.
  3. KINDS ARE RE-DERIVED. `migrated` requires the Bitwarden twin in
     `.ci/config/bws-secret-map.json`. `no-fetch-job` requires every read of the
     name to sit in a `<path>#<job>` listed under `no_fetch_jobs`, and each such
     row to name a job that exists AND still reads the name -- the same double
     liveness `check_bws_map.py` applies to its own `no_fetch_jobs`. `dead` is
     refused on sight: with reads it contradicts itself, without them clause 2
     fires, so a dead name is deleted from GitHub rather than written down.
  4. THE SECRETS ARM. Every `secrets.NAME` read outside a comment is either in
     `bootstrap_names` of `.ci/config/secret-supply.json` (the ruling that a
     credential cannot live in the store it unlocks, read from where it is made
     rather than restated) or `GITHUB_TOKEN`, which the runner mints per job and
     stores nowhere. A workflow that starts reading a new GitHub secret reds at
     the commit that adds it.
  5. COMMENTS ARE NOT READS. `secrets.ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN` sits in
     two comments of `.github/workflows/claude-review-reusable.yml` explaining a
     fallback that was removed, and `set-account-worker-secrets.sh` in a comment
     is `secrets.sh` to a careless pattern. A gate that counts either reds on a
     correct tree, which is the shape that gets suppressed. The commented
     mentions skipped are COUNTED and printed, so the blind spot has a number.
  6. ANTI-VACUITY, with no floor that reds on success. Zero workflow files is a
     REFUSAL: the instrument lost the tree. Zero `secrets.*` reads is a REFUSAL:
     every Bitwarden fetch reads `secrets.BWS_ACCESS_TOKEN`, so a scan that finds
     none has stopped scanning, and that stays true in the terminal state. An
     empty read set beside an empty file is the TERMINAL state and PASSES,
     printing zero. An EMPTY `vars` object beside live reads is deliberately NOT
     a refusal, although the plan's Decision 4 asked for one: in the terminal
     state that combination is exactly what a NEW read looks like, and a refusal
     telling its author "the file was emptied" would be a false message on the
     one event this gate exists to catch. It reds through clause 1 instead, once
     per read, and that message already names the deletion case. A typed floor of "at least twenty reads"
     would red exactly when the migration succeeds -- the finish-line trap
     `secret_supply.py` names in its own anti-vacuity section.

THE CORPUS AND THE PARSER ARE SHARED, NOT RE-TYPED. `rediacc_ci.workflows.call_sites` is the same file set `check_bws_map.py` scans (the workflows, the composite actions, and the frozen breakpoint twin under `.ci/breakpoint/workflow/`); `job_index`/`job_at` answer which job owns a line; `context_reads` is the one reader for both contexts. A second copy of any of them would be a second answer to one question.

WHY `.ci/config/` AND NOT `.ci/policy/`, by `secret_supply.py`'s reasoning, which applies unchanged: this file exempts nothing from another gate, deleting it makes this gate refuse rather than pass, and `.ci/policy/` is under four-way set equality via `check:ci-policy-inventory`.

WHAT A GREEN DOES NOT CLAIM. It does not talk to GitHub, so it cannot see a variable that exists in the org settings with no reader; the deletion of those is an operator action recorded in the plan. It does not know whether a Bitwarden value is correct, only that the name resolves. It sees `console`'s workflows only, not a submodule's.

Exit 1 on any finding or refusal, 2 on a failed control.
"""

from __future__ import annotations

import collections
import json
import pathlib
import sys
import typing

from rediacc_ci import log, paths, workflows
from rediacc_ci.controls import Checker, controls_first, plant

SPEC_REL = ".ci/config/actions-vars.json"
MAP_REL = ".ci/config/bws-secret-map.json"
SUPPLY_REL = ".ci/config/secret-supply.json"

KINDS = ("migrated", "no-fetch-job", "dead")

# Minted by the runner for each job and stored nowhere, so it is not configuration anyone migrates. The GitLab analogue is CI_JOB_TOKEN. Named here rather than in the spec because it is a fact about the platform, not a decision about this repository.
RUNNER_MINTED = frozenset({"GITHUB_TOKEN"})

# The floor on a `no_fetch_jobs` reason, matching `check_bws_map.py`'s own: long enough that "BLOCKER: breakpoint" does not pass for an argument.
MIN_REASON = 60


class RefusalError(Exception):
    """The gate cannot reach a verdict. Exit 1, never a silent pass."""


class Read(typing.NamedTuple):
    """One `<ctx>.NAME` reference: where it is, which job owns it, and the name."""

    path: str
    line: int
    job: str | None
    name: str


# --------------------------------------------------------------------------- reading the tree ---------------------------------------------------------------------------


def _load(root: pathlib.Path, rel: str):
    path = root / rel
    if not path.is_file():
        raise RefusalError(
            "%s does not exist. Its absence is otherwise the cheapest way to make every "
            "finding disappear at once." % rel
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RefusalError(
            "%s exists but cannot be read (%s). A corrupt input is not an empty one." % (rel, exc)
        ) from exc


def read_spec(root: pathlib.Path):
    spec = _load(root, SPEC_REL)
    for key in ("kinds", "vars", "no_fetch_jobs"):
        if not isinstance(spec.get(key), dict):
            raise RefusalError("%s has no object under %r" % (SPEC_REL, key))
    if set(spec["kinds"]) != set(KINDS):
        raise RefusalError(
            "%s defines kinds %s, and this gate re-derives exactly %s. A kind the code does "
            "not know is a classification nothing checks; a kind removed from the file is a "
            "definition the entries still lean on." % (SPEC_REL, sorted(spec["kinds"]), list(KINDS))
        )
    for name, entry in spec["vars"].items():
        if not isinstance(entry, dict):
            raise RefusalError("%s: the entry for %r is not an object" % (SPEC_REL, name))
    return spec


def read_bootstrap(root: pathlib.Path) -> set[str]:
    names = _load(root, SUPPLY_REL).get("bootstrap_names")
    if not isinstance(names, list) or not names or not all(isinstance(n, str) for n in names):
        raise RefusalError(
            "%s has no non-empty `bootstrap_names`. That list is the ruling on which "
            "credential may stay a GitHub secret; with it gone the secrets arm would allow "
            "whatever the reader wanted." % SUPPLY_REL
        )
    return set(names)


def scan(root: pathlib.Path):
    """(vars_reads, secrets_reads, jobs_by_file, commented, file_count) over the shared corpus."""
    files = workflows.call_sites(root)
    if not files:
        raise RefusalError(
            "zero workflow files under %s (.github/workflows/*.yml, .github/actions/*/action.yml, "
            ".ci/breakpoint/workflow/*.yml). That is the instrument having lost the tree, not a "
            "repository with no workflows." % root
        )
    reads = {"vars": [], "secrets": []}
    commented = {"vars": 0, "secrets": 0}
    jobs = {}
    for path in files:
        rel = path.relative_to(root).as_posix()
        lines = path.read_text(encoding="utf-8").split("\n")
        index = workflows.job_index(lines)
        jobs[rel] = {name for _, name in index}
        for ctx, bucket in reads.items():
            found, skipped = workflows.context_reads(lines, ctx)
            commented[ctx] += skipped
            bucket.extend(Read(rel, i + 1, workflows.job_at(index, i), n) for i, n in found)
    return reads["vars"], reads["secrets"], jobs, commented, len(files)


# --------------------------------------------------------------------------- the clauses, pure so the controls drive them without a tree ---------------------------------------------------------------------------


def _where(read: Read) -> str:
    return "%s:%d job %s" % (read.path, read.line, read.job or "(above the first job)")


def evaluate_vars(spec, vars_reads, jobs, vault: set[str]) -> list[str]:
    """Clauses 1, 2 and 3."""
    entries = spec["vars"]
    no_fetch = spec["no_fetch_jobs"]
    by_name = collections.defaultdict(list)
    for read in vars_reads:
        by_name[read.name].append(read)
    findings = []

    # 1. FORWARD
    findings.extend(
        "UNDECLARED %s reads vars.%s, and %s has no entry for it. The ruling is that no "
        "workflow depends on a GitHub variable: seed the value into ci-shared, refresh the "
        "map, and read it through ./.github/actions/bws-secrets instead. If you got here by "
        "DELETING the entry, the read is still there -- trimming the file is not a way past "
        "the gate." % (_where(read), read.name, SPEC_REL)
        for read in vars_reads
        if read.name not in entries
    )

    # 2. REVERSE
    findings.extend(
        "RESOLVED %s -- %s has an entry and nothing in the corpus reads vars.%s any more. "
        "Either the migration landed (delete the entry, and the GitHub variable once a real "
        "CI run is green) or the read moved somewhere this gate does not scan and the entry "
        "now lies. An entry for a read that does not exist is also what pre-banking looks "
        "like, which is refused here too." % (name, SPEC_REL, name)
        for name in sorted(set(entries) - set(by_name))
    )

    # 3. KINDS
    listed = collections.defaultdict(set)  # name -> {"path#job"}
    for key, rec in sorted(no_fetch.items()):
        if not isinstance(rec, dict):
            findings.append(
                "MALFORMED no_fetch_jobs %r: it is a %s, not an object. Write it as "
                '{"names": [...], "reason": "BLOCKER: ..."}.' % (key, type(rec).__name__)
            )
            continue
        path, _, job = key.partition("#")
        reason = str(rec.get("reason", ""))
        names = rec.get("names")
        if not reason.startswith("BLOCKER:") or len(reason) < MIN_REASON:
            findings.append(
                "THIN REASON no_fetch_jobs %r: it must start with 'BLOCKER:' and say what makes "
                "that job unable to fetch, or the list becomes a place to put anything "
                "inconvenient." % key
            )
        if not isinstance(names, list) or not names:
            findings.append(
                "NO NAMES no_fetch_jobs %r: say which variables the job may keep reading." % key
            )
            continue
        if path not in jobs or job not in jobs[path]:
            findings.append(
                "STALE no_fetch_jobs %r: %s. An exemption for a job that is gone forgives "
                "nothing; delete the row."
                % (key, "no such file in the corpus" if path not in jobs else "no such job in it")
            )
            continue
        for name in names:
            listed[name].add(key)
            if entries.get(name, {}).get("kind") != "no-fetch-job":
                findings.append(
                    "ORPHAN no_fetch_jobs %r lists %s, whose entry is not kind `no-fetch-job`. "
                    "The row and the entry must agree." % (key, name)
                )
            if not any(r.path == path and r.job == job for r in by_name.get(name, ())):
                findings.append(
                    "STALE no_fetch_jobs %r: job %s no longer reads vars.%s. The exemption "
                    "forgives nothing; delete the name from the row." % (key, job, name)
                )

    for name in sorted(entries):
        entry = entries[name]
        kind = entry.get("kind")
        if kind not in KINDS:
            findings.append(
                "UNDEFINED KIND %s: `%s` is not one of %s." % (name, kind, ", ".join(KINDS))
            )
        if not str(entry.get("why", "")).strip():
            findings.append(
                "NO REASON %s: every entry says why the variable has not moved. An unreasoned "
                "entry is a suppression nobody is looking at." % name
            )
        if kind == "migrated":
            twin = entry.get("bws") or name
            if twin not in vault:
                findings.append(
                    "FALSE MIGRATION %s: kind `migrated` names the ci-shared twin %s, and %s "
                    "does not hold it. Seed it and run scripts/ops/bws-map-refresh.py first."
                    % (name, twin, MAP_REL)
                )
        elif entry.get("bws"):
            findings.append("STRAY bws ON %s: only a `migrated` entry names a twin." % name)
        if kind == "no-fetch-job":
            if not listed.get(name):
                findings.append(
                    "NO JOB %s: kind `no-fetch-job` needs a `<path>#<job>` row under "
                    "`no_fetch_jobs` listing it." % name
                )
            findings.extend(
                "FETCHABLE %s reads vars.%s, which is kind `no-fetch-job`, and %s#%s is not a "
                "listed no-fetch job. That job can fetch, so the read migrates."
                % (_where(read), name, read.path, read.job)
                for read in by_name.get(name, ())
                if "%s#%s" % (read.path, read.job) not in listed.get(name, set())
            )
        if kind == "dead":
            findings.append(
                "DEAD ENTRY %s: a variable nothing reads is deleted from GitHub with `gh "
                "variable delete`, not recorded here." % name
            )
    return findings


def evaluate_secrets(secrets_reads, bootstrap: set[str]) -> list[str]:
    """Clause 4."""
    allowed = bootstrap | RUNNER_MINTED
    return [
        "GITHUB SECRET %s reads secrets.%s. The only GitHub secrets allowed are the bootstrap "
        "ruling in %s (%s) and the runner-minted %s. Seed the value into ci-shared and fetch "
        "it through ./.github/actions/bws-secrets."
        % (
            _where(read),
            read.name,
            SUPPLY_REL,
            ", ".join(sorted(bootstrap)),
            ", ".join(sorted(RUNNER_MINTED)),
        )
        for read in secrets_reads
        if read.name not in allowed
    ]


def run(root=None):
    """(findings, stats). Refuses rather than guessing."""
    root = pathlib.Path(root or paths.repo_root())
    spec = read_spec(root)
    vault_doc = _load(root, MAP_REL)
    vault = set(vault_doc.get("secrets") or ())
    if not vault:
        raise RefusalError(
            "%s lists no secrets. Every `migrated` claim would red against an empty map, "
            "and a refresh that produced one is a broken refresh." % MAP_REL
        )
    bootstrap = read_bootstrap(root)
    vars_reads, secrets_reads, jobs, commented, n_files = scan(root)

    if not secrets_reads:
        raise RefusalError(
            "zero `secrets.*` reads in %d workflow file(s). Every Bitwarden fetch reads "
            "secrets.BWS_ACCESS_TOKEN, so a scan that finds none has stopped scanning; this "
            "stays true when every variable has moved." % n_files
        )
    findings = evaluate_vars(spec, vars_reads, jobs, vault)
    findings += evaluate_secrets(secrets_reads, bootstrap)
    stats = {
        "files": n_files,
        "vars_reads": len(vars_reads),
        "vars_names": len({r.name for r in vars_reads}),
        "secrets": collections.Counter(r.name for r in secrets_reads),
        "entries": len(spec["vars"]),
        "no_fetch_jobs": len(spec["no_fetch_jobs"]),
        "commented": commented,
    }
    return findings, stats


# --------------------------------------------------------------------------- output ---------------------------------------------------------------------------


def report(stats) -> None:
    log.info(
        "  %d workflow file(s) scanned; %d vars.* read(s) of %d distinct name(s); %d "
        "entr(y/ies) in %s, %d no-fetch job(s)"
        % (
            stats["files"],
            stats["vars_reads"],
            stats["vars_names"],
            stats["entries"],
            SPEC_REL,
            stats["no_fetch_jobs"],
        )
    )
    log.info(
        "  secrets.* reads: %s"
        % ", ".join("%s %d" % (n, c) for n, c in sorted(stats["secrets"].items()))
    )
    log.info(
        "  commented mentions skipped, not counted as reads: vars.* %d, secrets.* %d"
        % (stats["commented"]["vars"], stats["commented"]["secrets"])
    )


def main(argv=None) -> int:
    argv = list(argv or [])
    if "--selftest" in argv:
        return 1 if selftest() else 0
    rc = controls_first("actions vars", selftest)
    if rc:
        return rc
    try:
        findings, stats = run()
    except (RefusalError, paths.RootError) as exc:
        log.error("actions vars: %s" % exc)
        return 1
    report(stats)
    if findings:
        for finding in findings:
            log.error("  %s" % finding)
        log.error(
            "%d finding(s) against %s. The file is set-equal with the tree in both directions, "
            "so a row that does not correspond to a real read reds the other way."
            % (len(findings), SPEC_REL)
        )
        return 1
    log.success(
        "actions vars: %d vars.* read(s), all declared and re-derived; every secrets.* read "
        "is the bootstrap token or the runner's own" % stats["vars_reads"]
    )
    return 0


# --------------------------------------------------------------------------- controls ---------------------------------------------------------------------------
#
# Every mutation goes through `plant()`, which raises when a substitution would not change the fixture, so no control can pass against clean input. Both directions of every clause are driven: a plant that must red, and a near-miss that must not.

_WORKFLOW = """\
name: fixture
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Fetch
        uses: ./.github/actions/bws-secrets
        with:
          access-token: ${{ secrets.BWS_ACCESS_TOKEN }}
          secrets: |
            FIX_TWIN > BWS_FIX_TWIN
      # set-account-worker-secrets.sh blanks a value here; commented, and a path
      # commented read: ${{ vars.FIX_COMMENTED }} and secrets.FIX_COMMENTED_SECRET
      - name: Use
        env:
          A: ${{ vars.FIX_PENDING }}
          B: plain  # vars.FIX_TRAILING_COMMENT is prose after a comment marker
          C: ${{ secrets.GITHUB_TOKEN }}
        run: |
          ./scripts/set-account-worker-secrets.sh
          echo "#${{ vars.FIX_QUOTED }}"
  shell:
    runs-on: ubuntu-latest
    steps:
      - name: Human shell
        env:
          D: ${{ vars.FIX_SHELL }}
        run: echo shell
"""

_SPEC = {
    "kinds": dict.fromkeys(KINDS, "fixture"),
    "vars": {
        "FIX_PENDING": {"kind": "migrated", "bws": "FIX_TWIN", "why": "the edit still to land"},
        "FIX_QUOTED": {
            "kind": "migrated",
            "bws": "FIX_TWIN",
            "why": "a quoted hash is not a comment",
        },
        "FIX_SHELL": {"kind": "no-fetch-job", "why": "the fixture's human-shell job"},
    },
    "no_fetch_jobs": {
        ".github/workflows/fixture.yml#shell": {
            "names": ["FIX_SHELL"],
            "reason": "BLOCKER: the fixture's job hands a human a shell, so nothing it fetches may land in GITHUB_ENV",
        }
    },
}
_MAP = {"project": "fixture", "secrets": {"FIX_TWIN": {}}}
_SUPPLY = {"bootstrap_names": ["BWS_ACCESS_TOKEN"]}


def _fixture(tmp, workflow=None, spec=None, vault_map=None, supply=None):
    import copy  # noqa: PLC0415

    root = pathlib.Path(tmp)
    (root / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (root / ".ci" / "config").mkdir(parents=True, exist_ok=True)
    (root / ".github" / "workflows" / "fixture.yml").write_text(
        workflow if workflow is not None else _WORKFLOW, encoding="utf-8"
    )
    for rel, obj, default in (
        (SPEC_REL, spec, _SPEC),
        (MAP_REL, vault_map, _MAP),
        (SUPPLY_REL, supply, _SUPPLY),
    ):
        doc = copy.deepcopy(obj if obj is not None else default)
        (root / rel).write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return root


def _refuses(root) -> bool:
    try:
        run(root)
    except RefusalError:
        return True
    return False


def _has(root, prefix: str) -> bool:
    return any(f.startswith(prefix) for f in run(root)[0])


def selftest() -> bool:
    """True when a control failed, which is what `controls_first` expects."""
    import copy  # noqa: PLC0415
    import tempfile  # noqa: PLC0415

    check = Checker()

    with tempfile.TemporaryDirectory() as tmp:
        findings, stats = run(_fixture(tmp))
        check("CONTROL: a spec matching its fixture is clean", findings == [])
        check(
            "CONTROL: and the scan is NOT trivially empty (3 live vars reads, 3 names)",
            (stats["vars_reads"], stats["vars_names"]) == (3, 3),
        )
        check(
            "CONTROL: both live secrets reads are seen, the bootstrap token and the runner's",
            dict(stats["secrets"]) == {"BWS_ACCESS_TOKEN": 1, "GITHUB_TOKEN": 1},
        )
        check(
            "ANTI-SILENCER: the commented mentions are counted, not silently dropped",
            stats["commented"] == {"vars": 2, "secrets": 1},
        )

    # ---- the four plants the plan names, each red against a green fixture ----
    with tempfile.TemporaryDirectory() as tmp:
        wf = plant(
            _WORKFLOW,
            "          C: ${{ secrets.GITHUB_TOKEN }}\n",
            "          C: ${{ secrets.GITHUB_TOKEN }}\n          E: ${{ vars.FIX_NEW }}\n",
        )
        check(
            "PLANT 1: a vars.X read with no entry reds as UNDECLARED, naming file, line and job",
            any(
                f.startswith(
                    "UNDECLARED .github/workflows/fixture.yml:20 job build reads vars.FIX_NEW"
                )
                for f in run(_fixture(tmp, workflow=wf))[0]
            ),
        )
    with tempfile.TemporaryDirectory() as tmp:
        wf = plant(_WORKFLOW, "          A: ${{ vars.FIX_PENDING }}\n", "")
        check(
            "PLANT 2: an entry whose last read was removed reds as RESOLVED",
            _has(_fixture(tmp, workflow=wf), "RESOLVED FIX_PENDING"),
        )
    with tempfile.TemporaryDirectory() as tmp:
        wf = plant(_WORKFLOW, "          D: ${{ vars.FIX_SHELL }}\n", "          D: literal\n")
        root = _fixture(tmp, workflow=wf)
        check(
            "PLANT 3: a no-fetch-job row whose job no longer reads the name reds as STALE",
            _has(
                root,
                "STALE no_fetch_jobs '.github/workflows/fixture.yml#shell': job shell no longer",
            ),
        )
    with tempfile.TemporaryDirectory() as tmp:
        wf = plant(_WORKFLOW, "${{ secrets.GITHUB_TOKEN }}", "${{ secrets.SOMETHING }}")
        check(
            "PLANT 4: a new secrets.SOMETHING read reds as GITHUB SECRET",
            _has(
                _fixture(tmp, workflow=wf),
                "GITHUB SECRET .github/workflows/fixture.yml:19 job build reads secrets.SOMETHING",
            ),
        )

    # ---- the two false-positive guards, both arms ----
    check(
        "FALSE POSITIVE 1: `set-account-worker-secrets.sh` is not a secrets read, live or commented",
        workflows.context_reads(
            [
                "# set-account-worker-secrets.sh:150",
                "run: ./set-www-worker-secrets.sh",
                "x secrets.sh",
            ],
            "secrets",
        )
        == ([], 0),
    )
    check(
        "FALSE POSITIVE 1b: a name that runs on into a path is not a read",
        workflows.context_reads(["cat secrets.FOO.sh secrets.BAR/x vars.BAZ-1"], "secrets")[0] == []
        and workflows.context_reads(["vars.BAZ-1"], "vars")[0] == [],
    )
    check(
        "FALSE POSITIVE 2: a commented ${{ vars.X }} and a commented secrets.X do not fire",
        workflows.context_reads(["  # ${{ vars.X }}", "a: b # ${{ vars.Y }}"], "vars") == ([], 2)
        and workflows.context_reads(["    # || secrets.ANTHROPIC_X fallback"], "secrets")
        == ([], 1),
    )
    check(
        "ANTI-SILENCER: a # inside quotes is not a comment, so the read after it counts",
        workflows.context_reads(['echo "#${{ vars.X }}"', "x: '#' ${{ vars.Y }}"], "vars")[0]
        == [(0, "X"), (1, "Y")],
    )
    check(
        "ANTI-SILENCER: a sentence-final period does not hide a read",
        workflows.context_reads(["see ${{ vars.X }}."], "vars")[0] == [(0, "X")],
    )

    # ---- clause 3, the kinds, both directions ----
    with tempfile.TemporaryDirectory() as tmp:
        empty_map = copy.deepcopy(_MAP)
        empty_map["secrets"] = {"SOMETHING_ELSE": {}}
        check(
            "CONTROL: `migrated` with no twin in the map reds as FALSE MIGRATION",
            _has(_fixture(tmp, vault_map=empty_map), "FALSE MIGRATION FIX_PENDING"),
        )
    with tempfile.TemporaryDirectory() as tmp:
        spec = copy.deepcopy(_SPEC)
        spec["vars"]["FIX_PENDING"]["kind"] = "dead"
        spec["vars"]["FIX_PENDING"].pop("bws")
        check(
            "CONTROL: a `dead` entry is refused on sight",
            _has(_fixture(tmp, spec=spec), "DEAD ENTRY FIX_PENDING"),
        )
    with tempfile.TemporaryDirectory() as tmp:
        wf = plant(
            _WORKFLOW,
            "          A: ${{ vars.FIX_PENDING }}\n",
            "          A: ${{ vars.FIX_PENDING }}\n          S: ${{ vars.FIX_SHELL }}\n",
        )
        check(
            "CONTROL: a no-fetch-job name read in a job that CAN fetch reds as FETCHABLE",
            _has(
                _fixture(tmp, workflow=wf), "FETCHABLE .github/workflows/fixture.yml:18 job build"
            ),
        )
    with tempfile.TemporaryDirectory() as tmp:
        spec = copy.deepcopy(_SPEC)
        spec["no_fetch_jobs"][".github/workflows/fixture.yml#shell"]["reason"] = "BLOCKER: shell"
        check("CONTROL: a thin BLOCKER reason reds", _has(_fixture(tmp, spec=spec), "THIN REASON"))
    with tempfile.TemporaryDirectory() as tmp:
        spec = copy.deepcopy(_SPEC)
        row = spec["no_fetch_jobs"].pop(".github/workflows/fixture.yml#shell")
        spec["no_fetch_jobs"][".github/workflows/fixture.yml#gone"] = row
        root = _fixture(tmp, spec=spec)
        check(
            "CONTROL: a row naming a job that does not exist reds as STALE",
            _has(root, "STALE no_fetch_jobs '.github/workflows/fixture.yml#gone': no such job"),
        )
        check(
            "CONTROL: and the name it no longer covers reds as NO JOB",
            _has(root, "NO JOB FIX_SHELL"),
        )
    with tempfile.TemporaryDirectory() as tmp:
        spec = copy.deepcopy(_SPEC)
        spec["no_fetch_jobs"][".github/workflows/fixture.yml#shell"]["names"].append("FIX_PENDING")
        check(
            "CONTROL: a row listing a name of another kind reds as ORPHAN",
            _has(_fixture(tmp, spec=spec), "ORPHAN"),
        )
    with tempfile.TemporaryDirectory() as tmp:
        spec = copy.deepcopy(_SPEC)
        spec["vars"]["FIX_QUOTED"]["kind"] = "invented"
        check(
            "CONTROL: an undefined kind reds",
            _has(_fixture(tmp, spec=spec), "UNDEFINED KIND FIX_QUOTED"),
        )
    with tempfile.TemporaryDirectory() as tmp:
        spec = copy.deepcopy(_SPEC)
        spec["vars"]["FIX_QUOTED"]["why"] = "  "
        check(
            "CONTROL: a blank reason reds", _has(_fixture(tmp, spec=spec), "NO REASON FIX_QUOTED")
        )
    with tempfile.TemporaryDirectory() as tmp:
        spec = copy.deepcopy(_SPEC)
        del spec["vars"]["FIX_QUOTED"]
        check(
            "TAMPER: deleting an entry whose read persists reds, so the file cannot be trimmed",
            _has(
                _fixture(tmp, spec=spec),
                "UNDECLARED .github/workflows/fixture.yml:22 job build reads vars.FIX_QUOTED",
            ),
        )
    with tempfile.TemporaryDirectory() as tmp:
        supply = {"bootstrap_names": ["SOME_OTHER_TOKEN"]}
        check(
            "CONTROL: the secrets arm takes its ruling from secret-supply.json, not a constant",
            _has(
                _fixture(tmp, supply=supply),
                "GITHUB SECRET .github/workflows/fixture.yml:10 job build reads secrets.BWS_ACCESS_TOKEN",
            ),
        )

    # ---- anti-vacuity: refusals, and the terminal state that must pass ----
    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp)
        (root / ".github" / "workflows" / "fixture.yml").unlink()
        check("REFUSAL: zero workflow files is the instrument losing the tree", _refuses(root))
    with tempfile.TemporaryDirectory() as tmp:
        wf = plant(_WORKFLOW, "${{ secrets.BWS_ACCESS_TOKEN }}", "x")
        wf = plant(wf, "${{ secrets.GITHUB_TOKEN }}", "y")
        check(
            "REFUSAL: zero secrets.* reads is a scan that stopped scanning",
            _refuses(_fixture(tmp, workflow=wf)),
        )
    with tempfile.TemporaryDirectory() as tmp:
        spec = copy.deepcopy(_SPEC)
        spec["vars"] = {}
        spec["no_fetch_jobs"] = {}
        root = _fixture(tmp, spec=spec)
        check(
            "TAMPER: emptying `vars` beside live reads reds once per read, it does not pass",
            not _refuses(root)
            and len([f for f in run(root)[0] if f.startswith("UNDECLARED ")]) == 3,
        )
    with tempfile.TemporaryDirectory() as tmp:
        spec = copy.deepcopy(_SPEC)
        del spec["kinds"]["dead"]
        check(
            "REFUSAL: a kinds table that disagrees with the code refuses",
            _refuses(_fixture(tmp, spec=spec)),
        )
    with tempfile.TemporaryDirectory() as tmp:
        check(
            "REFUSAL: an empty vault map refuses",
            _refuses(_fixture(tmp, vault_map={"secrets": {}})),
        )
    with tempfile.TemporaryDirectory() as tmp:
        check("REFUSAL: a missing bootstrap ruling refuses", _refuses(_fixture(tmp, supply={})))
    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp)
        (root / SPEC_REL).unlink()
        check("REFUSAL: deleting the spec refuses, it does not pass", _refuses(root))
    with tempfile.TemporaryDirectory() as tmp:
        root = _fixture(tmp)
        (root / SPEC_REL).write_text("{not json", encoding="utf-8")
        check("REFUSAL: a corrupt spec refuses, it is not read as empty", _refuses(root))
    with tempfile.TemporaryDirectory() as tmp:
        wf = plant(_WORKFLOW, "          A: ${{ vars.FIX_PENDING }}\n", "")
        wf = plant(wf, '          echo "#${{ vars.FIX_QUOTED }}"\n', "")
        wf = plant(wf, "          D: ${{ vars.FIX_SHELL }}\n", "          D: literal\n")
        spec = copy.deepcopy(_SPEC)
        spec["vars"] = {}
        spec["no_fetch_jobs"] = {}
        findings, stats = run(_fixture(tmp, workflow=wf, spec=spec))
        check(
            "ANTI-SILENCER: zero reads with an empty file is the TERMINAL state and passes, "
            "so no floor reds on success",
            findings == [] and stats["vars_reads"] == 0,
        )

    return not check.ok


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
