#!/usr/bin/env python3
"""Self-contained template catalog generator for `packages/json` (the `build` script).

Ported from `packages/json/generate.sh` (PLAN-retire-bash-oracles B5, W10). Processes the template directories into one JSON file each, a master `templates.json`, the config files and the static site, then validates and minifies the result into `packages/json/dist/`.

    python3 .ci/rediacc_ci/catalog/generate.py            # from anywhere; stdlib only

STDLIB ONLY, AND RUN BY PATH. `npm run build -w @rediacc/json` has no PYTHONPATH and no virtualenv, so this module imports nothing from `rediacc_ci` and finds `packages/json` from its own location.

EQUIVALENCE WAS MEASURED, NOT ASSUMED. Before the bash was deleted both generators ran on the real templates and every file under `dist/` was compared byte for byte (26 template files, `templates.json`, the two configs, `test-results.json`, `index.html`, `api.html`, `_config.yml`): identical except the `generated` timestamps, and the console output was identical line for line except the order of the "Processing template" lines (see below) and the elapsed time.

DELIBERATE DELTAS FROM THE BASH (Rule T), each with a test in `test_catalog_generate.py` that fails on the bash behaviour:

  * Every string is escaped by a real JSON encoder. The bash escaped five characters; any other control character (an ESC in a README) made invalid JSON, the title was not escaped at all (a `"` in a README heading broke the file), and the build then failed validation.
  * The title and the description are returned as a pair. The bash joined them with `|` and split them again with `cut`, so a `|` in a heading or in the first paragraph (common in markdown tables' prose) truncated the description or shifted it into the title.
  * A README with no `# heading` falls back to the template name. The bash wrote `grep ... | sed ... || echo name`; the pipeline status is sed's, never grep's, so the fallback was dead and the name was empty.
  * The skip list keeps its last line when the file has no trailing newline (`while read` skipped it) and tolerates CRLF and trailing blanks, which made an entry silently fail to match.
  * Template and category order is the byte order of the path, not the locale's `sort` collation. Under a locale such as en_US `docker-compose.yaml` sorted before `README.md`; under C it sorted after, so the same tree produced different files on different machines. The "Processing template" progress lines are sorted too (the bash printed them in directory-read order).
  * `templates.json` carries one `categories` key. The bash wrote an empty `"categories": []` first and the real list last, which only `jq` happened to resolve (last wins); strict readers saw a duplicate key.
  * `jq` is no longer a dependency. Minifying is `json.dumps` with the compact separators, DEL escaped the way `jq` escapes it so the bytes match.
  * Any build step that raises is reported as `[ERROR]` with exit 1 rather than leaving a half-built `dist/` behind a bare traceback.

WHAT STAYS EXACTLY AS IT WAS, because consumers read it: the file layout, the colour codes (printed even when not a tty, as before), the summary text, `generated` timestamps in UTC to the second, hidden files skipped except `.env`, `file_count` counting every regular file (hidden ones too) while a template's `files` list does not, and trailing newlines stripped from every file's content (the shell's `$(cat)` did that, and `dist/` consumers may depend on it).
"""

from __future__ import annotations

import datetime
import json
import pathlib
import re
import shutil
import sys

PACKAGE_DIR = pathlib.Path(__file__).resolve().parents[3] / "packages" / "json"

RED = "\033[0;31m"
GREEN = "\033[0;32m"
BLUE = "\033[0;34m"
YELLOW = "\033[1;33m"
NC = "\033[0m"

CONFIG_FILES = ("endpoints.json", "pricing.json", "services.json")
EMPTY_TEST_RESULTS = (
    '{"summary":{"total":0,"passed":0,"failed":0,"skipped":0,"duration":"0s","timestamp":""},'
    '"results":[]}\n'
)
FILE_TYPES = {
    "md": "markdown",
    "yaml": "yaml",
    "yml": "yaml",
    "json": "json",
    "sh": "script",
    "env": "environment",
    "dockerfile": "dockerfile",
    "Dockerfile": "dockerfile",
}
H1 = re.compile(r"#[^#]")
MARKER_FILES = ("README.md", "docker-compose.yaml", "Rediaccfile")


class BuildError(Exception):
    """A step of the build cannot continue."""


# ---------------------------------------------------------------------------- output


def log_info(msg: str) -> None:
    print("%s[INFO]%s %s" % (BLUE, NC, msg))


def log_success(msg: str) -> None:
    print("%s[SUCCESS]%s %s" % (GREEN, NC, msg))


def log_warning(msg: str) -> None:
    print("%s[WARNING]%s %s" % (YELLOW, NC, msg))


def log_error(msg: str) -> None:
    print("%s[ERROR]%s %s" % (RED, NC, msg))


