"""enterprise.names: reserved region, service and -proxy names, derived from regions.json and well-known."""

from __future__ import annotations

import json
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.enterprise import names
from rediacc_ci.well_known import PRODUCT_DOMAIN


def test_valid_names_pass():
    for ok in ("acme", "acme-corp", "a1b", "northwind42"):
        assert names.check(ok) == ok


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "ab",
        "Acme",
        "acme_corp",
        "-acme",
        "acme-",
        "ac--me",
        "ac.me",
        "x" * 31,
        "xn--acme",
        "acme corp",
        "acme\n",
    ],
)
def test_malformed_refused(bad):
    with pytest.raises(names.CompanyNameError):
        names.check(bad)


def test_the_three_region_ids_are_reserved_by_literal():
    assert {"eu", "us", "asia"} <= names.reserved()


def test_every_region_id_is_reserved():
    ids = [r["id"] for r in json.loads((paths.repo_root() / "regions.json").read_text())["regions"]]
    assert ids
    for region in ids:
        with pytest.raises(names.CompanyNameError, match="reserved"):
            names.check(region)


@pytest.mark.parametrize(
    "word",
    [
        "account",
        "proxy",
        "signer",
        "configs",
        "backups",
        "bench",
        "www",
        "stable",
        "edge",
        "control",
        "notify",
        "ops-health",
    ],
)
def test_service_words_reserved(word):
    with pytest.raises(names.CompanyNameError, match="reserved"):
        names.check(word)


def test_proxy_suffix_refused_even_for_unreserved_stem():
    with pytest.raises(names.CompanyNameError, match="-proxy"):
        names.check("acme-proxy")


def test_region_host_labels_derive_from_regions_json():
    """Each region's id and the leading label of its `domain` come from regions.json."""
    reserved = names.reserved()
    rows = json.loads((paths.repo_root() / "regions.json").read_text())["regions"]
    assert rows
    for row in rows:
        assert row["id"] in reserved
        assert row["domain"].split(".")[0] in reserved
    # Region ids that SERVICE_LABELS does not list (eu, us) can only be reserved because regions.json supplied them.
    derived = {r["id"] for r in rows} - set(names.SERVICE_LABELS)
    assert derived
    assert derived <= reserved


def test_opaque_store_id_shape_refused():
    with pytest.raises(names.CompanyNameError, match="opaque"):
        names.check("c0123456789ab")


def test_hosts_under_product_domain():
    assert names.hosts("acme", PRODUCT_DOMAIN) == (
        f"acme.{PRODUCT_DOMAIN}",
        f"acme-proxy.{PRODUCT_DOMAIN}",
    )
    with pytest.raises(names.CompanyNameError):
        names.hosts("eu", PRODUCT_DOMAIN)


def test_xn_prefix_is_refused_by_its_own_rule():
    with pytest.raises(names.CompanyNameError, match="xn--"):
        names.check("xn--acme")


@pytest.mark.parametrize("domain", [None, "", " ", ".", "\t", "\n", " .\t\r\n. "])
def test_hosts_refuses_a_missing_domain(domain: typing.Any):
    with pytest.raises(names.CompanyNameError, match="not a domain"):
        names.hosts("acme", domain)
