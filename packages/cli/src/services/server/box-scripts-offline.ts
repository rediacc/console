/**
 * The shell the air-gapped install and the template-edit guard run on the box. Like box-scripts.ts,
 * a script reads its arguments as `$1...` and prints `key=value` lines; no secret is ever printed.
 */

/** The tools renet's offline setup needs already on the box (pkgset.Essentials by command, plus docker and its compose plugin). Prints `missing=<names>`. */
export const OFFLINE_ESSENTIALS = `
export PATH="$PATH:/sbin:/usr/sbin"
miss=""
for c in mkfs.btrfs cryptsetup ssh ip socat jq iptables git lsof killall rsync curl wget unzip docker; do
  command -v "$c" >/dev/null 2>&1 || miss="$miss $c"
done
docker compose version >/dev/null 2>&1 || miss="$miss docker-compose-plugin"
echo "missing=$miss"
`;

/** `$1` is an image ref: prints `traefik=present` when the machine's Docker already holds it, else `traefik=absent`. */
export const PROXY_IMAGE_PROBE = `
if docker image inspect "$1" >/dev/null 2>&1; then echo traefik=present; else echo traefik=absent; fi
`;

/** `$1` is an uploaded image tar: loaded into the machine's Docker (the proxy's daemon) and removed. */
export const PROXY_IMAGE_LOAD = `
set -eu
trap 'rm -f "$1"' EXIT
docker load -i "$1"
`;

/**
 * Record the sha256 of every file the template wrote (`$1` the repo dir, the file names on stdin),
 * so a later upgrade can tell a local edit from the template's own content.
 */
export const TEMPLATE_SUMS_WRITE = `
set -eu
cd "$1"
: > .template-sums.tmp
while IFS= read -r f; do
  [ -n "$f" ] || continue
  sha256sum -- "$f" >> .template-sums.tmp
done
mv .template-sums.tmp .template-sums
`;

/** Prints `baseline=none` (no sums were recorded) or `baseline=sums` plus one `edited=<file>` per file that no longer matches. */
export const TEMPLATE_EDITS = `
cd "$1"
if [ ! -f .template-sums ]; then echo baseline=none; exit 0; fi
echo baseline=sums
sha256sum -c .template-sums 2>/dev/null | grep -v ': OK$' | sed 's/: .*//; s/^/edited=/' || true
`;
