"""Refuse a second local tree of this origin, typed into the Bash tool.

WHY. Operator ruling, ASKED:2026-11-04T10:15Z, "Refuse them": a /tmp clone of this origin. A clone escapes the one-branch rule, because `block_second_branch` skips any repository outside the checkout, and nothing follows or collects it. `git clone` yields no branch creation, so that guard's loop never reaches it, which is why this is a sibling (agent/plans/PLAN-worktree-lease.md, Design 6).

THE TARGET DOES NOT MATTER. `git clone <ours> ~/x` is the same second tree as /tmp/x, and a /tmp-only test is refused by moving one directory over.

WHAT COUNTS AS OURS. A source normalizing to the origin or mirror of the console or a submodule: the static table below, plus this checkout's remotes, `.gitmodules` and module configs, so a new submodule needs no edit. A local path in this checkout or its git directory. A local repository with a remote that is any of these, one hop or more away, since a clone of a clone is the same tree.

THE SAME ACT. `gh repo clone`, `gh repo fork --clone`, and outside this checkout (or in a repository the same command inits) `git fetch`, `git pull`, `git remote add|set-url` and `git submodule add` naming ours. Inside this checkout those verbs are ordinary work.

STRUCTURALLY UNTOUCHED. ci:quick's clone, the release clone, `renet-execution`, `gate_model`, `obs_ceph_autobump` and every test harness run `git clone` in a subprocess no PreToolUse hook sees. A clone over `ssh`, `docker exec` or `rdc term` makes no tree on this machine and is not walked.

PROGRAM TEXT. `block_worktree_add.interpreter_programs` hands over what a command gives an interpreter: every string of a program the command line holds is judged. A script run by path, or read on stdin from a file, is read too, and a tracked one unchanged from HEAD is not. In a Python script by path only what a call is handed and argv-shaped lists count, so a table of commands in a test is data. A script the hook cannot read is `block_worktree_add`'s refusal, earlier in the chain, and is refused here too when the command spells a clone verb as a word or names an untracked or changed file whose text does; `quick-clone.ts` is a name, not a verb (#82053b3b).

OUT OF REACH, stated: a string built at run time. A source the walk cannot expand is judged only when the command also names a way to ours (`rev-parse --show-toplevel`, `pwd`, an origin), because `git clone "$T/a"` over a fresh `mktemp` is a fixture. A plain `cp -a` of the tree, `parallel`, and config set outside the command line are not read either.

A diagnosis that needs a pristine clone is the operator's `!`, which never reaches this hook.
"""

import ast
import glob
import importlib.util
import os
import posixpath
import re
import shlex
import urllib.parse

from rediacc_hooks import commit_policy, hookio, shellscan, wellknown
from rediacc_hooks.guards import block_worktree_add as programs

CHAIN = "pre-bash"
OWN_SUITE = True
ORDER = 67

# The mirror host is `githooks.MIRROR_HOST`, the one place it is typed; loaded BY FILE like `block_push_to_protected_branch` does.
_GITHOOKS_SPEC = importlib.util.spec_from_file_location(
    "rediacc_hooks._githooks_origin_clone",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "git", "githooks.py"),
)
if _GITHOOKS_SPEC is None or _GITHOOKS_SPEC.loader is None:
    raise ImportError("block_origin_clone: git/githooks.py is missing")
githooks = importlib.util.module_from_spec(_GITHOOKS_SPEC)
_GITHOOKS_SPEC.loader.exec_module(githooks)

# The verdict itself. With it gone every spelling of a clone goes through.
DEFECT = ("if reason:", "if False:")

REPOS = ("console", "renet", "account", "elite", "homebrew-tap")
STATIC_ORIGINS = frozenset(
    {("github.com", "rediacc/%s" % name) for name in REPOS}
    | {(githooks.MIRROR_HOST, "rediacc-org/github/%s" % name) for name in REPOS}
)
HOST_ALIASES = {"ssh.github.com": "github.com", "www.github.com": "github.com"}
LOOPBACK = frozenset(("localhost", "127.0.0.1", "::1"))
# A submodule's directory may be empty or absent in a partial checkout, and the git directory holds the module stores.
ALWAYS_OURS = frozenset((".git", "private"))
MAX_HOPS = 3

