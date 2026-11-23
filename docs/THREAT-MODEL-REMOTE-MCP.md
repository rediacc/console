# Threat model: remote MCP

Scope: the hosted MCP endpoint (`mcp.<region>`), the agent grant behind each URL, the account Worker, the org executor container, MCP clients and the model provider the user connects. The local stdio server (`rdc mcp serve`) shares the decision function and is covered where it differs. Decisions cited as `Dn` are in `agent/programs/remote-mcp/02-decisions.md`. Each mitigation links the plan box that implements it as `PLAN-rmcp-<plan>.md#<box>`, and the box line states the test that proves it.

## Assets

| Asset | Where it lives | Why it matters |
|---|---|---|
| Config content (machines, repositories, credentials) | CEK-encrypted blobs in object storage, one subkey per config (D56) | Reaching it exposes SSH targets and repository passphrases |
| The CEK | Slot holders only; in executor RAM for the lifetime of a live grant (D8, D9) | Opens every config of the org |
| Agent bearer `rmcp_<grantId>.<S>` | The client's configuration; `S` is shown once and never stored by Rediacc (D9) | Acts as one user on one config until expiry or revocation |
| Policy record | Separate CEK-encrypted record with its own endpoint (D27) | Sets the ceiling for every agent and human |
| Tool output | Returned to the client and then the model provider | May contain machine names, logs and file content |

## Trust boundaries

1. Client and model provider to the MCP Worker (untrusted network, untrusted prompts).
2. MCP Worker to the account Worker (service binding; the bearer secret `S` stops at the MCP Worker, D13).
3. Account Worker to the org executor container (the container receives grant-scoped key material, never the long-term slot secrets).
4. Executor container to the user's machines (the existing SSH path).
5. Region to region (never crossed, D58).

## Threats and mitigations

### Leaked bearer URL or header

An attacker holding a bearer acts as the grant's user on the grant's one config until the grant ends.

- Lifetime is 7 days by default and 30 at most, one config per URL, one region per URL (D54, D55, D58): PLAN-rmcp-agent-grants.md#AG-LIFE, PLAN-rmcp-agent-grants.md#AG-REG, PLAN-rmcp-remote-worker.md#RW-SCOPE, PLAN-rmcp-remote-worker.md#RW-REG.
- The grant unwraps only its config's subkey, so no other config of the org is exposed (D56): PLAN-rmcp-policy-record.md#SK1, PLAN-rmcp-policy-record.md#SK2.
- The key material is split: the authentication tag and the wrapping key derive from `S`, and the slot key needs the server secret as well, so neither a database copy nor `S` alone opens the CEK: PLAN-rmcp-agent-grants.md#AG-C.
- Secrets never appear in a URL path or query, and a gate keeps request logging clean of them (D14): PLAN-rmcp-remote-worker.md#RW-T4, PLAN-rmcp-remote-worker.md#RW-D1.
- Revocation is pushed to the executor, and member removal, 2FA disablement, team archival, entitlement lapse and CEK rotation each end the affected grants: PLAN-rmcp-agent-grants.md#AG-S4, PLAN-rmcp-agent-grants.md#AG-S5.
- Creation needs 2FA and an elevated session, and sends an email: PLAN-rmcp-agent-grants.md#AG-S2.
- Unknown grants and wrong tags answer identically, and a burst of refusals from one grant raises an alert: PLAN-rmcp-remote-worker.md#RW-T4, PLAN-rmcp-remote-worker.md#RW-D3.
- A bearer cannot mint device tokens through the executor chain: PLAN-rmcp-writeback.md#WB4.

### Compromised proxy, MCP Worker or executor

A compromised component sees what it processes. The MCP Worker sees `S` on live requests; the executor holds a grant's config key in RAM; the account Worker sees neither `S` nor decrypted content (D13).

- The bearer secret never reaches the account Worker, and the executor holds only the one config's key: PLAN-rmcp-remote-worker.md#RW-T3, PLAN-rmcp-policy-record.md#SK2.
- Each region runs its own Workers, OAuth storage and executors, so a compromise stays in its region (D58): PLAN-rmcp-remote-worker.md#RW-REG.
- Executor sessions are keyed per grant and team, cached with a bounded lifetime, and revalidated against the account: PLAN-rmcp-executor-hardening.md#EH1, PLAN-rmcp-executor-hardening.md#EH2, PLAN-rmcp-executor-hardening.md#EH4, PLAN-rmcp-executor-hardening.md#EH5.
- Executor occupancy is not readable publicly (D52): PLAN-rmcp-executor-hardening.md#EH8.
- The on-premise daemon binds loopback by default and refuses a public bind without TLS: PLAN-rmcp-executor-hardening.md#EH9.
- Mutating commands fail closed when the audit route is unreachable: PLAN-rmcp-writeback.md#WB8.

The CEK-derived key stays reachable unattended for as long as a grant is live. This is the price of agent access without a human present and is listed under accepted risks.

