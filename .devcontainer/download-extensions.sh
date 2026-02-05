#!/usr/bin/env bash
# Download VS Code extensions from Open-VSX for pre-installation
# Extensions are stored in /opt/vscode-extensions/ for use by both
# GitHub Codespaces and self-hosted OpenVSCode Server
#
# Usage: ./download-extensions.sh
# Environment: VSCODE_EXTENSIONS_DIR (default: /opt/vscode-extensions)

set -euo pipefail

EXTENSIONS_DIR="${VSCODE_EXTENSIONS_DIR:-/opt/vscode-extensions}"
mkdir -p "$EXTENSIONS_DIR"

# Extension list - format: namespace.extension
# All extensions verified available on Open-VSX
EXTENSIONS=(
	"biomejs.biome"
	"dbaeumer.vscode-eslint"
	"GitHub.vscode-github-actions"
	"ms-playwright.playwright"
	"astro-build.astro-vscode"
	"golang.go"
	"ms-azuretools.vscode-docker"
	"redhat.vscode-yaml"
	"eamodio.gitlens"
	"ms-python.python"
)

download_extension() {
	local ext="$1"
	local namespace="${ext%%.*}"
	local name="${ext#*.}"

	echo "Downloading $ext from Open-VSX..."

	# Get latest version metadata
	local metadata
	metadata=$(curl -fsSL "https://open-vsx.org/api/${namespace}/${name}/latest" 2>/dev/null) || {
		echo "  WARNING: Could not fetch metadata for $ext, skipping"
		return 0
	}

	# Extract download URL from metadata
	local download_url
	download_url=$(echo "$metadata" | jq -r '.files.download // empty')

	if [ -z "$download_url" ]; then
		echo "  WARNING: No download URL found for $ext, skipping"
		return 0
	fi

	local version
	version=$(echo "$metadata" | jq -r '.version // "unknown"')
	local filename="${namespace}.${name}-${version}.vsix"

	if curl -fsSL -o "${EXTENSIONS_DIR}/${filename}" "$download_url"; then
		echo "  Downloaded: $filename"
	else
		echo "  WARNING: Failed to download $ext"
	fi
}

echo "========================================"
echo "Downloading ${#EXTENSIONS[@]} extensions from Open-VSX"
echo "Target directory: $EXTENSIONS_DIR"
echo "========================================"
echo ""

for ext in "${EXTENSIONS[@]}"; do
	download_extension "$ext"
done

echo ""
echo "========================================"
echo "Download complete"
echo "========================================"
ls -la "$EXTENSIONS_DIR"
