"""check:ci-bws-pr-path -- a job that runs on a pull request never fetches a release credential and never holds an OIDC grant.

WHY THIS EXISTS. `rediacc/console` is public. On a `pull_request` event GitHub runs the workflow files, the local reusable workflows and every script under `.ci/` from the PR's merge commit, with the repository's one secret (`BWS_ACCESS_TOKEN`) in reach, and every credential flows from Bitwarden through `.github/actions/bws-secrets`. A job on that path that fetches a production credential hands it to PR-controlled code. agent/plans/PLAN-pr-path-ephemeral-credentials.md (D7) replaces each such fetch with a throwaway credential and adds this gate so the shape cannot come back.

THE CLASSES are `.ci/config/bws-pr-path.json`: every store name is `pr-safe` or `release-only`, each with a reason, and a `release-only` reason starts with `BLOCKER:` and passes `rediacc_ci.core.allowlist.validate_reason`. The gate refuses:

  (i)   a `release-only` name requested by a bws-secrets step of a job reachable on a
        pull request. Reachability starts at every workflow triggered by `pull_request`
        (and by `pull_request_target` when it checks out the PR head), follows `uses:
        ./.github/workflows/*.yml` callers into reusable workflows with the caller's
        `with:` values as `inputs`, and drops a job or step only when its `if:` is
        DEFINITELY false on that event.
  (ii)  a store name with no class: every name in `.ci/config/bws-secret-map.json` and
        every name any bws-secrets block requests. A classed name the map does not
        hold is a dead entry and refused the same way.
  (iii) `id-token: write` (or `write-all`) in the effective permissions of a job
        reachable on a pull request, caller jobs included.

THE CONDITION EVALUATOR IS THREE-VALUED on purpose. It knows `github.event_name` (the triggering event), that `github.ref` is a `refs/pull/` ref, a reusable workflow's `inputs` (caller `with:` values, else the declared default), and `always()`. Everything else (`needs.*`, `steps.*`, `matrix.*`, `vars.*`, `success()`, a root workflow's `inputs`) is UNKNOWN, and an UNKNOWN condition keeps the job: a gate that drops a job it cannot rule out has a false negative where a credential leaks, which is the expensive direction. `&&` and `||` carry
both a value and a truth, so `always() && ... && github.event_name == 'push'` is false and `github.event_name == 'pull_request' && 'ephemeral' || 'release'` is `'ephemeral'`. A job whose `needs:` include a job that cannot run is dropped unless its `if:` names a status function other than `success()`.

THE BASELINE IS SHRINK-ONLY, and it is the plan's oracle. The fetches present when the gate landed sit in the config's `baseline` as stable ids: the first 12 hex of sha256 over `rule|call chain|name`, never a line number, so a moved block keeps its id and a renamed job or a new caller is a new finding a human looks at. A finding not in the baseline fails ("Do not add it to the baseline"); a baseline id no finding produces fails too, telling the author to drain with `--write-baseline`. `--write-baseline` ONLY REMOVES: it refuses while any finding is outside the baseline, so it cannot enshrine a fresh one, and it prints the removed ids. W3-W6 drive the baseline to zero. Rule (ii) is never baselined.

ANTI-VACUITY. No workflow triggered on a pull request, fewer reachable jobs than `MIN_PR_JOBS`, no bws-secrets fetch on the PR path, an empty class file, an unreadable secret map, or a reusable workflow that cannot be resolved is a failure, never a pass. The success line prints roots, reachable jobs, fetch steps, requested names by class and the baseline size so a collapse is visible.

THE PARSE IS SHARED, NOT RE-TYPED. The `NAME > ENV` grammar is `rediacc_ci.quality.bws_map.parse_requests` and the line-mapped step list is `rediacc_ci.quality.bws_step_scope.scan_jobs`, both imported; the YAML is `rediacc_ci.workflows`. The test drives `verdict` against fixture trees through its keyword arguments, so the CLI has no seam that could point a plain run at another tree.

---- gate ----
step: Bitwarden PR-path credentials
needs: none
selftest: true
lane: quality-security
why: the repository is public and a pull_request run executes PR-controlled code with
     the store token in reach. This refuses a release-only credential fetch, or an
     OIDC grant, on any job a pull request reaches.
---- end gate ----
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import pathlib
import re
import sys
import tempfile
from dataclasses import dataclass, field

from rediacc_ci import paths, workflows
from rediacc_ci.controls import Checker, controls_first, plant
from rediacc_ci.core import allowlist
from rediacc_ci.quality import bws_step_scope, shrink_only

CONFIG_REL = ".ci/config/bws-pr-path.json"
MAP_REL = ".ci/config/bws-secret-map.json"
WORKFLOWS_REL = ".github/workflows"
FETCH_ACTION = "./.github/actions/bws-secrets"
REUSABLE_PREFIX = "./.github/workflows/"

PR_SAFE = "pr-safe"
RELEASE_ONLY = "release-only"
CLASSES = (PR_SAFE, RELEASE_ONLY)

# Jobs reachable on a pull request when the gate landed, counted on the tree: lower it only when PR jobs are deleted.
MIN_PR_JOBS = 40
MIN_CONTROLS = 40
MAX_CALL_DEPTH = 6
CANNOT_RUN = 2

# A `pull_request_target` workflow runs the BASE branch's files, so it is PR-controlled only when it checks the PR head out.
PR_HEAD_RE = re.compile(r"github\.event\.pull_request\.head\.(?:sha|ref)|github\.head_ref")
STATUS_FN_RE = re.compile(r"\b(?:always|failure|cancelled)\s*\(")


class InstrumentError(Exception):
    """The scan cannot produce a verdict: an unparseable file, an unresolvable reusable workflow, an expression it cannot read."""


# --------------------------------------------------------------------------- The three-valued expression evaluator ---------------------------------------------------------------------------


class _Unknown:
    def __repr__(self) -> str:
        return "UNKNOWN"


class _PullRef:
    """`github.ref` on a pull request: some `refs/pull/<n>/merge`, number unknown."""

    def __repr__(self) -> str:
        return "refs/pull/*"


UNKNOWN = _Unknown()
PULL_REF = _PullRef()
PULL_PREFIX = "refs/pull/"


@dataclass(frozen=True)
class Val:
    """An expression result: its value (or UNKNOWN) and its truth (True, False, or None for unknown)."""

    value: object
    truth: bool | None


def _truth_of(value: object) -> bool | None:
    if value is UNKNOWN:
        return None
    if value is PULL_REF:
        return True
    if value is None or value is False:
        return False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, str):
        return value != ""
    return True


def _v(value: object) -> Val:
    return Val(value, _truth_of(value))


_TOKEN_RE = re.compile(
    r"\s*(?:(?P<str>'(?:[^']|'')*')|(?P<num>-?\d+(?:\.\d+)?)|(?P<op>==|!=|<=|>=|&&|\|\||[!<>(),\[\]])"
    r"|(?P<ident>[A-Za-z_][A-Za-z0-9_-]*(?:\.(?:[A-Za-z_*][A-Za-z0-9_-]*|\*))*))"
)


def tokenize(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    pos = 0
    text = text.rstrip()
    while pos < len(text):
        m = _TOKEN_RE.match(text, pos)
        if not m or m.end() == pos:
            msg = "cannot read the expression %r at offset %d" % (text, pos)
            raise InstrumentError(msg)
        kind = m.lastgroup or ""
        out.append((kind, m.group(kind)))
        pos = m.end()
        while pos < len(text) and text[pos].isspace():
            pos += 1
    return out


@dataclass
class Context:
    """What a condition can know on a pull-request run."""

    event: str
    inputs: dict[str, object] | None  # None for a root workflow: its `inputs` are UNKNOWN

    def ref(self, path: str) -> object:
        low = path.lower()
        if low == "github.event_name":
            return self.event
        if low == "github.ref":
            return PULL_REF
        if low.startswith("inputs."):
            if self.inputs is None:
                return UNKNOWN
            return self.inputs.get(path.split(".", 1)[1], None)
        if low in ("true", "false", "null"):
            return {"true": True, "false": False, "null": None}[low]
        return UNKNOWN


def _num(value: object) -> float | None:
    if value is None or value is False:
        return 0.0
    if value is True:
        return 1.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        if value.strip() == "":
            return 0.0
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _equal(a: object, b: object) -> bool | None:
    if a is UNKNOWN or b is UNKNOWN:
        return None
    if a is PULL_REF or b is PULL_REF:
        other = b if a is PULL_REF else a
        if other is PULL_REF:
            return None
        if isinstance(other, str):
            return None if other.lower().startswith(PULL_PREFIX) else False
        return False
    if isinstance(a, str) and isinstance(b, str):
        return a.lower() == b.lower()
    na, nb = _num(a), _num(b)
    if na is None or nb is None:
        return False
    return na == nb


def _starts_with(a: object, b: object) -> bool | None:
    if not isinstance(b, str):
        return None
    if a is PULL_REF:
        if PULL_PREFIX.startswith(b.lower()):
            return True
        return None if b.lower().startswith(PULL_PREFIX) else False
    if isinstance(a, str):
        return a.lower().startswith(b.lower())
    return None


class _Parser:
    def __init__(self, tokens: list[tuple[str, str]], ctx: Context, src: str) -> None:
        self.t = tokens
        self.i = 0
        self.ctx = ctx
        self.src = src

    def _peek(self) -> str | None:
        return self.t[self.i][1] if self.i < len(self.t) else None

    def _take(self, want: str | None = None) -> tuple[str, str]:
        if self.i >= len(self.t):
            msg = "the expression %r ends early" % self.src
            raise InstrumentError(msg)
        tok = self.t[self.i]
        if want is not None and tok[1] != want:
            msg = "the expression %r has %r where %r was expected" % (self.src, tok[1], want)
            raise InstrumentError(msg)
        self.i += 1
        return tok

    def parse(self) -> Val:
        v = self._or()
        if self.i != len(self.t):
            msg = "the expression %r has trailing tokens from %r" % (self.src, self.t[self.i][1])
            raise InstrumentError(msg)
        return v

    def _or(self) -> Val:
        left = self._and()
        while self._peek() == "||":
            self._take()
            right = self._and()
            if left.truth is True:
                continue
            if left.truth is False:
                left = right
                continue
            truth = True if right.truth is True else None
            left = Val(UNKNOWN, truth)
        return left

    def _and(self) -> Val:
        left = self._unary()
        while self._peek() == "&&":
            self._take()
            right = self._unary()
            if left.truth is False:
                continue
            if left.truth is True:
                left = right
                continue
            truth = False if right.truth is False else None
            left = Val(UNKNOWN, truth)
        return left

    def _unary(self) -> Val:
        if self._peek() == "!":
            self._take()
            v = self._unary()
            return _v(UNKNOWN) if v.truth is None else _v(not v.truth)
        return self._cmp()

    def _cmp(self) -> Val:
        left = self._primary()
        op = self._peek()
        if op in ("==", "!=", "<", ">", "<=", ">="):
            self._take()
            right = self._primary()
            if op in ("==", "!="):
                eq = _equal(left.value, right.value)
                if eq is None:
                    return _v(UNKNOWN)
                return _v(eq if op == "==" else not eq)
            return _v(UNKNOWN)
        return left

    def _primary(self) -> Val:
        kind, text = self._take()
        if kind == "str":
            return _v(text[1:-1].replace("''", "'"))
        if kind == "num":
            return _v(float(text))
        if text == "(":
            v = self._or()
            self._take(")")
            return v
        if kind != "ident":
            msg = "the expression %r has an unexpected %r" % (self.src, text)
            raise InstrumentError(msg)
        if self._peek() == "(":
            self._take("(")
            args: list[Val] = []
            while self._peek() != ")":
                args.append(self._or())
                if self._peek() == ",":
                    self._take(",")
            self._take(")")
            return self._call(text.lower(), args)
        value: object = self.ctx.ref(text)
        while self._peek() == "[":
            self._take("[")
            self._or()
            self._take("]")
            value = UNKNOWN
        return _v(value)

    @staticmethod
    def _call(name: str, args: list[Val]) -> Val:
        if name == "always":
            return _v(True)
        if name == "startswith" and len(args) == 2:
            r = _starts_with(args[0].value, args[1].value)
            return _v(UNKNOWN if r is None else r)
        if name == "contains" and len(args) == 2:
            a, b = args[0].value, args[1].value
            if isinstance(a, str) and isinstance(b, str):
                return _v(b.lower() in a.lower())
        return _v(UNKNOWN)


def strip_wrapper(text: str) -> str:
    m = re.fullmatch(r"\s*\$\{\{\s*(.*?)\s*\}\}\s*", text, re.DOTALL)
    return m.group(1) if m else text


def evaluate(expr: object, ctx: Context) -> Val:
    """Evaluate an `if:` value. A YAML boolean or number is its own value; a missing condition is true."""
    if expr is None:
        return _v(True)
    if isinstance(expr, bool):
        return _v(expr)
    if isinstance(expr, (int, float)):
        return _v(expr)
    src = strip_wrapper(str(expr))
    return _Parser(tokenize(src), ctx, src).parse()


def interpolate(value: object, ctx: Context) -> object:
    """A `with:` value as the callee sees it: a literal, a whole `${{ expr }}`'s value, or a mixed string when every part is known."""
    if not isinstance(value, str):
        return value
    if "${{" not in value:
        return value
    whole = re.fullmatch(r"\s*\$\{\{\s*(.*?)\s*\}\}\s*", value, re.DOTALL)
    if whole and "${{" not in whole.group(1):
        return evaluate(value, ctx).value
    out: list[str] = []
    pos = 0
    for m in re.finditer(r"\$\{\{(.*?)\}\}", value, re.DOTALL):
        out.append(value[pos : m.start()])
        part = evaluate(m.group(1), ctx).value
        if part is UNKNOWN or part is PULL_REF:
            return UNKNOWN
        out.append(
            "" if part is None else str(part).lower() if isinstance(part, bool) else str(part)
        )
        pos = m.end()
    out.append(value[pos:])
    return "".join(out)


