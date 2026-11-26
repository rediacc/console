"""check:ci-detect-wasm -- the account server's committed detector WASM is exactly what the renet gitlink builds.

WHY. The account Worker and the on-premise Node server score shipped forensics batches with `detect.wasm`, a `GOOS=js GOARCH=wasm` build of renet's own `pkg/detect` and `pkg/models` (agent/plans/PLAN-forensics-detection.md D6). The binary is committed in private/account beside Go's `wasm_exec.js` and `detect-wasm.json` (the digest of the renet inputs the build reads, Go version, model key, both sha256s), because a Worker cannot run Go and a TypeScript port would be a second implementation that drifts. A committed binary drifts too, just silently: a renet change to the detector, a gitlink bump without a rebuild, or a hand-touched byte would leave the server scoring with code no source describes. This gate is FD11: it rebuilds from the gitlink and compares.

PROVENANCE IS A DIGEST OF THE INPUTS, NOT THE COMMIT. The json used to record the renet commit, so every renet commit, a test-only one included, made the committed manifest stale and forced an account commit. `renet_inputs_sha256` is `./build.sh detect_wasm_inputs`: a sha256 over the non-test source files (and go:embed targets) of the module's packages in the GOOS=js GOARCH=wasm dependency closure of `cmd/detectwasm`, plus go.mod and go.sum. Only a change the WASM build can read moves it; a test, a doc or any other renet package does not.

THE RULES, in the order they are checked.
- R1 manifest: the three files exist, the json carries every field, and its two sha256s are the committed files' own. A flipped byte in a copy fails here first.
- R2 provenance: `renet_inputs_sha256` equals the digest the checkout at the console's private/renet gitlink computes now, and `go_version` is the `GO_VERSION` pin of .devcontainer/toolchain.env.
- R3 reproduction: `./build.sh detect_wasm <tmp>` at the gitlink, under the pinned Go and the json's model key, writes byte-identical `detect.wasm` and `wasm_exec.js` and the same json fields. A changed byte whose sha256 was also rewritten in the json passes R1 and fails here.

WHAT CANNOT RUN (exit 77, never a pass). private/renet or the artifact directory not checked out; the renet checkout not at its gitlink, since the rebuild would then describe some other source (a dirty working tree is judged as it stands and the verdict line says so, because the digest and the rebuild both read the files on disk); `go` missing or not at the pin, since a different toolchain emits different bytes and the comparison would be about the machine; the rebuild itself failing. Each refusal names the fix.

`--artifact-dir` compares another directory (a copy) against the same rebuild; it exists for the gate test's planted copies and is printed in every verdict line. CI never passes it.

Exit 0 identical, 1 finding, 2 a control did not behave, 77 cannot run.

---- gate ----
step: Check the detector WASM rebuilds from the renet gitlink
lane: quality-go
needs: go, submodules
selftest: true
why: private/account commits a WASM build of renet's detector; a rebuild at the gitlink must
     match it byte for byte, or the server scores with code no source describes.
---- end gate ----
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

from rediacc_ci import paths

RENET_REL = "private/renet"
ARTIFACT_REL = "private/account/src/services/forensics-detect/wasm"
TOOLCHAIN_REL = ".devcontainer/toolchain.env"
WASM = "detect.wasm"
EXEC = "wasm_exec.js"
MANIFEST = "detect-wasm.json"
FIELDS = (
    "renet_inputs_sha256",
    "go_version",
    "model_public_key",
    "sha256",
    "wasm_exec_sha256",
)
EXIT_CANNOT_RUN = 77
REBUILD_HINT = (
    "Rebuild and commit: (cd private/renet && ./build.sh detect_wasm ../account/src/services/forensics-detect/wasm),"
    " then commit the three files in private/account and bump its gitlink."
)

RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[0;33m"
NC = "\033[0m"


class CannotRunError(Exception):
    """No comparison is possible here; exit 77, never a verdict."""


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_manifest(directory: str) -> tuple[dict | None, list[str]]:
    """(the parsed json or None, R1 findings about presence and shape)."""
    findings = [
        "%s/%s is missing (R1). %s" % (directory, name, REBUILD_HINT)
        for name in (WASM, EXEC, MANIFEST)
        if not os.path.isfile(os.path.join(directory, name))
    ]
    if findings:
        return None, findings
    try:
        with open(os.path.join(directory, MANIFEST), encoding="utf-8") as fh:
            data = json.load(fh)
    except ValueError as exc:
        return None, [
            "%s/%s does not parse: %s (R1). %s" % (directory, MANIFEST, exc, REBUILD_HINT)
        ]
    if not isinstance(data, dict):
        return None, ["%s/%s is not a JSON object (R1)" % (directory, MANIFEST)]
    missing = [f for f in FIELDS if f not in data]
    if missing:
        return None, [
            "%s/%s lacks %s (R1). %s" % (directory, MANIFEST, ", ".join(missing), REBUILD_HINT)
        ]
    return data, []


def consistency_findings(directory: str, manifest: dict) -> list[str]:
    """R1: the json's sha256s describe the committed files."""
    out: list[str] = []
    for name, field in ((WASM, "sha256"), (EXEC, "wasm_exec_sha256")):
        got = sha256_of(os.path.join(directory, name))
        if got != manifest[field]:
            out.append(
                "%s/%s has sha256 %s but %s records %s=%s: the binary was changed without a rebuild (R1). %s"
                % (directory, name, got, MANIFEST, field, manifest[field], REBUILD_HINT)
            )
    return out


