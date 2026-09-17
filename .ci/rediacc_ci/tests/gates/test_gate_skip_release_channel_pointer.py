"""Port of `.ci/scripts/test/gates/test-skip-release-channel-pointer.sh`.

Gate: on a `bump-none` merge the R2 uploaders must write NOTHING on a release channel, and must keep writing everything the moment the signal is absent.

WHAT IS DRIVEN. `.ci/scripts/deploy/upload-to-r2.sh` is driven where it lives, in the real tree, because it takes every path it needs as an argument. `.ci/scripts/deploy/upload-repos-to-r2.sh` derives its root from `common.sh`'s own `BASH_SOURCE` and then `cd`s to it, so it is driven from a BYTE-IDENTICAL copy inside a sandbox whose `.ci/scripts/lib`, `.ci/config` and
`.devcontainer` are SYMLINKS to the real ones. The copy is `cmp`-checked against the original on every run: the sandbox exists to relocate a repo root, not to re-implement a script.

THE MUTANTS ARE ASSEMBLED BY CONSTRUCTION, head-up-to-anchor plus a replacement block written literally in this file plus tail-after-anchor. No pattern substitution of any live source line, so a reworded guard cannot silently produce an identical "mutant". Three refusals guard the assembly and all three are the twin's: the anchors must be found, the anchor must be GONE from the
output, and the output must differ from its source.

THE LIVENESS PROBE IS THE PART WORTH READING. A mutant that dies during startup (a missing sandbox file, a bad splice) exits non-zero for a reason unrelated to its plant, and every control below would read that as "the defect was detected". The twin records that this actually happened once, when `.devcontainer` was not linked into the sandbox and `constants.sh` hard-failed. So each
mutant is proven to LOAD and reach a check that sits ABOVE the spliced region before anything it says is trusted.

WHERE THIS REIMPLEMENTS grep, wc AND cmp, AND WHY THE ANSWERS AGREE. The anchor line numbers come from `grep -n ... | head -1 | cut -d: -f1` in the twin and from enumerating lines here; both take the FIRST line carrying the anchor. `wc -l` on the recorder log counts newline-terminated lines and the fake writes exactly one `printf '%s\\n'` per call, so counting `splitlines()` is the
same number.
`cmp -s` is a byte comparison, which is what `read_bytes() ==` is.

THE TWIN IS FLAT (it declares no `test_*` functions), so `test_twin_parity.py` compares this module's control count against the twin's runtime `PASS:` count: six properties, six controls and one shape line, thirteen each side.

NO `xdist_group`. The sandbox is module-scoped and built under pytest's own `tmp_path_factory`, which is per-worker, so two workers get two sandboxes and two recorders; within a worker pytest never runs two tests at once, so the single recorder log is written and read serially. Nothing outside the sandbox is written: the real `upload-to-r2.sh` is EXECUTED but never modified, and
its mutants are assembled into the sandbox.
"""

import os
import pathlib

import pytest

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-skip-release-channel-pointer.sh"

REAL_UPLOAD = paths.from_root(".ci", "scripts", "deploy", "upload-to-r2.sh")
REAL_REPOS = paths.from_root(".ci", "scripts", "deploy", "upload-repos-to-r2.sh")
VERSION = "9.9.9"

FAKE_AWS = """#!/bin/bash
printf '%%s\\n' "$*" >>"%(awslog)s"
case "$1 $2" in
    "s3api head-object") exit 254 ;;  # no .released sentinel -> guard says PROCEED
    "s3api list-objects-v2") echo 0 ;;
    # A cp whose SOURCE is - is fed on stdin (r2_put); consume it. A cp whose
    # DESTINATION is - (r2_get) reads nothing, and consuming stdin there blocks
    # forever on an inherited terminal -- a hang, not a failure, and a hang in
    # CI reads as a timeout with no verdict.
    "s3 cp") [[ "$3" == "-" ]] && cat >/dev/null ;;
esac
exit 0
"""

FAKE_PURGE = """#!/bin/bash
cat >>"%(purgelog)s"
"""

MUT_UNCONDITIONAL = """skip_release_requested() { return 0; }
if skip_release_requested; then
    echo "MUTANT: guard is unconditional"
    exit 0
fi"""

MUT_CHANNEL_BLIND = """skip_release_requested() {
    case "${SKIP_RELEASE:-}" in
        true | 1 | yes | y | on) return 0 ;;
        *) return 1 ;;
    esac
}
if skip_release_requested; then
    echo "MUTANT: guard ignores CHANNEL"
    exit 0
fi"""

