#!/usr/bin/env bash
# Best-effort submodule initialization.
#
# Tries each submodule individually so developers get whichever ones they have
# access to, without blocking on the rest. Runs in Codespaces, in the
# devcontainer, and on a plain host checkout.
#
# The point of this script is the DIAGNOSIS. An earlier version ran
# `git submodule update --init --recursive "$sub" 2>/dev/null` and printed
# "no access, skipping" for every failure. That is wrong often enough to cost a
# session: a valid token behind a stale credential helper, an expired token, a
# dropped network and a genuine permission denial all looked identical, and the
# actual git error was thrown away. Nothing here discards stderr.
#
# Usage:
#   ./init-submodules.sh [OPTIONS] [SUBMODULE_PATH...]
#
# Options:
#   --token-env <NAME>  Env var holding a GitHub token to retry auth failures
#                       with. Repeatable. Default: GITHUB_TOKEN GH_TOKEN PAT
#   --no-token          Never use a token; only whatever git is already configured with
#   --no-recursive      Do not initialize nested submodules
#   --quiet             Only print the summary and any failures
#   --help              Show this help
#
# Exit status: 0 if every submodule initialized, 1 otherwise. (postCreateCommand
# callers that must not block should invoke it as `bash init-submodules.sh || true`.)

set -uo pipefail

GREEN=''; RED=''; YELLOW=''; DIM=''; NC=''
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  GREEN=$'\033[0;32m'; RED=$'\033[0;31m'; YELLOW=$'\033[0;33m'; DIM=$'\033[2m'; NC=$'\033[0m'
fi

TOKEN_ENV_NAMES=()
USE_TOKEN=true
RECURSIVE=true
QUIET=false
WANTED=()

# The header comment above IS the help text; print it rather than maintaining a
# second copy that drifts from it.
show_help() { sed -n '2,/^[^#]/p' "$0" | sed '/^[^#]/d; s/^#\( \|$\)//'; }

while [ $# -gt 0 ]; do
  case "$1" in
    --token-env)    TOKEN_ENV_NAMES+=("$2"); shift 2 ;;
    --no-token)     USE_TOKEN=false; shift ;;
    --no-recursive) RECURSIVE=false; shift ;;
    --quiet)        QUIET=true; shift ;;
    --help|-h)      show_help; exit 0 ;;
    -*)             echo "Unknown option: $1" >&2; exit 2 ;;
    *)              WANTED+=("$1"); shift ;;
  esac
done

[ ${#TOKEN_ENV_NAMES[@]} -eq 0 ] && TOKEN_ENV_NAMES=(GITHUB_TOKEN GH_TOKEN PAT)

say() { [ "$QUIET" = true ] || printf '%s\n' "$*"; }

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "Not inside a git repository." >&2; exit 2; }
cd "$REPO_ROOT" || exit 2

if [ ! -f .gitmodules ]; then
  say "No .gitmodules found, nothing to initialize."
  exit 0
fi

mapfile -t ALL_SUBMODULES < <(git config --file .gitmodules --get-regexp '^submodule\..*\.path$' | awk '{print $2}')
if [ ${#ALL_SUBMODULES[@]} -eq 0 ]; then
  say "No submodules configured, nothing to initialize."
  exit 0
fi

if [ ${#WANTED[@]} -gt 0 ]; then
  SUBMODULES=()
  for w in "${WANTED[@]}"; do
    w="${w%/}"
    found=false
    for s in "${ALL_SUBMODULES[@]}"; do [ "$s" = "$w" ] && found=true && break; done
    if [ "$found" = true ]; then SUBMODULES+=("$w")
    else echo "${RED}Not a submodule of this repo: $w${NC}" >&2; exit 2; fi
  done
else
  SUBMODULES=("${ALL_SUBMODULES[@]}")
fi

# ---------------------------------------------------------------------------
# Token discovery. The token is never written to disk and never appears in a
# process argument: it is passed to git through an exported variable that an
# inline credential helper expands in its own shell.
# ---------------------------------------------------------------------------
SUBMODULE_TOKEN=""
TOKEN_SOURCE=""
if [ "$USE_TOKEN" = true ]; then
  for name in "${TOKEN_ENV_NAMES[@]}"; do
    if [ -n "${!name:-}" ]; then
      SUBMODULE_TOKEN="${!name}"
      TOKEN_SOURCE="\$$name"
      break
    fi
  done
fi
export SUBMODULE_TOKEN

# An empty helper entry FIRST resets any inherited/scoped helper (notably
# `!gh auth git-credential`, which is scoped to https://github.com in many
# ~/.gitconfig files and shadows the global one). Without the reset the token
# below is never consulted for github.com.
token_git_args=(
  -c 'credential.https://github.com.helper='
  -c 'credential.https://github.com.helper=!f() { test "$1" = get && printf "username=x-access-token\npassword=%s\n" "$SUBMODULE_TOKEN"; }; f'
)

# ---------------------------------------------------------------------------
# Failure classification, from the real stderr.
# ---------------------------------------------------------------------------
classify() {
  local err="$1"
  case "$err" in
    *"Invalid username or token"*|*"Authentication failed"*|*"could not read Username"*|\
    *"terminal prompts disabled"*|*"Support for password authentication was removed"*)
      echo auth ;;
    *"Repository not found"*|*"remote: Not Found"*|*"access denied"*|*"Permission denied"*|*"403"*)
      echo forbidden ;;
    *"Could not resolve host"*|*"Failed to connect"*|*"Connection timed out"*|\
    *"unable to access"*"Couldn't connect"*|*"TLS connect error"*|*"Operation timed out"*)
      echo network ;;
    *"did not contain the requested object"*|*"reference is not a tree"*|*"fatal: remote error"*)
      echo pointer ;;
    *) echo unknown ;;
  esac
}

