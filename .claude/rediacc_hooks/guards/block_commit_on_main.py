"""Refuse a commit on `main` unless it is a well-formed `[hotfix]`, and refuse `[hotfix]` anywhere else.

WHY. Operator ruling, 2026-09-25: "if we really need to fix some bugs on main then okay but otherwise we must follow the branch naming rules to open new branches if we're working on main." Work lands on the one `MMDD-N` branch in small reviewed commits; `main` takes a commit only for the main-only failure class of pr-merge step 5 (a job that failed on `main` never ran, or ran differently, on the PR's own run) or when the operator called it a hotfix in this task.

WHAT A HOTFIX CARRIES (the commit-policy plan in agent/plans, section 4.1, checked by `commit_policy.hotfix_ok`):

  * `[hotfix]` at the end of the subject;
  * a `Hotfix-Evidence:` trailer naming the red main run (id or actions/runs URL) or `ASKED:<ISO minute>`;
  * at most `hotfix_max_files` paths (5, decision 4), counted from the pathspec or, without one, from the index.

It needs no `PR-TASK:` trailer (`block_untagged_commit` stops asking on `main`), it is always reviewed (Z, operator ruling 1). Under the 2026-10-02 ruling `main` moves only through `gh pr merge --rebase --auto` or the guarded fast-forward fallback of the live branch (`block_push_to_protected_branch`); a commit made on `main` itself is neither, so that guard refuses its push from this tool, and it leaves the machine by a push outside it.

OFF `main` THE TAG IS REFUSED, so the audit stays clean: a `[hotfix]` on a feature branch would read as a reviewed-on-main commit to anyone scanning the log for them.

WHAT IS JUDGED. Every `git commit` bash would run in the command (a `sh -c` payload and an `eval` included), each against the branch of the repository it acts on: this checkout, or a submodule inside it through `cd`/`-C` (`git -C private/account commit` on account's `main` is refused like the console's). A repository outside this checkout (a `/tmp` fixture) is not this policy's business. The message is read in the three shapes `block_untagged_commit` established; one this guard cannot read on `main` is refused, because a hotfix it cannot see is not one it can admit. A `-F <file>` that an earlier clause of the same command writes is refused unread on any branch (`commit_policy.written_message_refusal`): its bytes on disk are an earlier command's, and reading them admitted a stale `[hotfix]` onto `main`.

WRITERS NEVER COMMIT IN THE MAIN CHECKOUT (section 3.2 of the commit-policy plan). The lead commits each writer's output once it has spot-checked it, so every git verb that creates a commit (`WRITER_VERBS`: `commit`, the landing verbs `cherry-pick`, `revert`, `merge`, `am`, `rebase`, `pull` and `commit-tree` with their no-commit forms, and the ref writers `fast-import`, `filter-branch`, `filter-repo` and `replay`, in any `-C`/`cd` spelling and in any submodule of this checkout) from a sub-agent is refused on any branch, unless its repository is a lease tree (`commit_policy.lease_root`), where the writer commits on the detached HEAD and the lead lands it. T0(a) settled how a sub-agent is recognised: PreToolUse fires for a sub-agent's Bash call (probed live 2026-10-04 from a writer: a `timeout 1 sleep 600` was refused by `block_long_sleep`), and the payload carries `agent_id` and `agent_type` only for a sub-agent, never on a main-loop call (measured 2026-08-09, `.claude/hooks/trapguard/dispatch.py`). There is no exemption (operator /ask 2026-10-04 declined one for `pr-babysitter`): a delegated `/pr-babysit bg` loop reports, and the lead commits. Before #60454abe only `commit` was judged, and a landing sub-agent ran `git -C private/renet cherry-pick` in the main checkout unrefused (2026-11-06). A sequencer's `--abort`/`--quit` and the read-only `--show-current-patch` create nothing and stay admitted.

THE VERB IS THE ONE GIT RUNS, NOT THE ONE TYPED (#6bb5e37a). Until then `git -c alias.cp=cherry-pick cp <sha>`, or `git cp` with `alias.cp` in the repository's config, created a commit from a sub-agent unrefused. `resolve` follows the typed verb through the command line's `-c`/`--config-env`/`GIT_CONFIG_*` and the configuration git reads where it runs (`-C` included), alias by alias up to `ALIAS_DEPTH`. Where it cannot read the answer (a `!shell` alias, an unreadable configuration, a chain past the cap, a name that is neither a command nor an alias, a `git config` naming an alias earlier in the same command, or any earlier clause that can write a file, such as `printf '[alias]...' >> .git/config`) a sub-agent in the main checkout is refused, never admitted unread. Lease and lead behave exactly as before.

THE GIT-LEVEL TWIN. `.claude/rediacc_hooks/git/commit-msg` enforces the same rule on every commit in a checkout whose `core.hooksPath` points there, including the operator's own terminal; that layer honours `COMMIT_POLICY_OK=1`, this one never does.
"""

