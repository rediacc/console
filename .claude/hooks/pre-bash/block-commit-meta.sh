#!/usr/bin/env bash
# Block Co-Authored-By / Generated with lines in commits.
#
# IT MUST BE A COMMIT. This guard's whole history is false positives, and the
# header used to record three of them: the unanchored `Generated with` fired
# inside "witho|ut", then on "Re|generated with npm@10" once a word boundary was
# added, then on an ordinary PR body describing a regenerated i18n baseline.
# Each fix narrowed the PHRASE. None of them asked the question that actually
# separates a violation from a sentence -- is this command writing a commit
# message at all?
#
# The unfixed half was `Co-Authored-By`, which the old header defended as
# "unambiguous anywhere". It is not. Measured 2026-08-27, it refused:
#
#   grep -rn 'co-authored-by' docs/        <- searching for the banned trailer
#   echo 'the rule bans Co-Authored-By'    <- prose naming the rule
#
# Both are how you AUDIT this rule, so the guard was blocking its own
# enforcement. Case-insensitivity made it worse, not better.
#
# So the phrase check now runs only when the command authors a message: a git
# commit, a git tag -m, or a gh pr create/edit. A heredoc body still counts,
# because the body is part of the command -- which is the case that matters, and
# the one every earlier narrowing preserved by accident rather than on purpose.
#
# The line anchoring on `Generated with` stays. A guard whose only failure mode
# is refusing CORRECT input teaches people to reword honest messages until it
# stops complaining, and the rewording hides what happened.
CMD=$(jq -r '.tool_input.command' 2>/dev/null)
[ -z "$CMD" ] && exit 0

# Not authoring a message -> not this guard's business.
#
# THE GAP MUST NOT CROSS A CLAUSE. `git ... commit` needs to tolerate flags in
# between (`git -C sub commit`, `git commit -a`), but a gap of "any non-space
# token" happily spans `|` and `&&`, so this matched:
#
#   git log --oneline | grep commit | grep Co-Auth[ored-By]
#
# -- a `git log` in one clause and the word `commit` in another, read as a
# commit that carries a trailer. Excluding `;|&` from the gap tokens keeps the
# verb and its subcommand in one clause, which is the same fix
# block-protected-files needed for the same reason on the same day.
printf '%s' "$CMD" | grep -qE '(^|[;&|(]|[[:space:]])git[[:space:]]+([^[:space:];|&]+[[:space:]]+)*(commit|tag)\b|(^|[;&|(]|[[:space:]])gh[[:space:]]+pr[[:space:]]+(create|edit)\b' || exit 0

if printf '%s' "$CMD" | grep -qiE 'Co-Authored-By|^[[:space:]]*([^[:alnum:]]{0,4}[[:space:]]*)?Generated with\b'; then
    echo "❌ BLOCKED: Do not add Co-Authored-By or Generated with lines in commits." >&2
    exit 2
fi
exit 0
