#!/usr/bin/env python3
"""Rotate BWS_ACCESS_TOKEN: take a new machine-account token from the operator's terminal, prove it works, then install it everywhere that already holds one.

WHAT THIS IS FOR. `agent/plans/PLAN-bws-rotation-on-failure.md` deletes the hand-maintained expiry date and makes a non-zero `bws` the only signal there is. This is the other half of that trade: the procedure the failure points at.

WHAT IT DELIBERATELY CANNOT DO. It cannot MINT a token. bws 2.1.0 has no such verb; a machine-account token is created in the Bitwarden web vault by a human
with an account. Everything here is downstream of a value the operator already
holds.

THE INPUT PATH IS A TTY AND NOTHING ELSE, and that refusal is the mechanism that keeps the value out of an AI session rather than a politeness. A Bash tool call has no controlling terminal, so an agent PHYSICALLY CANNOT feed this script: a non-tty stdin exits 2 before anything else runs.
There is no --token flag, no environment override and no stdin path, because each of those is a door an agent could walk through while believing it was being helpful.

NOTHING IS PRINTED. Not the token, not a prefix of it, not its length. The only thing derived from it that ever reaches a stream is the sha256 fingerprint of its CLIENT ID half, which `rediacc_ci.core.bws_env` computes and which is publishable by construction: the identifier is not a credential and 16 hex digits of a digest of it cannot be walked back to one.

THE VALIDATION GATE IS THE ANTI-invalid_signature CLAUSE, INVERTED. The bug this repository shipped once was an unchecked HTTP response becoming a credential.
The unchecked thing here would be an unverified paste becoming the credential for five repositories at once, and a SHORT LISTING is the exact analogue of that silent 404: a scoped-down token answers `secret list` with exit 0 and a handful of rows, which looks like success in every way except the count. So nothing is written until four things pass.

THE SEAMS, and why they exist. BWS_BIN, GH_BIN, BWS_ROTATE_ENV_FILE, BWS_ROTATE_GITMODULES and BWS_ROTATE_SECRET_MAP let `.ci/rediacc_ci/tests/gates/test_gate_bws_rotate.py` drive every function against fakes.
NONE of them is a door around the TTY refusal: the prompt has no seam at all, and the gate test reaches the functions by IMPORTING this module, which never runs `main()` on import.

PORTED FROM BASH 2026-09-23 (Ruling 7, 2026-09-06: these trees are Python). Ported faithfully from `scripts/dev/bws-rotate.sh`'s last bash revision -- same checks, same messages, same order, same seams. The bash file's own `.ci/scripts/test/gates/test-bws-rotate.sh` was the spec this port is verified against, case for case.
"""

from __future__ import annotations

import getpass
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import NoReturn

ROOT = Path(__file__).resolve().parents[2]

BWS_BIN = os.environ.get("BWS_BIN", "bws")
GH_BIN = os.environ.get("GH_BIN", "gh")
ENV_FILE = Path(os.environ.get("BWS_ROTATE_ENV_FILE", str(ROOT / "private/account/.env")))
GITMODULES = Path(os.environ.get("BWS_ROTATE_GITMODULES", str(ROOT / ".gitmodules")))
SECRET_MAP = Path(
    os.environ.get("BWS_ROTATE_SECRET_MAP", str(ROOT / ".ci/config/bws-secret-map.json"))
)
NOTICE = ROOT / ".ci/config/bws-rotation-notice.txt"

# The variable name, in one place. It is the one credential that cannot come out of Bitwarden, and it is spelled identically in .env, in every GitHub repo secret, and in `bws`'s own environment lookup.
VAR = "BWS_ACCESS_TOKEN"

# THE FLOOR IS THE SAME 40 `scripts/ops/bws-map-refresh.py` refuses below, and for the identical reason: a scoped-down token or a wrong project returns a SHORT list rather than an error. A rotation that installed such a token would succeed here and fail in CI, one secret at a time, days later.
MIN_SECRETS = int(os.environ.get("BWS_ROTATE_MIN_SECRETS", "40"))

# The parent repository. Every other target is derived from .gitmodules; this one cannot be, because a repository does not list itself as its own submodule.
PARENT_REPO = "rediacc/console"

# token_shape_ok <candidate> -- `0.<client-id>.<secret>:<key>`, the shape bws parses. A paste that lost its leading `0.` (a copy that started one character late is the commonest way) fails here rather than four steps later with "Doesn't contain a decryption key", which names nothing a reader can act on.
TOKEN_RE = re.compile(r"^0\.[^.\s]+\.[^:\s]+:\S+$")


def die(msg: str) -> NoReturn:
    print("✗ %s" % msg, file=sys.stderr)
    raise SystemExit(1)


def token_shape_ok(candidate: str) -> bool:
    return bool(TOKEN_RE.match(candidate))


