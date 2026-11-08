"""enterprise.names: reserved region, service and -proxy names, derived from regions.json and well-known."""

from __future__ import annotations

import json

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
    ],
)
def test_service_words_reserved(word):
    with pytest.raises(names.CompanyNameError, match="reserved"):
        names.check(word)


def test_proxy_suffix_refused_even_for_unreserved_stem():
    with pytest.raises(names.CompanyNameError, match="-proxy"):
        names.check("acme-proxy")


def test_region_host_labels_derive_from_regions_json():
    # edge-eu is a host label in regions.json; the stripped form is reserved too.
    reserved = names.reserved()
    assert {"eu", "us", "asia"} <= reserved
    assert any(label.startswith("edge-") for label in reserved) or "edge" in reserved


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