CLONE_SHORT_VALUES = frozenset("obucj")
CLONE_LONG_VALUES = frozenset(
    (
        "template",
        "reference",
        "reference-if-able",
        "origin",
        "branch",
        "revision",
        "upload-pack",
        "depth",
        "shallow-since",
        "shallow-exclude",
        "separate-git-dir",
        "ref-format",
        "config",
        "server-option",
        "filter",
        "bundle-uri",
        "jobs",
    )
)
# `git clone -h`, git 2.53.0: the flags, for git's unique-prefix rule.
CLONE_LONG_FLAGS = frozenset(
    (
        "verbose",
        "quiet",
        "progress",
        "reject-shallow",
        "no-checkout",
        "checkout",
        "bare",
        "mirror",
        "local",
        "no-hardlinks",
        "hardlinks",
        "shared",
        "recurse-submodules",
        "recursive",
        "dissociate",
        "single-branch",
        "tags",
        "shallow-submodules",
        "ipv4",
        "ipv6",
        "also-filter-submodules",
        "remote-submodules",
        "sparse",
        "help",
    )
)
GH_VALUE_FLAGS = frozenset(
    ("-u", "--upstream-remote-name", "--remote-name", "--org", "--fork-name")
)

URL_FORM = re.compile(r"^([A-Za-z][A-Za-z0-9+.-]*)://([^/]*)(/.*)?$")
SCP_FORM = re.compile(r"^(?:[^@/:]+@)?([^/:]+):(.*)$")
GH_OWNER_REPO = re.compile(r"^[\w.-]+/[\w.-]+$")
GH_HOST_OWNER_REPO = re.compile(r"^([\w-]+(?:\.[\w-]+)+)/([\w.-]+/[\w.-]+)$")
INSTEAD_OF = re.compile(r"^url\.(.+)\.insteadof=(.*)$", re.IGNORECASE)


def toplevel_sub():
    """The `$(...)` spelling of a path query, matched whole so the walk can substitute the root for it."""
    return re.compile(
        r"\$\(git(?: -C \S+)? rev-parse --(?:show-toplevel|show-superproject-working-tree|git-dir"
        r"|git-common-dir|absolute-git-dir)\)"
    )


# A source the walk cannot expand is judged only beside one of these.
NAMES_A_WAY_TO_OURS = re.compile(
    r"rev-parse[^;&|\n]*--(?:show-toplevel|show-superproject-working-tree|git-dir|git-common-dir"
    r"|absolute-git-dir)|\bpwd\b|\bPWD\b|\bOLDPWD\b|\bCLAUDE_PROJECT_DIR\b"
    r"|rediacc/(?:console|renet|account|elite|homebrew-tap)\b|rediacc-org/github/",
    re.IGNORECASE,
)
ARGV_GIT = re.compile(
    r"""['"]git['"][\s,\[({:\w]*?['"](clone|fetch|pull)['"]((?:\s*,\s*['"][^'"]*['"])*)"""
)
PLAIN_NOISE = re.compile(r"[\"'\\]")
SPELLABLE = ("clone", "fetch", "pull", "remote", "submodule")
# A verb as a word: bounded by anything but a filename character, so `quick-clone.ts`, `ci-quick-clones/` and `clone_d1.py` are names, not verbs. Two dashed spellings are verbs too, for every verb in SPELLABLE: after `--` (`gh repo fork --clone`, and so `--remote`, `--pull`) and after `git-` (git's own executables, `git-clone`, `git-fetch`, `git-pull`, `git-remote`, `git-submodule`). Only a run the hook cannot judge reads this, so the wider reading is the safe one: each `git-<verb>` is the same act as `git <verb>`, and the cost of the rest is a refusal of a script that could not be read anyway (review 97b8666f.1).
# Each dashed prefix starts at a word boundary too, so `digit-clone`, `legit-pull` and `foo--fetch` are names while `/usr/lib/git-core/git-pull` still counts (review 91768330.1).
VERB_WORD = re.compile(r"(?<![\w.-])(?:--|git-)?(?:%s)(?![\w.-])" % "|".join(SPELLABLE))
OUTSIDE_VERBS = frozenset(("fetch", "pull", "remote", "submodule"))

