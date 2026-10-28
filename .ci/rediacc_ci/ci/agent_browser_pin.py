#!/usr/bin/env python3
"""Read the agent-browser pin from the devcontainer and verify the installed binary against it.

`.github/workflows/ci-quality.yml` runs this in two steps of the quality-static job: "Install agent-browser" calls `read` to learn the version to install, and "Verify agent-browser is functional" calls `verify` to compare `agent-browser --version` with the same ARG line. The pin lives in `.devcontainer/Dockerfile` as `ARG AGENT_BROWSER_VERSION=<version>`, the site the pins registry bumps.

Both verbs fail loudly. A missing ARG line, an empty value, a failing `agent-browser --version` and a mismatch each exit 1 with a message on stderr. Two empty values never compare equal: empty is a refusal, not a match.

Environment: none. Everything arrives through flags.

Run locally from anywhere:

    PYTHONPATH=.ci python3 -m rediacc_ci.ci.agent_browser_pin read
    PYTHONPATH=.ci python3 -m rediacc_ci.ci.agent_browser_pin verify
    PYTHONPATH=.ci python3 -m rediacc_ci.ci.agent_browser_pin verify --version-output 'agent-browser 0.39.4'

`--dockerfile` defaults to `.devcontainer/Dockerfile` resolved against the repo root, not the cwd. `--version-output` replaces the `agent-browser --version` call, for tests.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys

from rediacc_ci import paths

DEFAULT_DOCKERFILE = ".devcontainer/Dockerfile"
ARG_NAME = "AGENT_BROWSER_VERSION"

_ARG_LINE = re.compile(r"^ARG " + ARG_NAME + r"=(.*)$")
_QUOTES = "\"'"


class PinError(Exception):
    """A refusal, carrying the sentence the operator reads."""


def parse_pin(text: str, source: str = DEFAULT_DOCKERFILE) -> str:
    """The value of the first `ARG AGENT_BROWSER_VERSION=` line, unquoted and trimmed.

    Pre-release (`0.40.0-beta.1`) and build metadata (`1.0.0+b.1`) pass through untouched.
    """
    for line in text.splitlines():
        match = _ARG_LINE.match(line)
        if match is None:
            continue
        value = match.group(1).strip().strip(_QUOTES).strip()
        if not value:
            raise PinError("ARG %s= in %s has an empty value" % (ARG_NAME, source))
        return value
    raise PinError("no `ARG %s=` line found in %s" % (ARG_NAME, source))


def read_pin(dockerfile: pathlib.Path) -> str:
    try:
        text = dockerfile.read_text(encoding="utf-8")
    except OSError as err:
        raise PinError("cannot read %s: %s" % (dockerfile, err)) from err
    return parse_pin(text, str(dockerfile))


def installed_version(output: str) -> str:
    """The last whitespace-separated token of `agent-browser --version`, or empty."""
    tokens = output.split()
    return tokens[-1] if tokens else ""


def compare(installed: str, pinned: str) -> None:
    """Exact string equality, and never between two empty values."""
    if not installed:
        raise PinError("agent-browser --version printed no version")
    if not pinned:
        raise PinError("the pinned version is empty")
    if installed != pinned:
        raise PinError(
            "agent-browser reports '%s', the ARG in the Dockerfile is '%s'" % (installed, pinned)
        )


def run_version() -> str:
    try:
        done = subprocess.run(
            ["agent-browser", "--version"], capture_output=True, text=True, check=False
        )
    except OSError as err:
        raise PinError("agent-browser --version failed after the install: %s" % err) from err
    if done.returncode != 0:
        raise PinError(
            "agent-browser --version failed after the install (rc=%d): %s"
            % (done.returncode, done.stderr.strip())
        )
    return done.stdout


def _dockerfile(arg: str | None) -> pathlib.Path:
    path = pathlib.Path(arg or DEFAULT_DOCKERFILE)
    return path if path.is_absolute() else paths.repo_root() / path


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="agent_browser_pin", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="verb", required=True)
    read_p = sub.add_parser("read", help="print the pinned version")
    verify_p = sub.add_parser("verify", help="compare the installed version with the pin")
    for p in (read_p, verify_p):
        p.add_argument(
            "--dockerfile", default=None, help="default: %s at the repo root" % DEFAULT_DOCKERFILE
        )
    verify_p.add_argument(
        "--version-output", default=None, help="stand-in for `agent-browser --version`"
    )
    args = parser.parse_args(argv)

    try:
        pinned = read_pin(_dockerfile(args.dockerfile))
        if args.verb == "read":
            print(pinned)
            return 0
        output = args.version_output if args.version_output is not None else run_version()
        compare(installed_version(output), pinned)
    except PinError as err:
        sys.stderr.write("agent_browser_pin: %s\n" % err)
        return 1
    print("agent-browser %s matches the pin" % pinned)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
