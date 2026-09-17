"""Asking GitHub a question through `gh`, where a FAILED call cannot look empty.

THE ONE RULE THIS MODULE EXISTS FOR. A `gh` call has three outcomes, not two:
it answered, it answered with nothing, or it never answered at all. Almost every
call site in this tree collapses the third into the second, and the collapse is
silent because the natural bash spelling makes it silent.

------------------------------------------------------------------------------
TRAP 1: `|| echo "[]"` AND `2>/dev/null` TURN AN OUTAGE INTO AN EMPTY ANSWER.
------------------------------------------------------------------------------
Measured across `.ci`, `scripts` and `.claude`: 28 `gh` call sites end in
`|| echo "..."` or a `// empty` jq default. A rate limit, an expired token or a
network blip then produces the SAME value as "there is nothing here", and the
caller acts on it. `.ci/scripts/lib/common.sh:392-397` already records what that
cost: "Nine call sites across the review, attribution and submodule-branch gates
were spelled `X=$(gh api ... 2>/dev/null || echo "[]")` ... those are
merge-blocking gates: a swallowed failure there is a silent green on the check
that is supposed to stop the merge." `_gh_probe` there is the bash answer, and
this module is its typed counterpart -- with one addition `_gh_probe` cannot
have, below.

------------------------------------------------------------------------------
TRAP 2: A PIPELINE ENDING IN `sort` ALWAYS EXITS 0, SO THE CALLER CANNOT CHECK.
------------------------------------------------------------------------------
This is the sharper version of trap 1, because here there is nothing left to
check even if the caller wanted to. `.claude/rediacc_hooks/guards/
block_nonstandard_branch_name.py:230-233` prints this as the advice for picking
the next branch name:

    gh pr list --state all --limit 100 --json headRefName \\
      --jq '.[].headRefName' | grep "^${d}-" | sed "s/^${d}-//" | sort -n | tail -1

`gh` is the FIRST stage. Its exit code is discarded by the pipe, `grep` finding
nothing exits 1, and `sort`/`tail` exit 0 with empty output. An unauthenticated
`gh` and a day with no branches yet produce byte-identical results: empty. The
caller adds one to nothing and picks `-1`. That same guard, at :228-231, names
what it cost: "that is exactly how 0826-1 got picked twice on 2026-08-26, the
second time after PR #576 had already merged it that morning."

`branch_indexes()` and `next_branch_name()` below are that pipeline, with the
failure kept. Measured while writing this module: an unauthenticated
`gh pr list --repo rediacc/console --state open --json number` exits **4**, not
1, and writes "To get started with GitHub CLI, please run: gh auth login" to
STDERR -- which `2>/dev/null` deletes and the pipe discards. Both halves of the
evidence are thrown away by the spelling the guard recommends.

------------------------------------------------------------------------------
HOW THE CHECK IS MADE IMPOSSIBLE TO SKIP: `.stdout` RAISES.
------------------------------------------------------------------------------
`GhResult.stdout` is a PROPERTY that raises the classified error when the call
did not succeed. There is no way to write `json.loads(result.stdout)` or
`result.stdout.splitlines()` and have a failure arrive as an empty answer,
because the attribute a caller reaches for first is the one that refuses.

THIS IS A DELIBERATE DIVERGENCE FROM `rediacc_ci.proc.Result`, whose `.stdout`
is a plain string, and the divergence is the point. `proc` is a general
subprocess layer where a non-zero exit is often the answer (`git diff --quiet`
means something at 1). `gh` is a network client where a non-zero exit is never
an answer about the repository, only about the call. The raw bytes are still
reachable as `.stdout_raw` for diagnostics and for the error messages, which is
the one use a failed call's output has.

`.stderr` is a plain attribute and is ALWAYS readable, because surfacing it is
the second half of the requirement: 28 sites send it to /dev/null, so the one
sentence that says "your token expired" never reaches a human.

------------------------------------------------------------------------------
TRAP 3: EXIT 0 IS NOT A PROMISE THAT THE BODY IS WHAT YOU ASKED FOR.
------------------------------------------------------------------------------
`common.sh:418-420`: "`gh api graphql` can exit 0 while returning a truncated or
malformed body, so an exit-code check alone misses it." So `json()` parses and
raises `GhBadOutputError` rather than returning whatever `json.loads` made of it, and
`value()` refuses an EMPTY string where a scalar was expected.

The reason that refusal is not paranoia is written down in this repository at
`docs/dev-environments.md:102-110` and `scripts/gates/check-external-links.ts:174-186`:
a documented one-liner piped an unchecked HTTP response into
`ACCOUNT_ED25519_PUBLIC_KEY`. The URL had started answering 404. With `curl -f`
the variable was assigned the EMPTY string; without `-f` the 404's HTML BODY was
baked into `keys.ProductionPublicKey` via ldflags. Either way the build
succeeded and every production-signed licence then failed as
`invalid_signature`. An unchecked response became a signing key. Nothing in this
module returns a caller-trusted value without first checking the status that
produced it.

------------------------------------------------------------------------------
GITHUB SECRETS ARE WRITE-ONLY. THERE IS NO GETTER HERE, AND THERE CANNOT BE ONE.
------------------------------------------------------------------------------
`secret_names()` lists names. `secret_value()` exists ONLY to raise, with the
reason, because the failure this module is guarding against was somebody
reaching for a value GitHub does not serve and settling for whatever a URL
returned instead. `docs/dev-environments.md:112-116`: "GitHub secrets are
write-only, so no command can fetch it, and the old one-liner was not merely
pointing at a dead URL but at a shape of solution that cannot exist."
`.ci/scripts/quality/check_bws_map.py:69-73` says the same from the write side:
"`gh secret set` cannot re-supply a value it is forbidden to read". An
`AttributeError` from a missing function sends the next reader to write their
own `curl`; a raised sentence sends them to the operator.

------------------------------------------------------------------------------
READ ONLY, BY CONSTRUCTION WHERE IT MATTERS
------------------------------------------------------------------------------
Every typed helper here is a read. `api_json()` takes no `method` argument at
all, so it cannot be turned into a POST by adding one flag at a call site; a
write goes through `gh()` explicitly, where a reviewer sees the verb. This is
not a security boundary -- `gh()` runs whatever it is given -- it is the same
argument the rest of this package makes about spelling: the dangerous thing
should be the one that has to be typed out.

WHY `gh` IS RUN THROUGH `rediacc_ci.proc`: for the bounded, stdin-closed,
streams-separate contract that module documents. `proc.run` closes stdin, which
matters more for `gh` than for anything else in this tree -- an expired token is
one of the three cases `proc`'s own docstring names as a command that decides to
prompt a terminal nobody is watching.
"""

