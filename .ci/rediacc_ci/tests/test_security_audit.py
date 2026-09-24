"""Behaviour suite for `rediacc_ci.security.audit`, the live gate `check:ci-security-audit`.

THIS WAS A DIFFERENTIAL AGAINST `.ci/scripts/security/audit.sh` UNTIL W7P5-b, and the twin it compared against is now deleted. The differential did its job: it licensed the deletion, alongside the K=5 ledger in `.ci/shadow/w7p6-audit.observations.jsonl`. What survives here is every expectation it established, restated as a LITERAL.

A CASE THAT COULD ONLY EVER SAY "the port matches the bash" says nothing once the bash is gone. The three cases that COMPUTED their expectation by running the twin were therefore rewritten rather than carried over: `describe_fix`'s seven answers and the three jq programs are now written out in full, captured from the twin at deletion time. The control was rewritten the same way,
and runs each plant against the unplanted gate.

NOTHING HERE RUNS THE GATE AGAINST THE REAL TREE. Every case is a scratch fixture holding the gate at its real relative path, with recording fakes for `npm`, `gh`, `node` and `sleep` on a scratch PATH. There is no read-only mode of this gate to borrow -- it shells out to the npm registry twice and to the GitHub Advisory Database once per advisory -- and a suite that made those
calls would be rate-limiting a shared account to prove a text transform.

WHY THE FIXTURE COPIES THE WHOLE PACKAGE. The gate resolves the repository root from its OWN location (`paths.repo_root()` walks up from `.ci/rediacc_ci/`) and imports four `rediacc_ci.core.*` modules under that root, so pointing it at a fixture means putting the package inside the fixture too.

FOUR CHANNELS ARE OBSERVED, NOT TWO:
  * exit code,
  * stdout and stderr, SEPARATELY (`differential.py` argues why at length; this
    gate splits one advisory across both streams, so merging them would hide a
    swap),
  * the CALL LOG: every fake appends its exact argv, so a change that produced
    identical bytes by asking different questions is still visible,
  * the ARTIFACTS: `audit-report.json` survives a run on purpose (CI uploads it)
    and `audit-prod.json` must not, so the leftovers are read back.

TWO NORMALISATIONS, both named:
  * the fixture root, which differs per test,
  * the SCRIPT PATH inside a `line N: npm: command not found`, spelled as
    `sys.argv[0]`. Nothing else about that line is normalised, including the
    line number, and those numbers are the DELETED twin's, carried into the port
    on purpose so the message stayed byte-identical.

ONE CHANNEL IS COMPARED AS A MULTISET, in the control, which is the only place two runs are set against each other: `gh api` runs under a thread pool, so the call log's order is a race. The log is compared as a sorted multiset, and the non-parallel subsequence is additionally compared IN ORDER, so serialisation is still pinned where it is deterministic.

WHAT THIS FILE PROVES ABOUT THE BASH THAT WAS, not just about the Python that is: six defects the port reproduces deliberately, each with a case named after it. DEFECT 6 is the one to read first -- `test_defect6_a_failed_gh_fetch_kills_the_gate_with_a_silent_exit_5`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.core import toolchain
from rediacc_ci.security import audit as port
from rediacc_ci.tests import differential

if typing.TYPE_CHECKING:  # pragma: no cover - annotations only
    import pathlib

ROOT = paths.repo_root()
PORT_REL = ".ci/rediacc_ci/security/audit.py"
PORT = ROOT / PORT_REL

# THE FAKES RECORD BEFORE THEY ANSWER, and they record TWICE: once into `$FAKE_LOG` (which the call-log channel compares) and once onto stderr with the same `call: ` prefix (which the shadow-gate ledger's `--finding-re` scopes to). The second copy is not decoration: `shadow-gate.ts` classifies `-> ` and `v ` lines as CHATTER before any message regex sees them, so a gate that
# reports mostly through log_info would record VACUOUS_BOTH_EMPTY rows forever.
FAKE_NPM = r"""#!/bin/bash
printf 'call: npm %s\n' "$*" >>"$FAKE_LOG"
printf 'call: npm %s\n' "$*" >&2
case "$*" in
    "--version") cat "$FAKE_DATA/npm.version" ;;
    "config get cache") cat "$FAKE_DATA/npm.cache" ;;
    "audit signatures")
        n=$(cat "$FAKE_DATA/npm.signatures.count" 2>/dev/null || echo 0)
        echo $((n + 1)) > "$FAKE_DATA/npm.signatures.count"
        [[ -f "$FAKE_DATA/npm.signatures.out" ]] && cat "$FAKE_DATA/npm.signatures.out"
        exit "$(cat "$FAKE_DATA/npm.signatures.exit")"
        ;;
    "install -g"*)
        [[ -f "$FAKE_DATA/npm.install.out" ]] && cat "$FAKE_DATA/npm.install.out"
        exit "$(cat "$FAKE_DATA/npm.install.exit" 2>/dev/null || echo 0)"
        ;;
    "audit --json --omit=dev")
        [[ -f "$FAKE_DATA/audit-prod" ]] && cat "$FAKE_DATA/audit-prod"
        exit "$(cat "$FAKE_DATA/audit-prod.exit" 2>/dev/null || echo 0)"
        ;;
    "audit --json")
        [[ -f "$FAKE_DATA/audit-all" ]] && cat "$FAKE_DATA/audit-all"
        exit "$(cat "$FAKE_DATA/audit-all.exit" 2>/dev/null || echo 0)"
        ;;
    "view "*" time --json")
        f="$FAKE_DATA/npmview.${2//\//_}"
        [[ -f "$f" ]] || exit 1
        cat "$f"
        ;;
    *) echo "fake npm: unexpected argv: $*" >&2; exit 2 ;;
esac
exit 0
"""

FAKE_GH = r"""#!/bin/bash
printf 'call: gh %s\n' "$*" >>"$FAKE_LOG"
printf 'call: gh %s\n' "$*" >&2
f="$FAKE_DATA/ghsa.${2##*/}.json"
[[ -f "$f" ]] || exit 1
cat "$f"
"""

# `node --experimental-strip-types <lib> --window-seconds|--eligible-epoch p w`. Only the LAST TWO argv words are logged, because the middle one is the absolute path of `scripts/lib/release-age.ts` under the fixture root and the log is compared verbatim.
FAKE_NODE = r"""#!/bin/bash
args=("$@")
n=${#args[@]}
printf 'call: node %s\n' "${args[$((n-1))]}" >>"$FAKE_LOG"
case "${args[$((n-1))]}" in
    --window-seconds) echo 86400; exit 0 ;;
esac
if [[ "${args[$((n-3))]}" == "--eligible-epoch" ]]; then
    printf 'call: node --eligible-epoch %s %s\n' "${args[$((n-2))]}" "${args[$((n-1))]}" \
        >>"$FAKE_LOG"
    echo $(( ( (${args[$((n-2))]} + ${args[$((n-1))]}) / 86400 + 1 ) * 86400 ))
    exit 0
