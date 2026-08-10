"""Mutation target for the mutate-check.sh self-test. Not production code.

Deliberately trivial: the gate needs a file whose content decides a fixture
suite's verdict, so the mutation runner can be driven through all four of its
outcomes in seconds instead of the 8-plus minutes a real suite costs.
"""

GUARD_ENABLED = True

# A line with no behavioural meaning, mutated by the scenario that proves the
# runner reports "the check does not detect this" when a mutation applies
# cleanly and changes nothing the suite can observe.
HARMLESS_MARKER = "unmutated"
