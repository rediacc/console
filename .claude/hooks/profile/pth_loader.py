# rediacc-resprofile-loader v1
"""The user-site loader for the resource recorder (agent/plans/PLAN-tooling-speed.md D6).

WHY. `bash_env.sh` reaches a plain `python3` through PYTHONPATH, and a command that sets its own PYTHONPATH (`PYTHONPATH=.ci python3 -m rediacc_ci...`) replaces that path, so the recorder never loaded for the commands this repo runs most. A `.pth` file in the user site directory is processed by `site` whatever PYTHONPATH says. `pth_setup.sh` copies this file there as `rediacc_resprofile_loader.py` with a one-line `rediacc_resprofile.pth` that imports it.

WHAT IT RUNS, and what it never runs. Every python3 of this user processes the `.pth`, so the loader acts only for a cwd under a repo root listed in `~/.claude/resprofile/pth-roots`, the list `pth_setup.sh` appends its own repo to. It never walks up from the cwd looking for a recorder: a directory anyone can create must not get code run by every interpreter started in it. For a listed root it runs that root's `.claude/hooks/profile/py/sitecustomize.py` by path, whose own contracts apply (WORKLIST_PROFILE=off, the cwd scope, one record per process by the pid marker). The deepest listed root wins, so a lease tree records under its own slug, as through PYTHONPATH.

COST. importlib.util (about 1 ms) and nothing heavier: contextlib alone costs about 10 ms at startup, which this file would add to every python3 of the user.

CONTRACTS, the same as the recorder's, because this runs at the start of every python3: never print, never raise, never change the exit status. The first line carries the version `pth_setup.sh` compares before copying.
"""

import os


def _root_for(cwd, roots):
    """The deepest listed root holding `cwd`, or None."""
    best = None
    for raw in roots:
        root = os.path.realpath(raw.strip()) if raw.strip() else ""
        inside = root and root != "/" and (cwd == root or cwd.startswith(root + os.sep))
        if inside and (best is None or len(root) > len(best)):
            best = root
    return best


def recorder_path(cwd=None, roots_file=None):
    """The recorder of the deepest listed root holding `cwd`, or None when no listed root holds it or the list is absent."""
    roots_file = roots_file or os.path.join(
        os.path.expanduser("~"), ".claude", "resprofile", "pth-roots"
    )
    try:
        cwd = os.path.realpath(cwd or os.getcwd())
        with open(roots_file, encoding="utf-8") as fh:
            root = _root_for(cwd, fh)
    except OSError:
        return None
    if root is None:
        return None
    path = os.path.join(root, ".claude", "hooks", "profile", "py", "sitecustomize.py")
    return path if os.path.isfile(path) else None


def _run(recorder):
    """Run `recorder` by path, under its own module name, so the distro `sitecustomize` it would shadow on PYTHONPATH is untouched."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("_rediacc_resprofile_site", recorder)
    if spec is not None and spec.loader is not None:
        spec.loader.exec_module(importlib.util.module_from_spec(spec))


def _load():
    try:
        recorder = recorder_path()
        if recorder is not None:
            _run(recorder)
    # swallowed-failure-ok: this runs at the start of every python3 of this user, so a failing loader must never change the interpreter's exit status or output; a dead loader shows as missing rows in the resprofile rollup, never as a failed command.
    except BaseException:
        pass


_load()
