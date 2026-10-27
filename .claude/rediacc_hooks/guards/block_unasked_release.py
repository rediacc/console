"""Refuse a release from agent Bash unless the operator asked for it, and refuse the raw publish verbs a release is made of.

WHY. agent/plans/PLAN-local-release.md (operator ruling ASKED:2026-10-27T06:37Z) moves the release from CD to one local entry, `npm run release:local -- --channel edge|stable [--dry-run]` (`rediacc_ci.release.local`, box W2-B). A release reaches every user, so this guard, box W2-C, holds two lines:

  1. THE ENTRY RUNS ONLY WHEN ASKED. `npm run release:local` (or `python3 -m rediacc_ci.release.local`) without `--dry-run` is admitted only when the command carries `RELEASE_ASKED=ASKED:<YYYY-MM-DDTHH:MM>Z` and that minute matches an AskUserQuestion answer in the payload's transcript within 300 s. The proof is `wl_checks._asked_in_transcript`, imported, the same check `block_vm_unverified_push` and `block_backup_unverified_push` use. `--dry-run` always passes: it reads no secret value and writes nothing.
  2. THE RAW PUBLISH VERBS DO NOT RUN FROM AGENT BASH, so the entry cannot be routed around one step at a time: `wrangler deploy|rollback|publish|versions deploy`, `gh release create|upload|edit|delete`, a `git push` of a `v*` tag (`refs/tags/v*`, `--tags`, `--mirror`), `docker push` (and `image push`, `manifest push`), a `docker build`/`buildx build` with `--push` or a registry output, `docker buildx imagetools create`, and `-m` on the publish modules in DEPLOY_MODULES and RELEASE_MODULES. The refusal points at `npm run release:local`.

A SHELL-WRITE TWIN rides the same module: an agent write under `.ci/cache/release/` (a redirect, `tee`, `sed -i`, a copy or move onto it, `rm`, `mkdir`, `touch`, `chmod`, a mutating `git` inside the release clone, an interpreter program writing there) is refused. Decision 1 of the plan judges cleanliness on a fresh clone of HEAD at `.ci/cache/release/<tree>/`; a clone a session can edit by hand proves nothing. Only the entry and its gates module write there. The Edit and Write tools are NOT judged here: that half is a pre-edit guard this module cannot be (one module, one chain).

EXEMPTIONS, each by name, each printed when it admits so the debt stays visible. They exist because flows the operator has authorized still need a path until W3 replaces them with `release:local --workers-only`:

  * `deploy_proxy --target bench`: the bench proxy stays manual (deploy skill section 4a) and builds renet with the dev licence key; it is not a release target. Every other `--target` is refused.
  * `deploy_account --region eu`: the operator ruled on 2026-09-26 that an eu account deploy needs no question while there are no active users (memory feedback_eu_deploy_no_ask).
  * `deploy_account` for another region, `deploy_www`, `deploy_edge`: the deploy skill's local path (section 4), which its section 0 already requires the operator to ask for in the task. Admitted only with the same proven `RELEASE_ASKED` minute, until W3-D moves the skill to `release:local --workers-only`.
  * NOT IN THE LISTS, so never refused here: `rediacc_ci.ops.deploy_bench` (bench deploys keep working) and `rediacc_ci.deploy.account_secrets_local` (the skill's per-region secrets push).

A `--help`/`-h` on a publish module passes, and so does `--dry-run` on one whose own source declares `--dry-run` (a module that does not would reject the flag or, read with `parse_known_args`, ignore it and publish; the source is what says which).

WRAPPERS ARE UNWRAPPED. `./run.sh devbox exec -- ...`, `bws_env exec ... -- ...` and `docker exec <container> ...` hand their tail to another process, so the tail is judged as a command of its own with the outer environment carried in. `npm run <script>` is judged by the script's own text from the package.json of the directory it runs in (`--prefix`, a path `-w`, or `cd`), because `workers/mta-sts`'s `npm run deploy` is a `wrangler deploy` that names no publish verb on the command line.

WHAT IT DOES NOT SEE: a publish verb assembled at run time, `gh api` POSTs to the releases endpoint, a path into `.ci/cache/release/` spelled through a glob or a symlink the word does not resolve through, and a program that builds the path from parts. The release record and the R2 sentinel are what a release leaves behind, so a release this guard missed is still visible after the fact.

ORDER 64, appended. `block_vm_unverified_push` (62) and `block_backup_unverified_push` (63) each write a ledger line once they admit an escaped push, on the claim that every other guard ran first; with this guard behind them a command that escapes a push AND runs a refused publish verb leaves a ledger line for a push that never ran. Moving this guard ahead of them shifts both of their ORDER lines, which this box does not own.

THIS GUARD HAS NO BASH TWIN (`OWN_SUITE = True`); it is judged by `test-block_unasked_release.py` beside it, which also plants DEFECT and every MUTANT.
"""