MESSAGE = (
    "BLOCKED: %s\n"
    "\n"
    "Operator ruling ASKED:2026-11-04T10:15Z: a clone of this origin is refused, in /tmp and\n"
    "anywhere else, because a second tree escapes the one-branch rule and nothing follows or\n"
    "collects it. Work in this checkout. A separate tree comes from `./run.sh worktree lease`.\n"
    "CI's object set is `git rev-list --objects HEAD`, with no clone (docs/agent-reference/TRAPS.md).\n"
    "A diagnosis that really needs a pristine clone is the operator's `!`, which bypasses this hook.\n"
)


def _could_spell(text):
    bare = PLAIN_NOISE.sub("", text)
    return any(word in bare for word in SPELLABLE)


def _canonical(host, path):
    host = host.lower().rstrip(".")
    host = HOST_ALIASES.get(host, host)
    path = posixpath.normpath("/" + urllib.parse.unquote(path)).strip("/").lower()
    return host, path.removesuffix(".git")


def url_parts(text):
    """`(host, path)` for a url or scp form, `("", path)` for a `file:` url, None for anything else."""
    found = URL_FORM.match(text)
    if found:
        scheme, authority, path = found.groups()
        if scheme.lower() == "file":
            return "", path or "/"
        host = authority.rsplit("@", 1)[-1]
        host = host[1:].split("]", 1)[0] if host.startswith("[") else host.split(":", 1)[0]
        return host, path or ""
    found = SCP_FORM.match(text)
    return (found.group(1), found.group(2)) if found else None


def gh_parts(text):
    """`url_parts`, plus what `gh repo clone` alone accepts: OWNER/REPO and HOST/OWNER/REPO."""
    if GH_OWNER_REPO.match(text):
        return "github.com", text
    found = GH_HOST_OWNER_REPO.match(text)
    return (found.group(1), found.group(2)) if found else url_parts(text)


def clone_source(words):
    """The repository operand of the words after `git clone`, by git's option parse, or None."""
    k = 0
    while k < len(words):
        word = words[k]
        if word in ("--", "--end-of-options"):
            return words[k + 1] if k + 1 < len(words) else None
        if word.startswith("--"):
            name = word[2:].split("=", 1)[0]
            if "=" not in word and _long_takes_value(name):
                k += 1
        elif word.startswith("-") and len(word) > 1:
            for pos, letter in enumerate(word[1:], 1):
                if letter in CLONE_SHORT_VALUES:
                    if pos == len(word) - 1:
                        k += 1
                    break
        else:
            return word
        k += 1
    return None


def _long_takes_value(name):
    if name in CLONE_LONG_VALUES:
        return True
    if name in CLONE_LONG_FLAGS or name.startswith("no-"):
        return False
    known = CLONE_LONG_VALUES | CLONE_LONG_FLAGS
    matches = [candidate for candidate in known if candidate.startswith(name)]
    return len(matches) == 1 and matches[0] in CLONE_LONG_VALUES


def gh_source(words):
    """The repository operand of the words after `gh repo clone` or `gh repo fork`, or None."""
    k = 0
    while k < len(words):
        word = words[k]
        if word == "--":
            return None
        if word in GH_VALUE_FLAGS:
            k += 1
        elif not word.startswith("-"):
            return word
        k += 1
    return None


def _operands(words):
    return [word for word in words if word and not word.startswith("-")]


def _words(run_):
    """The run's words as bash hands them over, a word the walk cannot expand left as typed."""
    argv = list(run_.argv)
    expanded = run_.xargv
    if expanded is None:
        return argv
    if len(expanded) == len(argv):
        return [
            typed if shellscan._UNRESOLVED in known else known
            for typed, known in zip(argv, expanded, strict=True)
        ]
    return argv if any(shellscan._UNRESOLVED in word for word in expanded) else list(expanded)


