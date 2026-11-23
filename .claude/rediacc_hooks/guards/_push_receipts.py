"""The push-receipt rule table: "a push needs receipt X", one row per receipt kind (box CR6 of agent/plans/PLAN-tooling-code-reduction.md, Design D5).

WHY ONE TABLE. Four pre-bash guards refuse a `git push` that no receipt covers: `block_unverified_push` (ci:quick), `block_vm_unverified_push` (vm:check), `block_backup_unverified_push` (backup) and `block_renet_untested_push` (renet). Before this module each declared its receipt file, its admit line, its escape variable and its ledger in prose and constants of its own, and the three escape-carrying guards carried three copies of the escape judgement and the ledger writer. A row here is the one declaration of what a push needs; the guards keep their own refusal text (the frozen goldens are byte for byte) and their own mutation sites (`check:ci-guard-mutations` plants only in the guard file), and call this module for the parts that were copied.

A ROW is `Row(id, guard, order, receipt, verdict, admit, refusals, escape, kinds, why_names, ledger, touched, reader, origins)`:

    id         the receipt kind: ci:quick, vm:check, backup, renet
    guard      the guard stem that enforces it; `order` is that guard's pre-bash ORDER
    receipt    where the receipt for a tree is read from, as the reader resolves it
    verdict    the verdict a receipt must carry to admit the push
    admit      the exact lines the refusal prints that write the receipt; each must appear in the guard's refusal text and name a real npm script or drill (`admit_parity`)
    refusals   the guard attributes holding that refusal text
    escape     the operator-ASKED environment variable, None when only a receipt admits; `kinds` are its admitted kinds and `why_names` what the why must name
    ledger     where an admitted escape is appended
    touched    the predicate over the pushed range that decides whether the push needs this receipt
    reader     the tree-based receipt reader: `read(row_id, root, tree)` returns what it reads for that tree
    origins    the guard attribute mapping an origin kind to a reader of carried entries, None when the row has none

SPECS ARE STRINGS, resolved on use (`resolve`): `guard:<attr>` is an attribute of the row's guard, `ci:<module>:<attr>` a `rediacc_ci` module through `syspath.import_from_ci`, `stop:<module>:<attr>` a Stop-hook module. The guards import this module, so a direct reference back to them would be an import cycle; a spec is resolved only when a reader is asked for, and `admit_parity` resolves every one, so a renamed reader turns the parity test red rather than failing at a push.

THE SEAM FOR ATTESTED RECEIPTS (PLAN-two-track-merge-dev R4). The ci:quick row's `origins` is `block_unverified_push.ORIGIN_READERS`, whose `ci` reader (`ci_origin_gate`) re-verifies a signed CI receipt through `attested`. `readers(row_id)` returns the row's tree reader beside every origin reader under one interface, so a new receipt kind (another signer, another CI) is one more `ORIGIN_READERS` entry and, when it needs a row of its own, one more row here; `attested` is reused unchanged.
"""

import dataclasses
import datetime
import importlib
import json
import pathlib
import re
import sys

from rediacc_hooks import syspath

#: The escape value: `<kind>: <rest>`. Every escape-carrying row reads it the same way.
REASON_RE = re.compile(r"^\s*([A-Za-z-]+)\s*:\s*(.*?)\s*$", re.DOTALL)
#: The `ASKED:` token, stripped from the why before its length is counted.
ASKED_TOKEN_RE = re.compile(r"\s*\bASKED:\S*")
#: The minute the escape must spell; `wl_checks.ASKED_RE` is the same shape, and matching it here lets a malformed token be named before the transcript is read.
ASKED_STRICT_RE = re.compile(r"\bASKED:\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?Z")
#: The shortest why an escape may carry.
MIN_WHY = 40

GUARD_PKG = "rediacc_hooks.guards"


