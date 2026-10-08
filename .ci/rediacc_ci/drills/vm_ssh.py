"""How a drill reaches an ops VM over ssh: the user the fleet provisions, the one key it authorizes, and no fallback to any other identity.

THE USER. `renet ops up` creates the VM account named by `VMUser()` (private/renet/pkg/infra/opsconfig/config.go), which is the operator's `$USER`. A hardcoded account name works only on the one host whose operator happens to carry it.

THE KEY. The VMs authorize the key `renet ops` itself provisions them with: `id_rsa` under the renet staging folder (rooted at RENET_DATA_DIR or ~/.renet), NOT ~/.ssh/id_ed25519. A plain `ssh` still connects with the wrong `-i`, because OpenSSH falls through to the agent, ~/.ssh/config and its default identities after the named key is refused, while the CLI (ssh2, one explicit key) fails with "All configured authentication methods failed". `-F /dev/null`, `IdentitiesOnly` and `IdentityAgent=none` close that fallthrough, so a drill's own ssh connects with exactly the key it hands the CLI.

THE EXIT CODE. ssh exits 255 when the connection or the authentication failed, and with the remote command's status otherwise. A caller that reads "non-zero" as "the remote probe said no" turns an auth refusal into a false statement about the machine; `SSH_FAILED` is the code to tell the two apart.
"""

from __future__ import annotations

import getpass
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

SSH_FAILED = 255


def default_user(environ: Mapping[str, str] | None = None) -> str:
    """`SSH_USER`, else `$USER` (what `VMUser()` provisions), else the login name."""
    env = os.environ if environ is None else environ
    return env.get("SSH_USER") or env.get("USER") or getpass.getuser()


def default_key(environ: Mapping[str, str] | None = None) -> str:
    """`SSH_KEY`, else `<RENET_DATA_DIR or ~/.renet>/staging/.ssh/id_rsa`."""
    env = os.environ if environ is None else environ
    renet_data = env.get("RENET_DATA_DIR") or os.path.join(env.get("HOME", "~"), ".renet")
    return env.get("SSH_KEY") or os.path.join(renet_data, "staging", ".ssh", "id_rsa")


def ssh_argv(user: str, key: str, host: str, command: str) -> list[str]:
    """`ssh` with EXACTLY one identity and no host-key bookkeeping (the VMs are recreated freely)."""
    return [
        "ssh",
        "-F",
        "/dev/null",
        "-i",
        key,
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "IdentityAgent=none",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "LogLevel=ERROR",
        "%s@%s" % (user, host),
        command,
    ]
