"""`rediacc_ci.core.xml_trusted`: the one XML parse site, and what it is trusted for."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from rediacc_ci.core import xml_trusted

JUNIT = '<testsuites><testsuite name="s" tests="2"><testcase name="a"/><testcase name="b"/></testsuite></testsuites>'


def test_fromstring_returns_the_root_for_text_and_for_bytes():
    assert xml_trusted.fromstring(JUNIT).tag == "testsuites"
    assert len(xml_trusted.fromstring(JUNIT.encode()).findall(".//testcase")) == 2


def test_parse_returns_the_root_of_a_file(tmp_path):
    path = tmp_path / "junit.xml"
    path.write_text(JUNIT, encoding="utf-8")
    suite = xml_trusted.parse(path).find("testsuite")
    assert suite is not None
    assert suite.get("name") == "s"


def test_malformed_input_raises_the_parse_error_the_callers_catch(tmp_path):
    path = tmp_path / "bad.xml"
    path.write_text("<a><b></a>", encoding="utf-8")
    with pytest.raises(ET.ParseError):
        xml_trusted.fromstring("<a><b></a>")
    with pytest.raises(ET.ParseError):
        xml_trusted.parse(path)