def provenance_findings(manifest: dict, inputs: str, go_pin: str) -> list[str]:
    """R2: built from the detector inputs the gitlink has, under the pinned Go."""
    out: list[str] = []
    if manifest["renet_inputs_sha256"] != inputs:
        out.append(
            "%s records renet_inputs_sha256 %s but the detector inputs of %s now hash to %s: a file the detector build reads (pkg/detect, pkg/models, cmd/detectwasm, go.mod, go.sum) changed without a rebuild (R2). %s"
            % (MANIFEST, manifest["renet_inputs_sha256"], RENET_REL, inputs, REBUILD_HINT)
        )
    if manifest["go_version"] != go_pin:
        out.append(
            "%s records go_version %s but %s pins %s: rebuild under the pinned toolchain (R2). %s"
            % (MANIFEST, manifest["go_version"], TOOLCHAIN_REL, go_pin, REBUILD_HINT)
        )
    return out


def reproduction_findings(committed: str, rebuilt: str) -> list[str]:
    """R3: the rebuild's bytes and json fields equal the committed ones."""
    out: list[str] = []
    for name in (WASM, EXEC):
        want = sha256_of(os.path.join(committed, name))
        got = sha256_of(os.path.join(rebuilt, name))
        if want != got:
            out.append(
                "%s/%s (sha256 %s) is not what the gitlink builds (sha256 %s) (R3). %s"
                % (committed, name, want, got, REBUILD_HINT)
            )
    with open(os.path.join(committed, MANIFEST), encoding="utf-8") as fh:
        want_m = json.load(fh)
    with open(os.path.join(rebuilt, MANIFEST), encoding="utf-8") as fh:
        got_m = json.load(fh)
    out.extend(
        "%s/%s field %s is %s; the rebuild writes %s (R3). %s"
        % (
            committed,
            MANIFEST,
            field,
            json.dumps(want_m.get(field)),
            json.dumps(got_m.get(field)),
            REBUILD_HINT,
        )
        for field in FIELDS
        if want_m.get(field) != got_m.get(field)
    )
    return out


def go_pin(root: str) -> str:
    path = os.path.join(root, TOOLCHAIN_REL)
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        raise CannotRunError("%s is unreadable: %s" % (TOOLCHAIN_REL, exc)) from exc
    m = re.search(r"^GO_VERSION=(\S+)$", text, re.MULTILINE)
    if not m:
        raise CannotRunError(
            "%s carries no GO_VERSION line, so the pinned Go is unknown" % TOOLCHAIN_REL
        )
    return "go" + m.group(1)