class World:
    """What one event judges against. Git is asked only once a clone or fetch has been found."""

    def __init__(self, ev, cmd):
        self.root = ev.project_dir
        self.base = ev.field("cwd") or self.root
        self.home = ev.env("HOME")
        self.cmd = cmd
        self.text = cmd
        self._common = None
        self._origins = None

    def common(self):
        if self._common is None:
            got = commit_policy.git(
                ["rev-parse", "--path-format=absolute", "--git-common-dir"],
                cwd=self.root,
                foreign=True,
            )
            self._common = got or ""
        return self._common

    def origins(self):
        if self._origins is None:
            found = set(STATIC_ORIGINS)
            gitmodules = os.path.join(self.root, ".gitmodules")
            texts = [_remote_lines(self.root), _config_urls(gitmodules, "submodule")]
            if self.common():
                pattern = os.path.join(self.common(), "modules", "**", "config")
                texts.extend(_config_urls(c, "remote") for c in glob.glob(pattern, recursive=True))
            for text in texts:
                for line in text.splitlines():
                    parts = url_parts(line.split(" ", 1)[-1])
                    if parts and parts[0]:
                        found.add(_canonical(*parts))
            self._origins = found
        return self._origins

    def is_place_of_ours(self, real):
        """Is the resolved path this checkout, its git directory, or a path in them?"""
        common = self.common()
        if common and commit_policy.is_inside(real, common):
            return True
        if not commit_policy.is_inside(real, self.root):
            return False
        rel = os.path.relpath(real, os.path.realpath(self.root))
        first = rel.split(os.sep, 1)[0]
        return rel == "." or first in ALWAYS_OURS or os.path.exists(os.path.join(self.root, first))

    def is_source_of_ours(self, real):
        """Does a clone SOURCE name this checkout or its git directory? A place test is too wide for a source: from a run standing below the root (a package directory, a lease under `.claude/worktrees/`) every bare word resolves under an existing top-level entry, so `fetch` read as a source was "ours" (#11ad5926). git clones only a source that exists, so a source must exist, apart from a path under `.git` and an absent submodule directory (`private/<name>`). A bare absent `private` is not one: it is a plain directory of the superproject, never a repository, so git clones nothing from it (review c804bc45.2)."""
        common = self.common()
        if common and commit_policy.is_inside(real, common):
            return True
        if not commit_policy.is_inside(real, self.root):
            return False
        if os.path.exists(real):
            return True
        rel = os.path.relpath(real, os.path.realpath(self.root))
        parts = rel.split(os.sep)
        # In a lease `.git` is a file, so `.git/modules/...` names the module store only by its spelling.
        return parts[0] == ".git" or (parts[0] == "private" and len(parts) == 2)


def _config_urls(config, section):
    if not os.path.isfile(config):
        return ""
    argv = ["config", "--file", config, "--get-regexp", r"^%s\..*\.url$" % section]
    return commit_policy.git(argv, foreign=True) or ""


def _remote_lines(path):
    if not os.path.isdir(path):
        return ""
    return (
        commit_policy.git(
            ["config", "--local", "--get-regexp", r"^remote\..*\.url$"], cwd=path, foreign=True
        )
        or ""
    )


def _remotes(path):
    """`{name: url}` for the repository at `path`, empty for none."""
    out = {}
    for line in _remote_lines(path).splitlines():
        key, _, url = line.partition(" ")
        out[key[len("remote.") : -len(".url")]] = url
    return out


def _expand_typed(word, world, directory):
    """A word the walk could not expand, with what this event knows filled in; None if a part is still unknown."""
    text = toplevel_sub().sub(lambda _: world.root, word)
    for name, value in (
        ("HOME", world.home),
        ("PWD", directory),
        ("CLAUDE_PROJECT_DIR", world.root),
    ):
        text = text.replace("${%s}" % name, value).replace("$%s" % name, value)
    text = text.replace("$(pwd)", directory).replace("`pwd`", directory)
    return None if "$" in text or "`" in text else text


def _judge_local(path, directory, world, hops):
    real = os.path.realpath(os.path.join(directory, path))
    if world.is_source_of_ours(real):
        return "`%s` is a path in this checkout or its git directory" % path
    if hops >= MAX_HOPS:
        return None
    for url in _remotes(real).values():
        why = _judge(url, real, world, hops + 1)
        if why:
            return "`%s` is a local repository with a remote of ours: %s" % (path, why)
    return None


