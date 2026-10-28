"""Refuse a stable release or deploy from agent Bash unless the operator asked for it, refuse the raw publish verbs a release is made of, and leave edge and bench free.

WHY. agent/plans/PLAN-local-release.md moves the edge release to one local entry, `npm run release:local -- --channel edge [--dry-run]` (`rediacc_ci.release.local`, box W2-B). The operator ruling of 2026-10-27T09:45Z sets the line this guard (box W2-C) holds: "EU/ASIA/US stable should be asked! They're CI/CD only. BUT edge and bench could be released via agent or with CI/CD." So:

  1. EDGE AND BENCH ARE FREE, with no question: `npm run release:local -- --channel edge` (with or without `--dry-run`), `deploy_edge`, `deploy_account --target edge` in any region, `account_secrets_local --target edge`, `deploy_proxy`/`console_executor --target edge|bench` (`--target` read in every prefix spelling argparse accepts, `--tar` included), `deploy_bench`, and `set_*_worker_secrets` whose `TARGET`/`WORKER_NAME` on the command line name edge.
  2. EVERY STABLE TARGET NEEDS A PROVEN ASK, in every region, eu included (the 2026-09-26 eu exemption is retired by this ruling): `deploy_account` with any `--target` but `edge` (its default is production), `deploy_www`, `account_secrets_local`/`deploy_proxy`/`console_executor` with a stable target, `set_*_worker_secrets` for a stable Worker or with no target on the command line, `wrangler deploy|rollback` on a stable config, and the promote verbs (`promote_r2_to_stable`, its hotfix twin, `promote_docker_to_stable_hotfix`, `mark_production`). Each is admitted only when the command carries `RELEASE_ASKED=ASKED:<YYYY-MM-DDTHH:MM>Z` and that minute matches an AskUserQuestion answer in the payload's transcript within 300 s. The proof is `wl_checks._asked_in_transcript`, imported, the same check `block_vm_unverified_push` and `block_backup_unverified_push` use.
  3. `release:local --channel stable` IS REFUSED OUTRIGHT, dry run included, and RELEASE_ASKED does not admit it: stable is promoted by `.github/workflows/promote-stable.yml` only. A run of the entry naming no channel is refused too, and each launcher is told its own reason: npm hands the script only the words after `--` (`npm run release:local --channel edge` reaches the script with no channel at all), while `python3 -m rediacc_ci.release.local` sees every word and simply names none.
  4. THE RAW PUBLISH VERBS STAY REFUSED, with no escape: `gh release create|upload|edit|delete`, a `git push` of a `v*` tag (`refs/tags/v*`, `--tags`, `--mirror`, and `--follow-tags` on any push but the GitLab mirror push of `main`), `docker push` (and `image push`, `manifest push`, `compose push|publish`, `compose build --push`), a `docker build`/`buildx build` with `--push` or a registry output (`-o` attached or bundled too), `docker buildx imagetools create`, `wrangler pages deploy|publish`, a `wrangler deploy|rollback|publish|versions deploy` on an edge, bench or preview config (judged on the config's file name, never the directories above it) (the edge modules above are its path), and `-m` on the release entry's own steps (`upload_to_r2`, `upload_repos_to_r2`, `write_release_sentinel`, `create_github_release`, `tag_submodules`, `update_homebrew_tap`), which the entry runs in order with its gates and record.

A SHELL-WRITE TWIN rides the same module: an agent write under `.ci/cache/release/` (a redirect, `tee`, `sed -i`, a copy or move onto it, `rm`, `mkdir`, `touch`, `chmod`, a mutating `git` inside the release clone, an interpreter program writing there) is refused. Decision 1 of the plan judges cleanliness on a fresh clone of HEAD at `.ci/cache/release/<tree>/`; a clone a session can edit by hand proves nothing. Only the entry and its gates module write there. The Edit and Write tools are NOT judged here: that half is a pre-edit guard this module cannot be (one module, one chain).

A `--help`/`-h` on a publish module passes, as does `--help` on a `wrangler`, `gh` or `docker` publish verb, and so does `--dry-run` on one whose own source declares `--dry-run` (a module that does not would reject the flag or, read with `parse_known_args`, ignore it and publish; the source is what says which). `set_preview_worker_secrets` is not judged: a preview Worker is never stable.

WRAPPERS ARE UNWRAPPED. `./run.sh devbox exec -- ...`, `bws_env exec ... -- ...` and `docker exec <container> ...` hand their tail to another process, so the tail is judged as a command of its own with the outer environment carried in. `npm run <script>` is judged by the script's own text from the package.json of each directory it runs in (`--prefix`, `cd`, or each workspace `-w` names by path or package name, every one under `--workspaces`), because `workers/mta-sts`'s `npm run deploy` is a `wrangler deploy` that names no publish verb on the command line.

WHAT IT DOES NOT SEE: a publish verb assembled at run time, `gh api` POSTs to the releases endpoint, a `TARGET` or `WORKER_NAME` the session's own environment holds (absent from the command line, it reads as stable, the fail-closed direction), a path into `.ci/cache/release/` spelled through a glob or a symlink the word does not resolve through, and a program that builds the path from parts. The release record and the R2 sentinel are what a release leaves behind, so a release this guard missed is still visible after the fact.

ORDER 62, ahead of `block_vm_unverified_push` (63) and `block_backup_unverified_push` (64). Both write a ledger line once they admit an escaped push, on the claim that every refusing guard ran first; with this guard behind them a command that escapes a push AND runs a refused publish verb left a ledger line for a push that never ran.

THIS GUARD HAS NO BASH TWIN (`OWN_SUITE = True`); it is judged by `test-block_unasked_release.py` beside it, which also plants DEFECT and every MUTANT.
"""

