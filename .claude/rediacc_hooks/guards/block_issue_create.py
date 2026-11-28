"""Refuse opening a GitHub issue from agent Bash.

WHY (operator ruling 5, ASKED:2026-11-16T09:19Z, agent/plans/PLAN-retire-nightlies-and-mentions.md D3): "New Claude hook guard: block `gh issue create` (and API equivalents such as `gh api .../issues -X POST`) from agent Bash; the refusal tells the agent to ask the operator, because the planning system (agent/plans, worklist) replaces issues." An auto-opened issue duplicates a worklist item and is read by nobody who works the worklist.

WHAT IS REFUSED, in any repository (a submodule's `--repo` included) and under `sh -c`, `env`, `cd`, `$(...)`, `xargs` and the other wrappers `shellscan.every_run` walks:

  * `gh issue create`, and its gh alias `gh issue new`, with the `issue` command's own `-R/--repo` read before the verb as gh reads it;
  * `gh api` to an endpoint ending `repos/<owner>/<repo>/issues` whose method is POST: `-X POST`, `--method POST`, or a field or `--input` making it one (`shellscan.gh_api_method`, the same pflag reader `sanctioned.api_method` wraps);
  * `gh api graphql` whose query carries a `createIssue` mutation, in a field value as bash expands it (a `$Q` or a `${C}eIssue` this same command assigned), or in a `query=@<file>`/`--input <file>` the guard can read; when any query source is not known (an expansion the walk cannot evaluate, stdin, a file that is missing, not a regular file, or one the same command could write first), the whole command text is searched instead, together with every word of every command as bash expands it, every stdin feed and every regular file a word names (the `cp`/`cat` source that fills the query file, review 4347c4c0.1), so an unknown source never admits a mutation the command spells, a `${C}eIssue` echoed into `--input -` included (review 29f470ef.1);
  * `curl` or `wget` sending a POST, or a body that makes one, to an `api.github.com/repos/<owner>/<repo>/issues` URL.

WHAT IS ADMITTED: `gh issue list|view|comment|...`, every GET, `issues/<n>/comments` (the PR-comment endpoint `wl_prreview` answers reviews through, so only the CREATE endpoint is refused), and prose that merely names a command (`echo 'gh issue create'`).

NO ESCAPE VARIABLE, by design: the ruling says ask the operator, and an operator who wants an issue opens it with their own `!` command.
"""

import itertools
import os
import pathlib
import re
import stat

from rediacc_hooks import hookio, shellscan
from rediacc_hooks.guards import tables

__getattr__ = tables("block_issue_create", "EDGE_CASES")

CHAIN = "pre-bash"
OWN_SUITE = True
ORDER = 72

# The create-verb test emptied: `gh issue create` and `gh issue new` run unrefused again.
DEFECT = ('_CREATE_VERBS = ("create", "new")', "_CREATE_VERBS = ()")

# `gh issue create --help` on gh 2.x: ALIASES `gh issue new`.
_CREATE_VERBS = ("create", "new")

# The `issue` command's persistent flags, read before the verb the way gh reads them (`gh issue -R o/r create`).
_ISSUE_TABLE = {"help": ("h", False), "repo": ("R", True)}

# `repos/<owner>/<repo>/issues` exactly, matched against `shellscan.gh_api_endpoint`'s answer, which has already dropped the scheme and host, the query string and the leading and trailing slashes (so `/repos/o/r/issues/?x=1` reaches this as `repos/o/r/issues`); a GitHub Enterprise `api/v3/` prefix is the same endpoint.
_ISSUES_PATH = re.compile(r"^(?:api/v3/)?repos/[^/]+/[^/]+/issues$")
_ISSUES_URL = re.compile(
    r"^(?:https?://)?api\.github\.com/repos/[^/?#]+/[^/?#]+/issues/?(?:[?#].*)?$", re.IGNORECASE
)

_CREATE_ISSUE = re.compile(r"\bcreateIssue\b")
# How much of a file a word names the unknown-source fallback reads: a query is small, and the pre-bash hook must not read a large artifact whole.
_FILE_CAP = 1 << 20

# curl flags that carry a body, and so make the request a POST unless `-G/--get` or `-X` says otherwise.
_CURL_DATA_LONG = (
    "--data",
    "--data-ascii",
    "--data-binary",
    "--data-raw",
    "--data-urlencode",
    "--json",
    "--form",
    "--form-string",
)
_CURL_VALUE_SHORTS = "dFXoHuAeEKbcrTwxyYzmCQtUP"


