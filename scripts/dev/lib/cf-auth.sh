#!/bin/bash
# Shared Cloudflare + AWS authentication for dev scripts.
#
# Source this file after common.sh. It provides:
#   - resolve_cf_auth:       Sets CF_AUTH_HEADERS array from env vars or interactive prompt
#   - resolve_aws_auth:      Exports AWS_ACCESS_KEY_ID/SECRET from AWS_SES_ADMIN_* env vars
#   - self_destruct_credentials: Deletes the CF token and/or AWS key used to run the script
#
# Env vars:
#   CF_MANAGEMENT_TOKEN  - Scoped API token (recommended, supports self-destruct)
#   CF_API_KEY + CF_EMAIL - Global API Key (legacy, cannot self-destruct)
#   AWS_SES_ADMIN_KEY_ID + AWS_SES_ADMIN_SECRET - IAM admin credentials

CF_API_BASE="https://api.cloudflare.com/client/v4"
CF_AUTH_HEADERS=()

# Resolve Cloudflare authentication.
# Sets CF_AUTH_HEADERS array for use with curl.
resolve_cf_auth() {
    if [[ -n "${CF_MANAGEMENT_TOKEN:-}" ]]; then
        CF_AUTH_HEADERS=(-H "Authorization: Bearer ${CF_MANAGEMENT_TOKEN}")
    elif [[ -n "${CF_API_KEY:-}" && -n "${CF_EMAIL:-}" ]]; then
        CF_AUTH_HEADERS=(-H "X-Auth-Key: ${CF_API_KEY}" -H "X-Auth-Email: ${CF_EMAIL}")
    else
        echo "Authentication method:"
        echo "  1) API Token (recommended, supports self-destruct)"
        echo "  2) Global API Key + Email"
        echo -n "Choose [1/2]: "
        read -r auth_choice
        if [[ "$auth_choice" == "2" ]]; then
            echo -n "Enter email: "
            read -r CF_EMAIL
            echo -n "Enter Global API Key: "
            read -rs CF_API_KEY
            echo
            CF_AUTH_HEADERS=(-H "X-Auth-Key: ${CF_API_KEY}" -H "X-Auth-Email: ${CF_EMAIL}")
        else
            echo -n "Enter API Token: "
            read -rs CF_MANAGEMENT_TOKEN
            echo
            CF_AUTH_HEADERS=(-H "Authorization: Bearer ${CF_MANAGEMENT_TOKEN}")
        fi
    fi

    if [[ ${#CF_AUTH_HEADERS[@]} -eq 0 ]]; then
        log_error "Cloudflare authentication credentials are required"
        exit 1
    fi
}

# Resolve AWS SES admin authentication.
# Exports standard AWS env vars for the aws CLI.
resolve_aws_auth() {
    if [[ -z "${AWS_SES_ADMIN_KEY_ID:-}" || -z "${AWS_SES_ADMIN_SECRET:-}" ]]; then
        log_error "AWS_SES_ADMIN_KEY_ID and AWS_SES_ADMIN_SECRET are required"
        exit 1
    fi
    export AWS_ACCESS_KEY_ID="$AWS_SES_ADMIN_KEY_ID"
    export AWS_SECRET_ACCESS_KEY="$AWS_SES_ADMIN_SECRET"
    export AWS_DEFAULT_REGION="${AWS_SES_ADMIN_REGION:-eu-central-1}"
}

# Verify self-destruct is possible (requires CF_MANAGEMENT_TOKEN).
# Call this during preflight if self-destruct is enabled.
check_self_destruct_capable() {
    if [[ -z "${CF_MANAGEMENT_TOKEN:-}" ]]; then
        log_error "Self-destruct requires CF_MANAGEMENT_TOKEN (scoped API token)"
        log_error "Global API Key cannot be deleted via API."
        log_error "Either use CF_MANAGEMENT_TOKEN, or pass --keep-credentials to skip self-destruct."
        exit 1
    fi
}

# Destroy credentials used to run the script.
# Deletes the CF management token (self-destruct) and optionally the AWS admin key.
# Args: [--aws] to also delete the AWS admin key
self_destruct_credentials() {
    local destroy_aws=false
    for arg in "$@"; do
        [[ "$arg" == "--aws" ]] && destroy_aws=true
    done

    log_step "=== Self-destruct: destroying credentials used for this run ==="

    # 1. AWS admin key (if requested)
    if [[ "$destroy_aws" == "true" && -n "${AWS_SES_ADMIN_KEY_ID:-}" ]]; then
        log_step "Deleting AWS admin key: $AWS_SES_ADMIN_KEY_ID"
        if ! aws iam delete-access-key --access-key-id "$AWS_SES_ADMIN_KEY_ID" 2>&1; then
            log_warn "Failed to delete AWS admin key: $AWS_SES_ADMIN_KEY_ID"
            log_warn "Manually delete it from: https://us-east-1.console.aws.amazon.com/iam/home#/security_credentials"
        else
            log_info "AWS admin key deleted"
        fi
    fi

    # 2. CF management token (self-destruct)
    if [[ -n "${CF_MANAGEMENT_TOKEN:-}" ]]; then
        log_step "Deleting CF management token..."
        local token_id
        token_id=$(curl -s -X GET "${CF_API_BASE}/user/tokens/verify" \
            "${CF_AUTH_HEADERS[@]}" -H "Content-Type: application/json" | jq -r '.result.id // empty')
        if [[ -n "$token_id" ]]; then
            curl -s -X DELETE "${CF_API_BASE}/user/tokens/$token_id" \
                "${CF_AUTH_HEADERS[@]}" -H "Content-Type: application/json" >/dev/null 2>&1
            log_info "CF management token deleted (self-destruct)"
        else
            log_warn "Could not determine CF token ID for self-destruct"
        fi
    fi
}
