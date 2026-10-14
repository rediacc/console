"""The one place `.ci` parses XML with the standard library, and what that is trusted for.

ruff's S314 reports every `xml.etree.ElementTree` parse, because the module expands internal entities and so a hostile document can balloon. It expands no external entities and fetches nothing. Every caller here parses a document it has just verified or produced itself: a junit file written by pytest or gotestsum in this repository's own CI (a moment earlier, or an earlier run's unit-duration artifact that `budget_report.parse_gotestsum_junit_unit_ms` downloads, only from runs built from a branch of this repository: `budget_report.from_this_repo` drops a fork's pull-request run, including one whose fork is deleted, before any artifact is fetched), and the RPM repo metadata after its signature or checksum was checked. A parse of input from anyone else does not belong here.

`fromstring` and `parse` are the funnel: S314 is per-file-ignored for this module only (pyproject.toml), so a new `ET.fromstring` elsewhere is reported and sent here, where the trust boundary is written down.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import os


def fromstring(text: str | bytes) -> ET.Element:
    """The root element of a trusted document held in memory."""
    return ET.fromstring(text)


def parse(path: str | os.PathLike[str]) -> ET.Element:
    """The root element of a trusted document on disk."""
    return ET.parse(path).getroot()
