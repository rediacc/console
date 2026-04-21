#!/usr/bin/env bash
# Apply + verify the Cloudflare apex redirect rule for rediacc.com -> www.rediacc.com.
#
# Idempotent: reads current state of the Dynamic Redirect ruleset on the
# rediacc.com zone, asserts the apex rule exists with the expected shape, and
# creates it if missing. Safe to re-run.
#
# Why this exists:
#   Google Search Console reported ~58 indexed URLs on the bare apex
#   `rediacc.com/*` returning 404 because the apex used to CNAME to a dead
#   GitHub Pages site. The Worker-side redirect table at
#   `workers/www/src/redirects.json` handles 404s under `www.rediacc.com` but
#   can't see apex requests. A zone-level Redirect Rule is needed to bounce
#   apex -> www before the Worker runs.
#
# Auth:
#   CLOUDFLARE_API_TOKEN, OR
#   CF_API_KEY + CF_EMAIL (fallback for Global API Key)
#
# Usage:
#   ./scripts/dev/apply-cf-redirect-rules.sh              # verify + create if missing
#   ./scripts/dev/apply-cf-redirect-rules.sh --dry-run    # verify only, never mutate

set -euo pipefail

ZONE_ID="9e802649c143c9cefd811d8fd671d31c"  # rediacc.com
DRY_RUN=0

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "unknown arg: $arg" >&2
      exit 2
      ;;
  esac
done

if [[ -n "${CLOUDFLARE_API_TOKEN:-}" ]]; then
  AUTH=(-H "Authorization: Bearer $CLOUDFLARE_API_TOKEN")
elif [[ -n "${CF_API_KEY:-}" && -n "${CF_EMAIL:-}" ]]; then
  AUTH=(-H "X-Auth-Email: $CF_EMAIL" -H "X-Auth-Key: $CF_API_KEY")
else
  echo "ERROR: set CLOUDFLARE_API_TOKEN or CF_API_KEY + CF_EMAIL" >&2
  exit 1
fi

# Locate the http_request_dynamic_redirect ruleset for this zone.
RULESET_ID=$(
  curl -sSf "${AUTH[@]}" \
    "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/rulesets" \
  | jq -r '.result[] | select(.phase == "http_request_dynamic_redirect") | .id'
)
if [[ -z "$RULESET_ID" ]]; then
  echo "ERROR: no http_request_dynamic_redirect ruleset on zone ${ZONE_ID}" >&2
  exit 1
fi
echo "ruleset: ${RULESET_ID}"

# Fetch current rules.
CURRENT=$(
  curl -sSf "${AUTH[@]}" \
    "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/rulesets/${RULESET_ID}"
)

# The apex rule: match any URL on the bare rediacc.com host, 301 to
# https://www.rediacc.com/<path>, preserve query string.
APEX_EXPR='(http.request.full_uri wildcard r"https://rediacc.com/*")'
APEX_TARGET_EXPR='wildcard_replace(http.request.full_uri, r"https://rediacc.com/*", r"https://www.rediacc.com/${1}")'

HAS_APEX=$(jq -r --arg expr "$APEX_EXPR" '
  .result.rules[]?
  | select(.expression == $expr and .action == "redirect")
  | select(.action_parameters.from_value.status_code == 301)
  | .id
' <<<"$CURRENT")

if [[ -n "$HAS_APEX" ]]; then
  echo "[OK]   apex redirect rule present (id=$HAS_APEX)"
else
  echo "[MISS] apex redirect rule absent"
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "       (dry-run: would create it)"
    exit 0
  fi

  # Patch the ruleset with an additional rule. Using PATCH preserves existing rules.
  PAYLOAD=$(jq -n \
    --arg expr "$APEX_EXPR" \
    --arg target_expr "$APEX_TARGET_EXPR" '
    {
      rules: [{
        expression: $expr,
        action: "redirect",
        action_parameters: {
          from_value: {
            status_code: 301,
            preserve_query_string: true,
            target_url: { expression: $target_expr }
          }
        },
        description: "Redirect from root to WWW"
      }]
    }')

  RESP=$(curl -sSf "${AUTH[@]}" -X POST \
    -H "Content-Type: application/json" \
    -d "$PAYLOAD" \
    "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/rulesets/${RULESET_ID}/rules")

  NEW_ID=$(jq -r '.result.rules[-1].id // empty' <<<"$RESP")
  if [[ -n "$NEW_ID" ]]; then
    echo "[OK]   created apex redirect rule id=$NEW_ID"
  else
    echo "[FAIL] CF API did not return a rule id" >&2
    echo "$RESP" | jq . >&2
    exit 1
  fi
fi

# Smoke test (no-auth, follows public traffic path).
echo ""
echo "smoke test:"
STATUS=$(curl -sI "https://rediacc.com/solutions/backup-verification/" | head -1 | awk '{print $2}')
LOC=$(curl -sI "https://rediacc.com/solutions/backup-verification/" | grep -i '^location:' | awk '{print $2}' | tr -d '\r')
if [[ "$STATUS" == "301" ]] && [[ "$LOC" == *"www.rediacc.com"* ]]; then
  echo "[OK]   rediacc.com/* -> www.rediacc.com/* (live, 301)"
else
  echo "[WARN] smoke test unexpected: status=${STATUS} location=${LOC}" >&2
fi

# Advisory: console.rediacc.com is NOT proxied, so CF Redirect Rules can't catch it.
# Left as manual operator action — only 1 URL in the GSC 404 list.
CONSOLE_CNAME=$(
  curl -sSf "${AUTH[@]}" \
    "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/dns_records?name=console.rediacc.com" \
  | jq -r '.result[0] | "\(.content) proxied=\(.proxied)"'
)
echo ""
echo "advisory:"
echo "  console.rediacc.com -> ${CONSOLE_CNAME}"
echo "  Not proxied; CF Redirect Rules can't intercept it."
echo "  Fix (manual): flip proxied=true on that CNAME + add a redirect rule,"
echo "  OR change the CNAME to an orange-clouded host we control."
echo "  Priority: low (1 URL in GSC 404 list)."
