"""Stage 1 of feedback triage: the deterministic quarantine that runs before any model sees a report (PLAN-rdc-feedback D5, D6).

A report is attacker-controlled text. Every reporter-written field of an export item is matched against RULES, one table, in order (the instruction-to-the-model rules first, so the note names the most telling shape); the first hit moves the report to `quarantined` with the rule and the field as its `triage_note`. A quarantined report is never classified by a model and never reproduced.

The rule families are the plan's: a URL that survived the scrubber (the raw `scheme://` form, a `www.` host, a host with a path on any 2 to 24 letter TLD, so a host the scrubber already handles also screens when text survives it, a protocol-relative `//host`, and a defanged `hxxp`, `[.]` or `[:]` spelling), a shell-command shape (`curl`, `wget`, a pipe into a shell, `$(`, a backtick span, `sudo`, `rm -rf`), an instruction to the model ("ignore previous", "system prompt", "act as", "assistant:", role tags, `<|`), a base64 run over 200 characters, and a non-printing character (a control character other than tab, newline and carriage return, or a Unicode format character such as a zero-width space or a bidi override).

The `<url:host-redacted>` marker is NOT a trigger. packages/shared/src/feedback/scrub.ts writes it in place of every URL, and the account re-scrubs every field before it stores it, so the marker is the server's own text: a rule on it quarantined every real error that once held a URL and kept it from ever being classified. What the marker replaced is gone; only URL text the scrubber missed is reporter-controlled, and the url family above screens that.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

# The export fields the reporter wrote, in the order they are screened. Server-set fields (status, category, plan_ref, fixed_in, triage_note) are this pipeline's own and are not screened.
SCREENED_FIELDS = (
    "kind",
    "commandPath",
    "argv",
    "errorCode",
    "errorMessage",
    "stderrTail",
    "message",
    "os",
    "arch",
    "versions",
)

BASE64_RUN_MIN = 201
ALLOWED_CONTROLS = frozenset("\t\n\r")
NOTE_PREFIX = "stage1 quarantine"


@dataclass(frozen=True)
class Rule:
    """One quarantine rule: `name` is what the triage note records, `test` answers whether a field value matches."""

    name: str
    family: str
    test: Callable[[str], bool]


def _pattern(regex: str, flags: int = re.IGNORECASE) -> Callable[[str], bool]:
    compiled = re.compile(regex, flags)
    return lambda text: compiled.search(text) is not None


def _non_printing(text: str) -> bool:
    for ch in text:
        if ch in ALLOWED_CONTROLS:
            continue
        if unicodedata.category(ch) in ("Cc", "Cf", "Co", "Cs"):
            return True
    return False


RULES: tuple[Rule, ...] = (
    Rule(
        "inject-ignore-previous",
        "inject",
        _pattern(
            r"\b(?:ignore|disregard|forget)\s+(?:all\s+|any\s+|the\s+|your\s+)*"
            r"(?:previous|prior|above|earlier)\b"
        ),
    ),
    Rule("inject-system-prompt", "inject", _pattern(r"\bsystem\s+prompt\b")),
    Rule("inject-act-as", "inject", _pattern(r"\bact\s+as\b")),
    Rule("inject-assistant-turn", "inject", _pattern(r"\bassistant\s*:")),
    Rule(
        "inject-role-tag",
        "inject",
        _pattern(r"</?\s*(?:system|assistant|user|human|developer|tool)\s*>|\[/?INST\]|<<SYS>>"),
    ),
    Rule("inject-special-token", "inject", _pattern(r"<\|")),
    Rule("url", "url", _pattern(r"\b[a-z][a-z0-9+.-]*://\S")),
    Rule("url-www", "url", _pattern(r"\bwww\.[a-z0-9-]+\.[a-z]{2,}")),
    Rule(
        "url-host-path",
        "url",
        _pattern(r"\b(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,24}/[^\s/]"),
    ),
    Rule("url-protocol-relative", "url", _pattern(r"(?<![:\w/])//[a-z0-9-]+\.[a-z0-9-]")),
    Rule("url-defanged", "url", _pattern(r"\bhxxps?\b|\[\.\]|\[:\]")),
    Rule("shell-curl", "shell", _pattern(r"\bcurl\b")),
    Rule("shell-wget", "shell", _pattern(r"\bwget\b")),
    Rule("shell-pipe-sh", "shell", _pattern(r"\|\s*(?:sudo\s+)?(?:ba|z|da|k)?sh\b")),
    Rule("shell-subst", "shell", _pattern(r"\$\(")),
    Rule("shell-backtick", "shell", _pattern(r"`[^`\n]+`")),
    Rule("shell-sudo", "shell", _pattern(r"\bsudo\b")),
    Rule("shell-rm-rf", "shell", _pattern(r"\brm\s+-(?:[a-z]*r[a-z]*f|[a-z]*f[a-z]*r)[a-z]*\b")),
    Rule("base64-run", "encoded", _pattern(r"[A-Za-z0-9+/_-]{%d,}={0,2}" % BASE64_RUN_MIN, 0)),
    Rule("non-printing", "non-printing", _non_printing),
)

RULE_NAMES = tuple(rule.name for rule in RULES)


@dataclass(frozen=True)
class Hit:
    """The first rule a report matched and the field it matched in."""

    rule: str
    field: str

    @property
    def note(self) -> str:
        return "%s: rule %s matched field %s" % (NOTE_PREFIX, self.rule, self.field)


def _values(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list | tuple):
        for member in value:
            if isinstance(member, str):
                yield member


def screen(item: Mapping[str, Any]) -> Hit | None:
    """The first (rule, field) a report's screened fields match, in RULES order and then SCREENED_FIELDS order; None when the report is clean."""
    for rule in RULES:
        for field in SCREENED_FIELDS:
            if any(rule.test(text) for text in _values(item.get(field))):
                return Hit(rule.name, field)
    return None