def _judge(word, directory, world, hops=0, parts_of=url_parts):
    """Why `word`, read as a repository from `directory`, is ours, or None. A word still unknown is judged by what the command names."""
    if not word:
        return None
    if "$" in word or "`" in word:
        word = _expand_typed(word, world, directory)
        if word is None:
            if NAMES_A_WAY_TO_OURS.search(world.text):
                return "the source is built at run time, by a command that names a way to ours"
            return None
    if word == "~" or word.startswith("~/"):
        word = (world.home or "~") + word[1:]
    # git reads an existing directory as a path before it reads a colon as a host.
    if not URL_FORM.match(word) and os.path.exists(os.path.join(directory, word)):
        return _judge_local(word, directory, world, hops)
    parts = parts_of(word)
    if parts is None:
        return _judge_local(word, directory, world, hops)
    host, path = parts
    if not host or host.lower() in LOOPBACK:
        return _judge_local("/" + path.lstrip("/"), directory, world, hops)
    if _canonical(host, path) in world.origins():
        return "`%s` is an origin or mirror of this repository" % word
    return None


def _rewrite(source, before_verb):
    """`source` under the `-c url.<base>.insteadOf=<prefix>` the command line sets."""
    for k, word in enumerate(before_verb[:-1]):
        if word == "-c":
            found = INSTEAD_OF.match(before_verb[k + 1])
            if found and source.startswith(found.group(2)):
                return found.group(1) + source[len(found.group(2)) :]
    return source


def _fed_words(run_):
    """What xargs hands the command: every word of its feed, the producer's name included, read as a possible source."""
    if not run_.feed or "xargs" not in run_.via:
        return []
    try:
        return shlex.split(run_.feed)
    except ValueError:
        return run_.feed.split()


def _git_dir_of(run_, words, verb_at, directory):
    """Where git really acts: `--git-dir`, or `GIT_DIR`, else the run's directory."""
    chosen = (run_.env or {}).get("GIT_DIR")
    before = words[:verb_at]
    for k, word in enumerate(before):
        if word.startswith("--git-dir="):
            chosen = word.split("=", 1)[1]
        elif word == "--git-dir" and k + 1 < len(before):
            chosen = before[k + 1]
    if not chosen:
        return os.path.realpath(directory)
    return os.path.realpath(os.path.join(directory, chosen))


def _init_targets(runs, world):
    """Every directory the command inits. A repository made here is a second tree wherever it sits."""
    out = set()
    for run_ in runs:
        if run_.git_sub != "init":
            continue
        words = _words(run_)
        at, _ = shellscan._git_verb_at(words)
        directory = commit_policy.run_dir(run_, world.base)
        names = _operands(words[at + 1 :]) if at is not None else []
        for name in names or ["."]:
            if "$" not in name and "`" not in name:
                out.add(os.path.realpath(os.path.join(directory, name)))
    return out


def _judge_git(run_, world, inits):
    words = _words(run_)
    verb_at, _ = shellscan._git_verb_at(words)
    if verb_at is None:
        return None
    verb, after = run_.git_sub, words[verb_at + 1 :]
    directory = commit_policy.run_dir(run_, world.base)
    if verb == "clone":
        before = words[:verb_at]
        source = clone_source(after)
        candidates = ([_rewrite(source, before)] if source else []) + _fed_words(run_)
        for candidate in candidates:
            why = _judge(candidate, directory, world)
            if why:
                return "`git clone`: %s." % why
        return None
    if verb not in OUTSIDE_VERBS:
        return None
    if verb == "remote" and not (after and after[0] in ("add", "set-url")):
        return None
    if verb == "submodule" and not (after and after[0] == "add"):
        return None
    place = _git_dir_of(run_, words, verb_at, directory)
    if verb in ("remote", "submodule"):
        operands = _operands(after[1:])
    else:
        operands = _operands(after) or ["origin"]
    if world.is_place_of_ours(place) and place not in inits:
        return None
    named = _remotes(place) if os.path.isdir(place) else {}
    for operand in operands:
        target = named.get(operand, operand)
        why = _judge(target, directory, world)
        if why:
            return "`git %s` outside this checkout makes the same second tree: %s." % (verb, why)
    return None


def _judge_gh(run_, world):
    words = _words(run_)
    forks_a_clone = words[:2] == ["repo", "fork"] and any(
        word == "--clone" or (word.startswith("--clone=") and not word.endswith("false"))
        for word in words[2:]
    )
    if not (words[:2] == ["repo", "clone"] or forks_a_clone):
        return None
    source = gh_source(words[2:])
    if not source:
        return None
    directory = commit_policy.run_dir(run_, world.base)
    why = _judge(source, directory, world, parts_of=gh_parts)
    return "`gh repo %s`: %s." % (words[1], why) if why else None