def utc_stamp() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------- encoding


def enc(value: object) -> str:
    """One JSON value as text: real escaping, non-ASCII kept as UTF-8."""
    return json.dumps(value, ensure_ascii=False)


def minify_text(text: str) -> str:
    """`jq -c .` on `text`: compact, order kept, UTF-8 raw, DEL escaped as jq does."""
    out = json.dumps(json.loads(text), separators=(",", ":"), ensure_ascii=False)
    return out.replace("\x7f", "\\u007f") + "\n"


def read_text(path: pathlib.Path) -> str:
    """File content as the shell's `$(cat file)` gave it: trailing newlines stripped."""
    try:
        return path.read_bytes().decode("utf-8").rstrip("\n")
    except UnicodeDecodeError as exc:
        raise BuildError("%s is not valid UTF-8 (%s)" % (path, exc.reason)) from exc


def file_content(path: pathlib.Path) -> str:
    return read_text(path) if path.is_file() else ""


# ---------------------------------------------------------------------------- templates


def load_skip_list(package_dir: pathlib.Path) -> list[str]:
    """Entries of `.templates-skiplist`: one `category/name` per line, `#` comments."""
    skiplist = package_dir / ".templates-skiplist"
    skips: list[str] = []
    if not skiplist.is_file():
        return skips
    log_info("Loading skip list from .templates-skiplist")
    for raw in skiplist.read_text(encoding="utf-8").split("\n"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        skips.append(line)
        log_info("  ⏭️  Will skip: %s" % line)
    return skips


def split_lines(text: str) -> list[str]:
    """Lines the way awk and grep see them: only `\\n` ends one, and a final newline adds none."""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def template_metadata(template_dir: pathlib.Path) -> tuple[str, str]:
    """(title, description): the first `# heading` and the first paragraph line after it."""
    name = template_dir.name
    readme = template_dir / "README.md"
    title = name
    description = ""
    if readme.is_file():
        lines = split_lines(readme.read_bytes().decode("utf-8", errors="replace"))
        heading = next((ln for ln in lines if H1.match(ln)), None)
        if heading is not None:
            title = re.sub(r"^# *", "", heading)
        found = False
        for line in lines:
            if H1.match(line):
                found = True
                continue
            if not found or line == "":
                continue
            if not line.startswith("#"):
                description = line
                break
    return title, description or "Template for %s" % name


def file_type(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1] if "." in filename else filename
    return FILE_TYPES.get(ext, "text")


def is_template(template_dir: pathlib.Path) -> bool:
    return any((template_dir / marker).is_file() for marker in MARKER_FILES)


def template_dirs(templates_dir: pathlib.Path) -> list[pathlib.Path]:
    """Every `templates/<category>/<name>` directory, in byte order of the path."""
    found: list[pathlib.Path] = []
    if not templates_dir.is_dir():
        return found
    for category in sorted(_subdirs(templates_dir)):
        found.extend(sorted(_subdirs(category)))
    return found


def _subdirs(path: pathlib.Path) -> list[pathlib.Path]:
    return [p for p in path.iterdir() if p.is_dir() and not p.is_symlink()]


def regular_files(directory: pathlib.Path) -> list[pathlib.Path]:
    """Direct children that are regular files (symlinks excluded, as `find -type f`), byte order."""
    return sorted(p for p in directory.iterdir() if p.is_file() and not p.is_symlink())


def template_json_text(template_dir: pathlib.Path, stamp: str) -> str:
    """One template's JSON file, laid out the way the bash wrote it before minifying."""
    name = template_dir.name
    category = template_dir.parent.name
    title, description = template_metadata(template_dir)
    parts = [
        "{\n"
        '  "id": %s,\n  "name": %s,\n  "description": %s,\n  "category": %s,\n'
        '  "tags": [%s, %s],\n  "files": [\n'
        % (
            enc("%s_%s" % (category, name)),
            enc(title),
            enc(description),
            enc(category),
            enc(category),
            enc(name),
        )
    ]
    entries = []
    for file in regular_files(template_dir):
        if file.name.startswith(".") and file.name != ".env":
            continue
        entries.append(
            "    {\n"
            '      "name": %s,\n      "path": %s,\n      "type": %s,\n      "content": %s\n'
            "    }\n"
            % (
                enc(file.name),
                enc("%s/%s" % (name, file.name)),
                enc(file_type(file.name)),
                enc(read_text(file)),
            )
        )
    parts.append(",\n".join(entries))
    parts.append(
        '\n  ],\n  "readme": %s,\n  "generated": %s\n}\n'
        % (enc(file_content(template_dir / "README.md")), enc(stamp))
    )
    return "".join(parts)


def catalog_json_text(templates_dir: pathlib.Path, skips: list[str], stamp: str) -> str:
    """The master `templates.json`, laid out the way the bash wrote it before minifying."""
    dirs = [d for d in template_dirs(templates_dir) if is_template(d)]
    entries = []
    categories: set[str] = set()
    for template_dir in dirs:
        name = template_dir.name
        category = template_dir.parent.name
        categories.add(category)
        title, description = template_metadata(template_dir)
        template_id = "%s_%s" % (category, name)
        status = "skipped" if "%s/%s" % (category, name) in skips else "active"
        entries.append(
            "    {\n"
            '      "id": %s,\n      "name": %s,\n      "description": %s,\n'
            '      "category": %s,\n      "tags": [%s, %s],\n      "file_count": %d,\n'
            '      "has_readme": %s,\n      "has_docker": %s,\n      "status": %s,\n'
            '      "download_url": %s,\n      "readme": %s\n'
            "    }\n"
            % (
                enc(template_id),
                enc(title),
                enc(description),
                enc(category),
                enc(category),
                enc(name),
                len(regular_files(template_dir)),
                "true" if (template_dir / "README.md").is_file() else "false",
                "true" if (template_dir / "docker-compose.yaml").is_file() else "false",
                enc(status),
                enc("templates/%s.json" % template_id),
                enc(file_content(template_dir / "README.md")),
            )
        )
    cats = ",\n".join("    %s" % enc(c) for c in sorted(categories))
    return (
        '{\n  "version": "1.0",\n  "generated": %s,\n  "total_templates": %d,\n'
        '  "categories": [\n%s\n  ],\n  "templates": [\n%s\n  ]\n}\n'
        % (enc(stamp), len(dirs), cats, ",\n".join(entries))
    )


def copy_template_assets(templates_dir: pathlib.Path, assets_out: pathlib.Path) -> None:
    """Copy each `<category>/<name>/assets/*` (dotfiles excluded) into `assets/<category>/`."""
    print("Copying template assets...")
    for assets_dir in sorted(p for p in templates_dir.rglob("assets") if p.is_dir()):
        rel = assets_dir.parent.relative_to(templates_dir)
        if len(rel.parts) < 2:
            continue
        target = assets_out / rel.parts[0]
        target.mkdir(parents=True, exist_ok=True)
        for child in sorted(assets_dir.iterdir()):
            if child.name.startswith("."):
                continue
            if child.is_dir():
                shutil.copytree(child, target / child.name, dirs_exist_ok=True)
            else:
                shutil.copy2(child, target / child.name)
    print("Template assets copied")


# ---------------------------------------------------------------------------- build steps


def clean_build(build_dir: pathlib.Path) -> None:
    log_info("Cleaning build directory...")
    shutil.rmtree(build_dir, ignore_errors=True)
    for sub in ("templates", "configs", "assets"):
        (build_dir / sub).mkdir(parents=True, exist_ok=True)
    log_success("Build directory cleaned")


def process_templates(package_dir: pathlib.Path, build_dir: pathlib.Path, skips: list[str]) -> None:
    log_info("Processing templates...")
    templates_dir = package_dir / "templates"
    stamp = utc_stamp()
    processed = 0
    for template_dir in template_dirs(templates_dir):
        if not is_template(template_dir):
            continue
        category = template_dir.parent.name
        name = template_dir.name
        if "%s/%s" % (category, name) in skips:
            continue
        print("Processing template: %s/%s" % (category, name))
        target = build_dir / "templates" / ("%s_%s.json" % (category, name))
        target.write_text(template_json_text(template_dir, stamp), encoding="utf-8")
        processed += 1
    log_success("Processed %d templates" % processed)

    log_info("Generating templates index...")
    print("Generating template catalog...")
    (build_dir / "templates.json").write_text(
        catalog_json_text(templates_dir, skips, stamp), encoding="utf-8"
    )
    log_success("Templates index generated")

    copy_template_assets(templates_dir, build_dir / "assets")
    log_success("Template assets copied")


def process_configs(package_dir: pathlib.Path, build_dir: pathlib.Path) -> None:
    log_info("Processing configuration files...")
    processed = 0
    config_dir = package_dir / "config"
    for config in sorted(config_dir.glob("*.json")):
        if config.is_file() and config.name in CONFIG_FILES:
            shutil.copy2(config, build_dir / "configs" / config.name)
            processed += 1
    log_success("Processed %d configuration files" % processed)


def generate_website(package_dir: pathlib.Path, build_dir: pathlib.Path) -> None:
    log_info("Generating GitHub Pages website...")
    log_info("Copying website templates...")
    for name in ("index.html", "_config.yml", "api.html"):
        shutil.copy2(package_dir / "src" / name, build_dir / name)
    log_success("GitHub Pages website generated")


def copy_test_results(package_dir: pathlib.Path, build_dir: pathlib.Path) -> None:
    log_info("Copying test results")
    source = package_dir / "test-results.json"
    if source.is_file():
        print("%s✓%s Found test-results.json, copying to build directory" % (GREEN, NC))
        shutil.copy2(source, build_dir / "test-results.json")
    else:
        print("%s⚠%s No test-results.json found, creating empty results file" % (YELLOW, NC))
        (build_dir / "test-results.json").write_text(EMPTY_TEST_RESULTS, encoding="utf-8")
    print()


def _valid_json(path: pathlib.Path) -> bool:
    try:
        json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, ValueError):
        return False
    return True