import os
import shlex
import subprocess
import typing

from rediacc_hooks import commit_policy, hookio

CHAIN = "pre-bash"
OWN_SUITE = True
ORDER = 45

# The `main` arm is the guard. With it gone every commit on `main` passes, which is the drift the ruling exists to stop.
DEFECT = ('if branch == "main":', "if False:")

ENVS: list[tuple[str, dict[str, str], dict[str, str]]] = [
    ("main-branch", {"CLAUDE_PROJECT_DIR": "{FIXTURE:git-main}"}, {}),
    ("feature-branch", {"CLAUDE_PROJECT_DIR": "{FIXTURE:git-ahead}"}, {}),
]

HOTFIX = 'git commit -m "fix(ci): x [hotfix]\n\nHotfix-Evidence: 12345678" -- a.ts'


# Every git subcommand that writes a commit onto a ref. Their no-commit forms stay refused too (`cherry-pick -n`, `revert --no-commit`, `merge --squash`): each applies another commit's change to the main checkout, which is landing, and landing is the lead's (`WRITER_COMMIT`); `merge --no-commit` still fast-forwards HEAD. `fast-import`, `filter-branch`, `filter-repo` and `replay` write commits onto refs as well (review 547cb159.1). `stash` is not here: it writes no branch commit, and its own guard refuses it.
WRITER_VERBS = frozenset(
    (
        "commit",
        "cherry-pick",
        "revert",
        "merge",
        "am",
        "rebase",
        "pull",
        "commit-tree",
        "fast-import",
        "filter-branch",
        "filter-repo",
        "replay",
    )
)
# The sequencer flags that create no commit: leaving an operation, or reading its state.
NO_COMMIT_FLAGS = frozenset(("--abort", "--quit", "--show-current-patch"))
# The non-git commands that write no file of their own, so an alias read at hook time is still the one git reads after them. Any other command, and any of these with an output redirect, can write a git configuration file (`printf '[alias]...' >> .git/config`) and redefine a later alias (review 50ba07da.1), so it fails closed.
INERT_COMMANDS = frozenset(
    (
        ":",
        "[",
        "cat",
        "cd",
        "date",
        "echo",
        "false",
        "grep",
        "head",
        "ls",
        "popd",
        "printf",
        "pushd",
        "pwd",
        "sleep",
        "tail",
        "test",
        "true",
        "wc",
    )
)

WRITER_COMMIT = (
    "BLOCKED: a sub-agent (`%s`) is committing (`git %s`), and writers never commit.\n"
    "\n"
    "The lead commits each writer's output once it has spot-checked it (the\n"
    "commit-policy plan, section 3.1): a writer committing its own work commits an\n"
    "unchecked report, the no-amend rule makes undoing it a second commit, and\n"
    "parallel writers race on index.lock and HEAD.\n"
    "\n"
    "Leave the change in the tree and list every path it touched in the report.\n"
    "Landing a lease (`cherry-pick`, `merge`, `am`) is the lead's too: report the\n"
    "lines `./run.sh worktree land <id>` prints, and the lead runs them.\n"
)