import json
import os
import re
import shlex

from rediacc_hooks import commit_policy, hookio, plan_gate, shellscan, syspath
from rediacc_hooks.guards.block_host_toolchain_run import _python_target

CHAIN = "pre-bash"
OWN_SUITE = True
ORDER = 64

# Planted, no finding is ever refused: every publish verb, every unproven ASKED and every write into the release clone passes.
DEFECT = ("    if refusals:\n", "    if False:\n")
# The further mutants the own suite plants; each must flip at least one named refusal to allowed.
MUTANTS = {
    "asked-always-true": (
        "return bool(wl_checks._asked_in_transcript(value, transcript))",
        "return True",
    ),
    "dry-run-before-separator": (
        'tail = args[args.index("--") + 1 :] if "--" in args else []\n    return',
        "tail = args\n    return",
    ),
    "bench-any-target": (
        'if module == "rediacc_ci.deploy.deploy_proxy" and target == "bench":',
        'if module == "rediacc_ci.deploy.deploy_proxy":',
    ),
    "eu-any-region": (
        'if module == "rediacc_ci.deploy.deploy_account" and region == "eu":',
        'if module == "rediacc_ci.deploy.deploy_account":',
    ),
    "tag-push-ignored": ("    return _TAG_REF.match(ref) is not None", "    return False"),
    "release-dir-ignored": (
        "    if not word:\n        return False",
        "    if True:\n        return False",
    ),
}

ASK_ENV = "RELEASE_ASKED"
ASK_VALUE = re.compile(r"\AASKED:\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z\Z")
RELEASE_SCRIPT = "release:local"
RELEASE_MODULE = "rediacc_ci.release.local"
# The writers of the release clone: the entry and the gates module it calls (box W2-A).
CLONE_WRITERS = (RELEASE_MODULE, "rediacc_ci.release.local_gates")

DEPLOY_MODULES = tuple(
    "rediacc_ci.deploy.%s" % m
    for m in (
        "deploy_account",
        "deploy_www",
        "deploy_edge",
        "deploy_proxy",
        "upload_to_r2",
        "upload_repos_to_r2",
        "write_release_sentinel",
        "promote_r2_to_stable",
    )
)
RELEASE_MODULES = tuple(
    "rediacc_ci.release.%s" % m
    for m in ("create_github_release", "tag_submodules", "update_homebrew_tap", "mark_production")
)
# The deploy skill's local path (section 4), admitted under a proven RELEASE_ASKED until W3-D.
SKILL_MODULES = (
    "rediacc_ci.deploy.deploy_account",
    "rediacc_ci.deploy.deploy_www",
    "rediacc_ci.deploy.deploy_edge",
)

WRANGLER_PUBLISH = ("deploy", "rollback", "publish")
WRANGLER_VALUE_OPTIONS = ("-c", "--config", "-e", "--env", "--cwd", "--env-file")
GH_RELEASE_PUBLISH = ("create", "upload", "edit", "delete")
DOCKER_PUSH_VERBS = (("push",), ("image", "push"), ("manifest", "push"))
DOCKER_VALUE_OPTIONS = (
    "-t",
    "--tag",
    "-f",
    "--file",
    "--platform",
    "--builder",
    "-o",
    "--output",
    "--context",
    "-H",
    "--host",
)
NPM_VALUE_OPTIONS = ("--prefix", "-w", "--workspace", "--loglevel", "--userconfig", "-C")
NPM_RUN_VERBS = ("run", "run-script", "rum", "urn")
DOCKER_EXEC_VALUE_OPTIONS = (
    "-u",
    "--user",
    "-w",
    "--workdir",
    "-e",
    "--env",
    "--env-file",
    "--detach-keys",
)
# The two argument exemptions, printed on every admission so the debt stays visible.
BENCH_NOTE = (
    "deploy_proxy --target bench admitted: the bench proxy stays manual and is not a release target"
)
EU_NOTE = (
    "deploy_account --region eu admitted: operator ruling 2026-09-26, an eu deploy needs no "
    "question (record the rollback version and the D1 bookmark first)"
)
# A tag ref a release owns: `v1.2.3`, `refs/tags/v1.2.3`, or a pattern over them.
_TAG_REF = re.compile(r"\A(?:refs/tags/)?v[0-9*]")
# How deep wrappers and npm scripts are followed; past it the command is refused as unreadable.
MAX_DEPTH = 4