@dataclasses.dataclass(frozen=True)
class Row:
    id: str
    guard: str
    order: int
    receipt: tuple[str, ...]
    verdict: str
    admit: tuple[str, ...]
    refusals: tuple[str, ...]
    touched: str
    reader: str
    escape: str | None = None
    kinds: tuple[str, ...] = ()
    why_names: str = ""
    ledger: str | None = None
    origins: str | None = None

    @property
    def label(self):
        """The guard's name as its stderr notes spell it: `block-vm-unverified-push`."""
        return self.guard.replace("_", "-")


ROWS = (
    Row(
        id="ci:quick",
        guard="block_unverified_push",
        order=39,
        receipt=(".ci/cache/receipts/<tree>.json", ".ci/cache/prepush-receipt.json"),
        verdict="schema 2, headTree equal to the pushed tree or advanced to it, whole, exitCode 0 or every red carried",
        admit=("npm run ci:quick",),
        refusals=("REFUSAL_TAIL",),
        touched="guard:pushed_tree",
        reader="guard:read_receipt",
        origins="ORIGIN_READERS",
    ),
    Row(
        id="vm:check",
        guard="block_vm_unverified_push",
        order=62,
        receipt=(".ci/cache/vm-check/<tree>.json", ".ci/cache/vm-check/receipt.json"),
        verdict="VERIFIED for the tree or its trigger digest, the phase of every touched side run",
        admit=("npm run vm:check -- --changed",),
        refusals=("REFUSAL",),
        touched="guard:_hits",
        reader="ci:rediacc_ci.proof.vm_tier:admit",
        escape="VM_CHECK_PUSH_REASON",
        kinds=("vm-unavailable", "not-runtime", "deadline"),
        why_names="the files or the deadline",
        ledger="agent/ledgers/vm-check-push-reasons.jsonl",
    ),
    Row(
        id="backup",
        guard="block_backup_unverified_push",
        order=63,
        receipt=(".ci/cache/backup-check/<tree>.json", ".ci/cache/backup-check/receipt.json"),
        verdict="VERIFIED with legs a-l and the on-premise variant, both gitlinks equal to the pushed tree's",
        admit=("./run.sh drill backup", "./run.sh drill backup-onprem"),
        refusals=("REFUSAL",),
        touched="guard:_hits",
        reader="ci:rediacc_ci.drills.backup_check_trigger:admit",
        escape="BACKUP_CHECK_PUSH_REASON",
        kinds=("drill-unavailable", "not-runtime", "deadline"),
        why_names="the files or the deadline",
        ledger="agent/ledgers/backup-check-push-reasons.jsonl",
    ),
    Row(
        id="renet",
        guard="block_renet_untested_push",
        order=65,
        receipt=("$RENET_TEST_RECEIPT_DIR/<renet tree>.json",),
        verdict="a passing run of every package the renet test map selects (`all` covers any selection)",
        admit=("npm run check:ci-renet-test-map",),
        refusals=("REFUSAL",),
        touched="guard:_required",
        reader="stop:wl_renettests:read_receipt",
        escape="RENET_TEST_PUSH_REASON",
        kinds=("environment", "deadline"),
        why_names="the tests or the deadline",
        ledger="agent/ledgers/renet-test-push-reasons.jsonl",
    ),
)

BY_ID = {r.id: r for r in ROWS}


def row(row_id):
    """The row of `row_id`; KeyError names an unknown kind."""
    return BY_ID[row_id]


# --------------------------------------------------------------------------- resolving specs


def guard_module(r):
    return importlib.import_module("%s.%s" % (GUARD_PKG, r.guard))


def resolve(r, spec):
    """The object `spec` names for row `r` (module docstring, SPECS ARE STRINGS). Raises ImportError or AttributeError when it does not exist."""
    where, _, rest = spec.partition(":")
    if where == "guard":
        return getattr(guard_module(r), rest)
    module, _, attr = rest.rpartition(":")
    if where == "ci":
        return getattr(syspath.import_from_ci(module), attr)
    if where == "stop":
        syspath.on_sys_path(syspath.STOP_DIR)
        return getattr(importlib.import_module(module), attr)
    raise ValueError("unknown spec location %r in %r" % (where, spec))