# --------------------------------------------------------------------------- Reachability ---------------------------------------------------------------------------


@dataclass
class Fetch:
    chain: str
    file: str
    line: int
    step: str
    name: str


@dataclass
class Grant:
    chain: str
    file: str
    what: str


@dataclass
class Scan:
    roots: list[str] = field(default_factory=list)
    jobs: list[str] = field(default_factory=list)
    fetch_steps: int = 0
    fetches: list[Fetch] = field(default_factory=list)
    grants: list[Grant] = field(default_factory=list)


def _triggers(doc: dict) -> list[str]:
    on = doc.get("on", doc.get(True))
    if isinstance(on, str):
        return [on]
    if isinstance(on, list):
        return [str(x) for x in on]
    if isinstance(on, dict):
        return [str(k) for k in on]
    return []


def pr_event(doc: dict, text: str) -> str | None:
    """The PR event this root runs PR-controlled code on, or None."""
    trig = _triggers(doc)
    if "pull_request" in trig:
        return "pull_request"
    if "pull_request_target" in trig and PR_HEAD_RE.search(text):
        return "pull_request_target"
    return None


def _grants_id_token(perms: object) -> str | None:
    if isinstance(perms, str):
        return "permissions: write-all" if perms.strip() == "write-all" else None
    if isinstance(perms, dict) and str(perms.get("id-token", "")).strip() == "write":
        return "id-token: write"
    return None