def _sequence_nodes(tree):
    """`programs._sequences`, each list paired with the node it came from: a list, tuple or set literal, or a call (its positional arguments)."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            yield node, [programs._const_str(e) for e in node.elts]
        elif isinstance(node, ast.Call) and node.args:
            yield node, [programs._const_str(a) for a in node.args]


# Builtins that run no process and call nothing they are handed, so an argument they take is not yet an argv. `map` and `filter` call their first argument, and `sorted`, `min` and `max` call a `key=`, so those are not here or stop counting once a `key` is passed.
PURE_BUILTINS = frozenset(
    (
        "print",
        "len",
        "repr",
        "str",
        "list",
        "tuple",
        "sorted",
        "set",
        "frozenset",
        "sum",
        "min",
        "max",
        "any",
        "all",
        "enumerate",
        "zip",
        "isinstance",
        "bool",
        "type",
        "id",
    )
)


def _rebound_names(tree):
    """Every name the program binds itself: a def, a class, an import, an argument or an assignment target. A pure builtin rebound so is the program's own callable."""
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(node.name)
        elif isinstance(node, ast.alias):
            out.add((node.asname or node.name).split(".", 1)[0])
        elif isinstance(node, ast.arg):
            out.add(node.arg)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            out.add(node.id)
    return out


def _bindings(tree):
    """`{name: [value, ...]}` for every plain, annotated, augmented or walrus assignment to a bare name."""
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            pairs = [(target, node.value) for target in node.targets]
        elif (
            isinstance(node, (ast.AnnAssign, ast.AugAssign, ast.NamedExpr))
            and node.value is not None
        ):
            pairs = [(node.target, node.value)]
        else:
            continue
        for target, value in pairs:
            if isinstance(target, ast.Name):
                out.setdefault(target.id, []).append(value)
    return out


def _handed_sequences(tree):
    """The ids of every call that can run something, and of every list, tuple or set literal such a call is handed.

    A call counts unless its callee is a bare pure builtin the program does not rebind (`PURE_BUILTINS`): `print(SPELLABLE)` or `len(SPELLABLE)` hands nothing (review 21761c0f.1). What a counting call is handed is its whole argument expressions, through a pure builtin, a subscript or an operator inside them (`sh("git", *ARGV)`, `run_git(list(ARGV))`, `subprocess.run(["git", *ARGV])`, review c804bc45.1). A name reached so hands every literal bound to it, and so does every name its bindings mention (`X = list(ARGV)` then `run_git(X)`), until nothing new is reached. Scope is ignored, so a name that reaches such a call anywhere hands every literal bound to it anywhere.
    """
    sequences = (ast.List, ast.Tuple, ast.Set)
    pure = PURE_BUILTINS - _rebound_names(tree)
    out, names = set(), set()

    def hand(value):
        for node in ast.walk(value):
            if isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, sequences):
                out.add(id(node))

    def runs_something(call):
        func = call.func
        if not (isinstance(func, ast.Name) and func.id in pure):
            return True
        # A `**mapping` expansion can carry any keyword, `key=` included (`sorted(x, **{"key": f})`), so a pure builtin
        # called with one is not judged pure (review 4c1ac1fc.1).
        if any(k.arg is None for k in call.keywords):
            return True
        return func.id in ("sorted", "min", "max") and any(k.arg == "key" for k in call.keywords)

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and runs_something(node):
            out.add(id(node))
            for arg in list(node.args) + [keyword.value for keyword in node.keywords]:
                hand(arg)
    bindings, done = _bindings(tree), set()
    while names - done:
        name = (names - done).pop()
        done.add(name)
        for value in bindings.get(name, ()):
            hand(value)
    return out