fi
exit 1
"""

# `sleep` IS FAKED RATHER THAN WAITED OUT, and that is the reason the port spawns it instead of calling `time.sleep`: the retry ladder is then observable, and the two 10-second waits in the signature-failure case cost nothing.
FAKE_SLEEP = r"""#!/bin/bash
printf 'call: sleep %s\n' "$*" >>"$FAKE_LOG"
printf 'call: sleep %s\n' "$*" >&2
exit 0
"""

# A two-advisory production report: one package reached through a string `via`
# (which the `select(type == "object")` filter drops) and one with two object
# `via` entries sharing a package.
AUDIT_PROD = """{
  "auditReportVersion": 2,
  "vulnerabilities": {
    "@astrojs/mdx": {
      "name": "@astrojs/mdx",
      "severity": "low",
      "via": ["astro"],
      "range": "<=4.3.14",
      "fixAvailable": { "name": "@astrojs/mdx", "version": "8.0.1", "isSemVerMajor": true }
    },
    "astro": {
      "name": "astro",
      "severity": "high",
      "via": [
        {
          "source": 1117141,
          "name": "astro",
          "title": "Astro: XSS in define:vars via incomplete </script> tag sanitization",
          "url": "https://github.com/advisories/GHSA-j687-52p2-xcff",
          "severity": "moderate"
        },
        {
          "source": 1139377,
          "name": "astro",
          "title": "Astro: Host header SSRF in prerendered error page fetch",
          "url": "https://github.com/advisories/GHSA-2pvr-wf23-7pc7",
          "severity": "high"
        }
      ],
      "range": "<=7.0.1",
      "fixAvailable": { "name": "astro", "version": "7.0.2", "isSemVerMajor": true }
    }
  },
  "metadata": {
    "vulnerabilities": {"info": 0, "low": 1, "moderate": 0, "high": 1, "critical": 0, "total": 2}
  }
}
"""

# The same report plus one DEV-ONLY advisory whose `fixAvailable` is the boolean `true`, which is the arm that reaches `npm view <pkg> time --json`.
AUDIT_ALL = json.dumps(
    {
        **json.loads(AUDIT_PROD),
        "vulnerabilities": {
            **json.loads(AUDIT_PROD)["vulnerabilities"],
            "vitest": {
                "name": "vitest",
                "severity": "moderate",
                "via": [
                    {
                        "source": 1193684,
                        "name": "vitest",
                        "title": "Vitest: Path Traversal via @vitest/mocker Redirect Mock",
                        "url": "https://github.com/advisories/GHSA-82fw-gwwq-j7x9",
                        "severity": "moderate",
                    }
                ],
                "range": "2.1.0 - 4.1.10",
                "fixAvailable": True,
            },
        },
        "metadata": {
            "vulnerabilities": {
                "info": 0,
                "low": 1,
                "moderate": 1,
                "high": 1,
                "critical": 0,
                "total": 3,
            }
        },
    },
    indent=2,
)

# The same production report with every fix removed, so the stale sweep emits NOTHING for an allowlisted entry and its output stops depending on iteration order. Used by the DEFECT 2 case, which needs a deterministic prefix.
AUDIT_PROD_NO_FIX = AUDIT_PROD.replace(
    '"fixAvailable": { "name": "astro", "version": "7.0.2", "isSemVerMajor": true }',
    '"fixAvailable": false',
).replace(
    '"fixAvailable": { "name": "@astrojs/mdx", "version": "8.0.1", "isSemVerMajor": true }',
    '"fixAvailable": false',
)

# ONE advisory reached through TWO packages, which is what `unique` and `unique_by(.source)` exist for: npm emits the same `source` under every package the vulnerability propagates to. The two `via` objects deliberately DIFFER in title and url, because `unique_by` keeps the FIRST in input order and a port that kept the last would print the other one.
AUDIT_DUPE = """{
  "auditReportVersion": 2,
  "vulnerabilities": {
    "astro": {
      "name": "astro",
      "severity": "high",
      "via": [
        {
          "source": 1117141,
          "name": "astro",
          "title": "Astro: XSS in define:vars (first occurrence)",
          "url": "https://github.com/advisories/GHSA-j687-52p2-xcff",
          "severity": "moderate"
        }
      ],
      "range": "<=7.0.1",
      "fixAvailable": false
    },
    "vite": {
      "name": "vite",
      "severity": "high",
      "via": [
        {
          "source": 1117141,
          "name": "astro",
          "title": "Astro: XSS in define:vars (second occurrence, different text)",
          "url": "https://github.com/advisories/GHSA-zzzz-zzzz-zzzz",
          "severity": "low"
        }
      ],
      "range": "*",
      "fixAvailable": false
    }
  },
  "metadata": {
    "vulnerabilities": {"info": 0, "low": 0, "moderate": 0, "high": 2, "critical": 0, "total": 2}
  }
}
"""

CLEAN_REPORT = """{
  "auditReportVersion": 2,
  "vulnerabilities": {},
  "metadata": {
    "vulnerabilities": {"info": 0, "low": 0, "moderate": 0, "high": 0, "critical": 0, "total": 0}
  }
}
"""

GHSA_ASTRO_XSS = """{
  "ghsa_id": "GHSA-j687-52p2-xcff",
  "description": "Astro **fails** to sanitize `</script>`.\\n\\n## Impact\\nXSS.",
  "vulnerabilities": [{"vulnerable_version_range": "< 6.1.6", "first_patched_version": "6.1.6"}]
}
"""

# THE EMPTY RANGE IS THE POINT OF THIS FIXTURE, not an oversight: it is DEFECT 3, where the collapsing `read` shifts `first_patched_version` into the range slot.
GHSA_ASTRO_SSRF = """{
  "ghsa_id": "GHSA-2pvr-wf23-7pc7",
  "description": "Host header SSRF.",
  "vulnerabilities": [{"vulnerable_version_range": "", "first_patched_version": "7.0.2"}]
}
"""

GHSA_VITEST = """{
  "ghsa_id": "GHSA-82fw-gwwq-j7x9",
  "description": "Vitest mocker redirects.",
  "vulnerabilities": [
    {"vulnerable_version_range": ">= 2.1.0, < 4.1.11", "first_patched_version": "4.1.11"}
  ]
}
"""

PROD_ALLOWLIST_BOTH = """# astro XSS + SSRF, both fixed only by the astro 7 major migration
# BLOCKER: astro 7 is a major migration tracked separately; the site is statically
# pre-rendered so neither advisory is reachable at request time
1117141
1139377
"""

DEV_ALLOWLIST_VITEST = """# vitest path traversal in the mocker, dev-only
# BLOCKER: the mocker runs only under the test runner over our own fixtures, so no
# attacker-supplied redirect path reaches it
1193684
"""

EMPTY_PROD_ALLOWLIST = "# no production suppressions\n"
EMPTY_DEV_ALLOWLIST = "# no dev suppressions\n"
EMPTY_BLOCKLIST = "# no packages held back\n"

# Everything the gate and this file's oracles shell out to, minus the four that are faked. `sleep` is deliberately ABSENT: the fake must be the only `sleep` on the PATH, or a case that removes it would wait for real seconds. `xargs` left with the twin, whose `xargs -P 8` the port replaced with a thread pool.
SYS_TOOLS = (
    "bash",
    "sh",
    "env",
    "cat",
    "cp",
    "cut",
    "date",
    "dirname",
    "basename",
    "git",
    "grep",
    "head",
    "jq",
    "ls",
    "mkdir",
    "mktemp",
    "python3",
    "rm",
    "sed",
    "sort",
    "tail",
    "tr",
    "uname",
    "wc",
)


class Fixture:
    """A scratch repository with the gate, the fakes, and the policy."""

    def __init__(self, root: pathlib.Path) -> None:
        self.root = root

    # -- authoring ---------------------------------------------------------

    def data(self, name: str, text: str) -> None:
        (self.root / "fake" / "data" / name).write_text(text, encoding="utf-8")

    def policy(self, name: str, text: str) -> None:
        (self.root / ".ci" / "policy" / name).write_text(text, encoding="utf-8")

    def reports(self, prod: str, everything: str | None = None) -> None:
        self.data("audit-prod", prod)
        self.data("audit-all", prod if everything is None else everything)

    def advisories(self, *bodies: tuple[str, str]) -> None:
        for slug, body in bodies:
            self.data("ghsa.%s.json" % slug, body)

    def unfake(self, name: str) -> None:
        """Remove a fake binary, so the call finds NOTHING on PATH."""
        (self.root / "fake" / "bin" / name).unlink()

    # -- running -----------------------------------------------------------

    def env(self, log: pathlib.Path, **extra: str) -> dict[str, str]:
        """REPLACES the caller's environment; see `differential.BASE_ENV`.

        THE PATH IS TWO CURATED DIRECTORIES AND NOTHING ELSE, which is a safety control before it is a determinism one. Appending the caller's PATH after the fakes leaves the REAL `npm`, `node` and `gh` reachable, and the first version of this file proved it: removing the `npm` fake to test the missing-binary path found `~/.local/bin/npm` instead and ran a real `npm audit
        signatures` against a scratch directory. A test suite that can reach the npm registry by deleting one file is a test suite that will.
        """
        env = differential.env_for(PYTHONDONTWRITEBYTECODE="1")
        env["PATH"] = "%s%s%s" % (
            self.root / "fake" / "bin",
            os.pathsep,
            self.root / "fake" / "sysbin",
        )
        env["HOME"] = str(self.root / "fake" / "home")
        env["TZ"] = "UTC"
        env["FAKE_DATA"] = str(self.root / "fake" / "data")
        env["FAKE_LOG"] = str(log)
        env["PYTHONPATH"] = str(self.root / ".ci")
        env.update(extra)
        return env

    def _reset(self) -> None:
        for rel in (".audit-advisory-cache", "audit-prod.json", "audit-report.json"):
            target = self.root / rel
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()
        count = self.root / "fake" / "data" / "npm.signatures.count"
        if count.exists():
            count.unlink()

    def run(self, **extra: str) -> Run:
        self._reset()
        log = self.root / "calls"
        log.write_text("", encoding="utf-8")
        proc = subprocess.run(
            ["python3", str(self.root / PORT_REL)],
            env=self.env(log, **extra),
            cwd=str(self.root),
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
        return Run(
            exit=proc.returncode,
            stdout=self._normalise(proc.stdout),
            stderr=self._normalise(proc.stderr),
            calls=log.read_text(encoding="utf-8").splitlines(),
            artifacts=self._artifacts(),
        )

    def _normalise(self, text: str) -> str:
        text = text.replace(str(self.root), "<fx>")
        return text.replace(PORT_REL, "<script>")

    def _artifacts(self) -> dict[str, str]:
        """Everything the run left behind, so a port that forgot the cleanup fails."""
        out: dict[str, str] = {}
        for rel in ("audit-prod.json", "audit-report.json"):
            path = self.root / rel
            if path.is_file():
                out[rel] = path.read_text(encoding="utf-8")
        cache = self.root / ".audit-advisory-cache"
        if cache.is_dir():
            for entry in sorted(cache.iterdir()):
                out[".audit-advisory-cache/%s" % entry.name] = entry.read_text(encoding="utf-8")
        return out


class Run:
    """One run's four channels."""

    __slots__ = ("artifacts", "calls", "exit", "stderr", "stdout")

    def __init__(
        self,
        exit: int,  # noqa: A002 -- the channel is called `exit`, like the deleted twin's
        stdout: str,
        stderr: str,
        calls: list[str],
        artifacts: dict[str, str],
    ) -> None:
        self.exit = exit
        self.stdout = stdout
        self.stderr = stderr
        self.calls = calls
        self.artifacts = artifacts


@pytest.fixture
def fx(tmp_path: pathlib.Path) -> Fixture:
    """A scratch repository holding the gate and the four fakes."""
    root = tmp_path / "fx"
    (root / ".ci" / "policy").mkdir(parents=True)
    (root / "fake" / "bin").mkdir(parents=True)
    (root / "fake" / "data").mkdir(parents=True)
    (root / "fake" / "home").mkdir(parents=True)

    # The WHOLE package: the gate imports four `rediacc_ci.core.*` modules, all resolved from the fixture root.
    shutil.copytree(
        ROOT / ".ci" / "rediacc_ci",
        root / ".ci" / "rediacc_ci",
        ignore=shutil.ignore_patterns("__pycache__", "tests"),
    )
    # The pins file, because the npm the gate upgrades to is read from it rather than written into the gate.
    (root / ".devcontainer").mkdir()
    shutil.copy2(ROOT / ".devcontainer" / "toolchain.env", root / ".devcontainer" / "toolchain.env")

    # The ONLY system tools the two implementations may reach. Resolved here and symlinked, so the PATH the gate runs under contains no third directory: see `Fixture.env`. A tool missing from this list fails loudly at fixture build time rather than as a mystery inside a case.
    sysbin = root / "fake" / "sysbin"
    sysbin.mkdir(parents=True)
    for tool in SYS_TOOLS:
        found = shutil.which(tool)
        assert found, (
            "%s is not on PATH, so the fixture cannot build a hermetic one. Install it "
            "or drop it from SYS_TOOLS." % tool
        )
        (sysbin / tool).symlink_to(found)
    for name in ("npm", "node", "gh"):
        assert shutil.which(name, path=str(sysbin)) is None, (
            "%s resolves inside the curated sysbin, so the fakes are not the only way to "
            "reach it and a case could hit the real tool." % name
        )

    fixture = Fixture(root)
    for name, body in (
        ("npm", FAKE_NPM),
        ("gh", FAKE_GH),
        ("node", FAKE_NODE),
        ("sleep", FAKE_SLEEP),
    ):
        path = root / "fake" / "bin" / name
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)

    fixture.data("npm.version", "11.17.0\n")
    fixture.data("npm.cache", "%s/fake/npmcache\n" % root)
    fixture.data("npm.signatures.exit", "0\n")
    fixture.data("npm.signatures.out", "audited 1200 packages\n")
    fixture.reports(CLEAN_REPORT)
    fixture.policy(".audit-prod-allowlist", EMPTY_PROD_ALLOWLIST)
    fixture.policy(".audit-allowlist", EMPTY_DEV_ALLOWLIST)
    fixture.policy(".deps-upgrade-blocklist", EMPTY_BLOCKLIST)
    return fixture


# --------------------------------------------------------------------------- running, and comparing two runs ---------------------------------------------------------------------------


def run_gate(fx: Fixture, **extra: str) -> Run:
    """One run of the gate over one fixture, returned on all four channels.

    THIS ASSERTS NOTHING, and the absence is the point. While the bash twin existed the helper here ruled on agreement and handed the case the twin's run; every caller then went on to assert what it had actually seen, because two identically broken sides would otherwise have scored as agreement. Those literal assertions are now the whole test. A helper that quietly re-added an
    expectation of its own would put the only real claim back out of sight of the case that makes it.
    """
    return fx.run(**extra)


def assert_same(left: Run, right: Run) -> None:
    """All four channels of two runs, for the control at the bottom of this file.

    THE CALL LOG IS A MULTISET PLUS AN ORDERED SUBSEQUENCE. `gh api` runs under a thread pool, so the order of those lines is a race and comparing them verbatim would flake; everything else runs in a fixed order and is compared as it stands, so serialisation is still pinned where it is deterministic.
    """
    assert left.exit == right.exit, "exit: %s then %s\nstderr:\n%s\n%s" % (
        left.exit,
        right.exit,
        left.stderr,
        right.stderr,
    )
    assert left.stdout == right.stdout, "stdout:\n--- left\n%s--- right\n%s" % (
        left.stdout,
        right.stdout,
    )
    assert left.stderr == right.stderr, "stderr:\n--- left\n%s--- right\n%s" % (
        left.stderr,
        right.stderr,
    )
    assert left.artifacts == right.artifacts, "artifacts: %s then %s" % (
        sorted(left.artifacts),
        sorted(right.artifacts),
    )
    assert sorted(left.calls) == sorted(right.calls), "call log:\n--- left\n%s\n--- right\n%s" % (
        "\n".join(left.calls),
        "\n".join(right.calls),
    )
    left_serial = [line for line in left.calls if not line.startswith("call: gh ")]
    right_serial = [line for line in right.calls if not line.startswith("call: gh ")]
    assert left_serial == right_serial, "serial call order:\n--- left\n%s\n--- right\n%s" % (
        "\n".join(left_serial),
        "\n".join(right_serial),
    )


# --------------------------------------------------------------------------- the happy paths ---------------------------------------------------------------------------


def test_a_clean_tree_passes(fx: Fixture) -> None:
    run = run_gate(fx)
    assert run.exit == 0
    assert "✓ Security audit passed" in run.stdout
    # SEEN, not inferred: the gate really did run both audits.
    assert run.calls.count("call: npm audit --json --omit=dev") == 1
    assert run.calls.count("call: npm audit --json") == 1
    assert "audit-report.json" in run.artifacts, "pass 2's report must survive for the CI artifact"
    assert "audit-prod.json" not in run.artifacts, "the prod sidecar must be cleaned up"


def test_every_advisory_allowlisted_with_a_blocker(fx: Fixture) -> None:
    """The full three-pass run: warnings, GHSA enrichment, and the stale sweep."""
    fx.reports(AUDIT_PROD, AUDIT_ALL)
    fx.advisories(
        ("GHSA-j687-52p2-xcff", GHSA_ASTRO_XSS),
        ("GHSA-2pvr-wf23-7pc7", GHSA_ASTRO_SSRF),
        ("GHSA-82fw-gwwq-j7x9", GHSA_VITEST),
    )
    fx.policy(".audit-prod-allowlist", PROD_ALLOWLIST_BOTH)
    fx.policy(".audit-allowlist", DEV_ALLOWLIST_VITEST)
    run = run_gate(fx)
    assert run.exit == 0
    assert "⚠ Allowed production vulnerabilities: 2" in run.stdout
    assert "⚠ Allowed dev vulnerabilities: 1" in run.stdout
    # Pass 3 warns on every entry that HAS a fix but carries a BLOCKER.
    assert "major upgrade required (to 7.0.2) %s BLOCKED:" % port.EM in run.stdout
    assert "✓ Security audit passed" in run.stdout


def test_defect3_an_empty_vulnerable_range_shifts_the_two_fields(fx: Fixture) -> None:
    """`Affected: 7.0.2 -> Patched in: Host header SSRF.`, and that is not a typo.

    GHSA-2pvr's `vulnerable_version_range` is the empty string, so the TAB run in the `@tsv` row collapses, `first_patched_version` lands in the range slot and the DESCRIPTION lands in the patched slot. This is the case that would make a naive `line.split("\\t")` port disagree, and it disagrees in a direction that looks like the port being correct.
    """
    fx.reports(AUDIT_PROD, AUDIT_ALL)
    fx.advisories(
        ("GHSA-j687-52p2-xcff", GHSA_ASTRO_XSS),
        ("GHSA-2pvr-wf23-7pc7", GHSA_ASTRO_SSRF),
        ("GHSA-82fw-gwwq-j7x9", GHSA_VITEST),
    )
    fx.policy(".audit-prod-allowlist", PROD_ALLOWLIST_BOTH)
    fx.policy(".audit-allowlist", DEV_ALLOWLIST_VITEST)
    run = run_gate(fx)
    assert "  Affected: 7.0.2  →  Patched in: Host header SSRF." in run.stdout, (
        "the field shift is gone; DEFECT 3 needs re-measuring against the twin in git history"
    )
    # The advisory that HAS a range renders correctly, so the shift is the empty field's doing and not a broken renderer.
    assert "  Affected: < 6.1.6  →  Patched in: 6.1.6" in run.stdout


def test_the_github_annotation_form_under_ci(fx: Fixture) -> None:
    """`CI=true` moves the warn header onto stdout as `::warning::` and drops colour."""
    fx.reports(AUDIT_PROD, AUDIT_ALL)
    fx.advisories(
        ("GHSA-j687-52p2-xcff", GHSA_ASTRO_XSS),
        ("GHSA-2pvr-wf23-7pc7", GHSA_ASTRO_SSRF),
        ("GHSA-82fw-gwwq-j7x9", GHSA_VITEST),
    )
    fx.policy(".audit-prod-allowlist", PROD_ALLOWLIST_BOTH)
    fx.policy(".audit-allowlist", DEV_ALLOWLIST_VITEST)
    run = run_gate(fx, CI="true")
    assert "::warning::Allowed production vulnerabilities: 2" in run.stdout
    assert "\033[" not in run.stdout, "colour must be off under CI"


# --------------------------------------------------------------------------- the failing paths ---------------------------------------------------------------------------


def test_an_unallowed_production_advisory_fails(fx: Fixture) -> None:
    fx.reports(AUDIT_PROD, AUDIT_ALL)
    fx.advisories(
        ("GHSA-j687-52p2-xcff", GHSA_ASTRO_XSS),
        ("GHSA-2pvr-wf23-7pc7", GHSA_ASTRO_SSRF),
    )
    run = run_gate(fx)
    assert run.exit == 1
    assert "✗ Production vulnerabilities: 0 critical, 1 high, 2 total" in run.stderr
    assert "major upgrade required (to 7.0.2)" in run.stdout
    assert "call: npm audit --json" not in run.calls, "pass 2 must not be reached"


def test_an_unallowed_dev_advisory_fails_in_pass_two(fx: Fixture) -> None:
    fx.reports(AUDIT_PROD, AUDIT_ALL)
    fx.advisories(
        ("GHSA-j687-52p2-xcff", GHSA_ASTRO_XSS),
        ("GHSA-2pvr-wf23-7pc7", GHSA_ASTRO_SSRF),
        ("GHSA-82fw-gwwq-j7x9", GHSA_VITEST),
    )
    fx.policy(".audit-prod-allowlist", PROD_ALLOWLIST_BOTH)
    fx.data("npmview.vitest", '{"modified":"2020-01-02T03:04:05.000Z"}\n')
    run = run_gate(fx)
    assert run.exit == 1
    assert "✗ New dev vulnerabilities: 0 critical, 1 high" in run.stderr
    assert "transitive fix path exists" in run.stdout
    # The freshness delegate WAS consulted, and said the 2020 publish is eligible.
    assert "call: npm view vitest time --json" in run.calls
    assert any(line.startswith("call: node --eligible-epoch") for line in run.calls)


def test_one_advisory_reached_through_two_packages_is_reported_once(fx: Fixture) -> None:
    """`unique` and `unique_by(.source)`, and the FIRST occurrence wins.

    Both are dedup steps a port can drop without any fixture noticing, because every other report here mentions each source once. This is the case that notices: without `unique` the advisory is emitted twice, and with the wrong end of `unique_by` it is emitted with the second package's title and url.
    """
    fx.reports(AUDIT_DUPE)
    fx.advisories(("GHSA-j687-52p2-xcff", GHSA_ASTRO_XSS))
    run = run_gate(fx)
    assert run.exit == 1
    assert run.stderr.count("1117141 (astro") == 1, "the advisory was emitted twice"
    assert "(first occurrence)" in run.stderr, "unique_by kept the wrong end"
    assert "(second occurrence" not in run.stderr
    # ONE fetch, not two: the second `via` object never reaches the GHSA table.
    assert run.calls.count("call: gh api /advisories/GHSA-j687-52p2-xcff") == 1
    assert not [line for line in run.calls if "GHSA-zzzz" in line]


def test_a_stale_allowlist_entry_is_named_and_fails(fx: Fixture) -> None:
    """An id that no longer appears, with other vulnerabilities still in the report."""
    fx.reports(AUDIT_PROD, AUDIT_ALL)
    fx.advisories(
        ("GHSA-j687-52p2-xcff", GHSA_ASTRO_XSS),
        ("GHSA-2pvr-wf23-7pc7", GHSA_ASTRO_SSRF),
        ("GHSA-82fw-gwwq-j7x9", GHSA_VITEST),
    )
    fx.policy(
        ".audit-prod-allowlist",
        PROD_ALLOWLIST_BOTH
        + "\n# an advisory that stopped firing when the chain that pulled it left\n"
        "# BLOCKER: kept deliberately so this case has something to condemn; the "
        "electron chain that pulled it is gone\n1124334\n",
    )
    fx.policy(".audit-allowlist", DEV_ALLOWLIST_VITEST)
    run = run_gate(fx)
    assert run.exit == 1
    assert "✗ Stale allowlist entry: 1124334 does not appear in audit-prod.json" in run.stderr
    assert "%s Allowlist problems found %s" % ("\u2717", port.EM) in run.stderr


def test_an_allowlist_entry_with_no_blocker_is_refused(fx: Fixture) -> None:
    fx.policy(".audit-prod-allowlist", "# no reason at all\n1117141\n")
    run = run_gate(fx)
    assert run.exit == 1
    assert "strict gate enforced" in run.stderr
    assert "call: npm --version" not in run.calls, "the run must stop before touching npm"


def test_a_low_effort_blocker_is_refused(fx: Fixture) -> None:
    fx.policy(".audit-prod-allowlist", "# BLOCKER: no fix\n1117141\n")
    run = run_gate(fx)
    assert run.exit == 1
    assert "strict gate enforced" in run.stderr


# --------------------------------------------------------------------------- the six defects ---------------------------------------------------------------------------


def test_defect1_an_empty_audit_report_is_a_green_run(fx: Fixture) -> None:
    """A ZERO-BYTE `npm audit --json` passes `jq empty` and the gate reports clean.

    This is the vacuity case: the gate audits nothing and says so in green. It is pinned as the behaviour the bash had and the port kept, not fixed here.
    """
    fx.reports("", "")
    run = run_gate(fx)
    assert run.exit == 0
    assert "✓ No production vulnerabilities" in run.stdout
    assert "✓ Security audit passed" in run.stdout
    assert run.artifacts["audit-report.json"] == "", "the empty report really is empty"


def test_defect2_a_non_numeric_allowlist_entry_kills_the_gate_with_exit_5(fx: Fixture) -> None:
    """`tonumber` on a GHSA-shaped id is jq exit 5, and `set -e` takes it silently."""
    fx.reports(AUDIT_PROD_NO_FIX)
    fx.advisories(
        ("GHSA-j687-52p2-xcff", GHSA_ASTRO_XSS),
        ("GHSA-2pvr-wf23-7pc7", GHSA_ASTRO_SSRF),
    )
    # NO-FIX REPORT ON PURPOSE. Both numeric entries then take the
    # `fixAvailable == false` early continue and emit nothing, so how much output
    # precedes the death does not depend on which order the sweep walks the allowlist in -- which is the one thing bash's hash order and a Python dict genuinely disagree about (see the port's divergence list).
    fx.policy(
        ".audit-prod-allowlist",
        PROD_ALLOWLIST_BOTH + "\n# an entry keyed by GHSA id instead of by npm advisory source id\n"
        "# BLOCKER: the same astro 7 major migration; written the way the advisory "
        "database spells it\nGHSA-j687-52p2-xcff\n",
    )
    run = run_gate(fx)
    assert run.exit == 5, "the silent jq death is the behaviour under test"
    assert "Stale allowlist entry" not in run.stderr
    # The run got all the way to pass 3 before dying, so both audits already ran.
    assert "→ Checking allowlist entries against available fixes" in run.stdout


def test_defect6_a_failed_gh_fetch_kills_the_gate_with_a_silent_exit_5(fx: Fixture) -> None:
    """The worst of the six: no advisory JSON for a slug, and the gate exits 5 mute.

    `xargs -I {}` rewrites the `{}` inside the worker script, so the fallback
    writes the SLUG into the cache file; the next `jq` cannot parse it and the
    unguarded `details=$(jq ...)` takes the whole gate down under `set -e`. Every
    `gh api` failure -- 404, offline, or the anonymous rate limit the gate header's BLOCKER is about -- lands here.
    """
    fx.reports(AUDIT_PROD, AUDIT_ALL)
    # Only ONE of the three advisories has a cached body; the other two fail.
    fx.advisories(("GHSA-j687-52p2-xcff", GHSA_ASTRO_XSS))
    fx.policy(".audit-prod-allowlist", PROD_ALLOWLIST_BOTH)
    fx.policy(".audit-allowlist", DEV_ALLOWLIST_VITEST)
    run = run_gate(fx)
    assert run.exit == 5
    # The fetch was ATTEMPTED: `gh`'s own stderr goes to /dev/null in the worker, so the call log is the only place this is visible.
    assert "call: gh api /advisories/GHSA-2pvr-wf23-7pc7" in run.calls
    assert "✗" not in run.stderr, "the death says nothing at all, which is the finding"
    assert "✗" not in run.stdout
    cached = run.artifacts[".audit-advisory-cache/GHSA-2pvr-wf23-7pc7.json"]
    assert cached == "GHSA-2pvr-wf23-7pc7\n", (
        "the slug fallback is gone; DEFECT 6 needs re-measuring against the twin in "
        "git history (expected the slug, got %r)" % cached
    )


def test_defect5_a_wrong_shaped_report_passes_with_a_jq_error(fx: Fixture) -> None:
    """Valid JSON, no `.vulnerabilities`: jq complains on stderr and the gate is green."""
    fx.reports('{"hello": 1}\n')
    run = run_gate(fx)
    assert run.exit == 0
    assert "jq: error (at audit-prod.json:1): null (null) has no keys" in run.stderr
    assert "✓ Security audit passed" in run.stdout


def test_a_multiline_wrong_shaped_report_names_the_closing_line(fx: Fixture) -> None:
    """jq's `(at <file>:<line>)` is where the DOCUMENT ENDS, not where the fault is."""
    fx.reports('{\n  "hello": 1,\n  "x": [1,\n2]\n}\n')
    run = run_gate(fx)
    assert "jq: error (at audit-prod.json:5): null (null) has no keys" in run.stderr


def test_invalid_json_is_refused_with_the_registry_advice(fx: Fixture) -> None:
    fx.reports("not json at all\n")
    run = run_gate(fx)
    assert run.exit == 1
    assert "✗ npm audit failed to produce valid JSON (exit code: 0)" in run.stderr
    assert "✗ This may indicate a network error or npm registry issue" in run.stderr


def test_a_killed_npm_audit_blames_the_signal_and_not_the_registry(fx: Fixture) -> None:
    """Exit 137 with truncated JSON is a local OOM, and the message says so."""
    fx.reports('{"vulnerabilities": {"astro": {"via": [\n')
    fx.data("audit-prod.exit", "137\n")
    run = run_gate(fx)
    assert run.exit == 1
    assert "✗ npm audit was KILLED by signal 9 (raw 137) before it finished writing JSON" in (
        run.stderr
    )
    assert "NOT a registry or network fault" in run.stderr


# --------------------------------------------------------------------------- signatures, npm version, missing binaries ---------------------------------------------------------------------------


def test_a_signature_failure_retries_three_times_and_refuses(fx: Fixture) -> None:
    fx.data("npm.signatures.exit", "1\n")
    fx.data("npm.signatures.out", "EMISSINGSIGNATUREKEY\n")
    run = run_gate(fx)
    assert run.exit == 1
    assert run.calls.count("call: npm audit signatures") == 3
    assert run.calls.count("call: sleep 10") == 2, "one sleep between each pair of attempts"
    assert "npm audit signatures failed %s at least one installed package" % port.EM in (run.stderr)
    assert "do NOT allowlist" in run.stderr
    # The TUF cache is cleared before the first attempt and before each retry.
    assert run.calls.count("call: npm config get cache") == 3


def test_a_signature_failure_that_clears_on_the_second_attempt(fx: Fixture) -> None:
    """The fake fails once, then succeeds, so the ladder must stop at two."""
    fx.data("npm.signatures.exit", "0\n")
    (fx.root / "fake" / "bin" / "npm").write_text(
        FAKE_NPM.replace(
            'exit "$(cat "$FAKE_DATA/npm.signatures.exit")"',
            "[[ $n -eq 0 ]] && exit 1\n        exit 0",
        ),
        encoding="utf-8",
    )
    (fx.root / "fake" / "bin" / "npm").chmod(0o755)
    run = run_gate(fx)
    assert run.exit == 0
    assert run.calls.count("call: npm audit signatures") == 2
    assert run.calls.count("call: sleep 10") == 1
    assert "⚠ npm audit signatures failed (attempt 1); clearing TUF cache" in run.stdout


def test_an_old_npm_is_upgraded_before_signature_verification(fx: Fixture) -> None:
    fx.data("npm.version", "10.9.4\n")
    fx.data("npm.install.out", "added 1 package\n")
    run = run_gate(fx)
    assert run.exit == 0
    assert "⚠ Upgrading npm to 11.x for Sigstore attestation key compatibility" in run.stdout
    pin = toolchain.pin_for("npm", toolchain.load_pins(ROOT / ".devcontainer" / "toolchain.env"))
    assert "call: npm install -g npm@%s --no-audit --no-fund" % pin in run.calls


def test_a_failed_npm_upgrade_ends_the_run_with_npms_status(fx: Fixture) -> None:
    fx.data("npm.version", "10.9.4\n")
    fx.data("npm.install.exit", "9\n")
    run = run_gate(fx)
    assert run.exit == 9, "set -e hands npm's own status back"
    assert "call: npm audit signatures" not in run.calls


def test_a_missing_npm_is_a_loud_127_naming_the_line(fx: Fixture) -> None:
    """The one case where the two sides' TEXT differs only in the script path."""
    fx.unfake("npm")
    run = run_gate(fx)
    assert run.exit == 127
    assert "<script>: line 385: npm: command not found" in run.stderr
    assert "<script>: line 387: npm: command not found" in run.stderr


# --------------------------------------------------------------------------- deferral ---------------------------------------------------------------------------


def test_a_fix_held_in_the_upgrade_blocklist_is_deferred_not_failed(fx: Fixture) -> None:
    fx.reports(AUDIT_PROD, AUDIT_ALL)
    fx.advisories(
        ("GHSA-j687-52p2-xcff", GHSA_ASTRO_XSS),
        ("GHSA-2pvr-wf23-7pc7", GHSA_ASTRO_SSRF),
        ("GHSA-82fw-gwwq-j7x9", GHSA_VITEST),
    )
    fx.policy(
        ".deps-upgrade-blocklist",
        "# held back\nastro  # BLOCKER: astro 7 removes legacy content collections\n",
    )
    fx.policy(".audit-allowlist", DEV_ALLOWLIST_VITEST)
    run = run_gate(fx)
    assert run.exit == 0
    assert "deferred %s fix requires astro@7.0.2, held in .ci/policy/.deps-upgrade-blocklist" % (
        port.EM
    ) in (run.stdout)
    assert "⚠ Deferred 2 production advisory(ies)" in run.stdout
    assert "call: npm view" not in "\n".join(run.calls), (
        "the blocklist arm must short-circuit before the registry lookup"
    )


def test_a_fix_inside_the_freshness_window_is_deferred(fx: Fixture) -> None:
    """A version published minutes ago is not installable today, so it warns."""
    fx.reports(AUDIT_PROD, AUDIT_ALL)
    fx.advisories(
        ("GHSA-j687-52p2-xcff", GHSA_ASTRO_XSS),
        ("GHSA-2pvr-wf23-7pc7", GHSA_ASTRO_SSRF),
        ("GHSA-82fw-gwwq-j7x9", GHSA_VITEST),
    )
    fx.policy(".audit-allowlist", DEV_ALLOWLIST_VITEST)
    # `date -u -d @<now> --iso-8601=seconds` would be a second implementation of
    # the clock; the fixture just says "2999", which is inside every window.
    fx.data("npmview.astro", '{"7.0.2":"2999-01-01T00:00:00.000Z"}\n')
    run = run_gate(fx)
    assert run.exit == 0
    assert "deferred %s fix published 2999-01-01, within freshness window" % port.EM in (run.stdout)
    assert "call: npm view astro time --json" in run.calls


# --------------------------------------------------------------------------- age ---------------------------------------------------------------------------


def _git(root: pathlib.Path, *args: str, when: str | None = None) -> None:
    env = dict(os.environ)
    env.update(
        {
            "GIT_AUTHOR_NAME": "Fixture",
            "GIT_AUTHOR_EMAIL": "fixture@example.com",
            "GIT_COMMITTER_NAME": "Fixture",
            "GIT_COMMITTER_EMAIL": "fixture@example.com",
        }
    )
    if when:
        env["GIT_AUTHOR_DATE"] = when
        env["GIT_COMMITTER_DATE"] = when
    subprocess.run(
        ["git", "-C", str(root), *args], env=env, check=True, capture_output=True, timeout=120
    )


def test_an_allowlist_entry_older_than_the_fail_window_is_refused(fx: Fixture) -> None:
    """The age gate, driven over a REAL git history rather than a stubbed date.

    `entry_age_days` is `git log -S<entry> --diff-filter=A`, so the fixture needs
    a commit that introduced the line and a committer date old enough to cross AGE_FAIL_DAYS. Without the repository the gate answers 0 and the case would pass while measuring nothing.
    """
    fx.policy(".audit-prod-allowlist", PROD_ALLOWLIST_BOTH)
    _git(fx.root, "init", "-q", "-b", "main")
    _git(fx.root, "add", ".ci/policy/.audit-prod-allowlist")
    _git(fx.root, "commit", "-q", "-m", "seed", when="2019-01-01T00:00:00 +0000")
    run = run_gate(fx)
    assert run.exit == 1
    assert "days old (>365) %s yearly re-review required" % port.EM in run.stdout
    assert "strict age gate enforced" in run.stderr
    assert "1117141 (audit-prod-allowlist entry" in run.stderr


def test_an_allowlist_entry_past_the_warn_window_only_warns(fx: Fixture) -> None:
    fx.policy(".audit-prod-allowlist", PROD_ALLOWLIST_BOTH)
    _git(fx.root, "init", "-q", "-b", "main")
    _git(fx.root, "add", ".ci/policy/.audit-prod-allowlist")
    _git(fx.root, "commit", "-q", "-m", "seed", when="2019-01-01T00:00:00 +0000")
    run = run_gate(fx, AGE_WARN_DAYS="100", AGE_FAIL_DAYS="100000")
    assert run.exit == 0
    assert "days old (>100) %s due for re-review" % port.EM in run.stdout
    assert "✓ Security audit passed" in run.stdout


# --------------------------------------------------------------------------- the pure helpers, and the re-implementations, against the real tools ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fix_type", "is_major", "fix_version", "fix_value", "expected"),
    [
        ("null", "null", "", "null", "no fix information in npm audit output"),
        (
            "boolean",
            "null",
            "",
            "true",
            "transitive fix path exists (try 'npm update <pkg>' or add a root overrides entry)",
        ),
        ("boolean", "null", "", "false", "no fix available upstream"),
        ("object", "true", "7.0.2", "null", "major upgrade required (to 7.0.2)"),
        ("object", "false", "1.2.3", "null", "non-breaking upgrade available (to 1.2.3)"),
        ("object", "true", "", "null", "major upgrade required"),
        ("string", "null", "", "null", "unknown fix type: string"),
    ],
)
def test_describe_fix_answers_what_the_twins_case_statement_answered(
    fix_type: str, is_major: str, fix_version: str, fix_value: str, expected: str
) -> None:
    """The pure helper, against the seven answers the bash `case` gave.

    EACH EXPECTATION IS THE TWIN'S OWN STDOUT, CAPTURED AT DELETION TIME. Until W7P5-b this case lifted `describe_fix() {` out of `audit.sh`'s text and ran it under bash, on the argument that re-typing the `case` here would make the case a test of the copy. That argument dies with the file: there is no longer an original to be a copy OF, and a case that reads a deleted file is
    not a stricter test, it is a broken one. So the seven answers are written down instead, and this is the record of what the gate used to say as well as the check that it still says it.
    """
    assert port.describe_fix(fix_type, is_major, fix_version, fix_value) == expected


@pytest.mark.parametrize(
    "line",
    [
        "a\tb\tc",
        "\t1.2.3\tdesc",
        "a\t\tc",
        "a\tb\tc\td",
        "\t\t",
        "",
        "only",
        "trailing\t\t\t",
        "a\t\t\tb\tc\td\te",
    ],
)
def test_bash_read_fields_matches_a_real_bash_read(line: str) -> None:
    """`IFS=$'\\t' read -r a b c` on THIS bash, not on a remembered rule.

    Nine shapes, including the two the collapsing rule makes surprising: a leading tab and an interior empty field.
    """
    script = 'IFS=$\'\\t\' read -r a b c <<< "$1"; printf \'%s\\x1f%s\\x1f%s\' "$a" "$b" "$c"'
    proc = subprocess.run(
        ["bash", "-c", script, "_", line], capture_output=True, text=True, check=False, timeout=60
    )
    assert proc.returncode == 0, proc.stderr
    assert port.bash_read_fields(line, 3) == proc.stdout.split("\x1f")


@pytest.mark.parametrize(
    "pkg",
    ["astro", "@eslint/js", "foo.bar", "foo", "vite", "not-there", "es", "sharp"],
)
def test_deps_blocklist_has_matches_the_real_grep(
    fx: Fixture, monkeypatch: pytest.MonkeyPatch, pkg: str
) -> None:
    """The re-implemented `grep -qE '^<pkg>([[:space:]]|$)'`, against the real one.

    `grep` here is ugrep, and this repo has already been bitten by ugrep answering differently from PCRE on an alternated anchor. This case is the reason the port is allowed to re-implement the match at all: if the two ever disagree, it goes red naming the package.
    """
    body = (
        "# packages held back\n"
        "astro  # BLOCKER: astro 7 removes legacy content collections\n"
        "@eslint/js  # BLOCKER: v10 peer deps are not ready across three plugins\n"
        "foo.bar\n"
        "foobar\n"
        "esbuild\theld\n"
        "sharp\n"
    )
    fx.policy(".deps-upgrade-blocklist", body)
    pattern = "^%s([[:space:]]|$)" % pkg.replace(".", "\\.")
    real = subprocess.run(
        ["grep", "-qE", pattern, str(fx.root / ".ci" / "policy" / ".deps-upgrade-blocklist")],
        capture_output=True,
        check=False,
        timeout=60,
    )
    monkeypatch.chdir(fx.root)
    assert port.Audit().deps_blocklist_has(pkg) is (real.returncode == 0)


# THE THREE JQ PROGRAMS THE TWIN RAN, WRITTEN OUT IN FULL, indentation included. They were lifted out of `audit.sh`'s text until W7P5-b deleted it; these are the exact strings that lift produced on its last run, and the port's re-implementations are still checked against REAL jq executing them, which is the half of the case that always mattered.
PROGRAM_ADVISORIES = (
    '[.vulnerabilities[].via[] | select(type == "object") | .source] | unique | .[]'
)

PROGRAM_ADVISORY_MAP = """[.vulnerabilities | to_entries[].value.via[]
                     | select(type == "object")
                     | {source, url, title, severity}]
                    | unique_by(.source)
                    | .[] | [.source, .severity, .url, .title] | @tsv"""

PROGRAM_FIX_INFO = """        .vulnerabilities | to_entries[] |
        select(.value.via[] | objects | select(.source == ($id | tonumber))) |
        {
            pkg: .key,
            fixType: (.value.fixAvailable | type),
            fixValue: (if (.value.fixAvailable | type) == "boolean"
                       then (.value.fixAvailable | tostring)
                       else null end),
            isMajor: (if (.value.fixAvailable | type) == "object"
                      then (.value.fixAvailable.isSemVerMajor | tostring)
                      else null end),
            fixVersion: (if (.value.fixAvailable | type) == "object"
                         then .value.fixAvailable.version
                         else null end),
            fixName: (if (.value.fixAvailable | type) == "object"
                      then .value.fixAvailable.name
                      else null end)
        }
    """


def test_the_jq_programs_match_the_real_jq(tmp_path: pathlib.Path) -> None:
    """Every jq program the twin ran, against the jq on this host.

    WHAT THE DELETION COST AND WHAT IT DID NOT. Lifting the programs out of the twin's text caught one thing this cannot: a jq edit in the bash that the port did not follow. There is no bash to drift from any more, so that half is gone with it. The half that remains is the one a re-implementation actually needs -- `program_advisories` and its two siblings are Python rewrites of jq,
    and jq is still here to say whether they agree.
    """
    report = tmp_path / "audit-prod.json"
    report.write_text(AUDIT_ALL, encoding="utf-8")

    def run_jq(*args: str) -> str:
        proc = subprocess.run(
            ["jq", *args, str(report)], capture_output=True, text=True, check=False, timeout=60
        )
        assert proc.returncode == 0, proc.stderr
        return proc.stdout

    document = json.loads(AUDIT_ALL)

    assert port.program_advisories(document) == run_jq("-r", PROGRAM_ADVISORIES).split()
    assert port.program_advisory_map(document) == run_jq("-r", PROGRAM_ADVISORY_MAP).splitlines()

    assert (
        port.jq_print(port.jq_alt(document["metadata"]["vulnerabilities"]["total"], 0))
        == run_jq(".metadata.vulnerabilities.total // 0").strip()
    )

    for advisory_id in ("1117141", "1193684", "9999999"):
        expected = subprocess.run(
            ["jq", "-c", "--arg", "id", advisory_id, PROGRAM_FIX_INFO, str(report)],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        assert expected.returncode == 0, expected.stderr
        assert port.program_fix_info(document, advisory_id) == expected.stdout.splitlines()


def test_the_details_program_matches_the_real_jq(tmp_path: pathlib.Path) -> None:
    """The GHSA-detail `@tsv` row, gsubs and 240-codepoint slice included."""
    cache = tmp_path / "GHSA-x.json"
    body = json.dumps(
        {
            "description": "**Bold** and `code`\r\n\n\n## Heading\nA " + ("long " * 80),
            "vulnerabilities": [
                {"vulnerable_version_range": "< 1.0.0", "first_patched_version": "1.0.0"}
            ],
        }
    )
    cache.write_text(body, encoding="utf-8")
    program = (
        "[\n"
        '    (.vulnerabilities[0].vulnerable_version_range // ""),\n'
        '    (.vulnerabilities[0].first_patched_version // ""),\n'
        '    ((.description // "") | gsub("\\r"; "") | gsub("\\n+"; " ") '
        '| gsub("\\\\*\\\\*|##|`"; "") | .[0:240])\n'
        "] | @tsv"
    )
    proc = subprocess.run(
        ["jq", "-r", program, str(cache)], capture_output=True, text=True, check=False, timeout=60
    )
    assert proc.returncode == 0, proc.stderr
    assert port.program_details(json.loads(body)) == proc.stdout.rstrip("\n")


