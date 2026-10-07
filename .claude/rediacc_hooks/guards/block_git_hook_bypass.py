"""Refuse an agent's way around the git-level commit-policy hooks.

WHY (F3 of the commit-policy plan in agent/plans, section 5.3; operator ruling 2, 2026-09-25). The git-level hooks under `.claude/rediacc_hooks/git/` are installed for everyone through `core.hooksPath`, with one operator override, `COMMIT_POLICY_OK=1`. Every one of these skips them, and none of them was refused anywhere before this guard (a grep of the guards found none):

  git commit --no-verify / -n           skips pre-commit and commit-msg
  git push --no-verify                  skips pre-push (NOT `push -n`, a dry run)
  git merge|rebase --no-verify, git am --no-verify / -n
  git -c core.hooksPath=<x> ...         points this one command elsewhere
  git --config-env core.hooksPath=<v>   the same through an environment variable
  git config [--local|...] core.hooksPath <x>, --unset, --unset-all, set, unset
  COMMIT_POLICY_OK=1 <anything>         the operator's override, set by an agent
  GIT_CONFIG_PARAMETERS= / GIT_CONFIG_KEY_<n>= / GIT_CONFIG_COUNT=  config by environment

Reads stay allowed: `git config --get core.hooksPath`, `git config core.hooksPath` with no value, `git log -n 5`, and every ordinary commit.

READ THE WAY GIT READS IT (#9de9a8e9). Whether a verb skips its hooks is `shellscan.git_args`, git's own parse-options over each verb's complete option table: a unique prefix is the option (`--no-veri`), a bundle carries it (`git am -3n`), and the LAST of `--no-verify`/`--verify`/`--no-no-verify` wins. Until 2026-10-07 this read `"--no-verify" in args`, which refused `git push --no-verify --verify` (the hooks run: measured on git 2.53.0) and admitted
`git push --no-veri` and `git am -n` (both skip them). `git cherry-pick` is not judged: it has no `--no-verify` (git exits 129 and runs nothing). An option git calls ambiguous (`--no-ver`) is not refused here either: git refuses it and runs nothing.

WHICH LAYER RULES. This pre-bash layer stays authoritative for agents, because only it can give a rich message before anything runs. The git layer is the backstop for commands that never reach a hook: the operator's own terminal, `!` commands, and subprocesses. The override is the operator's; an agent that sets it is refused here, and the operator's `!` route does not pass through this guard at all.
"""

import re

from rediacc_hooks import commit_policy, hookio, shellscan

CHAIN = "pre-bash"
OWN_SUITE = True
ORDER = 49

# The verdict itself: with it gone, every spelling of `--no-verify` on every verb skips the hooks unrefused.
DEFECT = ('if shellscan.git_args(sub, args).on("no-verify"):', "if False:")

VERIFYING = frozenset(("commit", "push", "merge", "am", "rebase"))

HOOKS_KEY = re.compile(r"^core\.hookspath$", re.IGNORECASE)

# `git config`'s subcommands, which the operands lead with in its new spelling.
CONFIG_SUBCOMMANDS = frozenset(
    ("list", "get", "set", "unset", "rename-section", "remove-section", "edit")
)
CONFIG_READS = (
    "get",
    "get-all",
    "get-regexp",
    "get-urlmatch",
    "list",
    "get-color",
    "get-colorbool",
)
CONFIG_WRITES = ("unset", "unset-all", "replace-all", "add")
CORE_SECTION = re.compile(r"^core$", re.IGNORECASE)

ENV_BYPASS = re.compile(
    r"^(%s|GIT_CONFIG_PARAMETERS|GIT_CONFIG_COUNT|GIT_CONFIG_KEY_[0-9]+)\+?="
    % commit_policy.OVERRIDE_ENV
)

EDGE_CASES = [
    ("commit --no-verify", "git commit --no-verify -m x -- a"),
    ("commit -n", "git commit -n -m x -- a"),
    ("a bundled -n", "git commit -anm x"),
    ("-c core.hooksPath", "git -c core.hooksPath=/dev/null commit -m x -- a"),
    ("config core.hooksPath", "git config core.hooksPath /tmp/x"),
    ("config --unset", "git config --unset core.hooksPath"),
    ("push --no-verify", "git push --no-verify origin 0923-1"),
    ("the override set by an agent", "COMMIT_POLICY_OK=1 git commit -m x -- a"),
    ("config --get is a read", "git config --get core.hooksPath"),
    ("config with no value is a read", "git config core.hooksPath"),
    ("log -n is not a commit", "git log -n 5"),
    ("push -n is a dry run", "git push -n origin 0923-1"),
    ("an ordinary commit", "git commit -F m -- a"),
    ("prose naming the flag", "echo 'never git commit --no-verify'"),
    ("the last of --no-verify and --verify wins", "git push --no-verify --verify origin 0923-1"),
    ("am -n is --no-verify", "git am -3n x.patch"),
    ("a unique prefix is the option", "git rebase --no-veri main"),
    ("cherry-pick has no --no-verify", "git cherry-pick --no-verify HEAD"),
]