import json
import os
import re
import sys
import time

from rediacc_ci import proc

# Every one of these closes a way `gh` can decide to wait for a human, page its output, or colour it. The pager pair matters twice over: `gh` honours GH_PAGER and falls back to PAGER, and a pager on a non-tty is how a call that "hung in CI" actually spent its fifteen minutes.
NONINTERACTIVE = {
    "GH_PROMPT_DISABLED": "1",
    "GH_NO_UPDATE_NOTIFIER": "1",
    "GH_PAGER": "cat",
    "PAGER": "cat",
    # Colour in a captured stream is escape bytes inside a value a caller then compares. `differential.escape_bytes` exists because this repo has been bitten by exactly that.
    "NO_COLOR": "1",
    "CLICOLOR": "0",
}

# The observed `gh` timeouts in this tree are 20 seconds (`block-admin-merge.sh:64`, the only site that bounds it at all). Everything else is unbounded. 30 here so no existing behaviour gets tighter by being ported, and nothing is unbounded.
DEFAULT_TIMEOUT = 30.0

# `gh`'s own exit code for "you are not authenticated". MEASURED 2026-09-06: `gh pr list --repo rediacc/console --state open --json number` with an empty GH_CONFIG_DIR and no token exits 4. Not 1. A call site that branches on 1 therefore misclassifies the single most common failure, and one that branches on "non-zero" cannot tell it from a genuine finding.
AUTH_FAILED_RC = 4

# 127 from `proc.run` means the binary could not be spawned at all.
NOT_INSTALLED_RC = proc.SPAWN_FAILED_RC

# The classification vocabulary. Strings rather than an Enum because these are printed into messages and compared in tests, and an Enum's repr is noise in both places.
FAILURE_NOT_INSTALLED = "not-installed"
FAILURE_UNAUTHENTICATED = "unauthenticated"
FAILURE_RATE_LIMITED = "rate-limited"
FAILURE_TIMED_OUT = "timed-out"
FAILURE_FAILED = "failed"

