#!/bin/bash
# Version Management Script for GitHub Pages
# Manages versioned deployments with size-based cleanup

set -e

# Configuration
MAX_SIZE_MB=128
MAX_SIZE_BYTES=$((MAX_SIZE_MB * 1024 * 1024))
VERSIONS_DIR="versions"
KEEP_LATEST_COUNT=3  # Always keep at least this many versions regardless of size

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to get directory size in bytes
get_dir_size() {
    local dir="$1"
    if [ -d "$dir" ]; then
        du -sb "$dir" | cut -f1
    else
        echo "0"
    fi
}

# Function to format bytes to human readable
format_bytes() {
    local bytes=$1
    if [ $bytes -lt 1024 ]; then
        echo "${bytes}B"
    elif [ $bytes -lt $((1024 * 1024)) ]; then
        echo "$((bytes / 1024))KB"
    else
        echo "$((bytes / 1024 / 1024))MB"
    fi
}

# Function to extract semantic version from directory name (vX.Y.Z)
version_to_number() {
    local version="$1"
    # Remove 'v' prefix and convert to comparable number
    # v1.2.3 -> 1002003 (major*1000000 + minor*1000 + patch)
    version="${version#v}"
    IFS='.' read -r major minor patch <<< "$version"
    printf "%d%03d%03d" "${major:-0}" "${minor:-0}" "${patch:-0}"
}

# Function to list all version directories sorted by semantic version (newest first)
list_versions_sorted() {
    local gh_pages_dir="$1"

    if [ ! -d "$gh_pages_dir/$VERSIONS_DIR" ]; then
        return
    fi

    # List all version directories and sort by semantic version
    for version_dir in "$gh_pages_dir/$VERSIONS_DIR"/v*.*.*; do
        if [ -d "$version_dir" ]; then
            local version_name=$(basename "$version_dir")
            local version_number=$(version_to_number "$version_name")
            echo "$version_number $version_name"
        fi
    done | sort -rn | cut -d' ' -f2
}

