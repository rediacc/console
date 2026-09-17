#!/usr/bin/env python3
"""Port of `.ci/scripts/build/canonicalise-gpg-key.sh`.

Rewrites an armored GPG private key into CANONICAL armor, in place. See the twin's own header for the incident (run 33990640584, 2026-09-05) and the structural repair this performs: a key stored as two Bitwarden fields gets welded when the halves are concatenated without a newline, producing one over-long armor line that gpg reads leniently and Go's `openpgp.ReadArmoredKeyRing`
rejects outright. Importing and re-exporting through gpg repairs every variant gpg can read.

Usage: canonicalise_gpg_key.py <key-file> [passphrase] Exit 0 the key was ALREADY canonical; the file is unchanged in substance
     10 the key was REPAIRED -- the stored value is malformed and should be
        fixed at source, not left to this script
     1  gpg could not read the key at all

PORT NOTES.

THE USAGE-ERROR TEXT DOES NOT MATCH THE TWIN BYTE FOR BYTE, and that is a
deliberate, checked call rather than an oversight. The twin's `${1:?msg}`
prints a bash-INTERNAL diagnostic that embeds the invoking script's own path and an interpreter line number (`<script>: line 43: 1: usage: ...`), which is not a thing a second language can reproduce and which a caller has no reason to depend on: `scripts/lib/shadow-gate.ts`'s `PATH_LINE`/`MARKERS` classifiers do not recognise that shape (no `:digits` immediately after `.sh`, no
`::error::`/`✗`/`ERROR:` marker), so it normalizes to CHATTER on both sides and plays no part in any recorded verdict. Exit code 1 is what is being ported.

EVERY OTHER ERROR MESSAGE IS TRANSLITERATED VERBATIM, because those ARE the finding text a reader diffs: "<path> is missing or empty", "gpg is not installed", "gpg could not import the key", "no secret key after import", "re-export produced nothing".

`GNUPGHOME` IS SET VIA A COPIED ENVIRONMENT, never a bare `{"GNUPGHOME": ...}`,
matching the twin's `GNUPGHOME="$HOME_DIR" gpg ...` prefix form, which inherits
the rest of the calling shell's environment (PATH, HOME, etc.) rather than replacing it.

THE REPAIR CHECK RUNS ON THE ORIGINAL BYTES, before the file is overwritten, matching the twin's ordering: `awk ... "$KEY_FILE"` runs before `cat "$OUT" >"$KEY_FILE"`. `_max_body_line_length` transliterates
`awk 'BEGIN{m=0} !/-----/ { if (length($0) > m) m = length($0) } END { print
m+0 }'`: skip any line containing the literal substring `-----` (awk's `/-----/`
is a substring match, not an anchored one), track the longest line among the rest, by character count. AWK's default record separator drops a final trailing newline into no extra empty record, which `str.split("\n")` does not match on its own -- a length-1 trailing empty element is trimmed to mirror it, though it is inert here either way since an empty string never becomes the max.

`_fpr_from_colons` transliterates `awk -F: '$1=="fpr"{print $10; exit}'`
against `gpg --list-secret-keys --with-colons`: colon-delimited records, first line whose field 1 (0-indexed 0) is exactly `fpr`, field 10 (0-indexed 9). AWK is 1-indexed; Python's split gives 0-indexed fields, hence `fields[9]`.

GPG'S OWN OUTPUT NEVER REACHES EITHER STREAM ON THE SUCCESS PATH, matching the twin's `2>/dev/null` on every gpg invocation and its stdout never being inherited (import's stdout is not redirected in the twin, but gpg 2.4 writes its own progress there almost never -- the status lines observed in manual testing all landed on stderr, which both the twin and this port discard). Nothing
here relies on that being true; it is recorded because it is what makes the byte-identical, empty-both-streams success case documented in `rediacc_ci.quality.release_key_canonical`'s own header possible.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile


def _fpr_from_colons(colon_output: str) -> str:
    """First `--with-colons` record whose field 1 is `fpr`, field 10 (1-indexed)."""
    for line in colon_output.splitlines():
        fields = line.split(":")
        if fields and fields[0] == "fpr" and len(fields) > 9:
            return fields[9]
    return ""


def _max_body_line_length(key_file: pathlib.Path) -> int:
    """`awk 'BEGIN{m=0} !/-----/ { if (length($0) > m) m = length($0) } END { print m+0 }'`."""
    text = key_file.read_bytes().decode("utf-8", errors="surrogateescape")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    m = 0
    for line in lines:
        if "-----" in line:
            continue
        m = max(m, len(line))
    return m


def main(argv: list[str]) -> int:
    if not argv or argv[0] == "":
        print(
            "canonicalise-gpg-key: usage: canonicalise-gpg-key.sh <key-file> [passphrase]",
            file=sys.stderr,
        )
        return 1

    key_file = pathlib.Path(argv[0])
    passphrase = argv[1] if len(argv) > 1 else ""

    if not key_file.is_file() or key_file.stat().st_size == 0:
        print(f"canonicalise-gpg-key: {key_file} is missing or empty", file=sys.stderr)
        return 1

    if shutil.which("gpg") is None:
        print("canonicalise-gpg-key: gpg is not installed", file=sys.stderr)
        return 1

    home_dir = tempfile.mkdtemp()
    try:
        os.chmod(home_dir, 0o700)
        env = dict(os.environ)
        env["GNUPGHOME"] = home_dir

        imported = subprocess.run(
            [
                "gpg",
                "--batch",
                "--pinentry-mode",
                "loopback",
                "--passphrase",
                passphrase,
                "--import",
                str(key_file),
            ],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if imported.returncode != 0:
            print("canonicalise-gpg-key: gpg could not import the key", file=sys.stderr)
            return 1

        listed = subprocess.run(
            ["gpg", "--list-secret-keys", "--with-colons"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            text=True,
        )
        fpr = _fpr_from_colons(listed.stdout or "")
        if not fpr:
            print("canonicalise-gpg-key: no secret key after import", file=sys.stderr)
            return 1

        out_path = pathlib.Path(home_dir) / "canonical.asc"
        with open(out_path, "wb") as out_fh:
            exported = subprocess.run(
                [
                    "gpg",
                    "--batch",
                    "--pinentry-mode",
                    "loopback",
                    "--passphrase",
                    passphrase,
                    "--armor",
                    "--export-secret-keys",
                    fpr,
                ],
                env=env,
                stdout=out_fh,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        if exported.returncode != 0 or not out_path.is_file() or out_path.stat().st_size == 0:
            print("canonicalise-gpg-key: re-export produced nothing", file=sys.stderr)
            return 1

        # JUDGE THE INPUT, NOT A DIFF AGAINST THE OUTPUT -- see the twin's own comment. gpg re-encrypts with fresh salt on every export, so the body differs every time even for a canonical key; the weld leaves a structural signature (one armor line over 64 columns) instead.
        repaired = _max_body_line_length(key_file) > 64

        shutil.copyfile(out_path, key_file)
    finally:
        shutil.rmtree(home_dir, ignore_errors=True)

    return 10 if repaired else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
