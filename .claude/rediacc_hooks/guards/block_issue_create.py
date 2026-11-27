"""Refuse opening a GitHub issue from agent Bash.

WHY (operator ruling 5, ASKED:2026-11-16T09:19Z, agent/plans/PLAN-retire-nightlies-and-mentions.md D3): "New Claude hook guard: block `gh issue create` (and API equivalents such as `gh api .../issues -X POST`) from agent Bash; the refusal tells the agent to ask the operator, because the planning system (agent/plans, worklist) replaces issues." An auto-opened issue duplicates a worklist item and is read by nobody who works the worklist.

WHAT IS REFUSED, in any repository (a submodule's `--repo` included) and under `sh -c`, `env`, `cd`, `$(...)`, `xargs` and the other wrappers `shellscan.every_run` walks:

  * `gh issue create`, and its gh alias `gh issue new`, with the `issue` command's own `-R/--repo` read before the verb as gh reads it;
  * `gh api` to an endpoint ending `repos/<owner>/<repo>/issues` whose method is POST: `-X POST`, `--method POST`, or a field or `--input` making it one (`shellscan.gh_api_method`, the same pflag reader `sanctioned.api_method` wraps);
  * `gh api graphql` whose query carries a `createIssue` mutation, in a field value, a `query=@<file>` the guard can read, or the command text a `$Q` would expand from;
  * `curl` or `wget` sending a POST, or a body that makes one, to an `api.github.com/repos/<owner>/<repo>/issues` URL.

WHAT IS ADMITTED: `gh issue list|view|comment|...`, every GET, `issues/<n>/comments` (the PR-comment endpoint `wl_prreview` answers reviews through, so only the CREATE endpoint is refused), and prose that merely names a command (`echo 'gh issue create'`).

NO ESCAPE VARIABLE, by design: the ruling says ask the operator, and an operator who wants an issue opens it with their own `!` command.
"""

import itertools
import pathlib
import re

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

# `repos/<owner>/<repo>/issues` and nothing after it but a slash or a query string; a GitHub Enterprise `api/v3/` prefix is the same endpoint.
_ISSUES_PATH = re.compile(r"^(?:api/v3/)?repos/[^/]+/[^/]+/issues$")
_ISSUES_URL = re.compile(
    r"^(?:https?://)?api\.github\.com/repos/[^/?#]+/[^/?#]+/issues/?(?:[?#].*)?$", re.IGNORECASE
)

_CREATE_ISSUE = re.compile(r"\bcreateIssue\b")

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


def _query_texts(parsed, base):
    """Every graphql query text a parsed `gh api graphql` call sends: each field value, and the file a `query=@<path>` or `--input <path>` names when it can be read."""
    out = []
    for name in ("field", "raw-field"):
        for value in parsed.values(name):
            _key, _eq, val = value.partition("=")
            out.append(val)
            if name == "field" and val.startswith("@") and val != "@-":
                out.append(_read(base, val[1:]))
    out.extend(_read(base, path) for path in parsed.values("input") if path != "-")
    return out


def _read(base, path):
    try:
        return (pathlib.Path(base) / path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _gh_refusal(argv, cmd, base):
    """Which create shape a walked `gh` run is, or ""."""
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
        # GraphQL is always a POST; the query decides. The command text is read too, since `-f query="$Q"` carries the mutation in a variable this same command assigned.
        if any(_CREATE_ISSUE.search(t) for t in _query_texts(parsed, base)) or _CREATE_ISSUE.search(
            cmd
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
    for run_ in shellscan.every_run(cmd):
        name = shellscan._base(run_.name)
        argv = list(run_.argv)
        if name == "gh":
            found = _gh_refusal(argv, cmd, base)
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
