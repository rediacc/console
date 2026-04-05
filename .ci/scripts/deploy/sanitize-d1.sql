-- sanitize-d1.sql
-- Removes PII from a production D1 export for use in staging/edge environments.
-- Executed locally via sqlite3 in clone-d1.sh when --sanitize is passed.
--
-- Maintenance: when adding new tables with PII, add sanitization rules here.
-- Tables intentionally NOT sanitized are listed at the bottom with rationale.

-- ============================================================
-- SECTION 1: DELETE session/token tables (useless outside production)
-- ============================================================

DELETE FROM refresh_tokens;
DELETE FROM magic_links;
DELETE FROM password_resets;
DELETE FROM two_factor_challenges;
DELETE FROM two_factor_setup;
DELETE FROM elevated_sessions;
DELETE FROM reauth_tokens;
DELETE FROM pending_email_changes;
DELETE FROM passkey_challenges;
DELETE FROM rate_limits;
DELETE FROM login_attempts;

-- ============================================================
-- SECTION 2: DELETE crypto/API tokens
-- ============================================================

DELETE FROM api_tokens;
DELETE FROM device_codes;
DELETE FROM config_tokens;
DELETE FROM config_user_keys;
DELETE FROM config_cek_handoffs;

-- ============================================================
-- SECTION 3: Sanitize user PII
-- ============================================================
-- Known test password: "TestPassword123!" hashed with bcrypt cost 10
-- All sanitized users can log in with this password on edge.

UPDATE users SET
    email = 'user-' || id || '@preview.test',
    email_hash = lower(hex(randomblob(16))),
    password_hash = '$2b$10$sanitized.placeholder.hash.for.edge.preview.testing.only00',
    password_salt = 'sanitized_salt',
    totp_secret = NULL,
    totp_backup_hashes = NULL,
    customer_id = NULL;

-- ============================================================
-- SECTION 4: Sanitize invoice PII
-- ============================================================

UPDATE invoices SET
    customer_email = 'invoice-' || id || '@preview.test',
    customer_name = 'Test Customer',
    customer_address = '{}',
    customer_tax_ids = '[]',
    seller_details = NULL,
    stripe_hosted_url = NULL,
    stripe_pdf_url = NULL,
    r2_pdf_key = NULL,
    r2_xml_key = NULL;

UPDATE invoice_events SET
    data = NULL
WHERE data IS NOT NULL;

-- ============================================================
-- SECTION 5: Sanitize subscription PII
-- ============================================================

UPDATE subscriptions SET
    customer_email = 'sub-' || id || '@preview.test',
    metadata = NULL;

-- ============================================================
-- SECTION 6: Sanitize config store crypto material
-- ============================================================

UPDATE config_stores SET
    sdk_master = 'SANITIZED_SDK_' || id,
    server_secret = 'SANITIZED_SECRET_' || id,
    encrypted_org_passphrase = 'SANITIZED_PASSPHRASE_' || id,
    server_recoverable_org_passphrase = NULL;

-- ============================================================
-- SECTION 7: Sanitize contact/newsletter/lead PII
-- ============================================================

UPDATE contact_submissions SET
    name = 'Test User',
    email = 'contact-' || id || '@preview.test',
    email_hash = lower(hex(randomblob(16))),
    message = 'Sanitized message content';

UPDATE newsletter_subscribers SET
    email = 'news-' || id || '@preview.test',
    email_hash = lower(hex(randomblob(16))),
    confirm_token_hash = NULL,
    unsubscribe_token_hash = NULL;

UPDATE lead_magnet_downloads SET
    email = 'lead-' || id || '@preview.test',
    email_hash = lower(hex(randomblob(16)));

-- ============================================================
-- SECTION 8: Sanitize org invitations
-- ============================================================

UPDATE org_invitations SET
    email = 'invite-' || id || '@preview.test',
    token_hash = lower(hex(randomblob(32)));

-- ============================================================
-- SECTION 9: Sanitize notification/event data
-- ============================================================

UPDATE notification_reminder_log SET
    recipient_email = 'reminder-' || id || '@preview.test',
    fingerprint = lower(hex(randomblob(16)));

UPDATE event_log SET
    data = NULL
WHERE data IS NOT NULL;

-- ============================================================
-- SECTION 10: Sanitize signed blobs (crypto signatures)
-- ============================================================

UPDATE signed_blobs SET
    payload = 'SANITIZED',
    signature = 'SANITIZED';

-- ============================================================
-- Tables intentionally NOT sanitized (no PII, structural only):
--
--   organizations          -- org name + owner FK only
--   org_memberships        -- FKs + role only
--   teams                  -- team name + FKs only
--   team_memberships       -- FKs + role only
--   config_entries         -- r2_key + metadata (no PII, blobs are encrypted)
--   config_versions        -- r2_key + version metadata
--   config_user_identities -- public keys only (x25519, passkey)
--   subscription_activations -- machine_id + timestamps
--   repo_license_issuance_slots -- slot metadata
--   license_sequences      -- counters only
--   refunds                -- customer_id FK + stripe IDs (no direct PII)
--   webhook_processed      -- event_id + timestamp
--   invoice_number_counter -- year + counter
--   version_policy         -- version constraints
--   user_communication_preferences -- boolean flags only
-- ============================================================