explain() {
  case "$1" in
    auth)      echo "authentication rejected" ;;
    forbidden) echo "repository not visible to these credentials" ;;
    network)   echo "network/DNS failure" ;;
    pointer)   echo "pinned commit missing from the remote" ;;
    *)         echo "failed" ;;
  esac
}

# ---------------------------------------------------------------------------
# GitHub credential diagnosis. Printed once, only when an auth failure actually
# happens, so the happy path stays fast and quiet.
# ---------------------------------------------------------------------------
diagnose_github_auth() {
  echo ""
  echo "${YELLOW}Diagnosing GitHub credentials${NC}"

  local helpers
  helpers="$(git config --get-all 'credential.https://github.com.helper' 2>/dev/null)"
  if [ -n "$helpers" ]; then
    echo "  A github.com-scoped credential helper is configured:"
    printf '%s\n' "$helpers" | sed 's/^/    /'
    echo "  ${DIM}A URL-scoped helper list REPLACES the global one for that URL, so a working${NC}"
    echo "  ${DIM}global helper (e.g. 'store') is not consulted for github.com at all.${NC}"
    case "$helpers" in
      *"gh auth git-credential"*)
        if command -v gh >/dev/null 2>&1; then
          if gh auth status >/dev/null 2>&1; then
            echo "  gh is authenticated, so the helper itself looks healthy."
          else
            echo "  ${RED}gh is NOT authenticated${NC}, so that helper hands git an invalid token:"
            gh auth status 2>&1 | sed 's/^/    /'
            echo "  Fix by re-authenticating gh (needs a token with 'read:org'):"
            echo "    gh auth login --hostname github.com"
            echo "  or drop the git-side override so the global helper is used again:"
            echo "    git config --global --unset-all 'credential.https://github.com.helper'"
          fi
          # gh's helper also runs `erase` on failure, which deletes the entry a
          # `store` helper just saved. Worth stating: writing ~/.git-credentials
          # while this helper is active can look like it silently did nothing.
          echo "  ${DIM}Note: this helper runs 'erase' on failure, wiping entries other helpers stored.${NC}"
        else
          echo "  ${RED}gh is not installed${NC} but is configured as the credential helper."
        fi
        ;;
    esac
  else
    echo "  No github.com-scoped helper; git uses: ${DIM}$(git config --get-all credential.helper | tr '\n' ' ')${NC}"
  fi

  if [ -n "$SUBMODULE_TOKEN" ]; then
    if ! command -v curl >/dev/null 2>&1; then
      echo "  Token present in ${TOKEN_SOURCE}; curl is missing so it cannot be validated here."
    else
      # One request, headers and body together, and the HTTP CODE decides. An
      # earlier version keyed off "did curl print anything", which reports a
      # rejected token as valid: `curl -f -D -` still dumps the 401 headers.
      local resp code login scopes
      resp="$(curl -sS --retry 5 --retry-delay 3 -D - -H "Authorization: Bearer $SUBMODULE_TOKEN" \
                https://api.github.com/user 2>/dev/null)"
      code="$(printf '%s' "$resp" | sed -n '1s@^HTTP/[0-9.]* \([0-9]*\).*@\1@p' | tail -1)"
      if [ "$code" = 200 ]; then
        login="$(printf '%s' "$resp" | sed -n 's/.*"login"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)"
        scopes="$(printf '%s' "$resp" | sed -n 's/^[Xx]-[Oo][Aa]uth-[Ss]copes:[[:space:]]*//p' | tr -d '\r' | head -1)"
        echo "  Token in ${TOKEN_SOURCE}: ${GREEN}accepted by the GitHub API${NC} (login ${login:-?}, scopes: ${scopes:-none})"
        case ",$(printf '%s' "$scopes" | tr -d ' ')," in
          *,repo,*) echo "  ${DIM}It has 'repo', so a private submodule failing here is an access grant, not the token.${NC}" ;;
          *) echo "  ${RED}It lacks the 'repo' scope${NC}, which private submodules require." ;;
        esac
      else
        echo "  Token in ${TOKEN_SOURCE}: ${RED}rejected by the GitHub API${NC} (HTTP ${code:-no response}) — expired or revoked."
      fi
    fi
  else
    echo "  No token found in: ${TOKEN_ENV_NAMES[*]}"
    echo "  Export one of those with a 'repo'-scoped token and re-run to retry automatically."
  fi
  echo ""
}