def readers(row_id):
    """{"tree": the row's tree reader, <origin kind>: origin reader, ...}: every reader the row admits through, under one interface (module docstring, THE SEAM)."""
    r = row(row_id)
    out = {"tree": resolve(r, r.reader)}
    if r.origins:
        out.update(getattr(guard_module(r), r.origins))
    return out


def _vm_tier():
    return syspath.import_from_ci("rediacc_ci.proof.vm_tier")


def _backup_trigger():
    return syspath.import_from_ci("rediacc_ci.drills.backup_check_trigger")


def candidates(row_id, root, tree):
    """The receipts a row reads for `tree`, in the order its guard judges them: the per-tree archive, then the latest file. None entries stand for a file that is absent or unreadable."""
    r = row(row_id)
    if r.id == "vm:check":
        mod = _vm_tier()
        return (mod.read_archive(root, tree), mod.read_latest(root))
    if r.id == "backup":
        mod = _backup_trigger()
        return (mod.read_archive(root, tree), mod.read_latest(root))
    return (read(row_id, root, tree),)


def read(row_id, root, tree):
    """THE SHARED TREE-BASED RECEIPT READER: the receipt that speaks for `tree` under row `row_id`, or None.

    ci:quick is `block_unverified_push.read_receipt(root, tree)` (the per-tree archive, then the latest file, with its UNPARSEABLE and MISFILED markers); vm:check and backup the per-tree archive, else the latest file when it names `tree`; renet `wl_renettests.read_receipt(tree)`, keyed on the renet tree alone.
    """
    r = row(row_id)
    if r.id == "renet":
        return resolve(r, r.reader)(tree)
    if r.id in ("vm:check", "backup"):
        archive, latest = candidates(row_id, root, tree)
        if archive is not None:
            return archive
        return latest if isinstance(latest, dict) and latest.get("tree") == tree else None
    return resolve(r, r.reader)(root, tree)


# --------------------------------------------------------------------------- the escape, shared by every row that has one


def judge_escape(ev, row_id, reason, answered):
    """(kind, why) when `reason` passes the checks every escape shares, else (None, the refusal line).

    The checks, in order: present, a kind of the row's, a why of MIN_WHY characters once the ASKED token is stripped, a well-formed `ASKED:` minute, and an operator answer at that minute (`answered(ev, reason)`, the guard's own `_operator_answered`, which stays in the guard as its mutation site). A row's further checks (the NOT_VERIFIED attempt of vm:check and backup) run after this in the guard.
    """
    r = row(row_id)
    if reason is None:
        return None, "escape-missing: no `%s=` on it" % r.escape
    m = REASON_RE.match(reason)
    kind, rest = (m.group(1).lower(), m.group(2)) if m else ("", reason)
    if kind not in r.kinds:
        return (
            None,
            "escape-kind: `%s=%r`: the kind must be one of %s"
            % (r.escape, reason, ", ".join(r.kinds)),
        )
    why = ASKED_TOKEN_RE.sub("", rest).strip()
    if len(why) < MIN_WHY:
        return (
            None,
            "escape-why: `%s`: the why is %d characters; at least %d name %s"
            % (reason, len(why), MIN_WHY, r.why_names),
        )
    if not ASKED_STRICT_RE.search(reason):
        return None, "escape-asked: `%s` carries no ASKED:<YYYY-MM-DDTHH:MM>Z" % reason
    if not answered(ev, reason):
        return (
            None,
            "escape-unproven: its ASKED: minute matches no AskUserQuestion answer in this session's transcript (within 300 s)",
        )
    return kind, why


