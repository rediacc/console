r"""Workflow files must not use patterns that violate the CI design principles.

Ported from `.ci/scripts/quality/check-workflows.sh`, which is NOT deleted; see
`rediacc_ci.quality.__init__`.

-----------------------------------------------------------------------------
THE TWIN'S HEADER, CARRIED ACROSS.
-----------------------------------------------------------------------------

Validates that GitHub Actions workflows and actions don't use patterns that
violate CI design principles:
  - continue-on-error: Silently ignores step/job failures
  - script: |          Inline scripts violate multi-CI design (use .ci/scripts/)
  (fail-fast was previously banned but GitHub defaults to true, not false.
   Matrix fail-fast cancellation happens BEFORE the watchdog sees the failure.
   Jobs that need independent matrix entries should set fail-fast: false
   explicitly.)

SECURITY BANS, each with its own reason:

  pull_request_target -- exposes secrets to fork PRs. Use 'pull_request'
  instead. If required, add a fork guard and a '# security: approved' comment.

  secrets: inherit -- explicit passing is safer. Pass required secrets
  explicitly: secrets: { GITHUB_APP_PRIVATE_KEY: ${{ secrets.X }} }.

  allow-unsafe-pr-checkout -- actions/checkout v7 refuses to check out fork-PR
  code under pull_request_target or workflow_run unless this flag is passed
  (enforced 2026-07-20). It is the one input that converts those two triggers --
  which run with the base repository's secrets -- into arbitrary fork code
  execution with those secrets in scope. The ban is here rather than in review
  because it reads as a compatibility shim: a checkout upgrade that "stopped
  working" invites pasting it in.

  secrets in run blocks -- shell injection risk. Secrets must be passed via
  env: blocks, never interpolated directly in run: shell code.
      Safe:   env: { KEY: ${{ secrets.X }} } then run: echo "$KEY"
      Unsafe: run: echo "${{ secrets.X }}" | command

  unpinned third-party actions -- all uses: references must use SHA pinning
  (e.g. @abc123...def  # v3). Local actions (./) are exempt since they're part
  of the repo.

-----------------------------------------------------------------------------
THE FOUR STRUCTURAL RULES AND THE INCIDENTS BEHIND THEM.
-----------------------------------------------------------------------------

THE INLINE-RUN RULE. CI step LOGIC belongs in .ci/scripts/<area>/<name>.sh,
which is locally runnable and shareable across CI systems. A workflow `run:`
block scalar whose shell logic (non-blank, non-comment lines) exceeds
$INLINE_MAX_LOGIC lines is a violation. Full stop -- there is no baseline and no
grandfathering. There used to be a ratchet:
.ci/quality/workflow-inline-baseline.json froze 52 legacy violations per-file
and only allowed the counts to fall. All 52 were extracted, so the file and its
ratchet logic are gone. Do not reintroduce them: an escape hatch that exists
gets used, and the rule only actually held once the hatch was removed.

A block owns every following line that is blank OR indented deeper than the
`run:` key; a logic line is a non-blank line whose first non-space char is not
`#`.

Anti-vacuity: no workflows parsed means the layout moved and this gate is
asserting nothing. Fail loudly rather than report a clean run.

THE `env:` SHELL-SYNTAX RULE. GitHub does NOT expand shell syntax in an `env:`
VALUE -- only `${{ }}` expressions -- and bash does not recursively expand a
variable's value. So

    env:
      SSH_KEY: $RUNNER_TEMP/renet/staging/.ssh/id_rsa

reaches the script as the 24-character literal `$RUNNER_TEMP/renet/...`, and the
failure is a confusing "No such file or directory" naming a path with a dollar
sign in it. Real case: OPS Provision, run 29830623794. This is specifically an
inline-extraction hazard. Inside a `run:` block the shell DOES expand
$RUNNER_TEMP, so moving that same text into `env:` while extracting a script
silently changes its meaning. That is how it got here. Fix: use the GitHub
context (`${{ runner.temp }}`, `${{ github.workspace }}`), or assign on the run
line where the shell can expand it (`run: VAR="$HOME/x" ./script.sh`) for
variables with no context equivalent.

NOTE THE EXPLICIT BOUNDARY CLASS rather than `\b`: in awk regex `\b` is a
BACKSPACE, not a word boundary. The first version of this rule used it and
matched nothing -- permanently vacuous, and green. Caught only by planting a
violation. The class also stops $HOMEBREW_PREFIX reading as $HOME.

Comment lines are prose, not values -- housekeeping.yml:72 documents
`${IN_FLIGHT_VERSION:-}` inside an env: block and must not read as a violation.

ANY shell-style variable, not a list of six. The six-name form
(RUNNER_TEMP|RUNNER_OS|GITHUB_WORKSPACE|GITHUB_SHA|HOME|PWD) let
`SECRET_X: $SOME_VAR` through -- the exact idiom a job-start secret fetch
invites, and one that ships an EMPTY string because GitHub never expands it.
Widened 2026-09-02.

THE `pr-` ENVIRONMENT RULE. A job-level `environment:` makes GitHub create the
environment OBJECT plus a deployment record. ci.yml's deploy-preview job did
that for every PR, and CI cannot undo it: deleting an environment needs
Administration:write, which check-no-app-admin-perm.sh forbids the CI App from
holding. 25 empty `pr-*` shells accumulated on /deployments before they were
deleted by hand. BOTH SYNTACTIC FORMS, because only one of them is the obvious
one:

    environment:            environment: pr-${{ ... }}
      name: pr-${{ ... }}

A `grep 'name: pr-'` would be the vacuous version -- it misses the scalar
shorthand entirely, and the shorthand is exactly what somebody writes when
re-adding this in a hurry. No escape hatch, matching the inline-run rule above
and for its stated reason: a hatch that exists gets used. An environment that
legitimately needs a `pr-` prefix should be renamed.

THE gh `--slurp`/`--jq` RULE. The RUNNER's gh refuses `--slurp` combined with
`--jq` ("the --slurp option is not supported with --jq or --template") while
local gh versions accept it, so the incompatibility is invisible to every local
run and to shell linting (the bash is valid; the tool rejects the flags at
runtime). It killed the first live autopilot dispatch on 2026-08-09 (run
31321043543). Pipe the --slurp output through jq as a separate process instead.
Control-first: the scanner must prove it can fire before its silence means
anything. The scanner's own awk program and control string carry both flags;
scanning this file would be a permanent self-match, not a finding.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

`grep -n "$pattern"` IS BASIC REGULAR EXPRESSION, not extended, in four of the
five `check_pattern` calls, and that is load-bearing for one of them:
`"script:[[:space:]]*|"` relies on `|` being LITERAL in BRE. Read as ERE it
would be the alternation of `script:[[:space:]]*` with the empty string, which
matches every line. The Python translations below are written as explicit
patterns with the `|` escaped, and each one is quoted above its constant so the
BRE-versus-ERE question is answered in the file rather than re-derived.

THE MATCH SPLIT IS `${match%%:*}` AND `${match#*:}`, so the "line number" is
everything before the FIRST colon and the "content" is everything after it. With
`grep -n` over a single file that is exactly right. It is written out here
rather than using a regex, because a regex would silently do something else on a
line whose content contains a colon.

`grep -qE "^\s*#"` USES `\s`, WHICH IS A GNU/ugrep EXTENSION, not POSIX. It is
carried as `[ \t]` plus the leading anchor, which is what it means for these
inputs; the difference (`\s` also matching a form feed) cannot arise in a YAML
line that reached this point.

`require_cmd jq` IS PRESERVED EVEN THOUGH NOTHING PARSES JSON ANY MORE. The
inline-run rule used to read a baseline JSON file; the baseline was deleted with
its ratchet, and the `require_cmd jq` line stayed. Removing it would be a
behaviour change on a machine without jq -- the twin exits 1 there, and so does
this -- so it stays, and this paragraph is the record of why a jq-less gate
still demands jq.

THE AWK BLOCK-SCALAR PARSER IS TRANSLATED, not shelled out. Its two subtleties
are reproduced explicitly: `match(line, /^ */)` counts SPACES only, so a
tab-indented block is measured as indent 0; and a line inside a block that is
blank was already skipped by the `^[[:space:]]*$` rule ABOVE the block handling,
so blanks never terminate a block and never count as logic.

`match($0, /[^ ]/)` IN THE env RULE IS ALSO SPACES-ONLY, and it returns a
1-BASED index, with 0 for a line that is entirely spaces. Both facts are carried
because the comparison is `ind <= envind`, and an off-by-one there silently
changes which lines belong to the mapping.

STREAMS. `log_error` is `✗ <msg>` on stderr; every `Line:` / `Fix:` /
continuation line is a bare `echo` on stdout. That split is the reason
`scripts/lib/shadow-gate.ts` sees one finding per violation rather than three.
"""

