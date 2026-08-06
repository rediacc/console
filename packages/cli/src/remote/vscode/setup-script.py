"""Prepare a remote machine's VS Code Server environment.

Executed on the REMOTE host over SSH by
packages/cli/src/remote/vscode/bootstrap.ts, which embeds this file's text at
bundle time (esbuild `loader: {".py": "text"}`) and runs it as
`python3 -c <this source> <config-json>`.

WHY THIS IS A FILE AND NOT A TEMPLATE LITERAL. It used to be 130 lines of
Python inside a TypeScript backtick string, where no linter, formatter or type
checker could see it, and it stayed that way long enough to grow a
code-injection hole: four of the six values interpolated into it went in
unescaped, so a UNIVERSAL_USER of `\'; import os; os.system(\'id\'); x=\'`
parsed cleanly and executed -- on a remote host, under `sudo -u` on the
user-switch path.

The fix is not better escaping. There is NO interpolation into this file at
all: every value arrives as JSON in argv[1], so the only quoting left is
shell-quoting a single opaque argument. A value can no longer become code.
"""

import contextlib
import json
import os
import pathlib
import pwd
import sys

_CONFIG = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
ENV_BLOCK = _CONFIG["envBlock"]
BASH_FUNCTIONS = _CONFIG["bashFunctions"]
UNIVERSAL_USER = _CONFIG["universalUser"]
SERVER_INSTALL_PATH = _CONFIG["serverInstallPath"]
MARKER_START = _CONFIG["markerStart"]
MARKER_END = _CONFIG["markerEnd"]


def get_uid_gid(username):
    """Get UID and GID for a username"""
    try:
        pw = pwd.getpwnam(username)
        return pw.pw_uid, pw.pw_gid
    except KeyError:
        return None, None


def safe_chown(path, uid, gid):
    """chown that gracefully degrades when running without root (e.g., inside sandbox)"""
    with contextlib.suppress(OSError):
        os.chown(path, uid, gid)


def ensure_dir(path, mode=0o755, uid=None, gid=None):
    """Create directory with proper permissions and ownership"""
    path = pathlib.Path(path)
    if not path.exists():
        path.mkdir(parents=True, mode=mode)
    if uid is not None and gid is not None:
        safe_chown(path, uid, gid)


def write_file_atomic(path, content, mode=0o644, uid=None, gid=None):
    """Write file atomically with proper permissions"""
    path = pathlib.Path(path)
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(content)
    os.chmod(temp_path, mode)
    if uid is not None and gid is not None:
        safe_chown(temp_path, uid, gid)
    temp_path.rename(path)


def update_managed_content(path, new_content, mode=0o644, uid=None, gid=None):
    """Update managed section in a file, preserving other content"""
    path = pathlib.Path(path)

    existing = ""
    if path.exists():
        existing = path.read_text()

    # Check for existing managed section
    start_idx = existing.find(MARKER_START)
    end_idx = existing.find(MARKER_END)

    managed_block = f"{MARKER_START}\n{new_content}\n{MARKER_END}"

    if start_idx != -1 and end_idx != -1:
        # Replace existing managed section
        new_content_full = (
            existing[:start_idx] + managed_block + existing[end_idx + len(MARKER_END) :]
        )
    else:
        # Append managed section
        new_content_full = (
            existing.rstrip() + "\n\n" + managed_block + "\n" if existing else managed_block + "\n"
        )

    write_file_atomic(path, new_content_full, mode, uid, gid)


def main():
    uid, gid = get_uid_gid(UNIVERSAL_USER)

    # Setup directory: ~/.vscode-server or {server_install_path}/.vscode-server
    if SERVER_INSTALL_PATH:
        setup_dir = pathlib.Path(SERVER_INSTALL_PATH) / ".vscode-server"
    else:
        setup_dir = pathlib.Path.home() / ".vscode-server"

    # Create directory structure
    ensure_dir(setup_dir, 0o775, uid, gid)

    # Write bash helper functions alongside env file (shared content with rdc term)
    bash_funcs_file = setup_dir / "bashrc-rediacc"
    write_file_atomic(bash_funcs_file, BASH_FUNCTIONS + "\n", 0o644, uid, gid)

    # Write environment file (includes sourcing bash functions)
    env_content = (
        ENV_BLOCK
        + f'\n\n# Source bash helper functions\nsource "{bash_funcs_file}" 2>/dev/null || true\n'
    )
    env_file = setup_dir / "rediacc-env.sh"
    write_file_atomic(env_file, env_content, 0o644, uid, gid)

    # Write server-env-setup file (sourced by VS Code)
    setup_file = setup_dir / "server-env-setup"
    setup_content = f'source "{env_file}"'
    update_managed_content(setup_file, setup_content, 0o644, uid, gid)

    # Write terminal init script (sourced via --rcfile so PS1 isn't overridden)
    # --rcfile replaces ~/.bashrc, so we source it explicitly after our env setup
    terminal_init = setup_dir / "terminal-init.sh"
    init_content = f'source /etc/bash.bashrc 2>/dev/null\nsource "{env_file}" 2>/dev/null\nsource ~/.bashrc 2>/dev/null\n'
    write_file_atomic(terminal_init, init_content, 0o644, uid, gid)

    # Write Machine settings to force /bin/bash with our init as default shell
    # --rcfile replaces the default ~/.bashrc sourcing, so we source /etc/bash.bashrc
    # ourselves followed by rediacc-env.sh (which includes PS1 and helper functions)
    data_dir = setup_dir / "data"
    machine_dir = data_dir / "Machine"
    ensure_dir(data_dir, 0o775, uid, gid)
    ensure_dir(machine_dir, 0o775, uid, gid)

    settings_file = machine_dir / "settings.json"
    machine_settings = {}
    if settings_file.exists():
        # OSError: unreadable. ValueError: not JSON (UnicodeDecodeError is a
        # subclass). Either way the file is replaced; anything else is a defect
        # here and must not be swallowed.
        with contextlib.suppress(OSError, ValueError):
            machine_settings = json.loads(settings_file.read_text())
    machine_settings["terminal.integrated.defaultProfile.linux"] = "bash"
    machine_settings["terminal.integrated.profiles.linux"] = {
        "bash": {"path": "/bin/bash", "args": ["--rcfile", str(terminal_init)]}
    }
    write_file_atomic(settings_file, json.dumps(machine_settings, indent=2) + "\n", 0o644, uid, gid)

    print(f"Environment setup complete: {env_file}")


if __name__ == "__main__":
    main()
