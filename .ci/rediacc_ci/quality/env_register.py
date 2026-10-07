r"""npm run env:register -- one environment name, registered everywhere it must be, in one command.

    npm run env:register -- <module> <NAME> --class <shard>
                            [--kind <k> --default <spelling>... --why <text>]

THE FAN-OUT THIS REPLACES. Adding one environment read used to mean editing up to three files by hand, in an order nobody wrote down, and then running three gates to find out which one had been missed: one hook variable took three commits on 2026-10-04. Each name has exactly ONE authored home, and this verb writes it, then derives everything else:

  WORKLIST_* names   `.ci/policy/worklist-env-registry.json` `names` (with
                     `kind`, `class`, pinned `defaults` and, for flag, handle and
                     corpus, a `why`), or `foreign_reads` when the reader is not
                     Python or bash and the registry's scan cannot see it
  every other name   its shard list in `.ci/config/env-manifest.json`

THE STEPS, in order, and the order is the contract:

  1. VALIDATE, and on any refusal write NOTHING. `--class` is one of
     env_manifest.LIVE_SHARDS (and `harness` or `gate-seam` for a WORKLIST
     name). A WORKLIST name read from Python or bash needs `--kind` and
     `--default`, plus `--why` for flag, handle and corpus: the same rule the
     registry gate applies, refused here instead of red there. A name already
     registered under a DIFFERENT class is refused: moving a name between shards
     changes who may supply it, and that is a hand edit with a reason, not a
     side effect of registering a second reader. The module must already read the
     name, because both registries pin READS and a name registered before its
     read exists is reported dead by the next gate run.
  2. WRITE the authored home, sorted.
  3. RE-RENDER the env-manifest WORKLIST_* members from the registry classes
     (`env_manifest.render_worklist`).
  4. RECORD THE READ, for a `.py` module whose `module:NAME` pair is not already
     in `.ci/config/python-env-registry.json`:
     `check_python_env_registry.py --write-baseline --allow-new <module>:<NAME>`.
     A typed addition, never a blanket reseed.
  5. REGENERATE the docs: `npm run -s gen:docs -- --write`, which feeds the
     doc-registry env-manifest region. It has no `--only`.
  6. CHECK, read-only, with the three registry gates, and print each verdict.
     Any red makes this verb exit 1.

It NEVER COMMITS, and it writes a file only when its bytes change, so re-running it for a name that is already registered leaves the tree byte-identical before steps 5 and 6.

THE SUBPROCESS SEAM. Steps 4, 5 and 6 run through one `runner(cmd, cwd)` callable returning `(rc, stdout, stderr)`. `main(argv, runner=...)` takes a recording runner in `test_quality_env_register.py`, which is how the steps are proven to run in order, with the exact arguments, against a fixture tree selected through `REDIACC_CI_ROOT`, without ever invoking gen-docs on the real repository.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

from rediacc_ci import log, paths
from rediacc_ci.policy_paths import policy_path
from rediacc_ci.quality import env_manifest as em
from rediacc_ci.quality import python_env_registry as per
from rediacc_ci.quality import worklist_env_registry as wer

USAGE = (
    "usage: npm run env:register -- <module> <NAME> --class <shard> "
    "[--kind <k> --default <spelling>... --why <text>]\n"
    "  <module>   the tracked file that reads NAME, relative to the repository root\n"
    "  --class    one of: %s (WORKLIST_* names: %s)\n"
    "  --kind     WORKLIST_* only: one of %s\n"
    "  --default  WORKLIST_* only, repeatable: a default SPELLING exactly as the registry gate\n"
    "             derives it, e.g. \"'60'\", NONE (no fallback), REQUIRED (os.environ[...])\n"
    "  --why      WORKLIST_* only: required for flag, handle and corpus, and for a name read\n"
    "             outside Python and bash"
    % (", ".join(em.LIVE_SHARDS), ", ".join(wer.CLASSES), ", ".join(wer.KINDS))
)

GATES = (
    "check_env_manifest.py",
    "check_worklist_env_registry.py",
    "check_python_env_registry.py",
)


class RefusalError(Exception):
    """A request this verb will not carry out. Nothing has been written when it is raised."""


class Request:
    """One parsed invocation."""

    def __init__(self, module, name, cls, kind=None, defaults=(), why=None):
        self.module = module
        self.name = name
        self.cls = cls
        self.kind = kind
        self.defaults = list(defaults)
        self.why = why


def parse_args(argv):
    """argv -> Request. Raises RefusalError on anything malformed; a flag is never silently dropped."""
    positional = []
    opts = {"--class": None, "--kind": None, "--why": None}
    defaults = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in opts or arg == "--default":
            if i + 1 >= len(argv) or argv[i + 1].startswith("--"):
                raise RefusalError("%s needs a value after it" % arg)
            if arg == "--default":
                defaults.append(argv[i + 1])
            elif opts[arg] is not None:
                raise RefusalError("%s was given twice" % arg)
            else:
                opts[arg] = argv[i + 1]
            i += 2
            continue
        if arg.startswith("--"):
            raise RefusalError("unknown flag %s" % arg)
        positional.append(arg)
        i += 1
    if len(positional) != 2:
        raise RefusalError(
            "expected <module> <NAME>, got %d positional argument(s)" % len(positional)
        )
    if opts["--class"] is None:
        raise RefusalError("--class is required")
    module = str(pathlib.PurePosixPath(positional[0]))
    return Request(module, positional[1], opts["--class"], opts["--kind"], defaults, opts["--why"])


# ------------------------------------------------------------------ reading the tree


def _read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RefusalError("cannot read %s: %s" % (path, exc)) from exc


def _dump(obj):
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def _write_if_changed(path, text):
    """Atomic, and only when the bytes differ. Returns True when it wrote."""
    if path.is_file() and path.read_text(encoding="utf-8") == text:
        return False
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".%s." % path.name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return True


def _scanned_by_registry(module):
    """True when the worklist registry's scan reads this module (Python or bash)."""
    return module.endswith((".py", ".sh"))


