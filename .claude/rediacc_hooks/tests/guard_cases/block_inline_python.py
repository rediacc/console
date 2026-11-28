"""The test tables of `block_inline_python`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards.tables`."""

from rediacc_hooks.tests.fixtures.guards.loader import load_table

# The two sides of the escape hatch. Both are run over the whole case list, so the override is proved to let a real finding through rather than assumed to.
ENVS: list = [
    ("default", {}, {}),
    ("override", {"REDIACC_ALLOW_INLINE_PYTHON": "1"}, {}),
]


# The detector's own control case, reused rather than reinvented: two distinct statement-shaped signals at the head of a line inside one quoted region.
_PROGRAM = "const s = `\nimport os\nimport pathlib\n\ndef go():\n    print(os.getcwd())\n`;\n"


EDGE_CASES = load_table("block_inline_python", "EDGE_CASES")