BEGIN_ANCHOR = "SKIP_RELEASE_GUARD_BEGIN"
END_ANCHOR = "SKIP_RELEASE_GUARD_END"


class Refusal(harness.GateAssertionError):
    """A fixture that could not be built. Loud, and never a skip."""


class Sandbox:
    """The fake repo root, the recorders, the six mutants and the two drivers."""

    def __init__(self, root: pathlib.Path) -> None:
        self.root = root / "root"
        self.bin = root / "bin"
        self.awslog = root / "aws.log"
        self.purgelog = root / "purge.log"
        self.env_binary = harness.require_tool("env", "install coreutils")

        for path in (REAL_UPLOAD, REAL_REPOS):
            if not path.is_file():
                raise Refusal("target not found: %s" % paths.relative_to_root(path))

        for relative in (
            ".ci/scripts/deploy",
            ".ci/scripts/lib",
            ".ci/config",
            "dist/cli",
            "dist/repos/apt/dists",
            "dist/pages",
        ):
            (self.root / relative).mkdir(parents=True, exist_ok=True)
        self.bin.mkdir(parents=True, exist_ok=True)

        for source_dir, target_dir in (
            (paths.from_root(".ci", "scripts", "lib"), self.root / ".ci" / "scripts" / "lib"),
            (paths.from_root(".ci", "config"), self.root / ".ci" / "config"),
        ):
            for entry in sorted(source_dir.iterdir()):
                (target_dir / entry.name).symlink_to(entry)
        # constants.sh resolves .devcontainer/toolchain.env RELATIVE TO THE ROOT it is sourced from and hard-fails without it. Omitting this link made every mutant die during startup, which the controls then read as "the planted defect was detected".
        (self.root / ".devcontainer").symlink_to(paths.from_root(".devcontainer"))

        # Fixture artifacts. Two binaries plus a manifest is the shape stage-artifacts hands the uploader.
        (self.root / "dist/cli/rdc-linux-x64").write_text("ELF-ish\n", encoding="utf-8")
        (self.root / "dist/cli/rdc-darwin-arm64").write_text("ELF-ish\n", encoding="utf-8")
        (self.root / "dist/cli/manifest.json").write_text(
            '{"version":"%s"}\n' % VERSION, encoding="utf-8"
        )
        (self.root / "dist/repos/apt/dists/Packages").write_text("Package: rdc\n", encoding="utf-8")
        (self.root / "dist/pages/install.sh").write_text(
            "REDIACC_CHANNEL:-stable\n", encoding="utf-8"
        )
        self.fixture_binaries = len(list((self.root / "dist" / "cli").glob("rdc-*")))
        if self.fixture_binaries == 0:
            raise Refusal(
                "ANTI-VACUITY: the fixture yielded zero rdc-* binaries; every upload "
                "assertion below would be trivially satisfiable"
            )

        self._write_exec(self.bin / "aws", FAKE_AWS % {"awslog": self.awslog})
        # upload-repos-to-r2.sh calls cf-purge-urls.sh by a repo-relative path after cd'ing to get_repo_root().
        self._write_exec(
            self.root / ".ci/scripts/deploy/cf-purge-urls.sh",
            FAKE_PURGE % {"purgelog": self.purgelog},
        )

        self.sandbox_repos = self.root / ".ci/scripts/deploy/upload-repos-to-r2.sh"
        self.sandbox_repos.write_bytes(REAL_REPOS.read_bytes())
        self.sandbox_repos.chmod(0o755)
        if self.sandbox_repos.read_bytes() != REAL_REPOS.read_bytes():
            raise Refusal(
                "sandbox copy of upload-repos-to-r2.sh is not byte-identical to the real script"
            )

        deploy = self.root / ".ci" / "scripts" / "deploy"
        self.mutants = {
            "a-noguard": self._assemble(REAL_UPLOAD, deploy / "mutant-a-noguard.sh", ""),
            "b-uncond": self._assemble(
                REAL_UPLOAD, deploy / "mutant-b-uncond.sh", MUT_UNCONDITIONAL
            ),
            "c-blind": self._assemble(REAL_UPLOAD, deploy / "mutant-c-blind.sh", MUT_CHANNEL_BLIND),
            "r-noguard": self._assemble(self.sandbox_repos, deploy / "mutant-r-noguard.sh", ""),
            "r-uncond": self._assemble(
                self.sandbox_repos, deploy / "mutant-r-uncond.sh", MUT_UNCONDITIONAL
            ),
            "r-blind": self._assemble(
                self.sandbox_repos, deploy / "mutant-r-blind.sh", MUT_CHANNEL_BLIND
            ),
        }

    # -- construction --------------------------------------------------------

    @staticmethod
    def _write_exec(path: pathlib.Path, body: str) -> None:
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)

    def _assemble(self, source: pathlib.Path, out: pathlib.Path, replacement: str) -> pathlib.Path:
        lines = source.read_text(encoding="utf-8").splitlines()
        begin = next((i for i, line in enumerate(lines) if BEGIN_ANCHOR in line), None)
        end = next((i for i, line in enumerate(lines) if END_ANCHOR in line), None)
        if begin is None or end is None or end <= begin:
            raise Refusal(
                "CONTROL COULD NOT PLANT: guard anchors not found in %s (begin=%s end=%s)"
                % (source, begin, end)
            )
        body = lines[:begin]
        if replacement:
            body.extend(replacement.splitlines())
        body.extend(lines[end + 1 :])
        out.write_text("\n".join(body) + "\n", encoding="utf-8")
        out.chmod(0o755)
        text = out.read_text(encoding="utf-8")
        if BEGIN_ANCHOR in text:
            raise Refusal("CONTROL COULD NOT PLANT: anchor survived in %s" % out)
        if out.read_bytes() == source.read_bytes():
            raise Refusal("CONTROL COULD NOT PLANT: %s is identical to %s" % (out, source))
        self._prove_live(out, text)
        return out

    def _prove_live(self, mutant: pathlib.Path, text: str) -> None:
        """The probe is chosen to be independent of the plant: it exercises argument handling, which sits ABOVE the spliced region in both scripts."""
        if "upload-repos-to-r2.sh: CHANNEL must be set" in text:
            probe = self._env_run(["bash", str(mutant)], {}, unset=("CHANNEL", "SKIP_RELEASE"))
            if "CHANNEL must be set" not in probe.combined:
                raise Refusal(
                    "MUTANT IS NOT LIVE: %s did not reach its CHANNEL check (exit %d): %s"
                    % (mutant, probe.rc, probe.combined.strip())
                )
            return
        probe = self._env_run(["bash", str(mutant), "--help"], {}, unset=("SKIP_RELEASE",))
        if probe.rc != 0 or "Usage:" not in probe.combined:
            raise Refusal(
                "MUTANT IS NOT LIVE: %s --help exited %d without a usage line: %s"
                % (mutant, probe.rc, probe.combined.strip())
            )

    # -- drivers -------------------------------------------------------------

    def _env_run(
        self, argv: list[str], assignments: dict, unset: tuple[str, ...] = ()
    ) -> harness.RunResult:
        """`env -u NAME ... KEY=VALUE ... <argv>`, with stdin closed.

        The `env` BINARY rather than `harness.run(env=...)`: the overlay can set
        a variable but cannot UNSET one, and an inherited `SKIP_RELEASE` would silence exactly the cases this file exists to see.
        """
        command = [self.env_binary]
        for name in unset:
            command += ["-u", name]
        command.append("PATH=%s:%s" % (self.bin, os.environ.get("PATH", "")))
        command += ["%s=%s" % (key, value) for key, value in sorted(assignments.items())]
        command += argv
        return harness.run(command, stdin="")

    def reset(self) -> None:
        self.awslog.write_text("", encoding="utf-8")
        self.purgelog.write_text("", encoding="utf-8")

    def calls(self) -> list[str]:
        if not self.awslog.is_file():
            return []
        return [line for line in self.awslog.read_text(encoding="utf-8").splitlines() if line]

    def purges(self) -> list[str]:
        if not self.purgelog.is_file():
            return []
        return [line for line in self.purgelog.read_text(encoding="utf-8").splitlines() if line]

    def run_upload(self, script: pathlib.Path, skip: str, channel: str) -> harness.RunResult:
        self.reset()
        assignments = {
            "CLOUDFLARE_R2_ACCESS_KEY_ID": "k",
            "CLOUDFLARE_R2_SECRET_ACCESS_KEY": "s",
            "CLOUDFLARE_R2_ENDPOINT": "https://example.invalid",
            "NPM_DIR": str(self.root / "dist" / "npm-absent"),
        }
        if skip:
            assignments["SKIP_RELEASE"] = skip
        return self._env_run(
            [
                "bash",
                str(script),
                "--version",
                VERSION,
                "--channel",
                channel,
                "--cli-dir",
                str(self.root / "dist" / "cli"),
            ],
            assignments,
            unset=("SKIP_RELEASE",),
        )

    def run_repos(self, script: pathlib.Path, skip: str, channel: str) -> harness.RunResult:
        self.reset()
        assignments = {
            "CHANNEL": channel,
            "CLOUDFLARE_R2_ACCESS_KEY_ID": "k",
            "CLOUDFLARE_R2_SECRET_ACCESS_KEY": "s",
            "CLOUDFLARE_R2_ENDPOINT": "https://example.invalid",
            "CLOUDFLARE_ZONE_ID": "zone",
            "CLOUDFLARE_API_TOKEN": "tok",
        }
        if skip:
            assignments["SKIP_RELEASE"] = skip
        return self._env_run(["bash", str(script)], assignments, unset=("SKIP_RELEASE",))