import glob
import json
import os
import re
import shlex

from rediacc_hooks import commit_policy, hookio, plan_gate, shellscan, syspath
from rediacc_hooks.guards.block_host_toolchain_run import _python_target
from rediacc_hooks.wellknown import IMAGE_REGISTRY

CHAIN = "pre-bash"
OWN_SUITE = True
ORDER = 62

# Planted, no finding is ever refused: every publish verb, every unproven ASKED and every write into the release clone passes.
DEFECT = ("    if refusals:\n", "    if False:\n")
# The further mutants the own suite plants; each must flip at least one named refusal to allowed.
MUTANTS = {
    "asked-always-true": (
        "return bool(wl_checks._asked_in_transcript(value, transcript))",
        "return True",
    ),
    "channel-before-separator": (
        '    tail = args[args.index("--") + 1 :] if "--" in args else []\n    return _option(tail',
        "    tail = args\n    return _option(tail",
    ),
    "any-channel-admitted": ('    if channel == "edge":\n', "    if True:\n"),
    "account-target-ignored": (
        'return "edge" if target == "edge" else "stable"',
        'return "edge"',
    ),
    "proxy-target-ignored": (
        'return "edge" if target in EDGE_TARGETS else "stable"',
        'return "edge"',
    ),
    "stable-config-unasked": (
        'return "ask", "wrangler %s on the stable',
        'return "", "wrangler %s on the stable',
    ),
    "tag-push-ignored": ("    return _TAG_REF.match(ref) is not None", "    return False"),
    "release-dir-ignored": (
        "    if not word:\n        return False",
        "    if True:\n        return False",
    ),
    "module-no-channel-says-npm": (
        "NO_CHANNEL_REFUSAL if npm else NO_CHANNEL_MODULE_REFUSAL",
        "NO_CHANNEL_REFUSAL",
    ),
    "config-path-judged-whole": (
        '_EDGE_CONFIG.search(_base(config.replace("\\\\", "/")).lower())',
        're.search(r"edge|bench|preview", config.lower())',
    ),
    "follow-tags-ignored": (
        'if parsed.on("follow-tags") and not _mirror_push(parsed.operands):',
        "if False:",
    ),
    "target-prefix-ignored": ("not name.startswith(spelled)", "spelled != name"),
    "workspace-name-ignored": ("elif value in spaces:", "elif False:"),
    "short-output-ignored": (
        'outputs = [_option(args, "--output"), *_short_values(args, "o")]',
        'outputs = [_option(args, "--output"), _option(args, "-o")]',
    ),
    "compose-push-ignored": ("    if verb in COMPOSE_PUSH_VERBS:\n", "    if False:\n"),
    "pages-ignored": ('if sub == "pages" and', 'if False and sub == "pages" and'),
    "account-target-case-folded": (
        'flag[2:].replace("-", "_").upper() == "TARGET"',
        'flag == "--target"',
    ),
    "account-bare-target-kept": (
        '                value = "true"\n',
        "                value = target\n",
    ),
    "help-taken-as-value": (
        'if not (before.startswith("-") and len(before) > 1 and "=" not in before):',
        "if True:",
    ),
    "help-undeclared": (
        '_asks_help(rest, ("--help", "-h")) and _declares_help(root, module)',
        '_asks_help(rest, ("--help", "-h"))',
    ),
    "workspace-glob-through-path": (
        "glob.glob(pattern, root_dir=here)",
        "glob.glob(os.path.join(here, pattern))",
    ),
}