AUTH_AUTHENTICATED = "authenticated"
AUTH_UNAUTHENTICATED = "unauthenticated"
AUTH_UNKNOWN = "unknown"

# Matched case-insensitively against STDERR. Every string here was produced by a real `gh` on this host on 2026-09-06 except the two HTTP ones, which are what `gh api` prints when the token is present but rejected.
#
# THE MARKERS ARE A REFINEMENT, NEVER THE VERDICT. The verdict is the exit code: anything non-zero is a failure whatever the stderr says. A marker only chooses WHICH failure, so a `gh` release that rewords its messages degrades this to FAILURE_FAILED and never to "success".
_UNAUTHENTICATED_MARKERS = (
    "gh auth login",
    "not logged into any github host",
    "populate the gh_token environment variable",
    "http 401",
    "bad credentials",
    "requires authentication",
)
_RATE_LIMIT_MARKERS = (
    "rate limit",
    "api rate limit exceeded",
    "secondary rate limit",
)

# A branch name this repo will accept: MMDD-N, no suffix. The guard at .claude/rediacc_hooks/guards/block_nonstandard_branch_name.py:204 pins the
# same shape with `^[0-9]{4}-[0-9]+$`.
_DAY_RE = re.compile(r"^[0-9]{4}$")


class GhError(RuntimeError):
    """A `gh` call that did not answer. Carries the evidence, not just a message.

    The four fields are the ones a reader needs and a bare `RuntimeError("gh
    failed")` throws away: what was run, what it exited with, what it said, and
    which classification this module reached. `str(exc)` renders all of them,
    stderr included, because the whole point of the module is that stderr stops
    going to /dev/null.
    """

    def __init__(self, argv: list[str], returncode: int, stderr: str, failure: str) -> None:
        self.argv = list(argv)
        self.returncode = returncode
        self.stderr = stderr
        self.failure = failure
        detail = stderr.strip().splitlines()
        first = detail[0] if detail else "(no stderr)"
        super().__init__(
            "%s exited %d [%s]: %s" % (" ".join(self.argv), returncode, failure, first)
        )


class GhNotInstalledError(GhError):
    """`gh` is not on PATH. Not evidence about GitHub, and never a finding."""


class GhUnauthenticatedError(GhError):
    """`gh` ran and GitHub refused the credentials.

    Its own class because the ACTION differs: a missing binary is installed, an
    expired token is refreshed, and neither is a statement about the repository.
    """


class GhRateLimitedError(GhError):
    """GitHub answered, and the answer was "not now". Retryable; the others are not."""


class GhBadOutputError(GhError):
    """`gh` exited 0 and the body was not usable. TRAP 3.

    Reached with returncode 0, which looks contradictory and is exactly the case
    worth naming: `common.sh:418-420` records `gh api graphql` doing it.
    """


class SecretValueUnavailableError(NotImplementedError):
    """Raised by `secret_value`. A GitHub secret cannot be read back, ever.

    NotImplementedError and not GhError on purpose: no call was made and none
    could be. This is a mistake in the calling program, not a failure of the
    network.
    """


def _classify(returncode: int, stderr: str, *, timed_out: bool) -> str:
    """Which failure this is. Only ever called for a non-zero exit."""
    if timed_out:
        return FAILURE_TIMED_OUT
    if returncode == NOT_INSTALLED_RC:
        return FAILURE_NOT_INSTALLED
    lowered = stderr.lower()
    # RATE LIMIT IS TESTED BEFORE AUTH, and the order is load bearing. GitHub's rate-limit body for an unauthenticated caller says "rate limit exceeded" AND suggests authenticating, so an auth-first test would classify a retryable condition as a credential problem and send the reader to rotate a token that is fine.
    if any(marker in lowered for marker in _RATE_LIMIT_MARKERS):
        return FAILURE_RATE_LIMITED
    if returncode == AUTH_FAILED_RC or any(m in lowered for m in _UNAUTHENTICATED_MARKERS):
        return FAILURE_UNAUTHENTICATED
    return FAILURE_FAILED


_ERROR_CLASSES = {
    FAILURE_NOT_INSTALLED: GhNotInstalledError,
    FAILURE_UNAUTHENTICATED: GhUnauthenticatedError,
    FAILURE_RATE_LIMITED: GhRateLimitedError,
}


