"""wl_popup.should_pop() -- both directions, deterministically.

A feature whose only test asserts a rate over many real calls is a coin-flip pretending to be a proof. Both cases here are 1.0 or 0.0 for a fixed seed, so each runs once.
"""

import random

import wl_popup


def test_should_pop_fires_under_a_seed_that_rolls_low() -> None:
    rng = random.Random(1)
    assert rng.random() < wl_popup.POP_PROBABILITY, "seed 1's first draw must be under the floor for this test to mean anything"
    assert wl_popup.should_pop(random.Random(1)) is True


def test_should_pop_stays_silent_under_a_seed_that_rolls_high() -> None:
    rng = random.Random(0)
    assert rng.random() >= wl_popup.POP_PROBABILITY, "seed 0's first draw must clear the floor for this test to mean anything"
    assert wl_popup.should_pop(random.Random(0)) is False


def test_the_default_rng_is_the_module_level_random() -> None:
    """CONTROL: an explicit rng and the default must agree on a seeded instance, so `rng=None` is really `random` and not a second, silently different generator."""
    random.seed(1)
    default_roll = wl_popup.should_pop()
    assert default_roll == wl_popup.should_pop(random.Random(1))


def test_the_probability_is_one_in_five() -> None:
    """PIN, not a measurement: the operator asked for 20%. A silent change to this constant should be a visible diff, not a passing test."""
    assert wl_popup.POP_PROBABILITY == 0.2
