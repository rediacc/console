"""Differential: `rediacc_ci.security.audit` against `.ci/scripts/security/audit.sh`.

THE TWIN IS THE LIVE GATE `check:ci-security-audit`, so nothing here runs it
against the real tree: every case is a scratch fixture holding BOTH
implementations at their real relative paths, with recording fakes for `npm`,
`gh`, `node` and `sleep` on a scratch PATH. There is no read-only mode of this
gate to borrow -- it shells out to the npm registry twice and to the GitHub
Advisory Database once per advisory -- and a differential that made those calls
would be rate-limiting a shared account to prove a text transform.

WHY THE FIXTURE COPIES BOTH IMPLEMENTATIONS AND THE WHOLE PACKAGE. Each side
resolves the repository root from its OWN location (`audit.sh` walks up from
`.ci/scripts/security/`, `paths.repo_root()` walks up from `.ci/rediacc_ci/`),
and the twin's four sourced libraries then shell out to `rediacc_ci.core.*`
under that root. Pointing both at a fixture therefore means putting both, and
the package they share, inside it.

FOUR CHANNELS ARE COMPARED, NOT TWO:
  * exit code,
  * stdout and stderr, SEPARATELY (`differential.py` argues why at length; this
    gate splits one advisory across both streams, so merging them would hide a
    swap),
  * the CALL LOG: every fake appends its exact argv, so a port that produced
    identical bytes by asking different questions fails here,
  * the ARTIFACTS: `audit-report.json` survives a run on purpose (CI uploads it)
    and `audit-prod.json` must not, so both sides' leftovers are diffed too.

TWO NORMALISATIONS, both named:
  * the fixture root, which differs per test,
  * the SCRIPT PATH inside a `line N: npm: command not found`, which bash spells
    as the .sh it is running and the port spells as `sys.argv[0]`. Nothing else
    about that line is normalised, including the line number.

ONE COMPARED-AS-A-MULTISET CHANNEL AND ONE KNOWN COUNT DIVERGENCE:
  * `gh api` runs under `xargs -P 8` / a thread pool, so the call log's order is
    a race. The log is compared as a sorted multiset, and the non-parallel
    subsequence is additionally compared IN ORDER, so serialisation is still
    pinned where it is deterministic.
  * `node --window-seconds`: the twin re-probes its runner on every delegate
    call because the assignment happens inside a command substitution
    (`core/release_age.py` DEFECT 1, measured there), and the port memoises. The
    twin therefore makes exactly ONE more probe than the port whenever the
    freshness delegate is reached. That is asserted as a number rather than
    smoothed away, so it cannot quietly change size.

WHAT THIS FILE PROVES ABOUT THE TWIN, not just about the port: six defects, each
with a case named after it. DEFECT 6 is the one to read first --
`test_defect6_a_failed_gh_fetch_kills_both_sides_with_a_silent_exit_5`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.security import audit as port
from rediacc_ci.tests import differential

if typing.TYPE_CHECKING:  # pragma: no cover - annotations only
    import pathlib

ROOT = paths.repo_root()
TWIN_REL = ".ci/scripts/security/audit.sh"
PORT_REL = ".ci/rediacc_ci/security/audit.py"
TWIN = ROOT / TWIN_REL
PORT = ROOT / PORT_REL

LIB_REL = (
    ".ci/scripts/lib/emit-advisory.sh",
    ".ci/scripts/lib/blocker-validator.sh",
    ".ci/scripts/lib/release-age.sh",
    ".ci/scripts/lib/age-check.sh",
)

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

# Everything the twin, its four libraries, and the port shell out to, minus the four that are faked. `sleep` is deliberately ABSENT: the fake must be the only `sleep` on the PATH, or a case that removes it would wait for real seconds.
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
    "xargs",
)


class Fixture:
    """A scratch repository with both implementations, the fakes, and the policy."""

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

        THE PATH IS TWO CURATED DIRECTORIES AND NOTHING ELSE, which is a safety
        control before it is a determinism one. Appending the caller's PATH after
        the fakes leaves the REAL `npm`, `node` and `gh` reachable, and the first
        version of this file proved it: removing the `npm` fake to test the
        missing-binary path found `~/.local/bin/npm` instead and ran a real
        `npm audit signatures` against a scratch directory. A test suite that can
        reach the npm registry by deleting one file is a test suite that will.
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

    def run(self, side: str, **extra: str) -> Run:
        self._reset()
        log = self.root / ("calls.%s" % side)
        log.write_text("", encoding="utf-8")
        argv = (
            ["bash", str(self.root / TWIN_REL)]
            if side == "old"
            else ["python3", str(self.root / PORT_REL)]
        )
        proc = subprocess.run(
            argv,
            env=self.env(log, **extra),
            cwd=str(self.root),
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
        return Run(
            side=side,
            exit=proc.returncode,
            stdout=self._normalise(proc.stdout),
            stderr=self._normalise(proc.stderr),
            calls=log.read_text(encoding="utf-8").splitlines(),
            artifacts=self._artifacts(),
        )

    def _normalise(self, text: str) -> str:
        text = text.replace(str(self.root), "<fx>")
        return text.replace(TWIN_REL, "<script>").replace(PORT_REL, "<script>")

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
    """One side's four channels."""

    __slots__ = ("artifacts", "calls", "exit", "side", "stderr", "stdout")

    def __init__(
        self,
        side: str,
        exit: int,  # noqa: A002 -- the channel is called `exit`, like the twin's
        stdout: str,
        stderr: str,
        calls: list[str],
        artifacts: dict[str, str],
    ) -> None:
        self.side = side
        self.exit = exit
        self.stdout = stdout
        self.stderr = stderr
        self.calls = calls
        self.artifacts = artifacts