# --------------------------------------------------------------------------- the control: this suite can go red ---------------------------------------------------------------------------


def _scenario(fx: Fixture, name: str) -> None:
    """The three fixtures the plants run against, so each plant is visible.

    A plant that changes nothing OBSERVABLE in the scenario it runs under is a control that cannot fire, and the first cut of this file had exactly that: the tab-split plant ran against a fixture whose stale sweep was never reached, so the shifted field was never printed and the mutation looked harmless.
    """
    fx.reports(AUDIT_PROD, AUDIT_ALL)
    fx.policy(".audit-prod-allowlist", PROD_ALLOWLIST_BOTH)
    fx.policy(".audit-allowlist", DEV_ALLOWLIST_VITEST)
    bodies = [
        ("GHSA-j687-52p2-xcff", GHSA_ASTRO_XSS),
        ("GHSA-2pvr-wf23-7pc7", GHSA_ASTRO_SSRF),
        ("GHSA-82fw-gwwq-j7x9", GHSA_VITEST),
    ]
    if name == "missing-ghsa":
        bodies = bodies[:1]
    fx.advisories(*bodies)
    if name == "signatures-fail":
        fx.data("npm.signatures.exit", "1\n")


def _plant(fx: Fixture, old_text: str, new_text: str) -> None:
    """Mutate the FIXTURE's copy of the port. Nothing under `.ci/` is written."""
    target = fx.root / PORT_REL
    body = target.read_text(encoding="utf-8")
    assert old_text in body, "the plant no longer matches the port: %r" % old_text[:60]
    target.write_text(body.replace(old_text, new_text, 1), encoding="utf-8")


