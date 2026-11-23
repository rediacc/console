"""The test tables of `block_shape_lessons`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards._cases.lazy`."""

EDGE_CASES = [
    ("a millisecond date under uutils (TRAPS seed, warns)", "date +%s%3N"),
    ("a date run inside a substitution warns too", "t=$(date +%s%3N); echo $t"),
    ("a date with no precision digit", "date +%s"),
    ("the shape named inside an echo is not a run", 'echo "date +%s%3N"'),
    ("an unrelated command", "git status"),
]
