#!/usr/bin/env bash
# WARN (never block) when a commit would carry a staged deletion of tracked
# files inside a submodule.
#
# Why warn and not block: removing a file from a submodule is ordinary work, so
# a guard that refuses it would be wrong most of the times it fires, and a guard
# whose usual outcome is a false positive teaches people to route around it.
# What is worth surfacing is the case where the deletion is not YOURS: a
# submodule checkout carried a staged `rm` of Formula/rediacc-cli.rb and
# README.md -- the entire content of rediacc/homebrew-tap -- from before the
# session that found it. It sat unnoticed for hours because the parent reports
# only "m private/homebrew-tap", with no per-file detail, and `git status` in
# the parent never shows what was staged inside.
#
# Committing that would have deleted the published Homebrew formula.
#
# Exit 0 ALWAYS. This hook's only job is to put the paths in front of you.
CMD=$(jq -r '.tool_input.command' 2>/dev/null)

# Only interesting just before a commit is created.
echo "$CMD" | grep -qE '(^|[;&|[:space:]])git[[:space:]]+(-C[[:space:]]+\S+[[:space:]]+)?commit\b' || exit 0

ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
cd "$ROOT" 2>/dev/null || exit 0
[ -f .gitmodules ] || exit 0

found=""
while IFS= read -r sub; do
    [ -n "$sub" ] || continue
    [ -e "$sub/.git" ] || continue
    # --cached: what is STAGED for the submodule's next commit, which is exactly
    # what the parent's status cannot show you.
    dels=$(git -C "$sub" diff --cached --name-only --diff-filter=D 2>/dev/null)
    [ -n "$dels" ] || continue
    tracked=$(git -C "$sub" ls-tree -r HEAD --name-only 2>/dev/null | wc -l)
    ndel=$(printf '%s\n' "$dels" | wc -l)
    found="${found}
  ${sub}: ${ndel} of ${tracked} tracked file(s) staged for deletion
$(printf '%s\n' "$dels" | sed 's/^/      /')"
    # The loudest case: the deletion would empty the submodule.
    if [ "$ndel" -ge "$tracked" ] && [ "$tracked" -gt 0 ]; then
        found="${found}
      ^^ this is EVERY tracked file in that submodule"
    fi
done < <(git config -f .gitmodules --get-regexp path 2>/dev/null | awk '{print $2}')

if [ -n "$found" ]; then
    echo "⚠️  NOTE: a submodule has staged DELETIONS. Not blocking; look before you commit." >&2
    echo "$found" >&2
    echo "" >&2
    echo "  If they are not yours, restore from HEAD rather than committing them:" >&2
    echo "    git -C <submodule> show HEAD:<path> > <path> && git -C <submodule> add <path>" >&2
fi
exit 0
