#!/usr/bin/env bash
# Block Co-Authored-By / Generated with lines in commits.
CMD=$(jq -r '.tool_input.command' 2>/dev/null)
# WORD BOUNDARY ON `with`, and it is load-bearing. Without it the pattern also
# matches "with" inside "witho ut", so an ordinary sentence like "audio
# generated without --subtitle" was blocked as an attribution trailer. That is
# the cry-wolf direction: a guard whose only failure mode is refusing correct
# input teaches people to work around it, and the workaround here is to reword
# a truthful commit message until the guard stops complaining.
if echo "$CMD" | grep -qiE 'Co-Authored-By|Generated with\b'; then
    echo "❌ BLOCKED: Do not add Co-Authored-By or Generated with lines in commits." >&2
    exit 2
fi
exit 0