import os
import pathlib
import re
import shutil
import sys
import tempfile

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls

# The seams the twin exposes so the standalone gate test can drive the
# inline-run rule against fixtures.
WORKFLOW_DIR_ENV = "WORKFLOW_DIR"
INLINE_MAX_ENV = "INLINE_MAX_LOGIC"
INLINE_ONLY_ENV = "WORKFLOW_INLINE_ONLY"

DEFAULT_WORKFLOW_DIR = ".github/workflows"
DEFAULT_INLINE_MAX_LOGIC = 8

# The two skip conditions every banned-pattern scan applies to a matched line.
COMMENT_RE = re.compile(r"^[ \t]*#")
APPROVED = "# security: approved"

# The five banned patterns, as (pattern, label, fix hint). The regexes are the
# BRE the twin hands to `grep -n`, re-spelled; see the port notes for why the
# `script:` one matters.
BANNED = (
    (
        re.compile(r"continue-on-error"),
        "continue-on-error",
        "Ensure upstream dependencies are correct so steps always succeed",
    ),
    (
        # BRE `script:[[:space:]]*|` -- the `|` is LITERAL there.
        re.compile(r"script:[ \t]*\|"),
        "inline script: |",
        (
            "Move script to .ci/scripts/ and use: script: return await "
            "require('./.ci/scripts/ci/my-script.cjs')({github, context, core})"
        ),
    ),
    (
        re.compile(r"pull_request_target"),
        "pull_request_target trigger",
        (
            "Use 'pull_request' instead. pull_request_target exposes secrets to forks. "
            "If required, add fork guard and '# security: approved' comment"
        ),
    ),
    (
        re.compile(r"secrets:[ \t]*inherit"),
        "secrets: inherit",
        (
            "Pass required secrets explicitly: secrets: { GITHUB_APP_PRIVATE_KEY: "
            "${{ secrets.GITHUB_APP_PRIVATE_KEY }} }"
        ),
    ),
    (
        re.compile(r"allow-unsafe-pr-checkout"),
        "allow-unsafe-pr-checkout",
        (
            "Do not check out fork-PR code in a secret-bearing trigger. Use pull_request, "
            "or check out the BASE ref and treat the fork's code as data. If a reviewed "
            "exception is genuinely needed, add '# security: approved' on the line."
        ),
    ),
)

