"""Route a gate at the devbox when the host cannot run it but the container can.

WHY. Measured 2026-08-27, over several hours: `check:ci-python-lint` reported "ruff is not available and neither is uvx" and `check:ci-renet` reported `command not found`, and this session recorded BOTH as environmental gaps and moved on -- twice teaching a gate to say "cannot run here" and once nearly marking a third that way when the real cause was an empty node_modules.

The devbox was running the entire time and carries ruff 0.16.1, the pinned shfmt 3.13.1, shellcheck and Go. Nothing was missing. The gates were being run in the wrong place, and every "environmental" verdict written on that basis was wrong.

It cost more than tidiness. `check:ci-renet` inside the container does not fail to start -- it RUNS, and reports `govulncheck` exit 3 with six stdlib vulnerabilities. Attributed afterwards by running govulncheck in throwaway containers at three toolchains: those six belong to go1.26.4, the version this image happened to ship. go1.26.6 and go1.25.13 (which is what CI installs, via
go-version-file on private/renet/go.mod) both report none of them. So the finding was about the IMAGE and not the shipped code, and CI was never red on it -- but it was invisible from the host either way, behind a message that read like a local inconvenience.

WHAT THIS DOES NOT DO. It does not route every `npm run`. Most gates are node and TypeScript and run identically on the host, where they are faster and their output lands directly in the transcript. It fires only when the command names a gate whose toolchain THIS host lacks and the container has -- that is the whole condition, and it is checked against the host, not assumed.

=============================================================================
PORT NOTES
=============================================================================

TWO BASH ASSOCIATIVE ARRAYS ARE ITERATED, AND THEIR ORDER IS A HASH ORDER.
`for key in "${!NEEDS[@]}"` does not visit the keys in the order they were
written, nor in sorted order: it visits them in the order bash's hash table yields, and the FIRST match wins because both loops `break`. That is observable, because `check:ci-renet` is a substring of `check:ci-renet-tiers` so a command naming the longer key matches both, and `$HIT` reaches the message and the suggested `npm run` line.

Measured on bash 5.3.9 on this host, and hard-coded below in exactly that order rather than sorted:

    NEEDS      check:ci-python-lint, check:ci-renet, check:ci-renet-tiers
    NEEDS_ENV  sync-media-from-r2, sync-media-to-r2, --publish-www

A different bash could hash differently. That is a property of the ORIGINAL, not of this port, and the differential is what would report it: the two sides would disagree on `$HIT` for a command naming two keys, on the machine where the hash order differs. Recorded here so such a report is read as what it is.

`command -v` DOES NOT MEAN "EXECUTABLE", and this guard's own comment says so. Measured on bash 5.3.9: with a mode-0600 file on PATH, `command -v faketool` prints its path and exits 0, while `test -x` on that path exits 1. The port therefore resolves the path the way `command -v` does -- first PATH entry holding a file of that name, executability NOT consulted -- and then applies
`os.access(..., X_OK)` separately. Collapsing the two into one `which()` would be a different test that agrees on a healthy host and disagrees on the half-installed one this line exists for.

`for tok in $SCAN` IS UNQUOTED, so bash both word-splits it on IFS and then PATHNAME-EXPANDS each word against the current directory. With no `nullglob`, a word that matches nothing stays literal. Both halves are reproduced, because a token carrying a `*` is not exotic in a command line and dropping the expansion would make the host-bound walk look at a different set of paths.
"""

import glob as globmod
import os
import pathlib
import re
import sys

from rediacc_hooks import hookio, shellscan

CHAIN = "pre-bash"
TWIN = "pre-bash/block-host-toolchain-run.sh"
ORDER = 35

# The host-bound arm, added 2026-08-28. Without it a command reaching into a component with its own `.venv` is routed into the container, where the venv's absolute shebangs and host glibc do not exist: the measured symptom was `ModuleNotFoundError: No module named anyio`.
DEFECT = ("if hostbound:", "if False:")

# NPX CANNOT RESOLVE A NON-NPM BINARY. Measured 2026-08-28: `npx --yes ruff format ...` failed with "npm error could not determine executable to run", and the session reading that failure concluded "no ruff binary resolves in this shell" and hand-patched two files instead of running the tool. The real ruff (0.16.1, the pinned version) was on PATH the entire time. npx resolves its
# argument as an NPM PACKAGE NAME; none of this repo's pinned non-JS toolchain binaries are npm packages, so npx can never run them, whether or not they are actually installed. This fires on the shape alone, independent of host tool state, because the diagnosis is "wrong verb", not "missing tool".
NPX_TOOLS = ("ruff", "go", "shfmt", "shellcheck", "actionlint")

