"""`rediacc_ci.infra.obs_ceph_autobump`: the plan and land jobs of obs-ceph-autobump.yml.

Nothing here runs npm, gh or git, or touches the network: every command goes through a fake runner that answers from a dict and records what it was asked, and a clone is a directory the fake writes. The site regexes are the real ones from .ci/config/pins.json, so a registry edit that breaks the rewrite reds here. The verdicts that carry the design, each with its control:

  * a bump line is a bump, a `REFUSED ... current` is nothing to do, anything else is red;
  * plan refuses a bump that moved a renet file outside the registry's sites, and passes one that moved only sites;
  * the rewrite moves exactly the site value, leaves an already-moved site alone, and refuses a hand-moved one;
  * land pushes only to the one open MMDD-N PR head, refuses none, two, or a non MMDD-N head;
  * land refuses a branch snapshot without exactly one PR-TASK epic;
  * land commits on renet and moves the console gitlink, each carrying the trailer, and pushes without force;
  * an already-landed bump pushes nothing.
"""

from __future__ import annotations

import json
import pathlib
import subprocess

import pytest

from rediacc_ci.infra import obs_ceph_autobump as ab

OLD = "19.2.3-lp160.2.1"
NEW = "19.2.3-lp160.2.2"
BRANCH = "1023-1"
TASK = "cafe1234"
GITLINK = "a" * 40
REGISTRY = (ab.ROOT / ab.PINS_REL).read_text(encoding="utf-8")


def renet_files(evr: str) -> dict[str, str]:
    return {
        ".ceph-image-pin": "image=x\n# a comment naming nothing\nhost.opensuse-16.0=%s\nreview=x\n"
        % evr,
        "pkg/infra/cephpkg/cephpkg.go": (
            'var hostPins = map[string]string{\n\t"el10":          "2:19.2.3-1.el10s",\n'
            '\t"opensuse-16.0": "%s",\n}\n' % evr
        ),
        "cmd/renet/ceph_install_profile_test.go": (
            '\t\t\t"zypper -n install --no-recommends ceph-common=%s",\n' % evr
        ),
    }


def done(out: str = "", rc: int = 0, err: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], rc, out, err)