@pytest.mark.parametrize(
    ("scenario", "old_text", "new_text"),
    [
        # The collapsing read, replaced with the obvious wrong thing. Visible only where a shifted field is PRINTED, which is the stale sweep.
        (
            "full",
            'body = line.strip("\\t")',
            (
                'return [*line.split("\\t"), *([""] * count)][:count]  # planted\n'
                '    body = line.strip("\\t")'
            ),
        ),
        # The DEFECT 6 fallback, "fixed" to write valid JSON. The gate then does not die, which is a different exit code and eleven more lines.
        (
            "missing-ghsa",
            'pathlib.Path(out).write_text("%s\\n" % slug, encoding="utf-8")',
            'pathlib.Path(out).write_text("{}\\n", encoding="utf-8")',
        ),
        # One retry fewer: same verdict, one fewer `npm audit signatures` and one fewer `sleep`, which only the CALL LOG channel can see.
        ("signatures-fail", "SIGNATURE_ATTEMPTS = 3", "SIGNATURE_ATTEMPTS = 2"),
        # DEFECT 4's green line, "fixed" into a conditional one.
        (
            "full",
            'advisory.log_success("No production vulnerabilities")',
            (
                "if not _arith_gt(prod_total, 0):\n            advisory.log_success("
                '"No production vulnerabilities")'
            ),
        ),
    ],
)
def test_a_planted_defect_in_the_port_is_caught(
    fx: Fixture, scenario: str, old_text: str, new_text: str
) -> None:
    """Four plants, four reds. A suite nobody has seen fail is not one.

    Each plant is a change a reviewer might call an IMPROVEMENT -- a tab split that looks right, a fallback that writes valid JSON, one retry fewer, a green line that stops lying. Every one of them is a behavioural difference, and this case is what says so. The last two are the interesting ones: `one attempt fewer` is invisible on stdout and stderr and is caught ONLY by the call
    log.

    THE BASELINE IS THE UNPLANTED GATE, which is what changed at W7P5-b. It used to be the bash twin, and the claim was that the plant made the port disagree with the bash. The two claims are the same claim: the ledger and this file's own cases are what established that the unplanted port and the deleted bash said the same thing, so the recorded run below stands in for the twin
    exactly. It also removes the last way this control could go green for the wrong reason -- a fixture that cannot run EITHER side no longer exists, because there is only one side and the baseline run must succeed before the plant is written.
    """
    _scenario(fx, scenario)
    baseline = run_gate(fx)
    _plant(fx, old_text, new_text)
    with pytest.raises(AssertionError):
        assert_same(baseline, run_gate(fx))


