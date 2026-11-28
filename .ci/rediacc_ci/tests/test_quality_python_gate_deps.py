"""`rediacc_ci.quality.python_gate_deps`: the first-party judgement of a gate script's imports."""

from rediacc_ci.quality import python_gate_deps as g


def test_rediacc_hooks_is_first_party_only_when_the_package_exists(tmp_path, monkeypatch):
    """38a7133c.1: the substring alone no longer marks it first-party."""
    monkeypatch.setattr(g, "REPO", tmp_path)
    script = tmp_path / "check_x.py"
    script.write_text("import rediacc_hooks\n# rediacc_hooks\n", encoding="utf-8")
    assert "rediacc_hooks" in g.third_party_imports(script)
    (tmp_path / ".claude" / "rediacc_hooks").mkdir(parents=True)
    assert "rediacc_hooks" not in g.third_party_imports(script)
