#!/usr/bin/env bash
# Block Co-Authored-By / Generated with lines in commits.
CMD=$(jq -r '.tool_input.command' 2>/dev/null)
# ANCHORED TO A LINE START, because what is banned is a TRAILER, not a phrase.
# The unanchored pattern fired twice in twenty minutes on ordinary prose in this
# repo's own commit messages: once inside "witho|ut" (no word boundary), and
# again on "Re|generated with npm@10" once the boundary was added, because that
# really does contain the token. Both were truthful sentences describing real
# work, and both were rejected as attribution.
#
# A real trailer begins its line, optionally behind the robot emoji. Matching
# there catches every form the tools actually emit while leaving prose alone.
# This direction matters: a guard whose only failure mode is refusing CORRECT
# input teaches people to reword honest messages until it stops complaining,
# which is worse than not having the guard, because the rewording hides what
# happened. Co-Authored-By stays unanchored: it is unambiguous anywhere.
if echo "$CMD" | grep -qiE 'Co-Authored-By|^[[:space:]]*(.{0,4}[[:space:]]*)?Generated with\b'; then
    echo "❌ BLOCKED: Do not add Co-Authored-By or Generated with lines in commits." >&2
    exit 2
fi
exit 0
