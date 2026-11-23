"""The one environment registry file, `.ci/config/env-manifest.json`, and its three sections.

ONE FILE, THREE SECTIONS (agent/plans/PLAN-tooling-code-reduction.md D3). Every environment name this repository reads used to be recorded in three files, each with its own gate: the shard classification, the AST-measured Python read set and the WORKLIST_* registry. They are now sections of one document, held by one gate (`check:ci-env-registry`, `env_registry.py`) and written by one verb (`npm run env:register`):

  `shards` (with `shard_definitions`, `tombstone_proof_sites`, `collisions`, `notes`)
                 who supplies each name and who may read it, `env_manifest.py`
  `python_reads` the `module -> [NAME]` read set, `python_env_registry.py`
  `worklist`     every WORKLIST_* name with its kind, class and pinned defaults,
                 `worklist_env_registry.py`

The shard keys stay at the top level, where `secret_supply.py`, `scripts/lib/doc-providers.ts` and the gen-docs trigger already read them.

ONE SERIALISATION. Every writer goes through `dump`, so a writer that changes one section leaves the other two byte-identical, and re-running `env:register` for a name that is already registered rewrites nothing.

ONE TEST SEAM. `ENV_REGISTRY_OVERRIDE_FILE` names a tmp copy of the whole document, read IN PLACE OF the tracked file by every section's real invocation (a call with no explicit root). A plant test mutates the copy and never writes the tracked file, so a kill inside the test cannot corrupt it.
"""

from __future__ import annotations

import json
import os
import pathlib

from rediacc_ci import paths

DOC_REL = ".ci/config/env-manifest.json"
SHARDS = "shards"
PYTHON_READS = "python_reads"
WORKLIST = "worklist"

#: Test-only: an absolute path read in place of `DOC_REL` by a real invocation.
OVERRIDE = os.environ.get("ENV_REGISTRY_OVERRIDE_FILE", "")


class DocError(Exception):
    """The document cannot be read. Each caller turns this into its own refusal."""


def doc_path(root) -> pathlib.Path:
    """The document a call reads: the override for the real invocation (`root` is None), else `<root>/DOC_REL`.

    A selftest always passes an explicit fixture root, so a plant test's override sitting in the same process environment can never redirect a control onto the wrong file.
    """
    if root is None and OVERRIDE:
        return pathlib.Path(OVERRIDE)
    return pathlib.Path(root or paths.repo_root()) / DOC_REL


def shown(path: pathlib.Path) -> str:
    """How a message names the document: `DOC_REL` for the tracked file (or a fixture's copy of it), else the path itself, so an override pointed at the wrong file says so."""
    return DOC_REL if str(path).endswith(DOC_REL) else str(path)


def read(path: pathlib.Path) -> dict:
    """The whole document. A missing, unreadable or non-object file raises DocError, never `{}`."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DocError("cannot read %s (%s)" % (path, exc)) from exc
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DocError("%s is not valid JSON: %s" % (path, exc)) from exc
    if not isinstance(obj, dict):
        raise DocError("%s is not a JSON object" % path)
    return obj


def dump(obj: dict) -> str:
    """The one serialisation every writer uses."""
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def write(path: pathlib.Path, obj: dict) -> bool:
    """Write `obj` atomically, only when its bytes differ. True when it wrote."""
    text = dump(obj)
    if path.is_file() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(".%s.%d.tmp" % (path.name, os.getpid()))
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()
    return True
