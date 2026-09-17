"""What THIS bash says when it complains, asked rather than assumed.

WHY THIS EXISTS. Bash 5.3 reworded several diagnostics that ported modules and their tests reproduce as string literals. Measured 2026-09-15 by running both bashes, not by reading a changelog:

    bash 5.3.9(1)   [[: 1 2: arithmetic syntax error in expression (error token is "2")
    bash 5.2.21(1)  [[: 1 2: syntax error in expression (error token is "2")

    bash 5.3.9(1)   ((: 1;ls: arithmetic syntax error: invalid arithmetic operator (error token is ";ls")
    bash 5.2.21(1)  ((: 1;ls: syntax error: invalid arithmetic operator (error token is ";ls")

    bash 5.3.9(1)   ((: + : arithmetic syntax error: operand expected (error token is "+ ")
    bash 5.2.21(1)  ((: + : syntax error: operand expected (error token is "+ ")

    bash 5.3.9(1)   [: abc: integer expected
    bash 5.2.21(1)  [: abc: integer expression expected

    bash 5.3.9(1)   cd "" -> cd: null directory
    bash 5.2.37(1)  cd "" -> (silence; the empty argument is simply accepted)

THREE independent changes: a uniform `arithmetic ` prefix on all three arithmetic shapes, `[`'s integer complaint losing the word `expression`, and `cd ""` going from silent to refused. The third is the odd one out and the reason this module returns a STRING rather than a flag -- on 5.2 the honest answer is the empty string, so a caller can append it unconditionally.

HOW IT HID FOR 53 WAVES. Every port here is verified against its bash twin by a differential test asserting the two produce the same bytes. Both sides run on the same host, so a literal baked into the port agrees with the twin **on the machine that wrote it** and disagrees nowhere a developer can see. This tree's
hosts run bash 5.3; every GitHub runner is ubuntu-24.04, which is bash 5.2. The
divergence was therefore invisible locally by construction and unreachable in CI, because `quality-security` -- the only lane that runs this suite -- had been watchdog-cancelled on every run of the wave. It surfaced in run 34970782616, the first that ever let that lane finish, as fourteen failures.

WHY IT PROBES INSTEAD OF COMPARING VERSION NUMBERS. `BASH_VERSINFO >= (5, 3)`
would be a claim about where the boundary is, inferred from two measurements at 5.2.21 and 5.3.9 and blind to a distro that backports the strings without the version. Asking bash what it actually prints cannot be wrong about that, costs one subprocess per process, and is the same move the rest of this campaign makes: run the thing that decides.

WHICH BASH. The one on PATH -- the same resolution the twins get when a test runs `bash <script>`, and the same one `differential.bash_streams` uses. Callers inside a differential that stubs PATH should pass that env through, so the port
is told about the bash the twin will really run; `env=None` means the ambient
one.

IF THE PROBE CANNOT RUN it returns the 5.3 spellings, which is what every call site hardcoded before this module existed. A missing bash therefore changes nothing rather than silently rewording every diagnostic in the tree.
"""

from __future__ import annotations

import functools
import subprocess

# Every diagnostic from ONE bash, so a single probe answers all of them and a host cannot be seen half-5.2 and half-5.3. `[[ ]]` yields the arithmetic shape,
# `[` the integer one, and `cd ""` the null-directory one; none writes to stdout,
# and `cd ""` does not move the shell (it is refused on 5.3 and a no-op on 5.2).
_PROBE = '[[ "1 2" -gt 0 ]]; [ abc -gt 1 ]; cd ""; read -r _bd < /'