@pytest.fixture
def fx(tmp_path: pathlib.Path) -> Fixture:
    """A scratch repository holding both implementations and the four fakes."""
    root = tmp_path / "fx"
    (root / ".ci" / "scripts" / "security").mkdir(parents=True)
    (root / ".ci" / "scripts" / "lib").mkdir(parents=True)
    (root / ".ci" / "policy").mkdir(parents=True)
    (root / "fake" / "bin").mkdir(parents=True)
    (root / "fake" / "data").mkdir(parents=True)
    (root / "fake" / "home").mkdir(parents=True)

    shutil.copy2(TWIN, root / TWIN_REL)
    for rel in LIB_REL:
        shutil.copy2(ROOT / rel, root / rel)
    # The WHOLE package: the twin's shims run `python3 -m rediacc_ci.core.*` and the port imports four of those modules, all resolved from the fixture root.
    shutil.copytree(
        ROOT / ".ci" / "rediacc_ci",
        root / ".ci" / "rediacc_ci",
        ignore=shutil.ignore_patterns("__pycache__", "tests"),
    )

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


# --------------------------------------------------------------------------- comparison ---------------------------------------------------------------------------

WINDOW_PROBE = "call: node --window-seconds"


def assert_agree(fx: Fixture, **extra: str) -> Run:
    """Run both sides over one fixture and rule on all four channels.

    Returns the TWIN's run, so a case can then assert what it actually saw --
    without which two identically broken sides would score as agreement.
    """
    old = fx.run("old", **extra)
    new = fx.run("new", **extra)

    assert new.exit == old.exit, "exit: twin %s, port %s\ntwin stderr:\n%s\nport stderr:\n%s" % (
        old.exit,
        new.exit,
        old.stderr,
        new.stderr,
    )
    assert new.stdout == old.stdout, "stdout:\n--- twin\n%s--- port\n%s" % (old.stdout, new.stdout)
    assert new.stderr == old.stderr, "stderr:\n--- twin\n%s--- port\n%s" % (old.stderr, new.stderr)
    assert new.artifacts == old.artifacts, "artifacts: twin %s, port %s" % (
        sorted(old.artifacts),
        sorted(new.artifacts),
    )

    # THE RUNNER-PROBE DIVERGENCE, AS A NUMBER. See the module docstring.
    old_probes = old.calls.count(WINDOW_PROBE)
    new_probes = new.calls.count(WINDOW_PROBE)
    if old_probes or new_probes:
        assert old_probes == new_probes + 1, (
            "the runner-probe divergence changed size: twin %d probes, port %d. "
            "core/release_age.py DEFECT 1 says the twin re-probes per delegate call "
            "and the port memoises, which is exactly one extra probe." % (old_probes, new_probes)
        )

    old_rest = [line for line in old.calls if line != WINDOW_PROBE]
    new_rest = [line for line in new.calls if line != WINDOW_PROBE]
    assert sorted(new_rest) == sorted(old_rest), "call log:\n--- twin\n%s\n--- port\n%s" % (
        "\n".join(old.calls),
        "\n".join(new.calls),
    )
    # The parallel `gh` fetches are a race; everything else is a fixed order.
    old_serial = [line for line in old_rest if not line.startswith("call: gh ")]
    new_serial = [line for line in new_rest if not line.startswith("call: gh ")]
    assert new_serial == old_serial, "serial call order:\n--- twin\n%s\n--- port\n%s" % (
        "\n".join(old_serial),
        "\n".join(new_serial),
    )
    return old


