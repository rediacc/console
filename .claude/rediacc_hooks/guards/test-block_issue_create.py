#!/usr/bin/env python3
"""Control harness for block_issue_create (OWN_SUITE: never bash, so no golden).

Each refused shape of agent/plans/PLAN-retire-nightlies-and-mentions.md D3 must be DENIED with the ruling's refusal text, a submodule `--repo` and an `sh -c` wrap included; the admitted shapes of box G1 (a comment on `issues/<n>/comments`, `gh issue list`, a GET of `repos/o/r/issues`, prose naming the command) must be ALLOWED. Every case drives the live guard through the dispatcher, so the module that runs in the hook chain is the one judged.

THE DEFECT CONTROL plants the guard's declared `DEFECT` (the create-verb test emptied) in a copy and requires every `gh issue create|new` fire case to flip to allowed while the API, GraphQL and curl fire cases stay refused, so the control proves the verb test is what refuses those shapes and nothing else is.
"""

import importlib.util
import json
import os
import pathlib
import sys
import tempfile

import _hookpath

from rediacc_hooks.guards import _harness

HERE = pathlib.Path(__file__).resolve().parent
DISPATCH = str(HERE.parent / "dispatch.py")
STEM = "block_issue_create"
GUARD = HERE / ("%s.py" % STEM)

_RUNTMP = importlib.util.spec_from_file_location(
    "runtmp", HERE.parents[2] / ".ci" / "rediacc_ci" / "runtmp.py"
)
if _RUNTMP is None or _RUNTMP.loader is None:
    raise SystemExit("%s: .ci/rediacc_ci/runtmp.py is missing" % __file__)
runtmp = importlib.util.module_from_spec(_RUNTMP)
_RUNTMP.loader.exec_module(runtmp)
WORK = pathlib.Path(
    tempfile.mkdtemp(prefix="guard-issue-create-", dir=runtmp.run_dir("guard-issue-"))
)
(WORK / "create.graphql").write_text(
    'mutation { createIssue(input:{repositoryId:"R", title:"x"}) { issue { number } } }\n',
    encoding="utf-8",
)
(WORK / "read.graphql").write_text(
    'query { repository(owner:"o", name:"r") { issues(first:1) { nodes { number } } } }\n',
    encoding="utf-8",
)
(WORK / "body.json").write_text('{"title":"x"}\n', encoding="utf-8")

NEEDLE = "Issues are retired for agents"
MUTATION = (
    'mutation { createIssue(input:{repositoryId:\\"R\\", title:\\"x\\"}) { issue { number } } }'
)