class GhResult:
    """What a `gh` call did, with the success check in front of the output.

    `.stdout` RAISES unless the call succeeded. See the module docstring; that
    property is the whole mechanism, and every accessor below routes through it,
    so there is no second path that forgets to check.
    """

    __slots__ = ("argv", "duration", "returncode", "stderr", "stdout_raw", "timed_out")

    def __init__(
        self,
        argv: list[str],
        returncode: int,
        stdout: str,
        stderr: str,
        *,
        timed_out: bool = False,
        duration: float = 0.0,
    ) -> None:
        self.argv = list(argv)
        self.returncode = returncode
        # NAMED `stdout_raw`, not `_stdout`. A single leading underscore says "private", which invites a reader to use it anyway once they decide
        # they know better; `stdout_raw` says what it is -- the bytes, unchecked
        # -- so a call site that uses it reads as a deliberate choice.
        self.stdout_raw = stdout
        self.stderr = stderr
        self.timed_out = timed_out
        self.duration = duration

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def __bool__(self) -> bool:
        return self.ok

    def __repr__(self) -> str:
        return "GhResult(argv=%r, returncode=%d, failure=%r, out=%d B, err=%d B)" % (
            self.argv,
            self.returncode,
            self.failure,
            len(self.stdout_raw),
            len(self.stderr),
        )

    @property
    def failure(self) -> str | None:
        """The classification, or None when the call succeeded."""
        if self.ok:
            return None
        return _classify(self.returncode, self.stderr, timed_out=self.timed_out)

    def error(self) -> GhError:
        """The typed exception for this failure. Raises if called on a success.

        Building an error object for a call that worked is always a bug in the
        caller, and returning a plausible one would hide it.
        """
        failure = self.failure
        if failure is None:
            raise ValueError("error() on a successful call: %r" % self)
        cls = _ERROR_CLASSES.get(failure, GhError)
        return cls(self.argv, self.returncode, self.stderr, failure)

    @property
    def stdout(self) -> str:
        """The output -- or the classified exception. THE CHECK THAT CANNOT BE SKIPPED."""
        if not self.ok:
            raise self.error()
        return self.stdout_raw

    def lines(self) -> list[str]:
        """Non-empty output lines. [] means the call SUCCEEDED and said nothing."""
        return [line for line in self.stdout.splitlines() if line.strip()]

    def value(self, what: str = "value") -> str:
        """One stripped scalar. Refuses empty.

        THE `invalid_signature` CLAUSE. An empty string is what an unchecked
        `curl -f` assigns, and a build that accepts it succeeds while producing
        artefacts that cannot work. Where a caller genuinely wants "maybe
        nothing", `lines()` says so with a list; this one is for the case where
        emptiness is a defect.
        """
        text = self.stdout.strip()
        if not text:
            raise GhBadOutputError(
                self.argv,
                self.returncode,
                "gh exited 0 but printed nothing where a %s was required. An empty "
                "value is not an answer: this is the shape that put an empty "
                "ACCOUNT_ED25519_PUBLIC_KEY into a production build "
                "(docs/dev-environments.md:102-110)." % what,
                FAILURE_FAILED,
            )
        return text

    def json(self) -> object:
        """Parse the body. TRAP 3: exit 0 does not promise the body is JSON."""
        text = self.stdout
        try:
            return json.loads(text)
        except ValueError as exc:
            raise GhBadOutputError(
                self.argv,
                self.returncode,
                "gh exited 0 and the body is not JSON (%s). First 200 bytes: %r"
                % (exc, text[:200]),
                FAILURE_FAILED,
            ) from exc

    def json_list(self) -> list:
        """`json()` that also insists the body is a list.

        `gh api` answers an error with a JSON OBJECT (`{"message": "Not Found"}`)
        at some statuses, and a caller that wrote `for row in result.json()`
        would iterate the object's KEYS -- one string, "message" -- and report
        one finding named after the error. A type check is one line and closes it.
        """
        parsed = self.json()
        if not isinstance(parsed, list):
            raise GhBadOutputError(
                self.argv,
                self.returncode,
                "expected a JSON array, got %s: %r" % (type(parsed).__name__, parsed),
                FAILURE_FAILED,
            )
        return parsed


def which_gh(env: dict[str, str] | None = None) -> str | None:
    """Absolute path of `gh`, or None. Asked BEFORE blaming GitHub for anything."""
    return proc.which("gh", env)