def _needs(body: dict) -> list[str]:
    n = body.get("needs")
    if isinstance(n, str):
        return [n]
    if isinstance(n, list):
        return [str(x) for x in n]
    return []


def _callee_inputs(callee_doc: dict, given: dict[str, object]) -> dict[str, object]:
    on = callee_doc.get("on", callee_doc.get(True))
    call = on.get("workflow_call") if isinstance(on, dict) else None
    declared = (call or {}).get("inputs") if isinstance(call, dict) else None
    out: dict[str, object] = {}
    if isinstance(declared, dict):
        for name, raw_spec in declared.items():
            spec = raw_spec if isinstance(raw_spec, dict) else {}
            if "default" in spec:
                out[name] = spec["default"]
            else:
                out[name] = False if spec.get("type") == "boolean" else ""
    out.update(given)
    return out


class Walker:
    def __init__(self, workflow_dir: pathlib.Path, rel_base: pathlib.Path) -> None:
        self.dir = workflow_dir
        self.rel_base = rel_base
        self.cache: dict[str, tuple[dict, str, dict]] = {}
        self.scan = Scan()

    def label(self, path: pathlib.Path) -> str:
        try:
            return str(path.resolve().relative_to(self.rel_base.resolve()))
        except ValueError:
            return str(path)

    def load(self, path: pathlib.Path) -> tuple[dict, str, dict]:
        key = str(path)
        if key not in self.cache:
            label = self.label(path)
            try:
                text = path.read_text(encoding="utf-8")
                doc = workflows.parse(text)
            except OSError as exc:
                msg = "%s cannot be read (%s)" % (label, exc)
                raise InstrumentError(msg) from exc
            except (workflows.WorkflowParseError, workflows.UnsupportedYAMLError) as exc:
                msg = "%s: %s" % (label, exc)
                raise InstrumentError(msg) from exc
            if not isinstance(doc, dict):
                doc = {}
            try:
                steps = {j.job_id: j for j in bws_step_scope.scan_jobs(text, label)}
            except bws_step_scope.InstrumentError as exc:
                raise InstrumentError(str(exc)) from exc
            self.cache[key] = (doc, text, steps)
        return self.cache[key]

    def walk_root(self, path: pathlib.Path) -> None:
        doc, text, _steps = self.load(path)
        event = pr_event(doc, text)
        if event is None:
            return
        self.scan.roots.append(self.label(path))
        self.walk(path, Context(event, None), "", 0)

    def walk(self, path: pathlib.Path, ctx: Context, prefix: str, depth: int) -> None:
        if depth > MAX_CALL_DEPTH:
            msg = "%s: reusable workflow nesting deeper than %d; a call cycle?" % (
                prefix,
                MAX_CALL_DEPTH,
            )
            raise InstrumentError(msg)
        doc, _text, steps = self.load(path)
        label = self.label(path)
        jobs = doc.get("jobs")
        if not isinstance(jobs, dict):
            return
        wf_perms = doc.get("permissions")
        possible: dict[str, bool] = {}

        def runs(job_id: str, seen: tuple[str, ...] = ()) -> bool:
            if job_id in possible:
                return possible[job_id]
            body = jobs.get(job_id)
            if not isinstance(body, dict) or job_id in seen:
                possible[job_id] = isinstance(body, dict)
                return possible[job_id]
            cond = body.get("if")
            ok = evaluate(cond, ctx).truth is not False
            if ok and not STATUS_FN_RE.search(str(cond or "")):
                ok = all(runs(n, (*seen, job_id)) for n in _needs(body) if n in jobs)
            possible[job_id] = ok
            return ok

        for job_id, body in jobs.items():
            if not isinstance(body, dict) or not runs(job_id):
                continue
            chain = "%s%s:%s" % (prefix, label, job_id)
            self.scan.jobs.append(chain)
            perms = body.get("permissions", wf_perms)
            what = _grants_id_token(perms)
            if what:
                self.scan.grants.append(Grant(chain, label, what))
            uses = body.get("uses")
            if isinstance(uses, str):
                if not uses.startswith(REUSABLE_PREFIX):
                    msg = (
                        "%s calls the remote reusable workflow %r, which this gate cannot read; "
                        "its fetches would go unchecked" % (chain, uses)
                    )
                    raise InstrumentError(msg)
                callee = self.dir / uses[len(REUSABLE_PREFIX) :].split("@", 1)[0]
                if not callee.is_file():
                    msg = "%s calls %s, which does not exist under %s" % (
                        chain,
                        uses,
                        self.label(self.dir),
                    )
                    raise InstrumentError(msg)
                callee_doc = self.load(callee)[0]
                given = {k: interpolate(v, ctx) for k, v in (body.get("with") or {}).items()}
                self.walk(
                    callee,
                    Context(ctx.event, _callee_inputs(callee_doc, given)),
                    chain + " > ",
                    depth + 1,
                )
                continue
            job = steps.get(job_id)
            if job is None:
                continue
            for step in job.steps:
                if not step.uses.startswith(FETCH_ACTION):
                    continue
                if evaluate(step.cond, ctx).truth is False:
                    continue
                self.scan.fetch_steps += 1
                for line, name, _env in step.requests:
                    self.scan.fetches.append(Fetch(chain, label, line, step.label, name))