# gate key -> the host binary it needs. Extend this table when a gate acquires a new toolchain dependency; the entry is what makes the refusal specific enough to act on, and a gate absent from it is never routed.
#
# AN ENTRY BELONGS HERE ONLY IF THE GATE FAILS WITHOUT THE BINARY ON PATH. Three of the original six did not, and each produced a confident, specific refusal of a gate that works: check:ci-shell-lint shellcheck.sh calls toolchain_acquire check:ci-shell-format shfmt.sh calls toolchain_acquire check:ci-actionlint downloads a pinned, checksum-verified release toolchain_acquire
# fetching the PIN is the entire point of that helper -- its own comment says a bare `command -v` accepts any version and "a stale binary on a developer's PATH silently decided this gate's verdict". Measured 2026-08-27 with neither tool on PATH: shfmt.sh acquired v3.13.1 and reported "Shell script formatting passed", exit 0. Check for toolchain_acquire in the gate's script before
# adding an entry. NO check:ci-actionlint ENTRY, DELIBERATELY. That gate provisions its own tool: .ci/scripts/security/actionlint.sh uses actionlint from PATH if it is there and otherwise downloads a pinned, checksum-verified release, refusing any version with no recorded checksum. Verified 2026-08-27 with no actionlint on this host: "actionlint clean across 29 workflow file(s)".
# Listing it here sent a working gate into the fix-the-image branch, which is confident and specific advice to do work that buys nothing. Only add a gate here if it genuinely fails without the binary on PATH.
NEEDS = (
    ("check:ci-python-lint", "ruff"),
    ("check:ci-renet", "go"),
    ("check:ci-renet-tiers", "go"),
    # `.ci/rediacc_ci/quality/release_state.py:115-123` shells out to the `aws` CLI and `require_cmd`s it up front, so the gate FAILS without the binary rather than provisioning its own pin. That is the entry test the paragraph above states, and it is the one this table's original six got wrong three times.
    ("check:ci-release-state", "aws"),
)

# SCRIPTS THAT NAME NO GATE KEY AND NO BARE TOOL. Added 2026-09-23.
#
# A session ran `.ci/scripts/release/assert-edge-tag-exists.sh` on the HOST, read `Required command 'aws' is not available`, and began evaluating an `awscli` install on the host. The devbox has carried aws-cli 2.36.40 the whole time (`.devcontainer/Dockerfile:467-490`). Neither table above could see the command: it names no gate key, and the tool it needs appears nowhere in the
# command line -- the script reaches `aws` from inside itself. So the SCRIPT is what has to be matched.
#
# Twelve of these `require_cmd aws` (a hard refusal without the binary) and two -- `upload-to-r2.sh`, `r2-oneshot-scrub.sh` -- call `aws` directly under `set -euo pipefail` with no guard at all, which fails the same way with a worse message. Counted 2026-09-23, not estimated.
#
# `.ci/breakpoint/scripts/publish-endpoints.sh:96` is DELIBERATELY ABSENT, on the same precedent as `check:ci-actionlint` above: it degrades to skipping a notification rather than failing, so routing it would send a working path into the fix-the-image branch for nothing.
#
# MATCHED WITH `_is_invoked`, NEVER A SUBSTRING TEST. Every key here is a path a session has a real reason to grep, sed or cat, and `NEEDS`'s older `grep_q(..., fixed=True)` is exactly the "reading a script is mistaken for running it" bug `_is_invoked` was written to end for `NEEDS_ENV`.
NEEDS_SCRIPT = (
    ("assert-edge-tag-exists.sh", "aws"),
    ("write-release-sentinel.sh", "aws"),
    ("delete-r2-channel.sh", "aws"),
    ("promote-r2-to-stable.sh", "aws"),
    ("promote-r2-to-stable-hotfix.sh", "aws"),
    ("simulate-promotion.sh", "aws"),
    ("upload-repos-to-r2.sh", "aws"),
    ("cleanup-versions.sh", "aws"),
    ("upload-r2.sh", "aws"),
    ("scrub-sentinel.sh", "aws"),
    ("sync-media-to-r2.sh", "aws"),
    ("sync-media-from-r2.sh", "aws"),
    ("upload-to-r2.sh", "aws"),
    ("r2-oneshot-scrub.sh", "aws"),
)

# CREDENTIALS THAT LIVE IN A FILE, NOT IN YOUR SHELL. Measured 2026-08-28.
#
# `main.py --publish-www` copied 52 files locally, uploaded ZERO, exited 0, and printed "R2_MEDIA_* env vars not set". Every one of those words was load-bearing and the run still read as a publish: the site had new files in packages/www, and nothing reached media.rediacc.com.
#
# The credentials are not meant to be in the shell. They live in private/account/.env, a SUBMODULE file, alongside 48 other keys. A command that needs them and does not source it does not fail; it half-succeeds, which is worse. So require the sourcing to be VISIBLE in the command.
#
# Extend the table when another command grows a credential dependency. Match on something specific to that command, never on a bare tool name.
NEEDS_ENV = (
    ("sync-media-from-r2", "CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID"),
    ("sync-media-to-r2", "CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID"),
    ("--publish-www", "CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID"),
)