### Malicious client metadata document and SSRF

OAuth clients identify themselves with a Client ID Metadata Document fetched by the authorization server, which makes the fetch an SSRF primitive and the displayed client name an impersonation vector.

- Client metadata URLs resolving to private, link-local or metadata-service addresses, or using a non-https scheme, are refused: PLAN-rmcp-remote-worker.md#RW-A1.
- Only PKCE with S256 is accepted, redirects match exactly, tokens are bound to one grant's resource, and refresh tokens rotate with reuse detection that revokes the family: PLAN-rmcp-remote-worker.md#RW-A1.
- Token lifetimes are capped at the grant expiry: PLAN-rmcp-remote-worker.md#RW-SCOPE.

### Phishing consent screen

An attacker links a victim to an authorization request naming a harmless-looking client.

- The consent page shows the client's name together with its domain, the config, scope, overrides and expiry, and the secret reaches the MCP Worker by form POST, never in a URL: PLAN-rmcp-remote-worker.md#RW-U.
- Granting needs a signed-in session with 2FA and an elevated session: PLAN-rmcp-agent-grants.md#AG-S2.
- The grants page lists every live URL for revocation: PLAN-rmcp-agent-grants.md#AG-W.

### Prompt injection through tool output

Content returned by a tool (logs, file names, repository text) can carry instructions aimed at the agent.

- Every tool call passes the one decision function. The agent's permission is the human opt-in AND the policy ceiling, so injected instructions cannot exceed what the human allowed: PLAN-rmcp-decide.md#D1, PLAN-rmcp-decide.md#D3, PLAN-rmcp-decide.md#D6.
- Tool annotations state read, write and destructive honestly so clients can gate them: PLAN-rmcp-local-mcp.md#LM5.
- A confirmation-class decision asks through elicitation, or a retry argument bound to the original arguments, and a tampered, replayed or cross-user confirmation state is refused: PLAN-rmcp-remote-worker.md#RW-T5.
- Policy edits are not a tool surface: they need 2FA and an elevated session in the portal, and a policy field pushed through a config is refused: PLAN-rmcp-policy-record.md#G1.
- Rate limits cap call volume and concurrency per grant: PLAN-rmcp-remote-worker.md#RW-T5, PLAN-rmcp-executor-hardening.md#EH12.

### Rollback or forgery of the policy record

An attacker with write access to storage replays an older, more permissive policy, or a member pushes a `policy` field inside a config.

- Policy lives in its own record, encrypted under the CEK with the store, config, team and version bound as additional authenticated data, so swapping any of them fails decryption: PLAN-rmcp-policy-record.md#S1.
- A policy field inside a remote config fails schema parsing, and a push carrying one is refused before the network: PLAN-rmcp-policy-record.md#S1, PLAN-rmcp-policy-record.md#G1.
- The CLI keeps a high-water mark of the policy version and refuses an older record: PLAN-rmcp-policy-record.md#C1.
- The effective policy is the org policy intersected with the team policy, deny wins, locked keys ignored: PLAN-rmcp-policy-record.md#S1.
- Policy history is an audit event only, so there are no stored versions to roll back to (D31).

### Stolen database copy or login token

- Slot secrets and the recovery kit are absent from any database dump, and password slots no longer exist, so nothing user-chosen remains to guess offline: PLAN-rmcp-policy-record.md#K1, PLAN-rmcp-policy-record.md#K2, PLAN-rmcp-policy-record.md#K5.
- Login tokens expire when idle and absolutely, device-code tokens are stored sealed, and strict rate limits are shared across instances: PLAN-rmcp-executor-hardening.md#EH10, PLAN-rmcp-executor-hardening.md#EH11, PLAN-rmcp-executor-hardening.md#EH12.

## Accepted risks

- **Model provider visibility.** Tool output reaches the model provider the user connects. Rediacc does not choose that provider, and some connectors are not eligible for zero data retention (Claude API MCP connector, `agent/programs/remote-mcp/03-external-research.md`). The privacy page says so (PLAN-rmcp-docs.md#DO11).
- **Live-grant key reachability.** While a grant is live, the executor can decrypt that one config without a human present. Expiry, revocation and the per-config subkey bound the exposure; they do not remove it.
- **Login password hashing.** Account login passwords use PBKDF2 at 100,000 iterations, the Workers Web Crypto ceiling (D35). A database copy enables offline guessing of weak passwords, and 2FA is the control.
- **Lost recovery kit.** The kit is the member's responsibility (D43). A store whose last key holder loses both passkey and kit is unrecoverable, so owners are advised to keep a second holder (D44).
- **On-premise host access.** On-premise, host access replaces the Worker-secret boundary: whoever reads the host environment reads the secrets the cloud keeps in Worker secrets (D48).
- **Removed member keeps pulled data.** Data already pulled stays with the member until a CEK rotation.
- **IP restriction.** Not offered (D2).
