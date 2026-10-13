"""`rediacc_ci.catalog.generate`, the port of `packages/json/generate.sh`.

THE BASH TWIN WAS RETIRED WITH THIS FILE (PLAN-retire-bash-oracles B5, W10). Before it went, the bash and the port were both run on the real `packages/json/templates` and every file under `dist/` was compared byte for byte after normalising the `generated` timestamps: 33 files, 0 differing. The cases below hold what that comparison cannot keep alive once the twin is gone: the structural invariants on the real tree, and one test per deliberate delta (Rule T) that fails on the bash behaviour.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from rediacc_ci import paths
from rediacc_ci.catalog import generate

if TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
REAL = ROOT / "packages" / "json"
PORT = ROOT / ".ci" / "rediacc_ci" / "catalog" / "generate.py"


def _package(
    tmp_path: pathlib.Path, templates: dict[str, dict[str, str]], skip: str = ""
) -> pathlib.Path:
    """A throwaway `packages/json`: `templates` maps "cat/name" to {filename: content}."""
    pkg = tmp_path / "pkg"
    (pkg / "src").mkdir(parents=True)
    (pkg / "config").mkdir()
    for name in ("index.html", "api.html", "_config.yml"):
        (pkg / "src" / name).write_text("x\n", encoding="utf-8")
    (pkg / "config" / "endpoints.json").write_text(
        '{"a": 1,\n "b": [1.5, "x"]}\n', encoding="utf-8"
    )
    (pkg / "config" / "other.json").write_text("{}", encoding="utf-8")
    for rel, files in templates.items():
        directory = pkg / "templates" / rel
        directory.mkdir(parents=True)
        for filename, content in files.items():
            (directory / filename).write_bytes(content.encode("utf-8"))
    if skip:
        (pkg / ".templates-skiplist").write_bytes(skip.encode("utf-8"))
    return pkg


def _build(pkg: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    rc = generate.main([], package_dir=pkg)
    return rc, capsys.readouterr().out


def _read(pkg: pathlib.Path, rel: str) -> dict:
    return json.loads((pkg / "dist" / rel).read_text(encoding="utf-8"))


def _no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    keys = [k for k, _ in pairs]
    assert len(keys) == len(set(keys)), "duplicate key in %r" % keys
    return dict(pairs)


# ---------------------------------------------------------------------------- the real tree


@pytest.fixture(scope="module")
def real_build(tmp_path_factory: pytest.TempPathFactory) -> pathlib.Path:
    """The real templates, configs and site, built into a copy so the checkout's `dist/` is untouched."""
    pkg = tmp_path_factory.mktemp("real") / "json"
    shutil.copytree(REAL, pkg, ignore=shutil.ignore_patterns("node_modules", "dist"))
    assert generate.main([], package_dir=pkg) == 0
    return pkg


def test_real_tree_builds_one_file_per_active_template(real_build: pathlib.Path) -> None:
    skips = generate.load_skip_list(real_build)
    expected = {
        "%s_%s.json" % (d.parent.name, d.name)
        for d in generate.template_dirs(real_build / "templates")
        if generate.is_template(d) and "%s/%s" % (d.parent.name, d.name) not in skips
    }
    built = {p.name for p in (real_build / "dist" / "templates").glob("*.json")}
    assert built == expected
    assert len(built) > 10


def test_real_catalog_is_consistent(real_build: pathlib.Path) -> None:
    catalog = json.loads(
        (real_build / "dist" / "templates.json").read_text(encoding="utf-8"),
        object_pairs_hook=_no_duplicate_keys,
    )
    entries = catalog["templates"]
    assert catalog["total_templates"] == len(entries)
    assert catalog["categories"] == sorted({e["category"] for e in entries})
    skipped = {e["id"] for e in entries if e["status"] == "skipped"}
    built = {p.stem for p in (real_build / "dist" / "templates").glob("*.json")}
    assert skipped
    assert not skipped & built
    assert {e["id"] for e in entries if e["status"] == "active"} == built