RELEASE_DIR = re.compile(r"(?:\A|/)\.ci/cache/release(?:/|\Z)")
RELEASE_LITERAL = re.compile(r"['\"](?:[^'\"\s]*/)?\.ci/cache/release(?:/|['\"])")
WRITE_CODE = re.compile(
    r"open\([^)]*,\s*(mode\s*=\s*)?['\"][^'\"]*[wax+]|\.open\(\s*(mode\s*=\s*)?['\"][^'\"]*[wax+]"
    r"|write_text|write_bytes|os\.replace|os\.rename|os\.remove|os\.unlink|os\.makedirs|os\.mkdir"
    r"|shutil\.|unlink|rmtree|mkdir|writeFileSync|appendFileSync|rmSync"
)
# Commands whose operands are what they change: any operand inside the clone is a write to it.
MUTATORS = (
    "rm",
    "rmdir",
    "mkdir",
    "mv",
    "touch",
    "truncate",
    "shred",
    "unlink",
    "tee",
    "chmod",
    "chown",
    "chgrp",
    "setfacl",
    "ln",
)
# git verbs that only read; any other verb run inside the clone changes it.
GIT_READ = (
    "status",
    "log",
    "show",
    "diff",
    "rev-parse",
    "ls-files",
    "ls-tree",
    "cat-file",
    "describe",
    "blame",
    "grep",
    "for-each-ref",
    "rev-list",
    "show-ref",
    "merge-base",
    "name-rev",
    "shortlog",
    "help",
    "version",
)

# The cheap pre-filter: a command naming none of these can neither publish nor reach the clone.
_PREFILTER = re.compile(
    r"wrangler|\bgh\b|\bgit\b|docker|buildx|rediacc_ci|release|deploy|upload_|promote_|sentinel"
    r"|tag_submodules|homebrew|mark_production|run\.sh|\bnpm\b|bws_env|\.ci/cache"
)

MESSAGE = """BLOCKED: this command publishes, or reaches the release clone, outside the one release entry.

%s

A release is published by ONE command, which runs the gates, builds in a fresh clone, seals the
sentinel, tags at once and records every step (agent/plans/PLAN-local-release.md):

    npm run release:local -- --channel edge --dry-run        # always allowed: names every step
    RELEASE_ASKED=ASKED:<YYYY-MM-DDTHH:MM>Z npm run release:local -- --channel edge

The ASKED minute must match an AskUserQuestion answer in this session's transcript (within 300 s),
so the operator is asked first. A raw wrangler deploy, gh release, v* tag push, docker push or
publish module skips the gates and the record; routing around this guard one step at a time is
the failure it exists for.
"""

_ASK = "ASKED:2026-01-01T00:00Z"

