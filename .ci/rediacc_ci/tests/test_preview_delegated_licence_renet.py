"""PLAN-preview-signer A1: a delegated repo licence whose subscription id is `pv-<name>-<8 hex>` validates in renet's create and operate tiers, and a licence outside its cert is refused.

The Go program below drives the exported validators of `private/renet/pkg/license`, the same functions the create tier (`ValidateRepoForMachine`) and the operate tier (`ValidateRepoForMachineOperate`) call with the key baked into a production renet. A generated master key stands in for the baked one, since the validators take the master key as an argument and the production private key is not in the tree. Nothing is written into the renet checkout: the program lives in a temp module that points at it through a `replace` directive.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import typing

import pytest

from rediacc_ci import paths

if typing.TYPE_CHECKING:
    import pathlib

RENET = paths.from_root("private", "renet")

PROGRAM = r"""package main

import (
	"crypto/ed25519"
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"time"

	"github.com/rediacc/renet/pkg/license"
	"github.com/rediacc/renet/pkg/subscription"
)

const sub = "pv-able-baker-charlie-1a2b3c4d"
const guid = "550e8400-e29b-41d4-a716-446655440000"

func sign(v any, priv ed25519.PrivateKey) (string, string) {
	data, _ := json.Marshal(v)
	p := base64.StdEncoding.EncodeToString(data)
	return p, base64.StdEncoding.EncodeToString(ed25519.Sign(priv, []byte(p)))
}

func gen() (ed25519.PublicKey, ed25519.PrivateKey) {
	pub, priv, _ := ed25519.GenerateKey(rand.Reader)
	return pub, priv
}

func build(licSub string, certSub string, masterPriv ed25519.PrivateKey, masterID string, delPub ed25519.PublicKey, delPriv ed25519.PrivateKey) *license.SignedRepoLicense {
	now := time.Now()
	cert := subscription.DelegationCert{
		Version: 1, SubscriptionID: certSub, PlanCode: subscription.PlanProfessional,
		MaxRepositorySizeGb: 100, MaxTotalIssuances: -1,
		DelegatedPublicKey: base64.StdEncoding.EncodeToString(delPub),
		ValidFrom: now.Add(-time.Hour).Format(time.RFC3339),
		ValidUntil: now.Add(time.Hour).Format(time.RFC3339),
		IssuedAt: now.Format(time.RFC3339),
	}
	cp, cs := sign(cert, masterPriv)
	lic := license.RepoLicense{
		Version: 1, SubscriptionID: licSub, RepositoryGuid: guid, MachineID: "m1",
		PlanCode: "PROFESSIONAL", MaxRepositorySizeGb: 50, Sequence: 1,
		IssuedAt: now, HardExpiresAt: now.Add(24 * time.Hour),
	}
	lp, ls := sign(lic, delPriv)
	return &license.SignedRepoLicense{
		Payload: lp, Signature: ls, PublicKeyID: subscription.KeyFingerprint(delPub),
		DelegationCert: &subscription.SignedDelegationCert{Payload: cp, Signature: cs, PublicKeyID: masterID},
	}
}

func verdict(err error) string {
	if err == nil {
		return "ok"
	}
	return err.Error()
}

func main() {
	mPub, mPriv := gen()
	mID := subscription.KeyFingerprint(mPub)
	dPub, dPriv := gen()
	good := build(sub, sub, mPriv, mID, dPub, dPriv)
	other := build(sub, "pv-other-name-charlie-deadbeef", mPriv, mID, dPub, dPriv)
	_, e1 := license.ValidateRepoForMachine(good, mPub, mID, "m1", guid)
	_, e2 := license.ValidateRepoForMachineOperate(good, mPub, mID, "m1", guid)
	_, e3 := license.ValidateRepoForMachine(other, mPub, mID, "m1", guid)
	_, e4 := license.ValidateRepoForMachineOperate(other, mPub, mID, "m1", guid)
	out, _ := json.Marshal(map[string]string{"create": verdict(e1), "operate": verdict(e2), "createOther": verdict(e3), "operateOther": verdict(e4)})
	fmt.Println(string(out))
}
"""


def _run_program(tmp_path: pathlib.Path) -> dict[str, str]:
    go = shutil.which("go")
    if go is None:
        pytest.fail("the go toolchain is required to drive renet's validators")
        raise AssertionError  # pytest.fail never returns; narrows `go` for mypy
    mod = (RENET / "go.mod").read_text(encoding="utf-8")
    # The probe module inherits renet's requirement set, so every indirect version resolves as it does in renet itself.
    probe = mod.replace("module github.com/rediacc/renet", "module a1probe", 1)
    (tmp_path / "go.mod").write_text(
        f"{probe}\nrequire github.com/rediacc/renet v0.0.0\n\nreplace github.com/rediacc/renet => {RENET}\n",
        encoding="utf-8",
    )
    shutil.copyfile(RENET / "go.sum", tmp_path / "go.sum")
    (tmp_path / "main.go").write_text(PROGRAM, encoding="utf-8")
    done = subprocess.run(
        [go, "run", "."],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def verdicts(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    return _run_program(tmp_path_factory.mktemp("a1probe"))


def test_pv_subscription_id_validates_in_the_create_tier(verdicts: dict[str, str]) -> None:
    assert verdicts["create"] == "ok"


def test_pv_subscription_id_validates_in_the_operate_tier(verdicts: dict[str, str]) -> None:
    assert verdicts["operate"] == "ok"


def test_a_licence_outside_its_cert_subscription_is_refused_in_both_tiers(
    verdicts: dict[str, str],
) -> None:
    for tier in ("createOther", "operateOther"):
        assert "not covered by delegation cert" in verdicts[tier], verdicts[tier]