def _python_reasons(code, world, depth, by_path):
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return _text_reason(code, world, depth)
    strings = []
    for node in ast.walk(tree):
        if not by_path:
            value = programs._const_str(node)
            if value is not None:
                strings.append(value)
        elif isinstance(node, ast.Call):
            for arg in list(node.args) + [keyword.value for keyword in node.keywords]:
                pieces = programs._pieces(arg)
                if pieces != [None]:
                    strings.append("".join(" " if p is None else p for p in pieces))
    if not by_path:
        strings.extend(programs._python_folds(tree, False))
    for text in dict.fromkeys(strings):
        why = _walk(text, world, depth + 1)
        if why:
            return why
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and programs._callee(node) in programs.EVALUATORS
            and node.args
        ):
            program = programs._const_str(node.args[0])
            if program is not None and depth < programs.MAX_PROGRAM_DEPTH:
                why = _python_reasons(program, world, depth + 1, by_path)
                if why:
                    return why
    handed = _handed_sequences(tree)
    for node, seq in _sequence_nodes(tree):
        if not seq:
            continue
        # A helper taking the verb's argv: `sh('git', ['clone', ...])`. Only a sequence a call that can run something is handed, directly or through the name it is bound to, reads so; a literal no such call takes, like `SPELLABLE = ("clone", "fetch", ...)` printed or counted, is a table of words, not a git argv (#11ad5926, c804bc45.1, 21761c0f.1).
        verb_first = seq[0] in ("clone", "fetch", "pull") and id(node) in handed
        words = ["git", *seq] if verb_first else seq
        if words[0] == "git" and any(e is not None for e in words[1:]):
            why = _walk(programs._joined(words), world, depth + 1)
            if why:
                return why
    return None


def _text_reason(code, world, depth):
    for literal in programs._text_literals(code):
        why = _walk(literal, world, depth + 1)
        if why:
            return why
    for found in ARGV_GIT.finditer(code):
        words = ["git", found.group(1)]
        words += [
            next(g for g in m.groups() if g is not None)
            for m in programs.LITERAL.finditer(found.group(2))
        ]
        why = _walk(" ".join(shlex.quote(word) for word in words), world, depth + 1)
        if why:
            return why
    return None


def _program_reason(family, code, world, depth, by_path=False):
    if family == "python":
        return _python_reasons(code, world, depth, by_path)
    if family == "shell":
        return _walk(code, world, depth + 1)
    return _text_reason(code, world, depth)


def _shell_script_text(run_, world):
    """`(text, kind)` for a shell script run by path, the rules of `shellscan.interpreter_program`: what the command wrote there, else the file, a tracked unchanged one exempt."""
    path = programs._shell_script_path(run_, world.cmd, world.base)
    if not path:
        return None, None
    target = shellscan._script_path(path, run_.cwd, world.base)
    written = shellscan._written_scripts(world.cmd, run_, world.base)
    if target in written:
        return (written[target], "file") if written[target] is not None else (None, "unjudgeable")
    return _script_file(target)


def _script_file(target):
    reason, text = programs._stdin_file(target)
    if reason or not text or text.startswith("\x7fELF") or not _could_spell(text):
        return None, None
    return (None, None) if programs._tracked_unchanged(target) else (text, "file")


def _names_a_verb(cmd, world):
    """Does `cmd` spell a clone verb as a word, or name a readable, untracked-or-changed file whose text does?

    The whole text is read, not only the runs' words, because a verb written into the unread script sits in a heredoc body, a `sed` expression or an assignment as often as in an argv. A file the command names is read the way a script run by path is: a source copied or `cat`'d into the unread script carries its verbs under any name, and a tracked unchanged one is exempt.
    """
    if VERB_WORD.search(PLAIN_NOISE.sub("", cmd)):
        return True
    try:
        words = shlex.split(cmd)
    except ValueError:
        words = cmd.split()
    for word in dict.fromkeys(words):
        if "$" in word or "`" in word or word.startswith("-"):
            continue
        target = os.path.join(world.base, os.path.expanduser(word))
        if not os.path.isfile(target):
            continue
        text = _script_file(target)[0]
        if text and VERB_WORD.search(PLAIN_NOISE.sub("", text)):
            return True
    return False


def _by_path_reason(cmd, world, depth):
    if not (shellscan.PROGRAM_PREFILTER.search(cmd) or programs.SHELL_SCRIPT_PREFILTER.search(cmd)):
        return None
    for run_ in shellscan.every_run(cmd):
        if programs._reads_stdin_operand(run_):
            continue
        text, kind = shellscan.interpreter_program(run_, cmd, world.base)
        family = programs._interpreter_name(run_.name) or programs._interpreter_name(
            shellscan.shebang_interpreter(run_, world.base) or ""
        )
        if kind not in ("file", "unjudgeable"):
            text, kind = _shell_script_text(run_, world)
            family = "shell"
        if kind == "unjudgeable" and _names_a_verb(cmd, world):
            return "this runs a script the hook cannot judge, and the command names a clone verb."
        if kind == "file" and text and _could_spell(text):
            why = _program_reason(family, text, world, depth, by_path=True)
            if why:
                return why
    return None


