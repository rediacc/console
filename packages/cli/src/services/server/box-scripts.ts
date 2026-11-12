/**
 * The shell the install runs on the box, and the parsers for what it prints.
 *
 * Secrets are generated on the box and written only to the repo's `secrets.env` (0600). Values
 * the CLI sends (the cert, the renew token, the domain) travel on stdin, never in an argv a
 * process listing would show. The scripts print only public facts, except `READ_BUNDLE`, which
 * `rdc server backup` and the one-time recovery print run on purpose.
 */

import { shellQuote } from '../../utils/shell-quote.js';

/** What a value written into `secrets.env` may carry: neither compose's env reader nor `source` reads any of it specially. */
const ENV_SAFE = /^[A-Za-z0-9._~@%+=:,/-]*$/;
const ENV_KEY = /^[A-Z][A-Z0-9_]*$/;

/** The recovery bundle: what restoring the box needs that the box alone holds (private/elite/BACKUP.md). */
export const BUNDLE_KEYS = [
  'ACCOUNT_ED25519_PRIVATE_KEY',
  'ACCOUNT_ED25519_PUBLIC_KEY',
  'ACCOUNT_CONFIG_SERVER_KEY',
  'RUSTFS_ACCESS_KEY',
  'RUSTFS_SECRET_KEY',
] as const;

/** The public facts `status` and `upgrade` read back from the box. */
export const PUBLIC_KEYS = [
  'ACCOUNT_ED25519_PUBLIC_KEY',
  'DELEGATION_CERT_BASE64',
  'ELITE_DOMAIN',
  'ELITE_STORE_DOMAIN',
  'ELITE_IMAGE',
  'TAG',
] as const;

/** `sh -c <script> server <args...>`, under `sudo -n` when the box needs root for the repo mount. */
export function shCommand(script: string, args: string[], sudo = true): string {
  const parts = ['sh', '-c', shellQuote(script), 'server', ...args.map(shellQuote)];
  return (sudo ? ['sudo', '-n', ...parts] : parts).join(' ');
}

/**
 * The preflight probe: `$1` is the datastore path, `$2` the renet path. Runs as the SSH user;
 * only `sudo -n` itself and the port-holder lookup need root.
 */
export const PREFLIGHT = `
if sudo -n true >/dev/null 2>&1; then echo sudo=1; else echo sudo=0; fi
echo arch=$(uname -m)
echo epoch=$(date +%s)
if [ -x "$2" ] || command -v renet >/dev/null 2>&1; then echo renet=1; else echo renet=0; fi
d="$1"; while [ ! -d "$d" ]; do d=$(dirname "$d"); done
echo free_kb=$(df -Pk "$d" | awk 'NR==2 {print $4}')
for p in 80 443; do
  h=$(sudo -n ss -ltnpH "sport = :$p" 2>/dev/null | head -n 1 | tr '\\n' ' ')
  echo "port$p=$h"
done
`;

/**
 * Generate every secret the stack needs, on the box, into `$1/secrets.env`; a key already present is
 * kept, so a rerun converges. Prints only the Ed25519 public key, which the delegation cert names.
 */
export const KEYGEN = `
set -eu
f="$1/secrets.env"
umask 077
[ -f "$f" ] || : > "$f"
chmod 600 "$f"
have() { grep -q "^$1=..*" "$f"; }
put() { { grep -v "^$1=" "$f" || true; } > "$f.tmp"; printf '%s=%s\\n' "$1" "$2" >> "$f.tmp"; mv "$f.tmp" "$f"; chmod 600 "$f"; }
rnd() { openssl rand -base64 48 | tr -d '/+=\\n' | cut -c1-64; }
pair() {
  k=$(openssl genpkey -algorithm "$1" -outform DER | base64 | tr -d '\\n')
  p=$(printf '%s' "$k" | base64 -d | openssl pkey -inform DER -pubout -outform DER | base64 | tr -d '\\n')
}
if ! have ACCOUNT_ED25519_PRIVATE_KEY; then pair ed25519; put ACCOUNT_ED25519_PRIVATE_KEY "$k"; put ACCOUNT_ED25519_PUBLIC_KEY "$p"; fi
if ! have ACCOUNT_X25519_PRIVATE_KEY; then pair x25519; put ACCOUNT_X25519_PRIVATE_KEY "$k"; put ACCOUNT_X25519_PUBLIC_KEY "$p"; fi
for v in ACCOUNT_SERVER_API_KEY ACCOUNT_JWT_SECRET RUSTFS_SECRET_KEY; do have "$v" || put "$v" "$(rnd)"; done
have RUSTFS_ACCESS_KEY || put RUSTFS_ACCESS_KEY "$(rnd | cut -c1-20)"
have ACCOUNT_CONFIG_SERVER_KEY || put ACCOUNT_CONFIG_SERVER_KEY "$(openssl rand -base64 32 | tr -d '\\n')"
echo "ACCOUNT_ED25519_PUBLIC_KEY=$(grep '^ACCOUNT_ED25519_PUBLIC_KEY=' "$f" | cut -d= -f2-)"
`;