# GIT RUNS A BUILTIN BEFORE AN ALIAS OF THE SAME NAME (`alias.*` in git-config(1): "aliases that hide existing Git commands are ignored except for deprecated commands"), and none of these is deprecated, so they never resolve through one and need no config read. A fast path only: a verb missing here is resolved, never admitted unread.
PLAIN_VERBS = frozenset(
    (
        "add",
        "apply",
        "bisect",
        "blame",
        "branch",
        "cat-file",
        "check-ignore",
        "checkout",
        "clone",
        "config",
        "describe",
        "diff",
        "fetch",
        "for-each-ref",
        "format-patch",
        "grep",
        "help",
        "init",
        "log",
        "ls-files",
        "ls-remote",
        "ls-tree",
        "merge-base",
        "mv",
        "notes",
        "push",
        "reflog",
        "remote",
        "reset",
        "restore",
        "rev-list",
        "rev-parse",
        "rm",
        "show",
        "shortlog",
        "stash",
        "status",
        "submodule",
        "switch",
        "symbolic-ref",
        "tag",
        "version",
        "worktree",
    )
)
# A chain longer than this is refused rather than followed: git stops a loop itself, and no honest alias chains this deep.
ALIAS_DEPTH = 10
# The global options that decide which configuration git reads, forwarded to the alias lookup. `-C` moves the directory instead.
CONFIG_OPTS = frozenset(("-c", "--config-env", "--git-dir", "--work-tree"))

ALIAS_UNREADABLE = (
    "BLOCKED: a sub-agent (`%s`) runs `git %s`, which this guard cannot resolve to a\n"
    "git verb, and writers never commit in the main checkout.\n"
    "\n"
    "  %s\n"
    "\n"
    "A git alias (`-c alias.<name>=...` or one in git config) can spell any of the\n"
    "commit-creating verbs, so a verb this guard cannot read through is refused rather\n"
    "than admitted unread. Run the git command the alias stands for, spelled out, so\n"
    "it is judged as typed.\n"
)


class Write(typing.NamedTuple):
    """One git invocation a sub-agent's command runs: `typed` is the verb as written, `verb` the one git performs after every alias, `via` the alias chain, `args` the verb's arguments after every expansion, `directory` where git runs, and `refusal` why the guard cannot read it ("" when it can)."""

    run: typing.Any
    typed: str
    verb: str
    via: tuple
    args: tuple
    directory: str
    refusal: str


def _config_opts(opts):
    """The configuration-deciding words among a git argv's global options."""
    out = []
    k = 0
    while k < len(opts):
        arg = opts[k]
        if arg in CONFIG_OPTS and k + 1 < len(opts):
            out += [arg, opts[k + 1]]
            k += 2
            continue
        if arg.split("=", 1)[0] in CONFIG_OPTS or arg == "--bare":
            out.append(arg)
        k += 1
    return out


def _lookup_env(run):
    """`(environment, problem)` for an alias lookup: this process's, minus the repository pins, plus what the command line sets (`GIT_CONFIG_PARAMETERS`, `GIT_CONFIG_COUNT`, a `--config-env` source). A `GIT_CONFIG*` value the walk cannot know makes the lookup unreadable."""
    from rediacc_hooks import shellscan

    env = {k: v for k, v in os.environ.items() if k not in commit_policy.REPO_ENV}
    given = getattr(run, "env", None) or {}
    if shellscan._CLEARED in given:
        env = {k: env[k] for k in ("PATH", "HOME") if k in env}
    for key, value in given.items():
        if key == shellscan._CLEARED:
            continue
        if value is None:
            env.pop(key, None)
        elif shellscan._UNRESOLVED in value:
            if key.startswith("GIT_CONFIG"):
                return env, "`%s` is set to a value this guard cannot know" % key
            env.pop(key, None)
        else:
            env[key] = value
    return env, ""


