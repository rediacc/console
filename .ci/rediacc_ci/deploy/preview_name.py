"""The one derivation of a preview's public name from its PR number.

`pv-<word>-<word>-<word>`: three words from `.ci/config/preview-words.txt` (2048 words, 11 bits each, 33 bits per name) chosen by HMAC-SHA256 keyed with `PREVIEW_NAME_KEY` over the decimal PR number. Nothing is stored: deploy, cleanup, the R2 channel and the sweep all call this module, and the operator runs it to look up a PR's address. Without the key a name cannot be recovered from a PR number.

    PYTHONPATH=.ci python3 -m rediacc_ci.deploy.preview_name --pr 123
    PYTHONPATH=.ci python3 -m rediacc_ci.deploy.preview_name --match pv-a-b-c-signer --open-prs 12 15 20

`--match` exit codes: 0 the worker belongs to one of the open PRs (the PR number is printed), 1 it has the preview shape but no open PR derives it (the sweep deletes it), 2 it does not have the preview shape (the sweep never touches it, checked before the key is read), 3 the key or the word list is unusable (the sweep keeps the worker).

`PREVIEW_NAME_KEY` is the base64 of 32 random bytes. A missing, empty or malformed key is refused, never defaulted.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import hmac
import os
import re
import sys
from functools import lru_cache
from pathlib import Path

WORD_COUNT = 2048
WORDS_PER_NAME = 3
PREFIX = "pv-"
KEY_ENV = "PREVIEW_NAME_KEY"
WORDS_FILE = Path(__file__).resolve().parents[2] / "config" / "preview-words.txt"
NAME_RE = re.compile(r"pv-[a-z]+-[a-z]+-[a-z]+(-signer)?")


class PreviewNameError(Exception):
    pass


@lru_cache(maxsize=1)
def load_words() -> tuple[str, ...]:
    try:
        words = tuple(WORDS_FILE.read_text(encoding="utf-8").split())
    except (OSError, UnicodeDecodeError) as exc:
        raise PreviewNameError(f"{WORDS_FILE} is unreadable: {exc}") from exc
    if len(words) != WORD_COUNT:
        raise PreviewNameError(f"{WORDS_FILE} holds {len(words)} words, expected {WORD_COUNT}")
    return words


def load_key(environ: dict[str, str] | None = None) -> bytes:
    raw = (os.environ if environ is None else environ).get(KEY_ENV, "")
    if not raw:
        raise PreviewNameError(f"{KEY_ENV} is required (base64 of 32 bytes)")
    try:
        key = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise PreviewNameError(f"{KEY_ENV} is not valid base64") from exc
    if len(key) != 32:
        raise PreviewNameError(f"{KEY_ENV} decodes to {len(key)} bytes, expected 32")
    return key


def preview_name(pr: int, key: bytes) -> str:
    if pr < 1:
        raise PreviewNameError(f"PR number must be positive, got {pr}")
    digest = hmac.new(key, str(pr).encode("ascii"), hashlib.sha256).digest()
    bits = int.from_bytes(digest[:5], "big")
    words = load_words()
    picked = [words[(bits >> (11 * i)) & (WORD_COUNT - 1)] for i in range(WORDS_PER_NAME)]
    return PREFIX + "-".join(picked)


def is_preview_worker(worker: str) -> bool:
    return NAME_RE.fullmatch(worker) is not None


def match_worker(worker: str, open_prs: list[int], key: bytes) -> int | None:
    """The open PR whose derived name is `worker` (or its `-signer` Worker), else None."""
    base = worker.removesuffix("-signer")
    for pr in open_prs:
        if preview_name(pr, key) == base:
            return pr
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="preview_name", description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--pr", type=int, help="print the preview name of this PR")
    group.add_argument(
        "--match", metavar="WORKER", help="classify a Worker name against --open-prs"
    )
    parser.add_argument(
        "--open-prs", type=int, nargs="*", default=[], help="numbers of the open PRs"
    )
    args = parser.parse_args(argv)
    if args.match is not None and not is_preview_worker(args.match):
        return 2
    try:
        key = load_key()
        if args.pr is not None:
            print(preview_name(args.pr, key))
            return 0
        pr = match_worker(args.match, args.open_prs, key)
        if pr is None:
            return 1
        print(pr)
        return 0
    except PreviewNameError as exc:
        print(f"preview_name: {exc}", file=sys.stderr)
        return 1 if args.match is None else 3


if __name__ == "__main__":
    sys.exit(main())