# ---------------------------------------------------------------------------
# Per-submodule attempt.
# ---------------------------------------------------------------------------
update_args=(submodule update --init)
[ "$RECURSIVE" = true ] && update_args+=(--recursive)

attempt() { # attempt <use_token> <path> -> prints stderr, returns git status
  local use_token="$1" sub="$2"
  # Capture stderr only: git's progress chatter on stdout is noise, its error
  # text is the whole point. The braces make the order unambiguous (plain
  # `2>&1 >/dev/null` reads like a mistake and shellcheck flags it as SC2069).
  if [ "$use_token" = true ]; then
    { GIT_TERMINAL_PROMPT=0 git "${token_git_args[@]}" "${update_args[@]}" -- "$sub" >/dev/null; } 2>&1
  else
    { GIT_TERMINAL_PROMPT=0 git "${update_args[@]}" -- "$sub" >/dev/null; } 2>&1
  fi
}

say "Initializing ${#SUBMODULES[@]} submodule(s) in $REPO_ROOT"
[ -n "$SUBMODULE_TOKEN" ] && say "${DIM}Token available from ${TOKEN_SOURCE} for retrying auth failures.${NC}"
say ""

ok=0
failed_paths=()
failed_reasons=()
diagnosed=false

for sub in "${SUBMODULES[@]}"; do
  status_char="$(git submodule status -- "$sub" 2>/dev/null | cut -c1)"
  if [ "$status_char" = " " ] && [ -n "$(ls -A "$sub" 2>/dev/null)" ]; then
    say "  ${GREEN}✓${NC} $sub ${DIM}(already initialized)${NC}"
    ((ok++))
    continue
  fi

  # '+' means the submodule is checked out at a DIFFERENT commit than the
  # superproject pins. Running `submodule update` there detaches it onto the
  # pinned commit and silently walks away from whatever was checked out. That is
  # someone's work, so refuse and let them decide.
  if [ "$status_char" = "+" ]; then
    have="$(git -C "$sub" rev-parse --short HEAD 2>/dev/null)"
    want="$(git ls-tree HEAD -- "$sub" 2>/dev/null | awk '{print substr($3,1,7)}')"
    echo "  ${YELLOW}!${NC} $sub — checked out at ${have}, superproject pins ${want}; left alone."
    echo "      ${DIM}Run 'git submodule update -- $sub' yourself if that commit is disposable.${NC}"
    ((ok++))
    continue
  fi

  err="$(attempt false "$sub")"
  rc=$?
  used_token=false

  if [ $rc -ne 0 ] && [ -n "$SUBMODULE_TOKEN" ]; then
    kind="$(classify "$err")"
    if [ "$kind" = auth ] || [ "$kind" = forbidden ]; then
      err="$(attempt true "$sub")"
      rc=$?
      used_token=true
    fi
  fi

  if [ $rc -eq 0 ]; then
    sha="$(git -C "$sub" rev-parse --short HEAD 2>/dev/null)"
    suffix=""
    [ "$used_token" = true ] && suffix=" ${DIM}(via ${TOKEN_SOURCE})${NC}"
    say "  ${GREEN}✓${NC} $sub ${DIM}${sha}${NC}${suffix}"
    ((ok++))
  else
    kind="$(classify "$err")"
    echo "  ${RED}✗${NC} $sub — $(explain "$kind")"
    printf '%s\n' "$err" | sed '/^$/d' | sed "s/^/      ${DIM}/;s/$/${NC}/"
    failed_paths+=("$sub")
    failed_reasons+=("$kind")
    if [ "$kind" = auth ] && [ "$diagnosed" = false ]; then
      diagnose_github_auth
      diagnosed=true
    fi
  fi
done

echo ""
echo "Initialized $ok/${#SUBMODULES[@]} submodule(s)."

if [ ${#failed_paths[@]} -gt 0 ]; then
  echo "${RED}Failed:${NC} ${failed_paths[*]}"
  for i in "${!failed_paths[@]}"; do
    case "${failed_reasons[$i]}" in
      network) echo "  ${failed_paths[$i]}: transient — re-run this script once connectivity is back." ;;
      pointer) echo "  ${failed_paths[$i]}: the superproject points at a commit the remote does not have;"
               echo "      someone force-pushed or forgot to push. Ask for the missing commit." ;;
      forbidden) echo "  ${failed_paths[$i]}: credentials are valid but lack access to that repository." ;;
    esac
  done
  exit 1
fi
exit 0
