"""Credential headers reach `curl` on STDIN, as a `-K -` config, and never on argv.

Every argument of every process on a host is readable through `ps` and `/proc/<pid>/cmdline` for as long as the process lives. A `curl -H "Authorization: Bearer <token>"` therefore publishes the token for the length of the request, and the twins these ports came from built every Cloudflare call that way (worklist #a2d19f74).

`stdin_headers` takes the argv a port already builds, and pins in its tests, and returns the argv curl is really started with: each header whose NAME is in `CREDENTIAL_HEADERS` is removed in every spelling curl reads (`-H v`, `--header v`, `-Hv`, `--header=v`, and a cluster of no-argument flags ending in `H`), and an argv still holding credential text in any other spelling is refused, one `-K -` takes the place of the first of them, and the removed headers come back as curl config text for the child's stdin. A call that carries no such header is returned unchanged with no config, so it keeps whatever stdin it had.

`argv_with_config` is the inverse, the argv curl acts on once it has read the config. The recording fake `curl` of each differential applies it, so the recorded request is the twin's request and the frozen goldens keep their meaning.

A caller that already feeds curl's stdin (`--data @-`, `-T -`) AND carries a credential header cannot use this: there is one stdin. `stdin_headers` refuses such an argv rather than letting the body and the config collide; one without a credential header is returned as it is.
"""

from __future__ import annotations

import itertools
import re

CREDENTIAL_HEADERS = frozenset({"authorization", "x-auth-key", "x-auth-email"})
STDIN_CONFIG = ("-K", "-")
_STDIN_READERS = ("@-", "-")
_ESCAPES = {"\\": "\\\\", '"': '\\"', "\n": "\\n", "\r": "\\r", "\t": "\\t", "\v": "\\v"}
_UNESCAPES = {"\\": "\\", '"': '"', "n": "\n", "r": "\r", "t": "\t", "v": "\v"}


def _is_credential(header: str) -> bool:
    return header.split(":", 1)[0].strip().lower() in CREDENTIAL_HEADERS


# curl's short options that take no argument, so a cluster of them may end in `H` (`-sH v`, `-vsHv`); an argument-taking letter before `H` makes the rest its value, which the fail-closed check below catches.
_NO_ARG_SHORT = frozenset("sSvfLkiIgGNqZ#0123456:")
CREDENTIAL_TEXT = re.compile(r"(?i)(?:authorization|x-auth-key|x-auth-email)\s*:")


def _short_cluster_header(arg: str) -> str | None:
    """For a short-option cluster ending in or holding `H` (`-H`, `-sH`, `-Hv`, `-vHv`), the attached header text ("" when the value is the next word); None for anything else."""
    if not arg.startswith("-") or arg.startswith("--") or "H" not in arg[1:]:
        return None
    head = arg[1 : arg.index("H")]
    if any(ch not in _NO_ARG_SHORT for ch in head):
        return None
    return arg[arg.index("H") + 1 :]


def _quoted(value: str) -> str:
    return '"%s"' % "".join(_ESCAPES.get(ch, ch) for ch in value)


def stdin_headers(argv: list[str]) -> tuple[list[str], str | None]:
    """(argv without credential headers, the curl config carrying them), or (argv, None) when it carries none, stdin untouched. ValueError when the argv carries a credential header AND already reads curl's stdin (review 6d354ee8.1: an argv with no credential needs no config, so its stdin use is no conflict). Every spelling curl takes a header in is read: `-H v`, `--header v`, `-Hv` and `--header=v` (review 6d354ee8.2)."""
    out: list[str] = []
    lines: list[str] = []

    def take(header: str) -> None:
        if not lines:
            out.extend(STDIN_CONFIG)
        lines.append("header = %s\n" % _quoted(header))

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("-H", "--header") and i + 1 < len(argv) and _is_credential(argv[i + 1]):
            take(argv[i + 1])
            i += 2
            continue
        cluster = _short_cluster_header(arg)
        if cluster is not None:
            if cluster == "" and i + 1 < len(argv) and _is_credential(argv[i + 1]):
                if arg.index("H") > 1:
                    out.append(arg[: arg.index("H")])
                take(argv[i + 1])
                i += 2
                continue
            if cluster and _is_credential(cluster):
                if arg.index("H") > 1:
                    out.append(arg[: arg.index("H")])
                take(cluster)
                i += 1
                continue
        attached = arg[len("--header=") :] if arg.startswith("--header=") else None
        if attached is not None and _is_credential(attached):
            take(attached)
            i += 1
            continue
        out.append(arg)
        i += 1
    # FAIL CLOSED (review 9b39fee1.1): a credential header left anywhere on argv, in a spelling the walk above does not read, is refused rather than started.
    for arg in out:
        if CREDENTIAL_TEXT.search(arg):
            raise ValueError(
                "a credential header is still on curl's argv in an unrecognised spelling; pass it as -H <header>"
            )
    if not lines:
        return list(argv), None
    for flag, value in itertools.pairwise(argv):
        if flag in ("--data", "--data-binary", "--data-raw", "-d", "-T", "-K", "--config") and (
            value in _STDIN_READERS
        ):
            raise ValueError(
                "curl already reads stdin through %s; no room for a -K - config" % flag
            )
    return out, "".join(lines)


def _unquoted(text: str) -> str:
    if not (len(text) >= 2 and text[0] == '"' and text[-1] == '"'):
        return text
    body, out, i = text[1:-1], [], 0
    while i < len(body):
        if body[i] == "\\" and i + 1 < len(body):
            out.append(_UNESCAPES.get(body[i + 1], body[i + 1]))
            i += 2
            continue
        out.append(body[i])
        i += 1
    return "".join(out)


def argv_with_config(argv: list[str], stdin: str) -> list[str]:
    """The argv `stdin_headers` started from: the `header = "..."` lines of `stdin` spliced back as `-H` pairs where `-K -` stands. An argv without `-K -` is returned unchanged."""
    for i in range(len(argv) - 1):
        if (argv[i], argv[i + 1]) == STDIN_CONFIG:
            headers: list[str] = []
            for line in stdin.splitlines():
                name, sep, value = line.partition("=")
                if sep and name.strip() == "header":
                    headers += ["-H", _unquoted(value.strip())]
            return [*argv[:i], *headers, *argv[i + 2 :]]
    return list(argv)