def _config_write(args):
    """Whether `git config <args>` writes or removes `core.hooksPath`, or the whole `core` section it lives in.

    Read by `shellscan.git_args("config", ...)`, git's parse-options over the config options (#e8be3092), so a valued option's value (`-f <file>`, `--type <t>`) is never the key and a unique prefix is the action (`--unset-a`, `--repl`). Measured on git 2.53.0: `--unset-a core.hooksPath`, `-f .git/config core.hooksPath x`, `set -f .git/config core.hooksPath x`, `--type path core.hooksPath x` and `unset --file .git/config core.hooksPath` each rewrote or removed the key, and the flag-name matching this replaced read every one as a read.
    """
    parsed = shellscan.git_args("config", args)
    words = parsed.operands
    if words[:1] and words[0] in CONFIG_SUBCOMMANDS:
        sub, rest = words[0], words[1:]
        if sub in ("set", "unset"):
            return bool(rest) and bool(HOOKS_KEY.match(rest[0]))
        if sub in ("rename-section", "remove-section"):
            return bool(rest) and bool(CORE_SECTION.match(rest[0]))
        return False
    if any(parsed.on(f) for f in CONFIG_READS):
        return False
    if parsed.on("rename-section") or parsed.on("remove-section"):
        return bool(words) and bool(CORE_SECTION.match(words[0]))
    if not words or not HOOKS_KEY.match(words[0]):
        return False
    return any(parsed.on(f) for f in CONFIG_WRITES) or len(words) > 1


def _global_hooks_path(globals_):
    for k, arg in enumerate(globals_):
        if arg in ("-c", "--config-env") and k + 1 < len(globals_):
            key = globals_[k + 1].split("=", 1)[0]
            if HOOKS_KEY.match(key):
                return True
        if arg.startswith("--config-env=") and HOOKS_KEY.match(
            arg[len("--config-env=") :].split("=", 1)[0]
        ):
            return True
    return False


def _env_bypass(cmd):
    """An UNQUOTED word setting the override or git's config-by-environment variables, anywhere in the command's own tokens."""
    try:
        toks = shellscan._Lexer(cmd).tokens()
    except Exception:  # noqa: BLE001 -- an unlexable command sets nothing this can see
        return ""
    for tok in toks:
        if not isinstance(tok, shellscan._Word) or not tok.parts:
            continue
        if tok.parts[0].kind != "lit":
            continue
        value = shellscan._word_value(tok)
        match = ENV_BYPASS.match(value)
        if match:
            return value.split("=", 1)[0].rstrip("+")
    return ""


def _refuse(ev, what):
    ev.warn_raw(
        "BLOCKED: %s\n"
        "\n"
        "The git-level commit-policy hooks (core.hooksPath -> .claude/rediacc_hooks/git/)\n"
        "run for everyone, and this skips or disarms them. The override,\n"
        "COMMIT_POLICY_OK=1, is the operator's: it goes on the operator's own `!` command,\n"
        "never on an agent's. When a hook refuses something, fix what it names.\n" % what
    )
    return hookio.DENY


def run(ev):
    cmd = ev.raw("tool_input", "command")
    if cmd in ("", "null"):
        return hookio.ALLOW
    # SCOPE: this policy is about THIS checkout and its submodules. A commit in a repository outside it (a `/tmp` fixture, even one the same command `git init`s) is not its business (finding #5810a9f3).
    if commit_policy.foreign_only(ev, cmd):
        return hookio.ALLOW
    name = _env_bypass(cmd)
    if name:
        return _refuse(ev, "this command sets `%s`." % name)
    for run_ in commit_policy.git_runs(cmd):
        globals_, sub, args = commit_policy.git_split(run_.argv)
        if _global_hooks_path(globals_):
            return _refuse(ev, "`-c core.hooksPath=...` points this git command at other hooks.")
        if sub == "config" and _config_write(args):
            return _refuse(ev, "this rewrites or removes `core.hooksPath`.")
        if sub not in VERIFYING:
            continue
        if shellscan.git_args(sub, args).on("no-verify"):
            short = " (`-n` is the same option)" if sub in ("commit", "am") else ""
            return _refuse(ev, "`git %s --no-verify`%s skips the git-level hooks." % (sub, short))
    return hookio.ALLOW