class Fake:
    """A runner answering gh and git from state, writing clones to disk."""

    def __init__(
        self,
        *,
        prs: list[dict[str, object]] | None = None,
        snapshot: str | None = "`PR-TASK: %s`\n" % TASK,
        renet_branch: bool = True,
        renet_evr: str = OLD,
        gitlink_evr: str = OLD,
        push_rc: int = 0,
        renet_ahead: bool = False,
    ) -> None:
        self.prs = prs if prs is not None else [{"headRefName": BRANCH, "isCrossRepository": False}]
        self.snapshot = snapshot
        self.renet_branch = renet_branch
        self.renet_evr = renet_evr
        self.gitlink_evr = gitlink_evr
        self.push_rc = push_rc
        self.calls: list[list[str]] = []
        self.renet_tip = GITLINK if renet_evr == gitlink_evr and not renet_ahead else "b" * 40
        self.messages: dict[str, str] = {}

    def __call__(
        self, argv: list[str], _cwd: str | None = None
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append(argv)
        if argv[:3] == ["gh", "pr", "list"]:
            return done(json.dumps(self.prs))
        if argv[:2] == ["git", "ls-remote"]:
            return done(
                "%s\trefs/heads/%s\n" % (self.renet_tip, BRANCH) if self.renet_branch else ""
            )
        if argv[:2] == ["git", "clone"]:
            dest = pathlib.Path(argv[-1])
            dest.mkdir(parents=True)
            if argv[-2].endswith("/console.git") and self.snapshot is not None:
                (dest / "agent" / "pr").mkdir(parents=True)
                (dest / "agent" / "pr" / ("%s.md" % BRANCH)).write_text(self.snapshot)
            if argv[-2].endswith("/renet.git"):
                for rel, text in renet_files(self.renet_evr).items():
                    (dest / rel).parent.mkdir(parents=True, exist_ok=True)
                    (dest / rel).write_text(text)
            return done()
        assert argv[:2] == ["git", "-C"], argv
        repo = pathlib.Path(argv[2]).name
        args = argv[7:]
        if args[:1] == ["rev-parse"]:
            return done((GITLINK if args[1].endswith(":private/renet") else self.renet_tip) + "\n")
        if args[:1] == ["commit"]:
            self.messages[repo] = pathlib.Path(args[2]).read_text()
            if repo == "renet":
                self.renet_tip = "c" * 40
            return done()
        if args[:1] == ["push"]:
            return done(rc=self.push_rc, err="! [rejected] (fetch first)")
        if args[:1] == ["show"]:
            return done(renet_files(self.gitlink_evr)[".ceph-image-pin"])
        return done()

    def pushes(self) -> list[list[str]]:
        return [c for c in self.calls if c[:2] == ["git", "-C"] and c[7:8] == ["push"]]


# --- plan -------------------------------------------------------------------------------------


def test_parse_bump_reads_the_three_verdicts() -> None:
    assert ab.parse_bump(0, "os:opensuse-16.0-ceph: %s -> %s\ngates: ok\n" % (OLD, NEW)) == ab.Plan(
        "bump", OLD, NEW
    )
    assert ab.parse_bump(
        1, "nothing written.\nREFUSED os:opensuse-16.0-ceph: current: current\n"
    ) == ab.Plan("none")
    with pytest.raises(ab.AutobumpError, match="no obs-mirror tag"):
        ab.parse_bump(1, "REFUSED os:opensuse-16.0-ceph: no obs-mirror tag for %s\n" % NEW)
    with pytest.raises(ab.AutobumpError, match="exited 1"):
        ab.parse_bump(1, "os:opensuse-16.0-ceph: %s -> %s\ngates: rc=1\n" % (OLD, NEW))
    with pytest.raises(ab.AutobumpError):
        ab.parse_bump(0, "os:opensuse-16.0-ceph: %s -> 20.1.0;rm\n" % OLD)


def _plan_tree(tmp_path: pathlib.Path, evr: str) -> pathlib.Path:
    (tmp_path / ".ci" / "config").mkdir(parents=True)
    (tmp_path / ".ci" / "config" / "pins.json").write_text(REGISTRY)
    renet = tmp_path / "private" / "renet"
    renet.mkdir(parents=True)
    (renet / ".ceph-image-pin").write_text(renet_files(evr)[".ceph-image-pin"])
    return tmp_path


def _plan_runner(moved: str):
    def run(argv: list[str], _cwd: str | None = None) -> subprocess.CompletedProcess[str]:
        if argv[0] == "npm":
            return done("os:opensuse-16.0-ceph: %s -> %s\n" % (OLD, NEW))
        return done(moved)

    return run


def test_plan_passes_a_bump_that_moved_only_sites(tmp_path: pathlib.Path) -> None:
    root = _plan_tree(tmp_path, NEW)
    moved = (
        ".ceph-image-pin\npkg/infra/cephpkg/cephpkg.go\ncmd/renet/ceph_install_profile_test.go\n"
    )
    assert ab.plan(_plan_runner(moved), root) == ab.Plan("bump", OLD, NEW)


def test_plan_refuses_a_bump_that_moved_another_renet_file(tmp_path: pathlib.Path) -> None:
    root = _plan_tree(tmp_path, NEW)
    with pytest.raises(ab.AutobumpError, match="only the registry's sites"):
        ab.plan(_plan_runner(".ceph-image-pin\npkg/daemon/x.go\n"), root)


def test_plan_refuses_a_pin_file_the_bump_did_not_move(tmp_path: pathlib.Path) -> None:
    root = _plan_tree(tmp_path, OLD)
    with pytest.raises(ab.AutobumpError, match="reads %s" % OLD):
        ab.plan(_plan_runner(".ceph-image-pin\n"), root)


# --- rewrite ----------------------------------------------------------------------------------


def test_rewrite_moves_only_the_site_value() -> None:
    files = renet_files(OLD)
    for site in ab.sites(REGISTRY):
        text, moved = ab.rewrite(files[site.file], site, OLD, NEW)
        assert moved
        assert text == renet_files(NEW)[site.file]


def test_rewrite_leaves_an_already_moved_site_alone() -> None:
    for site in ab.sites(REGISTRY):
        assert ab.rewrite(renet_files(NEW)[site.file], site, OLD, NEW) == (
            renet_files(NEW)[site.file],
            False,
        )


def test_rewrite_refuses_a_hand_moved_pin_and_a_wrong_count() -> None:
    site = next(s for s in ab.sites(REGISTRY) if s.file == ".ceph-image-pin")
    with pytest.raises(ab.AutobumpError, match="moved by hand"):
        ab.rewrite(renet_files("19.2.3-lp160.2.99")[site.file], site, OLD, NEW)
    with pytest.raises(ab.AutobumpError, match="expects 1"):
        ab.rewrite(renet_files(OLD)[site.file] * 2, site, OLD, NEW)


# --- land -------------------------------------------------------------------------------------


def test_land_commits_on_renet_moves_the_gitlink_and_pushes_without_force(
    tmp_path: pathlib.Path,
) -> None:
    fake = Fake()
    out = ab.land(OLD, NEW, work=tmp_path, pins_json=REGISTRY, run=fake)
    assert out == {"branch": BRANCH, "renet": "pushed", "console": "pushed", "action": "bump"}
    for rel, text in renet_files(NEW).items():
        assert (tmp_path / "renet" / rel).read_text() == text
    pushes = fake.pushes()
    assert [p[-1] for p in pushes] == ["HEAD:refs/heads/%s" % BRANCH] * 2
    assert not any(a.startswith(("-f", "--force", "+")) for p in pushes for a in p[8:])
    assert [pathlib.Path(p[2]).name for p in pushes] == ["renet", "console"]
    for repo in ("renet", "console"):
        assert fake.messages[repo].rstrip().endswith("PR-TASK: %s" % TASK)
    link = [c for c in fake.calls if "update-index" in c]
    assert link
    assert link[0][-1] == "160000,%s,private/renet" % ("c" * 40)


def test_land_cuts_the_renet_branch_from_the_gitlink_when_absent(tmp_path: pathlib.Path) -> None:
    fake = Fake(renet_branch=False)
    ab.land(OLD, NEW, work=tmp_path, pins_json=REGISTRY, run=fake)
    assert any(c[7:] == ["checkout", "-b", BRANCH, GITLINK] for c in fake.calls)


def test_land_pushes_nothing_once_landed(tmp_path: pathlib.Path) -> None:
    fake = Fake(renet_evr=NEW, gitlink_evr=NEW)
    out = ab.land(OLD, NEW, work=tmp_path, pins_json=REGISTRY, run=fake)
    assert out["action"] == "none"
    assert fake.pushes() == []


def test_land_leaves_a_gitlink_that_already_carries_the_pin(tmp_path: pathlib.Path) -> None:
    fake = Fake(renet_evr=NEW, gitlink_evr=NEW, renet_ahead=True)
    out = ab.land(OLD, NEW, work=tmp_path, pins_json=REGISTRY, run=fake)
    assert out["action"] == "none"
    assert fake.pushes() == []


def test_land_recovers_a_renet_push_whose_console_push_failed(tmp_path: pathlib.Path) -> None:
    fake = Fake(renet_evr=NEW, gitlink_evr=OLD)
    out = ab.land(OLD, NEW, work=tmp_path, pins_json=REGISTRY, run=fake)
    assert (out["renet"], out["console"]) == ("unchanged", "pushed")


@pytest.mark.parametrize(
    ("prs", "why"),
    [
        ([], "no open console PR"),
        ([{"headRefName": "main", "isCrossRepository": False}], "no open console PR"),
        ([{"headRefName": BRANCH, "isCrossRepository": True}], "no open console PR"),
        (
            [
                {"headRefName": BRANCH, "isCrossRepository": False},
                {"headRefName": "1024-1", "isCrossRepository": False},
            ],
            "more than one",
        ),
    ],
)
def test_land_refuses_anything_but_one_live_pr(
    tmp_path: pathlib.Path, prs: list[dict[str, object]], why: str
) -> None:
    fake = Fake(prs=prs)
    with pytest.raises(ab.AutobumpError, match=why):
        ab.land(OLD, NEW, work=tmp_path, pins_json=REGISTRY, run=fake)
    assert fake.pushes() == []


@pytest.mark.parametrize(
    "snapshot", [None, "no trailer\n", "PR-TASK: cafe1234\nPR-TASK: beef5678\n"]
)
def test_land_refuses_a_snapshot_without_exactly_one_epic(
    tmp_path: pathlib.Path, snapshot: str | None
) -> None:
    fake = Fake(snapshot=snapshot)
    with pytest.raises(ab.AutobumpError, match="exactly one"):
        ab.land(OLD, NEW, work=tmp_path, pins_json=REGISTRY, run=fake)
    assert fake.pushes() == []


def test_land_refuses_a_non_evr_and_a_rejected_push(tmp_path: pathlib.Path) -> None:
    with pytest.raises(ab.AutobumpError, match="not a Leap EVR"):
        ab.land(OLD, "19.2.3;rm -rf", work=tmp_path / "a", pins_json=REGISTRY, run=Fake())
    fake = Fake(push_rc=1)
    with pytest.raises(ab.AutobumpError, match="rejected"):
        ab.land(OLD, NEW, work=tmp_path / "b", pins_json=REGISTRY, run=fake)
    assert len(fake.pushes()) == 1


def test_branch_guard_refuses_main() -> None:
    with pytest.raises(ab.AutobumpError, match="only an MMDD-N"):
        ab._branch("main")
    assert ab._branch(BRANCH) == BRANCH