_ARITH_53 = "arithmetic syntax error"
_ARITH_52 = "syntax error"
_INTEGER_53 = "integer expected"
_INTEGER_52 = "integer expression expected"
# 5.3 REFUSES `cd ""` OUT LOUD; 5.2 says nothing at all, so the 5.2 answer is the
# empty string rather than a different wording. A caller that appends this to an expected stderr therefore appends nothing on 5.2, which is correct.
_CD_NULL_53 = "cd: null directory"
# The `read` builtin names the failing FD, and 5.3 MOVED it: 5.3.9 read: 0: read error: Is a directory 5.2.37 read: read error: 0: Is a directory A word ORDER change, not a rewording, so it cannot be expressed as a swappable noun the way the pairs above can.
_READ_FD_AFTER_REASON = "read error: 0:"  # the 5.2 shape, as the probe emits it


def _probe(env: dict[str, str] | None) -> tuple[str, str, str, bool]:
    try:
        proc = subprocess.run(
            ["bash", "-c", _PROBE],
            capture_output=True,
            text=True,
            env=env,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return _ARITH_53, _INTEGER_53, _CD_NULL_53, True
    err = proc.stderr
    # SUBSTRING ORDER MATTERS, and only in this direction: `syntax error` is a substring of `arithmetic syntax error`, so asking for the SHORT spelling first would call every 5.3 host a 5.2 host. Ask for the long one, and treat "neither appeared" as 5.3, which is what every call site hardcoded before this module existed.
    arith = _ARITH_53 if _ARITH_53 in err else (_ARITH_52 if _ARITH_52 in err else _ARITH_53)
    # The integer pair has the trap the other way round -- here the 5.2 spelling is the longer one -- so the long spelling is again what gets asked first.
    integer = _INTEGER_52 if _INTEGER_52 in err else _INTEGER_53
    cd_null = _CD_NULL_53 if _CD_NULL_53 in err else ""
    read_fd_first = _READ_FD_AFTER_REASON not in err
    return arith, integer, cd_null, read_fd_first


@functools.lru_cache(maxsize=1)
def _ambient() -> tuple[str, str, str, bool]:
    """The host's own bash, probed once per process."""
    return _probe(None)


def _dialect(env: dict[str, str] | None) -> tuple[str, str, str, bool]:
    # A caller that named an env is asking about THAT bash, so it neither reads nor writes the ambient cache.
    return _probe(env) if env is not None else _ambient()


def arith_syntax_error(env: dict[str, str] | None = None) -> str:
    """`arithmetic syntax error` on bash 5.3+, `syntax error` before it.

    The whole leading clause, not a prefix to glue on, so a call site reads as the sentence bash prints:

        '%s in expression (error token is "%s")' % (arith_syntax_error(), token)
        '%s: invalid arithmetic operator (error token is "%s")' % (arith_syntax_error(), token)
        '%s: operand expected (error token is "%s")' % (arith_syntax_error(), token)
    """
    return _dialect(env)[0]


def integer_expected(env: dict[str, str] | None = None) -> str:
    """`integer expected` on bash 5.3+, `integer expression expected` before it.

    What `[ abc -gt 1 ]` prints after `[: abc: `.
    """
    return _dialect(env)[1]


def cd_null_directory(env: dict[str, str] | None = None) -> str:
    """What bash says about `cd ""` -- `cd: null directory` on 5.3+, NOTHING before.

    The empty string is the real 5.2 answer, not a placeholder: that bash accepts `cd ""` silently. A caller building an expected stderr can append this unconditionally and get the right bytes on either.
    """
    return _dialect(env)[2]


def read_error(fd: str, reason: str, env: dict[str, str] | None = None) -> str:
    """The `read` builtin's failure line, in THIS bash's word order.

        bash 5.3.9   read: 0: read error: Is a directory
        bash 5.2.37  read: read error: 0: Is a directory

    The file descriptor moved from AFTER the phrase to BEFORE it, so unlike the other entries here this one cannot be handled by swapping a noun -- the caller has to be handed the whole assembled line.
    """
    if _dialect(env)[3]:
        return "read: %s: read error: %s" % (fd, reason)
    return "read: read error: %s: %s" % (fd, reason)


def reset_cache() -> None:
    """Forget the probed answer. For tests that fake a bash; nothing else."""
    _ambient.cache_clear()