def _worklist_reads(root, module, name):
    """The default spellings `module` reads WORKLIST `name` with, as the registry gate derives them."""
    source = (root / module).read_text(encoding="utf-8", errors="surrogateescape")
    try:
        reads = (
            wer.scan_python(module, source)
            if module.endswith(".py")
            else wer.scan_bash(module, source)
        )
    except SyntaxError as exc:
        raise RefusalError("%s does not parse (%s)" % (module, exc)) from exc
    return sorted({r.default for r in reads if r.name == name})


def _mentions(root, module, name):
    text = (root / module).read_text(encoding="utf-8", errors="replace")
    return re.search(r"\b%s\b" % re.escape(name), text) is not None


# ------------------------------------------------------------------ steps 1 to 3: validate, then write


def _current_shard(lists, name):
    for shard in em.ALL_SHARDS:
        if name in lists[shard]:
            return shard
    return None


def _validate_common(root, req):
    if not em.NAME_RE.match(req.name):
        raise RefusalError("%r is not an environment variable name" % req.name)
    if req.cls not in em.LIVE_SHARDS:
        raise RefusalError(
            "--class %r is not a live shard. Use one of: %s" % (req.cls, ", ".join(em.LIVE_SHARDS))
        )
    if ":" in req.module or not (root / req.module).is_file():
        raise RefusalError(
            "%s is not a file under %s. Register a name after the read exists: both "
            "registries pin READS, and a name with no reader is reported dead." % (req.module, root)
        )