# Function to cleanup old versions based on size constraint
cleanup_old_versions() {
    local gh_pages_dir="$1"
    local new_version_size="${2:-0}"

    log_info "Starting version cleanup (max size: $(format_bytes $MAX_SIZE_BYTES))..."

    if [ ! -d "$gh_pages_dir/$VERSIONS_DIR" ]; then
        log_info "No versions directory found, nothing to clean"
        return 0
    fi

    # Calculate current total size (excluding new version)
    local total_size=0
    local version_count=0
    local versions=()

    while IFS= read -r version_name; do
        local version_path="$gh_pages_dir/$VERSIONS_DIR/$version_name"
        local size=$(get_dir_size "$version_path")
        total_size=$((total_size + size))
        versions+=("$version_name:$size")
        version_count=$((version_count + 1))
    done < <(list_versions_sorted "$gh_pages_dir")

    log_info "Current versions: $version_count"
    log_info "Current total size: $(format_bytes $total_size)"
    log_info "New version size: $(format_bytes $new_version_size)"

    # Add new version size to total
    local projected_size=$((total_size + new_version_size))
    log_info "Projected size after deployment: $(format_bytes $projected_size)"

    # If within limits, no cleanup needed
    if [ $projected_size -le $MAX_SIZE_BYTES ]; then
        log_success "Size within limits, no cleanup needed"
        return 0
    fi

    log_warning "Projected size exceeds limit, cleanup required"

    # Start removing oldest versions (keeping at least KEEP_LATEST_COUNT)
    local removed_count=0
    local freed_space=0

    # Reverse the versions array to start from oldest
    local versions_reversed=()
    for ((i=${#versions[@]}-1; i>=0; i--)); do
        versions_reversed+=("${versions[$i]}")
    done

    for version_info in "${versions_reversed[@]}"; do
        local remaining_versions=$((version_count - removed_count))

        # Stop if we've reached minimum version count
        if [ $remaining_versions -le $KEEP_LATEST_COUNT ]; then
            log_warning "Reached minimum version count ($KEEP_LATEST_COUNT), stopping cleanup"
            break
        fi

        local version_name="${version_info%%:*}"
        local version_size="${version_info##*:}"
        local version_path="$gh_pages_dir/$VERSIONS_DIR/$version_name"

        # Check if removing this version would bring us under the limit
        local new_projected_size=$((projected_size - version_size))

        log_info "Removing old version: $version_name ($(format_bytes $version_size))"
        rm -rf "$version_path"

        removed_count=$((removed_count + 1))
        freed_space=$((freed_space + version_size))
        projected_size=$new_projected_size

        # If we're now under the limit, stop
        if [ $projected_size -le $MAX_SIZE_BYTES ]; then
            break
        fi
    done

    if [ $removed_count -gt 0 ]; then
        log_success "Removed $removed_count old version(s), freed $(format_bytes $freed_space)"
        log_info "New projected size: $(format_bytes $projected_size)"
    else
        log_warning "Could not remove any versions (minimum count reached)"
        log_warning "Final size will be: $(format_bytes $projected_size)"
    fi

    return 0
}

# Function to generate versions index page
generate_versions_index() {
    local gh_pages_dir="$1"
    local versions_file="$gh_pages_dir/$VERSIONS_DIR/index.html"

    log_info "Generating versions index page..."

    mkdir -p "$gh_pages_dir/$VERSIONS_DIR"

    # Start HTML
    cat > "$versions_file" << 'EOF'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Rediacc Console - Available Versions</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }

        .container {
            background: white;
            border-radius: 12px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            max-width: 800px;
            width: 100%;
            padding: 40px;
        }

        h1 {
            color: #333;
            margin-bottom: 10px;
            font-size: 2em;
        }

        .subtitle {
            color: #666;
            margin-bottom: 30px;
            font-size: 1.1em;
        }

        .version-list {
            list-style: none;
        }

        .version-item {
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            margin-bottom: 12px;
            transition: all 0.3s ease;
        }

        .version-item:hover {
            border-color: #667eea;
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.2);
            transform: translateY(-2px);
        }

        .version-link {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 20px;
            text-decoration: none;
            color: #333;
        }

        .version-info {
            flex: 1;
        }

        .version-tag {
            font-size: 1.3em;
            font-weight: 600;
            color: #667eea;
            margin-bottom: 5px;
        }

        .version-meta {
            font-size: 0.9em;
            color: #999;
        }

        .latest-badge {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 6px 16px;
            border-radius: 20px;
            font-size: 0.85em;
            font-weight: 600;
            margin-left: 15px;
        }

        .arrow {
            color: #667eea;
            font-size: 1.5em;
            margin-left: 15px;
        }

        .footer {
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #e0e0e0;
            text-align: center;
            color: #999;
            font-size: 0.9em;
        }

        .footer a {
            color: #667eea;
            text-decoration: none;
        }

        .footer a:hover {
            text-decoration: underline;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Rediacc Console</h1>
        <p class="subtitle">Available Versions</p>

        <ul class="version-list" id="versionList">
            <!-- Versions will be inserted here -->
        </ul>

        <div class="footer">
            <p>
                <a href="/">← Back to latest version</a> |
                <a href="https://github.com/rediacc/console" target="_blank">View on GitHub</a>
            </p>
        </div>
    </div>

    <script>
        // This will be populated by the build script
        const versions = VERSION_DATA_PLACEHOLDER;

        const versionList = document.getElementById('versionList');

        versions.forEach((version, index) => {
            const li = document.createElement('li');
            li.className = 'version-item';

            const isLatest = index === 0;

            li.innerHTML = `
                <a href="${version.path}" class="version-link">
                    <div class="version-info">
                        <div class="version-tag">${version.tag}</div>
                        <div class="version-meta">
                            Released: ${version.date} | Size: ${version.size}
                        </div>
                    </div>
                    ${isLatest ? '<span class="latest-badge">Latest</span>' : ''}
                    <span class="arrow">→</span>
                </a>
            `;

            versionList.appendChild(li);
        });
    </script>
</body>
</html>
EOF

    # Build versions data
    local versions_json="["
    local first=true

    while IFS= read -r version_name; do
        local version_path="/$VERSIONS_DIR/$version_name/"
        local version_size=$(get_dir_size "$gh_pages_dir/$VERSIONS_DIR/$version_name")
        local version_size_formatted=$(format_bytes $version_size)

        # Try to get release date from git tag (if available)
        local version_date="Unknown"
        if git show-ref --tags "$version_name" >/dev/null 2>&1; then
            version_date=$(git log -1 --format=%ai "$version_name" 2>/dev/null | cut -d' ' -f1 || echo "Unknown")
        fi

        if [ "$first" = false ]; then
            versions_json+=","
        fi
        first=false

        versions_json+="{\"tag\":\"$version_name\",\"path\":\"$version_path\",\"date\":\"$version_date\",\"size\":\"$version_size_formatted\"}"
    done < <(list_versions_sorted "$gh_pages_dir")

    versions_json+="]"

    # Replace placeholder with actual data
    sed -i "s|VERSION_DATA_PLACEHOLDER|$versions_json|g" "$versions_file"

    log_success "Versions index generated at $VERSIONS_DIR/index.html"
}

# Function to deploy a new version
deploy_version() {
    local gh_pages_dir="$1"
    local build_dir="$2"
    local version_tag="$3"

    log_info "Deploying version $version_tag..."

    # Get size of new version
    local new_version_size=$(get_dir_size "$build_dir")
    log_info "New version size: $(format_bytes $new_version_size)"

    # Run cleanup before deploying
    cleanup_old_versions "$gh_pages_dir" "$new_version_size"

    # Create versions directory structure
    mkdir -p "$gh_pages_dir/$VERSIONS_DIR"

    # Deploy to versioned subdirectory
    local version_path="$gh_pages_dir/$VERSIONS_DIR/$version_tag"
    log_info "Copying build to $VERSIONS_DIR/$version_tag/..."
    rm -rf "$version_path"
    cp -r "$build_dir" "$version_path"

    # Update root with latest version
    log_info "Updating root with latest version..."
    find "$gh_pages_dir" -maxdepth 1 -type f -delete
    find "$gh_pages_dir" -maxdepth 1 -type d ! -name "$VERSIONS_DIR" ! -name "." ! -name ".git" -exec rm -rf {} +
    cp -r "$build_dir"/* "$gh_pages_dir/"

    # Generate versions index
    generate_versions_index "$gh_pages_dir"

    # Create version manifest
    local manifest_file="$gh_pages_dir/versions.json"
    log_info "Creating versions manifest..."

    local versions_array="["
    local first=true
    while IFS= read -r version_name; do
        if [ "$first" = false ]; then
            versions_array+=","
        fi
        first=false
        versions_array+="\"$version_name\""
    done < <(list_versions_sorted "$gh_pages_dir")
    versions_array+="]"

    echo "{\"latest\":\"$version_tag\",\"versions\":$versions_array}" > "$manifest_file"

    log_success "Version $version_tag deployed successfully"
}

# Main command dispatcher
case "${1:-}" in
    cleanup)
        cleanup_old_versions "${2:-.}" "${3:-0}"
        ;;
    deploy)
        deploy_version "${2:-.}" "${3:-dist}" "${4:-v0.0.0}"
        ;;
    list)
        list_versions_sorted "${2:-.}"
        ;;
    generate-index)
        generate_versions_index "${2:-.}"
        ;;
    *)
        echo "Usage: $0 {cleanup|deploy|list|generate-index} [args...]"
        echo ""
        echo "Commands:"
        echo "  cleanup <gh-pages-dir> <new-version-size>  Clean old versions to fit size limit"
        echo "  deploy <gh-pages-dir> <build-dir> <version> Deploy new version with cleanup"
        echo "  list <gh-pages-dir>                        List all versions (newest first)"
        echo "  generate-index <gh-pages-dir>              Generate versions index page"
        echo ""
        echo "Example:"
        echo "  $0 deploy ./gh-pages ./dist v1.2.3"
        exit 1
        ;;
esac