def gh(
    args: list[str],
    *,
    repo: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    env: dict[str, str] | None = None,
    attempts: int = 1,
    sleep=time.sleep,
) -> GhResult:
    """Run `gh <args>` non-interactively. Never raises for a non-zero exit.

    The LOW level. It hands back a GhResult whose `.stdout` refuses, so the
    caller chooses where the failure surfaces without being able to lose it.

    `repo` appends `--repo <repo>` rather than relying on the cwd's remote,
    because `gh` resolves an ambiguous cwd by PROMPTING, and a prompt with stdin
    closed is a failure whose message names neither the repository nor the fork.

    `attempts` DEFAULTS TO 1, and that is a considered difference from
    `common.sh:_gh_probe`, which always tries three times. Retrying an
    unauthenticated call three times with backoff costs six seconds to learn
    something the first attempt already said. A caller in a merge-blocking gate
    passes `attempts=3` and gets exactly `_gh_probe`'s behaviour; `sleep` is
    injectable so a test can assert the schedule without spending it.
    """
    environ = dict(os.environ if env is None else env)
    environ.update(NONINTERACTIVE)
    argv = ["gh", *args]
    if repo is not None:
        argv += ["--repo", repo]
    result = proc.retry_command(
        argv,
        attempts=attempts,
        sleep=sleep,
        env=environ,
        timeout=timeout,
    )
    return GhResult(
        result.argv,
        result.returncode,
        result.stdout,
        result.stderr,
        timed_out=result.timed_out,
        duration=result.duration,
    )


def version(env: dict[str, str] | None = None) -> str:
    """The `gh version X.Y.Z` first line. Raises when gh is absent or broken."""
    return gh(["--version"], env=env, timeout=10).lines()[0]


def auth_state(env: dict[str, str] | None = None) -> str:
    """Tri-state: authenticated, unauthenticated, or unknown.

    THREE VALUES, NOT A BOOLEAN, for the reason `gitx.is_ancestor` gives about
    ancestry: a probe that could not run is not an answer of "no". `gh` absent,
    or a timeout, or an exit this module cannot classify, all mean the question
    was not answered -- and a caller that treats "unknown" as "unauthenticated"
    will tell a human to log in when the real problem is that gh is not
    installed.

    `gh auth status` exits 1 with "You are not logged into any GitHub hosts"
    (measured 2026-09-06), which classifies as unauthenticated through the
    stderr markers rather than through the exit code.
    """
    result = gh(["auth", "status"], env=env, timeout=20)
    if result.ok:
        return AUTH_AUTHENTICATED
    if result.failure == FAILURE_UNAUTHENTICATED:
        return AUTH_UNAUTHENTICATED
    return AUTH_UNKNOWN


def api_json(
    path: str,
    *,
    paginate: bool = False,
    jq: str | None = None,
    env: dict[str, str] | None = None,
    attempts: int = 1,
    timeout: float = DEFAULT_TIMEOUT,
    sleep=time.sleep,
) -> object:
    """`gh api <path>`, checked then parsed. Raises rather than returning a default.

    NO `method` ARGUMENT. This is a read, and the absence of the parameter is
    what keeps it one: a write has to be spelled out through `gh()` at a call
    site, where a reviewer sees the verb, instead of appearing as one extra
    keyword on a line that already looked harmless.

    `--paginate` WITH `--jq` IS THE COMBINATION THAT DOES NOT PRODUCE ONE JSON
    DOCUMENT: gh concatenates each page's jq output, so the result is a stream of
    values rather than an array, and `json.loads` on it fails. It is refused here
    with a sentence rather than left to surface as a confusing parse error.
    """
    if paginate and jq is not None:
        raise ValueError(
            "gh --paginate with --jq emits one jq result PER PAGE, which is a value "
            "stream and not a JSON document. Paginate without --jq and filter in "
            "Python, or page explicitly."
        )
    args = ["api", path]
    if paginate:
        args.append("--paginate")
    if jq is not None:
        args += ["--jq", jq]
    return gh(args, env=env, timeout=timeout, attempts=attempts, sleep=sleep).json()