# `grep -n '\${{.*secrets\.'` -- `\$` is a literal dollar in BRE.
SECRET_INTERP_RE = re.compile(r"\$\{\{.*secrets\.")
# A YAML key-value assignment whose key is NOT `run`. Safe: env:, with:,
# secrets:, private-key:, password: and friends.
YAML_KEY_RE = re.compile(r"^[ \t]+[a-zA-Z][a-zA-Z0-9_-]*:")
RUN_KEY_RE = re.compile(r"^[ \t]+run:")

# `grep -nE '^\s+uses:\s'` -- only YAML `uses:` KEYS, indented, as a key.
USES_RE = re.compile(r"^[ \t]+uses:[ \t]")
LOCAL_ACTION_RE = re.compile(r"uses:[ \t]*\./")
SHA_PIN_RE = re.compile(r"@[a-f0-9]{40}")

# The env-value rules.
ENV_KEY_RE = re.compile(r"^[ \t]*env:[ \t]*$")
SHELL_VAR_RE = re.compile(r"\$\{?[A-Za-z_][A-Za-z0-9_]*")
EXPRESSION_RE = re.compile(r"\$\{\{")

# The `pr-` environment rules, both syntactic forms.
ENV_SCALAR_RE = re.compile(r"^[ \t]*environment:[ \t]*[^\s#]")
ENV_MAPPING_RE = re.compile(r"^[ \t]*environment:[ \t]*$")
PR_NAME_RE = re.compile(r"^[ \t]*name:[ \t]*[\"']?pr-")
PR_SCALAR_RE = re.compile(r"^[\"']?pr-")

# The run: block-scalar shapes.
NAME_KEY_RE = re.compile(r"^[ \t]*(-[ \t]+)?name:[ \t]")
NAME_STRIP_RE = re.compile(r"^[ \t]*(-[ \t]+)?name:[ \t]*")
RUN_BLOCK_RE = re.compile(r"^[ \t]*run:[ \t]*[|>]")

# The gh flag pair, and the line-continuation shape that hides it.
CONTINUATION_RE = re.compile(r"\\[ \t]*$")


def require_cmd(name: str) -> bool:
    """`common.sh`'s `require_cmd`: log and fail when the tool is absent."""
    if shutil.which(name) is None:
        log.error("Required command '%s' is not available" % name)
        return False
    return True