def _plan_worklist(root, req, registry):
    """Apply a WORKLIST_* request to the registry object IN PLACE. Raises RefusalError; never writes."""
    if req.cls not in wer.CLASSES:
        raise RefusalError(
            "--class %r: a WORKLIST_* name is supplied by a local harness or a gate's own "
            "control, so its class is one of %s" % (req.cls, ", ".join(wer.CLASSES))
        )
    names = registry["names"]
    foreign = registry.get("foreign_reads") or {}
    current = wer.classes_of(registry).get(req.name)
    if current is not None and current != req.cls:
        raise RefusalError(
            "%s is already registered under class %r, and this asks for %r. Moving a name "
            "between shards changes who may supply it: edit its `class` in .ci/policy/%s by hand, "
            "with the reason in the commit, rather than as a side effect of registering a reader."
            % (req.name, current, req.cls, wer.REGISTRY_NAME)
        )
    if req.why is not None and len(req.why.strip()) < wer.WHY_MIN_CHARS:
        raise RefusalError(
            "--why has %d characters; the registry requires at least %d, saying which "
            "direction a typo fails" % (len(req.why.strip()), wer.WHY_MIN_CHARS)
        )

    if not _scanned_by_registry(req.module):
        if _plan_foreign(root, req, names, foreign):
            registry["foreign_reads"] = dict(sorted(foreign.items()))
        return

    derived = _worklist_reads(root, req.module, req.name)
    if not derived:
        raise RefusalError(
            "%s does not read %s (no os.environ / getenv read, or ${...} expansion, of that "
            "name). Write the read first; the registry pins reads." % (req.module, req.name)
        )
    if req.name in foreign:
        raise RefusalError(
            "%s is a foreign read (read only outside Python and bash) and %s reads it from a "
            "language the registry scans, so it belongs under `names`. Move the entry by hand, "
            "adding its kind and pinned defaults." % (req.name, req.module)
        )
    entry = dict(names.get(req.name) or {})
    if not entry:
        if req.kind not in wer.KINDS:
            raise RefusalError(
                "a new WORKLIST_* name needs --kind, one of %s (got %r)"
                % (", ".join(wer.KINDS), req.kind)
            )
        if not req.defaults:
            raise RefusalError(
                "a new WORKLIST_* name needs --default: %s reads it with %s"
                % (req.module, ", ".join(derived))
            )
        if req.kind in wer.WHY_REQUIRED and req.why is None:
            raise RefusalError(
                "a %s needs --why: a typo in a %s name turns something OFF or narrows what is "
                "looked at, and the reason says which way it fails" % (req.kind, req.kind)
            )
        entry = {"kind": req.kind, "class": req.cls, "defaults": []}
    elif req.kind is not None and req.kind != entry.get("kind"):
        raise RefusalError(
            "%s is registered as kind %r; --kind %r would change it. A kind is a claim about "
            "which way a typo fails: edit it by hand, with the reason."
            % (req.name, entry.get("kind"), req.kind)
        )
    pinned = sorted(set(entry.get("defaults", [])) | set(req.defaults))
    missing = [d for d in derived if d not in pinned]
    if missing:
        raise RefusalError(
            "%s reads %s with default spelling(s) %s, which the pin would not hold. Pass each "
            "as --default exactly as written there." % (req.module, req.name, ", ".join(missing))
        )
    entry["defaults"] = pinned
    entry["class"] = req.cls
    if req.why is not None:
        entry["why"] = req.why
    names[req.name] = entry
    registry["names"] = dict(sorted(names.items()))


def _plan_foreign(root, req, names, foreign):
    """A WORKLIST_* name read from a file the registry scan cannot see (TypeScript, YAML).

    Mutates `foreign` and returns True when it changed; False when there is nothing to record.
    """
    if req.kind is not None or req.defaults:
        raise RefusalError(
            "%s is not Python or bash, so the registry cannot derive or pin a kind or default "
            "for its read; drop --kind and --default" % req.module
        )
    if not _mentions(root, req.module, req.name):
        raise RefusalError("%s does not name %s. Write the read first." % (req.module, req.name))
    if req.name in names:
        # Already scanned elsewhere; a second reader in another language changes no pin.
        return False
    entry = dict(foreign.get(req.name) or {})
    if not entry:
        if req.why is None:
            raise RefusalError(
                "%s is read only outside Python and bash, so it is recorded under "
                "`foreign_reads`, which is an exclusion and needs --why" % req.name
            )
        entry = {"class": req.cls, "reader": req.module}
    if req.why is not None:
        entry["why"] = req.why
    foreign[req.name] = entry
    return True


def plan(root, req):
    """(new_registry_text | None, new_manifest_text). Raises RefusalError; writes nothing."""
    root = pathlib.Path(root)
    _validate_common(root, req)
    manifest_path = root / em.MANIFEST_REL
    registry_path = policy_path(wer.REGISTRY_NAME, root)
    manifest = _read_json(manifest_path)
    try:
        lists = em.shard_lists(manifest)
    except em.RefusalError as exc:
        raise RefusalError(str(exc)) from exc
    shard = _current_shard(lists, req.name)
    if shard == em.TOMBSTONE_SHARD:
        raise RefusalError(
            "%s is a tombstone. Bringing a retired name back is a decision with a replacement "
            "to unwind (docs/environment-variables.md); edit the manifest by hand." % req.name
        )

    registry_text = None
    if req.name.startswith(em.WORKLIST_PREFIX):
        registry = _read_json(registry_path)
        before = _dump(registry)
        _plan_worklist(root, req, registry)
        new_text = _dump(registry)
        registry_text = new_text if new_text != before else None
        classes = wer.classes_of(registry)
    else:
        if req.kind is not None or req.defaults or req.why is not None:
            raise RefusalError(
                "--kind, --default and --why describe WORKLIST_* names only; %s is "
                "classified by its shard alone" % req.name
            )
        if shard is not None and shard != req.cls:
            raise RefusalError(
                "%s is already in shard %r, and this asks for %r. Moving a name between shards "
                "changes who may supply it: move it by hand in %s, with the reason."
                % (req.name, shard, req.cls, em.MANIFEST_REL)
            )
        if shard is None:
            lists[req.cls] = sorted([*lists[req.cls], req.name])
        classes = wer.classes_of(_read_json(registry_path))

    _check_python_read(root, req)
    lists = em.render_worklist(lists, classes)
    for name in em.ALL_SHARDS:
        manifest["shards"][name] = lists[name]
    return registry_text, _dump(manifest)