# (name, command, expect_blocked, is_create_verb) ---- fire ----------------------------------------
FIRE = [
    ("gh issue create", "gh issue create -t x -b y", True),
    ("gh issue new (the alias)", "gh issue new -t x", True),
    ("bare gh issue create", "gh issue create", True),
    ("a submodule --repo after the verb", "gh issue create --repo rediacc/renet -t x -b y", True),
    ("a submodule -R before the verb", "gh issue -R rediacc/renet create -t x", True),
    ("--repo= before the verb", "gh issue --repo=rediacc/account create -t x", True),
    ("an sh -c wrap", "sh -c 'gh issue create -t x -b y'", True),
    ("a bash -lc wrap", 'bash -lc "gh issue create -t x"', True),
    ("an env prefix", "GH_TOKEN=t env GH_REPO=o/r gh issue create -t x", True),
    ("behind cd", "cd private/renet && gh issue create -t x", True),
    ("inside $(...)", "URL=$(gh issue create -t x -b y)", True),
    ("an absolute gh path", "/usr/bin/gh issue create -t x", True),
    ("through command", "command gh issue create -t x", True),
    ("through xargs", "printf x | xargs gh issue create -t", True),
    ("api -X POST", "gh api -X POST repos/o/r/issues -f title=x", False),
    ("api --method POST", "gh api --method POST repos/rediacc/console/issues -f title=x", False),
    ("api --method=post", "gh api --method=post repos/o/r/issues -f title=x", False),
    ("api -XPOST bundled", "gh api -XPOST repos/o/r/issues -f title=x", False),
    ("api a body field makes it POST", "gh api repos/o/r/issues -f title=x -f body=y", False),
    ("api -F typed field", "gh api repos/o/r/issues -F title=x", False),
    ("api --raw-field=", "gh api repos/o/r/issues --raw-field=title=x", False),
    ("api --input file", "gh api repos/o/r/issues --input body.json", False),
    ("api a leading slash", "gh api /repos/o/r/issues -f title=x", False),
    ("api a trailing slash", "gh api repos/o/r/issues/ -f title=x", False),
    ("api the full URL", "gh api https://api.github.com/repos/o/r/issues -f title=x", False),
    ("api {owner}/{repo} placeholders", "gh api 'repos/{owner}/{repo}/issues' -f title=x", False),
    ("api under sh -c", "sh -c 'gh api repos/o/r/issues -f title=x'", False),
    (
        "graphql createIssue inline",
        "gh api graphql -f query='%s'" % MUTATION.replace('\\"', '"'),
        False,
    ),
    ("graphql createIssue from a file", "gh api graphql -F query=@create.graphql", False),
    (
        "graphql createIssue in a variable",
        "Q='%s'; gh api graphql -f query=\"$Q\"" % MUTATION.replace('\\"', '"'),
        False,
    ),
    (
        "curl -X POST",
        "curl -X POST -H 'Authorization: token t' https://api.github.com/repos/o/r/issues -d '{\"title\":\"x\"}'",
        False,
    ),
    (
        "curl a -d body makes it POST",
        "curl -s https://api.github.com/repos/o/r/issues -d @body.json",
        False,
    ),
    ("curl --json", 'curl --json \'{"title":"x"}\' https://api.github.com/repos/o/r/issues', False),
    (
        "curl --request=POST --url",
        "curl --request=POST --url https://api.github.com/repos/o/r/issues",
        False,
    ),
    ("curl -XPOST bundled", "curl -sXPOST https://api.github.com/repos/o/r/issues", False),
    (
        "wget --post-data",
        'wget --post-data=\'{"title":"x"}\' https://api.github.com/repos/o/r/issues',
        False,
    ),
]
FIRE = [(n, c, True, verb) for n, c, verb in FIRE]

ADMIT = [
    ("comment on issues/<n>/comments", "gh api repos/o/r/issues/12/comments -f body=x"),
    ("comment POST explicit", "gh api -X POST repos/o/r/issues/12/comments -f body=x"),
    ("gh issue list", "gh issue list --state open"),
    ("gh issue view", "gh issue view 12 --repo rediacc/renet"),
    ("gh issue comment", "gh issue comment 12 -b x"),
    ("gh issue list -R before the verb", "gh issue -R o/r list"),
    ("api GET of repos/o/r/issues", "gh api repos/o/r/issues"),
    ("api -X GET with a field", "gh api -X GET repos/o/r/issues -f state=open"),
    ("api PATCH of one issue", "gh api -X PATCH repos/o/r/issues/12 -f state=closed"),
    ("api POST to pulls", "gh api repos/o/r/pulls -f title=x -f head=a -f base=main"),
    ("api POST to an issue-ish name", "gh api repos/o/issues/labels -f name=x"),
    ("graphql read of issues", "gh api graphql -F query=@read.graphql"),
    (
        "graphql resolveReviewThread",
        "gh api graphql -f query='mutation { resolveReviewThread(input:{threadId:\"T\"}) { thread { id } } }'",
    ),
    ("echo naming the command", "echo 'gh issue create'"),
    ("echo naming the api shape", "echo 'gh api -X POST repos/o/r/issues'"),
    ("grep for the command", "grep -rn 'gh issue create' .claude"),
    ("a heredoc to a file naming it", "cat > notes.md <<'EOF'\ngh issue create -t x\nEOF"),
    ("curl GET of issues", "curl -s https://api.github.com/repos/o/r/issues"),
    ("curl -G with data is a GET", "curl -G -d state=open https://api.github.com/repos/o/r/issues"),
    (
        "curl POST to comments",
        "curl -X POST https://api.github.com/repos/o/r/issues/12/comments -d x",
    ),
    ("wget GET of issues", "wget -qO- https://api.github.com/repos/o/r/issues"),
    ("gh pr create", "gh pr create --draft -t x -b y"),
    ("an empty command", ""),
]
ADMIT = [(n, c, False, False) for n, c in ADMIT]