def not_verified_attempt(row_id, root, tree, digest, for_these_inputs):
    """The NOT_VERIFIED receipt a row read for these inputs, or None. `for_these_inputs(receipt, tree, digest)` is the guard's own test, which stays in the guard as its mutation site."""
    r = row(row_id)
    status = (_vm_tier() if r.id == "vm:check" else _backup_trigger()).NOT_VERIFIED
    for receipt in candidates(row_id, root, tree):
        if receipt is None or receipt.get("status") != status:
            continue
        if for_these_inputs(receipt, tree, digest):
            return receipt
    return None


def asked_minute(reason):
    """The `YYYY-MM-DDTHH:MM[:SS]Z` an escape names, "" when none."""
    asked = ASKED_STRICT_RE.search(reason or "")
    return asked.group(0)[len("ASKED:") :] if asked else ""


def now_stamp():
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def record(ev, row_id, root, rows):
    """Append the ledger lines of admitted escapes to the row's ledger under `root`. A write that fails is named on stderr; the admission stands."""
    r = row(row_id)
    path = pathlib.Path(root) / r.ledger
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.writelines(json.dumps(line, sort_keys=True) + "\n" for line in rows)
    except OSError as exc:
        ev.warn("%s: the admission was NOT recorded in %s (%s)." % (r.label, r.ledger, exc))


# --------------------------------------------------------------------------- admit-line parity

_PLACEHOLDER = re.compile(r"%\((\w+)\)[sd]")
_NPM_RUN = re.compile(r"^npm run (?:-s )?([A-Za-z0-9:_.-]+)")
_DRILL = re.compile(r"^\./run\.sh drill ([A-Za-z0-9_-]+)$")
#: The guard constants a refusal template's placeholders are filled from before the admit lines are looked for.
_FILL = {"command": "COMMAND", "env": "REASON_ENV", "min": "MIN_WHY", "ledger": "LEDGER_REL"}


def refusal_text(r, module=None):
    """The row's refusal templates, joined, with every placeholder the guard fills from its own constants substituted (`%(command)s` -> COMMAND and so on)."""
    module = module or guard_module(r)
    text = "\n".join(getattr(module, name) for name in r.refusals)

    def fill(m):
        attr = _FILL.get(m.group(1))
        if attr and hasattr(module, attr):
            return str(getattr(module, attr))
        return m.group(0)

    return _PLACEHOLDER.sub(fill, text)