def pr_list(
    *,
    repo: str | None = None,
    state: str = "open",
    head: str | None = None,
    author: str | None = None,
    limit: int = 100,
    fields: tuple[str, ...] = ("number", "title", "headRefName", "state", "isDraft"),
    env: dict[str, str] | None = None,
    attempts: int = 1,
    sleep=time.sleep,
) -> list[dict]:
    """Pull requests as dicts. RAISES on a failed call; [] means genuinely none.

    The return type carries the whole rule: there is no value of this function
    that means "I could not ask". `.claude/rediacc_hooks/guards/block_second_open_pr.py:64-72`
    reaches the same conclusion in bash and says why -- "An unreadable list is
    not evidence that the list is empty" -- and fails closed. A Python caller
    gets that for free here, because the alternative to catching the exception is
    propagating it, not ignoring it.
    """
    if not fields:
        raise ValueError("pr_list needs at least one --json field; gh rejects an empty set")
    args = ["pr", "list", "--state", state, "--limit", str(limit), "--json", ",".join(fields)]
    if head is not None:
        args += ["--head", head]
    if author is not None:
        args += ["--author", author]
    return gh(args, repo=repo, env=env, attempts=attempts, sleep=sleep).json_list()


def pr_head_refs(
    *,
    repo: str | None = None,
    state: str = "all",
    limit: int = 100,
    env: dict[str, str] | None = None,
    attempts: int = 1,
    sleep=time.sleep,
) -> list[str]:
    """Every PR's head branch name. Raises on a failed call.

    `state="all"` IS THE DEFAULT HERE AND IT IS THE WHOLE POINT. A merged PR's
    branch is deleted, so `git branch -r` cannot see the name it consumed -- the
    guard at block_nonstandard_branch_name.py:227-229 says so in as many words.
    Only the PR list remembers.
    """
    rows = pr_list(
        repo=repo,
        state=state,
        limit=limit,
        fields=("headRefName",),
        env=env,
        attempts=attempts,
        sleep=sleep,
    )
    return [str(row["headRefName"]) for row in rows if row.get("headRefName")]


def branch_indexes(
    day: str,
    *,
    repo: str | None = None,
    limit: int = 100,
    env: dict[str, str] | None = None,
    attempts: int = 1,
    sleep=time.sleep,
) -> set[int]:
    """The N's already used by `MMDD-N` branches for `day`. TRAP 2, with the failure kept.

    A SET, and an empty set is a real answer that only ever means "no branch for
    this day yet". The failure arrives as an exception. That is the entire
    difference from the shell pipeline this replaces, and the difference is worth
    a whole function because the pipeline's two outcomes are byte-identical.

    `day` is validated. `branch_indexes("0826-1")` -- passing a branch where a day
    belongs -- would otherwise match nothing and answer "no branches today", which
    is the same wrong answer by a different route.
    """
    if not _DAY_RE.match(day):
        raise ValueError("day must be MMDD, four digits (got %r)" % day)
    prefix = day + "-"
    out: set[int] = set()
    for ref in pr_head_refs(
        repo=repo, state="all", limit=limit, env=env, attempts=attempts, sleep=sleep
    ):
        if not ref.startswith(prefix):
            continue
        tail = ref[len(prefix) :]
        # EXACT, not a prefix match. `0826-1-fixup` is not index 1 and must not be read as one: the repo's own convention forbids the suffix, so a ref carrying one is somebody else's mistake and cannot be allowed to collapse onto a legitimate name.
        if tail.isdigit():
            out.add(int(tail))
    return out


def next_branch_name(
    day: str,
    *,
    repo: str | None = None,
    limit: int = 100,
    env: dict[str, str] | None = None,
    attempts: int = 1,
    sleep=time.sleep,
) -> str:
    """`MMDD-N` with N one past the highest already used. Raises if gh cannot answer.

    Never returns `MMDD-0` and never returns a name it could not verify. Both of
    those are the 2026-08-26 duplicate in different clothes.
    """
    used = branch_indexes(day, repo=repo, limit=limit, env=env, attempts=attempts, sleep=sleep)
    return "%s-%d" % (day, (max(used) if used else 0) + 1)


def secret_names(
    *,
    org: str | None = None,
    repo: str | None = None,
    env: dict[str, str] | None = None,
    attempts: int = 1,
    sleep=time.sleep,
) -> list[str]:
    """The NAMES of the configured secrets. Never their values -- see `secret_value`.

    Sorted, so two enumerations are comparable; `check_bws_map.py` compares
    exactly this kind of set and a caller diffing git's order against a Python
    set would see churn that is not there.
    """
    if (org is None) == (repo is None):
        raise ValueError("secret_names needs exactly one of org= or repo=")
    args = ["secret", "list"]
    if org is not None:
        args += ["--org", org]
    result = gh(args, repo=repo, env=env, attempts=attempts, sleep=sleep)
    names = []
    for line in result.lines():
        # `gh secret list` is TAB separated: NAME, updated-at, and for an org also the visibility. Split on whitespace and a name is still the first field, so this survives the column set changing between gh releases -- which it has.
        first = line.split()[0] if line.split() else ""
        if first:
            names.append(first)
    return sorted(names)