def read_lines(path: pathlib.Path) -> list[str]:
    """A file's lines with no trailing empty element, or [] when unreadable."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def github_yamls(root: pathlib.Path) -> list[str]:
    """`find .github/workflows .github/actions -name "*.yml" -type f`.

    Root-relative, in walk order. The twin never sorts, and the comparison is a
    multiset, so the order is recorded here rather than imposed.
    """
    out: list[str] = []
    for rel in (".github/workflows", ".github/actions"):
        base = root / rel
        if not base.is_dir():
            continue
        for dirpath, _dirnames, filenames in os.walk(base):
            for name in filenames:
                candidate = pathlib.Path(dirpath) / name
                if name.endswith(".yml") and candidate.is_file():
                    out.append(str(candidate.relative_to(root)))
    return out


class Errors:
    """The `ERRORS` counter. One object so the count cannot drift from the text."""

    def __init__(self) -> None:
        self.count = 0

    def report(self, headline: str, detail_lines: list[str]) -> None:
        """A `log_error` headline on STDERR, then bare `echo` detail on STDOUT."""
        log.error(headline)
        for line in detail_lines:
            print(line)
        self.count += 1


def skip_line(content: str) -> bool:
    """Comment, or carrying the reviewed-exception marker."""
    return bool(COMMENT_RE.search(content)) or APPROVED in content


def check_pattern(
    errors: Errors,
    root: pathlib.Path,
    files: list[str],
    pattern: re.Pattern[str],
    label: str,
    fix_hint: str,
) -> None:
    """One banned pattern across every collected YAML."""
    for rel in files:
        for number, line in enumerate(read_lines(root / rel), start=1):
            if not pattern.search(line):
                continue
            if skip_line(line):
                continue
            errors.report(
                "%s:%d: %s is banned" % (rel, number, label),
                ["  Line: %s" % line, "  Fix:  %s" % fix_hint, ""],
            )


def check_secrets_in_run(errors: Errors, root: pathlib.Path, files: list[str]) -> None:
    """A secret interpolated into shell code rather than passed through env:."""
    for rel in files:
        for number, line in enumerate(read_lines(root / rel), start=1):
            if not SECRET_INTERP_RE.search(line):
                continue
            if skip_line(line):
                continue
            # Safe: a YAML key-value assignment whose key is not `run`.
            if YAML_KEY_RE.search(line) and not RUN_KEY_RE.search(line):
                continue
            errors.report(
                "%s:%d: secret used directly in shell code" % (rel, number),
                [
                    "  Line: %s" % line,
                    "  Fix:  Move secret to env: block and reference as $VAR_NAME in run:",
                    "",
                ],
            )


def check_unpinned_actions(errors: Errors, root: pathlib.Path, files: list[str]) -> None:
    """Every third-party `uses:` must name a 40-hex SHA."""
    for rel in files:
        for number, line in enumerate(read_lines(root / rel), start=1):
            if not USES_RE.search(line):
                continue
            if COMMENT_RE.search(line):
                continue
            if LOCAL_ACTION_RE.search(line):
                continue
            if APPROVED in line:
                continue
            if SHA_PIN_RE.search(line):
                continue
            errors.report(
                "%s:%d: unpinned action reference" % (rel, number),
                [
                    "  Line: %s" % line,
                    (
                        "  Fix:  Pin action to SHA commit hash "
                        "(e.g. uses: actions/checkout@abc123...def  # v4)"
                    ),
                    "",
                ],
            )


class Block:
    """One `run:` block scalar: where it starts, how much logic, whose step."""

    __slots__ = ("count", "start", "step")

    def __init__(self, start: int, count: int, step: str) -> None:
        self.start = start
        self.count = count
        self.step = step


def parse_run_blocks(lines: list[str]) -> list[Block]:
    """The block-scalar parser, translated from the awk program.

    A block owns every following line that is blank OR indented deeper than the
    `run:` key; a logic line is a non-blank line whose first non-space char is
    not `#`. `match(line, /^ */)` counts SPACES only, so a tab-indented block is
    measured as indent 0; see the port notes.
    """
    out: list[Block] = []
    in_block = False
    key_indent = 0
    count = 0
    start = 0
    step_name = ""
    block_step = ""

    def record() -> None:
        nonlocal in_block
        if in_block:
            out.append(Block(start, count, block_step))
            in_block = False

    for number, raw in enumerate(lines, start=1):
        line = raw.removesuffix("\r")
        if re.match(r"^[ \t]*$", line):
            continue
        cur = len(line) - len(line.lstrip(" "))
        if in_block:
            if cur > key_indent:
                rest = line[cur:]
                if not rest.startswith("#"):
                    count += 1
                continue
            record()
        if NAME_KEY_RE.match(line):
            step_name = NAME_STRIP_RE.sub("", line).rstrip(" \t")
        if RUN_BLOCK_RE.match(line):
            key_indent = cur
            in_block = True
            count = 0
            start = number
            block_step = step_name
    record()
    return out


def check_inline_run_blocks(
    errors: Errors, root: pathlib.Path, workflow_dir: str, max_logic: int
) -> None:
    """Workflow `run:` blocks must stay thin (env wiring plus one call)."""
    # `require_cmd jq` is preserved even though nothing parses JSON any more;
    # see the port notes.
    if not require_cmd("jq"):
        raise SystemExit(1)
    if not require_cmd("awk"):
        raise SystemExit(1)

    log.step("Checking workflow run: blocks stay thin (<= %d logic lines)..." % max_logic)

    actual: dict[str, int] = {}
    detail: dict[str, str] = {}
    base = root / workflow_dir
    if base.is_dir():
        for path in sorted(base.glob("*.yml")):
            name = path.name
            violations = 0
            lines_out = ""
            for block in parse_run_blocks(read_lines(path)):
                if block.count > max_logic:
                    violations += 1
                    lines_out += "      - %s:%d (step: %s) has %d logic lines\n" % (
                        name,
                        block.start,
                        block.step or "<unnamed>",
                        block.count,
                    )
            actual[name] = violations
            if lines_out:
                detail[name] = lines_out

    # Anti-vacuity: no workflows parsed means the layout moved and this gate is
    # asserting nothing. Fail loudly rather than report a clean run.
    if not actual:
        log.error("No workflows found under %s -- this check is blind" % workflow_dir)
        errors.count += 1
        return

    for name in sorted(actual):
        if actual[name] <= 0:
            continue
        body = []
        if name in detail:
            body.append(detail[name].rstrip("\n"))
        body.append(
            "  Fix:  extract each over-threshold block to .ci/scripts/<area>/<name>.sh; "
            "the workflow step becomes env wiring + one script call, and the script "
            "header documents its required env + how to run it locally."
        )
        body.append("")
        errors.report(
            "%s/%s: %d inline run: block(s) exceed %d logic lines"
            % (workflow_dir, name, actual[name], max_logic),
            body,
        )


def env_shell_hits(lines: list[str]) -> list[tuple[int, str]]:
    """`env:` values that reference a shell variable GitHub will not expand.

    `match($0, /[^ ]/)` counts SPACES only and is 1-BASED, returning 0 for a
    line that is entirely spaces. Both facts matter: the comparison is
    `ind <= envind`.
    """
    out: list[tuple[int, str]] = []
    in_env = False
    env_indent = 0
    for number, line in enumerate(lines, start=1):
        if ENV_KEY_RE.match(line):
            in_env = True
            env_indent = _first_non_space(line)
            continue
        if not in_env:
            continue
        ind = _first_non_space(line)
        if re.match(r"^[ \t]*$", line):
            continue
        if ind <= env_indent:
            in_env = False
        elif COMMENT_RE.match(line):
            continue
        elif SHELL_VAR_RE.search(line) and not EXPRESSION_RE.search(line):
            out.append((number, line))
    return out


def _first_non_space(line: str) -> int:
    """awk's `match($0, /[^ ]/)`: 1-based, SPACES only, 0 when all spaces."""
    for index, char in enumerate(line, start=1):
        if char != " ":
            return index
    return 0