@pytest.fixture(scope="module")
def sandbox(tmp_path_factory):
    return Sandbox(tmp_path_factory.mktemp("skip-release"))


# --- the six properties. Each returns the problems it found, empty when the property HOLDS. They are called twice: once against the real script (must hold) and once against the mutant that breaks exactly that property (must be violated).


def case_skip_writes_nothing(box: Sandbox, script: pathlib.Path) -> list[str]:
    result = box.run_upload(script, "true", "edge")
    problems = []
    if result.rc != 0:
        problems.append("exit %d (expected 0)" % result.rc)
    if box.calls():
        problems.append(
            "%d aws call(s) were made on a skipped edge release: %s"
            % (len(box.calls()), "; ".join(box.calls()))
        )
    if "bump-none" not in result.combined:
        problems.append("output does not name bump-none")
    return problems


def case_clean_writes_pointer(box: Sandbox, script: pathlib.Path) -> list[str]:
    result = box.run_upload(script, "", "edge")
    problems = []
    if result.rc != 0:
        problems.append("exit %d (expected 0)" % result.rc)
    log = "\n".join(box.calls())
    if not log:
        problems.append("ANTI-VACUITY: a clean edge upload made ZERO aws calls")
        return problems
    problems.extend(
        "a clean edge upload never wrote %s" % want
        for want in ("cli/edge/manifest.json", "cli/edge/latest.json", "cli/v%s/" % VERSION)
        if want not in log
    )
    return problems