def validate_output(build_dir: pathlib.Path) -> bool:
    log_info("Validating generated files...")
    errors = 0
    for name in ("index.html", "templates.json", "_config.yml", "api.html"):
        if not (build_dir / name).is_file():
            log_error("Required file missing: %s" % (build_dir / name))
            errors += 1
    catalog = build_dir / "templates.json"
    if catalog.is_file() and not _valid_json(catalog):
        log_error("templates.json is not valid JSON")
        errors += 1
    template_files = 0
    for template_file in sorted((build_dir / "templates").glob("*.json")):
        if not template_file.is_file():
            continue
        if not _valid_json(template_file):
            log_error("Invalid JSON: %s" % template_file.name)
            errors += 1
        template_files += 1
    log_info("Found %d template JSON files" % template_files)
    if errors == 0:
        log_success("All files validated successfully")
        return True
    log_error("Found %d validation errors" % errors)
    return False


def minify_json_files(build_dir: pathlib.Path) -> None:
    log_info("Minifying JSON files...")
    minified = 0
    before_total = 0
    after_total = 0
    for json_file in sorted(p for p in build_dir.rglob("*.json") if p.is_file()):
        size_before = json_file.stat().st_size
        before_total += size_before
        try:
            compact = minify_text(json_file.read_bytes().decode("utf-8"))
        except ValueError:
            log_warning("Failed to minify: %s" % json_file.name)
            after_total += size_before
            continue
        json_file.write_bytes(compact.encode("utf-8"))
        after_total += json_file.stat().st_size
        minified += 1
    if minified > 0:
        savings = before_total - after_total
        percentage = savings * 100 // before_total if before_total > 0 else 0
        log_success(
            "Minified %d JSON files (saved %d bytes, %d%% reduction)"
            % (minified, savings, percentage)
        )
    else:
        log_warning("No JSON files were minified")


