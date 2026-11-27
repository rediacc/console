r"""One parse and one walk per module, shared by the three env-registry scanners.

`env_manifest.names_from_py`, `python_env_registry.derive` and `worklist_env_registry.scan_python` each used to parse every tracked Python module and walk every tree two or three times (cProfile on the real tree: `ast.walk` was 60 of 94 s for the one gate, over about 2,450 modules). The three read the same files in the same process, so this module parses a source text once and walks a tree once, and hands the result to whoever asks next.

What is shared is only the work, never a verdict. `parse` caches a SUCCESS and nothing else: a file that does not parse raises on every call with the caller's own filename in the message, so each scanner still refuses an unparseable file in its own words.

`nodes` is also PRUNED by text. A scanner here only ever accepts a node whose own source span contains an `environ` or `getenv` token, so `parse` records the lines that carry one and `nodes` walks only the subtrees whose line span covers such a line (a decorated definition counts from its first decorator). The pruned walk yields a subsequence of `ast.walk` in the same order, and a tree built elsewhere with plain `ast.parse` (no recorded lines) falls back to the full walk, uncached. A scanner that needs every node, whatever the text (the sealed-module check also flags `putenv` and `unsetenv`), uses `all_nodes`. `imports` walks statements only, because an import is a statement and no expression holds one.

`may_read_env` is the cheap text pre-filter: a source containing neither token cannot yield a read. Its PARSE is never skipped: an unparseable file still refuses, tokens or not.

THE RESULTS LIVE IN SIDE TABLES KEYED BY `id(tree)`, never as an attribute of the tree. A node list that holds the tree, hung on the tree, is a reference cycle, and tearing down a few million cyclic nodes at interpreter exit measured 22 s beside a 10 s scan. `_TREES` keeps every keyed tree alive for the life of the process, so an id is never reused while its entry exists.
"""

from __future__ import annotations

import ast
import atexit
import bisect
import gc
import re
from collections import deque

ENV_TOKENS = ("environ", "getenv")

_TREES: dict[str, ast.Module] = {}
_LINES: dict[int, list[int]] = {}
_NODES: dict[int, list[ast.AST]] = {}
_ALL: dict[int, list[ast.AST]] = {}
_IMPORTS: dict[int, list[ast.AST]] = {}


def may_read_env(source: str) -> bool:
    """False only when `source` cannot contain an environment read at all."""
    return any(token in source for token in ENV_TOKENS)


_TOKEN_RE = re.compile("environ|getenv")


def _token_lines(source: str) -> list[int]:
    """The sorted 1-based line numbers that carry a token, counted without splitting the source."""
    if "\r" in source:
        # A lone carriage return is a line break to the parser but not to `count("\n")`; walk everything rather than guess.
        return list(range(1, source.count("\n") + source.count("\r") + 2))
    out: list[int] = []
    line = 1
    seen = 0
    for hit in _TOKEN_RE.finditer(source):
        line += source.count("\n", seen, hit.start())
        seen = hit.start()
        if not out or out[-1] != line:
            out.append(line)
    return out


def parse(source: str, filename: str = "<unknown>") -> ast.Module:
    """`ast.parse`, memoised per process on the source text. Failures are never cached."""
    tree = _TREES.get(source)
    if tree is None:
        # The cyclic collector re-scans the whole retained heap while a few million nodes are built and again on every later allocation, and that alone cost 3 to 5 s of a 10 s scan (tracked tree, measured). It is paused while the tree is built, and the finished tree is frozen out of later collections: a parse tree holds no cycle, so refcounting still frees it. `release` thaws.
        was_enabled = gc.isenabled()
        gc.disable()
        try:
            tree = ast.parse(source, filename=filename)
            lines = _token_lines(source)
            gc.freeze()
        finally:
            if was_enabled:
                gc.enable()
        _TREES[source] = tree
        _LINES[id(tree)] = lines
    return tree


def _covers(node: ast.AST, lines: list[int]) -> bool:
    """True when the node has no span, or its span holds a token line."""
    start = getattr(node, "lineno", None)
    end = getattr(node, "end_lineno", None)
    if start is None or end is None:
        return True
    for deco in getattr(node, "decorator_list", ()):
        start = min(start, deco.lineno)
    at = bisect.bisect_left(lines, start)
    return at < len(lines) and lines[at] <= end


def _pruned(tree: ast.AST, lines: list[int]) -> list[ast.AST]:
    if not lines:
        return []
    out: list[ast.AST] = []
    todo = deque([tree])
    while todo:
        node = todo.popleft()
        out.append(node)
        todo.extend(child for child in ast.iter_child_nodes(node) if _covers(child, lines))
    return out


def nodes(tree: ast.AST) -> list[ast.AST]:
    """Every node that can be an environment read, in `ast.walk` order, walked once per tree."""
    key = id(tree)
    lines = _LINES.get(key)
    if lines is None:
        return list(ast.walk(tree))
    cached = _NODES.get(key)
    if cached is None:
        cached = _NODES[key] = _pruned(tree, lines)
    return cached


def all_nodes(tree: ast.AST) -> list[ast.AST]:
    """Every node of `tree` in `ast.walk` order, walked once per tree."""
    key = id(tree)
    if key not in _LINES:
        return list(ast.walk(tree))
    cached = _ALL.get(key)
    if cached is None:
        cached = _ALL[key] = list(ast.walk(tree))
    return cached


def _statements(tree: ast.AST) -> list[ast.AST]:
    out: list[ast.AST] = []
    todo = deque([tree])
    while todo:
        node = todo.popleft()
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            out.append(node)
        todo.extend(
            child
            for child in ast.iter_child_nodes(node)
            if isinstance(child, (ast.stmt, ast.ExceptHandler, ast.match_case))
        )
    return out


def imports(tree: ast.AST) -> list[ast.AST]:
    """Every `import` and `from .. import` statement at any depth, in `ast.walk` order."""
    key = id(tree)
    if key not in _LINES:
        return _statements(tree)
    cached = _IMPORTS.get(key)
    if cached is None:
        cached = _IMPORTS[key] = _statements(tree)
    return cached


def release() -> None:
    """Drop every cached tree, results first and trees last (an unordered teardown at exit measured 17 s slower)."""
    for table in (_NODES, _ALL, _IMPORTS, _LINES, _TREES):
        table.clear()
    gc.unfreeze()


atexit.register(release)