def check_env_shell_vars(errors: Errors, root: pathlib.Path, workflow_dir: str) -> None:
    """An `env:` value may not carry shell syntax GitHub will not expand."""
    if not require_cmd("awk"):
        raise SystemExit(1)
    base = root / workflow_dir
    if not base.is_dir():
        return
    for path in sorted(base.glob("*.yml")):
        hits = env_shell_hits(read_lines(path))
        if not hits:
            continue
        # ONE `ERRORS` INCREMENT PER FILE, not per hit: the twin loops the hits
        # inside a single `if [[ -n "$out" ]]` block and increments once after
        # it. Every hit gets its own `log_error`, so the finding SET is per hit
        # and the COUNT is per file. That asymmetry is the twin's.
        for number, line in hits:
            log.error(
                "%s/%s:%d: env: value uses shell syntax GitHub will not expand"
                % (workflow_dir, path.name, number)
            )
            print("      %s" % line)
        print(
            "  Fix:  use a GitHub context (${{ runner.temp }}, ${{ github.workspace }}), "
            'or assign it on the run line so the shell expands it: run: VAR="$HOME/x" '
            "./script.sh"
        )
        print()
        errors.count += 1


def pr_environment_hits(lines: list[str], file_label: str) -> list[str]:
    """Both syntactic forms of a `pr-`-prefixed deployment environment."""
    out: list[str] = []
    in_env = False
    env_indent = 0
    for number, line in enumerate(lines, start=1):
        if ENV_SCALAR_RE.match(line):
            value = re.sub(r"^[ \t]*environment:[ \t]*", "", line)
            if PR_SCALAR_RE.match(value):
                out.append("%s:%d: %s" % (file_label, number, line))
            in_env = False
            continue
        if ENV_MAPPING_RE.match(line):
            env_indent = len(re.match(r"^[ \t]*", line).group(0))
            in_env = True
            continue
        if in_env:
            indent = len(re.match(r"^[ \t]*", line).group(0))
            if re.match(r"^[ \t]*$", line):
                continue
            if indent <= env_indent:
                in_env = False
                continue
            if PR_NAME_RE.match(line):
                out.append("%s:%d: %s" % (file_label, number, line))
    return out