@pytest.mark.parametrize("scenario", ["full", "missing-ghsa", "signatures-fail"])
def test_the_control_passes_without_the_plant(fx: Fixture, scenario: str) -> None:
    """The other half of the control: the same three fixtures, unplanted, REPEAT.

    Without this the plants above would pass for any reason at all, including a gate whose output is not stable between two runs of one fixture -- which would make every plant look caught while catching nothing.
    """
    _scenario(fx, scenario)
    first = run_gate(fx)
    assert_same(first, run_gate(fx))
    assert first.exit == {"full": 0, "missing-ghsa": 5, "signatures-fail": 1}[scenario]


def test_the_port_on_disk_is_unmodified() -> None:
    """The plants run on COPIES inside the fixture. This is the receipt."""
    body = PORT.read_text(encoding="utf-8")
    assert r'write_text("%s\n" % slug' in body
    assert "SIGNATURE_ATTEMPTS = 3" in body
    assert r'body = line.strip("\t")' in body


@pytest.mark.parametrize(
    ("text", "valid"),
    [
        ("", True),
        ("{}", True),
        ('{"a":1}\n{"b":2}\n', True),
        ("   \n\t\n", True),
        ("not json", False),
        ('{"a":1', False),
        ('{"a":1} trailing', False),
    ],
)
def test_jq_empty_matches_the_real_jq(tmp_path: pathlib.Path, text: str, valid: bool) -> None:
    """Including the zero-byte file, which is DEFECT 1's whole mechanism."""
    path = tmp_path / "doc.json"
    path.write_text(text, encoding="utf-8")
    real = subprocess.run(["jq", "empty", str(path)], capture_output=True, check=False, timeout=60)
    assert (real.returncode == 0) is valid, "jq changed its mind about %r" % text
    assert port.jq_empty(str(path)) is valid