def admit_parity(rows=ROWS, modules=None, scripts=None, drills=None, guard_stems=None):
    """Every disagreement between the table and the code it declares, as finding lines; [] when they agree.

    For each row: the guard module imports, declares the row's ORDER and pre-bash CHAIN, its `touched`, `reader` and `origins` resolve; each admit line appears verbatim in the guard's refusal text and names an npm script in package.json (`scripts`) or a drill in `rediacc_ci.core.run_verbs.DRILL_MODULES` (`drills`); an escape row's guard declares that REASON_ENV, those KINDS and that LEDGER_REL. Over the table: the rows are exactly the push-receipt guards (`guard_stems`, every guard importing this module), with no id twice. The arguments default to the live tree; a test hands in edited ones as controls.
    """
    modules = modules or {}
    if scripts is None:
        root = syspath.CLAUDE_DIR.parent
        scripts = json.loads((root / "package.json").read_text(encoding="utf-8")).get("scripts", {})
    if drills is None:
        drills = syspath.import_from_ci("rediacc_ci.core.run_verbs").DRILL_MODULES
    ids = [r.id for r in rows]
    findings = [
        "table: receipt kind %r is declared twice" % dup
        for dup in sorted({i for i in ids if ids.count(i) > 1})
    ]
    if guard_stems is not None:
        declared = {r.guard for r in rows}
        findings.extend(
            "table: %s imports the push-receipt table but has no row" % stem
            for stem in sorted(set(guard_stems) - declared)
        )
        findings.extend(
            "table: row guard %s does not import the push-receipt table" % stem
            for stem in sorted(declared - set(guard_stems))
        )
    for r in rows:
        try:
            module = modules.get(r.guard) or guard_module(r)
        except ImportError as exc:
            findings.append("%s: guard %s does not import (%s)" % (r.id, r.guard, exc))
            continue
        if getattr(module, "CHAIN", None) != "pre-bash":
            findings.append(
                "%s: %s.CHAIN is %r, not 'pre-bash'"
                % (r.id, r.guard, getattr(module, "CHAIN", None))
            )
        if getattr(module, "ORDER", None) != r.order:
            findings.append(
                "%s: %s.ORDER is %r, the row says %d"
                % (r.id, r.guard, getattr(module, "ORDER", None), r.order)
            )
        for field in ("touched", "reader"):
            spec = getattr(r, field)
            try:
                target = (
                    getattr(module, spec[len("guard:") :])
                    if spec.startswith("guard:")
                    else resolve(r, spec)
                )
            except (ImportError, AttributeError, ValueError) as exc:
                findings.append("%s: %s %r does not resolve (%s)" % (r.id, field, spec, exc))
                continue
            if not callable(target):
                findings.append("%s: %s %r is not callable" % (r.id, field, spec))
        if r.origins:
            origins = getattr(module, r.origins, None)
            if (
                not isinstance(origins, dict)
                or not origins
                or not all(callable(v) for v in origins.values())
            ):
                findings.append(
                    "%s: %s.%s is not a non-empty map of readers" % (r.id, r.guard, r.origins)
                )
        try:
            text = refusal_text(r, module)
        except (AttributeError, TypeError) as exc:
            findings.append("%s: refusal text %r does not read (%s)" % (r.id, r.refusals, exc))
            text = ""
        if not r.admit:
            findings.append("%s: the row names no admit line" % r.id)
        for line in r.admit:
            if line not in text:
                findings.append(
                    "%s: admit line `%s` is not in %s.%s; the refusal and the row must name the same command"
                    % (r.id, line, r.guard, "/".join(r.refusals))
                )
            npm, drill = _NPM_RUN.match(line), _DRILL.match(line)
            if npm and npm.group(1) not in scripts:
                findings.append(
                    "%s: admit line `%s` names no package.json script %r"
                    % (r.id, line, npm.group(1))
                )
            elif drill and drill.group(1) not in drills:
                findings.append(
                    "%s: admit line `%s` names no drill %r in run_verbs.DRILL_MODULES"
                    % (r.id, line, drill.group(1))
                )
            elif not npm and not drill:
                findings.append(
                    "%s: admit line `%s` is neither `npm run <script>` nor `./run.sh drill <name>`"
                    % (r.id, line)
                )
        if r.escape:
            for attr, want in (
                ("REASON_ENV", r.escape),
                ("KINDS", r.kinds),
                ("LEDGER_REL", r.ledger),
            ):
                if getattr(module, attr, None) != want:
                    findings.append(
                        "%s: %s.%s is %r, the row says %r"
                        % (r.id, r.guard, attr, getattr(module, attr, None), want)
                    )
            if "%s='" % r.escape not in text:
                findings.append(
                    "%s: the refusal does not spell the escape `%s='...'`" % (r.id, r.escape)
                )
    return findings


def importing_guards(guards_dir=None):
    """The guard stems whose source imports this module: the set `admit_parity` holds the table's rows to."""
    guards_dir = pathlib.Path(guards_dir or pathlib.Path(__file__).parent)
    pattern = re.compile(
        r"^from rediacc_hooks\.guards import [^\n]*\b_push_receipts\b", re.MULTILINE
    )
    return [
        path.stem
        for path in sorted(guards_dir.glob("block_*.py"))
        if pattern.search(path.read_text(encoding="utf-8"))
    ]


if __name__ == "__main__":  # pragma: no cover - a convenience for a reader at a shell
    found = admit_parity(guard_stems=importing_guards())
    print("\n".join(found) or "push-receipt table: %d rows, admit lines in parity" % len(ROWS))
    sys.exit(1 if found else 0)