EDGE_CASES = [
    ("the entry, no ASKED", "npm run release:local -- --channel edge"),
    ("the entry, dry run", "npm run release:local -- --channel edge --dry-run"),
    ("the entry, dry run before the separator", "npm run release:local --dry-run"),
    (
        "the entry by module, dry run",
        "PYTHONPATH=.ci python3 -m rediacc_ci.release.local --dry-run",
    ),
    ("the entry, ASKED with no transcript", "RELEASE_ASKED=%s npm run release:local" % _ASK),
    ("wrangler deploy", "npx wrangler deploy"),
    ("wrangler rollback under a prefix", "cd workers/www && ./node_modules/.bin/wrangler rollback"),
    ("wrangler deploy dry run", "npx wrangler deploy --dry-run --outdir /tmp/x"),
    ("wrangler tail reads", "npx wrangler tail edge-rediacc-www"),
    ("gh release create", "gh release create v1.2.3 --notes x"),
    ("gh release view", "gh release view v1.2.3"),
    ("a v tag push", "git push origin v1.2.3"),
    ("a branch push", "git push origin 1231-9"),
    ("docker push", "docker push ghcr.io/rediacc/renet:1.2.3"),
    ("buildx --push", "docker buildx build --push -t x ."),
    ("docker build", "docker build -t x ."),
    ("a deploy module", "PYTHONPATH=.ci python3 -m rediacc_ci.deploy.deploy_www"),
    ("a release module", "python3 -m rediacc_ci.release.create_github_release --version 1.2.3"),
    ("the bench proxy", "PYTHONPATH=.ci python3 -m rediacc_ci.deploy.deploy_proxy --target bench"),
    ("the eu proxy", "PYTHONPATH=.ci python3 -m rediacc_ci.deploy.deploy_proxy --target eu"),
    (
        "the eu account deploy",
        "python3 -m rediacc_ci.deploy.deploy_account --region eu --target edge",
    ),
    ("deploy_bench", "PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_bench"),
    ("pytest naming a module", "python3 -m pytest -k rediacc_ci.deploy.deploy_www"),
    ("prose naming a verb", "echo 'wrangler deploy'"),
    ("a redirect into the release clone", "echo x > .ci/cache/release/abc/a.txt"),
    ("reading the release clone", "cat .ci/cache/release/abc/a.txt"),
]


# --------------------------------------------------------------------------- the ASKED proof


def _asked_proven(ev, value):
    """True when the `ASKED:` minute in `value` matches an AskUserQuestion answer in the payload's transcript (`wl_checks._asked_in_transcript`, imported, never copied)."""
    transcript = ev.field("transcript_path")
    if not transcript:
        return False
    syspath.on_sys_path(plan_gate.STOP_DIR)
    try:
        import wl_checks
    except ImportError as exc:
        ev.warn(
            "block-unasked-release: wl_checks could not import (%s), so no ASKED: minute can "
            "be proven." % exc
        )
        return False
    return bool(wl_checks._asked_in_transcript(value, transcript))


# --------------------------------------------------------------------------- reading one run


def _base(name):
    return name.rsplit("/", 1)[-1]


def _positionals(args, value_options=()):
    """The words of `args` that are not options, skipping the value of each `value_options` spelling given apart from its option."""
    out = []
    k = 0
    while k < len(args):
        word = args[k]
        if word == "--":
            out.extend(args[k + 1 :])
            break
        if word in value_options:
            k += 2
            continue
        if word.startswith("-") and len(word) > 1:
            k += 1
            continue
        out.append(word)
        k += 1
    return out


def _option(args, name):
    """The last value `--name v` or `--name=v` gives in `args`, or ""."""
    found = ""
    for k, word in enumerate(args):
        if word == name and k + 1 < len(args):
            found = args[k + 1]
        elif word.startswith(name + "="):
            found = word[len(name) + 1 :]
    return found


def _join(cwd, *parts):
    """`parts` placed under `cwd`, an absolute part restarting the path."""
    path = cwd or ""
    for part in parts:
        if part:
            path = os.path.join(path, part)
    return os.path.normpath(path) if path else ""


def _module(run, where):
    """The dotted module a python run executes (`-m X`, or a script path under `.ci/`), or ""."""
    if not re.match(r"\Apython[0-9.]*\Z", _base(run.name)):
        return ""
    target = _python_target(list(run.argv)) or ""
    if not target.endswith(".py"):
        return target if target.startswith("rediacc_ci.") else ""
    path = _join(where, target).replace("\\", "/")
    found = re.search(r"(?:\A|/)(rediacc_ci/.+)\.py\Z", path)
    return found.group(1).replace("/", ".") if found else ""


def _module_args(run):
    """The words after the module or script a python run executes."""
    args = list(run.argv)
    for k, word in enumerate(args):
        if word == "-m":
            return args[k + 2 :]
        if word.startswith("-m") and len(word) > 2:
            return args[k + 1 :]
        if not word.startswith("-"):
            return args[k + 1 :]
    return []


def _declares_dry_run(root, module):
    path = os.path.join(str(root), ".ci", *module.split(".")) + ".py"
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return '"--dry-run"' in handle.read()
    except OSError:
        return False


