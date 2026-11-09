"""The Enterprise leak gate (rediacc_ci.quality.enterprise_leak) and the masking of the two public Cloudflare reports. Every check is driven in both directions: a plant that must fire and a twin that must stay quiet."""

from __future__ import annotations

import io
import json
import pathlib
import subprocess
import time

import pytest

from rediacc_ci import paths
from rediacc_ci.controls import fixture_git_env
from rediacc_ci.enterprise import names
from rediacc_ci.housekeeping import cf_leftovers as cfl
from rediacc_ci.ops import cf_usage_report as ur
from rediacc_ci.quality import enterprise_leak as leak
from rediacc_ci.tests import test_ops_cf_usage_report as usage_base
from rediacc_ci.tests.test_housekeeping_cf_leftovers import fake_api
from rediacc_ci.well_known import PRODUCT_DOMAIN

PUBLIC = names.reserved() | leak.FAKE_LABELS
# Company labels for the plants. Fictional on purpose; the plan's own fake, `acme`, is the name that must pass.
CO = "globex"
CO2 = "initech"


@pytest.fixture
def tree(tmp_path):
    env = leak._fixture(tmp_path, PRODUCT_DOMAIN)
    return tmp_path, env


def _scan(root, env, labels_env=None):
    return leak.scan(root, PUBLIC, labels_env or {}, PRODUCT_DOMAIN, env)


def _rules(findings, rule):
    return [f for f in findings if f.rule == rule]


def test_selftest_controls_hold():
    assert leak.main(["--selftest"]) == 0


def test_an_unknown_argument_is_exit_2(capsys):
    assert leak.main(["--bogus"]) == 2
    assert "usage" in capsys.readouterr().err


def test_a_tracked_company_toml_fires_and_the_template_does_not():
    found = leak.generated_toml_findings(
        [
            "workers/account/enterprise.template.toml",
            "workers/proxy/enterprise.%s.toml" % CO,
            "workers/account/wrangler.eu.toml",
            "docs/enterprise.md",
        ]
    )
    assert [f.path for f in found] == ["workers/proxy/enterprise.%s.toml" % CO]
    assert "git rm --cached" in found[0].fix


def test_store_names_shared_pass_opaque_and_named_fire(tree):
    root, env = tree
    findings, shape = _scan(root, env)
    stores = _rules(findings, "store-name")
    whats = " ".join(f.what for f in stores)
    assert len(stores) == 2
    assert "shared project's public record" in whats  # c0123abcd4567_ACCOUNT_JWT_SECRET
    assert "'%s-jwt' is neither" % CO in whats
    assert "'ACCOUNT_JWT_SECRET'" not in whats
    assert all(f.path == ".ci/config/bws-secret-map.json" for f in stores)
    assert shape.store_names == 8


def test_store_names_read_every_spelling_of_secret_supply(tmp_path):
    (tmp_path / ".ci/config").mkdir(parents=True)
    (tmp_path / ".ci/config/bws-secret-map.json").write_text(json.dumps({"secrets": {"A": {}}}))
    (tmp_path / ".ci/config/secret-supply.json").write_text(
        json.dumps(
            {
                "bootstrap_names": ["B"],
                "residue": {"C": {"alias_of": "D"}},
                "consumers": {"p": {"required": ["E > LOCAL_E"], "optional": ["F"]}},
                "dotenv": {"names": {"G": "x"}, "aliases": {"H": "I > H"}},
            }
        )
    )
    got = sorted(n for _, n in leak.store_names(tmp_path))
    assert got == ["A", "B", "C", "D", "E", "F", "G", "H", "I"]


def test_a_missing_secret_record_is_a_setup_error(tmp_path):
    with pytest.raises(leak.LeakSetupError, match=r"bws-secret-map\.json"):
        leak.store_names(tmp_path)


def test_zero_store_names_is_a_refusal_not_a_pass(tree):
    root, env = tree
    (root / ".ci/config/bws-secret-map.json").write_text(json.dumps({"secrets": {}}))
    (root / ".ci/config/secret-supply.json").write_text("{}")
    with pytest.raises(leak.LeakSetupError, match="zero store names"):
        _scan(root, env)


