"""Port of `.ci/scripts/test/gates/test-review-labels.sh`, retired in W7 P5.

Both-ways test for `claude-review-gate.sh --apply-labels`, the arm that labels a PR
from the automated review that just ran.

WHY THIS CLASS NEEDS A GATE. This arm writes to the repository on the word of a language model, and it is the one piece of the review pipeline that cannot be exercised before it reaches main: the workflow runs review scripts from `console@main` by design. So the only pre-merge evidence that exists is this file, and it has to cover the two failures that would matter.

  TOO LOUD. A hallucinated or malformed verdict reaching the labels API.
  `POST /issues/{n}/labels` is not a safe call for an unvalidated name, and a stray
  label fails `check:ci-label-inventory` for the whole repo until someone deletes it
  by hand. Every write is captured here and asserted on BY NAME, and the negative
  cases assert the write did not happen at all.

  TOO QUIET. The mechanical floor must still land when the model produced nothing,
  because a starved review is the common failure mode of this pipeline, not an
  exotic one.

Plus the property that makes the design safe to run unattended: removal is scoped to the arm's OWN ledger comment, so a hand-applied label survives any verdict, and a tampered ledger cannot be turned into a delete-anything primitive.

THE ONE PLACE THE PORT MUST NOT BE LITERAL, carried over from the twin verbatim because the reason still applies. `test_kind_vocabulary_maps_to_the_repo_labels`
BUILDS its needle rather than spelling it out: the string `labels[]=<word>` written
literally in this file is indistinguishable, to `check:ci-label-refs`, from real code applying a label by that name, and that gate would then demand the label be declared and created. Interpolating dodges its extractor honestly rather than by asking for an exclusion.

GitHub is a routing fake `gh` serving fixture JSON per endpoint, applying the caller's own `--jq` so the real extraction runs, and CAPTURING every non-GET call
with its full argv.
"""

import datetime
import json
import os
import pathlib
import re
import shutil
import stat

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

UNDER_TEST = paths.from_root(".ci", "scripts", "review", "claude-review-gate.sh")
LABELS_FILE = paths.from_root(".github", "labels.yml")
INVENTORY_GATE = paths.from_root(".ci", "rediacc_ci", "quality", "label_inventory.py")
INITIAL_PROMPT = paths.from_root(".ci", "scripts", "review", "prompts", "initial.md")
FOLLOWUP_PROMPT = paths.from_root(".ci", "scripts", "review", "prompts", "followup.md")
REUSABLE_WF = paths.from_root(".github", "workflows", "claude-review-reusable.yml")

# The fence key the prompt emits and this arm parses. Asserted present in BOTH producers below, for the reason test_gate_review_status.py spells out about json:review-findings: a rename on one side alone makes the parser silently blind
# while everything still reports OK.
LABELS_FENCE_KEY = "json:pr-labels"
LEDGER_PREFIX_EXPECTED = "<!-- claude-labels:"

HEAD_SHA = "3333333333333333333333333333333333333333"

TICKS = "```"

FAKE_GH = r"""#!/bin/bash
# Routing fake for `gh api`. GETs are served from fixture JSON with the caller's own
# --jq applied; every write is captured with its FULL argv and never served, so an
# assertion can name the label that was written rather than merely counting calls.
set -uo pipefail
printf '%s\n' "$*" >>"$GH_CALLS"
if [ -n "${GH_FAIL_ALL:-}" ]; then
    echo "fake gh: forced API failure" >&2
    exit 1
fi
method="GET"
path=""
jqexpr=""
args=("$@")
n=${#args[@]}
i=0
while [ "$i" -lt "$n" ]; do
    a="${args[$i]}"
    case "$a" in
        api) ;;
        -X | --method)
            i=$((i + 1))
            method="${args[$i]}"
            ;;
        --jq)
            i=$((i + 1))
            jqexpr="${args[$i]}"
            ;;
        -f | -F | --field | --raw-field | --input)
            i=$((i + 1))
            ;;
        --paginate | --silent) ;;
        -*) ;;
        *)
            if [ -z "$path" ]; then path="$a"; fi
            ;;
    esac
    i=$((i + 1))
done

if [ "$method" != "GET" ]; then
    {
        echo "WRITE $method $path"
        for a in "$@"; do
            case "$a" in
                -f | -F | --field | --raw-field | api | --silent) ;;
                *) echo "ARG $a" ;;
            esac
        done
        echo "ENDCALL"
    } >>"$GH_CAPTURE"
    echo '{"id": 4242}'
    exit 0
fi

key=""
case "$path" in
    */pulls/*/files) key="files" ;;
    */issues/*/comments) key="comments" ;;
    */pulls/*/comments) key="inline-comments" ;;
    */labels/*)
        # The single-label existence probe (create-on-demand). Absence is a 404,
        # which is a NON-ZERO exit, exactly as gh reports it.
        name="${path##*/labels/}"
        if [ -f "$GH_FIXTURES/live-labels.txt" ] && grep -qxF "$name" "$GH_FIXTURES/live-labels.txt"; then
            printf '{"name": "%s"}\n' "$name"
            exit 0
        fi
        echo "gh: Not Found (HTTP 404)" >&2
        exit 1
        ;;
    *)
        echo "fake gh: unrouted path: $path" >&2
        exit 3
        ;;
esac

file="$GH_FIXTURES/$key.json"
if [ ! -f "$file" ]; then
    echo "fake gh: missing fixture $file" >&2
    exit 4
fi
if [ -n "$jqexpr" ]; then
    jq -r "$jqexpr" "$file"
else
    cat "$file"
fi
"""