# BARE INVOCATIONS. The table above matches only a GATE KEY (`check:ci-python-lint` in the command), so a session running the tool directly -- `ruff format <files>`, not `npm run check:ci-python-lint` -- was invisible to it. That gap is real independent of the npx incident above: this catches the correctly-shaped direct command too, when the host genuinely lacks the tool.
#
# `aws`, `bw` and `bws` joined on 2026-09-23. All three are baked into `.devcontainer/Dockerfile` (aws at 467-490, bw at 509-553 pinned to 2026.9.0, bws at 555-587 pinned to 2.1.0), so a bare host that lacks one has somewhere to route to. Nothing in the tree invokes `bw`, and only `.ci/rediacc_ci/setup/tools.py:566-584` registers `bws`, so neither earns a NEEDS_SCRIPT row -- but a
# session typing either by hand on a host without it gets the same wrong lesson, which is what this array is for.
#
# NPX_TOOLS IS DELIBERATELY UNCHANGED. No `npx aws` or `npx bw` misuse has been measured here, and this file's discipline is measured incidents rather than symmetry.
BARE_TOOLS = ("ruff", "go", "shfmt", "shellcheck", "actionlint", "aws", "bw", "bws")

DEVBOX_LABEL = "label=com.rediacc.devbox.worktree"

# The BLOCKER-gated exception list, and the one reason it will not accept.
#
# THE ILLEGITIMATE CATEGORY IS THE WHOLE POINT. "the devbox does not have it" is not an exception, it is a bug report against `.devcontainer/Dockerfile`, and an exception list that accepts it converts every image gap into a permanent host fallback -- which is the outcome the block message spends fourteen lines arguing against. `rediacc_ci.core.allowlist`'s LOW_EFFORT_PHRASES cannot
# know that: "the devbox image has no aws" is specific, over the thirty-character floor, and passes every generic rule. So the phrase family is refused here, where the domain is.
EXCEPTIONS_FILE = ".host-toolchain-exceptions"

# TIER ONE: the exact phrases, including the four the plan named. Kept as literals because they are the wording a session actually reaches for, and a literal is the thing a reader can grep for when a refusal surprises them.
DEVBOX_GAP_PHRASES = (
    "exist on devbox",
    "exist on the devbox",
    "exist in devbox",
    "exist in the devbox",
    "absent from devbox",
    "absent from the devbox",
    "devbox lacks",
    "devcontainer lacks",
    "not installed in devbox",
    "not installed in the devbox",
    "not installed on devbox",
    "not installed on the devbox",
)

# TIER TWO, AND IT IS THE ONE THAT WORKS. The first cut of this refusal was tier one alone, and the very first reason written to test it -- "the devbox image does not have aws installed so the host is the only place this runs" -- was GRANTED: it says the banned thing in words no literal list had. A phrase list loses to paraphrase every time, and losing here is silent.
#
# So the rule is a CONJUNCTION over the whole reason: a devbox-ish subject, an absence verb, and a tool-ish object (including the binary actually being refused). All three, or nothing. That is deliberately coarse, and the asymmetry is why: a false refusal costs one rewording, and a false grant is a permanent host fallback wearing a BLOCKER comment.
#
# THE OBJECT TERM IS WHAT KEEPS THE LEGITIMATE CATEGORY IN. "the devbox has no TTY, and this unlock needs one" carries a subject and an absence and is exactly the host-only ceremony this list exists for; it is not about a tool, so it passes.
DEVBOX_GAP_SUBJECTS = ("devbox", "devcontainer", "container image", "docker image", "the image")

DEVBOX_GAP_ABSENCE = (
    "does not have",
    "doesn't have",
    "does not carry",
    "doesn't carry",
    "does not ship",
    "doesn't ship",
    "does not include",
    "doesn't include",
    "does not exist",
    "doesn't exist",
    "not installed",
    "missing",
    "absent",
    "lacks",
    # THE `<VERB> NO <THING>` FAMILY, added after "the container image ships no aws binary at all" was GRANTED by the first draft of this table. "has no" alone was there; the same sentence written with any other verb walked straight past it, which is the paraphrase failure tier two exists for happening one level down inside tier two.
    "has no",
    "have no",
    "ships no",
    "carries no",
    "contains no",
    "includes no",
    "provides no",
    "holds no",
    "with no",
    "never had",
    "not available",
    "not present",
    "no such",
    "without",
)

