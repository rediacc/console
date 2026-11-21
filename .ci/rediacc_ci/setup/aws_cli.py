"""The two logic steps of `.github/actions/setup-aws`, moved out of the action's YAML.

    PYTHONPATH=.ci python3 -m rediacc_ci.setup.aws_cli pin
    EXPORT_ENV=true PYTHONPATH=.ci python3 -m rediacc_ci.setup.aws_cli install

`pin` resolves the AWSCLI_VERSION pin and the sha256 pin for THIS runner's platform from `.devcontainer/toolchain.env` and appends `version=` and `sha=` to GITHUB_OUTPUT, which key the cache so a version bump or an installer swap can never restore the previous install. Environment: RUNNER_OS, RUNNER_ARCH, GITHUB_OUTPUT.

`install` runs `.ci/bootstrap.sh install aws` (idempotent on a cache hit; on a miss it downloads, verifies the sha256 and installs under `.ci/cache/toolchain`), locates the pinned binary with `which aws --pin`, appends `aws-bin=` to GITHUB_OUTPUT and, when EXPORT_ENV is `true`, appends AWS_BIN and the R2 client settings to GITHUB_ENV. Environment: EXPORT_ENV, RUNNER_TEMP, GITHUB_OUTPUT, GITHUB_ENV, and optionally AWS_CONFIG_FILE.

Every refusal prints an `::error::` annotation and exits 1.
"""

import os
import pathlib
import subprocess
import sys

from rediacc_ci.core import toolchain

# The sha256 pin key per runner platform; macOS is one key for both architectures.
SHA_KEYS = {
    ("Linux", "X64"): "AWSCLI_SHA256_LINUX_X86_64",
    ("Linux", "ARM64"): "AWSCLI_SHA256_LINUX_AARCH64",
    ("macOS", "X64"): "AWSCLI_SHA256_DARWIN",
    ("macOS", "ARM64"): "AWSCLI_SHA256_DARWIN",
}

# R2 rejects aws CLI v2's default flexible checksums on multipart uploads (InvalidPart), so every later step asks for them only where required; rediacc_ci.core.awscli.R2_CHECKSUM_ENV sets the same pair for Python callers.
R2_ENV = (
    "AWS_REQUEST_CHECKSUM_CALCULATION=when_required",
    "AWS_RESPONSE_CHECKSUM_VALIDATION=when_required",
)

# The classic S3 transfer client (.ci/config/aws-cli.cfg header says why), written outside the checkout so a sparse cone without .ci/config still gets it.
CLASSIC_CFG = "[default]\ns3 =\n  preferred_transfer_client = classic\n"


class RefusalError(Exception):
    """A state the step must fail on; the message is the annotation text."""


def append(path: str, text: str) -> None:
    with open(path, "a", encoding="utf-8") as out:
        out.write(text)


def pin_outputs(runner_os: str, runner_arch: str) -> list[str]:
    """The `version=` and `sha=` output lines for a platform, or a RefusalError."""
    try:
        version = toolchain.pin_for("aws")
    except toolchain.PinError:
        raise RefusalError("AWSCLI_VERSION is not pinned in .devcontainer/toolchain.env") from None
    sha_key = SHA_KEYS.get((runner_os, runner_arch))
    if sha_key is None:
        raise RefusalError("no pinned aws CLI installer for %s-%s" % (runner_os, runner_arch))
    try:
        sha = toolchain.pin(sha_key)
    except toolchain.PinError:
        raise RefusalError("%s is not pinned in .devcontainer/toolchain.env" % sha_key) from None
    return ["version=%s" % version, "sha=%s" % sha]


def run_pin() -> None:
    lines = pin_outputs(os.environ.get("RUNNER_OS", ""), os.environ.get("RUNNER_ARCH", ""))
    append(os.environ["GITHUB_OUTPUT"], "".join(line + "\n" for line in lines))


def run_install() -> None:
    subprocess.run(["bash", ".ci/bootstrap.sh", "install", "aws"], check=True)
    found = subprocess.run(
        ["bash", ".ci/bootstrap.sh", "which", "aws", "--pin"],
        check=True,
        capture_output=True,
        text=True,
    )
    aws_bin = found.stdout.strip()
    if not (aws_bin and os.path.isfile(aws_bin) and os.access(aws_bin, os.X_OK)):
        raise RefusalError("the pinned aws CLI is not executable at %s" % aws_bin)
    append(os.environ["GITHUB_OUTPUT"], "aws-bin=%s\n" % aws_bin)
    if os.environ.get("EXPORT_ENV", "") != "true":
        return
    env_lines = ["AWS_BIN=%s" % aws_bin, *R2_ENV]
    existing = os.environ.get("AWS_CONFIG_FILE", "")
    if existing:
        # A config the runner or job already names is kept, as rediacc_ci.core.awscli.r2_env keeps it (review c06b2082.3).
        print(
            "::notice::AWS_CONFIG_FILE is already set (%s); kept as is, so its "
            "preferred_transfer_client decides and the classic client is not enforced" % existing
        )
    else:
        cfg = pathlib.Path(os.environ["RUNNER_TEMP"]) / "aws-cli.cfg"
        cfg.write_text(CLASSIC_CFG, encoding="utf-8")
        env_lines.append("AWS_CONFIG_FILE=%s" % cfg)
    append(os.environ["GITHUB_ENV"], "".join(line + "\n" for line in env_lines))


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    verbs = {"pin": run_pin, "install": run_install}
    if len(args) != 1 or args[0] not in verbs:
        print(
            "usage: PYTHONPATH=.ci python3 -m rediacc_ci.setup.aws_cli pin|install", file=sys.stderr
        )
        return 2
    try:
        verbs[args[0]]()
    except RefusalError as exc:
        print("::error::%s" % exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