def fingerprint_of(candidate: str) -> str:
    """16 hex digits of sha256 over the CLIENT ID half.

    THE VALUE GOES THROUGH THE ENVIRONMENT OF ONE CHILD PROCESS, never through argv: argv is visible in `ps`, in process accounting and in a shell history. The computation itself is `rediacc_ci.core.bws_env.client_fingerprint`, which is where `warn_if_token_expiring()`'s one self-checking part went when the expiry file was deleted.
    One implementation, so two fingerprints are comparable.
    """
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "rediacc_ci.core.bws_env", "fingerprint"],
            env={**os.environ, "BWS_ACCESS_TOKEN": candidate, "PYTHONPATH": str(ROOT / ".ci")},
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return proc.stdout.strip()


def require_fingerprint_tool() -> None:
    """A CONTROL ON CHECK 3, run before the prompt.

    FOUND BY A PLANT, which is the only reason it exists. `fingerprint_of` returns "" both when the candidate has no client id and when the module could not be imported at all, and check 3 read the second as the first: a copy of this script run from outside the repository refused a perfectly good token with "the candidate has no client id to fingerprint".
    That is a missing tool wearing a verdict's clothes, which is the failure this whole estate is built to refuse.

    THE PROBE VALUE CERTAINLY HAS A CLIENT ID and is a credential nowhere. So an empty answer can only mean the tool did not run, and the message says which command to try and why check 3 cannot proceed without it.
    """
    if not fingerprint_of("0.probe-client-id.not-a-secret:not-a-key"):
        die(
            "the fingerprint tool could not be reached: "
            "`PYTHONPATH=%s python3 -m rediacc_ci.core.bws_env fingerprint` answered nothing "
            "for a probe value that certainly has a client id. Check 3 compares the "
            "candidate's machine account against the installed one and cannot run without it, "
            "so a token that merely repeats the current credential would be installed "
            "unnoticed. Run this from a checkout of the console repository. "
            "Nothing has been changed" % (ROOT / ".ci")
        )


def project_uuid() -> str:
    """The ci-shared project the listing must come from."""
    doc = json.loads(SECRET_MAP.read_text(encoding="utf-8"))
    return str(doc.get("project") or "")