def _git(*args: str) -> str:
    proc = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise CannotRunError("git %s failed: %s" % (" ".join(args), proc.stderr.strip()))
    return proc.stdout


def gitlink_of(root: str) -> str:
    """The commit the console's INDEX records for private/renet (so a staged bump is what gets judged)."""
    out = _git("-C", root, "ls-files", "-s", "--", RENET_REL).split()
    if len(out) < 2 or out[0] != "160000":
        raise CannotRunError("%s is not a gitlink in the console index" % RENET_REL)
    return out[1]


def detector_inputs(renet: str) -> str:
    """`./build.sh detect_wasm_inputs`: the digest of every file the WASM build reads."""
    env = dict(os.environ)
    env["GOTOOLCHAIN"] = "local"
    proc = subprocess.run(
        ["bash", os.path.join(renet, "build.sh"), "detect_wasm_inputs"],
        cwd=renet,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    digest = proc.stdout.strip()
    if proc.returncode != 0 or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise CannotRunError(
            "./build.sh detect_wasm_inputs exited %d and printed %r, so the inputs digest is unknown:\n%s"
            % (proc.returncode, digest[:80], "\n".join(proc.stderr.strip().splitlines()[-20:]))
        )
    return digest


def renet_checkout_state(renet: str) -> tuple[str, bool]:
    head = _git("-C", renet, "rev-parse", "HEAD").strip()
    dirty = bool(_git("-C", renet, "status", "--porcelain").strip())
    return head, dirty


def local_go_version() -> str:
    go = shutil.which("go")
    if go is None:
        raise CannotRunError(
            "`go` is not on PATH, so nothing can be rebuilt. Install the pinned toolchain: ./run.sh setup (or the setup-go step in CI)"
        )
    proc = subprocess.run([go, "env", "GOVERSION"], capture_output=True, text=True, check=False)
    if proc.returncode != 0 or not proc.stdout.strip():
        raise CannotRunError("`go env GOVERSION` failed: %s" % proc.stderr.strip())
    return proc.stdout.strip()


def rebuild(renet: str, out_dir: str, model_key: str) -> None:
    env = dict(os.environ)
    env.pop("MODEL_ED25519_PUBLIC_KEY", None)
    if model_key:
        env["MODEL_ED25519_PUBLIC_KEY"] = model_key
    # GOTOOLCHAIN=local: a go.mod `toolchain` line must not fetch another Go behind the pin check above.
    env["GOTOOLCHAIN"] = "local"
    proc = subprocess.run(
        ["bash", os.path.join(renet, "build.sh"), "detect_wasm", out_dir],
        cwd=renet,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        tail = "\n".join((proc.stdout + proc.stderr).strip().splitlines()[-20:])
        raise CannotRunError(
            "./build.sh detect_wasm exited %d, so nothing was compared:\n%s"
            % (proc.returncode, tail)
        )
    for name in (WASM, EXEC, MANIFEST):
        if not os.path.isfile(os.path.join(out_dir, name)):
            raise CannotRunError("./build.sh detect_wasm exited 0 but wrote no %s" % name)


def judge(root: str, artifact: str) -> dict:
    renet = os.path.join(root, RENET_REL)
    if not os.path.isfile(os.path.join(renet, "build.sh")):
        raise CannotRunError(
            "%s is not checked out; run `git submodule update --init %s`" % (RENET_REL, RENET_REL)
        )
    if not os.path.isdir(artifact):
        raise CannotRunError(
            "%s is not there; run `git submodule update --init private/account`" % artifact
        )
    manifest, findings = read_manifest(artifact)
    if manifest is None:
        return {"findings": findings, "rebuilt": False}
    findings = consistency_findings(artifact, manifest)
    gitlink = gitlink_of(root)
    pin = go_pin(root)
    head, dirty = renet_checkout_state(renet)
    if head != gitlink:
        raise CannotRunError(
            "%s is checked out at %s but its gitlink is %s; run `git submodule update %s`"
            % (RENET_REL, head[:12], gitlink[:12], RENET_REL)
        )
    local = local_go_version()
    if local != pin:
        raise CannotRunError(
            "the local Go is %s but %s pins %s; a different toolchain emits different bytes. Install %s (./run.sh setup)"
            % (local, TOOLCHAIN_REL, pin, pin)
        )
    inputs = detector_inputs(renet)
    findings += provenance_findings(manifest, inputs, pin)
    with tempfile.TemporaryDirectory(prefix="detect-wasm-") as tmp:
        rebuild(renet, tmp, str(manifest["model_public_key"]))
        findings += reproduction_findings(artifact, tmp)
        size = os.path.getsize(os.path.join(tmp, WASM))
    return {
        "findings": findings,
        "rebuilt": True,
        "gitlink": gitlink,
        "dirty": dirty,
        "inputs": inputs,
        "go": pin,
        "size": size,
        "sha256": manifest["sha256"],
    }


# ---- selftest ------------------------------------------------------------------

INPUTS = "a" * 64
PIN = "go1.0.0"


def _write_artifact(directory: str, wasm: bytes, exec_js: bytes, **overrides) -> None:
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, WASM), "wb") as fh:
        fh.write(wasm)
    with open(os.path.join(directory, EXEC), "wb") as fh:
        fh.write(exec_js)
    manifest = {
        "renet_inputs_sha256": INPUTS,
        "go_version": PIN,
        "model_public_key": "",
        "sha256": hashlib.sha256(wasm).hexdigest(),
        "wasm_exec_sha256": hashlib.sha256(exec_js).hexdigest(),
    }
    manifest.update(overrides)
    with open(os.path.join(directory, MANIFEST), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)


