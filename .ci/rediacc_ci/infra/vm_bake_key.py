#!/usr/bin/env python3
"""The bake key for a pre-baked E2E VM image: `vm-bake-v1-<distro>-<YYYY-MM>-<sha256[:16]>`.

PLAN-ci-prebaked-vm-images.md section 2a, box B3. The bake workflow (ci-vm-bake.yml) names each published image by this key, and every E2E Workers leg computes the same key to decide whether a baked image matching its tree exists. Two trees with the same inputs give the same key, a change to any input changes it, and a change anywhere else leaves it alone.

WHAT IS HASHED. The files that decide what `renet ops image build` leaves on the disk:

  * cmd/renet: setup_command.go, pkg_install_retry.go, image_build_command.go, and the
    same-package files they call into (literals.go, system_commands.go for getOSInfo,
    ceph_root.go for DefaultFilesystem, pkg_install_procgroup_unix.go, gpu_drivers.go for
    the GPU driver installs of setup, kernel_modules.go for the kernel swap the AMD install
    runs on zypper, ceph_host_runner.go for the runner those installs use, setup_phase.go
    for the phase markers and download bound pkg_install_retry.go uses);
  * pkg/config, pkg/infra/pkgset (the package registry), pkg/embed (its Go files only,
    so pkg/embed/proxy/** and the staged assets are out), pkg/infra/image;
  * pkg/infra/cephpkg/fingerprint.go, the OpenPGP fingerprint check gpu_drivers.go runs on
    NVIDIA's signing keys before it imports one;
  * pkg/infra/opsconfig/images.go, the base image pins;
  * embed-assets.lock.json, the pinned embedded binaries, and the three NVIDIA signing keys
    under cmd/renet/gpu_keys/ (EXTRA_FILES), which the GPU install trusts and so decide
    what a `--install-nvidia-driver` setup does;
  * this module's own bytes and the v1 salt, so a change to the rules rebakes.

Test files (`*_test.go`) are never hashed: they do not reach the image.

WHAT IS EXCLUDED, BY NAME, and why each one does not shape the guest disk: pkg/datastore (the bake runs no datastore work that the quick path does not redo), pkg/i18n (message text), pkg/infra/vm, vm/kvm and vm/imagedl (they drive the builder VM and fetch the pinned base image; the pin itself is hashed), opsconfig's config.go and parallel.go (fleet plumbing), cmd/renet/main.go and version.go (entry wiring and the build-time version), datastore_readme.go, backup_pull.go (system_commands.go names its methodRsync constant only in the `system check tools` list), pkg/infra/cephpkg/cephpkg.go (gpu_drivers.go uses only that package's fingerprint.go; the Ceph pins and plans reach no image), and the Windows-only process-group file.

COMPLETENESS IS COMPUTED, NOT TRUSTED. `findings()` walks every hashed Go file and follows two kinds of edge: an internal import (and the `pkg.Ident` references through it), and an unqualified reference to a top-level name another file of the same package declares. Every file or package the walk reaches must be classified HASH or EXCLUDE, or it is a finding, and `compute_key()` refuses to produce a key while any finding stands. A new internal import in setup_command.go therefore fails the key rather than silently leaving the new package out of it. The walk is lexical, not type-checked: a method reached only through a value is not followed, and a local variable that shares a top-level name makes the walk reach further than it needs to, never less far.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import pathlib
import re
import sys
from typing import TYPE_CHECKING

from rediacc_ci import paths

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

SALT = "vm-bake-v1"
HASH = "hash"
EXCLUDE = "exclude"

# Package directory (relative to the renet root) -> a verdict for the whole package, or a per-file map for a package that is only partly an input. A file of a partial package that the walk reaches and this map does not name is a finding.
PACKAGES: dict[str, str | dict[str, str]] = {
    "cmd/renet": {
        "setup_command.go": HASH,
        "pkg_install_retry.go": HASH,
        # Setup phase markers, heartbeats and the dnf/zypper download bound that pkg_install_retry.go calls (renet 2be6f4b).
        "setup_phase.go": HASH,
        "image_build_command.go": HASH,
        "literals.go": HASH,
        "system_commands.go": HASH,
        "ceph_root.go": HASH,
        "pkg_install_procgroup_unix.go": HASH,
        # GPU driver installs are part of setup (--install-amd-driver, --install-nvidia-driver); hostRunner is the runner they use.
        "gpu_drivers.go": HASH,
        # The kernel-module swap the AMD install runs on a zypper host with kernel-default-base (kernelModuleInstall).
        "kernel_modules.go": HASH,
        "ceph_host_runner.go": HASH,
        "pkg_install_procgroup_windows.go": EXCLUDE,
        "main.go": EXCLUDE,
        "version.go": EXCLUDE,
        "datastore_readme.go": EXCLUDE,
        # methodRsync ("rsync") is named only in `renet system check tools`'s list.
        "backup_pull.go": EXCLUDE,
    },
    "pkg/config": HASH,
    "pkg/infra/pkgset": HASH,
    # gpu_drivers.go uses only KeyFingerprint and NormalizeFingerprint. The pins, plans and embedded Ceph keys of cephpkg.go shape
    # no image, so a Ceph pin bump must not rebake every VM image.
    "pkg/infra/cephpkg": {
        "fingerprint.go": HASH,
        "cephpkg.go": EXCLUDE,
    },
    "pkg/embed": HASH,
    "pkg/infra/image": HASH,
    "pkg/infra/opsconfig": {
        "images.go": HASH,
        "config.go": EXCLUDE,
        "parallel.go": EXCLUDE,
    },
    "pkg/datastore": EXCLUDE,
    "pkg/i18n": EXCLUDE,
    "pkg/infra/vm": EXCLUDE,
    "pkg/infra/vm/kvm": EXCLUDE,
    "pkg/infra/vm/imagedl": EXCLUDE,
}

# Non-Go inputs, relative to the renet root: the pinned embedded binaries and the NVIDIA repository signing keys gpu_drivers.go embeds.
EXTRA_FILES = (
    "embed-assets.lock.json",
    "cmd/renet/gpu_keys/1940C73E.pub",
    "cmd/renet/gpu_keys/3A8B5622.pub",
    "cmd/renet/gpu_keys/CDF6BA43.pub",
)

KEY_RE = re.compile(r"^vm-bake-v1-[a-z0-9][a-z0-9.-]*-\d{4}-\d{2}-[0-9a-f]{16}$")
_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_IDENT_RE = re.compile(r"[A-Za-z_]\w*")
_QUALIFIED_RE = re.compile(r"\b([A-Za-z_]\w*)\s*\.\s*([A-Za-z_]\w*)")
_IMPORT_SPEC_RE = re.compile(r'^\s*([A-Za-z_]\w*|\.)?\s*"([^"]+)"', re.MULTILINE)
_GO_KEYWORDS = frozenset(
    [
        "break",
        "case",
        "chan",
        "const",
        "continue",
        "default",
        "defer",
        "else",
        "fallthrough",
        "for",
        "func",
        "go",
        "goto",
        "if",
        "import",
        "interface",
        "map",
        "package",
        "range",
        "return",
        "select",
        "struct",
        "switch",
        "type",
        "var",
    ]
)
_SKIP_NAMES = frozenset({"_", "init", "main"})


class BakeKeyError(RuntimeError):
    """The key cannot be computed: an unclassified input, a missing file, or a bad argument."""


def default_renet_root() -> pathlib.Path:
    return paths.repo_root() / "private" / "renet"


_LEXEME_RE = re.compile(
    r"//[^\n]*|/\*.*?\*/|\"(?:\\.|[^\"\\\n])*\"|`[^`]*`|'(?:\\.|[^'\\\n])*'", re.DOTALL
)


def _blank_go(text: str, keep_strings: bool = False) -> str:
    """Go source with comments removed and, unless `keep_strings`, string and rune bodies emptied."""

    def repl(m: re.Match[str]) -> str:
        lexeme = m.group(0)
        if lexeme.startswith("//"):
            return ""
        if lexeme.startswith("/*"):
            return " "
        return lexeme if keep_strings else lexeme[0] * 2

    return _LEXEME_RE.sub(repl, text)


def _module_path(root: pathlib.Path) -> str:
    gomod = root / "go.mod"
    try:
        text = gomod.read_text(encoding="utf-8")
    except OSError as exc:
        raise BakeKeyError("cannot read %s: %s" % (gomod, exc)) from exc
    m = re.search(r"^module\s+(\S+)", text, re.MULTILINE)
    if not m:
        raise BakeKeyError("%s has no module line" % gomod)
    return m.group(1)


def _imports(text: str) -> list[tuple[str | None, str]]:
    """(alias, import path) for every import in comment-stripped, string-kept source."""
    blocks = re.finditer(r"^import\s*(\((.*?)^\)|[^\n]*)", text, re.MULTILINE | re.DOTALL)
    return [
        (spec.group(1), spec.group(2))
        for m in blocks
        for spec in _IMPORT_SPEC_RE.finditer(m.group(2) if m.group(2) is not None else m.group(1))
    ]


def _declarations(text: str) -> set[str]:
    """Top-level names a blanked Go file declares (functions without receivers, var, const, type)."""
    names: set[str] = set()
    for m in re.finditer(r"^func\s+([A-Za-z_]\w*)", text, re.MULTILINE):
        names.add(m.group(1))
    for m in re.finditer(r"^(?:var|const|type)\s+([A-Za-z_]\w*)", text, re.MULTILINE):
        names.add(m.group(1))
    for block in re.finditer(r"^(?:var|const|type)\s*\((.*?)^\)", text, re.MULTILINE | re.DOTALL):
        for line in re.finditer(
            r"^[ \t]([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*)", block.group(1), re.MULTILINE
        ):
            names.update(part.strip() for part in line.group(1).split(","))
    return names


def _unqualified_refs(text: str) -> set[str]:
    refs: set[str] = set()
    for m in _IDENT_RE.finditer(text):
        k = m.start() - 1
        while k >= 0 and text[k] in " \t":
            k -= 1
        if k >= 0 and text[k] == ".":
            continue
        refs.add(m.group(0))
    return refs - _GO_KEYWORDS


def _package_files(root: pathlib.Path, pkg: str) -> list[pathlib.Path]:
    d = root / pkg
    if not d.is_dir():
        return []
    return sorted(p for p in d.glob("*.go") if p.is_file() and not p.name.endswith("_test.go"))


class _Tree:
    """Parsed view of the renet tree, one Go file at a time, cached."""

    def __init__(self, root: pathlib.Path) -> None:
        self.root = root
        self.module = _module_path(root)
        self._blank: dict[pathlib.Path, str] = {}
        self._kept: dict[pathlib.Path, str] = {}
        self._decls: dict[str, dict[str, list[str]]] = {}

    def blank(self, f: pathlib.Path) -> str:
        if f not in self._blank:
            self._blank[f] = _blank_go(f.read_text(encoding="utf-8", errors="replace"))
        return self._blank[f]

    def kept(self, f: pathlib.Path) -> str:
        if f not in self._kept:
            text = f.read_text(encoding="utf-8", errors="replace")
            self._kept[f] = _blank_go(text, keep_strings=True)
        return self._kept[f]

    def decls(self, pkg: str) -> dict[str, list[str]]:
        """Top-level name -> the file names in `pkg` that declare it."""
        if pkg not in self._decls:
            table: dict[str, list[str]] = {}
            for f in _package_files(self.root, pkg):
                for name in _declarations(self.blank(f)):
                    table.setdefault(name, []).append(f.name)
            self._decls[pkg] = table
        return self._decls[pkg]

    def internal_pkg(self, import_path: str) -> str | None:
        prefix = self.module + "/"
        return import_path[len(prefix) :] if import_path.startswith(prefix) else None


def hashed_files(root: pathlib.Path) -> list[pathlib.Path]:
    """Every renet file the key hashes, sorted by its path relative to `root`."""
    files: list[pathlib.Path] = []
    for pkg, verdict in PACKAGES.items():
        if verdict == HASH:
            files.extend(_package_files(root, pkg))
        elif isinstance(verdict, dict):
            files.extend(root / pkg / name for name, v in verdict.items() if v == HASH)
    files.extend(root / name for name in EXTRA_FILES)
    return sorted(set(files), key=lambda p: p.relative_to(root).as_posix())


def _classify_file(pkg: str, name: str) -> str | None:
    verdict = PACKAGES.get(pkg)
    if verdict is None:
        return None
    if isinstance(verdict, dict):
        return verdict.get(name)
    return verdict


def _stale_rules(root: pathlib.Path) -> list[str]:
    """Classified inputs the tree no longer has: a rename must not drop a file from the key."""
    out = [
        "%s: hashed package has no Go files (renamed or moved?)" % pkg
        for pkg, verdict in PACKAGES.items()
        if verdict == HASH and not _package_files(root, pkg)
    ]
    out += [
        "%s/%s: classified but missing (renamed or moved?)" % (pkg, name)
        for pkg, verdict in PACKAGES.items()
        if isinstance(verdict, dict)
        for name in verdict
        if not (root / pkg / name).is_file()
    ]
    out += ["%s: hashed input is missing" % n for n in EXTRA_FILES if not (root / n).is_file()]
    return out


def _same_package_findings(tree: _Tree, f: pathlib.Path, pkg: str, rel: str) -> list[str]:
    """Unqualified references from `f` to a sibling file its partial package leaves unclassified."""
    if not isinstance(PACKAGES.get(pkg), dict):
        return []  # a whole-HASH package has no unhashed sibling to reach
    blank = tree.blank(f)
    decls = tree.decls(pkg)
    return [
        "%s references %s, declared in %s/%s, which is neither hashed nor excluded"
        % (rel, ident, pkg, target)
        for ident in sorted(_unqualified_refs(blank) - _declarations(blank) - _SKIP_NAMES)
        for target in decls.get(ident, ())
        if target != f.name and _classify_file(pkg, target) is None
    ]


def _import_findings(tree: _Tree, f: pathlib.Path, rel: str) -> list[str]:
    """Internal imports of `f` into unclassified packages or unclassified files of a partial one."""
    out: list[str] = []
    qualified = sorted({(m.group(1), m.group(2)) for m in _QUALIFIED_RE.finditer(tree.blank(f))})
    for alias, path in _imports(tree.kept(f)):
        dep = tree.internal_pkg(path)
        if dep is None or alias == "_":
            continue
        dep_verdict = PACKAGES.get(dep)
        if dep_verdict is None:
            out.append("%s imports %s, which is neither hashed nor excluded" % (rel, dep))
        elif isinstance(dep_verdict, dict) and alias == ".":
            out.append("%s dot-imports %s, which is only partly classified" % (rel, dep))
        elif isinstance(dep_verdict, dict):
            local = alias or dep.rsplit("/", 1)[-1]
            dep_decls = tree.decls(dep)
            out += [
                "%s uses %s.%s, declared in %s/%s, which is neither hashed nor excluded"
                % (rel, local, ident, dep, target)
                for qual, ident in qualified
                if qual == local
                for target in dep_decls.get(ident, ())
                if _classify_file(dep, target) is None
            ]
    return out


def findings(root: pathlib.Path) -> list[str]:
    """Why the classification is incomplete for this tree; empty when every reached input is classified."""
    tree = _Tree(root)
    out = _stale_rules(root)
    for f in hashed_files(root):
        if f.suffix != ".go" or not f.is_file():
            continue
        rel = f.relative_to(root).as_posix()
        pkg = f.parent.relative_to(root).as_posix()
        out += _same_package_findings(tree, f, pkg, rel)
        out += _import_findings(tree, f, rel)
    return sorted(set(out))


def known_distros(root: pathlib.Path) -> set[str]:
    images = root / "pkg" / "infra" / "opsconfig" / "images.go"
    try:
        text = images.read_text(encoding="utf-8")
    except OSError as exc:
        raise BakeKeyError("cannot read %s: %s" % (images, exc)) from exc
    return set(re.findall(r'\bName:\s*"([^"]+)"', text))


def digest(root: pathlib.Path) -> str:
    """sha256[:16] over the salt, this module's bytes and every hashed file (path and content)."""
    problems = findings(root)
    if problems:
        raise BakeKeyError(
            "the bake key's input set is incomplete; classify each in %s:\n  %s"
            % (pathlib.Path(__file__).name, "\n  ".join(problems))
        )
    h = hashlib.sha256()
    h.update(SALT.encode() + b"\0")
    self_bytes = pathlib.Path(__file__).read_bytes()
    h.update(b"vm_bake_key.py\0%d\0" % len(self_bytes) + self_bytes)
    for f in hashed_files(root):
        data = f.read_bytes()
        h.update(f.relative_to(root).as_posix().encode() + b"\0%d\0" % len(data) + data)
    return h.hexdigest()[:16]