def probe_count(candidate: str) -> str | None:
    """How many secrets of the target project the candidate can actually read.

    Returns a NUMBER as a string, or None when bws failed.

    STDOUT IS PARSED AND NEVER SHOWN. `bws secret list` returns each secret's decrypted VALUE alongside its key, so the bytes are handed straight to a projection that counts them and keeps nothing. `--color no` is load-bearing for the same reason it is everywhere else in this tree: bws 2.1.0 wraps `--output json` in truecolor escapes that no JSON parser survives.
    """
    project = project_uuid()
    if not project:
        return None
    try:
        proc = subprocess.run(
            [BWS_BIN, "--color", "no", "secret", "list", project, "--output", "json"],
            env={**os.environ, "BWS_ACCESS_TOKEN": candidate},
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    try:
        rows = json.loads(proc.stdout)
    except ValueError:
        return None
    return str(len([r for r in rows if isinstance(r, dict)]))


# --------------------------------------------------------------------------
# PROPAGATION. Targets are DERIVED, so a fifth submodule needs no edit here.
# --------------------------------------------------------------------------

URL_RE = re.compile(r"^\s*url\s*=\s*(\S.*)$", re.MULTILINE)


def submodule_repos() -> list[str]:
    """`owner/name` for every submodule in .gitmodules, sorted.

    DERIVED AT RUN TIME AND NOT LISTED. A hardcoded list is a list that is right on the day it is written; D1's control fakes a fifth repository into holding the secret and requires it to be written, which is only possible if the target set comes from live state.
    """
    if not GITMODULES.is_file():
        return []
    repos = set()
    for raw in URL_RE.findall(GITMODULES.read_text(encoding="utf-8")):
        url = raw.strip()
        url = re.sub(r"^https://github\.com/", "", url)
        url = re.sub(r"^git@github\.com:", "", url)
        url = re.sub(r"\.git$", "", url)
        if re.match(r"^[^/]+/[^/]+$", url):
            repos.add(url)
    return sorted(repos)


def target_repos() -> list[str]:
    """The parent plus every submodule. The FULL candidate set, before anything is asked about which of them holds a secret."""
    return sorted({PARENT_REPO, *submodule_repos()})


def repo_has_secret(repo: str) -> bool:
    """Does this repository already carry $VAR?

    REFRESH-ONLY IS THE WHOLE POINT OF THIS QUESTION. Two of the five repositories hold the secret and have no consumer for it; two hold none at all. Adopting them would push a live credential into repositories that do not use one, which is the opposite of what a rotation is for. A repository without it is REPORTED by name so the omission is visible, never silently created.
    """
    try:
        proc = subprocess.run(
            [GH_BIN, "secret", "list", "-R", repo], capture_output=True, text=True, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if proc.returncode != 0:
        return False
    for line in proc.stdout.splitlines():
        parts = line.split()
        if parts and parts[0] == VAR:
            return True
    return False


def set_repo_secret(repo: str, candidate: str) -> bool:
    """The write. The value reaches gh on STDIN.

    NEVER ON argv, and `gh secret set NAME --body <value>` is exactly the call this avoids: the value would sit in `ps` output for the life of the process and in the shell history for ever.
    """
    try:
        proc = subprocess.run(
            [GH_BIN, "secret", "set", VAR, "-R", repo, "--body-file", "-"],
            input=candidate,
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def env_file_write(candidate: str) -> None:
    """Replace or append $VAR in the local .env.

    WRITTEN THROUGH A TEMPORARY AND MOVED INTO PLACE, with the mode carried over. A partial write to the file that every local command reads would break the working credential as well as the new one, and an in-place edit that dies halfway does exactly that.
    """
    if not ENV_FILE.is_file():
        die(
            "%s does not exist; this script refreshes the local credential, it does not "
            "create the file that holds it" % ENV_FILE
        )
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    seen = False
    for line in lines:
        key = line.split("=", 1)[0].strip()
        if key == VAR and not line.lstrip().startswith("#"):
            out.append("%s=%s" % (VAR, candidate))
            seen = True
        else:
            out.append(line)
    if not seen:
        out.append("%s=%s" % (VAR, candidate))
    fd, tmp_name = tempfile.mkstemp(prefix=ENV_FILE.name + ".rotate.", dir=str(ENV_FILE.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write("\n".join(out) + "\n")
        try:
            os.chmod(tmp_name, ENV_FILE.stat().st_mode)
        except OSError:
            os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, ENV_FILE)
    except BaseException:
        with __import__("contextlib").suppress(OSError):
            os.unlink(tmp_name)
        raise


# --------------------------------------------------------------------------
# THE PROMPT, AND THE ONE REFUSAL THAT HAS NO SEAM.
# --------------------------------------------------------------------------


def read_candidate() -> str:
    if not sys.stdin.isatty():
        print("✗ %s refuses a non-TTY stdin." % sys.argv[0], file=sys.stderr)
        print(file=sys.stderr)
        print(
            "  This is not a limitation to work around. The value is read from a terminal with echo off so that it never reaches argv, a shell history, a log or a process listing. A tool call has no controlling terminal, which is exactly what makes it unable to supply a credential here.",
            file=sys.stderr,
        )
        print(file=sys.stderr)
        print(
            "  The operator runs this in their own terminal. An AI session's whole part is to say so and stop; see .ci/config/bws-rotation-notice.txt.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    try:
        value = getpass.getpass("Paste the NEW %s (input is hidden), then press Enter: " % VAR)
    except (EOFError, KeyboardInterrupt):
        value = ""
    return value


# --------------------------------------------------------------------------
# THE RUN.
# --------------------------------------------------------------------------


def main() -> int:
    if shutil.which(BWS_BIN) is None:
        die(
            "the bws CLI is not on PATH (set BWS_BIN). The devcontainer installs it; "
            "see .devcontainer/Dockerfile"
        )
    if shutil.which(GH_BIN) is None:
        die(
            "the GitHub CLI is not on PATH (set GH_BIN). Repository secrets cannot be "
            "refreshed without it"
        )
    try:
        auth = subprocess.run([GH_BIN, "auth", "status"], capture_output=True, check=False)
    except (OSError, subprocess.SubprocessError):
        auth = None
    if auth is None or auth.returncode != 0:
        die("gh is not authenticated; run `gh auth login` first. Nothing has been changed")
    require_fingerprint_tool()

    if NOTICE.is_file() and NOTICE.stat().st_size > 0:
        print("The procedure this implements is in .ci/config/bws-rotation-notice.txt.")
        print()
    else:
        print(
            "!! %s is missing or empty. The rotation can still run; the document that" % NOTICE,
            file=sys.stderr,
        )
        print("   explains it to the next reader is what is absent.", file=sys.stderr)

    candidate = read_candidate()

    # ---- CHECK 1: shape.
    if not candidate:
        die("nothing was entered. Nothing has been changed")
    if not token_shape_ok(candidate):
        die(
            "that is not shaped like a machine-account token "
            "(`0.<client-id>.<secret>:<key>`). Nothing has been changed"
        )
    print("✓ 1/4 shape")

    # ---- CHECK 2: the live probe. A SHORT LISTING IS THE SILENT 404 OF THIS SCRIPT: exit 0, plausible output, and a credential that cannot read most of what the repository needs.
    count = probe_count(candidate)
    if count is None:
        die(
            "the candidate could not read the store at all. Either it is wrong, or Bitwarden "
            "is unreachable; the two look identical from here. Nothing has been changed"
        )
    if int(count) < MIN_SECRETS:
        die(
            "the candidate reads only %s secret(s) of the project, and the floor is %d. "
            "That is what a SCOPED-DOWN token looks like: exit 0, real output, and most of "
            "the store invisible. Nothing has been changed" % (count, MIN_SECRETS)
        )
    print("✓ 2/4 live probe: %s secret(s) readable, floor %d" % (count, MIN_SECRETS))

    # ---- CHECK 3: it is actually a different credential.
    new_fp = fingerprint_of(candidate)
    if not new_fp:
        die("the candidate has no client id to fingerprint. Nothing has been changed")
    old_fp = fingerprint_of(os.environ.get(VAR, ""))
    if old_fp and new_fp == old_fp:
        die(
            "the candidate is the SAME machine account as the one already installed (%s). "
            "A rotation that installs the credential it was meant to replace reports success "
            "and changes nothing. Nothing has been changed" % new_fp
        )
    print(
        "✓ 3/4 client id %s, which differs from the installed one (%s)"
        % (new_fp, old_fp or "none in this environment")
    )

    # ---- CHECK 4: nothing above printed any part of the value, and nothing below will either. Asserted by the gate test rather than by a line here, because a claim in a comment is not a check.
    print("✓ 4/4 no part of the value has been printed, and none will be")
    print()

    # ---- THE TARGET SET, derived, before anything is written.
    repos = target_repos()
    if not repos:
        die(
            "no target repository could be derived from %s. A rotation with nothing to write "
            "to is a wiring fault, not a quiet success" % GITMODULES
        )
    holders: list[str] = []
    absent: list[str] = []
    for repo in repos:
        (holders if repo_has_secret(repo) else absent).append(repo)
    if not holders:
        die(
            "none of the %d derived repositories carries a %s secret. Either gh cannot see "
            "them or the name has changed; both are louder problems than a stale token. "
            "Nothing has been changed" % (len(repos), VAR)
        )

    print("%d repository(ies) derived from %s plus the parent:" % (len(repos), GITMODULES.name))
    for repo in holders:
        print("    refresh  %s" % repo)
    for repo in absent:
        print(
            "    SKIP     %s (carries no %s; a rotation never CREATES one, because that "
            "would push a live credential into a repository with no consumer)" % (repo, VAR)
        )
    print()

    # ---- THE WRITES. Local first: it is the one target that can be corrected by hand in a second if anything below fails.
    env_file_write(candidate)
    print("✓ wrote %s to %s" % (VAR, ENV_FILE))

    failed: list[str] = []
    for repo in holders:
        if set_repo_secret(repo, candidate):
            print("✓ refreshed %s" % repo)
        else:
            failed.append(repo)
            print("✗ FAILED  %s" % repo, file=sys.stderr)

    print()
    if failed:
        print(
            "✗ %d of %d repository secret(s) were NOT written: %s"
            % (len(failed), len(holders), " ".join(failed)),
            file=sys.stderr,
        )
        print(
            "  The local .env and the repositories above DID take the new value, so the fleet is now split across two credentials. Re-run this script once gh can reach the failed repositories; writing the same value twice is harmless.",
            file=sys.stderr,
        )
        return 1

    print("✓ rotation complete: %s and %d repository secret(s)." % (ENV_FILE, len(holders)))
    print()
    print(
        "WHAT THIS PROVES, AND WHAT IT DOES NOT. A GitHub Actions secret cannot be read back through the API, so what was verified is that each write returned success and moved the secret's updated_at. That is not the same claim as the intended value having landed. The next CI run is the only end-to-end proof there is."
    )
    print()
    print(
        "The OLD token is still live. Revoking it in the web vault before the next green CI run would remove the fallback at the exact moment it might be needed."
    )
    print()
    # THE DORMANT-SECRET DECISION, printed HERE because this is the one moment anybody is thinking about these credentials. Measured 2026-09-06: private/account and private/renet hold a BWS_ACCESS_TOKEN set on 2026-09-02, and NOTHING in either repository reads it.
    # This script keeps them current because refresh-only is the rule, and keeping an unused credential alive is a choice rather than a default. It is the operator's to make, and it is stated rather than silently taken.
    print(
        "OPEN DECISION, and it belongs to the operator rather than to this script. Two of the repositories refreshed above were measured on 2026-09-06 to hold this secret with NO consumer: private/account and private/renet. Refresh-only keeps them current, which is the safe default and not necessarily the right one. Deleting them would be least-privilege; keeping them costs one more place a live credential sits. Either is fine, and choosing nothing is the one option that is not."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