DEVBOX_GAP_OBJECTS = ("tool", "toolchain", "binary", "cli", "command", "package", "install")

# The three docker worlds this guard's tail distinguishes, driven rather than described. Without them the differential only ever sees whichever devbox this machine happens to be running, and the two NOTE branches plus the refusal are a coin toss decided by another session's `devbox up`.
ENVS = [
    ("no-devbox", {}, {"docker": "#!/bin/sh\nexit 0\n"}),
    (
        "devbox-without-tool",
        {},
        {"docker": '#!/bin/sh\ncase "$1" in ps) echo rediacc-devbox-x ;; exec) exit 1 ;; esac\n'},
    ),
    (
        "devbox-with-tool",
        {},
        {"docker": '#!/bin/sh\ncase "$1" in ps) echo rediacc-devbox-x ;; exec) exit 0 ;; esac\n'},
    ),
]

EDGE_CASES = [
    # Already routed through the devbox, or driving the devbox itself.
    ("already routed", "./run.sh devbox exec -- npm run check:ci-python-lint"),
    ("a docker exec", "docker exec -u vscode box bash -lc 'ruff check .'"),
    # The npx arm fires on SHAPE, whatever the host has.
    ("npx ruff", "npx ruff format packages/cli"),
    ("npx --yes shfmt", "npx --yes shfmt -w run.sh"),
    ("npx on an npm package is not this guard's business", "npx tsx scripts/gen/gen-docs.ts"),
    # The bare-tool arm.
    ("a bare shfmt", "shfmt -w run.sh"),
    ("a bare shellcheck", "shellcheck .ci/scripts/quality/check-python-lint.sh"),
    ("a bare actionlint", "actionlint"),
    ("a bare tool after a separator", "cd packages/cli && shfmt -d ."),
    ("a tool named in prose", "echo 'run shfmt -w on it'"),
    # The gate-key arm, including the substring pair whose hash order decides $HIT.
    ("a gate key", "npm run check:ci-renet"),
    ("the longer gate key matches both", "npm run check:ci-renet-tiers"),
    # The host-bound arm.
    ("a host-bound pipeline", "shfmt -w private/growth/video_pipeline/run.sh"),
    ("a host-bound submodule", "shellcheck private/account/scripts/rotation/rotate.sh"),
]


def _command_v(tool):
    """`command -v <tool>` on bash 5.3.9: the first PATH entry holding that file.

    Executability is deliberately NOT consulted here; see the module docstring
    for the measurement. The caller applies `test -x` to the result.
    """
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        if not directory:
            continue
        candidate = os.path.join(directory, tool)
        if os.path.exists(candidate):
            return candidate
    return ""


def _have_executable(tool):
    """`test -x "$(command -v "$tool" 2>/dev/null)" 2>/dev/null`."""
    path = _command_v(tool)
    return path != "" and os.access(path, os.X_OK)


def _split_glob(text):
    """`for tok in $SCAN` -- IFS word splitting, then pathname expansion.

    With no `nullglob`, a pattern that matches nothing stays literal, which is what `glob` returning an empty list has to be turned back into here.
    """
    out = []
    for word in text.split():
        if any(c in word for c in "*?["):
            matches = sorted(globmod.glob(word))
            out.extend(matches or [word])
        else:
            out.append(word)
    return out


def _npx_pattern(tool):
    return (
        hookio.rx(r"(^|[;&|(]|\$\(|`)[{S}]*npx([{S}]+(-y|--yes))?[{S}]+")
        + tool
        + hookio.rx(r"([{S}]|$)")
    )


def _bare_pattern(tool):
    return hookio.rx(r"(^|[;&|(]|\$\(|`)[{S}]*") + tool + hookio.rx(r"([{S}]|$)")


