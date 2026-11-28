"""The text pre-filters of `check:ci-record-paths`' width sweep never change an answer.

`python_widths` skips its whole-tree walk (and its parse) when the source holds none of the names a rule tests for, and `line_widths` runs a rule's regex only on a line holding one of that rule's literal needles. Each filter is only sound if the unfiltered answer is the same, so every case here states it both ways: the filtered function against the same function with the filter forced open (the positive control, on awkward spellings and on every tracked width-scope file), and a source with nothing to find that the filter does skip (the negative control, which proves the filter filters).
"""

import os
import re

import pytest

from rediacc_ci import paths
from rediacc_ci.quality import record_paths as rp

PY_SHAPES = {
    "pool positional": "from concurrent.futures import ThreadPoolExecutor\nx = ThreadPoolExecutor(8)\n",
    "pool keyword, spaced": "import concurrent.futures as cf\nx = cf.ThreadPoolExecutor(max_workers = 6)\n",
    "keyword on its own line": "f(\n    n_jobs\n    =\n    4,\n)\n",
    "keyword, comment before the equals": "f(\n    n_jobs  # how many\n    =\n    4,\n)\n",
    "keyword, backslash continuation": "x = f(n_jobs \\\n    = 4)\n",
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
    for gap in ("keyword, comment before the equals", "keyword, backslash continuation"):
        assert found[gap], (
            "a comment or a continuation between keyword and `=` is still a width (d39f0ba2.1)"
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
    assert rp.WIDTH_WALK_RE.search(PY_SHAPES["keyword, comment before the equals"])
    assert rp.WIDTH_WALK_RE.search(PY_SHAPES["keyword, backslash continuation"])


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


LINE_RULE_SAMPLES = {
    "xargs -P": "ls | xargs -P 8 echo",
    "--jobs": "run --jobs 4",
    "make -j": "make -j 4 all",
    "pytest -n": "pytest -n 6 tests",
    "--maxWorkers": "jest --maxWorkers 4",
    "maxWorkers:": "maxWorkers: 4",
    "pLimit": "const lim = pLimit(5);",
    "core cap": "const n = Math.min(8, os.availableParallelism());",
    "width const": "const WORKER_CONCURRENCY = 7;",
    "GOMAXPROCS": "GOMAXPROCS=4 go test ./...",
    "RAYON_NUM_THREADS": "RAYON_NUM_THREADS=4 cargo build",
    "--threads": "run --threads 6",
    "--concurrency": "run --concurrency 5",
    "go -p": "go test -p 3 ./...",
}


def test_every_line_rule_is_paired_with_its_own_needles():
    """The import-time guard checks only equal length (60f2cc15.3), so the pairing is pinned here: each rule's sample line matches its regex and holds one of the needles at the SAME index, and the filtered `line_widths` finds it."""
    kinds = [kind for kind, _ in rp.LINE_RULES]
    assert kinds == list(LINE_RULE_SAMPLES), "a rule was added, removed or moved without a sample"
    for (kind, rx), needles in zip(rp.LINE_RULES, rp.LINE_NEEDLES, strict=True):
        sample = LINE_RULE_SAMPLES[kind]
        assert rx.search(sample), "%s: its sample does not match its regex" % kind
        assert any(n in sample for n in needles), "%s: no paired needle %r in the sample" % (
            kind,
            needles,
        )
        assert rp.line_widths("x.sh", sample + "\n"), "%s: the filtered scan misses it" % kind


def test_a_misplaced_needle_tuple_is_caught_by_the_pairing(monkeypatch):
    """Negative control: swapping two needle tuples keeps the length, so only the pairing test can see it."""
    needles = list(rp.LINE_NEEDLES)
    needles[0], needles[1] = needles[1], needles[0]
    monkeypatch.setattr(rp, "LINE_NEEDLES", tuple(needles))
    assert not rp.line_widths("x.sh", LINE_RULE_SAMPLES["xargs -P"] + "\n")


def test_rel_follows_a_relative_root_across_a_chdir(tmp_path, monkeypatch):
    """`_resolved` once memoised a relative root's absolute form for the whole process (60f2cc15.1), so after a chdir `_rel` answered with the old directory's prefix."""
    for name in ("a", "b"):
        (tmp_path / name / "sub").mkdir(parents=True)
    root = rp.pathlib.Path("sub")
    monkeypatch.chdir(tmp_path / "a")
    assert rp._rel(tmp_path / "a" / "sub" / "x.py", root) == "x.py"
    monkeypatch.chdir(tmp_path / "b")
    assert rp._rel(tmp_path / "b" / "sub" / "x.py", root) == "x.py"
    assert os.getcwd() == str(tmp_path / "b")


def test_an_absolute_root_is_still_resolved_once(tmp_path):
    rp._resolved_absolute.cache_clear()
    for _ in range(5):
        rp._resolved(tmp_path)
    info = rp._resolved_absolute.cache_info()
    assert (info.misses, info.hits) == (1, 4)


def _write_modules(tmp_path):
    for name in ("top", "in_func", "in_try", "in_class"):
        (tmp_path / (name + ".py")).write_text("X = 1\n", encoding="utf-8")
    user = tmp_path / "user.py"
    user.write_text(
        "import top\n"
        "def f():\n    import in_func\n"
        "try:\n    import in_try\nexcept ImportError:\n    pass\n"
        "class C:\n    def m(self):\n        from in_class import X\n",
        encoding="utf-8",
    )
    return user


def test_imports_nested_in_bodies_are_still_followed(tmp_path):
    """The import walk moved from `ast.walk` to `env_ast.imports` (60f2cc15.2); a function, a try and a method body each hide an import that a reader closure must still follow."""
    user = _write_modules(tmp_path)
    got = sorted(p.name for p in rp._py_imports_uncached(user, tmp_path))
    assert got == ["in_class.py", "in_func.py", "in_try.py", "top.py"]


def test_a_top_level_only_import_walk_would_be_caught(tmp_path, monkeypatch):
    """Negative control: with the walk narrowed to module-level statements the nested files drop out, so the assertion above can fail."""
    user = _write_modules(tmp_path)
    monkeypatch.setattr(
        rp.env_ast, "imports", lambda tree: [n for n in tree.body if type(n).__name__ == "Import"]
    )
    got = sorted(p.name for p in rp._py_imports_uncached(user, tmp_path))
    assert got == ["top.py"]