def case_pr_channel_unaffected(box: Sandbox, script: pathlib.Path) -> list[str]:
    result = box.run_upload(script, "true", "pr-7")
    problems = []
    if result.rc != 0:
        problems.append("exit %d (expected 0)" % result.rc)
    if "cli/pr-7/latest.json" not in "\n".join(box.calls()):
        problems.append("SKIP_RELEASE suppressed a pr-7 upload; the guard is not channel-scoped")
    return problems


def case_repos_skip_writes_nothing(box: Sandbox, script: pathlib.Path) -> list[str]:
    result = box.run_repos(script, "1", "edge")
    problems = []
    if result.rc != 0:
        problems.append("exit %d (expected 0)" % result.rc)
    if box.calls() or box.purges():
        problems.append(
            "%d aws call(s) / %d purge URL(s) on a skipped edge release"
            % (len(box.calls()), len(box.purges()))
        )
    if "bump-none" not in result.combined:
        problems.append("output does not name bump-none")
    return problems


def case_repos_clean_writes(box: Sandbox, script: pathlib.Path) -> list[str]:
    result = box.run_repos(script, "", "edge")
    problems = []
    if result.rc != 0:
        problems.append("exit %d (expected 0)" % result.rc)
    log = "\n".join(box.calls())
    if not log:
        problems.append("ANTI-VACUITY: a clean edge repo upload made ZERO aws calls")
        return problems
    problems.extend(
        "a clean edge repo upload never wrote %s" % want
        for want in ("apt/edge/", "cli/edge/install.sh")
        if want not in log
    )
    if not box.purges():
        problems.append("no Cloudflare purge was requested for a clean edge upload")
    return problems


def case_repos_pr_unaffected(box: Sandbox, script: pathlib.Path) -> list[str]:
    result = box.run_repos(script, "1", "pr-7")
    problems = []
    if result.rc != 0:
        problems.append("exit %d (expected 0)" % result.rc)
    if "apt/pr-7/" not in "\n".join(box.calls()):
        problems.append(
            "SKIP_RELEASE suppressed a pr-7 repo upload; the guard is not channel-scoped"
        )
    return problems


def must_hold(gate, box: Sandbox, case, script: pathlib.Path, label: str) -> None:
    problems = case(box, script)
    # The recorder count is read AFTER the case runs, never before: a count captured first reports the PREVIOUS case's log and would hide exactly the collapse anti-vacuity exists to expose.
    observed = len(box.calls())
    if problems:
        gate.log_fail("%s [%d aws call(s)]\n    %s" % (label, observed, "\n    ".join(problems)))
    gate.log_pass("%s [%d aws call(s)]" % (label, observed))