def test_zero_tracked_files_is_a_refusal_not_a_pass(tmp_path):
    env = fixture_git_env()
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True, env=env)
    with pytest.raises(leak.LeakSetupError, match="zero tracked files"):
        leak.scan(tmp_path, PUBLIC, {}, PRODUCT_DOMAIN, env)


def test_product_hosts_company_fires_regions_fake_and_placeholder_do_not(tree):
    root, env = tree
    findings, shape = _scan(root, env)
    hosts = _rules(findings, "product-host")
    assert sorted(f.what.split(" ")[0] for f in hosts) == sorted(
        ["%s.%s" % (CO, PRODUCT_DOMAIN), "%s-proxy.%s" % (CO2, PRODUCT_DOMAIN)]
    )
    assert {f.line for f in hosts} == {4, 5}
    assert shape.hosts == 6  # eu, us, acme, acme-proxy and the two plants
    assert shape.host_files == 1


def test_an_untracked_file_is_not_scanned(tree):
    root, env = tree
    (root / "draft.md").write_text("%s.%s\n" % ("hooli", PRODUCT_DOMAIN))
    findings, _ = _scan(root, env)
    assert not any(f.path == "draft.md" for f in findings)


def test_label_grammar_and_proxy_suffix():
    assert leak.label_is_public("eu", PUBLIC)
    assert leak.label_is_public("acme-proxy", PUBLIC)
    assert not leak.label_is_public(CO, PUBLIC)
    assert not leak.label_is_public(CO + "-proxy", PUBLIC)
    pat = leak.host_re(PRODUCT_DOMAIN)
    assert [m.group(1) for m in pat.finditer("proxy.eu.%s" % PRODUCT_DOMAIN)] == ["proxy.eu"]
    assert not list(pat.finditer("<company>.%s and _psl.%s" % (PRODUCT_DOMAIN, PRODUCT_DOMAIN)))


def test_a_company_label_behind_a_public_one_is_found_and_masked(tmp_path):
    (tmp_path / "doc.md").write_text("see %s.eu.%s here\n" % (CO, PRODUCT_DOMAIN))
    shape = leak.Shape()
    found = leak.host_findings(tmp_path, ["doc.md"], PUBLIC, PRODUCT_DOMAIN, shape)
    assert len(found) == 1
    assert "'%s'" % CO in found[0].what
    masked = leak.Masker(PUBLIC, frozenset(), PRODUCT_DOMAIN).mask(
        "%s.eu.%s and proxy.eu.%s" % (CO, PRODUCT_DOMAIN, PRODUCT_DOMAIN)
    )
    assert CO not in masked
    assert masked == "<company-1>.eu.%s and proxy.eu.%s" % (PRODUCT_DOMAIN, PRODUCT_DOMAIN)


def test_an_oversized_or_binary_file_is_counted_as_not_scanned(tmp_path, monkeypatch):
    monkeypatch.setattr(leak, "MAX_SCAN_BYTES", 16)
    (tmp_path / "big.txt").write_text("x" * 64)
    (tmp_path / "bin.dat").write_bytes(b"a\0b")
    (tmp_path / "ok.txt").write_text("fine")
    shape = leak.Shape()
    leak.host_findings(
        tmp_path, ["big.txt", "bin.dat", "ok.txt", "gone.txt"], PUBLIC, PRODUCT_DOMAIN, shape
    )
    assert shape.skipped == 2
    assert "2 tracked file(s) not scanned" in shape.render()


def test_a_company_worker_name_in_a_tracked_worker_toml_fires_and_a_public_one_does_not(tmp_path):
    (tmp_path / "workers" / "account").mkdir(parents=True)
    toml = tmp_path / "workers" / "account" / "wrangler.eu.toml"
    toml.write_text('name = "account-eu"\n[[services]]\nservice = "proxy-%s"\n' % CO)
    found = leak.worker_name_findings(tmp_path, ["workers/account/wrangler.eu.toml"], PUBLIC)
    assert [f.rule for f in found] == ["worker-name"]
    assert "proxy-%s" % CO in found[0].what
    assert found[0].line == 3