def secret_value(name: str) -> str:
    """ALWAYS RAISES. A GitHub secret's value cannot be read back, by design.

    This function exists so that reaching for it produces the REASON rather than
    an AttributeError, because the last time somebody in this repository needed a
    write-only secret locally they went looking for an endpoint that would serve
    it, found a URL that answered 404, and piped the answer into a build:
    `ACCOUNT_ED25519_PUBLIC_KEY` ended up empty (with `curl -f`) or holding the
    404's HTML body (without it), the build succeeded either way, and every
    production-signed licence failed as `invalid_signature`
    (docs/dev-environments.md:102-110, scripts/gates/check-external-links.ts:174-186).

    THE ANSWER IS NOT A DIFFERENT URL. There is no live endpoint, and
    `.ci/scripts/quality/check_bws_map.py:69-73` records the mirror image on the
    write side: `gh secret set` cannot re-supply a value it is forbidden to read.
    CI references the secret directly as `${{ secrets.NAME }}`; locally the value
    is pasted by the operator, from the password store, once.
    """
    raise SecretValueUnavailableError(
        "GitHub secrets are WRITE-ONLY: no gh command, no API route and no URL can "
        "return the value of %r. Do not substitute an HTTP response for it -- that "
        "is how an empty ACCOUNT_ED25519_PUBLIC_KEY reached a production build and "
        "every signed licence failed as invalid_signature "
        "(docs/dev-environments.md:102-110). In CI reference ${{ secrets.%s }} "
        "directly; locally ask the operator to paste it." % (name, name)
    )


# --------------------------------------------------------------------------- argv dispatch -- the surface a shell caller uses instead of a pipeline ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    """Verbs for shell callers. A FAILURE IS A NON-ZERO EXIT WITH STDERR, never empty stdout.

    That is the contract the pipeline in block_nonstandard_branch_name.py cannot
    offer: `python3 -m rediacc_ci.core.ghx next-branch-name 0826` either prints a
    name and exits 0, or prints nothing on stdout, the reason on stderr, and
    exits non-zero. `name="$(...)" || handle-it` then works, and `set -o pipefail`
    is not required for it to work.
    """
    if not argv:
        print("usage: python3 -m rediacc_ci.core.ghx <verb> [args]", file=sys.stderr)
        return 2
    verb, rest = argv[0], argv[1:]
    try:
        if verb == "version":
            print(version())
            return 0
        if verb == "auth-state":
            print(auth_state())
            return 0
        if verb == "next-branch-name":
            if not rest:
                print("usage: next-branch-name <MMDD> [repo]", file=sys.stderr)
                return 2
            print(next_branch_name(rest[0], repo=rest[1] if len(rest) > 1 else None))
            return 0
        if verb == "pr-head-refs":
            for ref in pr_head_refs(repo=rest[0] if rest else None):
                print(ref)
            return 0
    except GhError as exc:
        print("gh: %s" % exc, file=sys.stderr)
        return 1
    except (ValueError, SecretValueUnavailableError) as exc:
        print("gh: %s" % exc, file=sys.stderr)
        return 2

    print("unknown verb: %s" % verb, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))


__all__ = [
    "AUTH_AUTHENTICATED",
    "AUTH_FAILED_RC",
    "AUTH_UNAUTHENTICATED",
    "AUTH_UNKNOWN",
    "DEFAULT_TIMEOUT",
    "FAILURE_FAILED",
    "FAILURE_NOT_INSTALLED",
    "FAILURE_RATE_LIMITED",
    "FAILURE_TIMED_OUT",
    "FAILURE_UNAUTHENTICATED",
    "NONINTERACTIVE",
    "NOT_INSTALLED_RC",
    "GhBadOutputError",
    "GhError",
    "GhNotInstalledError",
    "GhRateLimitedError",
    "GhResult",
    "GhUnauthenticatedError",
    "SecretValueUnavailableError",
    "api_json",
    "auth_state",
    "branch_indexes",
    "gh",
    "main",
    "next_branch_name",
    "pr_head_refs",
    "pr_list",
    "secret_names",
    "secret_value",
    "version",
    "which_gh",
]