# --------------------------------------------------------------------------- the happy paths ---------------------------------------------------------------------------


def test_a_clean_tree_passes_on_both_sides(fx: Fixture) -> None:
    old = assert_agree(fx)
    assert old.exit == 0
    assert "✓ Security audit passed" in old.stdout
    # SEEN, not inferred: the gate really did run both audits.
    assert old.calls.count("call: npm audit --json --omit=dev") == 1
    assert old.calls.count("call: npm audit --json") == 1
    assert "audit-report.json" in old.artifacts, "pass 2's report must survive for the CI artifact"
    assert "audit-prod.json" not in old.artifacts, "the prod sidecar must be cleaned up"


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
    old = assert_agree(fx)
    assert old.exit == 0
    assert "⚠ Allowed production vulnerabilities: 2" in old.stdout
    assert "⚠ Allowed dev vulnerabilities: 1" in old.stdout
    # Pass 3 warns on every entry that HAS a fix but carries a BLOCKER.
    assert "major upgrade required (to 7.0.2) %s BLOCKED:" % port.EM in old.stdout
    assert "✓ Security audit passed" in old.stdout


def test_defect3_an_empty_vulnerable_range_shifts_the_two_fields(fx: Fixture) -> None:
    """`Affected: 7.0.2  ->  Patched in: Host header SSRF.` -- both sides.

    GHSA-2pvr's `vulnerable_version_range` is the empty string, so the TAB run in
    the `@tsv` row collapses, `first_patched_version` lands in the range slot and
    the DESCRIPTION lands in the patched slot. This is the case that would make a
    naive `line.split("\\t")` port disagree, and it disagrees in a direction that
    looks like the port being correct.
    """
    fx.reports(AUDIT_PROD, AUDIT_ALL)
    fx.advisories(
        ("GHSA-j687-52p2-xcff", GHSA_ASTRO_XSS),
        ("GHSA-2pvr-wf23-7pc7", GHSA_ASTRO_SSRF),
        ("GHSA-82fw-gwwq-j7x9", GHSA_VITEST),
    )
    fx.policy(".audit-prod-allowlist", PROD_ALLOWLIST_BOTH)
    fx.policy(".audit-allowlist", DEV_ALLOWLIST_VITEST)
    old = assert_agree(fx)
    assert "  Affected: 7.0.2  →  Patched in: Host header SSRF." in old.stdout, (
        "the field shift is gone from the twin; DEFECT 3 needs re-measuring"
    )
    # The advisory that HAS a range renders correctly, so the shift is the empty field's doing and not a broken renderer.
    assert "  Affected: < 6.1.6  →  Patched in: 6.1.6" in old.stdout


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
    old = assert_agree(fx, CI="true")
    assert "::warning::Allowed production vulnerabilities: 2" in old.stdout
    assert "\033[" not in old.stdout, "colour must be off under CI"


# --------------------------------------------------------------------------- the failing paths ---------------------------------------------------------------------------


def test_an_unallowed_production_advisory_fails(fx: Fixture) -> None:
    fx.reports(AUDIT_PROD, AUDIT_ALL)
    fx.advisories(
        ("GHSA-j687-52p2-xcff", GHSA_ASTRO_XSS),
        ("GHSA-2pvr-wf23-7pc7", GHSA_ASTRO_SSRF),
    )
    old = assert_agree(fx)
    assert old.exit == 1
    assert "✗ Production vulnerabilities: 0 critical, 1 high, 2 total" in old.stderr
    assert "major upgrade required (to 7.0.2)" in old.stdout
    assert "call: npm audit --json" not in old.calls, "pass 2 must not be reached"