def _npm_run(run):
    """`(script, args after the script, the directory option)` for an `npm run <script>`, else None."""
    if _base(run.name) != "npm":
        return None
    args = list(run.argv)
    directory = (
        _option(args, "--prefix")
        or _option(args, "-C")
        or _option(args, "-w")
        or _option(args, "--workspace")
    )
    words = _positionals(args, NPM_VALUE_OPTIONS)
    if len(words) < 2 or words[0] not in NPM_RUN_VERBS:
        return None
    script = words[1]
    return script, args[args.index(script) + 1 :], directory


def _npm_script_text(directory, script):
    """The text of `script` in `<directory>/package.json`, or ""."""
    try:
        with open(os.path.join(directory, "package.json"), encoding="utf-8") as handle:
            scripts = json.load(handle).get("scripts") or {}
    except (OSError, ValueError, AttributeError):
        return ""
    text = scripts.get(script) if isinstance(scripts, dict) else None
    return text if isinstance(text, str) else ""


def _dry_run_entry(args):
    """Is this npm run of the entry a dry run? Only a `--dry-run` AFTER `--` reaches the script: measured on npm 11.21.0, `npm run s --dry-run` hands the script no argument at all and sets `npm_config_dry_run=true` instead."""
    tail = args[args.index("--") + 1 :] if "--" in args else []
    return "--dry-run" in tail


def _tag_ref(ref):
    """Does one push refspec side name a release tag?"""
    return _TAG_REF.match(ref) is not None


def _pushes_release_tag(args):
    parsed = shellscan.git_push_args(args)
    if parsed.on("dry-run"):
        return ""
    if parsed.on("tags"):
        return "git push --tags (every tag, the v* release tags included)"
    if parsed.on("mirror"):
        return "git push --mirror (every ref, the v* release tags included)"
    for spec in parsed.operands[1:]:
        for side in spec.lstrip("+").split(":"):
            if side and _tag_ref(side):
                return "git push of the release tag `%s`" % spec
    return ""


def _wrapped(run, where):
    """The command a wrapper hands its tail to (`run.sh devbox exec`, `bws_env exec`, `docker exec`), as text, or None."""
    args = list(run.argv)
    name = _base(run.name)
    if name == "run.sh" and args[:2] == ["devbox", "exec"]:
        tail = args[2:]
        return shlex.join(tail[1:] if tail[:1] == ["--"] else tail)
    if _module(run, where) == "rediacc_ci.core.bws_env":
        rest = _module_args(run)
        if rest[:1] == ["exec"] and "--" in rest:
            return shlex.join(rest[rest.index("--") + 1 :])
        return None
    if name == "docker" and args[:1] == ["exec"]:
        # The container is the first word that is neither an option nor an option's value; everything after it is the container's own argv, its options included (`bash -lc '...'`).
        k = 1
        while k < len(args):
            if args[k] in DOCKER_EXEC_VALUE_OPTIONS:
                k += 2
            elif args[k].startswith("-"):
                k += 1
            else:
                return shlex.join(args[k + 1 :]) if k + 1 < len(args) else None
        return None
    return None


def _module_publish(module, rest, root):
    """`(kind, what, note)` for a run of one publish module with arguments `rest`."""
    if "--help" in rest or "-h" in rest:
        return "", "", ""
    if "--dry-run" in rest and _declares_dry_run(root, module):
        return "", "", ""
    target = _option(rest, "--target")
    region = _option(rest, "--region")
    if module == "rediacc_ci.deploy.deploy_proxy" and target == "bench":
        return "note", module, BENCH_NOTE
    if module == "rediacc_ci.deploy.deploy_account" and region == "eu":
        return "note", module, EU_NOTE
    if module in SKILL_MODULES:
        return "ask", "python3 -m %s (the deploy skill's local path)" % module, ""
    return "refuse", "python3 -m %s" % module, ""


def _docker_publish(name, args):
    words = _positionals(args, DOCKER_VALUE_OPTIONS)
    if any(tuple(words[: len(v)]) == v for v in DOCKER_PUSH_VERBS):
        return "refuse", "%s %s" % (name, " ".join(words[:2])), ""
    building = "build" in words[:2] or words[:1] == ["buildx"]
    outputs = [_option(args, "-o"), _option(args, "--output")]
    if building and (
        "--push" in args or any("type=registry" in o or "push=true" in o for o in outputs)
    ):
        return "refuse", "%s %s --push" % (name, " ".join(words[:2])), ""
    if words[:3] == ["buildx", "imagetools", "create"] and "--dry-run" not in args:
        return "refuse", "docker buildx imagetools create (writes a registry tag)", ""
    return "", "", ""


