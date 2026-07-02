#!/bin/bash
# Build the consolidated rediacc server image locally for testing.
#
# Usage:
#   scripts/docker/build-server.sh cloud   # builds rediacc-server-cloud:dev
#   scripts/docker/build-server.sh onprem  # builds rediacc-server-onprem:dev
#
# Tags are local-only (no ghcr.io/ prefix). They cannot be confused with --
# or accidentally pushed to -- the production registry path.
#
# Prerequisites:
#   - npm dependencies installed (run `npm ci` once)
#   - private/renet/bin/renet-linux-{amd64,arm64} present (run `./rdc.sh`
#     once to trigger the cross-compile, OR download from a recent CI run
#     with: gh run download <run-id> --name renet-binaries-<sha>)
#   - .env or shell env may set ACCOUNT_ED25519_PUBLIC_KEY (or it's read
#     from private/account/.env's ED25519_PUBLIC_KEY= line)

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd "$ROOT_DIR"

VARIANT="${1:-}"
case "$VARIANT" in
    cloud)
        ACCOUNT_ENTRY=node
        LOCAL_TAG=rediacc-server-cloud:dev
        ;;
    onprem)
        ACCOUNT_ENTRY=on-premise
        LOCAL_TAG=rediacc-server-onprem:dev
        ;;
    "")
        echo "usage: $0 <cloud|onprem>" >&2
        exit 2
        ;;
    *)
        echo "unknown variant: $VARIANT (expected cloud|onprem)" >&2
        exit 2
        ;;
esac

# Resolve account public key from environment or local account .env
ACCOUNT_KEY="${ACCOUNT_ED25519_PUBLIC_KEY:-}"
if [[ -z "$ACCOUNT_KEY" && -f private/account/.env ]]; then
    ACCOUNT_KEY=$(sed -n 's/^ED25519_PUBLIC_KEY=//p' private/account/.env | tr -d '\r')
fi

# Verify renet binaries exist (built by ./rdc.sh or downloaded from CI)
for arch in amd64 arm64; do
    if [[ ! -f "private/renet/bin/renet-linux-${arch}" ]]; then
        echo "error: missing private/renet/bin/renet-linux-${arch}" >&2
        echo "" >&2
        echo "Run ./rdc.sh once to trigger the cross-compile, or download from a" >&2
        echo "recent CI run:" >&2
        echo "  gh run list --workflow ci.yml --branch \$(git branch --show-current) --limit 5" >&2
        echo "  gh run download <run-id> --name renet-binaries-<sha>" >&2
        exit 1
    fi
done

echo "==> Staging build context..."

# Stage renet binaries (./binaries/ in build context, matches Dockerfile COPY)
mkdir -p binaries
cp "private/renet/bin/renet-linux-amd64" "binaries/renet-linux-amd64"
cp "private/renet/bin/renet-linux-arm64" "binaries/renet-linux-arm64"

# Stage marketing site
if [[ ! -d packages/www/dist ]]; then
    echo "==> Building packages/www..."
    (cd packages/www && npm run build)
fi
rm -rf www-assets
mkdir -p www-assets
cp -r packages/www/dist/. www-assets/

# Stage account portal SPA
if [[ ! -d private/account/web/dist ]]; then
    echo "==> Building private/account/web..."
    (cd private/account/web && npx vite build --outDir dist)
fi
rm -rf account-web-assets
mkdir -p account-web-assets
cp -r private/account/web/dist/. account-web-assets/

# Stage CLI npm tarball
echo "==> Packing CLI tarball..."
rm -rf cli-npm
mkdir -p cli-npm
(cd packages/cli && npm pack --pack-destination "$ROOT_DIR/cli-npm" >/dev/null)
(
    cd cli-npm
    # Bash glob + version sort: avoids parsing `ls` (shellcheck SC2012).
    # npm pack always produces exactly one tarball matching this glob.
    shopt -s nullglob
    pkgs=(rediacc-cli-*.tgz)
    shopt -u nullglob
    if ((${#pkgs[@]} == 0)); then
        echo "error: npm pack produced no rediacc-cli-*.tgz" >&2
        exit 1
    fi
    CLI_PKG=$(printf '%s\n' "${pkgs[@]}" | sort -V | tail -n 1)
    cp "$CLI_PKG" rediacc-cli-latest.tgz
)

echo "==> Building $LOCAL_TAG (--target $VARIANT)..."
docker buildx build \
    --file Dockerfile \
    --target "$VARIANT" \
    --build-arg ACCOUNT_ENTRY="$ACCOUNT_ENTRY" \
    --build-arg ACCOUNT_ED25519_PUBLIC_KEY="$ACCOUNT_KEY" \
    --build-arg VITE_APP_VERSION=dev \
    --tag "$LOCAL_TAG" \
    --load \
    .

echo ""
echo "Built: $LOCAL_TAG"
echo ""
echo "Run with:"
echo "  docker run --rm -p 8080:80 $LOCAL_TAG"