def _issue_verb(argv):
    """The verb of a `gh issue ...` run (`argv` after `gh`), with `-R/--repo` before it skipped as gh skips it; "" when there is none."""
    _flags, verb, _rest = shellscan._gh_parse(argv[1:], _ISSUE_TABLE, True)
    return verb[0] if verb else ""


def _query_texts(parsed, base, cmd, written, words=()):
    """`(texts, known)` for a parsed `gh api graphql` call (parsed from the EXPANDED argv): each field value, and the file a `query=@<path>` or `--input <path>` names when it can be read. `known` is False when any source is not: a value holding an expansion the walk could not evaluate, stdin (`@-`, `--input -`), or a file `_file_text` cannot vouch for."""
    out = []
    known = True
    files = []
    for name in ("field", "raw-field"):
        for value in parsed.values(name):
            _key, _eq, val = value.partition("=")
            out.append(val)
            if shellscan._UNRESOLVED in val:
                known = False
            elif name == "field" and val.startswith("@"):
                files.append(val[1:])
    files.extend(parsed.values("input"))
    for path in files:
        text = None if path == "-" else _file_text(base, path, cmd, written, words)
        if text is None:
            known = False
        else:
            out.append(text)
    return out, known


def _file_text(base, path, cmd, written, words=()):
    """The text of a query file, or None when it is not a known source: missing, not a regular file (review 81488a75.1: `/dev/zero` never ends and a FIFO blocks the pre-bash hook on open), or a file this same command could write before gh reads it (its name appears more than once in the command text or across `words`, every command's argv as bash expands it, so a `tee "$F"` naming it through a variable counts (review 29f470ef.2); or a redirect target of the command names it or cannot be known)."""
    if shellscan._UNRESOLVED in path:
        return None
    name = os.path.basename(path.rstrip("/"))
    if not name or cmd.count(name) > 1 or sum(w.count(name) for w in words) > 1:
        return None
    if any(shellscan._UNRESOLVED in w or os.path.basename(w) == name for w in written):
        return None
    full = pathlib.Path(base) / path
    try:
        if not stat.S_ISREG(full.stat().st_mode):
            return None
        return full.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _named_file_texts(base, words):
    """The text of every regular file a word names (the word itself, or the path after an `@` or `=@`), read only for an unknown GraphQL source: the file another command copies or redirects into the query file carries the mutation the command text does not (review 4347c4c0.1)."""
    for word in words:
        path = word.rpartition("@")[2] if "@" in word else word
        if path in ("", "-") or shellscan._UNRESOLVED in path:
            continue
        full = pathlib.Path(base) / path
        try:
            if stat.S_ISREG(full.stat().st_mode):
                with full.open(encoding="utf-8", errors="replace") as handle:
                    yield handle.read(_FILE_CAP)
        except (OSError, ValueError):
            continue


def _gh_refusal(argv, cmd, base, xargv=None, written=(), words=(), fallback=None):
    """Which create shape a walked `gh` run is, or "". `xargv` is the run's argv as bash expands it (None when the walk has none), `written` every redirect target of the command, `words` every command's expanded argv, and `fallback` the text searched when a query source is unknown (the command text when None)."""
    if not argv:
        return ""
    if argv[0] == "issue":
        verb = _issue_verb(argv)
        return "`gh issue %s`" % verb if verb in _CREATE_VERBS else ""
    if argv[0] != "api":
        return ""
    parsed = shellscan.gh_args(argv)
    endpoint = shellscan.gh_api_endpoint(parsed)
    if endpoint == "graphql":
        # GraphQL is always a POST; the query decides, read from the EXPANDED argv so `-f query="$Q"` and `${C}eIssue` (variables this same command assigned) are judged by their values (review 81488a75.2). The raw command text is the fallback only when a source is unknown, so a read whose sources are all known is not refused for a `createIssue` mentioned elsewhere in the command (review 81488a75.3).
        texts, known = _query_texts(shellscan.gh_args(xargv or argv), base, cmd, written, words)
        if xargv is None:
            known = False
        unknown_text = cmd if fallback is None else fallback
        if any(_CREATE_ISSUE.search(t) for t in texts) or (
            not known
            and (
                _CREATE_ISSUE.search(unknown_text)
                or any(_CREATE_ISSUE.search(t) for t in _named_file_texts(base, words))
            )
        ):
            return "a `gh api graphql` `createIssue` mutation"
        return ""
    if _ISSUES_PATH.match(endpoint) and shellscan.gh_api_method(parsed) == "POST":
        return "`gh api` POST to `%s`" % endpoint
    return ""


