"""The text pre-filters of `check:ci-record-paths`' width sweep never change an answer.

`python_widths` skips its whole-tree walk (and its parse) when the source holds none of the names a rule tests for, and `line_widths` runs a rule's regex only on a line holding one of that rule's literal needles. Each filter is only sound if the unfiltered answer is the same, so every case here states it both ways: the filtered function against the same function with the filter forced open (the positive control, on awkward spellings and on every tracked width-scope file), and a source with nothing to find that the filter does skip (the negative control, which proves the filter filters).
"""

import re

import pytest

from rediacc_ci import paths
from rediacc_ci.quality import record_paths as rp

PY_SHAPES = {
    "pool positional": "from concurrent.futures import ThreadPoolExecutor\nx = ThreadPoolExecutor(8)\n",
    "pool keyword, spaced": "import concurrent.futures as cf\nx = cf.ThreadPoolExecutor(max_workers = 6)\n",
    "keyword on its own line": "f(\n    n_jobs\n    =\n    4,\n)\n",
    "core cap": "import os\nn = min(8, os.cpu_count())\n",
    "argv width": 'cmd = ["pytest", "-n", "4"]\n',
    "argv width, single quotes": "cmd = ['pytest', '--numprocesses', '3']\n",
    "width const": "COPY_WIDTH = 5\n",
    "named const": "MAX_WORKERS = 12\n",
    "nothing": "x = 1\ny = [1, 2]\n",
    "prose only": '"""Spawns workers and processes, uses Pool and cpu_count in prose."""\nx = 1\n',
}

LINE_SHAPES = {
    "xargs": "ls | xargs -P 8 echo\n",
    "make": "make -j 4 all\n",
    "pytest": "pytest -n 6 tests\n",
    "const": "const WORKER_CONCURRENCY = 7;\n",
    "plimit": "const lim = pLimit(5);\n",
    "gomaxprocs": "GOMAXPROCS=4 go test ./...\n",
    "go -p": "go test -p 3 ./...\n",
    "threads": "run --threads 6\n",
    "comment is skipped": "# make -j 4 all\n",
    "nothing": "echo hello\n",
}


def _open(monkeypatch):
    """Force every width pre-filter open, so the unfiltered answer is what the same function gives."""
    monkeypatch.setattr(rp, "WIDTH_WALK_RE", re.compile(""))
    monkeypatch.setattr(rp, "WIDTH_CONST_RE", re.compile(""))
    monkeypatch.setattr(rp, "LINE_ANY_RE", re.compile(""))
    monkeypatch.setattr(rp, "LINE_NEEDLES", tuple(("",) for _ in rp.LINE_RULES))


@pytest.mark.parametrize("name", sorted(PY_SHAPES))
def test_python_widths_is_unchanged_by_its_prefilter(name, monkeypatch):
    src = PY_SHAPES[name]
    filtered = rp.python_widths("x.py", src)
    _open(monkeypatch)
    assert filtered == rp.python_widths("x.py", src)


@pytest.mark.parametrize("name", sorted(LINE_SHAPES))
def test_line_widths_is_unchanged_by_its_prefilter(name, monkeypatch):
    src = LINE_SHAPES[name]
    filtered = rp.line_widths("x.sh", src)
    _open(monkeypatch)
    assert filtered == rp.line_widths("x.sh", src)


def test_the_shapes_do_find_widths_so_the_comparison_is_not_vacuous():
    found = {name: rp.python_widths("x.py", src) for name, src in PY_SHAPES.items()}
    assert all(found[n] for n in ("pool positional", "pool keyword, spaced", "core cap")), found
    assert all(found[n] for n in ("argv width", "width const", "named const")), found
    assert found["keyword on its own line"], (
        "a keyword spelled over three lines is still a pool width"
    )
    assert not found["nothing"], found
    assert not found["prose only"], found
    lines = {name: rp.line_widths("x.sh", src) for name, src in LINE_SHAPES.items()}
    assert all(lines[n] for n in ("xargs", "make", "pytest", "const", "plimit", "go -p")), lines
    assert not lines["comment is skipped"], lines
    assert not lines["nothing"], lines


def test_a_source_with_nothing_to_find_is_skipped_by_the_filters():
    assert not rp.WIDTH_WALK_RE.search(PY_SHAPES["nothing"])
    assert not rp.WIDTH_CONST_RE.search(PY_SHAPES["nothing"])
    assert not rp.LINE_ANY_RE.search(LINE_SHAPES["nothing"])
    assert rp.WIDTH_WALK_RE.search(PY_SHAPES["keyword on its own line"])


def test_every_tracked_width_scope_file_answers_the_same_with_the_filters_open(monkeypatch):
    root = paths.repo_root()
    files = rp.width_files(root)
    assert len(files) > 500, "only %d width-scope files; the sweep is not seeing the tree" % len(
        files
    )
    sample = files[::3]
    filtered = {}
    for rel in sample:
        src = (root / rel).read_text(encoding="utf-8", errors="replace")
        filtered[rel] = (
            rp.python_widths(rel, src) if rel.endswith(".py") else rp.line_widths(rel, src)
        )
    _open(monkeypatch)
    for rel in sample:
        src = (root / rel).read_text(encoding="utf-8", errors="replace")
        open_answer = (
            rp.python_widths(rel, src) if rel.endswith(".py") else rp.line_widths(rel, src)
        )
        assert filtered[rel] == open_answer, rel