ASK_ENV = "RELEASE_ASKED"
ASK_VALUE = re.compile(r"\AASKED:\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z\Z")
RELEASE_SCRIPT = "release:local"
RELEASE_MODULE = "rediacc_ci.release.local"
# The writers of the release clone: the entry and the gates module it calls (box W2-A).
CLONE_WRITERS = (RELEASE_MODULE, "rediacc_ci.release.local_gates")

# The targets the 2026-10-27T09:45Z ruling leaves free; every other target is stable and needs a proven ask.
EDGE_TARGETS = ("edge", "bench")
# `--target edge` is free; any other value, its default `production` included, deploys stable.
ACCOUNT_MODULE = "rediacc_ci.deploy.deploy_account"
# `--target edge|bench` is free; `stable`, or no target, needs a proven ask.
TARGET_MODULES = (
    "rediacc_ci.deploy.deploy_proxy",
    "rediacc_ci.deploy.console_executor",
    "rediacc_ci.deploy.account_secrets_local",
)
# Edge or bench by construction: free.
EDGE_MODULES = ("rediacc_ci.deploy.deploy_edge", "rediacc_ci.ops.deploy_bench")
# Stable by construction: the stable www Worker and the promote verbs. Each needs a proven ask.
STABLE_MODULES = (
    "rediacc_ci.deploy.deploy_www",
    "rediacc_ci.deploy.promote_r2_to_stable",
    "rediacc_ci.deploy.promote_r2_to_stable_hotfix",
    "rediacc_ci.deploy.promote_docker_to_stable_hotfix",
    "rediacc_ci.release.mark_production",
)
# The Worker secret pushes, whose channel is the `TARGET` and `WORKER_NAME` on the command line.
SECRETS_MODULES = (
    "rediacc_ci.deploy.set_account_worker_secrets",
    "rediacc_ci.deploy.set_www_worker_secrets",
)
# The release entry's own steps: refused raw, because the entry runs them in order behind its gates.
STEP_MODULES = (
    "rediacc_ci.deploy.upload_to_r2",
    "rediacc_ci.deploy.upload_repos_to_r2",
    "rediacc_ci.deploy.write_release_sentinel",
    "rediacc_ci.release.create_github_release",
    "rediacc_ci.release.tag_submodules",
    "rediacc_ci.release.update_homebrew_tap",
)
PUBLISH_MODULES = (
    ACCOUNT_MODULE,
    *TARGET_MODULES,
    *EDGE_MODULES,
    *STABLE_MODULES,
    *SECRETS_MODULES,
    *STEP_MODULES,
)
STABLE_CHANNEL_REFUSAL = (
    "release:local --channel stable: stable is promoted through CI/CD only "
    "(.github/workflows/promote-stable.yml, operator ruling 2026-10-27T09:45Z); "
    "RELEASE_ASKED does not admit it"
)
NO_CHANNEL_REFUSAL = (
    "release:local names no --channel edge after `--` (npm hands the script only the words "
    "after `--`)"
)
# The same refusal for `python3 -m rediacc_ci.release.local`, where npm is not involved and every word reaches the module (review 22a275ab.1).
NO_CHANNEL_MODULE_REFUSAL = "python3 -m %s names no --channel edge" % RELEASE_MODULE

WRANGLER_PUBLISH = ("deploy", "rollback", "publish")
# An edge, bench or preview config, judged on the file NAME as a whole dot- or dash-separated word (`wrangler.edge-eu.toml`, `wrangler.bench.toml`): the directories above it say nothing about the Worker, so `/srv/edge-tools/wrangler.eu.toml` is the stable eu config and needs an ask, not a refusal (review 22a275ab.2).
_EDGE_CONFIG = re.compile(r"(?:\A|[.\-_])(?:edge|bench|preview)(?:[.\-_]|\Z)")
# `wrangler pages deploy|publish` publishes a Pages site, which no release path runs (review 2e939f2a.6).
WRANGLER_PAGES_PUBLISH = ("deploy", "publish")
WRANGLER_VALUE_OPTIONS = ("-c", "--config", "-e", "--env", "--cwd", "--env-file")
GH_RELEASE_PUBLISH = ("create", "upload", "edit", "delete")
DOCKER_PUSH_VERBS = (("push",), ("image", "push"), ("manifest", "push"))
DOCKER_NAMES = ("docker", "docker-buildx", "podman", "docker-compose", "podman-compose")
# `docker compose push` pushes every service image, `compose publish` the project as an OCI artifact, and `compose build --push` builds and pushes (review 2e939f2a.6).
COMPOSE_PUSH_VERBS = ("push", "publish")
COMPOSE_VALUE_OPTIONS = (
    "-f",
    "--file",
    "-p",
    "--project-name",
    "--project-directory",
    "--profile",
    "--env-file",
    "--ansi",
    "--progress",
    "--parallel",
)
# The shorthands of `docker build`/`buildx build` that take a value; in a bundle (`-qo...`) the first of them takes the rest of the word, so `-otype=registry` is `--output type=registry` (pflag's rule, review 2e939f2a.5).
DOCKER_SHORT_VALUES = "tfom"
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
# The console's GitLab mirror remote, `githooks.MIRROR_REMOTE` (.claude/rediacc_hooks/git/githooks.py), whose one admitted push carries `--follow-tags`.
MIRROR_REMOTE = "gitlab"
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