def test_an_unallowed_dev_advisory_fails_in_pass_two(fx: Fixture) -> None:
    fx.reports(AUDIT_PROD, AUDIT_ALL)
    fx.advisories(
        ("GHSA-j687-52p2-xcff", GHSA_ASTRO_XSS),
        ("GHSA-2pvr-wf23-7pc7", GHSA_ASTRO_SSRF),
        ("GHSA-82fw-gwwq-j7x9", GHSA_VITEST),
    )
    fx.policy(".audit-prod-allowlist", PROD_ALLOWLIST_BOTH)
    fx.data("npmview.vitest", '{"modified":"2020-01-02T03:04:05.000Z"}\n')
    old = assert_agree(fx)
    assert old.exit == 1
    assert "✗ New dev vulnerabilities: 0 critical, 1 high" in old.stderr
    assert "transitive fix path exists" in old.stdout
    # The freshness delegate WAS consulted, and said the 2020 publish is eligible.
    assert "call: npm view vitest time --json" in old.calls
    assert any(line.startswith("call: node --eligible-epoch") for line in old.calls)


def test_one_advisory_reached_through_two_packages_is_reported_once(fx: Fixture) -> None:
    """`unique` and `unique_by(.source)`, and the FIRST occurrence wins.

    Both are dedup steps a port can drop without any fixture noticing, because
    every other report here mentions each source once. This is the case that
    notices: without `unique` the advisory is emitted twice, and with the wrong
    end of `unique_by` it is emitted with the second package's title and url.
    """
    fx.reports(AUDIT_DUPE)
    fx.advisories(("GHSA-j687-52p2-xcff", GHSA_ASTRO_XSS))
    old = assert_agree(fx)
    assert old.exit == 1
    assert old.stderr.count("1117141 (astro") == 1, "the advisory was emitted twice"
    assert "(first occurrence)" in old.stderr, "unique_by kept the wrong end"
    assert "(second occurrence" not in old.stderr
    # ONE fetch, not two: the second `via` object never reaches the GHSA table.
    assert old.calls.count("call: gh api /advisories/GHSA-j687-52p2-xcff") == 1
    assert not [line for line in old.calls if "GHSA-zzzz" in line]


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
    old = assert_agree(fx)
    assert old.exit == 1
    assert "✗ Stale allowlist entry: 1124334 does not appear in audit-prod.json" in old.stderr
    assert "%s Allowlist problems found %s" % ("\u2717", port.EM) in old.stderr


def test_an_allowlist_entry_with_no_blocker_is_refused(fx: Fixture) -> None:
    fx.policy(".audit-prod-allowlist", "# no reason at all\n1117141\n")
    old = assert_agree(fx)
    assert old.exit == 1
    assert "strict gate enforced" in old.stderr
    assert "call: npm --version" not in old.calls, "the run must stop before touching npm"


def test_a_low_effort_blocker_is_refused(fx: Fixture) -> None:
    fx.policy(".audit-prod-allowlist", "# BLOCKER: no fix\n1117141\n")
    old = assert_agree(fx)
    assert old.exit == 1
    assert "strict gate enforced" in old.stderr


# --------------------------------------------------------------------------- the six defects ---------------------------------------------------------------------------


def test_defect1_an_empty_audit_report_is_a_green_run(fx: Fixture) -> None:
    """A ZERO-BYTE `npm audit --json` passes `jq empty` and the gate reports clean.

    This is the vacuity case: the gate audits nothing and says so in green. It is
    pinned as a fact about the twin, not fixed here.
    """
    fx.reports("", "")
    old = assert_agree(fx)
    assert old.exit == 0
    assert "✓ No production vulnerabilities" in old.stdout
    assert "✓ Security audit passed" in old.stdout
    assert old.artifacts["audit-report.json"] == "", "the empty report really is empty"


def test_defect2_a_non_numeric_allowlist_entry_kills_both_sides_with_exit_5(fx: Fixture) -> None:
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
    old = assert_agree(fx)
    assert old.exit == 5, "the silent jq death is the behaviour under test"
    assert "Stale allowlist entry" not in old.stderr
    # The run got all the way to pass 3 before dying, so both audits already ran.
    assert "→ Checking allowlist entries against available fixes" in old.stdout