def _publish(run, where, root):
    """`(kind, what, note)` for one run: kind "refuse", "ask" (needs a proven RELEASE_ASKED), "note" (admitted by a named exemption) or "" (not a publish)."""
    name = _base(run.name)
    args = list(run.argv)
    npm = _npm_run(run)
    if npm is not None and npm[0] == RELEASE_SCRIPT:
        if _dry_run_entry(npm[1]):
            return "", "", ""
        return "ask", "npm run release:local without -- --dry-run", ""
    module = _module(run, where)
    if module == RELEASE_MODULE:
        if "--dry-run" in _module_args(run):
            return "", "", ""
        return "ask", "python3 -m rediacc_ci.release.local without --dry-run", ""
    if name.startswith("wrangler"):
        words = _positionals(args, WRANGLER_VALUE_OPTIONS)
        sub = words[0] if words else ""
        publishes = sub in WRANGLER_PUBLISH or (sub == "versions" and words[1:2] == ["deploy"])
        if publishes and "--dry-run" not in args:
            return "refuse", "wrangler %s" % " ".join(words[:2] if sub == "versions" else [sub]), ""
        return "", "", ""
    if name == "gh":
        words = _positionals(args, ("-R", "--repo"))
        if words[:1] == ["release"] and words[1:2] and words[1] in GH_RELEASE_PUBLISH:
            return "refuse", "gh release %s" % words[1], ""
        return "", "", ""
    if name == "git":
        _globals, verb, rest = commit_policy.git_split(args)
        what = _pushes_release_tag(rest) if verb == "push" else ""
        return ("refuse", what, "") if what else ("", "", "")
    if name in ("docker", "docker-buildx", "podman"):
        return _docker_publish(name, args)
    if module in DEPLOY_MODULES or module in RELEASE_MODULES:
        return _module_publish(module, _module_args(run), root)
    return "", "", ""


def _judge(cmd, where_root, env, root, depth, found):
    """Append `(kind, what, note, env)` to `found` for every publish in `cmd`, wrappers and npm scripts followed."""
    if depth > MAX_DEPTH:
        found.append(("refuse", "a command nested more than %d levels deep" % MAX_DEPTH, "", env))
        return
    for run in shellscan.every_run(cmd):
        where = _join(where_root, run.cwd or "")
        merged = dict(env)
        merged.update(run.env)
        inner = _wrapped(run, where)
        if inner is not None:
            _judge(inner, where, merged, root, depth + 1, found)
            continue
        kind, what, note = _publish(run, where, root)
        if kind:
            found.append((kind, what, note, merged))
            continue
        npm = _npm_run(run)
        if npm is None:
            continue
        script, args, directory = npm
        home = _join(where, directory)
        text = _npm_script_text(home, script)
        if text:
            tail = args[args.index("--") + 1 :] if "--" in args else []
            _judge(
                ("%s %s" % (text, shlex.join(tail))).strip(), home, merged, root, depth + 1, found
            )


# --------------------------------------------------------------------------- the shell-write twin


def _in_release(word, where=None, base=None):
    """Is `word`, placed in the run's directory, inside `.ci/cache/release/` (as typed, or where the disk resolves it)?"""
    if not word:
        return False
    forms = [word]
    if where and not word.startswith("/"):
        forms.append(_join(where, word))
    if any(RELEASE_DIR.search(f.replace("\\", "/")) for f in forms):
        return True
    if not base or len(word) >= 4096 or "\n" in word or "\0" in word:
        return False
    try:
        landed = os.path.realpath(os.path.join(base, word))
    except (OSError, ValueError):
        return False
    return RELEASE_DIR.search(landed.replace("\\", "/")) is not None


def _operands(run, argv):
    ops = [a for a in argv if not (a.startswith("-") and len(a) > 1)]
    return shellscan.xargs_fed_operands(run, ops)


def _interpreter_write(run, name, cmd, cwd, where, base):
    text, kind = shellscan.interpreter_program(run, cmd, cwd)
    code = " ".join(run.argv)
    if kind in ("stdin", "file") and text:
        code += "\n" + text
    if _in_release(".", where, base) and WRITE_CODE.search(code):
        return "%s code that writes inside the release clone" % name
    for line in code.splitlines():
        if RELEASE_LITERAL.search(line) and WRITE_CODE.search(line):
            return "%s code that writes into the release clone" % name
    return ""