def reach(workflow_dir: pathlib.Path, rel_base: pathlib.Path) -> Scan:
    w = Walker(workflow_dir, rel_base)
    for path in sorted(workflow_dir.glob("*.yml")):
        w.walk_root(path)
    return w.scan


def requested_anywhere(files: list[pathlib.Path]) -> set[str]:
    out: set[str] = set()
    for f in files:
        out |= {
            name for _l, name, _e in bws_step_scope.parse_requests(f.read_text(encoding="utf-8"))
        }
    return out


# --------------------------------------------------------------------------- Config, findings, verdict ---------------------------------------------------------------------------


def finding_id(rule: str, chain: str, subject: str) -> str:
    """The stable baseline id: no line number, so a moved block keeps it."""
    return hashlib.sha256(("%s|%s|%s" % (rule, chain, subject)).encode("utf-8")).hexdigest()[:12]


@dataclass
class Finding:
    rule: str
    id: str
    text: str


@dataclass
class Config:
    classes: dict[str, str]
    baseline: list[str]
    problems: list[str]
    # `file:job` -> reason: a job named by an operator ruling that holds `id-token: write` on purpose (rule (iii) only).
    id_token_exemptions: dict[str, str] = field(default_factory=dict)


def load_config(path: pathlib.Path, label: str) -> Config:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return Config(
            {},
            [],
            ["%s cannot be read (%s); the gate has nothing to hold the tree to" % (label, exc)],
        )
    names = doc.get("names") if isinstance(doc, dict) else None
    if not isinstance(names, dict) or not names:
        return Config(
            {}, [], ["%s has no `names` object, or it is empty; refusing to pass vacuously" % label]
        )
    problems: list[str] = []
    classes: dict[str, str] = {}
    for name, raw_rec in names.items():
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
            problems.append("%s: %r is not a Bitwarden secret name" % (label, name))
            continue
        rec = raw_rec if isinstance(raw_rec, dict) else {}
        cls = rec.get("class")
        reason = rec.get("reason")
        if cls not in CLASSES:
            problems.append(
                "%s: %s has class %r; it must be one of %s" % (label, name, cls, ", ".join(CLASSES))
            )
            continue
        if not isinstance(reason, str):
            problems.append("%s: %s has no `reason`" % (label, name))
            continue
        body = reason
        if cls == RELEASE_ONLY:
            if not reason.startswith("BLOCKER:"):
                problems.append(
                    "%s: %s is release-only and its reason does not start with 'BLOCKER:'"
                    % (label, name)
                )
                continue
            body = reason[len("BLOCKER:") :]
        rejection = allowlist.validate_reason(name, body, label)
        if rejection is not None:
            problems.append(rejection.message)
            continue
        classes[name] = cls
    base = doc.get("baseline") if isinstance(doc, dict) else None
    ids = base.get("ids") if isinstance(base, dict) else None
    if not isinstance(ids, list) or not all(isinstance(x, str) for x in ids):
        problems.append(
            "%s: `baseline.ids` must be a list of finding ids (an empty list once drained)" % label
        )
        ids = []
    exemptions: dict[str, str] = {}
    raw_ex = doc.get("id_token_exemptions", {}) if isinstance(doc, dict) else {}
    if not isinstance(raw_ex, dict):
        problems.append(
            "%s: `id_token_exemptions` must be an object of `file:job` -> reason" % label
        )
        raw_ex = {}
    for job, reason in raw_ex.items():
        if not re.fullmatch(r"\.github/workflows/[A-Za-z0-9_.-]+\.yml:[A-Za-z0-9_-]+", job):
            problems.append(
                "%s: id_token_exemptions key %r is not a `workflow-file:job` reference"
                % (label, job)
            )
            continue
        if not isinstance(reason, str) or not reason.startswith("BLOCKER:"):
            problems.append(
                "%s: the id_token_exemptions reason for %s must be a string starting with 'BLOCKER:'"
                % (label, job)
            )
            continue
        rejection = allowlist.validate_reason(job, reason[len("BLOCKER:") :], label)
        if rejection is not None:
            problems.append(rejection.message)
            continue
        exemptions[job] = reason
    return Config(classes, list(ids), problems, exemptions)