def _config_table(directory, opts, env):
    """`{key: value or None}` for every `alias.*` git reads in `directory` under `opts`, keys lowercased the way git matches them; None when git cannot read its configuration there."""
    try:
        proc = subprocess.run(
            ["git", *opts, "config", "-z", "--get-regexp", r"^alias\."],
            cwd=directory,
            env=env,
            capture_output=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode == 1 and not proc.stdout:
        return {}
    if proc.returncode != 0:
        return None
    table = {}
    for entry in proc.stdout.decode("utf-8", "surrogateescape").split("\0"):
        if not entry:
            continue
        key, sep, value = entry.partition("\n")
        table[key.lower()] = value if sep else None
    return table


def _is_command(name, directory, env):
    """True when `name` is a git command (a builtin, or a `git-<name>` on the exec path or PATH)."""
    try:
        proc = subprocess.run(
            ["git", "--list-cmds=main,others,nohelpers"],
            cwd=directory,
            env=env,
            capture_output=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0 and name in proc.stdout.decode("utf-8", "replace").split()


def resolve(run, base, created=frozenset()):
    """The `Write` git really performs for a walked `git` run: the typed verb followed through `-c alias.<name>=...` on the command line and through the aliases configured where git runs (its `-C` included), recursively up to `ALIAS_DEPTH`.

    WHY. `git -c alias.cp=cherry-pick cp <sha>`, or `git cp` after `git config alias.cp cherry-pick`, created a commit from a sub-agent unrefused while only the typed verb was read (#6bb5e37a). A `!shell` alias, a configuration git cannot read here, a chain past the cap, and a name that is neither a command nor an alias each come back with a `refusal`: what this guard cannot read, it does not admit.
    """
    opts, verb, args = commit_policy.git_split(run.argv)
    directory = commit_policy.effective_dir(run, base, created)
    typed = verb
    via: list[str] = []

    def done(refusal=""):
        return Write(run, typed, verb, tuple(via), tuple(args), directory, refusal)

    # A missing directory is one git refuses to run in at all.
    if not verb or verb in WRITER_VERBS or verb in PLAIN_VERBS or not os.path.isdir(directory):
        return done()
    cfg = _config_opts(opts)
    env, problem = _lookup_env(run)
    if problem:
        return done(problem)
    seen = set()
    while True:
        table = _config_table(directory, cfg, env)
        if table is None:
            return done("git could not read its configuration in `%s`" % directory)
        key = "alias." + verb.lower()
        if key not in table:
            # Not an alias: a command git runs as is, or a name that is neither here and now. Git does not refuse that one reliably: `help.autocorrect` runs the command a typo resembles (a writer verb included), and an earlier step of the same command can define it (a `git-<name>` on PATH, a config write).
            if not _is_command(verb, directory, env):
                return done(
                    "`%s` is neither a git command nor an alias at the time of the check" % verb
                )
            return done()
        value = table[key]
        via.append("%s = %s" % (key, value))
        if value is None:
            # An alias with no value is one git refuses to run.
            return done()
        if value.startswith("!"):
            return done("`%s` is a shell alias, and what it runs is not read here" % key)
        if len(via) > ALIAS_DEPTH:
            return done("the alias chain is longer than %d" % ALIAS_DEPTH)
        try:
            words = shlex.split(value)
        except ValueError:
            return done("`%s` does not split into words" % key)
        seen.add(verb.lower())
        a_opts, verb, a_args = commit_policy.git_split(words)
        for k, word in enumerate(a_opts[:-1]):
            if word == "-C":
                directory = os.path.normpath(os.path.join(directory, a_opts[k + 1]))
        cfg += _config_opts(a_opts)
        args = a_args + args
        # A name the chain already expanded is a builtin git runs as is (git refuses a loop of aliases), and a writer verb or a plain one ends the chain.
        if not verb or verb in WRITER_VERBS or verb in PLAIN_VERBS or verb.lower() in seen:
            return done()
        if not os.path.isdir(directory):
            return done()


def _redirect_target(run):
    """The first file `run`'s output is redirected into, "" when there is none (a /dev sink is no file)."""
    from rediacc_hooks import shellscan

    for t in shellscan.redirect_targets(run):
        if t not in ("/dev/null", "/dev/stdout", "/dev/stderr", "/dev/tty") and not t.startswith(
            "/dev/fd/"
        ):
            return t
    return ""


def _file_writer(run):
    """A label for a non-git `run` that can write a git configuration file, "" for one that cannot: an `INERT_COMMANDS` name with no output redirect, and `eval` or a `sh -c` payload, whose own runs this loop judges in turn."""
    name = commit_policy._base(run.name)
    target = _redirect_target(run)
    if target:
        return "%s > %s" % (name, target)
    if name in INERT_COMMANDS:
        return ""
    # A `sh -c` payload and an `eval` string are walked into runs of their own, which this loop judges in turn.
    if name == "eval" or (name in ("sh", "bash", "dash", "zsh") and "-c" in run.argv):
        return ""
    return " ".join([name, *run.argv][:4])


# The writer verbs' options that take the NEXT word as their value: that word is a message, a path or a name, never a flag (`git merge -m --quit other`). `-s` and `-x` are values only where the verb says so (`merge`, `rebase` and `pull` take `-s <strategy>`, `rebase` takes `-x <cmd>`); for `cherry-pick`, `revert` and `am` they are the boolean `--signoff` and `--edit`/`-x` record, which consume nothing. `-S` takes its key id attached (`-S<keyid>`), never as the next word.
VALUE_FLAGS = frozenset(
    (
        "-m",
        "-F",
        "-C",
        "-c",
        "-X",
        "-t",
        "-O",
        "--message",
        "--file",
        "--strategy",
        "--strategy-option",
        "--into-name",
        "--cleanup",
        "--onto",
        "--exec",
        "--reuse-message",
        "--reedit-message",
        "--template",
    )
)
VERB_VALUE_FLAGS = {
    "merge": frozenset(("-s",)),
    "pull": frozenset(("-s",)),
    "rebase": frozenset(("-s", "-x")),
}


def _has_no_commit_flag(args, verb=""):
    """Whether `args` holds a NO_COMMIT_FLAGS flag as a FLAG. Only `--show-current-patch` takes an `=<format>` value (`git am`), so `--quit=1` or `--abort=x` is no such flag (review ad958d5a.1), and a word that follows an option taking a value (`-m --quit`) is that option's value and exempts nothing (review d412dae6.1). `verb` decides the options whose value-taking depends on it (`VERB_VALUE_FLAGS`)."""
    value_flags = VALUE_FLAGS | VERB_VALUE_FLAGS.get(verb, frozenset())
    value_of = False
    for arg in args:
        if value_of:
            value_of = False
            continue
        if arg in NO_COMMIT_FLAGS or arg.startswith("--show-current-patch="):
            return True
        value_of = arg in value_flags
    return False


def writer_runs(cmd, base, created=frozenset()):
    """Every git invocation in `cmd` that creates a commit (`WRITER_VERBS`, through any alias), minus a sequencer's `--abort`/`--quit`/`--show-current-patch`, plus every one `resolve` cannot read."""
    found = []
    defining = ""
    for run in commit_policy.runs(cmd):
        if commit_policy._base(run.name) != "git":
            label = _file_writer(run)
            if label and not defining:
                defining = label
            continue
        write = resolve(run, base, created)
        # A git run whose output is redirected into a file can write a configuration too (`git log --format='[alias]...' > .git/config`, review fab28346.1), so a LATER verb's alias is as unreadable as after any other file writer; this run itself is judged as it reads now.
        redirected = _redirect_target(run)
        if redirected and not defining:
            later_defining = "git %s > %s" % (run.argv[0] if run.argv else "", redirected)
        else:
            later_defining = ""
        # An alias read at hook time is the configuration BEFORE the command runs, so a `git config` earlier in the same command that names an alias or an include can redefine what the later verb means.
        if defining and not write.refusal and write.typed not in WRITER_VERBS | PLAIN_VERBS:
            write = write._replace(
                refusal="`%s` earlier in the same command can redefine `%s`"
                % (defining, write.typed)
            )
        if write.typed == "config" and any(
            "alias" in a.lower() or "include" in a.lower() or a in ("-e", "--edit")
            for a in write.args
        ):
            defining = "git config " + " ".join(write.args)
        if later_defining and not defining:
            defining = later_defining
        if write.refusal:
            found.append(write)
            continue
        if write.verb not in WRITER_VERBS:
            continue
        if write.verb != "commit" and _has_no_commit_flag(write.args, write.verb):
            continue
        found.append(write)
    return found


def _writer_message(agent_type, write):
    if write.refusal:
        return ALIAS_UNREADABLE % (agent_type, write.typed, write.refusal)
    text = WRITER_COMMIT % (agent_type, write.verb)
    if write.via:
        chain = " -> ".join("`%s`" % step for step in write.via)
        text = "`git %s` resolves through %s.\n%s" % (write.typed, chain, text)
    return text


EDGE_CASES = [
    ("a plain commit", 'git commit -m "feat(x): y" -- a.ts'),
    ("a valid hotfix", HOTFIX),
    (
        "a hotfix above the file limit",
        'git commit -m "fix: x [hotfix]\n\nHotfix-Evidence: 12345678" -- a b c d e f',
    ),
    ("a hotfix with no evidence", 'git commit -m "fix: x [hotfix]" -- a.ts'),
    (
        "a hotfix whose evidence has no known shape",
        'git commit -m "fix: x [hotfix]\n\nHotfix-Evidence: trust me" -- a.ts',
    ),
    (
        "the ASKED evidence form",
        'git commit -m "fix: x [hotfix]\n\nHotfix-Evidence: ASKED:2026-09-25T10:00Z" -- a.ts',
    ),
    ("a wrapper payload is still judged", "sh -c 'git commit -m \"feat: y\" -- a.ts'"),
    ("a commit in a scratch repo", 'git -C /tmp commit -m "x" -- a'),
    ("prose about committing", "echo 'git commit on main'"),
    ("git log is not a commit", "git log -n 5"),
]


def _message(branch, main_hint):
    if branch == "main":
        return (
            "BLOCKED: this commits to `main`, and it is not a `[hotfix]`.\n"
            "\n"
            "Operator ruling, 2026-09-25: work lands on the one MMDD-N branch in small\n"
            "reviewed commits; `main` takes a commit only for a genuine hotfix (a job that\n"
            "failed on `main` and never ran, or ran differently, on the PR's own run; or the\n"
            "operator called it a hotfix in this task).\n"
            "\n"
            "Move to the branch first; the uncommitted work comes along:\n"
            "\n"
            "  %s\n"
            "\n"
            "A genuine hotfix ends its subject with `[hotfix]` and carries a trailer:\n"
            "\n"
            "  fix(ci): what broke on main [hotfix]\n"
            "\n"
            "  Hotfix-Evidence: <red main run id or URL>   (or ASKED:<YYYY-MM-DDTHH:MMZ>)\n"
            "\n"
            "at most 5 files, no PR-TASK trailer. `main` moves only through `gh pr merge\n"
            "--rebase --auto` or the guarded fast-forward fallback of the live branch, so\n"
            "this tool's push of a commit made on `main` is refused; it goes out by a push\n"
            "outside this tool.\n" % main_hint
        )
    return (
        "BLOCKED: `[hotfix]` is for commits on `main`, and this branch is `%s`.\n"
        "\n"
        "A hotfix tag on a feature branch reads as a reviewed-on-main commit to anyone\n"
        "scanning the log for them. Drop the tag; the commit rides the branch's PR.\n" % branch
    )


def _switch_hint(repo_root, main_hint_cache):
    if repo_root in main_hint_cache:
        return main_hint_cache[repo_root]
    live = commit_policy.live_branches(repo_root, gh=False)
    if live:
        hint = "git switch %s" % live[0]
    else:
        hint = "git switch -c <today's MMDD-N: MAX+1 over `gh pr list --state all` heads>"
    main_hint_cache[repo_root] = hint
    return hint


def run(ev):
    cmd = ev.raw("tool_input", "command")
    if cmd in ("", "null"):
        return hookio.ALLOW
    commits = commit_policy.git_runs(cmd, "commit")
    agent = bool(ev.field("agent_id"))
    if not commits and not (agent and commit_policy.git_runs(cmd)):
        return hookio.ALLOW

    root = ev.env("CLAUDE_PROJECT_DIR") or hookio.git_out(["rev-parse", "--show-toplevel"])
    base = ev.field("cwd") or root
    created = commit_policy.created_dirs(cmd, base)
    writes = writer_runs(cmd, base, created) if agent else []
    agent_type = ev.field("agent_type") or "unknown"
    for write in writes:
        # A directory that resolves to no repository is one git itself will refuse; one outside this checkout is not this policy's business.
        write_repo = commit_policy.toplevel(write.directory)
        if not write_repo or not commit_policy.is_inside(write_repo, root):
            continue
        # A lease is the one place a writer commits: its HEAD is detached, its pin keeps the commit, and the lead lands it with `git cherry-pick -x` (agent/plans/PLAN-worktree-lease.md Design 3).
        if not commit_policy.lease_root(write_repo):
            ev.warn_raw(_writer_message(agent_type, write))
            return hookio.DENY
    if not commits:
        return hookio.ALLOW

    cfg = commit_policy.load_config(root)
    hints: dict[str, str] = {}
    for commit in commits:
        repo = commit_policy.run_repo(commit, base, created)
        if not repo or not commit_policy.is_inside(repo, root):
            continue
        # A `-F <file>` this same command writes first holds an earlier command's bytes: judging it admitted a stale `[hotfix]` onto `main` (#9888de00).
        written = commit_policy.written_message_refusal(cmd, commit, base, "`block_commit_on_main`")
        if written:
            ev.warn_raw(written)
            return hookio.DENY
        branch = commit_policy.current_branch(repo)
        msg = commit_policy.commit_message_text(cmd, base, run=commit)
        is_hotfix = "hotfix" in commit_policy.tags(msg)
        if branch == "main":
            if not is_hotfix:
                ev.warn_raw(_message("main", _switch_hint(repo, hints)))
                return hookio.DENY
            paths = commit_policy.judged_paths(commit, cmd, repo, base)
            ok, reason = commit_policy.hotfix_ok(msg, paths, cfg)
            if not ok:
                ev.warn_raw(
                    "BLOCKED: this `[hotfix]` on `main` is not well-formed: %s.\n"
                    "\n"
                    "A hotfix ends its subject with `[hotfix]`, carries a\n"
                    "`Hotfix-Evidence: <red main run id or URL | ASKED:<YYYY-MM-DDTHH:MMZ>>`\n"
                    "trailer, and touches at most %d files. Anything larger belongs on the\n"
                    "branch and its reviewed PR.\n" % (reason, int(cfg["hotfix_max_files"]))
                )
                return hookio.DENY
        elif is_hotfix:
            ev.warn_raw(_message(branch or "(detached)", ""))
            return hookio.DENY
    return hookio.ALLOW