def _flip(data: bytes, at: int) -> bytes:
    return data[:at] + bytes([data[at] ^ 0x01]) + data[at + 1 :]


def controls_fired() -> list[str]:
    """Each plant over scratch directories; returns the plants that did NOT behave. Exercises R1-R3's helpers with no build, so it runs in milliseconds before every real verdict."""
    missed: list[str] = []
    wasm = b"\x00asm\x01\x00\x00\x00" + bytes(range(256)) * 4
    exec_js = b"globalThis.Go = class {};\n"

    def expect(label: str, findings: list[str], needle: str | None) -> None:
        if needle is None and findings:
            missed.append("%s: fired where it must stay silent: %s" % (label, findings))
        elif needle is not None and not any(needle in f for f in findings):
            missed.append("%s: did not report %r (got %s)" % (label, needle, findings or "nothing"))

    def all_findings(committed: str, rebuilt: str) -> list[str]:
        manifest, found = read_manifest(committed)
        if manifest is None:
            return found
        return (
            consistency_findings(committed, manifest)
            + provenance_findings(manifest, INPUTS, PIN)
            + reproduction_findings(committed, rebuilt)
        )

    with tempfile.TemporaryDirectory() as tmp:
        rebuilt = os.path.join(tmp, "rebuilt")
        _write_artifact(rebuilt, wasm, exec_js)

        def case(
            label: str, needle: str | None, w: bytes = wasm, e: bytes = exec_js, **overrides
        ) -> None:
            committed = os.path.join(tmp, "c%d" % len(os.listdir(tmp)))
            _write_artifact(committed, w, e, **overrides)
            expect(label, all_findings(committed, rebuilt), needle)

        # CONTROL 0 first: an identical copy is silent, or every red below is the fixture's doing.
        case("CONTROL 0 identical artifact", None)
        if missed:
            return missed
        flipped = _flip(wasm, 100)
        case(
            "R1 one flipped byte, json untouched",
            "changed without a rebuild",
            w=flipped,
            sha256=hashlib.sha256(wasm).hexdigest(),
        )
        case(
            "R3 one flipped byte, json sha rewritten to match",
            "is not what the gitlink builds",
            w=flipped,
        )
        case("R3 wasm_exec.js changed", "wasm_exec.js (sha256", e=exec_js + b"//\n")
        case(
            "R2 detector inputs changed",
            "changed without a rebuild (R2)",
            renet_inputs_sha256="b" * 64,
        )
        case("R2 unpinned Go", "rebuild under the pinned toolchain", go_version="go9.9.9")
        case(
            "R3 model key differs from the rebuild", "field model_public_key", model_public_key="k"
        )
        committed = os.path.join(tmp, "missing")
        _write_artifact(committed, wasm, exec_js)
        os.unlink(os.path.join(committed, EXEC))
        expect("R1 a file missing", all_findings(committed, rebuilt), "wasm_exec.js is missing")
        committed = os.path.join(tmp, "nofield")
        _write_artifact(committed, wasm, exec_js)
        with open(os.path.join(committed, MANIFEST), "w", encoding="utf-8") as fh:
            json.dump({"sha256": "x"}, fh)
        expect("R1 a field missing", all_findings(committed, rebuilt), "lacks renet_inputs_sha256")
        # Negative: the json's key order and whitespace are not part of the comparison, only its fields.
        committed = os.path.join(tmp, "reordered")
        _write_artifact(committed, wasm, exec_js)
        with open(os.path.join(committed, MANIFEST), encoding="utf-8") as fh:
            data = json.load(fh)
        with open(os.path.join(committed, MANIFEST), "w", encoding="utf-8") as fh:
            json.dump(dict(reversed(list(data.items()))), fh)
        expect("negative: reordered json is the same json", all_findings(committed, rebuilt), None)
    try:
        go_pin(tempfile.gettempdir() + "/detect-wasm-no-such-root")
        missed.append("anti-vacuity: a missing toolchain.env produced a pin")
    except CannotRunError:
        pass
    return missed