def _stdin_file_reason(family, word, world, depth):
    """A file fed to a stdin program, read in each directory a run of the command stands in."""
    if "\0" in word or word.startswith(("<(", ">(")) or programs._stdin_path(word):
        return None
    written = shellscan._written_scripts(world.cmd, None, world.base)
    directories = {None} | {run_.cwd for run_ in shellscan.every_run(world.cmd)}
    for directory in sorted(directories, key=lambda d: d or ""):
        target = shellscan._script_path(word, directory, world.base)
        text = written.get(target)
        if text is None:
            text = _script_file(target)[0]
        if text and _could_spell(text):
            why = _program_reason(family, text, world, depth, by_path=True)
            if why:
                return why
    return None


def _walk(cmd, world, depth=0):
    """Why the shell command `cmd` makes a second tree of ours, or None."""
    if not cmd or depth > programs.MAX_PROGRAM_DEPTH:
        return None
    # A one-word string in a program is a name, and reading it as a script run by path would judge any file a program merely opens.
    if depth > 0 and (not _could_spell(cmd) or len(cmd.split()) < 2):
        return None
    outer, world.text = world.text, cmd
    try:
        return _walk_text(cmd, world, depth)
    finally:
        world.text = outer


def _walk_text(cmd, world, depth):
    runs = shellscan.every_run(cmd)
    inits = None
    for run_ in runs:
        base = run_.name.rsplit("/", 1)[-1]
        why = None
        if base == "git" and run_.git_sub in OUTSIDE_VERBS | {"clone"}:
            if inits is None:
                inits = _init_targets(runs, world)
            why = _judge_git(run_, world, inits)
        elif base == "gh":
            why = _judge_gh(run_, world)
        if why:
            return why
    files: list[tuple[str, str, str]] = []
    for family, code in programs.interpreter_programs(cmd, files=files):
        if _could_spell(code):
            why = _program_reason(family, code, world, depth)
            if why:
                return why
    for family, kind, value in files:
        # An unread producer is `block_worktree_add`'s refusal, earlier in this chain.
        if kind == "file":
            why = _stdin_file_reason(family, value, world, depth)
            if why:
                return why
    return _by_path_reason(cmd, world, depth)


_GHO = wellknown.GH_ORIGIN
_CONSOLE = wellknown.GH_REPO
_RENET = wellknown.RENET_REPO
_MIRROR = githooks.MIRROR_HOST
EDGE_CASES = [
    ("the origin", f"git clone {_GHO}/{_CONSOLE}.git /tmp/x"),
    ("a submodule", f"git clone git@github.com:{_RENET}.git /tmp/x"),
    ("the mirror", f"git clone https://{_MIRROR}/rediacc-org/github/console.git /tmp/x"),
    ("gh", f"gh repo clone {_CONSOLE}"),
    ("a wrapper", f"sh -c 'git clone {_GHO}/{_CONSOLE} /tmp/x'"),
    (
        "init and fetch",
        f"git init /tmp/x && git -C /tmp/x fetch {_GHO}/{_CONSOLE}.git",
    ),
    (
        "program text",
        f"python3 -c \"import os; os.system('git clone {_GHO}/{_CONSOLE} /x')\"",
    ),
    ("control: a fixture", "git clone /tmp/fixture /tmp/y"),
    ("control: an unrelated url", "git clone https://example.invalid/a.git /tmp/y"),
    ("control: prose", f"echo git clone {_GHO}/{_CONSOLE}.git /tmp/x"),
    (
        "control: a heredoc body",
        f"cat > n.md <<'EOF'\ngit clone {_GHO}/{_CONSOLE}.git /tmp/x\nEOF",
    ),
]


def run(ev):
    cmd = ev.field("tool_input", "command")
    if cmd == "":
        return hookio.ALLOW
    reason = _walk(cmd, World(ev, cmd))
    if reason:
        ev.warn_raw(MESSAGE % reason)
        return hookio.DENY
    return hookio.ALLOW