MESSAGE = """BLOCKED: this command publishes, or reaches the release clone, outside the sanctioned paths.

%s

EDGE AND BENCH ARE FREE, through the entry or the edge modules (operator ruling 2026-10-27T09:45Z):

    npm run release:local -- --channel edge [--dry-run]
    PYTHONPATH=.ci python3 -m rediacc_ci.deploy.deploy_edge
    PYTHONPATH=.ci python3 -m rediacc_ci.deploy.deploy_account --region <r> --target edge
    PYTHONPATH=.ci python3 -m rediacc_ci.deploy.deploy_proxy --target edge|bench --region <r>

STABLE IS CI/CD ONLY. A stable deploy from here needs the operator's answer first, and the
ASKED minute must match an AskUserQuestion answer in this session's transcript (within 300 s):

    RELEASE_ASKED=ASKED:<YYYY-MM-DDTHH:MM>Z <the stable deploy command>

`release:local --channel stable` is refused even then: promote-stable.yml promotes stable. A raw
gh release, v* tag push, docker push or release step is never admitted here; the entry runs them
behind its gates and records each one.
"""

_ASK = "ASKED:2026-01-01T00:00Z"
_PY = "PYTHONPATH=.ci python3 -m"

EDGE_CASES = [
    ("the edge entry", "npm run release:local -- --channel edge"),
    ("the edge entry, dry run", "npm run release:local -- --channel edge --dry-run"),
    ("the entry, channel before the separator", "npm run release:local --channel edge"),
    ("the stable entry", "npm run release:local -- --channel stable --dry-run"),
    (
        "the stable entry with an ASKED",
        "RELEASE_ASKED=%s %s" % (_ASK, "npm run release:local -- --channel stable"),
    ),
    ("the entry by module", "%s rediacc_ci.release.local --channel edge" % _PY),
    ("wrangler deploy on a stable config", "npx wrangler deploy --config wrangler.eu.toml"),
    ("wrangler deploy on an edge config", "npx wrangler deploy --config wrangler.edge-eu.toml"),
    ("wrangler deploy dry run", "npx wrangler deploy --dry-run --outdir /tmp/x"),
    ("wrangler tail reads", "npx wrangler tail edge-rediacc-www"),
    ("gh release create", "gh release create v1.2.3 --notes x"),
    ("gh release view", "gh release view v1.2.3"),
    ("a v tag push", "git push origin v1.2.3"),
    ("a branch push", "git push origin 1231-9"),
    ("docker push", "docker push %s/renet:1.2.3" % IMAGE_REGISTRY),
    ("docker build", "docker build -t x ."),
    ("the stable www deploy", "%s rediacc_ci.deploy.deploy_www" % _PY),
    ("the edge www deploy", "%s rediacc_ci.deploy.deploy_edge" % _PY),
    ("an eu stable account deploy", "%s rediacc_ci.deploy.deploy_account --region eu" % _PY),
    (
        "an asia edge account deploy",
        "%s rediacc_ci.deploy.deploy_account --region asia --target edge" % _PY,
    ),
    ("the bench proxy", "%s rediacc_ci.deploy.deploy_proxy --target bench" % _PY),
    ("a stable proxy", "%s rediacc_ci.deploy.deploy_proxy --target stable --region eu" % _PY),
    ("a raw release step", "%s rediacc_ci.release.create_github_release --version 1.2.3" % _PY),
    ("deploy_bench", "%s rediacc_ci.ops.deploy_bench" % _PY),
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
    """`(script, args after the script, every npm argument)` for an `npm run <script>`, else None."""
    if _base(run.name) != "npm":
        return None
    args = list(run.argv)
    words = _positionals(args, NPM_VALUE_OPTIONS)
    if len(words) < 2 or words[0] not in NPM_RUN_VERBS:
        return None
    script = words[1]
    return script, args[args.index(script) + 1 :], args


def _values(args, names):
    """Every value any of `names` takes in `args`, apart (`-w x`) or attached (`--workspace=x`), up to `--`."""
    out = []
    for k, word in enumerate(args):
        if word == "--":
            break
        for name in names:
            if word == name and k + 1 < len(args):
                out.append(args[k + 1])
            elif word.startswith(name + "="):
                out.append(word[len(name) + 1 :])
    return out


def _package(directory):
    """The parsed `<directory>/package.json` as a dict, or {}."""
    try:
        with open(os.path.join(directory, "package.json"), encoding="utf-8") as handle:
            doc = json.load(handle)
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def _workspaces(home):
    """`(root, {name: directory})`: the nearest of `home` and its parents whose package.json declares `workspaces`, and each workspace it globs to, by its package name. `(home, {})` when none declares any."""
    here = home
    while True:
        spaces = _package(here).get("workspaces")
        if isinstance(spaces, dict):
            spaces = spaces.get("packages")
        if isinstance(spaces, list):
            found = {}
            for pattern in spaces:
                if not isinstance(pattern, str) or pattern.startswith("!"):
                    continue
                # The pattern is globbed UNDER `here` (`root_dir`), never joined onto it: a project path holding `[`, `*` or `?` would read as glob syntax and match nothing, so no workspace would be judged (review 7f22f490.4).
                for leaf in sorted(glob.glob(pattern, root_dir=here)):
                    directory = os.path.join(here, leaf)
                    name = _package(directory).get("name")
                    if isinstance(name, str):
                        found[name] = os.path.normpath(directory)
            return here, found
        parent = os.path.dirname(here)
        if not here or parent == here:
            return home, {}
        here = parent


def _npm_dirs(where, args):
    """Every directory an `npm run` runs its script in: the prefix (`--prefix`, `-C`, else the run's own directory), or, when workspaces are selected, each one. `-w`/`--workspace` names a workspace by PATH or by package NAME (review 2e939f2a.4), and repeats; `--workspaces`/`-ws` selects all of them, and `--include-workspace-root` adds the root back."""
    home = _join(where, _option(args, "--prefix") or _option(args, "-C"))
    picked = _values(args, ("-w", "--workspace"))
    every = "-ws" in args or _bool_on(args, "--workspaces") or _bool_on(args, "--ws")
    if not picked and not every:
        return [home]
    root, spaces = _workspaces(home)
    dirs = list(spaces.values()) if every else []
    for value in picked:
        paths = [_join(base, value) for base in (home, root)]
        hit = next((d for d in paths if os.path.isfile(os.path.join(d, "package.json"))), "")
        if hit:
            dirs.append(hit)
        elif value in spaces:
            dirs.append(spaces[value])
        else:
            # A parent directory of workspaces selects every workspace inside it.
            dirs.extend(d for d in spaces.values() for p in paths if d.startswith(p + os.sep))
    if _bool_on(args, "--include-workspace-root"):
        dirs.append(root)
    return list(dict.fromkeys(dirs))


def _npm_script_text(directory, script):
    """The text of `script` in `<directory>/package.json`, or ""."""
    try:
        with open(os.path.join(directory, "package.json"), encoding="utf-8") as handle:
            scripts = json.load(handle).get("scripts") or {}
    except (OSError, ValueError, AttributeError):
        return ""
    text = scripts.get(script) if isinstance(scripts, dict) else None
    return text if isinstance(text, str) else ""


def _channel(args, npm):
    """The `--channel` a run of the entry hands the script. For npm only the words AFTER `--` reach it: measured on npm 11.21.0, `npm run s --dry-run` hands the script no argument at all and sets `npm_config_dry_run=true` instead, and `--channel` is read the same way."""
    if not npm:
        return _option(args, "--channel")
    tail = args[args.index("--") + 1 :] if "--" in args else []
    return _option(tail, "--channel")


def _entry_verdict(channel, npm):
    """`(kind, what, note)` for a run of the release entry on `channel`, launched through `npm run` when `npm` is true."""
    if channel == "edge":
        return "", "", ""
    if channel == "stable":
        return "refuse", STABLE_CHANNEL_REFUSAL, ""
    return "refuse", NO_CHANNEL_REFUSAL if npm else NO_CHANNEL_MODULE_REFUSAL, ""


def _tag_ref(ref):
    """Does one push refspec side name a release tag?"""
    return _TAG_REF.match(ref) is not None


def _mirror_push(operands):
    """Is this the GitLab mirror push of `main` (`githooks.MIRROR_REMOTE`, one refspec `main:main` or `refs/heads/main:refs/heads/main`)?"""
    return operands[:1] == [MIRROR_REMOTE] and operands[1:] in (
        ["main:main"],
        ["refs/heads/main:refs/heads/main"],
    )


def _pushes_release_tag(args):
    parsed = shellscan.git_push_args(args)
    if parsed.on("dry-run"):
        return ""
    if parsed.on("tags"):
        return "git push --tags (every tag, the v* release tags included)"
    if parsed.on("mirror"):
        return "git push --mirror (every ref, the v* release tags included)"
    # `--follow-tags` also pushes every annotated tag that points into the pushed history, so a v* release tag rides a branch push (review 2e939f2a.1). The one push that carries it by design is the GitLab mirror push of step 6b in .claude/commands/pr-merge.md, `git push gitlab refs/heads/main:refs/heads/main --follow-tags`; it copies only what GitHub's `main` holds, and `block_push_to_protected_branch` with the git-level `pre-push` hook (`githooks._mirror_push_refusal`) judge its URL and refs.
    if parsed.on("follow-tags") and not _mirror_push(parsed.operands):
        return "git push --follow-tags (the annotated v* release tags in the pushed history ride along)"
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


def _secrets_channel(env):
    """ "edge" when every channel signal on the command line names edge (`TARGET=edge`, `WORKER_NAME=edge-...`) and at least one is there; otherwise "stable", the fail-closed reading."""
    target = env.get("TARGET")
    worker = env.get("WORKER_NAME")
    if target is None and worker is None:
        return "stable"
    if target is not None and target != "edge":
        return "stable"
    if worker is not None and not worker.startswith("edge-"):
        return "stable"
    return "edge"


def _account_target(rest):
    """The `ARG_TARGET` `deploy_account` ends up with, read by its own parser's rules (`rediacc_ci.core.common.parse_args`, common.sh's twin), or "". That parser takes no prefix, so `--tar` is a different key; but it folds the key (`--TARGET`, `--Target` set `ARG_TARGET` too), a bare `--key` with no next word, or with a next word starting with `--`, stores "true", and the last store wins (review 7f22f490.2). Each of those reads production when the exact last `--target v` names edge."""
    target = ""
    k = 0
    while k < len(rest):
        word = rest[k]
        if not word.startswith("--"):
            k += 1
            continue
        flag, eq, value = word.partition("=")
        step = 1
        if not eq:
            if k + 1 < len(rest) and not rest[k + 1].startswith("--"):
                value, step = rest[k + 1], 2
            else:
                value = "true"
        if flag[2:].replace("-", "_").upper() == "TARGET":
            target = value
        k += step
    return target


def _account_channel(rest):
    target = _account_target(rest)
    return "edge" if target == "edge" else "stable"


def _prefix_option(args, name):
    """The last value an argparse option `name` takes in `args`, spelled in full or as any prefix of at least `--x` (`--tar eu`, `--targ=eu`), or "".
    argparse accepts a unique prefix by default (`allow_abbrev`), and `deploy_proxy`/`console_executor` keep that default (review 2e939f2a.2).
    NO AMBIGUITY CHECK IS MADE (review 7f22f490.1), and none is needed while no other long option of either parser starts with `--t`, which makes every prefix from `--t` up unique to `--target`; the harness reads both parsers' `add_argument` lines and fails when one does. Were a second `--t...` option added, an ambiguous prefix would make argparse exit before any deploy: reading it as `--target` could then admit a run that publishes nothing, never one that publishes stable.
    `account_secrets_local` parses exact words and exits 2 on any other, so a prefix there deploys nothing either."""
    found = ""
    for k, word in enumerate(args):
        if word == "--":
            break
        spelled, eq, value = word.partition("=")
        if len(spelled) < 3 or not spelled.startswith("--") or not name.startswith(spelled):
            continue
        if eq:
            found = value
        elif k + 1 < len(args):
            found = args[k + 1]
    return found


def _target_channel(rest):
    target = _prefix_option(rest, "--target")
    return "edge" if target in EDGE_TARGETS else "stable"


def _module_publish(module, rest, root, env):
    """`(kind, what, note)` for a run of one publish module with arguments `rest` and command-line environment `env`."""
    if _asks_help(rest, ("--help", "-h")) and _declares_help(root, module):
        return "", "", ""
    if "--dry-run" in rest and _declares_dry_run(root, module):
        return "", "", ""
    if module in STEP_MODULES:
        return "refuse", "python3 -m %s (a step of the release entry)" % module, ""
    if module in EDGE_MODULES:
        return "", "", ""
    if module in STABLE_MODULES:
        return "ask", "python3 -m %s (stable)" % module, ""
    if module == ACCOUNT_MODULE:
        side = _account_channel(rest)
    elif module in TARGET_MODULES:
        side = _target_channel(rest)
    else:
        side = _secrets_channel(env)
    if side == "edge":
        return "", "", ""
    return "ask", "python3 -m %s (a stable target)" % module, ""


def _wrangler_publish(args):
    """`(kind, what, note)` for a `wrangler` run: a publish on a stable config needs a proven ask, one on an edge, bench or preview config is refused for its module."""
    words = _positionals(args, WRANGLER_VALUE_OPTIONS)
    sub = words[0] if words else ""
    if sub == "pages" and words[1:2] and words[1] in WRANGLER_PAGES_PUBLISH:
        return "refuse", "wrangler pages %s (publishes a Pages site)" % words[1], ""
    publishes = sub in WRANGLER_PUBLISH or (sub == "versions" and words[1:2] == ["deploy"])
    if not publishes or "--dry-run" in args:
        return "", "", ""
    verb = " ".join(words[:2] if sub == "versions" else [sub])
    config = _option(args, "--config") or _option(args, "-c") or "wrangler.toml"
    if _EDGE_CONFIG.search(_base(config.replace("\\", "/")).lower()):
        return (
            "refuse",
            "wrangler %s on %s (an edge or bench Worker deploys through its module)"
            % (verb, config),
            "",
        )
    return "ask", "wrangler %s on the stable config %s" % (verb, config), ""


def _asks_help(args, words=("--help",)):
    """Does a help flag (`words`) stand among the options (before any `--`) where it cannot be an option's value? A help run publishes nothing, but `docker buildx build --push -t --help .` and `gh release create v1 --notes --help` hand `--help` to `-t` and `--notes` and publish (review 7f22f490.3); `upload_to_r2 --channel --help` does the same. Without each tool's table of value options, a help word right after a bare option word (`-t`, `--notes`, `-qt`; not `--x=v`) is read as that option's value: a help run spelled that way is judged as a publish, the fail-closed side."""
    head = args[: args.index("--")] if "--" in args else args
    for k, word in enumerate(head):
        if word not in words:
            continue
        before = head[k - 1] if k else ""
        if not (before.startswith("-") and len(before) > 1 and "=" not in before):
            return True
    return False


def _declares_help(root, module):
    """Does the module honour a help flag at all? argparse does by default; a hand parser does when its source names `"--help"`. `promote_r2_to_stable` takes no argv and `deploy_account`/`deploy_www` store `--help` as one more key, so `--help` on them publishes as if it were absent."""
    path = os.path.join(str(root), ".ci", *module.split(".")) + ".py"
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except OSError:
        return False
    return "argparse.ArgumentParser(" in text or '"--help"' in text


def _short_values(args, letter):
    """Every value the shorthand `-<letter>` takes in `args`: apart (`-o v`), attached (`-ov`, `-o=v`), or closing a bundle of value-less shorthands (`-qov`). Measured on pflag's rule: the first value-taking letter of a bundle takes the rest of the word."""
    out = []
    for k, word in enumerate(args):
        if word == "--":
            break
        if not word.startswith("-") or word.startswith("--") or len(word) < 2:
            continue
        for j, char in enumerate(word[1:], start=1):
            if char not in DOCKER_SHORT_VALUES:
                continue
            if char == letter:
                rest = word[j + 1 :].removeprefix("=")
                if rest:
                    out.append(rest)
                elif k + 1 < len(args):
                    out.append(args[k + 1])
            break
    return out


def _bool_on(args, name):
    """Is the boolean `name` set, as `--name` or `--name=<anything but false/0>`?"""
    on = False
    for word in args:
        if word == "--":
            break
        if word == name:
            on = True
        elif word.startswith(name + "="):
            on = word[len(name) + 1 :].lower() not in ("false", "0")
    return on


def _compose_publish(name, args):
    """`(kind, what, note)` for the words after `docker compose` (or a `docker-compose` run)."""
    words = _positionals(args, COMPOSE_VALUE_OPTIONS)
    verb = words[0] if words else ""
    if verb in COMPOSE_PUSH_VERBS:
        return "refuse", "%s %s" % (name, verb), ""
    if verb == "build" and _bool_on(args, "--push"):
        return "refuse", "%s build --push" % name, ""
    return "", "", ""


def _docker_publish(name, args):
    if name in ("docker-compose", "podman-compose"):
        return _compose_publish(name, args)
    words = _positionals(args, DOCKER_VALUE_OPTIONS)
    if words[:1] == ["compose"]:
        return _compose_publish("%s compose" % name, args[args.index("compose") + 1 :])
    if any(tuple(words[: len(v)]) == v for v in DOCKER_PUSH_VERBS):
        return "refuse", "%s %s" % (name, " ".join(words[:2])), ""
    building = "build" in words[:2] or words[:1] == ["buildx"]
    outputs = [_option(args, "--output"), *_short_values(args, "o")]
    if building and (
        _bool_on(args, "--push") or any("type=registry" in o or "push=true" in o for o in outputs)
    ):
        return "refuse", "%s %s --push" % (name, " ".join(words[:2])), ""
    if words[:3] == ["buildx", "imagetools", "create"] and "--dry-run" not in args:
        return "refuse", "docker buildx imagetools create (writes a registry tag)", ""
    return "", "", ""


def _publish(run, where, root, env):
    """`(kind, what, note)` for one run: kind "refuse", "ask" (needs a proven RELEASE_ASKED), or "" (free, or not a publish)."""
    name = _base(run.name)
    args = list(run.argv)
    npm = _npm_run(run)
    if npm is not None and npm[0] == RELEASE_SCRIPT:
        return _entry_verdict(_channel(npm[1], npm=True), npm=True)
    module = _module(run, where)
    if module == RELEASE_MODULE:
        return _entry_verdict(_channel(_module_args(run), npm=False), npm=False)
    if _asks_help(args) and (name.startswith("wrangler") or name in ("gh", *DOCKER_NAMES)):
        return "", "", ""
    if name.startswith("wrangler"):
        return _wrangler_publish(args)
    if name == "gh":
        words = _positionals(args, ("-R", "--repo"))
        if words[:1] == ["release"] and words[1:2] and words[1] in GH_RELEASE_PUBLISH:
            return "refuse", "gh release %s" % words[1], ""
        return "", "", ""
    if name == "git":
        _globals, verb, rest = commit_policy.git_split(args)
        what = _pushes_release_tag(rest) if verb == "push" else ""
        return ("refuse", what, "") if what else ("", "", "")
    if name in DOCKER_NAMES:
        return _docker_publish(name, args)
    if module in PUBLISH_MODULES:
        return _module_publish(module, _module_args(run), root, env)
    return "", "", ""


def _judge(cmd, where_root, env, root, depth, found):
    """Append `(kind, what, note, env)` to `found` for every publish in `cmd`, wrappers and npm scripts followed."""
    if depth > MAX_DEPTH:
        found.append(("refuse", "a command nested more than %d levels deep" % MAX_DEPTH, "", env))
        return
    launcher_env = dict(env)
    for run in shellscan.every_run(cmd):
        where = _join(where_root, run.cwd or "")
        # A command `npx` or `find -exec` launches inherits the launcher's environment, which the walk lists on the launcher alone: `RELEASE_ASKED=... npx wrangler deploy` carries the ask to wrangler.
        merged = dict(launcher_env if run.launch is not None else env)
        merged.update(run.env)
        if run.launch is None:
            launcher_env = merged
        inner = _wrapped(run, where)
        if inner is not None:
            _judge(inner, where, merged, root, depth + 1, found)
            continue
        kind, what, note = _publish(run, where, root, merged)
        if kind:
            found.append((kind, what, note, merged))
            continue
        npm = _npm_run(run)
        # The entry is judged by name above, on the words npm hands it; following its script text too would judge it twice.
        if npm is None or npm[0] == RELEASE_SCRIPT:
            continue
        script, args, npm_args = npm
        tail = args[args.index("--") + 1 :] if "--" in args else []
        for home in _npm_dirs(where, npm_args):
            text = _npm_script_text(home, script)
            if text:
                _judge(
                    ("%s %s" % (text, shlex.join(tail))).strip(),
                    home,
                    merged,
                    root,
                    depth + 1,
                    found,
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
    found: list[tuple[str, str, str, dict[str, str]]] = []
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