def test_defect6_a_failed_gh_fetch_kills_both_sides_with_a_silent_exit_5(fx: Fixture) -> None:
    """The worst of the six: no advisory JSON for a slug, and the gate exits 5 mute.

    `xargs -I {}` rewrites the `{}` inside the worker script, so the fallback
    writes the SLUG into the cache file; the next `jq` cannot parse it and the
    unguarded `details=$(jq ...)` takes the whole gate down under `set -e`. Every
    `gh api` failure -- 404, offline, or the anonymous rate limit the gate
    header's BLOCKER is about -- lands here.
    """
    fx.reports(AUDIT_PROD, AUDIT_ALL)
    # Only ONE of the three advisories has a cached body; the other two fail.
    fx.advisories(("GHSA-j687-52p2-xcff", GHSA_ASTRO_XSS))
    fx.policy(".audit-prod-allowlist", PROD_ALLOWLIST_BOTH)
    fx.policy(".audit-allowlist", DEV_ALLOWLIST_VITEST)
    old = assert_agree(fx)
    assert old.exit == 5
    # The fetch was ATTEMPTED: `gh`'s own stderr is redirected to /dev/null by the twin's worker, so the call log is the only place this is visible.
    assert "call: gh api /advisories/GHSA-2pvr-wf23-7pc7" in old.calls
    assert "✗" not in old.stderr, "the death says nothing at all, which is the finding"
    assert "✗" not in old.stdout
    cached = old.artifacts[".audit-advisory-cache/GHSA-2pvr-wf23-7pc7.json"]
    assert cached == "GHSA-2pvr-wf23-7pc7\n", (
        "the xargs placeholder substitution is gone from the twin; DEFECT 6 needs "
        "re-measuring (expected the slug, got %r)" % cached
    )


def test_defect5_a_wrong_shaped_report_passes_with_a_jq_error(fx: Fixture) -> None:
    """Valid JSON, no `.vulnerabilities`: jq complains on stderr and the gate is green."""
    fx.reports('{"hello": 1}\n')
    old = assert_agree(fx)
    assert old.exit == 0
    assert "jq: error (at audit-prod.json:1): null (null) has no keys" in old.stderr
    assert "✓ Security audit passed" in old.stdout


def test_a_multiline_wrong_shaped_report_names_the_closing_line(fx: Fixture) -> None:
    """jq's `(at <file>:<line>)` is where the DOCUMENT ENDS, not where the fault is."""
    fx.reports('{\n  "hello": 1,\n  "x": [1,\n2]\n}\n')
    old = assert_agree(fx)
    assert "jq: error (at audit-prod.json:5): null (null) has no keys" in old.stderr


def test_invalid_json_is_refused_with_the_registry_advice(fx: Fixture) -> None:
    fx.reports("not json at all\n")
    old = assert_agree(fx)
    assert old.exit == 1
    assert "✗ npm audit failed to produce valid JSON (exit code: 0)" in old.stderr
    assert "✗ This may indicate a network error or npm registry issue" in old.stderr


def test_a_killed_npm_audit_blames_the_signal_and_not_the_registry(fx: Fixture) -> None:
    """Exit 137 with truncated JSON is a local OOM, and the message says so."""
    fx.reports('{"vulnerabilities": {"astro": {"via": [\n')
    fx.data("audit-prod.exit", "137\n")
    old = assert_agree(fx)
    assert old.exit == 1
    assert "✗ npm audit was KILLED by signal 9 (raw 137) before it finished writing JSON" in (
        old.stderr
    )
    assert "NOT a registry or network fault" in old.stderr


# --------------------------------------------------------------------------- signatures, npm version, missing binaries ---------------------------------------------------------------------------


def test_a_signature_failure_retries_three_times_and_refuses(fx: Fixture) -> None:
    fx.data("npm.signatures.exit", "1\n")
    fx.data("npm.signatures.out", "EMISSINGSIGNATUREKEY\n")
    old = assert_agree(fx)
    assert old.exit == 1
    assert old.calls.count("call: npm audit signatures") == 3
    assert old.calls.count("call: sleep 10") == 2, "one sleep between each pair of attempts"
    assert "npm audit signatures failed %s at least one installed package" % port.EM in (old.stderr)
    assert "do NOT allowlist" in old.stderr
    # The TUF cache is cleared before the first attempt and before each retry.
    assert old.calls.count("call: npm config get cache") == 3


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
    old = assert_agree(fx)
    assert old.exit == 0
    assert old.calls.count("call: npm audit signatures") == 2
    assert old.calls.count("call: sleep 10") == 1
    assert "⚠ npm audit signatures failed (attempt 1); clearing TUF cache" in old.stdout