def _curl_refusal(argv):
    """Whether a walked `curl` run POSTs to a GitHub issues-create URL."""
    method = ""
    body = False
    get = False
    urls = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        i += 1
        if arg.startswith("--"):
            name, eq, value = arg.partition("=")
            if name in ("--request", "--url"):
                if not eq:
                    value = argv[i] if i < len(argv) else ""
                    i += 1
                if name == "--request":
                    method = value.upper()
                else:
                    urls.append(value)
            elif name in _CURL_DATA_LONG:
                body = True
                if not eq:
                    i += 1
            elif name == "--get":
                get = True
            continue
        if arg.startswith("-") and len(arg) > 1:
            letters = arg[1:]
            for pos, letter in enumerate(letters):
                if letter == "G":
                    get = True
                    continue
                if letter not in _CURL_VALUE_SHORTS:
                    continue
                value = letters[pos + 1 :]
                if not value:
                    value = argv[i] if i < len(argv) else ""
                    i += 1
                if letter == "X":
                    method = value.upper()
                elif letter in "dF":
                    body = True
                break
            continue
        urls.append(arg)
    if not any(_ISSUES_URL.match(u) for u in urls):
        return False
    if method:
        return method == "POST"
    return body and not get


def _wget_refusal(argv):
    """Whether a walked `wget` run POSTs to a GitHub issues-create URL."""
    posts = any(
        a.startswith(("--post-data", "--post-file", "--body-data", "--body-file"))
        or a.upper() == "--METHOD=POST"
        for a in argv
    )
    if not posts:
        for prev, nxt in itertools.pairwise(argv):
            if prev == "--method" and nxt.upper() == "POST":
                posts = True
    return posts and any(_ISSUES_URL.match(a) for a in argv)


def _refusal(cmd, base):
    runs = list(shellscan.every_run(cmd))
    written = [w for run_ in runs for w in (*run_.writes, *run_.xwrites)]
    # Every command's words as bash expands them, and what each reads on stdin: the fallback for an unknown GraphQL source reads these beside the typed text, since `C=creat; echo "${C}eIssue" | gh api graphql --input -` spells the mutation only after expansion (review 29f470ef.1).
    words = [w for run_ in runs for w in (run_.argv if run_.xargv is None else run_.xargv)]
    fallback = "\n".join([cmd, *words, *(run_.feed or "" for run_ in runs)])
    for run_ in runs:
        name = shellscan._base(run_.name)
        argv = list(run_.argv)
        if name == "gh":
            xargv = list(run_.xargv) if run_.xargv is not None else None
            found = _gh_refusal(argv, cmd, base, xargv, written, words, fallback)
            if found:
                return found
        elif name == "curl" and _curl_refusal(argv):
            return "`curl` POST to a GitHub issues endpoint"
        elif name == "wget" and _wget_refusal(argv):
            return "`wget` POST to a GitHub issues endpoint"
    return ""


def run(ev):
    cmd = ev.raw("tool_input", "command")
    if cmd in ("", "null") or not re.search(r"issue|graphql", cmd, re.IGNORECASE):
        return hookio.ALLOW
    base = ev.field("cwd") or ev.cwd or "."
    found = _refusal(cmd, base)
    if not found:
        return hookio.ALLOW
    ev.warn_raw(
        "BLOCKED: %s opens a GitHub issue.\n"
        "\n"
        "Issues are retired for agents (operator ruling 5, ASKED:2026-11-16T09:19Z,\n"
        "agent/plans/PLAN-retire-nightlies-and-mentions.md): agent/plans and the worklist\n"
        "replace them. Track the finding instead:\n"
        "  .claude/hooks/stop/worklist.py --add <me> <finding with its evidence>\n"
        "or write it into a plan under agent/plans. If a GitHub issue is still wanted, ask\n"
        "the operator; there is no override for this refusal.\n" % found
    )
    return hookio.DENY