def check_pr_environment_names(errors: Errors, root: pathlib.Path, workflow_dir: str) -> None:
    """No job may declare a `pr-`-prefixed environment."""
    if not require_cmd("awk"):
        raise SystemExit(1)
    base = root / workflow_dir
    if not base.is_dir():
        return
    for path in sorted(base.glob("*.yml")):
        hits = pr_environment_hits(read_lines(path), path.name)
        if not hits:
            continue
        errors.report(
            "job declares a pr-prefixed deployment environment in %s" % path.name,
            [
                *["    %s" % hit for hit in hits],
                "    GitHub creates the environment OBJECT for this, and no CI token can",
                "    delete it again (Administration:write is forbidden by",
                "    check-no-app-admin-perm.sh). Drop the environment: block; the preview",
                "    URL belongs in $GITHUB_STEP_SUMMARY.",
                "",
            ],
        )


def slurp_jq_offenders(text: str) -> list[int]:
    """Start line of each gh invocation carrying BOTH `--slurp` and `--jq`.

    Line continuations are joined first, which is how the real regression was
    written. Comments do not count and they RESET the join.
    """
    out: list[int] = []
    joined = ""
    start = 0
    for number, line in enumerate(text.split("\n"), start=1):
        if COMMENT_RE.match(line):
            joined = ""
            continue
        if joined != "":
            joined = joined + " " + line
        else:
            joined = line
            start = number
        if CONTINUATION_RE.search(line):
            continue
        if "--slurp" in joined and "--jq" in joined:
            out.append(start)
        joined = ""
    return out


def check_gh_slurp_jq(errors: Errors, root: pathlib.Path, files: list[str]) -> None:
    """The RUNNER's gh rejects `--slurp` with `--jq`. Control-first."""
    scan_files = list(files)
    ci_scripts = root / ".ci" / "scripts"
    if ci_scripts.is_dir():
        for dirpath, _dirnames, filenames in os.walk(ci_scripts):
            for name in filenames:
                candidate = pathlib.Path(dirpath) / name
                if name.endswith(".sh") and candidate.is_file():
                    scan_files.append(str(candidate.relative_to(root)))

    control = slurp_jq_offenders('gh api repos/x/issues --paginate --slurp \\\n    --jq ".[]"\n')
    if not control:
        log.error(
            "gh --slurp/--jq control did not fire on a planted two-line offender; the "
            "scanner is broken, refusing to certify anything"
        )
        errors.count += 1
        return

    for rel in scan_files:
        # The scanner's own awk program and control string carry both flags;
        # scanning this file would be a permanent self-match, not a finding.
        if rel.endswith("/check-workflows.sh"):
            continue
        path = root / rel
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for number in slurp_jq_offenders(text):
            errors.report(
                "%s:%d: gh invocation combines --slurp with --jq; the RUNNER's gh rejects "
                "this at runtime (proven live, run 31321043543)" % (rel, number),
                [
                    (
                        "  Fix:  drop --jq from the gh call and pipe the --slurp output "
                        "through jq separately"
                    ),
                    "",
                ],
            )


def main(argv: list[str] | None = None) -> int:
    """Run every rule. 0 clean, 1 problem."""
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    log.step("Checking workflows for banned patterns...")

    errors = Errors()
    files = github_yamls(root)

    workflow_dir = os.environ.get(WORKFLOW_DIR_ENV) or DEFAULT_WORKFLOW_DIR
    raw_max = os.environ.get(INLINE_MAX_ENV) or ""
    max_logic = int(raw_max) if raw_max.isdigit() else DEFAULT_INLINE_MAX_LOGIC

    # When the gate test exercises ONLY the inline-run rule, empty the file list
    # the banned-pattern scans iterate so they become no-ops. This keeps the rule
    # living in this one gate while letting the test point WORKFLOW_DIR at a
    # fixture tree without also tripping (or depending on) the real .github
    # banned-pattern state.
    if os.environ.get(INLINE_ONLY_ENV, "0") == "1":
        files = []

    for pattern, label, fix_hint in BANNED:
        check_pattern(errors, root, files, pattern, label, fix_hint)
    check_secrets_in_run(errors, root, files)
    check_unpinned_actions(errors, root, files)
    check_inline_run_blocks(errors, root, workflow_dir, max_logic)
    check_env_shell_vars(errors, root, workflow_dir)
    check_pr_environment_names(errors, root, workflow_dir)
    check_gh_slurp_jq(errors, root, files)

    if errors.count > 0:
        print()
        log.error("Found %d problem(s) in workflows" % errors.count)
        return 1
    log.info("All workflows are clean")
    return 0