def selftest() -> int:
    missed = controls_fired()
    if missed:
        print("%s✗%s detect-wasm selftest: controls did not behave:" % (RED, NC), file=sys.stderr)
        for m in missed:
            print("  %s" % m, file=sys.stderr)
        return 2
    print(
        "%s✓%s detect-wasm selftest: every plant fired and every negative control stayed silent"
        % (GREEN, NC)
    )
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--selftest", action="store_true", help="run the planted controls only")
    parser.add_argument(
        "--artifact-dir",
        default=None,
        help="compare this directory instead of the committed one (test copies only)",
    )
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    print("detect-wasm: controls first, then the verdict")
    if selftest():
        print(
            "✗ instrument control failed; every verdict below would be meaningless", file=sys.stderr
        )
        return 2
    root = str(paths.repo_root())
    # Relative when inside the tree, so findings read `private/account/...`; a test copy outside it keeps its absolute path, which names it as a copy.
    artifact = (
        os.path.abspath(args.artifact_dir)
        if args.artifact_dir
        else os.path.join(root, ARTIFACT_REL)
    )
    if artifact.startswith(root + os.sep):
        os.chdir(root)
        artifact = os.path.relpath(artifact, root)
    try:
        result = judge(root, artifact)
    except CannotRunError as exc:
        print("%sCANNOT RUN%s detect-wasm: %s" % (YELLOW, NC, exc), file=sys.stderr)
        return EXIT_CANNOT_RUN
    if result["findings"]:
        print(
            "%s✗%s detect-wasm: %s does not match the renet gitlink:" % (RED, NC, artifact),
            file=sys.stderr,
        )
        for f in result["findings"]:
            print("  %s" % f, file=sys.stderr)
        return 1
    print(
        "%s✓%s detect-wasm: %s rebuilt from renet %s%s (inputs %s) under %s; %s (%d bytes, sha256 %s), %s and %s identical"
        % (
            GREEN,
            NC,
            artifact,
            result["gitlink"][:12],
            " (working tree dirty, judged as it stands)" if result["dirty"] else "",
            result["inputs"][:16],
            result["go"],
            WASM,
            result["size"],
            result["sha256"][:16],
            EXEC,
            MANIFEST,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