def rule_ii(
    classes: dict[str, str], mapped: set[str], requested: set[str], label: str
) -> list[str]:
    out = [
        "rule (ii): %s is %s but has no class in %s. Fix: add it with `class` pr-safe or release-only and a reason "
        "(release-only reasons start with 'BLOCKER:'); when unsure it is release-only."
        % (name, "in %s" % MAP_REL if name in mapped else "requested by a bws-secrets block", label)
        for name in sorted((mapped | requested) - set(classes))
    ]
    out += [
        "rule (ii): %s is classed in %s but %s does not hold it; a dead entry. Fix: delete it."
        % (name, label, MAP_REL)
        for name in sorted(set(classes) - mapped)
    ]
    return out


def _chain_ends_at(chain: str, job: str) -> bool:
    """True when the last hop of a ` > `-joined call chain is `job` (`file:job`)."""
    return chain.rsplit(" > ", maxsplit=1)[-1] == job


def findings(scan: Scan, classes: dict[str, str]) -> list[Finding]:
    """Rules (i) and (iii): one finding per (call chain, name) and per granting chain."""
    out: dict[str, Finding] = {}
    for f in scan.fetches:
        if classes.get(f.name) != RELEASE_ONLY:
            continue
        fid = finding_id("i", f.chain, f.name)
        if fid in out:
            continue
        out[fid] = Finding(
            "i",
            fid,
            "rule (i) [%s] %s:%d job %s: the step %r fetches %s, which %s classes release-only, on a pull-request "
            "run. Fix: guard the fetch on the event (or the caller's input) so a PR run never reaches it, and give the PR "
            "path a throwaway credential instead."
            % (fid, f.file, f.line, f.chain, f.step, f.name, CONFIG_REL),
        )
    for g in scan.grants:
        fid = finding_id("iii", g.chain, "id-token")
        if fid in out:
            continue
        out[fid] = Finding(
            "iii",
            fid,
            "rule (iii) [%s] %s job %s grants %s and runs on a pull request, so PR code can mint an OIDC token. "
            "Fix: split the job so the PR variant carries no id-token grant."
            % (fid, g.file, g.chain, g.what),
        )
    return list(out.values())


@dataclass
class Outcome:
    rc: int
    stdout: list[str]
    stderr: list[str]
    current: list[Finding] = dataclasses.field(default_factory=list)
    baseline: list[str] = dataclasses.field(default_factory=list)


def _rel(path: pathlib.Path, root: pathlib.Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def evaluate_tree(
    root: pathlib.Path,
    *,
    workflow_dir: pathlib.Path | None = None,
    config_path: pathlib.Path | None = None,
    map_path: pathlib.Path | None = None,
    extra_files: list[pathlib.Path] | None = None,
    min_jobs: int = MIN_PR_JOBS,
) -> Outcome:
    """The whole judgement, returned rather than printed, so the selftest and pytest drive the real logic on fixtures."""
    wf_dir = workflow_dir or root / WORKFLOWS_REL
    cfg_path = config_path or root / CONFIG_REL
    mp = map_path or root / MAP_REL
    cfg_label = _rel(cfg_path, root)
    cfg = load_config(cfg_path, cfg_label)
    problems = list(cfg.problems)
    try:
        mapped = set(json.loads(mp.read_text(encoding="utf-8")).get("secrets") or {})
    except (OSError, ValueError, AttributeError) as exc:
        return Outcome(
            CANNOT_RUN,
            [],
            [
                "✗ %s cannot be read (%s); an unclassed name cannot be told apart"
                % (_rel(mp, root), exc)
            ],
        )
    if not mapped:
        return Outcome(
            CANNOT_RUN,
            [],
            ["✗ %s lists no secrets; the class check would pass vacuously" % _rel(mp, root)],
        )

    try:
        scan = reach(wf_dir, root)
        corpus = sorted(wf_dir.glob("*.yml"))
        if workflow_dir is None:
            corpus = workflows.call_sites(root)
        requested = requested_anywhere(corpus + list(extra_files or []))
    except InstrumentError as exc:
        return Outcome(CANNOT_RUN, [], ["✗ instrument: %s" % exc])

    problems += rule_ii(cfg.classes, mapped, requested, cfg_label)
    # Rule (iii) exemptions: a grant whose call chain ENDS at an exempted job is held on purpose. A caller job that carries the
    # same grant for it is exempted by naming it too (a called workflow holds no more than its caller). An exemption no grant matches is a dead entry and refused, so a deleted job cannot leave a standing pass.
    matched = {
        j for j in cfg.id_token_exemptions for g in scan.grants if _chain_ends_at(g.chain, j)
    }
    problems += [
        "id_token_exemptions entry %s in %s matches no id-token grant on a pull-request job; a dead entry. Fix: delete it."
        % (j, cfg_label)
        for j in sorted(set(cfg.id_token_exemptions) - matched)
    ]
    scan.grants = [
        g
        for g in scan.grants
        if not any(_chain_ends_at(g.chain, j) for j in cfg.id_token_exemptions)
    ]
    current = findings(scan, cfg.classes)
    base = set(cfg.baseline)
    new = [f for f in current if f.id not in base]
    fixed = sorted(base - {f.id for f in current})
    problems += [f.text + " Do not add it to the baseline." for f in new]
    problems += [
        "baseline id %s in %s is no longer produced: the fetch or grant it froze is gone. Drain it with "
        "`PYTHONPATH=.ci python3 -m rediacc_ci.quality.bws_pr_path --write-baseline`, which only removes ids."
        % (i, cfg_label)
        for i in fixed
    ]
    if not scan.roots:
        problems.append(
            "no workflow under %s runs on a pull request; the gate is not seeing the tree, and its green would mean nothing"
            % _rel(wf_dir, root)
        )
    elif len(scan.jobs) < min_jobs:
        problems.append(
            "only %d job(s) reachable on a pull request, floor is %d; the walk lost its subject, or PR jobs were deleted "
            "(lower MIN_PR_JOBS only then)" % (len(scan.jobs), min_jobs)
        )
    if scan.roots and scan.fetch_steps == 0:
        problems.append(
            "no bws-secrets fetch is reachable on a pull request; the scan lost its subject"
        )

    by_class = {
        c: sorted({f.name for f in scan.fetches if cfg.classes.get(f.name) == c}) for c in CLASSES
    }
    baselined = [f for f in current if f.id in base]
    if problems:
        err = ["✗ bws pr path (%d problem(s)):" % len(problems)] + ["    %s" % p for p in problems]
        return Outcome(1, [], err, current, cfg.baseline)
    out = [
        "✓ bws pr path: %d PR root(s), %d reachable job(s) (floor %d), %d fetch step(s) requesting %d pr-safe and %d "
        "release-only name(s); %d of %d store name(s) classed (%d release-only); baseline %d finding(s), none new, none fixed"
        % (
            len(scan.roots),
            len(scan.jobs),
            min_jobs,
            scan.fetch_steps,
            len(by_class[PR_SAFE]),
            len(by_class[RELEASE_ONLY]),
            len(cfg.classes),
            len(mapped),
            sum(1 for c in cfg.classes.values() if c == RELEASE_ONLY),
            len(base),
        )
    ]
    if baselined:
        rules = sorted({f.rule for f in baselined})
        out.append(
            "  Baselined debt still present (%s): %d finding(s) under rule(s) %s; agent/plans/PLAN-pr-path-ephemeral-credentials.md "
            "W3-W6 drain them. Print them with --show-baseline."
            % (CONFIG_REL, len(baselined), ", ".join("(%s)" % r for r in rules))
        )
    return Outcome(0, out, [], current, cfg.baseline)


def write_baseline(
    root: pathlib.Path,
    *,
    workflow_dir: pathlib.Path | None = None,
    config_path: pathlib.Path | None = None,
    map_path: pathlib.Path | None = None,
    min_jobs: int = MIN_PR_JOBS,
) -> int:
    """Remove fixed ids from the baseline. Refuses while any finding is outside it, so nothing new is ever absorbed.

    The keyword arguments are `evaluate_tree`'s, for the test's fixture trees; the CLI passes none.
    """
    cfg_path = config_path or root / CONFIG_REL
    res = evaluate_tree(
        root, workflow_dir=workflow_dir, config_path=cfg_path, map_path=map_path, min_jobs=min_jobs
    )
    if res.rc == CANNOT_RUN:
        print("\n".join(res.stderr), file=sys.stderr)
        return CANNOT_RUN
    old = list(res.baseline)
    cur = {f.id for f in res.current}
    added = shrink_only.baseline_additions(old, sorted(cur))
    if (
        shrink_only.write_verdict(baseline_exists=True, first_seed=False, additions=added)
        is not None
    ):
        print(
            "✗ --write-baseline only drains. %d finding(s) are not in the baseline (%s); fix them instead. "
            "Do not add them to the baseline." % (len(added), ", ".join(added)),
            file=sys.stderr,
        )
        return 1
    kept = [i for i in old if i in cur]
    removed = [i for i in old if i not in cur]
    doc = json.loads(cfg_path.read_text(encoding="utf-8"))
    doc["baseline"]["ids"] = kept
    cfg_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        "baseline %d -> %d: removed %s; added none"
        % (len(old), len(kept), ", ".join(removed) or "nothing")
    )
    return 0


