"""A writer an API error killed still blocks while the session stands down (wl_standdown.CORE).

ROOT CAUSE this file pins: `resume-dead-agent` (wl_checks, from wl_roster_resume) names each sub-agent an API error cut, with the SendMessage line that restarts it. wl_standdown's profiles are KEEP lists, so a key named in none of them stands down. The key sat in no profile, so under CONC_WAIT, the saturated wait, a dead writer was parked exactly when the lead was told to wait on writers, and the wait never ended on its own. `roster-dead` beside it was kept by every profile; the two are the same roster family and must stand together.
"""

from __future__ import annotations

from rediacc_hooks.tests import wlfix

STD = wlfix.import_wl("wl_standdown")

KEY = "resume-dead-agent"
SIBLING = "roster-dead"


def test_every_profile_keeps_a_dead_writer_beside_roster_dead() -> None:
    assert len(STD.PROFILES) >= 3, "SETUP: wl_standdown lists only %d profile(s)" % len(
        STD.PROFILES
    )
    for profile in STD.PROFILES:
        assert STD.keeps(profile, SIBLING, False, False), (
            "SETUP: %s no longer keeps %s, the sibling this key stands beside"
            % (profile.name, SIBLING)
        )
        assert STD.keeps(profile, KEY, False, False), (
            "%s stands down %s: a writer an API error killed would be parked while the lead waits on it"
            % (profile.name, KEY)
        )


def test_the_saturated_wait_keeps_it_without_the_always_tier_or_compaction() -> None:
    assert STD.keeps(STD.CONC_WAIT, KEY, False, False)
    assert KEY in STD.CORE


def test_control_conc_wait_still_parks_a_key_it_does_not_keep() -> None:
    """keeps() must be able to say no, or the cases above prove nothing."""
    parked = "plan-drift"
    assert parked in STD.PARKED_BY_DESIGN, "SETUP: the control key moved out of PARKED_BY_DESIGN"
    assert not STD.keeps(STD.CONC_WAIT, parked, False, False)
    assert not STD.keeps(STD.CONC_WAIT, "no-such-check", False, False)


def test_it_is_never_both_kept_and_parked_by_design() -> None:
    assert KEY not in STD.PARKED_BY_DESIGN