def test_a_tracked_worker_toml_that_does_not_parse_is_counted_not_scanned(tmp_path):
    (tmp_path / "workers" / "account").mkdir(parents=True)
    (tmp_path / "workers/account/broken.toml").write_text('name = "account-%s\n' % CO)
    (tmp_path / "workers/account/wrangler.template.toml").write_text('name = "@@WORKER@@"\n[')
    shape = leak.Shape()
    found = leak.worker_name_findings(
        tmp_path,
        ["workers/account/broken.toml", "workers/account/wrangler.template.toml"],
        PUBLIC,
        shape,
    )
    assert found == []
    assert shape.skipped == 1


def test_a_long_dotted_run_is_scanned_in_linear_time():
    pattern = leak.host_re(PRODUCT_DOMAIN)
    started = time.perf_counter()
    assert list(pattern.finditer("a." * 40000 + "x")) == []
    assert time.perf_counter() - started < 2.0
    # The run is still judged whole, and a leading dot still starts a match.
    hit = pattern.search("see a.b.%s.eu.%s" % (CO, PRODUCT_DOMAIN))
    assert hit is not None
    assert hit.group(1) == "a.b.%s.eu" % CO
    lead = pattern.search(" .%s.%s" % (CO, PRODUCT_DOMAIN))
    assert lead is not None
    assert lead.group(1) == CO