def test_an_old_npm_is_upgraded_before_signature_verification(fx: Fixture) -> None:
    fx.data("npm.version", "10.9.4\n")
    fx.data("npm.install.out", "added 1 package\n")
    old = assert_agree(fx)
    assert old.exit == 0
    assert "⚠ Upgrading npm to 11.x for Sigstore attestation key compatibility" in old.stdout
    assert "call: npm install -g npm@11.17.0 --no-audit --no-fund" in old.calls


def test_a_failed_npm_upgrade_ends_the_run_with_npms_status(fx: Fixture) -> None:
    fx.data("npm.version", "10.9.4\n")
    fx.data("npm.install.exit", "9\n")
    old = assert_agree(fx)
    assert old.exit == 9, "set -e hands npm's own status back"
    assert "call: npm audit signatures" not in old.calls


def test_a_missing_npm_is_a_loud_127_naming_the_line(fx: Fixture) -> None:
    """The one case where the two sides' TEXT differs only in the script path."""
    fx.unfake("npm")
    old = assert_agree(fx)
    assert old.exit == 127
    assert "<script>: line 385: npm: command not found" in old.stderr
    assert "<script>: line 387: npm: command not found" in old.stderr


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
    old = assert_agree(fx)
    assert old.exit == 0
    assert "deferred %s fix requires astro@7.0.2, held in .ci/policy/.deps-upgrade-blocklist" % (
        port.EM
    ) in (old.stdout)
    assert "⚠ Deferred 2 production advisory(ies)" in old.stdout
    assert "call: npm view" not in "\n".join(old.calls), (
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
    old = assert_agree(fx)
    assert old.exit == 0
    assert "deferred %s fix published 2999-01-01, within freshness window" % port.EM in (old.stdout)
    assert "call: npm view astro time --json" in old.calls


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
    a commit that introduced the line and a committer date old enough to cross
    AGE_FAIL_DAYS. Without the repository both sides answer 0 and the case would
    pass while measuring nothing.
    """
    fx.policy(".audit-prod-allowlist", PROD_ALLOWLIST_BOTH)
    _git(fx.root, "init", "-q", "-b", "main")
    _git(fx.root, "add", ".ci/policy/.audit-prod-allowlist")
    _git(fx.root, "commit", "-q", "-m", "seed", when="2019-01-01T00:00:00 +0000")
    old = assert_agree(fx)
    assert old.exit == 1
    assert "days old (>365) %s yearly re-review required" % port.EM in old.stdout
    assert "strict age gate enforced" in old.stderr
    assert "1117141 (audit-prod-allowlist entry" in old.stderr


def test_an_allowlist_entry_past_the_warn_window_only_warns(fx: Fixture) -> None:
    fx.policy(".audit-prod-allowlist", PROD_ALLOWLIST_BOTH)
    _git(fx.root, "init", "-q", "-b", "main")
    _git(fx.root, "add", ".ci/policy/.audit-prod-allowlist")
    _git(fx.root, "commit", "-q", "-m", "seed", when="2019-01-01T00:00:00 +0000")
    old = assert_agree(fx, AGE_WARN_DAYS="100", AGE_FAIL_DAYS="100000")
    assert old.exit == 0
    assert "days old (>100) %s due for re-review" % port.EM in old.stdout
    assert "✓ Security audit passed" in old.stdout


# --------------------------------------------------------------------------- the pure helpers, and the two re-implementations, against the real tools ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fix_type", "is_major", "fix_version", "fix_value"),
    [
        ("null", "null", "", "null"),
        ("boolean", "null", "", "true"),
        ("boolean", "null", "", "false"),
        ("object", "true", "7.0.2", "null"),
        ("object", "false", "1.2.3", "null"),
        ("object", "true", "", "null"),
        ("string", "null", "", "null"),
    ],
)
def test_describe_fix_matches_the_twins_case_statement(
    fx: Fixture, fix_type: str, is_major: str, fix_version: str, fix_value: str
) -> None:
    """The pure helper, driven directly on both sides.

    The twin's `describe_fix` is a shell function, so it is reached by sourcing
    the real file and calling it -- not by re-typing its `case` here, which would
    make this a test of the copy.
    """
    # `describe_fix` is defined in audit.sh's body; the twin has no library seam
    # for it, so the function is lifted out of the file's TEXT by name.
    text = (fx.root / TWIN_REL).read_text(encoding="utf-8")
    start = text.index("describe_fix() {")
    end = text.index("\n}\n", start) + 3
    script = text[start:end] + '\ndescribe_fix "$1" "$2" "$3" "$4"\n'
    proc = subprocess.run(
        ["bash", "-c", script, "_", fix_type, is_major, fix_version, fix_value],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert port.describe_fix(fix_type, is_major, fix_version, fix_value) == proc.stdout.rstrip("\n")


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

    Nine shapes, including the two the collapsing rule makes surprising: a
    leading tab and an interior empty field.
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

    `grep` here is ugrep, and this repo has already been bitten by ugrep
    answering differently from PCRE on an alternated anchor. This case is the
    reason the port is allowed to re-implement the match at all: if the two ever
    disagree, it goes red naming the package.
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


def test_the_jq_programs_match_the_real_jq(fx: Fixture, tmp_path: pathlib.Path) -> None:
    """Every jq program the twin runs, re-derived from the twin's own TEXT.

    The programs are lifted out of `audit.sh` rather than re-typed, so an edit to
    the twin's jq that this port did not follow goes red here instead of showing
    up as a mismatched byte three cases later.
    """
    report = tmp_path / "audit-prod.json"
    report.write_text(AUDIT_ALL, encoding="utf-8")
    twin = (fx.root / TWIN_REL).read_text(encoding="utf-8")

    def run_jq(*args: str) -> str:
        proc = subprocess.run(
            ["jq", *args, str(report)], capture_output=True, text=True, check=False, timeout=60
        )
        assert proc.returncode == 0, proc.stderr
        return proc.stdout

    document = json.loads(AUDIT_ALL)

    advisories_program = twin[twin.index("[.vulnerabilities[].via[]") :].split("'")[0]
    assert port.program_advisories(document) == run_jq("-r", advisories_program).split()

    start = twin.index("[.vulnerabilities | to_entries[].value.via[]")
    map_program = twin[start:].split("'")[0]
    assert port.program_advisory_map(document) == run_jq("-r", map_program).splitlines()

    assert (
        port.jq_print(port.jq_alt(document["metadata"]["vulnerabilities"]["total"], 0))
        == run_jq(".metadata.vulnerabilities.total // 0").strip()
    )

    start = twin.index("        .vulnerabilities | to_entries[] |")
    fix_program = twin[start:].split("'")[0]
    for advisory_id in ("1117141", "1193684", "9999999"):
        expected = subprocess.run(
            ["jq", "-c", "--arg", "id", advisory_id, fix_program, str(report)],
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


# --------------------------------------------------------------------------- the control: this differential can go red ---------------------------------------------------------------------------


def _scenario(fx: Fixture, name: str) -> None:
    """The three fixtures the plants run against, so each plant is visible.

    A plant that changes nothing OBSERVABLE in the scenario it runs under is a
    control that cannot fire, and the first cut of this file had exactly that:
    the tab-split plant ran against a fixture whose stale sweep was never
    reached, so the shifted field was never printed and the mutation looked
    harmless.
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
    """Four plants, four reds. A differential nobody has seen fail is not one.

    Each plant is a change a reviewer might call an IMPROVEMENT -- a tab split
    that looks right, a fallback that writes valid JSON, one retry fewer, a green
    line that stops lying. Every one of them is a behavioural difference from the
    live gate, and this case is what says so. The last two are the interesting
    ones: `one attempt fewer` is invisible on stdout and stderr and is caught
    ONLY by the call log.
    """
    _scenario(fx, scenario)
    _plant(fx, old_text, new_text)
    with pytest.raises(AssertionError):
        assert_agree(fx)


@pytest.mark.parametrize("scenario", ["full", "missing-ghsa", "signatures-fail"])
def test_the_control_passes_without_the_plant(fx: Fixture, scenario: str) -> None:
    """The other half of the control: the same three fixtures, unplanted, AGREE.

    Without this the plants above would pass for any reason at all, including a
    fixture that cannot run either side.
    """
    _scenario(fx, scenario)
    old = assert_agree(fx)
    assert old.exit == {"full": 0, "missing-ghsa": 5, "signatures-fail": 1}[scenario]


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