CASES = FIRE + ADMIT

BROKEN_RUNNER = (
    "import sys; sys.path.insert(0, %r)\n"
    "from rediacc_hooks import hookio\n"
    "src = open(%r, encoding='utf-8').read()\n"
    "old, new = %r\n"
    "import ast\n"
    "cut = [n for n in ast.parse(src).body if isinstance(n, ast.Assign)"
    " and any(isinstance(t, ast.Name) and t.id == 'DEFECT' for t in n.targets)]\n"
    "outside = '\\n'.join(l for i, l in enumerate(src.split('\\n'), 1)"
    " if not any(n.lineno <= i <= (n.end_lineno or n.lineno) for n in cut))\n"
    "assert cut and old in outside, 'DEFECT no longer applies outside its own declaration'\n"
    "ns = {'__name__': 'broken', '__file__': %r}\n"
    "exec(compile(src.replace(old, new), 'broken', 'exec'), ns)\n"
    "ev = hookio.Event(sys.stdin.read())\n"
    "rc = ns['run'](ev)\n"
    "sys.stderr.write(ev.result(rc)[2])\n"
    "sys.exit(rc)\n"
)


def _declared_defect():
    namespace: dict[str, object] = {}
    source = GUARD.read_text(encoding="utf-8")
    start = source.index("DEFECT = ")
    end = source.index(")\n", start) + 1
    exec(source[start:end], namespace)
    return namespace["DEFECT"]


DEFECT = _declared_defect()


def run(command, broken=False):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(WORK))
    payload = json.dumps(
        {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(WORK)}
    )
    if broken:
        code = BROKEN_RUNNER % (str(HERE.parents[1]), str(GUARD), DEFECT, str(GUARD))
        argv = [sys.executable, "-c", code]
    else:
        argv = [sys.executable, DISPATCH, STEM]
    proc = _harness.run(
        argv, input=payload, capture_output=True, text=True, check=False, env=env, cwd=str(WORK)
    )
    if proc.returncode not in (0, 2):
        raise SystemExit("guard runner crashed on %r: %s" % (command, proc.stderr[-800:]))
    return proc.returncode != 0, proc.stderr


fails = 0
fired = 0
for name, command, want, _verb in CASES:
    got, err = run(command)
    fired += got
    # A refusal counts only when it is THIS guard's refusal text, so a crash or another message cannot pass a fire case.
    ok = got == want and ((NEEDLE in err) if want else not err.strip())
    fails += not ok
    print(
        "%-44s want=%-8s got=%-8s %s"
        % (
            name,
            "BLOCKED" if want else "allowed",
            "BLOCKED" if got else "allowed",
            "ok" if ok else "*** FAIL ***",
        )
    )
    if not ok and err:
        print("    stderr: %s" % err.strip().splitlines()[:3])

print()
verb_cases = [(n, c) for n, c, want, verb in CASES if want and verb]
other_cases = [(n, c) for n, c, want, verb in CASES if want and not verb]
still_refused = [n for n, c in verb_cases if run(c, broken=True)[0]]
lost = [n for n, c in other_cases if not run(c, broken=True)[0]]
if still_refused or lost or not verb_cases:
    fails += 1
    print(
        "*** FAIL *** DEFECT control %r: verb cases still refused %r; non-verb cases lost %r"
        % (DEFECT, still_refused, lost)
    )
else:
    print(
        "DEFECT control: planted %r; all %d gh issue create|new case(s) flipped to allowed, "
        "all %d API/GraphQL/curl case(s) still refused"
        % (DEFECT[0], len(verb_cases), len(other_cases))
    )

print()
fire_n = sum(1 for c in CASES if c[2])
print(
    "%d case(s): %d fire, %d admit; %d refused; %d failure(s)"
    % (len(CASES), fire_n, len(CASES) - fire_n, fired, fails)
)
# Zero fire cases would make every green above vacuous.
if fire_n == 0 or fired == 0:
    print("*** FAIL *** no case was refused, so this suite proves nothing")
    fails += 1
sys.exit(1 if fails else 0)