def verdict(root: pathlib.Path) -> int:
    res = evaluate_tree(root)
    for line in res.stdout:
        print(line)
    for line in res.stderr:
        print(line, file=sys.stderr)
    return res.rc


# --------------------------------------------------------------------------- Controls ---------------------------------------------------------------------------

FIXTURE_MAP = {
    "secrets": {
        n: {"id": "0"} for n in ("DOCKERHUB_TOKEN", "RELEASE_GPG_PRIVATE_KEY", "PROD_API_TOKEN")
    }
}

FIXTURE_CONFIG = {
    "names": {
        "DOCKERHUB_TOKEN": {
            "class": PR_SAFE,
            "reason": "a read-only registry pull token; a leak costs a rate limit, nothing more",
        },
        "RELEASE_GPG_PRIVATE_KEY": {
            "class": RELEASE_ONLY,
            "reason": "BLOCKER: signs the packages every installed host trusts",
        },
        "PROD_API_TOKEN": {
            "class": RELEASE_ONLY,
            "reason": "BLOCKER: writes the production account database",
        },
    },
    "baseline": {"ids": []},
}

# The fixed shape: a PR root calling a reusable stage whose release-key fetch is guarded by the caller's input, and a push-only caller holding the OIDC grant.
FIXED_CI = """\
name: probe
on:
  push:
    branches: [main]
  pull_request:
jobs:
  init:
    runs-on: ubuntu-latest
    steps:
      - name: Fetch secrets from Bitwarden
        uses: ./.github/actions/bws-secrets
        with:
          access-token: ${{ secrets.BWS_ACCESS_TOKEN }}
          secrets: |
            DOCKERHUB_TOKEN > BWS_DOCKERHUB_TOKEN
      - run: echo ok
  stage:
    needs: [init]
    if: always() && needs.init.result == 'success'
    permissions:
      contents: read
    uses: ./.github/workflows/stage.yml
    with:
      signing: ${{ github.event_name == 'pull_request' && 'ephemeral' || 'release' }}
  release:
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    permissions:
      id-token: write
    runs-on: ubuntu-latest
    steps:
      - name: Fetch the production token
        uses: ./.github/actions/bws-secrets
        with:
          access-token: ${{ secrets.BWS_ACCESS_TOKEN }}
          secrets: |
            PROD_API_TOKEN > BWS_PROD_API_TOKEN
      - run: deploy
  after-release:
    needs: [release]
    runs-on: ubuntu-latest
    steps:
      - name: Fetch the production token again
        uses: ./.github/actions/bws-secrets
        with:
          access-token: ${{ secrets.BWS_ACCESS_TOKEN }}
          secrets: |
            PROD_API_TOKEN > BWS_PROD_API_TOKEN
      - run: verify
"""

FIXED_STAGE = """\
name: stage
on:
  workflow_call:
    inputs:
      signing:
        type: string
        default: release
permissions: {}
jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - name: Fetch the release signing key
        if: inputs.signing == 'release'
        uses: ./.github/actions/bws-secrets
        with:
          access-token: ${{ secrets.BWS_ACCESS_TOKEN }}
          secrets: |
            RELEASE_GPG_PRIVATE_KEY > BWS_RELEASE_GPG_PRIVATE_KEY
      - run: build
"""

