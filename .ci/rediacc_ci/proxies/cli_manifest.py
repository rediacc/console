"""Port of `.ci/scripts/test/proxies/proxy-cli-manifest.sh`.

Local proxy for `.ci/scripts/build/generate-cli-manifest.sh`, one of the release-path CI scripts the bash wave found with no test of any kind. The manifest it writes is what `rdc update` fetches to decide which binary to download and what sha256 to verify it against, so this proxy runs the REAL generator against a synthetic dist directory (six fake binaries with six `.sha256`
sidecars, plus one deliberately malformed sidecar) in a throwaway tmpdir. Nothing is written inside the checkout. The subject itself stays bash and unported -- only the proxy that drives it is ported here.

BOTH DIRECTIONS, preserved from the twin: the five well-formed platform/arch keys must be produced with the right URL and hash, a missing `--version` and an unknown flag must both be refused, and the malformed sidecar's entry must be OMITTED rather than emitted with a bad hash.

THE ONE HAZARD IS PRINTED, NOT RULED ON, exactly as in the bash twin: an input directory with no `.sha256` files makes the subject exit 0 with an empty `binaries` manifest, and fixing that means editing the subject, which this file does not own.

K=5 LEDGER: `.ci/shadow/w7p6-proxy-cli-manifest.observations.jsonl`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

from rediacc_ci import paths
from rediacc_ci.core import proxyx

GOOD_KEYS = ["linux-x64", "linux-arm64", "mac-x64", "mac-arm64", "win-x64"]


def _sha256sum(path: str) -> str:
    proc = subprocess.run(["sha256sum", path], capture_output=True, text=True, check=True)
    return proc.stdout.split()[0]


# The subject, which is the PORT since W7P6 retired `.ci/scripts/build/generate-cli-manifest.sh`.
SUBJECT_REL = ".ci/rediacc_ci/build/generate_cli_manifest.py"


def run() -> int:
    root = paths.repo_root()
    subject_path = str(root / SUBJECT_REL)
    # The licensed command form from the subject's own ledger, `python3 <path>` with `PYTHONPATH=.ci`. The interpreter is spelled `python3` rather than `sys.executable` so that this proxy and its bash twin build the same argv.
    subject = ["python3", subject_path]
    # ABSOLUTE, and set for both proxies alike: the subject imports `rediacc_ci`, and a relative `.ci` would depend on the directory the proxy happened to be started from.
    os.environ["PYTHONPATH"] = str(root / ".ci")

    p = proxyx.Proxy("cli-manifest", SUBJECT_REL)
    p.need_exec(subject_path, "the subject script is missing from this checkout")
    p.need_cmd("jq", "sudo apt-get install -y jq")
    p.need_cmd("sha256sum", "sudo apt-get install -y coreutils")
    p.preflight()

    with tempfile.TemporaryDirectory() as work:
        indir = os.path.join(work, "dist")
        os.makedirs(indir, exist_ok=True)

        expected_sha: dict[str, str] = {}
        for key in GOOD_KEYS:
            name = f"rdc-{key}"
            if key.startswith("win-"):
                name += ".exe"
            binpath = os.path.join(indir, name)
            with open(binpath, "w") as f:
                f.write(f"fixture binary for {key}\n")
            sha = _sha256sum(binpath)
            with open(binpath + ".sha256", "w") as f:
                f.write(f"{sha}  {name}\n")
            expected_sha[key] = sha

        # win-arm64 gets a truncated hash: the subject must SKIP it.
        with open(os.path.join(indir, "rdc-win-arm64.exe"), "w") as f:
            f.write("fixture binary for win-arm64\n")
        with open(os.path.join(indir, "rdc-win-arm64.exe.sha256"), "w") as f:
            f.write("deadbeef  rdc-win-arm64.exe\n")

        out = os.path.join(work, "manifest.json")
        proc = subprocess.run(
            [
                *subject,
                "--version",
                "9.9.9",
                "--channel",
                "edge",
                "--input",
                indir,
                "--output",
                out,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            p.ok("generate_cli_manifest.py exited 0 over the fixture dist dir")
        else:
            p.bad(f"generate_cli_manifest.py exited {proc.returncode}")
            print("  --- stdout ---", file=sys.stderr)
            print(proc.stdout, file=sys.stderr, end="")
            print("  --- stderr ---", file=sys.stderr)
            print(proc.stderr, file=sys.stderr, end="")

        manifest = None
        if os.path.isfile(out):
            try:
                with open(out) as f:
                    manifest = json.load(f)
            except (json.JSONDecodeError, OSError):
                manifest = None

        if manifest is not None:
            p.ok("the manifest exists and parses as JSON")

            binaries = manifest.get("binaries", {}) or {}
            got_keys = " ".join(sorted(binaries.keys()))
            want_keys = " ".join(sorted(GOOD_KEYS))
            if got_keys == want_keys:
                p.ok(f"binaries has exactly the {len(GOOD_KEYS)} well-formed keys: {got_keys}")
            else:
                p.bad(f"binaries keys are [{got_keys}], expected [{want_keys}]")

            if "win-arm64" in binaries:
                p.bad(
                    "win-arm64 was emitted despite a malformed (8-character) sidecar "
                    "hash; a bad checksum would ship to every updater"
                )
            else:
                p.ok("the malformed sidecar was skipped, not emitted")

            hash_ok = True
            for key in GOOD_KEYS:
                got = (binaries.get(key) or {}).get("sha256", "")
                if got != expected_sha[key]:
                    hash_ok = False
                    print(
                        f"  sha256 mismatch for {key}: manifest={got} fixture={expected_sha[key]}",
                        file=sys.stderr,
                    )
            if hash_ok:
                p.ok("every emitted sha256 equals the fixture's own sha256sum output")
            else:
                p.bad("at least one sha256 in the manifest does not match the file it names")

            url = (binaries.get("linux-x64") or {}).get("url", "")
            p.expect_contains(
                url, "/cli/v9.9.9/", "a release channel (edge) bakes the immutable v-version path"
            )
            p.expect_contains(url, "rdc-linux-x64", "the URL names the binary it describes")

            pr_out = os.path.join(work, "pr.json")
            pr_proc = subprocess.run(
                [
                    *subject,
                    "--version",
                    "9.9.9",
                    "--channel",
                    "pr-420",
                    "--input",
                    indir,
                    "--output",
                    pr_out,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if pr_proc.returncode == 0:
                try:
                    with open(pr_out) as f:
                        pr_manifest = json.load(f)
                    pr_url = (pr_manifest.get("binaries", {}).get("linux-x64") or {}).get("url", "")
                except (json.JSONDecodeError, OSError):
                    pr_url = ""
                p.expect_contains(
                    pr_url,
                    "/cli/pr-420/",
                    "a non-release channel points at its own channel path instead",
                )
            else:
                p.bad("the subject failed outright on --channel pr-420")

            ver = manifest.get("version", "")
            if ver == "9.9.9":
                p.ok("version is carried through verbatim")
            else:
                p.bad(f"version is '{ver}', expected '9.9.9'")
        else:
            p.bad(f"no parseable manifest was written to {out}")

        # The two documented refusals.
        p.expect_exit(
            "1",
            "a missing --version is refused",
            [*subject, "--input", indir, "--output", os.path.join(work, "x.json")],
        )
        p.expect_exit(
            "1",
            "an unknown flag is refused",
            [
                *subject,
                "--version",
                "9.9.9",
                "--input",
                indir,
                "--output",
                os.path.join(work, "y.json"),
                "--bogus",
            ],
        )

        # THE HAZARD, PRINTED EVERY RUN, NOT RULED ON.
        empty = os.path.join(work, "empty")
        os.makedirs(empty, exist_ok=True)
        empty_out = os.path.join(work, "empty.json")
        hazard_proc = subprocess.run(
            [
                *subject,
                "--version",
                "9.9.9",
                "--channel",
                "edge",
                "--input",
                empty,
                "--output",
                empty_out,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        erc = hazard_proc.returncode
        try:
            with open(empty_out) as f:
                ecount = str(len((json.load(f)).get("binaries", {}) or {}))
        except (OSError, json.JSONDecodeError):
            ecount = "?"

        yel = p._c(proxyx.YEL)
        off = p._c(proxyx.OFF)
        print(f"{yel}proxy cli-manifest: KNOWN HAZARD in the subject, reported not enforced.{off}")
        print(
            f"{yel}  With an input dir holding no .sha256 files the subject exits {erc} and writes{off}"
        )
        print(
            f"{yel}  a manifest with {ecount} binaries. A release published from that manifest offers{off}"
        )
        print(
            f"{yel}  no downloads at all, and nothing on the release path notices. Reproduce with:{off}"
        )
        print(
            f"{yel}    python3 {SUBJECT_REL} --version 9.9.9 --input "
            f"$(mktemp -d) --output /tmp/m.json{off}"
        )

    return p.finish()


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--selftest":
        return proxyx.run_selftest()
    return run()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
