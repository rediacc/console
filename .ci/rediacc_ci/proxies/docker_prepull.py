"""Port of `.ci/scripts/test/proxies/proxy-docker-prepull.sh`.

Local proxy for `.ci/scripts/infra/docker-prepull.sh`. The proxy runs the REAL
script, against docker, on the smallest public image there is
(`hello-world`), in both argument shapes the subject parses:
`<ref>` and `<ref>=<platform>`. The subject's argument grammar is the
interesting part -- `image="${spec%%=*}"` has to survive a ref that itself
contains `:` and `/` -- so this proxy exercises the split, not just the pull.
The subject stays bash and unported; only the proxy is ported here.

If the image was not already present it is removed afterwards, so the proxy
leaves the daemon exactly as it found it -- preserved as `_Cleanup` below.

THE FAILURE PATH IS DELIBERATELY NOT DRIVEN, same reason as the bash twin: an
unpullable ref costs three attempts with 30s/60s sleeps between them in the
subject, which would add 90s to a pre-push gate. The no-arguments refusal
proves the subject can fail and costs nothing.

CANNOT-RUN, not a verdict: no docker binary, no reachable daemon, or no
reachable registry all exit 77.

K=5 LEDGER: `.ci/shadow/w7p6-proxy-docker-prepull.observations.jsonl`.
"""

from __future__ import annotations

import subprocess
import sys

from rediacc_ci import paths
from rediacc_ci.core import proxyx

IMAGE = "hello-world:latest"


def _image_present(image: str) -> bool:
    return (
        subprocess.run(
            ["docker", "image", "inspect", image],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0
    )


def run() -> int:
    root = paths.repo_root()
    subject = str(root / ".ci" / "scripts" / "infra" / "docker-prepull.sh")

    p = proxyx.Proxy("docker-prepull", ".ci/scripts/infra/docker-prepull.sh")
    p.need_exec(subject, "the subject script is missing from this checkout")
    p.need_docker_daemon()
    p.need_url(
        "https://registry-1.docker.io/v2/",
        "the subject pulls public base images from docker hub",
    )
    p.preflight()

    preexisting = _image_present(IMAGE)
    try:
        # No arguments is refused, not an empty success.
        p.expect_exit("1", "no arguments is refused, not treated as an empty success", [subject])
        p.expect_contains(
            p.last_stderr + p.last_stdout,
            "Usage:",
            "the refusal prints its usage",
        )

        # Bare ref.
        p.expect_exit("0", "a bare ref pulls", [subject, IMAGE])
        p.expect_contains(
            p.last_stderr + p.last_stdout,
            "Pre-pulled 1 base image",
            "the bare-ref run reported the count it pulled",
        )

        if _image_present(IMAGE):
            p.ok(f"{IMAGE} is present in the local daemon after the pull")
        else:
            p.bad(
                f"{IMAGE} is absent after a run that exited 0; the subject reported "
                "success without pulling anything"
            )

        # "<ref>=<platform>".
        p.expect_exit("0", "the <ref>=<platform> form pulls", [subject, f"{IMAGE}=linux/amd64"])
        p.expect_contains(
            p.last_stderr + p.last_stdout,
            "Pre-pulled 1 base image",
            "the ref=platform run reported the count it pulled",
        )

        # Two specs in one call.
        p.expect_exit("0", "two specs in one call", [subject, IMAGE, f"{IMAGE}=linux/amd64"])
        p.expect_contains(
            p.last_stderr + p.last_stdout,
            "Pre-pulled 2 base image",
            "the two-spec run reported 2",
        )
    finally:
        if not preexisting:
            subprocess.run(
                ["docker", "image", "rm", "-f", IMAGE],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )

    return p.finish()


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--selftest":
        return proxyx.run_selftest()
    return run()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