def report_with_verdict(verdict: str = "") -> str:
    """The model's final report text, in the shape `--post-report` posts."""
    parts = [
        "## Review verdict: approve",
        "",
        "<details><summary>machine-readable findings</summary>",
        "",
        "%sjson:review-findings" % TICKS,
        "[]",
        TICKS,
        "",
        "</details>",
    ]
    if verdict:
        parts += ["", "%s%s" % (TICKS, LABELS_FENCE_KEY), verdict, TICKS]
    return "".join("%s\n" % line for line in parts)


def ledger_comment(comment_id: int, sha: str, applied: str) -> dict:
    return {
        "id": comment_id,
        "user": {"login": "github-actions[bot]"},
        "created_at": "2026-08-08T00:00:00Z",
        "body": "<!-- claude-labels: %s -->\napplied: %s" % (sha, applied),
    }


class World:
    """One temp review world: fake gh, its fixtures, the write capture."""

    def __init__(self, root: pathlib.Path) -> None:
        self.root = root
        self.bin = root / "bin"
        self.fixtures = root / "fixtures"
        self.capture = root / "capture.txt"
        self.calls = root / "calls.txt"
        self.execution = root / "execution.json"
        self.out = ""
        self.rc = 0

    def setup(self) -> None:
        """Reset to the default world: an ordinary source-code PR, no prior ledger, every managed label except `ci` already live on the repo."""
        shutil.rmtree(self.fixtures, ignore_errors=True)
        shutil.rmtree(self.bin, ignore_errors=True)
        self.fixtures.mkdir(parents=True)
        self.bin.mkdir(parents=True)
        gh = self.bin / "gh"
        gh.write_text(FAKE_GH, encoding="utf-8")
        gh.chmod(gh.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        self.calls.write_text("", encoding="utf-8")
        if self.capture.exists():
            self.capture.unlink()
        self.files_fixture("packages/cli/src/commands/repo.ts")
        self.comments_fixture()
        (self.fixtures / "inline-comments.json").write_text("[]\n", encoding="utf-8")
        self.live_labels(
            "bug", "enhancement", "documentation", "bump-minor", "bump-major", "full-ci", "rollback"
        )
        self.execution_file(
            report_with_verdict('{"bump": "patch", "kind": [], "why": "nothing to see"}')
        )

    def files_fixture(self, *filenames: str) -> None:
        (self.fixtures / "files.json").write_text(
            json.dumps([{"filename": f} for f in filenames]), encoding="utf-8"
        )

    def comments_fixture(self, *comments: dict) -> None:
        (self.fixtures / "comments.json").write_text(json.dumps(list(comments)), encoding="utf-8")

    def live_labels(self, *names: str) -> None:
        (self.fixtures / "live-labels.txt").write_text(
            "".join("%s\n" % n for n in names), encoding="utf-8"
        )

    def execution_file(self, report: str) -> None:
        self.execution.write_text(
            json.dumps([{"type": "result", "subtype": "success", "result": report}]),
            encoding="utf-8",
        )

    # -- driving -----------------------------------------------------------

    def _env(self, **extra: str) -> dict[str, str]:
        env = {
            "PATH": "%s%s%s" % (self.bin, os.pathsep, os.environ.get("PATH", "")),
            "GH_FIXTURES": str(self.fixtures),
            "GH_CAPTURE": str(self.capture),
            "GH_CALLS": str(self.calls),
            "GH_TOKEN": "fake",
            "GITHUB_REPOSITORY": "rediacc/console",
            "PR_NUMBER": "42",
            "HEAD_SHA": HEAD_SHA,
            "EXECUTION_FILE": str(self.execution),
            "NO_COLOR": "1",
        }
        env.update(extra)
        return env

    def run_apply(self, **env: str) -> None:
        bash = harness.require_tool("bash", "install bash; the subject is a bash script")
        result = harness.run(
            [bash, str(UNDER_TEST), "--apply-labels"], env=self._env(**env), timeout=120
        )
        self.out = result.combined
        self.rc = result.rc

    def run_mark(self, **env: str) -> None:
        bash = harness.require_tool("bash", "install bash; the subject is a bash script")
        overlay = self._env(**env)
        overlay.pop("EXECUTION_FILE")
        result = harness.run([bash, str(UNDER_TEST), "--mark"], env=overlay, timeout=120)
        self.out = result.combined
        self.rc = result.rc

    # -- reading the capture -----------------------------------------------

    def captured(self) -> str:
        return self.capture.read_text(encoding="utf-8") if self.capture.is_file() else ""

    def added(self) -> str:
        """Label names sent to the add-labels endpoint, sorted and space-joined."""
        names = re.findall(r"^ARG labels\[\]=(.*)$", self.captured(), re.MULTILINE)
        return " ".join(sorted(names))

    def removed(self) -> str:
        names = re.findall(
            r"^WRITE DELETE .*/issues/42/labels/(.*)$", self.captured(), re.MULTILINE
        )
        return " ".join(sorted(names))

    def created(self) -> str:
        """Label names sent to the CREATE-a-label endpoint. The awk block, ported."""
        names = []
        inblock = False
        for line in self.captured().splitlines():
            if line == "WRITE POST repos/rediacc/console/labels":
                inblock = True
                continue
            if line == "ENDCALL":
                inblock = False
            if inblock and line.startswith("ARG name="):
                names.append(line[len("ARG name=") :])
        return " ".join(sorted(names))

    def ledger(self) -> str:
        """The `applied:` line of the ledger comment body that was written."""
        found = re.findall(r"^applied: *(.*)$", self.captured(), re.MULTILINE)
        return found[-1] if found else ""

    def ledger_written(self) -> bool:
        return "ARG body=<!-- claude-labels:" in self.captured()


def make_world(gate, tmp_path) -> World:
    if not UNDER_TEST.is_file():
        gate.log_fail("%s is missing" % paths.relative_to_root(UNDER_TEST))
    harness.require_tool("jq", "install jq; the fake gh applies the caller's own --jq")
    world = World(tmp_path)
    world.setup()
    return world


def label_declared(name: str) -> bool:
    return bool(
        re.search(
            r"^- name: %s$" % re.escape(name),
            LABELS_FILE.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
    )


def label_field(name: str, field: str) -> str:
    """The `color` or `description` of `name` in labels.yml, or "" if absent.

    The twin's two awk one-liners, collapsed into one reader because they walk the identical block and differ only in which key they take out of it.
    """
    found = False
    for line in LABELS_FILE.read_text(encoding="utf-8").splitlines():
        if line == "- name: %s" % name:
            found = True
            continue
        if found and line.startswith("- name: "):
            break
        if found and line.startswith("  %s: " % field):
            return line[len("  %s: " % field) :].strip().strip('"')
    return ""


# --- FIRE: the writes that must happen --------------------------------------


def test_valid_verdict_applies_exactly_that_set(gate, tmp_path):
    world = make_world(gate, tmp_path)
    world.execution_file(
        report_with_verdict('{"bump": "minor", "kind": ["bug"], "why": "new flag plus a fix"}')
    )
    world.run_apply()
    gate.assert_exit(0, world, "the arm is advisory and always exits 0")
    gate.assert_eq(world.added(), "bug bump-minor", "exactly the mapped verdict, nothing else")
    gate.assert_eq(world.removed(), "", "nothing to remove on a first pass")
    gate.assert_eq(
        world.ledger(), "bump-minor,bug", "the ledger records what was applied, in apply order"
    )
    gate.log_pass(
        "FIRE: a valid verdict applies exactly its mapped set and records it in the ledger"
    )


def test_kind_vocabulary_maps_to_the_repo_labels(gate, tmp_path):
    """`feature` and `docs` are the model's vocabulary; the repo's labels are `enhancement` and `documentation`. A pass-through would create two new labels on the repo and fail the inventory gate."""
    world = make_world(gate, tmp_path)
    world.execution_file(
        report_with_verdict('{"bump": "patch", "kind": ["feature", "docs"], "why": "x"}')
    )
    world.run_apply()
    gate.assert_eq(
        world.added(), "documentation enhancement", "feature -> enhancement, docs -> documentation"
    )
    # The needle is BUILT, never spelled out. See the module docstring: written literally, it is indistinguishable to check:ci-label-refs from real code applying a label by that name.
    for raw in ("feature", "docs"):
        gate.assert_not_contains(
            world.captured(),
            "labels[]=%s" % raw,
            "the raw vocabulary word '%s' is never written to the labels API" % raw,
        )
    gate.log_pass("FIRE: the model's kind vocabulary is mapped to this repo's label names")


# --- the operator ruling: a major verdict is a RECOMMENDATION ---------------


def test_major_verdict_is_never_applied(gate, tmp_path):
    world = make_world(gate, tmp_path)
    world.execution_file(
        report_with_verdict('{"bump": "major", "kind": [], "why": "config schema break"}')
    )
    world.run_apply()
    gate.assert_eq(world.added(), "", "a major verdict applies NOTHING on the model's word")
    gate.assert_not_contains(world.captured(), "bump-major", "bump-major never reaches any write")
    gate.assert_contains(
        world.out, "RECOMMENDS a major bump", "but it is said out loud, with the reason"
    )
    gate.assert_contains(world.out, "config schema break", "and the reason is the model's own")

    # CONTROL: the identical path with `minor` DOES write. Without it the assertion above passes just as well on a harness that writes nothing ever.
    world.setup()
    world.execution_file(report_with_verdict('{"bump": "minor", "kind": [], "why": "new command"}'))
    world.run_apply()
    gate.assert_eq(
        world.added(), "bump-minor", "CONTROL: the same code path applies bump-minor autonomously"
    )
    gate.log_pass(
        "major is recommendation-only, minor is autonomous (CONTROL proves writes are reachable)"
    )


def test_managed_set_excludes_bump_major_by_construction(gate):
    """Behaviour proves the `major` BRANCH does not apply it. This proves no OTHER branch could either: the label is absent from the whitelist every write passes."""
    match = re.search(
        r"^MANAGED_LABELS=\((.*)\)$", UNDER_TEST.read_text(encoding="utf-8"), re.MULTILINE
    )
    managed = match.group(1) if match else ""
    if not managed:
        gate.log_fail(
            "MANAGED_LABELS is no longer parseable out of claude-review-gate.sh; this suite "
            "cannot prove what the arm may write"
        )
    gate.assert_not_contains(
        " %s " % managed,
        " bump-major ",
        "bump-major must never enter the managed set: every write path goes through it",
    )
    for name in managed.split():
        if not label_declared(name):
            gate.log_fail(
                "the applier may write '%s' but .github/labels.yml does not declare it; "
                "check:ci-label-inventory would fail the repo" % name
            )
    gate.log_pass(
        "every label the applier may write is declared, and bump-major is not one of them (%s)"
        % managed
    )


# --- TOO LOUD: malformed and hallucinated model output reaches nothing ------


def test_hallucinated_kind_invalidates_the_whole_verdict(gate, tmp_path):
    world = make_world(gate, tmp_path)
    world.files_fixture("docs/agent-reference/TRAPS.md")
    world.execution_file(
        report_with_verdict('{"bump": "minor", "kind": ["security"], "why": "made this up"}')
    )
    world.run_apply()
    gate.assert_not_contains(
        world.captured(), "security", "an invented label name never reaches the API"
    )
    gate.assert_eq(
        world.added(),
        "documentation",
        "the verdict is dropped WHOLE (no bump-minor either), and the mechanical floor still lands",
    )
    gate.assert_contains(world.out, "did not validate", "and it says the verdict was rejected")
    gate.log_pass("PLANTED hallucinated kind => whole verdict dropped, mechanical floor survives")


def test_malformed_json_is_treated_as_absent(gate, tmp_path):
    world = make_world(gate, tmp_path)
    world.files_fixture("docs/ci-overhaul/06-progress.md")
    world.execution_file(report_with_verdict('{"bump": "minor", "kind": [, oops'))
    world.run_apply()
    gate.assert_eq(world.added(), "documentation", "unparseable JSON applies no AI label at all")
    gate.assert_contains(world.out, "did not validate", "and says so")
    gate.log_pass("PLANTED unparseable fence => mechanical labels only")


def test_out_of_range_bump_is_rejected(gate, tmp_path):
    world = make_world(gate, tmp_path)
    world.execution_file(report_with_verdict('{"bump": "epic", "kind": ["bug"], "why": "x"}'))
    world.run_apply()
    gate.assert_eq(
        world.added(), "", "a bump value outside none|patch|minor|major invalidates the verdict"
    )
    gate.assert_not_contains(
        world.captured(), "epic", "and the invented value never leaves the script"
    )
    gate.log_pass("PLANTED bump=epic => verdict rejected whole")


def test_too_many_kinds_is_rejected(gate, tmp_path):
    world = make_world(gate, tmp_path)
    world.execution_file(
        report_with_verdict(
            '{"bump": "patch", "kind": ["bug", "feature", "docs"], "why": "everything"}'
        )
    )
    world.run_apply()
    gate.assert_eq(
        world.added(),
        "",
        "a kind list longer than the contract is a verdict that stopped following the contract",
    )
    gate.log_pass("PLANTED 3 kinds (contract says at most 2) => verdict rejected")


# --- TOO QUIET: the mechanical floor, the whole point of always() -----------


def test_missing_execution_file_still_applies_mechanical_labels(gate, tmp_path):
    world = make_world(gate, tmp_path)
    world.files_fixture(".ci/scripts/review/claude-review-gate.sh", ".github/workflows/ci.yml")
    world.run_apply(EXECUTION_FILE=str(tmp_path / "does-not-exist.json"))
    gate.assert_eq(
        world.added(),
        "ci",
        "a starved review (no execution file at all) still gets the path-derived label",
    )
    gate.assert_contains(world.out, "no json:pr-labels block", "and says why there was no verdict")
    gate.log_pass("no execution file => mechanical floor still lands (the starved-review case)")


def test_docs_only_diff_yields_documentation(gate, tmp_path):
    world = make_world(gate, tmp_path)
    world.files_fixture(
        "docs/agent-reference/ci-gates.md", "CLAUDE.md", "packages/cli/src/commands/repo.ts"
    )
    world.execution_file(report_with_verdict(""))
    gate.assert_eq(world.added(), "", "precondition: nothing captured yet")
    world.run_apply()
    # The rule is all-files and conservative: one real source file and this is not a docs PR, however many .md files ride along with it.
    gate.assert_eq(world.added(), "", "a single non-matching path disqualifies the all-files rule")

    world.setup()
    world.files_fixture(
        "docs/agent-reference/ci-gates.md",
        "CLAUDE.md",
        "LICENSE",
        "packages/www/src/content/docs/x.mdx",
    )
    world.execution_file(report_with_verdict(""))
    world.run_apply()
    gate.assert_eq(world.added(), "documentation", "CONTROL: an all-docs list DOES earn the label")
    gate.log_pass(
        "the documentation rule is all-files (one stray path disqualifies it; the control still fires)"
    )


def test_agent_notes_tree_is_documentation_whatever_the_extension(gate, tmp_path):
    """The tracked agent working-notes root. This arm exists SEPARATELY from the `\\.md$` alternative on purpose, and only a non-.md path can tell them apart."""
    world = make_world(gate, tmp_path)
    world.files_fixture(
        "agent/97604f47/STATE.md",
        "agent/programs/backup-storage/CHECKLIST.md",
        "agent/97604f47/report.json",
    )
    world.execution_file(report_with_verdict(""))
    world.run_apply()
    gate.assert_eq(
        world.added(),
        "documentation",
        "a notes-only diff earns documentation even with a non-.md file in it",
    )

    # CONTROL A: the arm is anchored to the tree, not to "any extension".
    world.setup()
    world.files_fixture("report.json")
    world.execution_file(report_with_verdict(""))
    world.run_apply()
    gate.assert_eq(world.added(), "", "the same file outside agent/ earns no label")

    # CONTROL B: all-files is still all-files.
    world.setup()
    world.files_fixture("agent/97604f47/STATE.md", "packages/cli/src/commands/repo.ts")
    world.execution_file(report_with_verdict(""))
    world.run_apply()
    gate.assert_eq(world.added(), "", "one source file disqualifies an otherwise notes-only diff")
    gate.log_pass("the agent/ notes tree is documentation by path, not by file extension")


def test_mixed_diff_earns_no_mechanical_label(gate, tmp_path):
    world = make_world(gate, tmp_path)
    world.files_fixture(
        ".ci/scripts/review/claude-review-gate.sh", "packages/cli/src/commands/repo.ts"
    )
    world.execution_file(report_with_verdict(""))
    world.run_apply()
    gate.assert_eq(world.added(), "", "a diff that is only PARTLY CI is not a CI PR")
    if not world.ledger_written():
        gate.log_fail(
            "the ledger must be written even when nothing is applied, or a later pass "
            "cannot reconcile"
        )
    gate.assert_eq(world.ledger(), "", "an empty ledger line is a real state, not a missing write")
    gate.log_pass("a mixed diff earns nothing, and the empty ledger is still recorded")


def test_unreadable_file_list_skips_the_mechanical_floor(gate, tmp_path):
    world = make_world(gate, tmp_path)
    (world.fixtures / "files.json").unlink()  # the files endpoint fails
    world.execution_file(report_with_verdict('{"bump": "minor", "kind": [], "why": "x"}'))
    world.run_apply()
    gate.assert_exit(0, world, "a failed file listing is advisory, like everything else here")
    gate.assert_eq(
        world.added(),
        "bump-minor",
        "the verdict still applies; only the path-derived part is skipped",
    )
    gate.assert_contains(
        world.out, "could not read the changed-file list", "and it says which half was skipped"
    )
    gate.log_pass("an unreadable file list skips the mechanical floor and keeps the verdict")


# --- create-on-demand -------------------------------------------------------


def test_ci_label_is_created_before_first_use(gate, tmp_path):
    world = make_world(gate, tmp_path)
    world.files_fixture(".ci/scripts/review/claude-review-gate.sh")
    world.execution_file(report_with_verdict(""))
    world.run_apply()
    gate.assert_eq(world.created(), "ci", "the label is created before it is applied")
    gate.assert_eq(world.added(), "ci", "and then applied")

    # CONTROL: once it exists, it must NOT be created again.
    world.setup()
    world.files_fixture(".ci/scripts/review/claude-review-gate.sh")
    world.execution_file(report_with_verdict(""))
    world.live_labels("bug", "enhancement", "documentation", "bump-minor", "ci")
    world.run_apply()
    gate.assert_eq(world.created(), "", "CONTROL: an existing label is not recreated")
    gate.assert_eq(world.added(), "ci", "but it is still applied")
    gate.log_pass(
        "the ci label is created on demand exactly once (probe drives it, not a blind create)"
    )


def test_create_on_demand_metadata_matches_the_declaration(gate):
    """The applier cannot read labels.yml (the post-review steps run from a staged copy of .ci alone), so colour and description are duplicated in the script. A duplicate with no gate drifts, and a drifted colour is a label that looks foreign in the UI forever. EVERY ROW, not just the first: the three scalars became a table when bump-none arrived, and a check reading only row
    one would leave row two free."""
    block = re.search(
        r"^CREATE_ON_DEMAND_LABELS=\(\n(.*?)^\)$",
        UNDER_TEST.read_text(encoding="utf-8"),
        re.MULTILINE | re.DOTALL,
    )
    rows = re.findall(r'^ *"(.*)"$', block.group(1), re.MULTILINE) if block else []
    if not rows:
        gate.log_fail("CREATE_ON_DEMAND_LABELS is no longer parseable out of claude-review-gate.sh")
    checked = 0
    for row in rows:
        name, color, desc = row.split("|", 2)
        yml_color = label_field(name, "color")
        yml_desc = label_field(name, "description")
        if not yml_color:
            gate.log_fail(
                "create-on-demand row '%s' names a label .github/labels.yml does not declare" % name
            )
        gate.assert_eq(
            color, yml_color, "%s: the created colour must match .github/labels.yml" % name
        )
        gate.assert_eq(
            desc, yml_desc, "%s: the created description must match .github/labels.yml" % name
        )
        checked += 1
    if checked < 2:
        gate.log_fail(
            "only %d create-on-demand row(s) checked; ci and bump-none both need one" % checked
        )
    gate.log_pass("create-on-demand metadata matches the declaration for all %d label(s)" % checked)


def test_ci_is_on_the_inventory_allowlist(gate):
    """Without this entry, `ci` is declared and absent and check:ci-label-inventory fails the repo until the first review creates it."""
    if '"ci|.ci/scripts/review/claude-review-gate.sh"' not in INVENTORY_GATE.read_text(
        encoding="utf-8"
    ):
        gate.log_fail(
            "label_inventory.py has no CREATE_ON_DEMAND entry for 'ci'; the label is "
            "declared and absent, which that gate treats as a failure"
        )
    if not label_declared("ci"):
        gate.log_fail(
            ".github/labels.yml does not declare 'ci', so the allowlist entry above would "
            "itself fail the gate"
        )
    gate.log_pass(
        "'ci' is declared AND allowlisted as create-on-demand (both halves, as that gate requires)"
    )


# --- ledger reconciliation --------------------------------------------------


def test_bump_none_verdict_applies_the_label(gate, tmp_path):
    """THE FEATURE. "none" means no user-facing surface, and the label it applies makes the merge skip the whole release (dispatch-release.sh reads it)."""
    world = make_world(gate, tmp_path)
    world.execution_file(
        report_with_verdict('{"bump": "none", "kind": ["ci"], "why": "CI plumbing only"}')
    )
    world.run_apply()
    gate.assert_exit(0, world, "the arm stays advisory")
    gate.assert_contains(" %s " % world.added(), " bump-none ", "a none verdict applies bump-none")
    gate.assert_not_contains(
        " %s " % world.added(), " bump-minor ", "and nothing else from the bump family"
    )
    gate.assert_contains(
        world.ledger(), "bump-none", "the ledger records it, so the next verdict can remove it"
    )
    gate.log_pass('FIRE: a "none" verdict applies bump-none and records it in the ledger')


def test_a_release_worthy_verdict_removes_a_stale_bump_none(gate, tmp_path):
    """THE OPERATOR'S EXACT CONCERN: a PR that was CI-only earns bump-none, then a later commit adds real product code. The fresh verdict must win, or a stale bump-none silently suppresses that PR's release forever."""
    world = make_world(gate, tmp_path)
    world.comments_fixture(ledger_comment(900, HEAD_SHA, "bump-none,ci"))
    world.execution_file(
        report_with_verdict('{"bump": "patch", "kind": ["feature"], "why": "now touches the CLI"}')
    )
    world.run_apply()
    gate.assert_contains(" %s " % world.removed(), " bump-none ", "the stale bump-none is REMOVED")
    gate.assert_contains(
        " %s " % world.added(), " enhancement ", "and the fresh verdict is applied"
    )
    gate.assert_not_contains(world.ledger(), "bump-none", "the ledger no longer claims it")
    gate.log_pass("FIRE: a release-worthy re-review removes a stale bump-none")


def test_bump_none_survives_a_re_review_that_still_says_none(gate, tmp_path):
    """CONTROL. Removal must be driven by the NEW verdict, not by the mere presence of a ledger entry: a second CI-only round must leave the label rather than churning it."""
    world = make_world(gate, tmp_path)
    world.comments_fixture(ledger_comment(900, HEAD_SHA, "bump-none,ci"))
    world.execution_file(
        report_with_verdict('{"bump": "none", "kind": ["ci"], "why": "still CI only"}')
    )
    world.run_apply()
    gate.assert_not_contains(
        " %s " % world.removed(),
        " bump-none ",
        "an unchanged verdict must not remove its own label",
    )
    gate.assert_contains(" %s " % world.added(), " bump-none ", "it is simply re-applied")
    gate.log_pass("CONTROL: a repeated none verdict leaves bump-none in place")


def test_bump_none_is_created_before_first_use(gate, tmp_path):
    """Same ordering trap as `ci`: the label is brand new, so the applier creates it immediately before applying it rather than demanding a human do it."""
    world = make_world(gate, tmp_path)
    world.live_labels(
        "bug",
        "enhancement",
        "documentation",
        "bump-minor",
        "bump-major",
        "full-ci",
        "rollback",
        "ci",
    )
    world.execution_file(
        report_with_verdict('{"bump": "none", "kind": [], "why": "no user-facing change"}')
    )
    world.run_apply()
    gate.assert_contains(
        " %s " % world.created(), " bump-none ", "the missing label is created before use"
    )
    gate.assert_contains(" %s " % world.added(), " bump-none ", "and then applied")
    gate.log_pass("bump-none is created on demand, then applied")


def test_bump_none_is_on_the_inventory_allowlist(gate):
    if '"bump-none|.ci/scripts/review/claude-review-gate.sh"' not in INVENTORY_GATE.read_text(
        encoding="utf-8"
    ):
        gate.log_fail("label_inventory.py has no CREATE_ON_DEMAND entry for 'bump-none'")
    if not label_declared("bump-none"):
        gate.log_fail(".github/labels.yml does not declare 'bump-none'")
    gate.log_pass("'bump-none' is declared AND allowlisted as create-on-demand")


def test_none_is_in_the_prompt_vocabulary(gate):
    """The applier accepts "none"; if the prompt never offers it, the verdict can never arrive and the whole feature is dead code that still passes its unit tests."""
    if '"none"' not in INITIAL_PROMPT.read_text(encoding="utf-8"):
        gate.log_fail('the initial prompt never offers "none" as a bump value')
    if "none|patch|minor|major" not in FOLLOWUP_PROMPT.read_text(encoding="utf-8"):
        gate.log_fail("the follow-up prompt's bump vocabulary does not include none")
    gate.log_pass(
        'both prompts offer "none", so the verdict the applier accepts can actually be produced'
    )


def test_stale_ledger_label_is_removed(gate, tmp_path):
    world = make_world(gate, tmp_path)
    world.comments_fixture(ledger_comment(900, HEAD_SHA, "bug,bump-minor"))
    world.execution_file(
        report_with_verdict('{"bump": "patch", "kind": ["bug"], "why": "downgraded"}')
    )
    world.run_apply()
    gate.assert_eq(
        world.removed(), "bump-minor", "a label this arm applied and no longer wants is removed"
    )
    gate.assert_eq(world.added(), "bug", "the still-wanted one is re-applied")
    gate.assert_eq(world.ledger(), "bug", "and the ledger is rewritten to the new set")
    gate.assert_contains(
        world.captured(),
        "WRITE PATCH repos/rediacc/console/issues/comments/900",
        "the existing ledger comment is updated, never duplicated",
    )
    gate.log_pass("a superseded verdict removes ONLY the labels the ledger recorded")


def test_hand_applied_labels_are_never_removed(gate, tmp_path):
    """The PR carries full-ci and bump-minor by hand. The ledger only ever recorded `bug`, and the new verdict wants nothing."""
    world = make_world(gate, tmp_path)
    world.comments_fixture(ledger_comment(900, HEAD_SHA, "bug"))
    world.execution_file(report_with_verdict('{"bump": "patch", "kind": [], "why": "nothing"}'))
    world.run_apply()
    gate.assert_eq(world.removed(), "bug", "only the ledger's own label is removed")
    gate.assert_not_contains(
        world.captured(), "labels/full-ci", "a hand-applied kill switch is untouched"
    )
    gate.assert_not_contains(world.captured(), "labels/bump-minor", "and so is a hand-applied bump")
    gate.log_pass(
        "hand-applied labels survive any verdict (removal is ledger-scoped, not a blind sync)"
    )


def test_tampered_ledger_cannot_delete_arbitrary_labels(gate, tmp_path):
    """The ledger is a PR comment, so anyone with write access can edit it. It must not become a delete-anything primitive."""
    world = make_world(gate, tmp_path)
    world.comments_fixture(ledger_comment(900, HEAD_SHA, "rollback,no-cancel-push,bug"))
    world.execution_file(report_with_verdict('{"bump": "patch", "kind": [], "why": "x"}'))
    world.run_apply()
    gate.assert_eq(world.removed(), "bug", "only names inside the managed set are ever deleted")
    gate.assert_not_contains(
        world.captured(),
        "labels/rollback",
        "a release-control label named by a tampered ledger is refused",
    )
    gate.assert_contains(world.out, "refusing to remove", "and the refusal is logged")
    gate.log_pass("PLANTED tampered ledger => only managed labels are removable")


def test_ledger_prefix_is_invisible_to_the_other_counters(gate):
    """Three comment prefixes now live on a PR. If the ledger shared a prefix with the marker it would satisfy last_marker_sha and suppress reviews; if it started with the report header it would consume review budget."""
    source = UNDER_TEST.read_text(encoding="utf-8")

    def scalar(name: str) -> str:
        match = re.search(r"^%s='(.*)'$" % name, source, re.MULTILINE)
        return match.group(1) if match else ""

    ledger = scalar("LEDGER_PREFIX")
    marker = scalar("MARKER_PREFIX")
    attempt = scalar("ATTEMPT_PREFIX")
    gate.assert_eq(
        ledger, LEDGER_PREFIX_EXPECTED, "the ledger prefix is the one this suite asserts on"
    )
    if ledger in (marker, attempt):
        gate.log_fail(
            "the ledger prefix collides with the reviewed-SHA marker or the spent-attempt marker"
        )
    if ledger.startswith("**Claude finished"):
        gate.log_fail("the ledger body would be counted as a posted review report")
    gate.log_pass(
        "the ledger prefix is distinct from the marker, the attempt marker and the report header"
    )


def test_mark_does_not_count_the_ledger_comment_as_output(gate, tmp_path):
    """THE HONESTY GUARD, driven for real. `--mark` refuses to stamp a SHA as reviewed unless the pass actually POSTED something. The ledger comment is written by this pipeline about itself seconds earlier, so counting it would let the pipeline vouch
    for itself: a review that "succeeded" and posted nothing (the 36-permission-denials
    shape that motivated the guard) would be marked reviewed on its own bookkeeping."""
    world = make_world(gate, tmp_path)
    now = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    world.comments_fixture(
        {
            "id": 901,
            "user": {"login": "github-actions[bot]"},
            "created_at": now,
            "body": "<!-- claude-labels: %s -->\napplied: ci" % HEAD_SHA,
        }
    )
    world.run_mark(REVIEW_OUTCOME="success")
    gate.assert_exit(1, world, "a ledger comment alone must NOT satisfy the posted-something guard")
    gate.assert_contains(world.out, "posted NOTHING", "and the refusal says why")

    # CONTROL: a real report comment in the same slot DOES satisfy it, so the assertion above is about the prefix and not about a broken fixture.
    world.comments_fixture(
        {
            "id": 902,
            "user": {"login": "github-actions[bot]"},
            "created_at": now,
            "body": "**Claude finished** the automated review.\nverdict: approve",
        }
    )
    if world.capture.exists():
        world.capture.unlink()
    world.run_mark(REVIEW_OUTCOME="success")
    gate.assert_exit(0, world, "CONTROL: a genuine posted report DOES let the SHA be marked")
    gate.assert_contains(world.captured(), "claude-reviewed:", "and the marker is written")
    gate.log_pass(
        "--mark ignores the label ledger as evidence of output (CONTROL: a real report still counts)"
    )


# --- advisory end to end ----------------------------------------------------


def test_fence_only_in_posted_comment_is_found(gate, tmp_path):
    """The feature's FIRST LIVE RUN (#559, run 31267699743): the model posted its summary itself and put the fence in the COMMENT; its result text back to the harness did not repeat it. The old extraction read only the result text, logged "no json:pr-labels block", and applied nothing beside a PR whose verdict comment plainly carried a verdict."""
    world = make_world(gate, tmp_path)
    world.execution_file(report_with_verdict(""))
    world.comments_fixture(
        {
            "id": 900001,
            "body": "## Verdict: request changes\n\n%s%s\n"
            '{"bump": "patch", "kind": ["bug", "ci"], "why": "live shape"}\n%s'
            % (TICKS, LABELS_FENCE_KEY, TICKS),
        }
    )
    world.run_apply()
    gate.assert_exit(0, world, "advisory always")
    gate.assert_eq(world.added(), "bug ci", "the comment-borne verdict is found and applied")
    gate.log_pass("FIRE: a fence living only in the posted comment is found by the fallback")


def test_result_fence_wins_over_comment_fence(gate, tmp_path):
    """Priority pin: when BOTH carry a fence, the result text stays the primary source. The comment path is a fallback, not a second voter."""
    world = make_world(gate, tmp_path)
    world.execution_file(
        report_with_verdict('{"bump": "patch", "kind": ["ci"], "why": "from the result"}')
    )
    world.comments_fixture(
        {
            "id": 900002,
            "body": '%s%s\n{"bump": "minor", "kind": ["bug"], "why": "from a comment"}\n%s'
            % (TICKS, LABELS_FENCE_KEY, TICKS),
        }
    )
    world.run_apply()
    gate.assert_eq(
        world.added(), "ci", "the result-text verdict wins; the comment fence is not consulted"
    )
    gate.log_pass("FIRE: the result-text fence outranks a comment fence")


def test_total_api_failure_is_advisory(gate, tmp_path):
    world = make_world(gate, tmp_path)
    world.execution_file(report_with_verdict('{"bump": "minor", "kind": ["bug"], "why": "x"}'))
    world.run_apply(GH_FAIL_ALL="1")
    gate.assert_exit(0, world, "no label failure may fail the review job or block a merge")
    gate.assert_contains(
        world.out, "could not", "and every failure is logged rather than swallowed"
    )
    gate.log_pass("every gh call failing => exit 0 with warnings (labels never block a merge)")


# --- contracts with the files this arm cannot reach at runtime --------------


def test_fence_key_is_shared_by_prompt_and_parser(gate):
    initial = INITIAL_PROMPT.read_text(encoding="utf-8")
    if LABELS_FENCE_KEY not in initial:
        gate.log_fail(
            "prompts/initial.md no longer asks for the '%s' block; --apply-labels would find "
            "nothing to parse forever" % LABELS_FENCE_KEY
        )
    if LABELS_FENCE_KEY not in FOLLOWUP_PROMPT.read_text(encoding="utf-8"):
        gate.log_fail(
            "prompts/followup.md no longer asks for the '%s' block; every re-review would "
            "silently drop the verdict" % LABELS_FENCE_KEY
        )
    if LABELS_FENCE_KEY not in UNDER_TEST.read_text(encoding="utf-8"):
        gate.log_fail("claude-review-gate.sh no longer parses '%s'" % LABELS_FENCE_KEY)
    # The closed vocabulary has to be stated to the model, or it will invent words the validator then rejects on every single run.
    for word in ("bug", "feature", "docs", "ci"):
        if word not in initial:
            gate.log_fail(
                "prompts/initial.md no longer names the kind '%s' the parser accepts" % word
            )
    if "RECOMMENDATION" not in initial:
        gate.log_fail(
            "the prompt no longer tells the model that a major verdict is advisory; it will "
            "report one as though it lands"
        )
    gate.log_pass(
        "the json:pr-labels fence and its vocabulary are stated by both prompts and parsed by the gate"
    )


def test_workflow_step_is_guarded_against_the_arm_not_being_on_main(gate):
    """Review scripts execute from console@main, the workflow comes from the PR. An unguarded call to a brand-new arm takes the job red for the whole life of the introducing PR; that exact mistake is documented at the "Record the review invocation" step (run 30552035566)."""
    workflow = REUSABLE_WF.read_text(encoding="utf-8")
    if "--apply-labels" not in workflow:
        gate.log_fail(
            "claude-review-reusable.yml never calls --apply-labels, so nothing applies labels at all"
        )
    if "grep -q -- '--apply-labels'" not in workflow:
        gate.log_fail(
            "the Apply PR labels step lost its grep guard; until the arm is on main it will "
            "fail the review job"
        )
    if "github.repository == 'rediacc/console'" not in workflow:
        gate.log_fail(
            "the Apply PR labels step is not scoped to console; the submodule repos consume no "
            "bump labels and have no inventory gate"
        )
    # The awk: from the step's name to its first `if:` line.
    guard = ""
    found = False
    for line in workflow.splitlines():
        if "name: Apply PR labels" in line:
            found = True
        if found and "if: " in line:
            guard = line
            break
    if "always()" not in guard:
        gate.log_fail(
            "the Apply PR labels step does not run under always(); a starved review would lose "
            "its mechanical labels"
        )
    gate.log_pass("the workflow step is guarded, console-scoped, and runs under always()")