def compute_key(root: pathlib.Path, distro: str, month: str | None = None) -> str:
    if month is None:
        month = datetime.datetime.now(datetime.UTC).strftime("%Y-%m")
    if not _MONTH_RE.match(month):
        raise BakeKeyError("--month must be YYYY-MM, got %r" % month)
    distros = known_distros(root)
    if distro not in distros:
        raise BakeKeyError(
            "unknown distro %r; images.go names: %s" % (distro, ", ".join(sorted(distros)))
        )
    return "%s-%s-%s-%s" % (SALT, distro, month, digest(root))


def _relative(files: Iterable[pathlib.Path], root: pathlib.Path) -> list[str]:
    return [f.relative_to(root).as_posix() for f in files]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m rediacc_ci.infra.vm_bake_key",
        description="Print the pre-baked VM image key for one distro.",
    )
    parser.add_argument("--distro", help="ops image name, e.g. ubuntu-24.04")
    parser.add_argument("--month", help="YYYY-MM (default: the current UTC month)")
    parser.add_argument(
        "--renet-root", type=pathlib.Path, help="renet checkout (default: private/renet)"
    )
    parser.add_argument(
        "--list-inputs", action="store_true", help="print the hashed files and exit"
    )
    parser.add_argument(
        "--check", action="store_true", help="only verify the input set is complete"
    )
    args = parser.parse_args(argv)
    root = (args.renet_root or default_renet_root()).resolve()
    try:
        if args.list_inputs:
            print("\n".join(_relative(hashed_files(root), root)))
            return 0
        if args.check:
            problems = findings(root)
            for p in problems:
                print(p, file=sys.stderr)
            return 1 if problems else 0
        if not args.distro:
            parser.error("--distro is required unless --list-inputs or --check is given")
        print(compute_key(root, args.distro, args.month))
        return 0
    except BakeKeyError as exc:
        print("vm_bake_key: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