def show_summary(build_dir: pathlib.Path) -> None:
    log_info("Generation Summary")
    print("====================")
    print("Build Directory: %s" % build_dir)
    print()
    print("Generated Files:")
    print("  - index.html          (Main website)")
    print("  - templates.json      (Templates index API)")
    print("  - api.html           (API documentation)")
    print("  - _config.yml        (GitHub Pages config)")
    print()
    if (build_dir / "templates").is_dir():
        count = sum(1 for _ in (build_dir / "templates").rglob("*.json"))
        print("  - templates/         (%d template JSON files)" % count)
    if (build_dir / "configs").is_dir():
        count = sum(1 for _ in (build_dir / "configs").rglob("*.json"))
        print("  - configs/           (%d config JSON files)" % count)
    if (build_dir / "assets").is_dir():
        count = sum(1 for p in (build_dir / "assets").rglob("*") if p.is_file())
        print("  - assets/            (%d asset files)" % count)
    print()
    print("Next Steps:")
    print("  1. Test locally: cd %s && python3 -m http.server 8000" % build_dir)
    print("  2. Deploy: Copy build/ contents to your GitHub Pages repository")
    print("  3. Access: Visit your GitHub Pages URL")
    print()


def main(argv: list[str] | None = None, package_dir: pathlib.Path | None = None) -> int:
    del argv  # the generator takes no arguments
    package_dir = package_dir or PACKAGE_DIR
    build_dir = package_dir / "dist"
    log_info("Starting JSON Config Generator")
    print("==============================")
    try:
        skips = load_skip_list(package_dir)
        clean_build(build_dir)
        process_templates(package_dir, build_dir, skips)
        process_configs(package_dir, build_dir)
        generate_website(package_dir, build_dir)
        copy_test_results(package_dir, build_dir)
    except (BuildError, OSError) as exc:
        log_error("Generation failed: %s" % exc)
        return 1
    if not validate_output(build_dir):
        log_error("Generation completed with errors")
        return 1
    minify_json_files(build_dir)
    show_summary(build_dir)
    log_success("Generation completed successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