def control_must_fail(gate, box: Sandbox, case, script: pathlib.Path, label: str) -> None:
    if not case(box, script):
        gate.log_fail(
            "CONTROL DID NOT FIRE: %s -- the planted defect went undetected, so this "
            "assertion proves nothing" % label
        )
    gate.log_pass("control fires: %s" % label)


def test_1_skip_release_on_edge_writes_nothing(gate, sandbox):
    must_hold(
        gate,
        sandbox,
        case_skip_writes_nothing,
        REAL_UPLOAD,
        "1. --skip-release on edge writes NOTHING to R2",
    )


def test_2_clean_edge_still_writes_the_channel_pointer(gate, sandbox):
    must_hold(
        gate,
        sandbox,
        case_clean_writes_pointer,
        REAL_UPLOAD,
        "2. no flag on edge still writes the channel pointer + cli/v%s/" % VERSION,
    )


def test_3_skip_release_is_ignored_on_a_pr_channel(gate, sandbox):
    must_hold(
        gate,
        sandbox,
        case_pr_channel_unaffected,
        REAL_UPLOAD,
        "3. SKIP_RELEASE is ignored on pr-7",
    )


def test_4_repos_skip_release_writes_nothing(gate, sandbox):
    must_hold(
        gate,
        sandbox,
        case_repos_skip_writes_nothing,
        sandbox.sandbox_repos,
        "4. SKIP_RELEASE on edge writes NOTHING (no upload, no purge)",
    )


def test_5_repos_clean_edge_still_publishes(gate, sandbox):
    must_hold(
        gate,
        sandbox,
        case_repos_clean_writes,
        sandbox.sandbox_repos,
        "5. no signal on edge still publishes the repos + install scripts",
    )


def test_6_repos_skip_release_is_ignored_on_a_pr_channel(gate, sandbox):
    must_hold(
        gate,
        sandbox,
        case_repos_pr_unaffected,
        sandbox.sandbox_repos,
        "6. SKIP_RELEASE is ignored on pr-7",
    )


def test_control_a_guard_deleted(gate, sandbox):
    control_must_fail(
        gate,
        sandbox,
        case_skip_writes_nothing,
        sandbox.mutants["a-noguard"],
        "a. guard deleted -> edge pointer is written on a skipped release",
    )


def test_control_b_guard_unconditional(gate, sandbox):
    control_must_fail(
        gate,
        sandbox,
        case_clean_writes_pointer,
        sandbox.mutants["b-uncond"],
        "b. guard unconditional -> a CLEAN edge release is silently withheld",
    )


def test_control_c_guard_ignores_channel(gate, sandbox):
    control_must_fail(
        gate,
        sandbox,
        case_pr_channel_unaffected,
        sandbox.mutants["c-blind"],
        "c. guard ignores CHANNEL -> pr-7 stops uploading",
    )


def test_control_r_guard_deleted(gate, sandbox):
    control_must_fail(
        gate,
        sandbox,
        case_repos_skip_writes_nothing,
        sandbox.mutants["r-noguard"],
        "a'. repos guard deleted",
    )


def test_control_r_guard_unconditional(gate, sandbox):
    control_must_fail(
        gate,
        sandbox,
        case_repos_clean_writes,
        sandbox.mutants["r-uncond"],
        "b'. repos guard unconditional -> clean edge silently withheld",
    )


def test_control_r_guard_ignores_channel(gate, sandbox):
    control_must_fail(
        gate,
        sandbox,
        case_repos_pr_unaffected,
        sandbox.mutants["r-blind"],
        "c'. repos guard ignores CHANNEL",
    )


def test_the_fixture_shape_is_non_trivial(gate, sandbox):
    # The twin's closing line, which is a control and not a summary: it names the numbers a reader would notice collapsing.
    if sandbox.fixture_binaries == 0:
        gate.log_fail("the fixture yielded zero rdc-* binaries")
    if len(sandbox.mutants) != 6:
        gate.log_fail(
            "%d mutant(s) were assembled, not 6; a control that was never built cannot "
            "fire" % len(sandbox.mutants)
        )
    gate.log_pass(
        "6 properties + 6 controls; %d fixture binaries; %d mutants assembled by "
        "construction and proven live" % (sandbox.fixture_binaries, len(sandbox.mutants))
    )
    gate.log_info(
        "BLIND SPOT: this cannot see whether any workflow PASSES --skip-release/SKIP_RELEASE. "
        "A flag nobody passes would leave every case above green. That wiring is "
        "check-ci-workflow-invariants.sh's subject, not this file's."
    )