def _run_write(run, cmd, cwd):
    """A short description of the write one run makes into `.ci/cache/release/`, or ""."""
    name = _base(run.name)
    argv = list(run.argv)
    where = _join(str(cwd or ""), shellscan.write_directory(run.cwd, cwd) or "")
    base = where if os.path.isabs(where) else None
    if _module(run, where) in CLONE_WRITERS:
        return ""
    npm = _npm_run(run)
    if npm is not None and npm[0] == RELEASE_SCRIPT:
        return ""
    for target in shellscan.redirect_targets(run):
        if _in_release(target, where, base):
            return "redirect into %s" % target
    operands = _operands(run, argv)
    if name in MUTATORS and any(_in_release(a, where, base) for a in operands):
        return "%s on the release clone" % name
    edits = shellscan.in_place_edit(run) is not None
    if edits and any(_in_release(a, where, base) for a in operands):
        return "%s -i on the release clone" % name
    copies = shellscan.run_copies(run, argv, cwd)
    if copies is not None and any(_in_release(d, where, base) for d in copies[1]):
        return "%s onto the release clone" % name
    if name == "dd" and any(a.startswith("of=") and _in_release(a[3:], where, base) for a in argv):
        return "dd of= the release clone"
    if name == "git":
        globals_, verb, _rest = commit_policy.git_split(argv)
        directory = _option(globals_, "-C") or "."
        if verb and verb not in GIT_READ and _in_release(directory, where, base):
            return "git %s inside the release clone" % verb
    for word, _how in shellscan.output_landings(run, argv, cwd):
        if _in_release(word, where, base):
            return "%s writing %s" % (name, word)
    if name.startswith(shellscan.INTERPRETER_NAMES):
        return _interpreter_write(run, name, cmd, cwd, where, base)
    return ""


def _release_write(cmd, cwd):
    """A short description of the first agent write into `.ci/cache/release/` in `cmd`, or ""."""
    base_cwd = cwd if cwd and os.path.isabs(str(cwd)) else None
    for target in shellscan.write_targets(cmd):
        if _in_release(target, cwd, base_cwd):
            return "redirect into %s" % target
    for run in shellscan.every_run(cmd):
        what = _run_write(run, cmd, cwd)
        if what:
            return what
    return ""


# --------------------------------------------------------------------------- the verdict


def _ask_verdict(ev, what, env):
    """`(refusal, note)` for one finding that needs a proven RELEASE_ASKED."""
    value = env.get(ASK_ENV) or ""
    if not value:
        return "  %s: carries no %s=ASKED:<YYYY-MM-DDTHH:MM>Z" % (what, ASK_ENV), ""
    if not ASK_VALUE.match(value):
        return "  %s: %s=%r is not ASKED:<YYYY-MM-DDTHH:MM>Z" % (what, ASK_ENV, value), ""
    if not _asked_proven(ev, value):
        return (
            "  %s: %s=%s matches no AskUserQuestion answer in this session's transcript "
            "(within 300 s)" % (what, ASK_ENV, value)
        ), ""
    return "", "%s admitted by %s=%s" % (what, ASK_ENV, value)


def run(ev):
    cmd = ev.raw("tool_input", "command")
    if cmd in ("", "null") or not _PREFILTER.search(cmd):
        return hookio.ALLOW
    root = ev.project_dir
    cwd = ev.field("cwd") or root
    found = []
    _judge(cmd, cwd, {}, root, 0, found)

    refusals = []
    notes = []
    for kind, what, note, env in found:
        if kind == "refuse":
            refusals.append("  %s: a raw publish verb" % what)
        elif kind == "note":
            notes.append(note)
        elif kind == "ask":
            refusal, admitted = _ask_verdict(ev, what, env)
            refusals.extend([refusal] if refusal else [])
            notes.extend([admitted] if admitted else [])
    write = _release_write(cmd, cwd)
    if write:
        refusals.append(
            "  %s: .ci/cache/release/ is the release clone, written only by the entry and its "
            "gates; a hand edit there makes the cleanliness gate prove nothing" % write
        )
    if refusals:
        ev.warn_raw(MESSAGE % "\n".join(refusals))
        return hookio.DENY
    for note in notes:
        ev.warn("NOTE (block-unasked-release): %s." % note)
    return hookio.ALLOW