# Today's cd-stage shape: the release-key fetch is unguarded, so a PR run reaches it through the caller.
_GUARD = "        if: inputs.signing == 'release'\n"
_PUSH_ONLY = "    if: github.event_name == 'push' && github.ref == 'refs/heads/main'\n"


def plants() -> dict[str, tuple[str, str, dict]]:
    """rule -> (ci.yml, stage.yml, config) that break that rule. Exported for the pytest."""
    cfg_ii = json.loads(json.dumps(FIXTURE_CONFIG))
    del cfg_ii["names"]["PROD_API_TOKEN"]
    return {
        "i": (FIXED_CI, plant(FIXED_STAGE, _GUARD, ""), FIXTURE_CONFIG),
        "ii": (FIXED_CI, FIXED_STAGE, cfg_ii),
        "iii": (
            FIXED_CI,
            plant(
                FIXED_STAGE, "      contents: read\n    steps:", "      id-token: write\n    steps:"
            ),
            FIXTURE_CONFIG,
        ),
    }


def run_fixture(tmp: pathlib.Path, ci: str, stage: str, config: dict) -> Outcome:
    wf = tmp / "workflows"
    wf.mkdir(parents=True, exist_ok=True)
    (wf / "ci.yml").write_text(ci, encoding="utf-8")
    (wf / "stage.yml").write_text(stage, encoding="utf-8")
    (tmp / "config.json").write_text(json.dumps(config), encoding="utf-8")
    (tmp / "map.json").write_text(json.dumps(FIXTURE_MAP), encoding="utf-8")
    return evaluate_tree(
        tmp, workflow_dir=wf, config_path=tmp / "config.json", map_path=tmp / "map.json", min_jobs=1
    )


def fired_rules(lines: list[str]) -> set[str]:
    return set(re.findall(r"rule \((i{1,3})\)", "\n".join(lines)))


