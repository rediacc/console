"""Refuse an agent's way around the git-level commit-policy hooks.

WHY (F3 of the commit-policy plan in agent/plans, section 5.3; operator ruling 2, 2026-09-25). The git-level hooks under `.claude/rediacc_hooks/git/` are installed for everyone through `core.hooksPath`, with one operator override, `COMMIT_POLICY_OK=1`. Every one of these skips them, and none of them was refused anywhere before this guard (a grep of the guards found none):

  git commit --no-verify / -n           skips pre-commit and commit-msg
  git push --no-verify                  skips pre-push (NOT `push -n`, a dry run)
  git merge|am|rebase|cherry-pick --no-verify
  git -c core.hooksPath=<x> ...         points this one command elsewhere
  git --config-env core.hooksPath=<v>   the same through an environment variable
  git config [--local|...] core.hooksPath <x>, --unset, --unset-all, set, unset
  COMMIT_POLICY_OK=1 <anything>         the operator's override, set by an agent
  GIT_CONFIG_PARAMETERS= / GIT_CONFIG_KEY_<n>= / GIT_CONFIG_COUNT=  config by environment

Reads stay allowed: `git config --get core.hooksPath`, `git config core.hooksPath` with no value, `git log -n 5`, and every ordinary commit.

WHICH LAYER RULES. This pre-bash layer stays authoritative for agents, because only it can give a rich message before anything runs. The git layer is the backstop for commands that never reach a hook: the operator's own terminal, `!` commands, and subprocesses. The override is the operator's; an agent that sets it is refused here, and the operator's `!` route does not pass through this guard at all.
"""

import re

from rediacc_hooks import commit_policy, hookio

CHAIN = "pre-bash"
OWN_SUITE = True
ORDER = 49

# The `-n` arm: `git commit -n` is the short spelling of `--no-verify`, and the one a bundle (`-anm`) hides.
DEFECT = ('if sub == "commit" and "-n" in flags:', "if False:")

VERIFYING = frozenset(("commit", "push", "merge", "am", "rebase", "cherry-pick"))

HOOKS_KEY = re.compile(r"^core\.hookspath$", re.IGNORECASE)

CONFIG_WRITES = frozenset(
    ("--unset", "--unset-all", "--replace-all", "--add", "--rename-section", "--remove-section")
)
CONFIG_READS = frozenset(("--get", "--get-all", "--get-regexp", "--list", "-l", "--get-urlmatch"))

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
]


def _config_write(args):
    """Whether `git config <args>` writes or removes `core.hooksPath`."""
    words = [a for a in args if not a.startswith("-")]
    flags = [a.split("=", 1)[0] for a in args if a.startswith("-")]
    if words[:1] in (["set"], ["unset"]) and len(words) > 1 and HOOKS_KEY.match(words[1]):
        return True
    if words[:1] in (["get"], ["list"]):
        return False
    if not words or not HOOKS_KEY.match(words[0]):
        return False
    if any(f in CONFIG_READS for f in flags):
        return False
    return any(f in CONFIG_WRITES for f in flags) or len(words) > 1


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
    from rediacc_hooks import shellscan  # noqa: PLC0415 -- shared lexer, as commit_policy uses it

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
        before = args[: args.index("--")] if "--" in args else args
        if "--no-verify" in before:
            return _refuse(ev, "`git %s --no-verify` skips the git-level hooks." % sub)
        flags = commit_policy.commit_flags(run_) if sub == "commit" else []
        if sub == "commit" and "-n" in flags:
            return _refuse(ev, "`git commit -n` is `--no-verify`, and skips the git-level hooks.")
    return hookio.ALLOW
