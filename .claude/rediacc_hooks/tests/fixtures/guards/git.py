"""The one `git` helper for the guard fixture builders."""

import subprocess


def fixture_git(cwd, *args, date=None):
    """`git` for the fixture builders, with the ambient config shut out; returns stdout, stripped.

    GIT_CONFIG_GLOBAL and GIT_CONFIG_SYSTEM point at /dev/null so a host `commit.gpgsign` or `core.hooksPath` cannot reach a tree that is meant to be a controlled world. `date` pins both commit dates, which makes every fixture commit id the same on every run, for a table whose refusal names one.
    """
    env = {
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "HOME": "/nonexistent",
        "GIT_AUTHOR_NAME": "Fixture",
        "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
        "GIT_COMMITTER_NAME": "Fixture",
        "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
    }
    if date is not None:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
    done = subprocess.run(
        ["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True, env=env
    )
    return done.stdout.strip()