def test_real_output_is_minified(real_build: pathlib.Path) -> None:
    for path in (real_build / "dist").rglob("*.json"):
        text = path.read_text(encoding="utf-8")
        assert text.endswith("\n")
        compact = json.dumps(json.loads(text), separators=(",", ":"), ensure_ascii=False)
        assert text == compact.replace("\x7f", "\\u007f") + "\n", path.name


# ---------------------------------------------------------------------------- deliberate deltas


def test_title_with_a_quote_and_a_control_character_stay_valid_json(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Rule T: the bash left the title unescaped and escaped only five characters, so this build failed validation."""
    pkg = _package(
        tmp_path,
        {
            "db/odd": {
                "README.md": '# The "odd" \\ one\n\nSee\x1b[0m here.\n',
                "Rediaccfile": "up() { :; }\n",
            }
        },
    )
    rc, out = _build(pkg, capsys)
    assert rc == 0, out
    template = _read(pkg, "templates/db_odd.json")
    assert template["name"] == 'The "odd" \\ one'
    assert "\x1b[0m" in template["readme"]


def test_pipe_in_the_heading_or_description_is_kept(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Rule T: the bash joined title and description with `|` and split with `cut`, truncating at a second pipe."""
    pkg = _package(
        tmp_path,
        {"db/pipe": {"README.md": "# A | B\n\nUse a | b | c for choices.\n", "Rediaccfile": ":\n"}},
    )
    rc, _ = _build(pkg, capsys)
    assert rc == 0
    template = _read(pkg, "templates/db_pipe.json")
    assert template["name"] == "A | B"
    assert template["description"] == "Use a | b | c for choices."


def test_readme_without_a_heading_falls_back_to_the_template_name(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Rule T: the bash fallback sat behind a pipeline whose status is sed's, so the title came out empty."""
    pkg = _package(
        tmp_path,
        {"db/plain": {"README.md": "just prose, no heading\n", "Rediaccfile": ":\n"}},
    )
    rc, _ = _build(pkg, capsys)
    assert rc == 0
    template = _read(pkg, "templates/db_plain.json")
    assert template["name"] == "plain"
    assert template["description"] == "Template for plain"


def test_skiplist_last_line_without_newline_and_crlf(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Rule T: `while read` dropped an unterminated last line, and CRLF made an entry never match."""
    files = {"README.md": "# T\n\nbody\n", "Rediaccfile": ":\n"}
    pkg = _package(
        tmp_path,
        {"a/one": files, "a/two": files, "a/three": files},
        skip="# comment\r\na/one\r\n\r\na/three",
    )
    rc, _ = _build(pkg, capsys)
    assert rc == 0
    built = sorted(p.name for p in (pkg / "dist" / "templates").glob("*.json"))
    assert built == ["a_two.json"]
    catalog = _read(pkg, "templates.json")
    assert {e["id"]: e["status"] for e in catalog["templates"]} == {
        "a_one": "skipped",
        "a_three": "skipped",
        "a_two": "active",
    }


def test_file_and_template_order_is_byte_order(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Rule T: the bash sorted with the locale's collation, so `docker-compose.yaml` moved against `README.md`."""
    pkg = _package(
        tmp_path,
        {
            "b/z": {
                "README.md": "# Z\n\nz\n",
                "docker-compose.yaml": "x: 1\n",
                "Rediaccfile": ":\n",
            },
            "B/y": {"README.md": "# Y\n\ny\n"},
            "a/m": {"README.md": "# M\n\nm\n"},
        },
    )
    rc, _ = _build(pkg, capsys)
    assert rc == 0
    names = [f["name"] for f in _read(pkg, "templates/b_z.json")["files"]]
    assert names == ["README.md", "Rediaccfile", "docker-compose.yaml"]
    catalog = _read(pkg, "templates.json")
    assert [e["id"] for e in catalog["templates"]] == ["B_y", "a_m", "b_z"]
    assert catalog["categories"] == ["B", "a", "b"]


def test_catalog_has_exactly_one_categories_key(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Rule T: the bash wrote `"categories": []` and then the real list; only jq's last-wins hid the duplicate."""
    pkg = _package(tmp_path, {"a/one": {"README.md": "# One\n\nx\n"}})
    rc, _ = _build(pkg, capsys)
    assert rc == 0
    text = (pkg / "dist" / "templates.json").read_text(encoding="utf-8")
    json.loads(text, object_pairs_hook=_no_duplicate_keys)
    assert text.count('"categories"') == 1


def test_build_runs_with_no_jq_on_the_path(tmp_path: pathlib.Path) -> None:
    """Rule T: jq is not a dependency any more."""
    pkg = _package(tmp_path, {"a/one": {"README.md": "# One\n\nx\n"}})
    code = (
        "import pathlib, sys; sys.path.insert(0, %r); "
        "from rediacc_ci.catalog import generate; "
        "sys.exit(generate.main([], package_dir=pathlib.Path(%r)))" % (str(ROOT / ".ci"), str(pkg))
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env={"PATH": str(tmp_path / "nowhere")},
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_a_hash_tag_line_is_not_the_title(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Review d1e160c5.2: `#tag` has no space, so it is not a `# heading`; the real heading below it is."""
    files = {"README.md": "#tag\n\n# Real Title\n\nbody line\n", "Rediaccfile": ":\n"}
    pkg = _package(tmp_path, {"a/one": files})
    rc, _ = _build(pkg, capsys)
    assert rc == 0
    template = _read(pkg, "templates/a_one.json")
    assert template["name"] == "Real Title"
    assert template["description"] == "body line"


def test_a_non_utf8_skiplist_is_a_reported_error_not_a_traceback(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Review d1e160c5.3: the bytes are rejected as a BuildError, so main prints `[ERROR]` and returns 1."""
    files = {"README.md": "# T\n\nbody\n", "Rediaccfile": ":\n"}
    pkg = _package(tmp_path, {"a/one": files})
    (pkg / ".templates-skiplist").write_bytes(b"a/\xff\xfe\n")
    rc, out = _build(pkg, capsys)
    assert rc == 1
    assert "[ERROR]" in out
    assert ".templates-skiplist" in out


def test_minify_matches_jq_for_the_cases_that_matter() -> None:
    assert generate.minify_text('{"a": 1,\n "b": [1.5, "x"]}\n') == '{"a":1,"b":[1.5,"x"]}\n'
    assert generate.minify_text('{"k": "\x7f é"}') == '{"k":"\\u007f é"}\n'
    jq = shutil.which("jq")
    if jq is None:
        pytest.skip("jq is not installed")
    sample = json.dumps(
        {"a": 1, "z": "\x7f \x01 é \u2028", "n": [0.10, 1000.0, True, None]}, ensure_ascii=False
    )
    ours = generate.minify_text(sample)
    assert jq is not None
    theirs = subprocess.run(
        [jq, "-c", "."], input=sample, capture_output=True, text=True, check=True
    )
    assert ours == theirs.stdout


# ---------------------------------------------------------------------------- behaviours kept


def test_hidden_files_are_skipped_except_env_and_counted_in_file_count(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pkg = _package(
        tmp_path,
        {
            "a/one": {
                "README.md": "# One\n\nx\n",
                ".env": "K=v\n",
                ".hidden": "h\n",
                "run.sh": ":\n",
            }
        },
    )
    rc, _ = _build(pkg, capsys)
    assert rc == 0
    names = [f["name"] for f in _read(pkg, "templates/a_one.json")["files"]]
    assert names == [".env", "README.md", "run.sh"]
    entry = _read(pkg, "templates.json")["templates"][0]
    assert entry["file_count"] == 4
    assert entry["download_url"] == "templates/a_one.json"


def test_content_has_trailing_newlines_stripped_and_types_are_mapped(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pkg = _package(
        tmp_path,
        {
            "a/one": {
                "README.md": "# One\n\nx\n\n\n",
                "docker-compose.yaml": "a: 1\n",
                "Dockerfile": "FROM x\n",
            }
        },
    )
    rc, _ = _build(pkg, capsys)
    assert rc == 0
    files = {f["name"]: f for f in _read(pkg, "templates/a_one.json")["files"]}
    assert files["README.md"]["content"] == "# One\n\nx"
    assert files["README.md"]["type"] == "markdown"
    assert files["docker-compose.yaml"]["type"] == "yaml"
    assert files["Dockerfile"]["type"] == "dockerfile"


def test_only_named_configs_are_copied_and_the_empty_results_file_is_made(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pkg = _package(tmp_path, {"a/one": {"README.md": "# One\n\nx\n"}})
    rc, out = _build(pkg, capsys)
    assert rc == 0
    assert [p.name for p in (pkg / "dist" / "configs").iterdir()] == ["endpoints.json"]
    assert _read(pkg, "test-results.json")["summary"]["total"] == 0
    assert "No test-results.json found" in out
    assert "Minified" in out


def test_existing_results_file_is_copied(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pkg = _package(tmp_path, {"a/one": {"README.md": "# One\n\nx\n"}})
    (pkg / "test-results.json").write_text(
        '{"summary": {"total": 7}, "results": []}', encoding="utf-8"
    )
    rc, out = _build(pkg, capsys)
    assert rc == 0
    assert _read(pkg, "test-results.json")["summary"]["total"] == 7
    assert "Found test-results.json" in out


def test_assets_are_copied_under_their_category(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pkg = _package(tmp_path, {"a/one": {"README.md": "# One\n\nx\n"}})
    assets = pkg / "templates" / "a" / "one" / "assets"
    assets.mkdir()
    (assets / "logo.png").write_bytes(b"\x89PNG")
    (assets / ".hidden").write_text("h", encoding="utf-8")
    rc, _ = _build(pkg, capsys)
    assert rc == 0
    assert (pkg / "dist" / "assets" / "a" / "logo.png").read_bytes() == b"\x89PNG"
    assert not (pkg / "dist" / "assets" / "a" / ".hidden").exists()


def test_a_missing_site_file_is_an_error_not_a_traceback(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pkg = _package(tmp_path, {"a/one": {"README.md": "# One\n\nx\n"}})
    (pkg / "src" / "api.html").unlink()
    rc, out = _build(pkg, capsys)
    assert rc == 1
    assert "[ERROR]" in out
    assert "Traceback" not in out


def test_invalid_utf8_in_a_template_is_an_error(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pkg = _package(tmp_path, {"a/one": {"README.md": "# One\n\nx\n"}})
    (pkg / "templates" / "a" / "one" / "blob.txt").write_bytes(b"\xff\xfe")
    rc, out = _build(pkg, capsys)
    assert rc == 1
    assert "not valid UTF-8" in out


def test_validation_fails_the_build(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pkg = _package(tmp_path, {"a/one": {"README.md": "# One\n\nx\n"}})
    dist = pkg / "dist"
    generate.main([], package_dir=pkg)
    capsys.readouterr()
    (dist / "templates" / "broken.json").write_text("{nope", encoding="utf-8")
    assert generate.validate_output(dist) is False
    out = capsys.readouterr().out
    assert "Invalid JSON: broken.json" in out
    assert "Found 1 validation errors" in out
    (dist / "templates.json").unlink()
    assert generate.validate_output(dist) is False
    assert "Required file missing" in capsys.readouterr().out


def test_output_text_keeps_the_shape_consumers_read(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pkg = _package(tmp_path, {"a/one": {"README.md": "# One\n\nx\n"}}, skip="a/none\n")
    rc, out = _build(pkg, capsys)
    assert rc == 0
    for line in (
        "\033[0;34m[INFO]\033[0m Starting JSON Config Generator\n",
        "\033[0;34m[INFO]\033[0m   ⏭️  Will skip: a/none\n",
        "Processing template: a/one\n",
        "\033[0;32m[SUCCESS]\033[0m Processed 1 templates\n",
        "\033[0;32m[SUCCESS]\033[0m All files validated successfully\n",
        "  - templates/         (1 template JSON files)\n",
        "\033[0;32m[SUCCESS]\033[0m Generation completed successfully!\n",
    ):
        assert line in out, line


def test_the_entry_point_runs_by_path_with_no_pythonpath() -> None:
    """`npm run build -w @rediacc/json` has no PYTHONPATH; the module must not need one."""
    source = PORT.read_text(encoding="utf-8")
    assert "from rediacc_ci" not in source
    assert "import rediacc_ci" not in source
    assert generate.PACKAGE_DIR == REAL