/** Set each `KEY=value` line read from stdin in `$1/secrets.env`, replacing an earlier line of that key. */
export const SET_ENV = `
set -eu
f="$1/secrets.env"
umask 077
[ -f "$f" ] || : > "$f"
while IFS= read -r line; do
  [ -n "$line" ] || continue
  key=\${line%%=*}
  { grep -v "^$key=" "$f" || true; } > "$f.tmp"
  printf '%s\\n' "$line" >> "$f.tmp"
  mv "$f.tmp" "$f"
done
chmod 600 "$f"
`;

/** The named keys of `$1/secrets.env`, plus the template's `VERSION` (`$1/VERSION`, absent reads as nothing). */
export function readKeysScript(keys: readonly string[]): string {
  const pattern = keys.join('|');
  return `
f="$1/secrets.env"
[ -f "$f" ] || { echo "secrets.env is missing" >&2; exit 3; }
grep -E '^(${pattern})=' "$f" || true
if [ -f "$1/VERSION" ]; then echo "VERSION=$(head -n 1 "$1/VERSION" | tr -dc '0-9')"; fi
`;
}

/**
 * Install a bring-your-own certificate for one host through renet (C6). The PEM pair arrives on
 * stdin, the cert first, separated by a line holding only `--RDC-SPLIT--`; the files live in a
 * root-only temporary directory removed on exit. `$1` is the renet path, `$2` the host.
 */
export const BYO_CERT = `
set -eu
umask 077
t=$(mktemp -d)
trap 'rm -rf "$t"' EXIT
awk -v d="$t" 'BEGIN {o = d "/cert.pem"} /^--RDC-SPLIT--$/ {o = d "/key.pem"; next} {print > o}'
"$1" proxy cert install --domain "$2" --cert "$t/cert.pem" --key "$t/key.pem"
`;

export const BYO_SPLIT = '--RDC-SPLIT--';

/** `docker pull` inside the repo's own daemon. `$1` is the daemon socket, `$2` the image ref. */
export const PULL_IMAGE = `
set -eu
DOCKER_HOST="unix://$1" docker pull "$2"
`;

/** `KEY=value` lines into a map; later lines win, other lines are ignored. */
export function parseEnvLines(text: string): Partial<Record<string, string>> {
  const out: Partial<Record<string, string>> = {};
  for (const raw of text.split('\n')) {
    const line = raw.trim();
    const eq = line.indexOf('=');
    if (eq <= 0) continue;
    const key = line.slice(0, eq);
    if (!ENV_KEY.test(key) && !/^[a-z0-9_]+$/.test(key)) continue;
    let value = line.slice(eq + 1);
    if (value.length >= 2 && value.startsWith('"') && value.endsWith('"')) {
      value = value.slice(1, -1);
    }
    out[key] = value;
  }
  return out;
}

/** The stdin `SET_ENV` reads. A key or value outside the safe set throws naming the key, never the value. */
export function envStdin(values: Record<string, string>): string {
  const lines: string[] = [];
  for (const [key, value] of Object.entries(values)) {
    if (!ENV_KEY.test(key)) throw new Error(`invalid secrets.env key ${key}`);
    if (!ENV_SAFE.test(value)) {
      throw new Error(`${key} carries a character secrets.env cannot hold safely`);
    }
    lines.push(`${key}=${value}`);
  }
  return `${lines.join('\n')}\n`;
}