def test_the_verdict_names_the_scan_limit_from_the_constant(monkeypatch):
    assert "over %d MiB" % (leak.MAX_SCAN_BYTES // 2**20) in leak.Shape().render()
    monkeypatch.setattr(leak, "MAX_SCAN_BYTES", 2 * 2**20)
    assert "over 2 MiB" in leak.Shape().render()


def test_known_labels_come_from_generated_tomls_and_the_env(tree):
    root, _env = tree
    labels, sources = leak.known_labels(root, {leak.LABELS_ENV: " Hooli, acme ,bad_label"})
    assert labels == [CO, "hooli", CO2]  # acme is the fake; an invalid label is dropped
    assert "2 generated toml(s)" in sources
    assert "1 from" in sources


def test_known_labels_fire_in_company_shapes_only(tree):
    root, env = tree
    findings, shape = _scan(root, env)
    spelled = sorted(f.what.split("'")[1] for f in _rules(findings, "known-label"))
    assert spelled == sorted(
        [
            "INITECH_JWT_SECRET",
            "account-%s" % CO,
            "%s.%s" % (CO, PRODUCT_DOMAIN),
            "%s-proxy.%s" % (CO2, PRODUCT_DOMAIN),
            "proxy-%s" % CO2,
        ]
    )
    assert shape.labels == 2


def test_no_known_label_means_the_label_scan_says_so():
    shape = leak.Shape(tracked=3, store_names=4)
    assert "0 company label(s) known locally (none generated here)" in shape.render()


def test_the_real_tree_is_scanned_non_vacuously():
    findings, shape = leak.scan(paths.repo_root(), PUBLIC, {}, PRODUCT_DOMAIN)
    assert shape.tracked > 1000
    assert shape.store_names > 100
    assert shape.generated_tracked == 0
    assert not _rules(findings, "store-name"), [f.render() for f in findings]


def test_masker_tokens_are_per_label_and_public_names_pass():
    m = leak.Masker(PUBLIC, frozenset({"account-db-eu"}), PRODUCT_DOMAIN)
    assert m.mask("account-%s" % CO) == "account-<company-1>"
    assert m.mask("%s.%s/*" % (CO, PRODUCT_DOMAIN)) == "<company-1>.%s/*" % PRODUCT_DOMAIN
    assert m.mask("backups-%s" % CO2) == "backups-<company-2>"
    for public in (
        "account-eu",
        "account-db-eu",
        "proxy-bench",
        "signer-bench-us",
        "pr-7",
        "media",
    ):
        assert m.mask(public) == public
    assert m.masked == 2
    assert CO not in m.mask("script account-%s does not exist" % CO)


def test_masker_for_tree_knows_the_shared_names():
    m = leak.Masker.for_tree()
    data = json.loads((paths.repo_root() / "regions.json").read_text())
    for region in data["regions"]:
        for key in ("workerName", "proxyWorkerName"):
            assert m.mask(region[key]) == region[key]
    assert m.mask("account-%s" % CO) == "account-<company-1>"


def test_report_masker_refuses_unmasked_under_github_actions():
    masker, refusal = leak.report_masker(["--unmasked"], {"GITHUB_ACTIONS": "true"}, "x")
    assert masker is None
    assert "public" in refusal
    masker, _ = leak.report_masker(["--unmasked"], {}, "x")
    assert masker is not None
    assert not masker.enabled
    masker, refusal = leak.report_masker(["--names"], {}, "x")
    assert masker is None
    assert "takes no arguments" in refusal


# ---------------------------------------------------------------------------
# The two public reports print through the masker.
# ---------------------------------------------------------------------------


def _usage_data():
    data = json.loads(json.dumps(usage_base.DATA))
    data["r2StorageAdaptiveGroups"].append(
        {
            "dimensions": {"bucketName": "configs-%s" % CO},
            "max": {"payloadSize": 1, "metadataSize": 0, "objectCount": 1},
        }
    )
    data["workersInvocationsAdaptive"].append(
        {"dimensions": {"scriptName": "account-%s" % CO}, "sum": {"requests": 1, "cpuTimeUs": 1}}
    )
    return data


def _usage_run(masker):
    base = usage_base
    out = io.StringIO()
    rc = ur.run(
        base.ENV,
        base.Fake(data=_usage_data()),
        now=base.NOW,
        ceilings=dict.fromkeys(base.CEILINGS, 10**12) | base.CONTAINER_CEILINGS,
        out=out,
        masker=masker,
    )
    return rc, out.getvalue()


def test_usage_report_masks_a_company_bucket_and_worker():
    rc, text = _usage_run(None)
    assert rc == 0, text
    assert CO not in text
    assert "r2.bucket.configs-<company-1>.bytes" in text
    assert "workers.account-<company-1>.requests" in text
    assert "r2.bucket.b1.bytes" in text
    assert "workers.w1.requests" in text
    assert "1 company label(s) masked" in text


def test_usage_report_unmasked_shows_names_and_says_so():
    rc, text = _usage_run(leak.Masker.identity())
    assert rc == 0
    assert "configs-%s" % CO in text
    assert "(--unmasked: names shown)" in text


def test_usage_report_unmasked_is_refused_under_github_actions(monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    assert ur.main(["--unmasked"]) == 2
    assert "refused under GITHUB_ACTIONS" in capsys.readouterr().err
    assert ur.main(["--other"]) == 2


def test_usage_report_that_cannot_mask_does_not_print(monkeypatch, capsys):
    def broken(_root=None):
        raise leak.LeakSetupError("regions.json cannot be read")

    monkeypatch.setattr(leak.Masker, "for_tree", staticmethod(broken))
    rc, text = _usage_run(None)
    assert rc == 2
    assert text == ""
    assert "cannot be masked" in capsys.readouterr().err


def test_leftovers_masks_company_scripts_routes_and_says_what_they_are(monkeypatch, capsys):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    routes = [{"pattern": "%s-proxy.%s/*" % (CO, PRODUCT_DOMAIN), "script": "proxy-%s" % CO}]
    get = fake_api(["account-%s" % CO, "stray-worker"], [], routes)
    assert cfl.main([], get=get) == 0
    out = capsys.readouterr().out
    assert CO not in out
    assert "LEFTOVER script account-<company-1>" in out
    assert "company-shaped name, masked" in out
    assert "<company-1>-proxy.%s/*" % PRODUCT_DOMAIN in out
    assert "script proxy-<company-1> does not exist" in out
    assert "LEFTOVER script stray-worker" in out
    assert "1 company label(s) masked" in out
    assert cfl.main(["--unmasked"], get=get) == 0
    assert "account-%s" % CO in capsys.readouterr().out


def test_leftovers_unmasked_is_refused_under_github_actions(monkeypatch, capsys):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    assert cfl.main(["--unmasked"], get=fake_api([], [], [])) == 1
    assert "refused under GITHUB_ACTIONS" in capsys.readouterr().err


def test_the_gate_source_names_no_product_host_literally():
    """The gate and this test build every host from PRODUCT_DOMAIN, so neither can carry a planted host into the tree it scans."""
    for rel in (
        ".ci/rediacc_ci/quality/enterprise_leak.py",
        ".ci/rediacc_ci/tests/test_enterprise_leak.py",
    ):
        assert PRODUCT_DOMAIN not in pathlib.Path(paths.repo_root(), rel).read_text()