def _check_python_read(root, req):
    """For a `.py` module whose pair is not yet recorded: the read must be one the python-env gate can SEE.

    Checked here, before anything is written, because step 4's `--allow-new` refuses a pair that is not a real addition, and by then steps 2 and 3 would have written. The derivation is the gate's own (`python_env_registry.derive`), so a read through a cross-module constant counts exactly as it will there.
    """
    if not req.module.endswith(".py"):
        return
    if "%s:%s" % (req.module, req.name) in _recorded_pairs(root):
        return
    try:
        derived, _ = per.derive(root)
    except per.RefusalError as exc:
        raise RefusalError("the python-env derivation cannot run: %s" % exc) from exc
    if req.name not in derived.get(req.module, []):
        raise RefusalError(
            "%s does not read %s as check_python_env_registry derives it (a tracked module, an "
            "os.environ / getenv read of a literal or a module constant). Write the read, and "
            "track the file, first." % (req.module, req.name)
        )


# ------------------------------------------------------------------ steps 4 to 6: subprocesses


def default_runner(cmd, cwd):
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, check=False)
    return proc.returncode, proc.stdout, proc.stderr


def _recorded_pairs(root):
    try:
        modules = _read_json(root / per.BASELINE_REL).get("modules") or {}
    except RefusalError:
        return set()
    return per.pairs_of(modules)


def _verdict(out, err):
    lines = [ln for ln in (err + out).splitlines() if ln.strip()]
    return lines[-1].strip() if lines else "(no output at all)"


def register(root, req, runner=default_runner):
    """Run all six steps. Returns the exit code."""
    root = pathlib.Path(root)
    registry_text, manifest_text = plan(root, req)

    wrote = []
    if registry_text is not None and _write_if_changed(
        policy_path(wer.REGISTRY_NAME, root), registry_text
    ):
        wrote.append(".ci/policy/%s" % wer.REGISTRY_NAME)
    if _write_if_changed(root / em.MANIFEST_REL, manifest_text):
        wrote.append(em.MANIFEST_REL)
    print("env:register %s %s --class %s" % (req.module, req.name, req.cls))
    print("  wrote: %s" % (", ".join(wrote) if wrote else "nothing (already registered so)"))

    quality = root / ".ci" / "scripts" / "quality"
    pair = "%s:%s" % (req.module, req.name)
    if not req.module.endswith(".py"):
        print("  python-env: skipped, %s is not a Python module" % req.module)
    elif pair in _recorded_pairs(root):
        print("  python-env: %s is already recorded" % pair)
    else:
        cmd = [
            sys.executable,
            str(quality / "check_python_env_registry.py"),
            "--write-baseline",
            "--allow-new",
            pair,
        ]
        rc, out, err = runner(cmd, root)
        print("  python-env: --allow-new %s -> rc %d" % (pair, rc))
        if rc != 0:
            log.error(
                "check_python_env_registry refused the typed addition, so the read is not "
                "recorded:\n%s" % (err + out).rstrip()
            )
            return 1

    rc, out, err = runner(["npm", "run", "-s", "gen:docs", "--", "--write"], root)
    print("  docs: npm run -s gen:docs -- --write -> rc %d" % rc)
    if rc != 0:
        log.error(
            "gen-docs failed, so the doc-registry region is stale:\n%s" % (err + out).rstrip()
        )
        return 1

    failed = 0
    for gate in GATES:
        rc, out, err = runner([sys.executable, str(quality / gate)], root)
        print("  check: %s -> rc %d: %s" % (gate, rc, _verdict(out, err)))
        failed += rc != 0
    if failed:
        log.error(
            "%d of %d registry gate(s) red after registering %s. Nothing was committed; read "
            "the verdicts above." % (failed, len(GATES), req.name)
        )
        return 1
    log.success(
        "%s registered as %s; %d gate(s) green. NOT COMMITTED: commit %s with the read."
        % (req.name, req.cls, len(GATES), ", ".join(wrote) or "the read")
    )
    return 0


def main(argv=None, runner=default_runner):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(USAGE)
        return 0 if argv else 2
    try:
        req = parse_args(argv)
        return register(paths.repo_root(), req, runner)
    except RefusalError as exc:
        log.error("env:register refused, and wrote nothing: %s" % exc)
        print(USAGE, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