def selftest() -> bool:
    """True when a control failed, which is what `controls_first` expects."""
    check = Checker()
    pr = Context("pull_request", None)

    def ev(expr: str, ctx: Context = pr) -> Val:
        return evaluate(expr, ctx)

    check("event_name == 'push' is false on a PR", ev("github.event_name == 'push'").truth is False)
    check(
        "event_name == 'pull_request' is true",
        ev("${{ github.event_name == 'pull_request' }}").truth is True,
    )
    check("event_name != 'push' is true", ev("github.event_name != 'push'").truth is True)
    check("a ref check against main is false", ev("github.ref == 'refs/heads/main'").truth is False)
    check(
        "startsWith(github.ref, 'refs/tags/') is false",
        ev("startsWith(github.ref, 'refs/tags/')").truth is False,
    )
    check(
        "startsWith(github.ref, 'refs/pull/') is true",
        ev("startsWith(github.ref, 'refs/pull/')").truth is True,
    )
    check("needs.* alone is unknown", ev("needs.x.result == 'success'").truth is None)
    check(
        "always() && unknown && push-only is false",
        ev("always() && needs.a.result == 'success' && github.event_name == 'push'").truth is False,
    )
    check(
        "unknown || pull_request is true",
        ev("needs.a.result == 'x' || github.event_name == 'pull_request'").truth is True,
    )
    check(
        "unknown || push is unknown, never false",
        ev("needs.a.result == 'x' || github.event_name == 'push'").truth is None,
    )
    check("!(push) is true", ev("!(github.event_name == 'push')").truth is True)
    check("!unknown is unknown", ev("!cancelled()").truth is None)
    check(
        "the ternary picks 'ephemeral' on a PR",
        ev("github.event_name == 'pull_request' && 'ephemeral' || 'release'").value == "ephemeral",
    )
    check(
        "the ternary picks 'release' on push",
        ev(
            "github.event_name == 'pull_request' && 'ephemeral' || 'release'", Context("push", None)
        ).value
        == "release",
    )
    check(
        "string compare is case-insensitive",
        ev("'Pull_Request' == github.event_name").truth is True,
    )
    check("a root workflow's inputs are unknown", ev("inputs.signing == 'release'").truth is None)
    stage_ctx = Context("pull_request", {"signing": "ephemeral"})
    check("a callee's input is known", ev("inputs.signing == 'release'", stage_ctx).truth is False)
    check(
        "an unpassed boolean input is false",
        ev("inputs.flag", Context("pull_request", {"flag": False})).truth is False,
    )
    check("a bare if: success() is unknown", ev("success()").truth is None)
    check("a YAML false condition is false", evaluate(False, pr).truth is False)
    check("contains() on known strings works", ev("contains('abc', 'B')").truth is True)
    check("index access is unknown", ev("github.event['x'] == 'y'").truth is None)
    check("interpolate keeps a literal", interpolate("release", pr) == "release")
    check(
        "interpolate evaluates a whole expression",
        interpolate("${{ github.event_name == 'pull_request' }}", pr) is True,
    )
    check(
        "interpolate of mixed text with an unknown part is unknown",
        interpolate("v${{ needs.x.outputs.v }}", pr) is UNKNOWN,
    )
    try:
        tokenize("github.event_name == `x`")
        bad = False
    except InstrumentError:
        bad = True
    check("an unreadable expression is an instrument error, not a pass", bad)

    check(
        "finding ids carry no line number",
        finding_id("i", "a.yml:j", "N") == finding_id("i", "a.yml:j", "N"),
    )
    check(
        "a different chain is a different id",
        finding_id("i", "a.yml:j", "N") != finding_id("i", "a.yml:k", "N"),
    )

    with tempfile.TemporaryDirectory() as d:
        base = pathlib.Path(d)
        fixed = run_fixture(base / "fixed", FIXED_CI, FIXED_STAGE, FIXTURE_CONFIG)
        check(
            "the fixed fixture is green (rc=%d, %s)" % (fixed.rc, fixed.stderr[1:2]), fixed.rc == 0
        )
        check(
            "the fixed fixture's success line names one PR root",
            fixed.rc == 0 and "1 PR root(s)" in fixed.stdout[0],
        )
        for rule, (ci, stage, cfg) in plants().items():
            res = run_fixture(base / ("plant-" + rule), ci, stage, cfg)
            got = fired_rules(res.stderr)
            check(
                "plant (%s) is red and names rule (%s) (rc=%d, fired %s)"
                % (rule, rule, res.rc, sorted(got)),
                res.rc == 1 and rule in got,
            )
            check(
                "plant (%s) fires no other rule (%s)" % (rule, sorted(got - {rule})),
                not (got - {rule}),
            )
        # An unguarded release fetch in a push-only job stays silent; the same fetch in a job only `needs:`-gated on it stays silent.
        res = run_fixture(
            base / "nopr", plant(FIXED_CI, "  pull_request:\n", ""), FIXED_STAGE, FIXTURE_CONFIG
        )
        check(
            "a tree with no PR root is a failure, never a pass (rc=%d)" % res.rc,
            res.rc == 1 and "runs on a pull request" in "\n".join(res.stderr),
        )
        res = run_fixture(
            base / "unpruned",
            plant(FIXED_CI, _PUSH_ONLY, "    if: needs.init.result == 'success'\n"),
            FIXED_STAGE,
            FIXTURE_CONFIG,
        )
        check(
            "an unknown job condition keeps the job, so its release fetch fires (i)",
            "i" in fired_rules(res.stderr),
        )
        check("... and its OIDC grant fires (iii)", "iii" in fired_rules(res.stderr))
        res = run_fixture(
            base / "always",
            plant(FIXED_CI, "    needs: [release]\n", "    needs: [release]\n    if: always()\n"),
            FIXED_STAGE,
            FIXTURE_CONFIG,
        )
        check(
            "always() on a job that needs a push-only job keeps it (i)",
            "i" in fired_rules(res.stderr),
        )
        cfg = json.loads(json.dumps(FIXTURE_CONFIG))
        cfg["baseline"]["ids"] = [
            finding_id(
                "i", "workflows/ci.yml:stage > workflows/stage.yml:build", "RELEASE_GPG_PRIVATE_KEY"
            )
        ]
        ci, stage, _ = plants()["i"]
        res = run_fixture(base / "baselined", ci, stage, cfg)
        check("a baselined finding is green (rc=%d, %s)" % (res.rc, res.stderr[1:2]), res.rc == 0)
        res = run_fixture(base / "drained", FIXED_CI, FIXED_STAGE, cfg)
        check(
            "a baselined finding that is fixed reds, asking for a drain",
            res.rc == 1 and "--write-baseline" in "\n".join(res.stderr),
        )
        cfg = json.loads(json.dumps(FIXTURE_CONFIG))
        cfg["names"]["PROD_API_TOKEN"]["reason"] = (
            "writes the production account database, no prefix"
        )
        res = run_fixture(base / "noblocker", FIXED_CI, FIXED_STAGE, cfg)
        check(
            "a release-only reason without BLOCKER: reds",
            res.rc == 1 and "BLOCKER:" in "\n".join(res.stderr),
        )
        cfg = json.loads(json.dumps(FIXTURE_CONFIG))
        cfg["names"]["GONE_TOKEN"] = {
            "class": PR_SAFE,
            "reason": "a token that the store no longer holds at all",
        }
        res = run_fixture(base / "dead", FIXED_CI, FIXED_STAGE, cfg)
        check(
            "a classed name the map lacks is a dead entry (ii)",
            res.rc == 1 and "dead entry" in "\n".join(res.stderr),
        )
        res = run_fixture(
            base / "remote",
            plant(
                FIXED_CI,
                "uses: ./.github/workflows/stage.yml",
                "uses: other/repo/.github/workflows/s.yml@v1",
            ),
            FIXED_STAGE,
            FIXTURE_CONFIG,
        )
        check(
            "a remote reusable workflow cannot be read, so it is an instrument failure (rc=%d)"
            % res.rc,
            res.rc == CANNOT_RUN,
        )
        prt = plant(FIXED_CI, "  pull_request:\n", "  pull_request_target:\n")
        res = run_fixture(base / "prt", prt, FIXED_STAGE, FIXTURE_CONFIG)
        check(
            "pull_request_target without a PR-head checkout is not a PR root",
            res.rc == 1 and "runs on a pull request" in "\n".join(res.stderr),
        )
        prt_head = plant(
            prt,
            "      - run: echo ok\n",
            "      - uses: actions/checkout@v4\n        with:\n          ref: ${{ github.event.pull_request.head.sha }}\n",
        )
        res = run_fixture(base / "prt-head", prt_head, plants()["i"][1], FIXTURE_CONFIG)
        check(
            "pull_request_target checking out the PR head is a PR root (i)",
            "i" in fired_rules(res.stderr),
        )

    check(
        "parse_requests is check_bws_map's",
        bws_step_scope.bws_map_gate().parse_requests.__module__ == "rediacc_ci.quality.bws_map",
    )

    if check.count < MIN_CONTROLS:
        print(
            "  FAIL  only %d control(s) ran; the file is not being executed as written"
            % check.count,
            file=sys.stderr,
        )
        return True
    return not check.ok


def show_baseline(root: pathlib.Path) -> int:
    res = evaluate_tree(root)
    base = set(res.baseline)
    for f in res.current:
        if f.id in base:
            print(f.text)
    print(
        "%d baselined finding(s) present of %d id(s)"
        % (sum(1 for f in res.current if f.id in base), len(base))
    )
    return 0 if res.rc != CANNOT_RUN else CANNOT_RUN


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    root = paths.repo_root()
    try:
        if "--selftest" in argv:
            return 1 if selftest() else 0
        if "--write-baseline" in argv:
            return write_baseline(root)
        if "--show-baseline" in argv:
            return show_baseline(root)
        rc = controls_first("bws pr path", selftest)
    except InstrumentError as exc:
        print("✗ instrument: %s" % exc, file=sys.stderr)
        return CANNOT_RUN
    if rc:
        return rc
    return verdict(root)


__all__ = [
    "CONFIG_REL",
    "FIXED_CI",
    "FIXED_STAGE",
    "Context",
    "InstrumentError",
    "evaluate",
    "evaluate_tree",
    "finding_id",
    "findings",
    "fired_rules",
    "interpolate",
    "load_config",
    "main",
    "plants",
    "reach",
    "run_fixture",
    "selftest",
    "verdict",
    "write_baseline",
]


if __name__ == "__main__":
    from rediacc_ci.quality import gate_args

    gate_args.parse(
        "bws_pr_path.py",
        sys.argv[1:],
        switches=("--selftest", "--write-baseline", "--show-baseline"),
    )
    raise SystemExit(main(sys.argv[1:]))