def _is_invoked(key, scan):
    """Is `key` being RUN here, or merely NAMED?

    A plain `grep_q(key, scan, fixed=True)` was the rule, and it blocked reading the
    script as well as running it. Measured 2026-09-09: `grep -n assets/videos .ci/scripts/deploy/sync-media-to-r2.sh` was refused with a message about credentials that a grep does not need, and `sed -n 1,5p <same path>` likewise. Only `echo '<path>'` escaped, and for the wrong reason -- `scan_target` strips QUOTED spans, so the guard was anchored on quoting rather than on
    invocation.

    The rule is command position: the token holding the key opens the command, follows a separator, or is the argument of an interpreter (`bash`, `sh`, `zsh`, `source`, `.`). Anything else -- a path handed to grep, sed, cat, head, wc, an editor -- is a mention. `npm run <script>` and `./path/to/it` both still read as invocations.

    DELIBERATELY NOT A READER BLOCKLIST. Enumerating grep/sed/cat/head/less/awk means the next reader command is a fresh false positive, and false positives are what teach a session to route around a guard: this one cost a writer a workaround before it cost me a command.
    """
    interp = r"(bash|sh|zsh|source|\.|npm[{S}]+run|npx)"
    # ONE `rx()` OVER THE WHOLE PATTERN. The first cut put the middle class outside it,
    # so `{S}` stayed literal and `[^{S};&|]` read as "not {, S, }, ; & or |" -- which
    # matches a SPACE, letting the pattern skip the whole command and find the key anywhere. Every mention case still blocked and the failure looked like the anchor not working rather than the class being wrong.
    pat = hookio.rx(r"(^|[;&|(]|\$\(|`|" + interp + r"[{S}]+)[{S}]*[^{S};&|]*" + re.escape(key))
    return hookio.grep_q(pat, scan)


def _ci_seams():
    """`.ci`'s allowlist parser and policy-path seam, with `sys.path` restored.

    THE CODE COMES FROM THIS CHECKOUT, NOT FROM THE ROOT `_exception` IS GIVEN, and the two are the same directory in production. They part only under test, where a fixture root supplies the policy FILE while the parser is still the real one -- which is the split that keeps the fixture honest: a harness that also supplied the parser would be testing its own copy of the grammar.

    THE INSERT IS SCOPED AND REMOVED, the same shape as `block_prose_style_edit._engine` and for the same reason: the dispatcher runs every guard in one process, and a permanent `.ci` entry would put `rediacc_ci` and `_cipath` on every later guard's import path, where a name collision surfaces as some other guard misbehaving with nothing pointing back here.

    IMPORTED RATHER THAN REIMPLEMENTED. The BLOCKER grammar has had four hand-rolled copies in this tree and `rediacc_ci.core.allowlist` exists to end that; a fifth living in a hook would be the same mistake one directory further out.
    """
    cipath = str(hookio.repo_root() / ".ci")
    inserted = cipath not in sys.path
    if inserted:
        sys.path.insert(0, cipath)
    try:
        from rediacc_ci.core import allowlist  # noqa: PLC0415 - deliberately late
        from rediacc_ci.policy_paths import policy_path  # noqa: PLC0415 - deliberately late
    finally:
        if inserted and cipath in sys.path:
            sys.path.remove(cipath)
    return allowlist, policy_path


def _is_devbox_gap(reason, need):
    """Is this reason the one category that may never be an exception?

    Two tiers, and the second is the load-bearing one; the tables above carry the measurement that made it necessary.
    """
    lowered = reason.lower()
    if any(phrase in lowered for phrase in DEVBOX_GAP_PHRASES):
        return True
    objects = (*DEVBOX_GAP_OBJECTS, need.lower())
    return (
        any(word in lowered for word in DEVBOX_GAP_SUBJECTS)
        and any(word in lowered for word in DEVBOX_GAP_ABSENCE)
        and any(word in lowered for word in objects)
    )


def _exception(root, hit, need):
    """`(granted, refused)` for one `<hit>@<need>` pair, from the policy file.

    `granted` is the BLOCKER text of a valid entry and means the command is allowed through with a note. `refused` is why a PRESENT entry was ignored, which must be said out loud: an exception someone wrote and believes is in force, silently doing nothing, is worse than no exception at all.

    AN UNREADABLE LIST GRANTS NOTHING. Both shared readers treat a missing file as zero entries and so does this, deliberately -- but a missing file here fails CLOSED (the command is still refused and routed), which is the direction that cannot hide. `parse_file(missing_ok=True)` is spelled out for exactly the reason its own docstring gives: the claim should be visible at the call
    site.
    """
    try:
        allowlist, policy_path = _ci_seams()
        path = policy_path(EXCEPTIONS_FILE, root)
        entries = allowlist.parse_file(path, missing_ok=True)
    except (ImportError, OSError, ValueError):
        return "", ""

    want = "%s@%s" % (hit, need)
    for entry in entries:
        if entry.entry != want:
            continue
        failures = allowlist.verify([entry], str(path))
        if failures:
            return "", failures[0].split("\n")[0]
        if _is_devbox_gap(entry.blocker, need):
            return "", (
                "%s line %d excuses '%s' on the grounds that the devbox does not carry"
                " '%s'. That is not an exception, it is a bug report against"
                " .devcontainer/Dockerfile: pin '%s' there and rebuild the IMAGE"
                % (EXCEPTIONS_FILE, entry.line, want, need, need)
            )
        return entry.blocker, ""
    return "", ""