def selftest() -> int:
    """Both directions on every rule, driven through the pure matchers."""
    ctl = Controls("workflows", floor=46, verbose=True)

    # -- the five banned patterns -------------------------------------------
    cont_re, script_re, pr_target_re, inherit_re, unsafe_re = (b[0] for b in BANNED)
    ctl.truthy(
        "PLANT: continue-on-error is banned", bool(cont_re.search("    continue-on-error: true"))
    )
    ctl.truthy(
        "PLANT: an inline `script: |` is banned", bool(script_re.search("        script: |"))
    )
    ctl.falsy(
        "MIRROR: `script:` with a one-line value is not the block form, so the LITERAL "
        "pipe in the BRE is what makes this rule usable",
        bool(script_re.search("        script: return await require('./x.cjs')()")),
    )
    ctl.truthy(
        "PLANT: pull_request_target is banned", bool(pr_target_re.search("  pull_request_target:"))
    )
    ctl.truthy(
        "PLANT: `secrets: inherit` is banned", bool(inherit_re.search("    secrets: inherit"))
    )
    ctl.truthy(
        "PLANT: allow-unsafe-pr-checkout is banned",
        bool(unsafe_re.search("      allow-unsafe-pr-checkout: true")),
    )

    # -- the two skip conditions, which apply to every scan -----------------
    ctl.truthy(
        "CONTROL: a commented violation is skipped", skip_line("  # continue-on-error: true")
    )
    ctl.truthy(
        "CONTROL: a reviewed exception is skipped", skip_line("  x: y  # security: approved")
    )
    ctl.falsy("MIRROR: an ordinary line is not skipped", skip_line("  continue-on-error: true"))

    # -- the secret-in-run rule ---------------------------------------------
    unsafe = '        run: echo "${{ secrets.TOKEN }}" | base64'
    safe = "          TOKEN: ${{ secrets.TOKEN }}"
    ctl.truthy(
        "PLANT: a secret interpolated into a run: line matches",
        bool(SECRET_INTERP_RE.search(unsafe)),
    )
    ctl.truthy("CONTROL: it is NOT a plain key-value assignment", bool(RUN_KEY_RE.search(unsafe)))
    ctl.truthy(
        "MIRROR: a secret passed through env: IS a key-value assignment",
        bool(YAML_KEY_RE.search(safe)),
    )
    ctl.falsy("MIRROR: and that assignment's key is not `run`", bool(RUN_KEY_RE.search(safe)))

    # -- the unpinned-action rule -------------------------------------------
    ctl.truthy(
        "CONTROL: an indented `uses:` key is a subject",
        bool(USES_RE.search("        uses: actions/checkout@v4")),
    )
    # A BLIND SPOT IN THE TWIN, PINNED HERE RATHER THAN WIDENED. `^\s+uses:\s`
    # requires `uses:` to follow leading WHITESPACE, so the YAML list form
    # `      - uses: actions/checkout@v4` -- a step with no `name:` -- is not a
    # subject at all and its pin is never checked. The form that IS checked is
    # the continuation `        uses:` under a `- name:`, which is what this
    # repo's workflows happen to use. Widening the pattern would be a verdict
    # change on any tree that carries the other spelling, so the control asserts
    # the CURRENT answer and names it as the defect it is.
    ctl.falsy(
        "INHERITED DEFECT: the `- uses:` list form is NOT a subject (the anchor "
        "demands whitespace immediately before `uses:`)",
        bool(USES_RE.search("      - uses: actions/checkout@v4")),
    )
    ctl.falsy(
        "MIRROR: the WORD uses inside prose is not",
        bool(USES_RE.search("# this workflow uses: nothing")),
    )
    ctl.truthy(
        "MIRROR: a local action is exempt",
        bool(LOCAL_ACTION_RE.search("      - uses: ./.github/actions/x")),
    )
    ctl.truthy(
        "MIRROR: a 40-hex pin satisfies the rule",
        bool(SHA_PIN_RE.search("uses: actions/checkout@" + "a" * 40)),
    )
    ctl.falsy(
        "PLANT: a tag-only reference does not", bool(SHA_PIN_RE.search("uses: actions/checkout@v4"))
    )

    # -- the block-scalar parser --------------------------------------------
    thin = [
        "    steps:",
        "      - name: Thin step",
        "        run: |",
        "          ./script.sh",
        "      - name: next",
    ]
    blocks = parse_run_blocks(thin)
    ctl.check("CONTROL: one run: block is found", len(blocks), 1)
    ctl.check("CONTROL: its logic-line count is right", blocks[0].count, 1)
    ctl.check("CONTROL: and it is attributed to its step name", blocks[0].step, "Thin step")

    commented = ["      - name: X", "        run: |", "          # a comment", "          echo hi"]
    ctl.check(
        "CONTROL: a comment inside a block is not logic", parse_run_blocks(commented)[0].count, 1
    )

    blanked = ["      - name: X", "        run: |", "          echo a", "", "          echo b"]
    ctl.check(
        "CONTROL: a blank line neither counts nor ends the block",
        parse_run_blocks(blanked)[0].count,
        2,
    )

    dedented = [
        "      - name: X",
        "        run: |",
        "          echo a",
        "      - name: Y",
        "        run: echo b",
    ]
    ctl.check("CONTROL: a dedent ends the block", parse_run_blocks(dedented)[0].count, 1)
    ctl.check(
        "MIRROR: `run:` with no block scalar is not a block",
        len(parse_run_blocks(["        run: echo hi"])),
        0,
    )
    ctl.check(
        "VACUITY: a file with no run: block yields none",
        len(parse_run_blocks(["jobs:", "  x:"])),
        0,
    )
    ctl.check(
        "CONTROL: an unnamed block carries an empty step name, which the caller renders "
        "as <unnamed>",
        parse_run_blocks(["        run: |", "          echo a"])[0].step,
        "",
    )

    # -- the env-value rule --------------------------------------------------
    ctl.check(
        "PLANT: `SSH_KEY: $RUNNER_TEMP/...` is caught (run 29830623794)",
        len(env_shell_hits(["    env:", "      SSH_KEY: $RUNNER_TEMP/renet/.ssh/id_rsa"])),
        1,
    )
    ctl.check(
        "PLANT: ANY shell variable, not a list of six (widened 2026-09-02)",
        len(env_shell_hits(["    env:", "      SECRET_X: $SOME_VAR"])),
        1,
    )
    ctl.check(
        "MIRROR: a ${{ }} expression is the CORRECT form and is not flagged",
        len(env_shell_hits(["    env:", "      T: ${{ runner.temp }}"])),
        0,
    )
    ctl.check(
        "MIRROR: a COMMENT inside an env: block is prose (housekeeping.yml:72)",
        len(env_shell_hits(["    env:", "      # documents ${IN_FLIGHT_VERSION:-}"])),
        0,
    )
    ctl.check(
        "MIRROR: a line dedented out of the env: mapping is not an env value",
        len(env_shell_hits(["    env:", "      A: 1", "    run: echo $HOME"])),
        0,
    )
    ctl.check(
        "VACUITY: a file with no env: block yields nothing",
        len(env_shell_hits(["    run: echo $HOME"])),
        0,
    )

    # -- the pr- environment rule -------------------------------------------
    ctl.check(
        "PLANT: the MAPPING form is caught",
        len(
            pr_environment_hits(
                ["    environment:", "      name: pr-${{ github.event.number }}"], "f"
            )
        ),
        1,
    )
    ctl.check(
        "PLANT: the SCALAR SHORTHAND is caught too, which a `grep 'name: pr-'` would miss",
        len(pr_environment_hits(["    environment: pr-${{ github.event.number }}"], "f")),
        1,
    )
    ctl.check(
        "MIRROR: a non-pr environment is fine",
        len(pr_environment_hits(["    environment:", "      name: production"], "f")),
        0,
    )
    ctl.check(
        "MIRROR: a `name:` outside an environment: mapping is a step name",
        len(pr_environment_hits(["      - name: pr-something"], "f")),
        0,
    )

    # -- the gh --slurp/--jq rule -------------------------------------------
    ctl.check(
        "CONTROL: the two-line continuation offender is found (run 31321043543)",
        slurp_jq_offenders('gh api x --paginate --slurp \\\n    --jq ".[]"\n'),
        [1],
    )
    ctl.check(
        "CONTROL: a one-line offender is found",
        slurp_jq_offenders('gh api x --slurp --jq ".[]"\n'),
        [1],
    )
    ctl.check("MIRROR: --slurp alone is fine", slurp_jq_offenders("gh api x --slurp\n"), [])
    ctl.check("MIRROR: --jq alone is fine", slurp_jq_offenders('gh api x --jq ".[]"\n'), [])
    ctl.check(
        "MIRROR: a COMMENT naming both flags is prose",
        slurp_jq_offenders("# never combine --slurp with --jq\n"),
        [],
    )

    # -- the whole gate, over a fixture tree --------------------------------
    def run(root: pathlib.Path) -> int:
        saved = os.environ.get(paths.ROOT_ENV)
        os.environ[paths.ROOT_ENV] = str(root)
        try:
            return main([])
        finally:
            if saved is None:
                del os.environ[paths.ROOT_ENV]
            else:
                os.environ[paths.ROOT_ENV] = saved

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        wf = root / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "ci.yml").write_text(
            "jobs:\n  q:\n    steps:\n      - uses: actions/checkout@%s\n"
            "      - name: Thin\n        run: |\n          ./x.sh\n" % ("a" * 40),
            encoding="utf-8",
        )
        ctl.check("CONTROL: a clean workflow tree passes", run(root), 0)
        (wf / "bad.yml").write_text("jobs:\n  q:\n    continue-on-error: true\n", encoding="utf-8")
        ctl.check("PLANT: one banned pattern reds the gate", run(root), 1)

    with tempfile.TemporaryDirectory() as tmp:
        # THE ANTI-VACUITY CASE. A tree with no workflows at all must be a
        # FAILURE: the layout moved and the gate is asserting nothing.
        ctl.check(
            "VACUITY: no workflows under the scan dir is a FAILURE, never a clean run",
            run(pathlib.Path(tmp)),
            1,
        )

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