def run(ev):
    cmd = ev.raw("tool_input", "command")
    if cmd == "":
        return hookio.ALLOW

    scan = shellscan._command_substitution(shellscan.scan_target(cmd))

    # Repo root from BASH_SOURCE, not CLAUDE_PROJECT_DIR, which is unreliable inside hooks.
    repo_root = str(hookio.repo_root())

    # Already routed through the devbox, or driving the devbox itself: out of scope.
    if hookio.grep_q(hookio.rx(r"devbox|docker[{S}]+exec"), cmd):
        return hookio.ALLOW

    for tool in NPX_TOOLS:
        if not hookio.grep_q(_npx_pattern(tool), scan):
            continue
        ev.warn_raw(
            "BLOCKED: npx cannot run '%s'. npx resolves its argument as an NPM PACKAGE NAME, and\n"
            "'%s' is one of this repo's pinned non-JS toolchain binaries, never an npm package --\n"
            "so this fails whether or not '%s' is actually on PATH, with an error ('npm error\n"
            "could not determine executable to run') that reads like a missing tool and is not one.\n"
            "\n"
            "Run it directly instead:\n"
            "\n"
            "    %s ...\n"
            "\n"
            "If '%s' is genuinely missing from PATH, that is what the direct form (and the rest\n"
            "of this guard) will tell you. Try that and read ITS answer, not npx's.\n"
            % (tool, tool, tool, tool, tool)
        )
        return hookio.DENY

    account_env = "%s/private/account/.env" % repo_root
    if pathlib.Path(account_env).is_file():
        for key, var in NEEDS_ENV:
            if not _is_invoked(key, scan):
                continue
            # Already sourcing the file, or setting the credential inline: fine.
            if hookio.grep_q("private/account/.env", cmd, fixed=True):
                continue
            if hookio.grep_q(var, cmd, fixed=True):
                continue
            # Only complain if the file actually carries the credential.
            try:
                env_text = pathlib.Path(account_env).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if not hookio.grep_q_line("^%s=" % var, env_text):
                continue
            ev.warn_raw(
                "BLOCKED: '%s' uploads to R2, and its credentials are NOT in your shell."
                " They live\n"
                "in private/account/.env, which this command does not source.\n"
                "\n"
                "Without them the run does NOT fail. It copies files locally, uploads nothing,"
                " exits 0,\n"
                "and warns about the wrong thing. That happened on 2026-08-28: 52 files copied, 0\n"
                "uploaded, and the closing line blamed unset env vars that were about to be set.\n"
                "\n"
                "Load the file in the same command:\n"
                "\n"
                "    source scripts/lib/env-file.sh;"
                " env_file_load private/account/.env\n"
                "    <your command>\n"
                "\n"
                "Not `set -a; . private/account/.env; set +a`: that EXECUTES the file (it"
                " holds\n"
                "ACCOUNT_ED25519_PRIVATE_KEY and ACCOUNT_JWT_SECRET, and a $(...) in a value"
                " would\n"
                "run) and lets the file overwrite anything you set on the command line.\n"
                "\n"
                "If you are deliberately doing a local-only copy, say so by setting the variable\n"
                "yourself (%s=) so the intent is in the command rather than in your memory.\n"
                % (key, var)
            )
            return hookio.DENY

    hit = ""
    need = ""
    bare = False
    for key, tool in NEEDS:
        if not hookio.grep_q(key, scan, fixed=True):
            continue
        # THE HOST IS ASKED, NOT ASSUMED. A developer who has installed ruff should not be pushed into a container for it; the point is to stop a MISSING tool being recorded as a property of the repo. `command -v` resolves a name on PATH and says NOTHING about whether it can be executed: on bash 5.3.9 it returns 0 for a mode-0600 file. A half-installed ruff/go/shfmt would therefore
        # read as "the host is fine" and this guard would decline to route the gate, which is the exact outcome it exists to prevent wearing the face of a guard that simply did not fire. `test -x` asks the real question.
        # Verified 2026-08-27: command -v rc=0 and test -x rc=1 on the same file.
        if _have_executable(tool):
            continue
        hit = key
        need = tool
        break

    if hit == "":
        for tool in BARE_TOOLS:
            if not hookio.grep_q(_bare_pattern(tool), scan):
                continue
            if _have_executable(tool):
                continue
            hit = tool
            need = tool
            bare = True
            break
    if hit == "":
        # `bare = True` HERE TOO, and it is not a detail. The label branch below turns a non-bare hit into "npm run <hit>", and `npm run assert-edge-tag-exists.sh` is not a command that exists -- the same reading error that made the bare-tool arm need its own label in the first place. What the reader needs is "this command needs 'aws'", followed by the command they typed.
        for key, tool in NEEDS_SCRIPT:
            if not _is_invoked(key, scan):
                continue
            if _have_executable(tool):
                continue
            hit = key
            need = tool
            bare = True
            break
    if hit == "":
        return hookio.ALLOW

    # THE EXCEPTION LIST, and it is empty on purpose. There is exactly ONE category it exists for: a host-only interactive auth ceremony a headless container cannot complete. The category it refuses -- a tool the devbox does not carry -- is checked in `_exception` rather than left to the reader, because that reason reads as perfectly good prose and is the one that must never work.
    granted, refused = _exception(repo_root, hit, need)
    if granted:
        ev.warn_raw(
            "NOTE: %s needs '%s', which this host lacks, and %s carries an exception for\n"
            "it:\n"
            "\n"
            "  %s\n"
            "\n"
            "Proceeding on that basis. If the reason above is no longer true, delete the entry\n"
            "rather than leaving it to decide this silently.\n"
            % (hit, need, EXCEPTIONS_FILE, granted)
        )
        return hookio.ALLOW
    if refused:
        ev.warn_raw("NOTE: an exception entry was found and IGNORED -- %s.\n" % refused)

    # HOST-BOUND WORK MUST NOT BE ROUTED. Measured 2026-08-28.
    #
    # Routing into the devbox is only correct when the command can actually RUN there. Two whole families cannot, and both live in this repo:
    #
    # * the eight Python pipelines under private/growth (and private/generative) each carry their own `.venv`, built against the HOST interpreter. A venv is not portable into a container: absolute shebangs, host glibc. Routing `video_pipeline/run.sh` into the devbox produced `ModuleNotFoundError: No module named anyio` -- the container has aws and none of the pipeline's
    # dependencies. * node_modules is deliberately NOT shared between host and container
    #     (different glibc; CLAUDE.md, REDIACC_NPM_RUNTIME). private/account
    # carries a host-built one.
    #
    # So before routing, ask whether the command reaches into a directory that owns a host-built toolchain. If it does, the container is the WRONG destination and saying so is more useful than a block the reader has to argue with. This is the submodule / non-submodule split: a root-repo gate is portable, a submodule or pipeline with its own venv is not.
    hostbound = ""
    for tok in _split_glob(scan):
        if tok.startswith("-"):
            continue
        cand = tok.removeprefix("./")
        # Start at the token ITSELF when it names a directory. Starting at its parent skipped the very case this guard is for: `--prefix private/growth/video_pipeline` walked from private/growth and never saw the venv one level down.
        if pathlib.Path("%s/%s" % (repo_root, cand)).is_dir():
            directory = "%s/%s" % (repo_root, cand)
        else:
            # `${cand%/*}` leaves the word UNCHANGED when it holds no slash.
            directory = "%s/%s" % (repo_root, cand.rsplit("/", 1)[0] if "/" in cand else cand)
        # Walk up from the referenced path looking for a host-built toolchain.
        while directory not in (repo_root, "/") and directory != "":
            if (
                pathlib.Path("%s/.venv" % directory).is_dir()
                or pathlib.Path("%s/node_modules" % directory).is_dir()
            ):
                hostbound = directory[len(repo_root) + 1 :]
                break
            directory = directory.rsplit("/", 1)[0] if "/" in directory else ""
        if hostbound != "":
            break

    # LABEL and ROUTE differ for a gate-key hit ("check:ci-python-lint needs 'ruff'", routed as "npm run check:ci-python-lint") versus a bare-tool hit ("go needs 'go'" read wrong, and "npm run go" is not a command that exists). BARE is set above by whichever of the two loops matched.
    if bare:
        label = "this command"
        route = "./run.sh devbox exec -- %s" % cmd
    else:
        label = "gate '%s'" % hit
        route = "./run.sh devbox exec -- npm run %s" % hit

    if hostbound:
        ev.warn_raw(
            "NOTE: %s needs '%s', which this host lacks -- but this command reaches into\n"
            "'%s', which owns a HOST-BUILT toolchain (.venv or node_modules). The devbox\n"
            "cannot run it: a venv carries absolute shebangs and host glibc, and node_modules is\n"
            "deliberately not shared across the boundary.\n"
            "\n"
            "Routing this would trade a missing tool for a missing interpreter. Install '%s' on\n"
            "the host instead, or into that component's own venv, which is usually one command:\n"
            "\n"
            "    %s/.venv/bin/pip install <the package providing %s>\n"
            "\n"
            "Proceeding, because the container is not the answer here.\n"
            % (label, need, hostbound, need, hostbound, need)
        )
        return hookio.ALLOW

    # The container must actually be able to help, or this is a wall rather than a route. If it is not running, or lacks the tool too, say so and let the command proceed -- the gate's own refusal is then the honest answer.
    cid_out = hookio.run_out(["docker", "ps", "--filter", DEVBOX_LABEL, "--format", "{{.Names}}"])
    # `| head -1`: the first record, or "" when there is none.
    records, _ = hookio._records(hookio._printf_line(cid_out) if cid_out else "")
    cid = records[0] if records else ""
    if cid == "":
        ev.warn_raw(
            "NOTE: this gate needs a toolchain this host does not have. The devbox would have\n"
            "it, but no devbox is running for this worktree.\n"
            "\n"
            "There is ONE container per worktree, so a fresh branch or worktree has none yet\n"
            "and `devbox up` alone will not conjure one:\n"
            "\n"
            "    ./run.sh setup        # a worktree that has never been prepared: builds the\n"
            "                          # image if needed, then creates this worktree's container\n"
            "    ./run.sh devbox up    # the worktree is already prepared, container stopped\n"
            "\n"
            "Then re-run the gate through it. Proceeding for now, so the gate's own refusal\n"
            "is what you see rather than this note standing in for a verdict.\n"
        )
        return hookio.ALLOW

    if (
        hookio.run_rc(
            ["docker", "exec", "-u", "vscode", cid, "bash", "-lc", "command -v %s" % need]
        )
        != 0
    ):
        ev.warn_raw(
            "NOTE: %s needs '%s'. Neither this host nor the devbox (%s) has it, so it\n"
            "genuinely cannot run anywhere right now -- that is a real finding about the\n"
            "IMAGE, not about your change.\n"
            "\n"
            'Fix the image rather than recording another "environmental" red:\n'
            "  1. add '%s' to .devcontainer/Dockerfile with an explicit version, the way\n"
            "     the other tools there are pinned (an unpinned tool that decides a CI\n"
            "     verdict is a different verdict on every rebuild)\n"
            '  2. REBUILD THE IMAGE, not just the container. "devbox remove" removes the\n'
            "     CONTAINER; devbox_ensure_image then short-circuits on the image it\n"
            "     already has (.ci/lib/devbox.sh:367), and if you delete the image it\n"
            "     PULLS from the registry first -- so a local Dockerfile edit reaches the\n"
            "     box by neither route. Measured 2026-08-27: GO_VERSION was bumped to\n"
            "     1.26.6 and the container still reported go1.26.4. What actually works:\n"
            "         docker build -t ghcr.io/rediacc/devcontainer:latest -f"
            " .devcontainer/Dockerfile .devcontainer\n"
            "         ./run.sh devbox remove && ./run.sh devbox up\n"
            "  3. re-run the gate and say in your summary that you changed the image\n"
            "\n"
            "Proceeding, so the gate's own message is what you see.\n" % (label, need, cid, need)
        )
        return hookio.ALLOW

    ev.warn_raw(
        "BLOCKED: %s needs '%s', which is missing on this host and PRESENT in the devbox.\n"
        "\n"
        "Run it there instead:\n"
        "\n"
        "  %s\n"
        "\n"
        "WHY THIS IS REFUSED RATHER THAN WARNED. A gate that cannot run does not report a\n"
        "verdict about your code, and this session recorded exactly that as an\n"
        '"environmental gap" three times in one afternoon while the container sat running\n'
        "with the right tool. Once it was worse than tidiness: check:ci-renet on the host\n"
        "said 'command not found', and in the devbox it RUNS and reports six stdlib\n"
        "vulnerabilities in the image's own go1.26.4. Not a defect in the shipped code --\n"
        "CI installs a different toolchain and sees none of them -- but a real finding\n"
        "about the image that the host could not see at all.\n"
        "\n"
        "IF THE DEVBOX IS ALSO WRONG, FIX THE IMAGE -- that is in scope and is the point\n"
        "of this guard. .devcontainer/Dockerfile is where the toolchain is declared, and\n"
        "'%s' should be pinned there with an explicit version, because a tool that\n"
        "decides a CI verdict must be the same one CI uses. Rebuild the IMAGE, not the\n"
        'container: "devbox remove" leaves the image untouched and devbox_ensure_image\n'
        "reuses or re-pulls it, so a Dockerfile edit reaches the box by neither route.\n"
        "    docker build -t ghcr.io/rediacc/devcontainer:latest -f"
        " .devcontainer/Dockerfile .devcontainer\n"
        "    ./run.sh devbox remove && ./run.sh devbox up\n"
        "and say in your summary that you changed the image, since that is a change the\n"
        "operator did not ask for.\n"
        "\n"
        "If you genuinely mean to run it on the host and read its refusal, say so and use\n"
        "the devbox form to get a real answer instead.\n" % (label, need, route, need)
    )
    return hookio.DENY
