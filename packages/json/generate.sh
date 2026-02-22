#!/bin/bash

# Self-Contained Template Catalog Generator
# Processes template directories and generates JSON catalog with GitHub Pages website
#
# Features:
# - Converts template directories to individual JSON files
# - Generates master catalog.json with all templates
# - Creates GitHub Pages website with interactive catalog
# - Minifies JSON files for optimal performance
# - Supports nested template organization by category
#
# Usage: ./generate.sh
#
# Dependencies: python3, jq

set -e  # Exit on any error

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$SCRIPT_DIR"
BUILD_DIR="$SCRIPT_DIR/dist"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Skip list for templates
declare -a SKIP_LIST=()

# Load skip list from .templates-skiplist file
load_skip_list() {
    local skiplist_file="$SCRIPT_DIR/.templates-skiplist"
    if [[ -f "$skiplist_file" ]]; then
        log_info "Loading skip list from .templates-skiplist"
        while IFS= read -r line; do
            # Skip comments and empty lines
            if [[ ! "$line" =~ ^#.*$ ]] && [[ -n "$line" ]]; then
                SKIP_LIST+=("$line")
                log_info "  ⏭️  Will skip: $line"
            fi
        done < "$skiplist_file"
    fi
}

# Check if template should be skipped
should_skip_template() {
    local template_path="$1"
    for skip in "${SKIP_LIST[@]}"; do
        if [[ "$template_path" == "$skip" ]]; then
            return 0  # Should skip
        fi
    done
    return 1  # Should not skip
}

# Template Processing Functions
# Converts template directories to JSON format

# Function to escape JSON strings
json_escape() {
    local string="$1"
    string="${string//\\/\\\\}"
    string="${string//\"/\\\"}"
    string="${string//$'\n'/\\n}"
    string="${string//$'\r'/\\r}"
    string="${string//$'\t'/\\t}"
    echo "$string"
}

# Function to read file content and escape for JSON
read_file_content() {
    local file="$1"
    if [[ -f "$file" ]]; then
        json_escape "$(cat "$file")"
    else
        echo ""
    fi
}

# Function to get template metadata from README
extract_template_metadata() {
    local template_dir="$1"
    local template_name="$(basename "$template_dir")"
    local readme_file="$template_dir/README.md"

    # Extract title (first header)
    local title="$template_name"
    if [[ -f "$readme_file" ]]; then
        title=$(grep -m1 '^#[^#]' "$readme_file" 2>/dev/null | sed 's/^# *//' || echo "$template_name")
    fi

    # Extract description (first paragraph after title)
    local description=""
    if [[ -f "$readme_file" ]]; then
        description=$(awk '/^#[^#]/{found=1; next} found && /^$/{next} found && /^[^#]/ {print; exit}' "$readme_file" 2>/dev/null | head -1 || echo "")
    fi

    # Default description if empty
    if [[ -z "$description" ]]; then
        description="Template for $template_name"
    fi

    echo "$title|$description"
}

# Function to check if directory should be excluded
should_exclude_directory() {
    local dir_name="$1"
    local exclude_dirs=("dist" "assets" "catalog" "config" "templates" ".github")

    # Check if it's a hidden directory
    if [[ "$dir_name" =~ ^\..*$ ]]; then
        return 0  # Should exclude
    fi

    # Check if it's a file (ends with extension)
    if [[ "$dir_name" == *.* ]]; then
        return 0  # Should exclude files
    fi

    # Check against exclude list
    for exclude in "${exclude_dirs[@]}"; do
        if [[ "$dir_name" == "$exclude" ]]; then
            return 0  # Should exclude
        fi
    done

    return 1  # Should not exclude
}

# Function to get file type based on extension
get_file_type() {
    local filename="$1"
    case "${filename##*.}" in
        md) echo "markdown" ;;
        yaml|yml) echo "yaml" ;;
        json) echo "json" ;;
        sh) echo "script" ;;
        env) echo "environment" ;;
        dockerfile|Dockerfile) echo "dockerfile" ;;
        *) echo "text" ;;
    esac
}

# Function to generate individual template JSON file
generate_template_json() {
    local template_dir="$1"
    local output_file="$2"
    local template_name="$(basename "$template_dir")"
    local category="$(basename $(dirname "$template_dir"))"

    echo "Processing template: $category/$template_name"

    # Extract metadata
    local metadata=$(extract_template_metadata "$template_dir")
    local title="$(echo "$metadata" | cut -d'|' -f1)"
    local description="$(echo "$metadata" | cut -d'|' -f2)"

    # Create template ID from category and name
    local template_id="${category}_${template_name}"

    # Start JSON structure
    cat > "$output_file" << EOF
{
  "id": "$template_id",
  "name": "$title",
  "description": "$(json_escape "$description")",
  "category": "$category",
  "tags": ["$category", "$template_name"],
  "files": [
EOF

    local first=true

    # Process all files in template directory
    while IFS= read -r -d '' file; do
        local relative_path="${file#$template_dir/}"
        local filename=$(basename "$file")

        # Skip hidden files and directories, except .env files
        if [[ -d "$file" ]]; then
            continue
        fi

        # Skip hidden files except .env
        if [[ "$filename" =~ ^\..*$ ]] && [[ "$filename" != ".env" ]]; then
            continue
        fi

        if [[ "$first" == "true" ]]; then
            first=false
        else
            echo "," >> "$output_file"
        fi

        # Add file to JSON
        cat >> "$output_file" << EOF
    {
      "name": "$(json_escape "$filename")",
      "path": "$(json_escape "$template_name/$relative_path")",
      "type": "$(get_file_type "$filename")",
      "content": "$(read_file_content "$file")"
    }
EOF

    done < <(find "$template_dir" -maxdepth 1 -type f -print0 | sort -z)

    # Close JSON structure
    cat >> "$output_file" << EOF

  ],
  "readme": "$(read_file_content "$template_dir/README.md")",
  "generated": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
}
EOF
}

# Function to generate master catalog JSON
generate_catalog_json() {
    local templates_dir="$1"
    local output_file="$2"

    echo "Generating template catalog..."

    # Count valid templates by finding all template directories recursively
    # Include skipped templates in count for full transparency
    local template_count=0
    for template_dir in $(find "$templates_dir" -mindepth 2 -maxdepth 2 -type d); do
        if [[ -f "$template_dir/README.md" ]] || [[ -f "$template_dir/docker-compose.yaml" ]] || [[ -f "$template_dir/Rediaccfile" ]]; then
            template_count=$((template_count + 1))
        fi
    done

    # Start catalog structure
    cat > "$output_file" << EOF
{
  "version": "1.0",
  "generated": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "total_templates": $template_count,
  "categories": [],
  "templates": [
EOF

    local first=true
    local categories=()

    # Process each template directory recursively
    while IFS= read -r -d '' template_dir; do
        if [[ -f "$template_dir/README.md" ]] || [[ -f "$template_dir/docker-compose.yaml" ]] || [[ -f "$template_dir/Rediaccfile" ]]; then
            local template_name="$(basename "$template_dir")"
            local category_path="$(dirname "$template_dir" | sed 's|.*/templates||' | sed 's|^/||')"
            local category="$(echo "$category_path" | cut -d'/' -f1)"
            local template_path="${category}/${template_name}"

            # Check if template is in skip list
            local template_status="active"
            if should_skip_template "$template_path"; then
                template_status="skipped"
            fi

            local metadata=$(extract_template_metadata "$template_dir")
            local title="$(echo "$metadata" | cut -d'|' -f1)"
            local description="$(echo "$metadata" | cut -d'|' -f2)"
            local template_id="${category}_${template_name}"

            # Track categories
            if [[ ! " ${categories[@]} " =~ " ${category} " ]]; then
                categories+=("$category")
            fi

            # Count files in template
            local file_count=$(find "$template_dir" -maxdepth 1 -type f | wc -l)
            local has_readme=$([ -f "$template_dir/README.md" ] && echo "true" || echo "false")
            local has_docker=$([ -f "$template_dir/docker-compose.yaml" ] && echo "true" || echo "false")

            if [[ "$first" == "true" ]]; then
                first=false
            else
                echo "," >> "$output_file"
            fi

            # Add template to catalog
            cat >> "$output_file" << EOF
    {
      "id": "$template_id",
      "name": "$title",
      "description": "$(json_escape "$description")",
      "category": "$category",
      "tags": ["$category", "$template_name"],
      "file_count": $file_count,
      "has_readme": $has_readme,
      "has_docker": $has_docker,
      "status": "$template_status",
      "download_url": "templates/$template_id.json",
      "readme": "$(read_file_content "$template_dir/README.md")"
    }
EOF
        fi
    done < <(find "$templates_dir" -mindepth 2 -maxdepth 2 -type d -print0 | sort -z)

    # Close templates array and add categories
    echo "" >> "$output_file"
    echo "  ]," >> "$output_file"
    echo '  "categories": [' >> "$output_file"

    local first=true
    for category in $(printf '%s\n' "${categories[@]}" | sort); do
        if [[ "$first" == "true" ]]; then
            first=false
        else
            echo "," >> "$output_file"
        fi
        echo "    \"$category\"" >> "$output_file"
    done

    echo "" >> "$output_file"
    echo "  ]" >> "$output_file"
    echo "}" >> "$output_file"
}

# Function to copy template assets to build directory
copy_template_assets() {
    local templates_dir="$1"
    local assets_output_dir="$2"

    echo "Copying template assets..."

    # Copy any assets found in template directories
    find "$templates_dir" -name "assets" -type d | while read -r assets_dir; do
        if [[ -d "$assets_dir" ]]; then
            local template_path="${assets_dir%/assets}"
            local template_name="$(basename "$template_path")"
            local category_path="$(dirname "$template_path" | sed 's|.*/templates/||')"
            local category="$(echo "$category_path" | cut -d'/' -f1)"

            mkdir -p "$assets_output_dir/$category"
            cp -r "$assets_dir"/* "$assets_output_dir/$category/" 2>/dev/null || true
        fi
    done

    echo "Template assets copied"
}

# Logging functions
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

# Function to clean build directory
clean_build() {
    log_info "Cleaning build directory..."
    rm -rf "$BUILD_DIR"
    mkdir -p "$BUILD_DIR"/{templates,configs,assets}
    log_success "Build directory cleaned"
}

# Function to process templates
process_templates() {
    log_info "Processing templates..."


    local templates_dir="$SOURCE_DIR/templates"
    local output_dir="$BUILD_DIR/templates"

    # Exclude generator, config, and dist directories from template processing
    local exclude_dirs=("dist" "assets" "catalog" "config" ".github")

    local processed=0

    # Process each template directory recursively (category/template structure)
    for template_dir in $(find "$templates_dir" -mindepth 2 -maxdepth 2 -type d); do
        if [[ -f "$template_dir/README.md" ]] || [[ -f "$template_dir/docker-compose.yaml" ]] || [[ -f "$template_dir/Rediaccfile" ]]; then
            local template_name="$(basename "$template_dir")"
            local category="$(basename $(dirname "$template_dir"))"
            local template_path="${category}/${template_name}"
            local template_id="${category}_${template_name}"

            # Skip if in skip list
            if should_skip_template "$template_path"; then
                continue
            fi

            local output_file="$output_dir/$template_id.json"
            generate_template_json "$template_dir" "$output_file"
            processed=$((processed + 1))
        fi
    done

    log_success "Processed $processed templates"

    # Generate master templates index
    log_info "Generating templates index..."
    generate_catalog_json "$templates_dir" "$BUILD_DIR/templates.json"
    log_success "Templates index generated"

    # Copy assets
    copy_template_assets "$templates_dir" "$BUILD_DIR/assets"
    log_success "Template assets copied"
}

# Function to process configuration files
process_configs() {
    log_info "Processing configuration files..."

    local configs_dir="$SOURCE_DIR/config"
    local output_dir="$BUILD_DIR/configs"

    local processed=0

    # Copy config files from config directory
    for config_file in "$configs_dir"/*.json; do
        if [[ -f "$config_file" ]]; then
            local filename="$(basename "$config_file")"
            # Only copy config files (endpoints, pricing, services, tiers)
            if [[ "$filename" == "endpoints.json" ]] || [[ "$filename" == "pricing.json" ]] || [[ "$filename" == "services.json" ]] || [[ "$filename" == "tiers.json" ]]; then
                cp "$config_file" "$output_dir/$filename"
                processed=$((processed + 1))
            fi
        fi
    done

    log_success "Processed $processed configuration files"
}

# Function to generate GitHub Pages website
generate_website() {
    log_info "Generating GitHub Pages website..."

    # Copy website files from src directory
    log_info "Copying website templates..."
    cp "$SOURCE_DIR/src/index.html" "$BUILD_DIR/index.html"
    cp "$SOURCE_DIR/src/_config.yml" "$BUILD_DIR/_config.yml"
    cp "$SOURCE_DIR/src/api.html" "$BUILD_DIR/api.html"

    # Legacy heredoc removed - files now maintained in src/ directory
    # This comment block replaces the old heredoc for index.html
    : << 'HEREDOC_REMOVED'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Rediacc Repository Template Catalog</title>

    <!-- Markdown and Syntax Highlighting Libraries -->
    <script src="https://cdn.jsdelivr.net/npm/marked@11.1.1/marked.min.js"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/vs2015.min.css">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>

    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; background: #f5f7fa; }
        .container { max-width: 75rem; margin: 0 auto; padding: 1.25rem; }
        header { text-align: center; margin-bottom: 2.5rem; background: white; padding: 2.5rem; border-radius: 0.625rem; box-shadow: 0 0.125rem 0.625rem rgba(0,0,0,0.1); }
        h1 { color: #2c3e50; font-size: 2.5rem; margin-bottom: 0.625rem; }
        .subtitle { color: #7f8c8d; font-size: 1.1rem; }
        .stats { display: flex; justify-content: center; gap: 1.875rem; margin-top: 1.25rem; }
        .stat { text-align: center; }
        .stat-number { font-size: 2rem; font-weight: bold; color: #3498db; }
        .stat-label { color: #7f8c8d; font-size: 0.9rem; }
        .filters { background: white; padding: 1.25rem; border-radius: 0.625rem; margin-bottom: 1.875rem; box-shadow: 0 0.125rem 0.625rem rgba(0,0,0,0.1); }
        .filter-group { display: flex; gap: 0.9375rem; align-items: center; flex-wrap: wrap; }
        .filter-group label { font-weight: 500; color: #2c3e50; }
        input, select { padding: 0.5rem 0.75rem; border: 0.125rem solid #e0e6ed; border-radius: 0.3125rem; font-size: 0.875rem; }
        input:focus, select:focus { outline: none; border-color: #3498db; }
        .templates-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(21.875rem, 1fr)); gap: 1.5625rem; }
        .template-card { background: white; border-radius: 0.625rem; overflow: hidden; box-shadow: 0 0.125rem 0.625rem rgba(0,0,0,0.1); transition: transform 0.2s, box-shadow 0.2s; }
        .template-card:hover { transform: translateY(-0.125rem); box-shadow: 0 0.25rem 1.25rem rgba(0,0,0,0.15); }
        .template-header { padding: 1.25rem; border-bottom: 0.0625rem solid #e0e6ed; }
        .template-title { font-size: 1.3rem; font-weight: 600; color: #2c3e50; margin-bottom: 0.5rem; }
        .template-meta { display: flex; gap: 0.625rem; align-items: center; margin-bottom: 0.625rem; }
        .template-category { background: #3498db; color: white; padding: 0.25rem 0.5rem; border-radius: 0.9375rem; font-size: 0.8rem; font-weight: 500; }
        .template-files { background: #ecf0f1; color: #7f8c8d; padding: 0.25rem 0.5rem; border-radius: 0.9375rem; font-size: 0.8rem; }
        .template-description { color: #7f8c8d; line-height: 1.5; }
        .template-actions { padding: 1.25rem; background: #f8f9fa; }
        .btn { display: inline-block; padding: 0.625rem 1.25rem; background: #3498db; color: white; text-decoration: none; border-radius: 0.3125rem; font-weight: 500; transition: background 0.2s; cursor: pointer; border: none; }
        .btn:hover { background: #2980b9; }
        .btn-secondary { background: #95a5a6; }
        .btn-secondary:hover { background: #7f8c8d; }
        .no-results { text-align: center; color: #7f8c8d; font-size: 1.2rem; margin-top: 3.75rem; }
        .api-docs { background: white; padding: 1.875rem; border-radius: 0.625rem; margin-top: 2.5rem; box-shadow: 0 0.125rem 0.625rem rgba(0,0,0,0.1); }
        .api-title { font-size: 1.5rem; color: #2c3e50; margin-bottom: 1.25rem; }
        .endpoint { background: #f8f9fa; padding: 0.9375rem; border-radius: 0.3125rem; margin-bottom: 0.9375rem; font-family: 'Monaco', 'Menlo', monospace; }
        .method { background: #27ae60; color: white; padding: 0.125rem 0.5rem; border-radius: 0.1875rem; font-size: 0.8rem; margin-right: 0.625rem; }

        /* Modal Styles */
        .modal-overlay {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.6);
            backdrop-filter: blur(0.25rem);
            z-index: 1000;
            animation: fadeIn 0.2s ease-in-out;
        }

        .modal-overlay.active {
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 1.25rem;
        }

        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }

        @keyframes slideUp {
            from {
                opacity: 0;
                transform: translateY(1.875rem);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        .modal-container {
            background: white;
            border-radius: 0.75rem;
            max-width: 87.5rem;
            width: 100%;
            height: 90vh;
            display: flex;
            flex-direction: column;
            box-shadow: 0 1.25rem 3.75rem rgba(0, 0, 0, 0.3);
            animation: slideUp 0.3s ease-out;
        }

        .modal-header {
            padding: 1.5625rem 1.875rem;
            border-bottom: 0.0625rem solid #e0e6ed;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-shrink: 0;
        }

        .modal-header-content {
            display: flex;
            align-items: center;
            gap: 0.9375rem;
        }

        .modal-icon {
            font-size: 2.5rem;
        }

        .modal-title-group h2 {
            color: #2c3e50;
            font-size: 1.8rem;
            margin-bottom: 0.3125rem;
        }

        .modal-tags {
            display: flex;
            gap: 0.5rem;
            flex-wrap: wrap;
        }

        .modal-tag {
            background: #3498db;
            color: white;
            padding: 0.25rem 0.75rem;
            border-radius: 0.9375rem;
            font-size: 0.85rem;
            font-weight: 500;
        }

        .modal-close {
            background: none;
            border: none;
            font-size: 2rem;
            color: #7f8c8d;
            cursor: pointer;
            padding: 0.3125rem 0.625rem;
            transition: color 0.2s;
        }

        .modal-close:hover {
            color: #2c3e50;
        }

        .modal-tabs {
            display: flex;
            padding: 0 1.875rem;
            background: #f8f9fa;
            border-bottom: 0.125rem solid #e0e6ed;
            flex-shrink: 0;
        }

        .modal-tab {
            padding: 0.9375rem 1.5625rem;
            background: none;
            border: none;
            color: #7f8c8d;
            font-size: 1rem;
            font-weight: 500;
            cursor: pointer;
            position: relative;
            transition: color 0.2s;
        }

        .modal-tab:hover {
            color: #2c3e50;
        }

        .modal-tab.active {
            color: #3498db;
        }

        .modal-tab.active::after {
            content: '';
            position: absolute;
            bottom: -0.125rem;
            left: 0;
            right: 0;
            height: 0.125rem;
            background: #3498db;
        }

        .modal-body {
            flex: 1;
            overflow-y: auto;
            padding: 1.875rem;
            min-height: 0;
        }

        .tab-content {
            display: none;
            height: 100%;
        }

        .tab-content.active {
            display: block;
        }

        /* Overview Tab */
        .overview-content {
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 1.875rem;
            height: 100%;
        }

        .readme-section, .features-section {
            background: #f8f9fa;
            padding: 1.5625rem;
            border-radius: 0.625rem;
            overflow-y: auto;
        }

        .section-title {
            font-size: 1.3rem;
            color: #2c3e50;
            margin-bottom: 0.9375rem;
            font-weight: 600;
        }

        .readme-content {
            color: #333;
            line-height: 1.8;
        }

        .readme-content h1 { font-size: 1.8rem; margin: 1.25rem 0 0.625rem; color: #2c3e50; }
        .readme-content h2 { font-size: 1.5rem; margin: 1.125rem 0 0.625rem; color: #2c3e50; }
        .readme-content h3 { font-size: 1.3rem; margin: 0.9375rem 0 0.5rem; color: #34495e; }
        .readme-content p { margin: 0.625rem 0; }
        .readme-content ul, .readme-content ol { margin: 0.625rem 0 0.625rem 1.5625rem; }
        .readme-content li { margin: 0.3125rem 0; }
        .readme-content code { background: #2c3e50; color: #ecf0f1; padding: 0.125rem 0.375rem; border-radius: 0.1875rem; font-size: 0.9em; }
        .readme-content pre { background: #2c3e50; color: #ecf0f1; padding: 0.9375rem; border-radius: 0.3125rem; overflow-x: auto; margin: 0.9375rem 0; }
        .readme-content pre code { background: none; padding: 0; }
        .readme-content blockquote { border-left: 0.25rem solid #3498db; padding-left: 0.9375rem; margin: 0.9375rem 0; color: #555; }

        .feature-list {
            list-style: none;
        }

        .feature-item {
            display: flex;
            align-items: center;
            gap: 0.625rem;
            margin-bottom: 0.75rem;
            color: #555;
        }

        .feature-icon {
            color: #27ae60;
            font-size: 1.2rem;
        }

        /* Files Tab */
        .files-content {
            display: grid;
            grid-template-columns: 18.75rem 1fr;
            gap: 1.25rem;
            height: 100%;
        }

        .file-list {
            background: #f8f9fa;
            border-radius: 0.625rem;
            overflow-y: auto;
        }

        .file-list-header {
            padding: 0.9375rem;
            border-bottom: 0.0625rem solid #e0e6ed;
            font-weight: 600;
            color: #2c3e50;
            position: sticky;
            top: 0;
            background: #f8f9fa;
        }

        .file-item {
            padding: 0.75rem 0.9375rem;
            cursor: pointer;
            transition: background 0.2s;
            border-left: 0.1875rem solid transparent;
            display: flex;
            align-items: center;
            gap: 0.625rem;
        }

        .file-item:hover {
            background: #e8ecef;
        }

        .file-item.active {
            background: rgba(52, 152, 219, 0.1);
            border-left-color: #3498db;
            color: #3498db;
            font-weight: 500;
        }

        .file-icon {
            font-size: 1.1rem;
        }

        .file-viewer {
            background: #f8f9fa;
            border-radius: 0.625rem;
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }

        .file-viewer-header {
            padding: 0.9375rem;
            border-bottom: 0.0625rem solid #e0e6ed;
            font-family: 'Monaco', 'Menlo', monospace;
            font-size: 0.9rem;
            color: #555;
            background: #fff;
            font-weight: 500;
        }

        .file-viewer-content {
            flex: 1;
            overflow: auto;
            background: #1e1e1e;
        }

        .file-viewer-content pre {
            margin: 0;
            padding: 1.25rem;
        }

        .file-viewer-content code {
            font-family: 'Monaco', 'Menlo', monospace;
            font-size: 0.9rem;
            line-height: 1.6;
        }

        /* Security Tab */
        .security-content {
            max-width: 56.25rem;
        }

        .security-alert {
            background: #e3f2fd;
            border-left: 0.25rem solid #2196f3;
            padding: 1.25rem;
            border-radius: 0.3125rem;
            margin-bottom: 1.875rem;
        }

        .security-alert-title {
            font-weight: 600;
            color: #1976d2;
            margin-bottom: 0.5rem;
            font-size: 1.1rem;
        }

        .security-alert-desc {
            color: #555;
            line-height: 1.6;
        }

        .security-section {
            margin-bottom: 1.875rem;
        }

        .security-section h3 {
            color: #2c3e50;
            margin-bottom: 0.9375rem;
            font-size: 1.3rem;
        }

        .security-section ul {
            list-style: none;
            padding-left: 0;
        }

        .security-section li {
            padding: 0.625rem 0;
            padding-left: 1.875rem;
            position: relative;
            color: #555;
            line-height: 1.6;
        }

        .security-section li::before {
            content: '✓';
            position: absolute;
            left: 0;
            color: #27ae60;
            font-weight: bold;
            font-size: 1.2rem;
        }

        /* Loading State */
        .loading-spinner {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 3.75rem;
            color: #7f8c8d;
        }

        .spinner {
            border: 0.25rem solid #f3f3f3;
            border-top: 0.25rem solid #3498db;
            border-radius: 50%;
            width: 3.125rem;
            height: 3.125rem;
            animation: spin 1s linear infinite;
            margin-bottom: 1.25rem;
        }

        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        /* Responsive Design */
        @media (max-width: 64em) {
            .overview-content {
                grid-template-columns: 1fr;
            }

            .files-content {
                grid-template-columns: 1fr;
                height: auto;
            }

            .file-list {
                max-height: 12.5rem;
            }

            .file-viewer {
                min-height: 25rem;
            }
        }

        @media (max-width: 48em) {
            .container {
                padding: 1rem;
            }

            header {
                padding: 1.5rem;
                margin-bottom: 1.5rem;
            }

            h1 {
                font-size: 1.75rem;
            }

            .templates-grid {
                grid-template-columns: 1fr;
                gap: 1rem;
            }

            .modal-container {
                height: 95vh;
                margin: 0.625rem;
                border-radius: 0.5rem;
            }

            .modal-header {
                padding: 1.25rem;
            }

            .modal-header-content {
                flex-direction: column;
                align-items: flex-start;
                gap: 0.625rem;
            }

            .modal-icon {
                font-size: 2rem;
            }

            .modal-title-group h2 {
                font-size: 1.5rem;
            }

            .modal-body {
                padding: 1.25rem;
            }

            .modal-tabs {
                overflow-x: auto;
                padding: 0 1.25rem;
            }

            .modal-tab {
                padding: 0.75rem 0.9375rem;
                font-size: 0.9rem;
                white-space: nowrap;
            }

            .overview-content {
                gap: 1.25rem;
            }

            .files-content {
                gap: 1rem;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Rediacc Repository Template Catalog</h1>
            <p class="subtitle">Discover and download infrastructure templates</p>
            <div class="stats">
                <div class="stat">
                    <div class="stat-number" id="total-templates">0</div>
                    <div class="stat-label">Templates</div>
                </div>
                <div class="stat">
                    <div class="stat-number" id="total-categories">0</div>
                    <div class="stat-label">Categories</div>
                </div>
            </div>
        </header>

        <div class="filters">
            <div class="filter-group">
                <label>Search:</label>
                <input type="text" id="search" placeholder="Search templates...">
                <label>Category:</label>
                <select id="category-filter">
                    <option value="">All Categories</option>
                </select>
                <label>Docker:</label>
                <select id="docker-filter">
                    <option value="">All Templates</option>
                    <option value="true">With Docker</option>
                    <option value="false">Without Docker</option>
                </select>
            </div>
        </div>

        <div id="templates-container">
            <div class="templates-grid" id="templates-grid"></div>
            <div class="no-results" id="no-results" style="display: none;">
                No templates found matching your criteria.
            </div>
        </div>

        <div class="api-docs">
            <h2 class="api-title">API Endpoints</h2>
            <div class="endpoint">
                <span class="method">GET</span> /templates.json - Complete templates index
            </div>
            <div class="endpoint">
                <span class="method">GET</span> /templates/{template-id}.json - Individual template
            </div>
            <div class="endpoint">
                <span class="method">GET</span> /configs/pricing.json - Pricing configuration
            </div>
            <div class="endpoint">
                <span class="method">GET</span> /configs/services.json - Services configuration
            </div>
        </div>
    </div>

    <!-- Template Details Modal -->
    <div class="modal-overlay" id="template-modal">
        <div class="modal-container">
            <div class="modal-header">
                <div class="modal-header-content">
                    <div class="modal-icon">📦</div>
                    <div class="modal-title-group">
                        <h2 id="modal-template-name">Template Name</h2>
                        <div class="modal-tags" id="modal-tags"></div>
                    </div>
                </div>
                <button class="modal-close" onclick="closeModal()">&times;</button>
            </div>

            <div class="modal-tabs">
                <button class="modal-tab active" data-tab="overview" onclick="switchTab('overview')">
                    📄 Overview
                </button>
                <button class="modal-tab" data-tab="files" onclick="switchTab('files')">
                    📁 Files
                </button>
                <button class="modal-tab" data-tab="security" onclick="switchTab('security')">
                    🔒 Security
                </button>
            </div>

            <div class="modal-body">
                <!-- Overview Tab -->
                <div class="tab-content active" id="tab-overview">
                    <div class="overview-content">
                        <div class="readme-section">
                            <h3 class="section-title">Description</h3>
                            <div class="readme-content" id="readme-content">
                                Loading...
                            </div>
                        </div>
                        <div class="features-section">
                            <h3 class="section-title">Features</h3>
                            <ul class="feature-list" id="features-list"></ul>
                        </div>
                    </div>
                </div>

                <!-- Files Tab -->
                <div class="tab-content" id="tab-files">
                    <div class="files-content">
                        <div class="file-list">
                            <div class="file-list-header">Files</div>
                            <div id="file-list-items"></div>
                        </div>
                        <div class="file-viewer">
                            <div class="file-viewer-header" id="current-file-name">Select a file</div>
                            <div class="file-viewer-content" id="file-content">
                                <pre><code>Select a file to view its contents</code></pre>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Security Tab -->
                <div class="tab-content" id="tab-security">
                    <div class="security-content">
                        <div class="security-alert">
                            <div class="security-alert-title">Security Review</div>
                            <div class="security-alert-desc">
                                Please review the template files for security considerations before deployment.
                                Always verify configurations and credentials are properly secured.
                            </div>
                        </div>

                        <div class="security-section">
                            <h3>Best Practices</h3>
                            <ul>
                                <li>Review all configuration files before deployment</li>
                                <li>Update default passwords and credentials immediately</li>
                                <li>Ensure proper network security configuration</li>
                                <li>Keep software components up to date with security patches</li>
                                <li>Use environment variables for sensitive data</li>
                                <li>Enable SSL/TLS for production deployments</li>
                            </ul>
                        </div>

                        <div class="security-section">
                            <h3>Container Security</h3>
                            <ul>
                                <li>Always review container configurations</li>
                                <li>Use official images from trusted sources</li>
                                <li>Implement proper access controls</li>
                                <li>Regular security audits and updates</li>
                                <li>Monitor container logs for suspicious activity</li>
                            </ul>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        let allTemplates = [];
        let filteredTemplates = [];
        let currentTemplate = null;
        let selectedFileIndex = 0;

        // Initialize marked and highlight.js
        if (typeof marked !== 'undefined') {
            marked.setOptions({
                breaks: true,
                gfm: true
            });
        }

        // Load templates data
        fetch('templates.json')
            .then(response => response.json())
            .then(data => {
                allTemplates = data.templates;
                filteredTemplates = [...allTemplates];

                // Update stats
                document.getElementById('total-templates').textContent = data.total_templates;
                document.getElementById('total-categories').textContent = data.categories.length;

                // Populate category filter
                const categorySelect = document.getElementById('category-filter');
                data.categories.forEach(category => {
                    const option = document.createElement('option');
                    option.value = category;
                    option.textContent = category.charAt(0).toUpperCase() + category.slice(1);
                    categorySelect.appendChild(option);
                });

                // Initial render
                renderTemplates();

                // Setup event listeners
                setupFilters();
            })
            .catch(error => console.error('Error loading templates:', error));

        function renderTemplates() {
            const grid = document.getElementById('templates-grid');
            const noResults = document.getElementById('no-results');

            if (filteredTemplates.length === 0) {
                grid.style.display = 'none';
                noResults.style.display = 'block';
                return;
            }

            grid.style.display = 'grid';
            noResults.style.display = 'none';

            grid.innerHTML = filteredTemplates.map(template => `
                <div class="template-card">
                    <div class="template-header">
                        <h3 class="template-title">${template.name}</h3>
                        <div class="template-meta">
                            <span class="template-category">${template.category}</span>
                            <span class="template-files">${template.file_count} files</span>
                            ${template.has_docker ? '<span class="template-files">Docker</span>' : ''}
                        </div>
                        <p class="template-description">${template.description}</p>
                    </div>
                    <div class="template-actions">
                        <a href="${template.download_url}" class="btn">Download JSON</a>
                        <button onclick="viewTemplate('${template.id}')" class="btn btn-secondary">View Details</button>
                    </div>
                </div>
            `).join('');
        }

        function setupFilters() {
            const searchInput = document.getElementById('search');
            const categoryFilter = document.getElementById('category-filter');
            const dockerFilter = document.getElementById('docker-filter');

            function applyFilters() {
                const searchTerm = searchInput.value.toLowerCase();
                const selectedCategory = categoryFilter.value;
                const dockerRequirement = dockerFilter.value;

                filteredTemplates = allTemplates.filter(template => {
                    const matchesSearch = template.name.toLowerCase().includes(searchTerm) ||
                                        template.description.toLowerCase().includes(searchTerm) ||
                                        template.tags.some(tag => tag.toLowerCase().includes(searchTerm));

                    const matchesCategory = !selectedCategory || template.category === selectedCategory;

                    const matchesDocker = !dockerRequirement ||
                                        (dockerRequirement === 'true' && template.has_docker) ||
                                        (dockerRequirement === 'false' && !template.has_docker);

                    return matchesSearch && matchesCategory && matchesDocker;
                });

                renderTemplates();
            }

            searchInput.addEventListener('input', applyFilters);
            categoryFilter.addEventListener('change', applyFilters);
            dockerFilter.addEventListener('change', applyFilters);
        }

        function viewTemplate(templateId) {
            // Show loading state
            const modal = document.getElementById('template-modal');
            const readmeContent = document.getElementById('readme-content');
            const featuresList = document.getElementById('features-list');
            const fileListItems = document.getElementById('file-list-items');

            readmeContent.innerHTML = '<div class="loading-spinner"><div class="spinner"></div><p>Loading template details...</p></div>';
            featuresList.innerHTML = '';
            fileListItems.innerHTML = '';

            modal.classList.add('active');
            document.body.style.overflow = 'hidden';

            // Fetch template details
            fetch(`templates/${templateId}.json`)
                .then(response => response.json())
                .then(data => {
                    currentTemplate = data;
                    selectedFileIndex = 0;

                    // Update modal header
                    document.getElementById('modal-template-name').textContent = data.name;

                    // Update tags
                    const tagsContainer = document.getElementById('modal-tags');
                    tagsContainer.innerHTML = '';
                    if (data.category) {
                        const categoryTag = document.createElement('span');
                        categoryTag.className = 'modal-tag';
                        categoryTag.textContent = data.category;
                        tagsContainer.appendChild(categoryTag);
                    }
                    if (data.tags && data.tags.length > 0) {
                        // Filter out category from tags to avoid duplication
                        const uniqueTags = data.tags.filter(tag => tag.toLowerCase() !== (data.category || '').toLowerCase());
                        uniqueTags.slice(0, 3).forEach(tag => {
                            const tagEl = document.createElement('span');
                            tagEl.className = 'modal-tag';
                            tagEl.style.background = '#95a5a6';
                            tagEl.textContent = tag;
                            tagsContainer.appendChild(tagEl);
                        });
                    }

                    // Render README
                    if (data.readme && typeof marked !== 'undefined') {
                        readmeContent.innerHTML = marked.parse(data.readme);
                    } else {
                        readmeContent.textContent = data.readme || 'No description available.';
                    }

                    // Render features/tags
                    if (data.tags && data.tags.length > 0) {
                        featuresList.innerHTML = data.tags.map(tag => `
                            <li class="feature-item">
                                <span class="feature-icon">✓</span>
                                <span>${tag}</span>
                            </li>
                        `).join('');
                    } else {
                        featuresList.innerHTML = '<li class="feature-item"><span class="feature-icon">ℹ</span><span>No features listed</span></li>';
                    }

                    // Render file list
                    if (data.files && data.files.length > 0) {
                        fileListItems.innerHTML = data.files.map((file, index) => `
                            <div class="file-item ${index === 0 ? 'active' : ''}" onclick="selectFile(${index})">
                                <span class="file-icon">📄</span>
                                <span>${file.path || file.name}</span>
                            </div>
                        `).join('');

                        // Display first file by default
                        selectFile(0);
                    } else {
                        fileListItems.innerHTML = '<div style="padding: 20px; text-align: center; color: #7f8c8d;">No files available</div>';
                    }
                })
                .catch(error => {
                    console.error('Error loading template:', error);
                    readmeContent.innerHTML = '<p style="color: #e74c3c;">Failed to load template details. Please try again.</p>';
                });
        }

        function selectFile(index) {
            if (!currentTemplate || !currentTemplate.files || !currentTemplate.files[index]) {
                return;
            }

            selectedFileIndex = index;
            const file = currentTemplate.files[index];

            // Update active file in list
            document.querySelectorAll('.file-item').forEach((item, i) => {
                item.classList.toggle('active', i === index);
            });

            // Update file viewer header
            document.getElementById('current-file-name').textContent = file.path || file.name;

            // Update file content with syntax highlighting
            const fileContent = document.getElementById('file-content');
            const language = detectLanguage(file.name);

            if (language === 'markdown' && typeof marked !== 'undefined') {
                // Render markdown
                fileContent.innerHTML = `<div style="padding: 20px; background: white; color: #333;">${marked.parse(file.content)}</div>`;
            } else if (typeof hljs !== 'undefined') {
                // Syntax highlighting
                try {
                    const highlighted = hljs.highlightAuto(file.content, [language]).value;
                    fileContent.innerHTML = `<pre><code class="hljs">${highlighted}</code></pre>`;
                } catch (e) {
                    fileContent.innerHTML = `<pre><code>${escapeHtml(file.content)}</code></pre>`;
                }
            } else {
                fileContent.innerHTML = `<pre><code>${escapeHtml(file.content)}</code></pre>`;
            }
        }

        function detectLanguage(filename) {
            const ext = filename.split('.').pop().toLowerCase();
            const languageMap = {
                'yaml': 'yaml',
                'yml': 'yaml',
                'json': 'json',
                'sh': 'bash',
                'bash': 'bash',
                'env': 'bash',
                'md': 'markdown',
                'py': 'python',
                'js': 'javascript',
                'ts': 'typescript',
                'jsx': 'javascript',
                'tsx': 'typescript',
                'html': 'html',
                'css': 'css',
                'sql': 'sql',
                'xml': 'xml',
                'conf': 'nginx',
                'config': 'ini'
            };
            return languageMap[ext] || 'plaintext';
        }

        function escapeHtml(text) {
            const map = {
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                '"': '&quot;',
                "'": '&#039;'
            };
            return text.replace(/[&<>"']/g, m => map[m]);
        }

        function switchTab(tabName) {
            // Update tab buttons
            document.querySelectorAll('.modal-tab').forEach(tab => {
                tab.classList.toggle('active', tab.dataset.tab === tabName);
            });

            // Update tab contents
            document.querySelectorAll('.tab-content').forEach(content => {
                content.classList.toggle('active', content.id === `tab-${tabName}`);
            });
        }

        function closeModal() {
            const modal = document.getElementById('template-modal');
            modal.classList.remove('active');
            document.body.style.overflow = '';
            currentTemplate = null;
            selectedFileIndex = 0;

            // Reset to overview tab
            switchTab('overview');
        }

        // Close modal on overlay click
        document.getElementById('template-modal').addEventListener('click', function(e) {
            if (e.target === this) {
                closeModal();
            }
        });

        // Close modal on ESC key
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') {
                closeModal();
            }
        });
    </script>
</body>
</html>
HEREDOC_REMOVED

    # _config.yml is now copied from src/ directory
    # Legacy heredoc removed
    : << 'HEREDOC_REMOVED'
# GitHub Pages configuration
title: Template Catalog
description: Infrastructure template catalog and configuration repository
baseurl: ""
url: ""

# Build settings
markdown: kramdown
highlighter: rouge
theme: minima

# Include/exclude files
include:
  - "*.json"
  - "templates/"
  - "configs/"
  - "assets/"

exclude:
  - "README.md"
  - "Gemfile"
  - "Gemfile.lock"

# Enable directory indexes
plugins:
  - jekyll-optional-front-matter

# MIME types for JSON files
defaults:
  - scope:
      path: "**/*.json"
    values:
      layout: null
HEREDOC_REMOVED

    # api.html is now copied from src/ directory
    # Legacy heredoc removed
    : << 'HEREDOC_REMOVED'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>API Documentation - Template Catalog</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; max-width: 1000px; margin: 0 auto; padding: 20px; }
        .header { text-align: center; margin-bottom: 40px; }
        .endpoint { background: #f8f9fa; padding: 20px; margin: 20px 0; border-radius: 8px; border-left: 4px solid #007bff; }
        .method { background: #28a745; color: white; padding: 4px 8px; border-radius: 4px; font-size: 0.8rem; font-weight: bold; }
        .url { font-family: 'Monaco', 'Menlo', monospace; background: #e9ecef; padding: 2px 6px; border-radius: 3px; }
        code { background: #f1f3f4; padding: 2px 4px; border-radius: 3px; font-family: 'Monaco', 'Menlo', monospace; }
        pre { background: #f8f9fa; padding: 15px; border-radius: 5px; overflow-x: auto; }
        .back-link { display: inline-block; margin-bottom: 20px; color: #007bff; text-decoration: none; }
    </style>
</head>
<body>
    <a href="index.html" class="back-link">← Back to Catalog</a>

    <div class="header">
        <h1>API Documentation</h1>
        <p>RESTful JSON API for accessing template and configuration data</p>
    </div>

    <div class="endpoint">
        <h3><span class="method">GET</span> <span class="url">/templates.json</span></h3>
        <p>Returns the complete templates index with metadata for all available templates.</p>
        <h4>Response Format:</h4>
        <pre><code>{
  "version": "1.0",
  "generated": "2024-01-01T00:00:00Z",
  "total_templates": 22,
  "categories": ["api", "auth", "cache", "db", ...],
  "templates": [
    {
      "id": "template_name",
      "name": "Display Name",
      "description": "Template description",
      "category": "category_name",
      "tags": ["tag1", "tag2"],
      "file_count": 4,
      "has_readme": true,
      "has_docker": true,
      "download_url": "templates/template_name.json"
    }
  ]
}</code></pre>
    </div>

    <div class="endpoint">
        <h3><span class="method">GET</span> <span class="url">/templates/{template-id}.json</span></h3>
        <p>Returns detailed information and file contents for a specific template.</p>
        <h4>Example URLs:</h4>
        <ul>
            <li><code>/templates/api-gateway_kong.json</code></li>
            <li><code>/templates/databases_mysql.json</code></li>
            <li><code>/templates/caching_redis.json</code></li>
        </ul>
        <h4>Response Format:</h4>
        <pre><code>{
  "id": "template_name",
  "name": "Display Name",
  "description": "Template description",
  "category": "category_name",
  "tags": ["tag1", "tag2"],
  "files": [
    {
      "name": "docker-compose.yaml",
      "path": "docker-compose.yaml",
      "type": "yaml",
      "content": "file contents here..."
    }
  ],
  "readme": "README.md contents...",
  "generated": "2024-01-01T00:00:00Z"
}</code></pre>
    </div>

    <div class="endpoint">
        <h3><span class="method">GET</span> <span class="url">/configs/pricing.json</span></h3>
        <p>Returns pricing configuration data including tiers and professional services.</p>
    </div>

    <div class="endpoint">
        <h3><span class="method">GET</span> <span class="url">/configs/services.json</span></h3>
        <p>Returns services configuration data.</p>
    </div>

    <div class="endpoint">
        <h3><span class="method">GET</span> <span class="url">/configs/tiers.json</span></h3>
        <p>Returns tier configuration data.</p>
    </div>

    <h2>Usage Examples</h2>
    <h3>JavaScript/Fetch</h3>
    <pre><code>// Load templates index
const templates = await fetch('/templates.json').then(r => r.json());

// Load specific template
const template = await fetch(`/templates/${templateId}.json`).then(r => r.json());

// Get file content
const dockerCompose = template.files.find(f => f.name === 'docker-compose.yaml')?.content;</code></pre>

    <h3>curl</h3>
    <pre><code># Get templates index
curl https://json.rediacc.com/templates.json

# Get specific template
curl https://json.rediacc.com/templates/api-gateway_kong.json</code></pre>
</body>
</html>
HEREDOC_REMOVED

    log_success "GitHub Pages website generated"
}

# Function to validate generated files
validate_output() {
    log_info "Validating generated files..."

    local errors=0

    # Check required files exist
    local required_files=(
        "$BUILD_DIR/index.html"
        "$BUILD_DIR/templates.json"
        "$BUILD_DIR/_config.yml"
        "$BUILD_DIR/api.html"
    )

    for file in "${required_files[@]}"; do
        if [[ ! -f "$file" ]]; then
            log_error "Required file missing: $file"
            ((errors++))
        fi
    done

    # Check templates.json is valid JSON
    if [[ -f "$BUILD_DIR/templates.json" ]]; then
        if ! python3 -m json.tool "$BUILD_DIR/templates.json" >/dev/null 2>&1; then
            log_error "templates.json is not valid JSON"
            ((errors++))
        fi
    fi

    # Check template JSON files
    local template_files=0
    for template_file in "$BUILD_DIR/templates"/*.json; do
        if [[ -f "$template_file" ]]; then
            if ! python3 -m json.tool "$template_file" >/dev/null 2>&1; then
                log_error "Invalid JSON: $(basename "$template_file")"
                ((errors++))
            fi
            ((template_files++))
        fi
    done

    log_info "Found $template_files template JSON files"

    if [[ $errors -eq 0 ]]; then
        log_success "All files validated successfully"
        return 0
    else
        log_error "Found $errors validation errors"
        return 1
    fi
}

# Function to minify JSON files
minify_json_files() {
    log_info "Minifying JSON files..."

    local minified=0
    local total_size_before=0
    local total_size_after=0

    # Find all JSON files in build directory
    while IFS= read -r -d '' json_file; do
        if [[ -f "$json_file" ]]; then
            local size_before=$(stat -f%z "$json_file" 2>/dev/null || stat -c%s "$json_file" 2>/dev/null || echo "0")
            total_size_before=$((total_size_before + size_before))

            # Create temporary file and minify
            local temp_file="${json_file}.tmp"
            if jq -c . "$json_file" > "$temp_file" 2>/dev/null; then
                mv "$temp_file" "$json_file"
                local size_after=$(stat -f%z "$json_file" 2>/dev/null || stat -c%s "$json_file" 2>/dev/null || echo "0")
                total_size_after=$((total_size_after + size_after))
                minified=$((minified + 1))
            else
                log_warning "Failed to minify: $(basename "$json_file")"
                rm -f "$temp_file"
                total_size_after=$((total_size_after + size_before))
            fi
        fi
    done < <(find "$BUILD_DIR" -name "*.json" -type f -print0)

    if [[ $minified -gt 0 ]]; then
        local savings=$((total_size_before - total_size_after))
        local percentage=0
        if [[ $total_size_before -gt 0 ]]; then
            percentage=$((savings * 100 / total_size_before))
        fi
        log_success "Minified $minified JSON files (saved ${savings} bytes, ${percentage}% reduction)"
    else
        log_warning "No JSON files were minified"
    fi
}

# Function to display summary
show_summary() {
    log_info "Generation Summary"
    echo "===================="
    echo "Build Directory: $BUILD_DIR"
    echo ""
    echo "Generated Files:"
    echo "  - index.html          (Main website)"
    echo "  - templates.json      (Templates index API)"
    echo "  - api.html           (API documentation)"
    echo "  - _config.yml        (GitHub Pages config)"
    echo ""

    if [[ -d "$BUILD_DIR/templates" ]]; then
        local template_count=$(find "$BUILD_DIR/templates" -name "*.json" | wc -l)
        echo "  - templates/         ($template_count template JSON files)"
    fi

    if [[ -d "$BUILD_DIR/configs" ]]; then
        local config_count=$(find "$BUILD_DIR/configs" -name "*.json" | wc -l)
        echo "  - configs/           ($config_count config JSON files)"
    fi

    if [[ -d "$BUILD_DIR/assets" ]]; then
        local asset_count=$(find "$BUILD_DIR/assets" -type f | wc -l)
        echo "  - assets/            ($asset_count asset files)"
    fi

    echo ""
    echo "Next Steps:"
    echo "  1. Test locally: cd $BUILD_DIR && python3 -m http.server 8000"
    echo "  2. Deploy: Copy build/ contents to your GitHub Pages repository"
    echo "  3. Access: Visit your GitHub Pages URL"
    echo ""
}

# Copy test results if they exist
copy_test_results() {
    log_info "Copying test results"

    if [[ -f "$SOURCE_DIR/test-results.json" ]]; then
        echo -e "${GREEN}✓${NC} Found test-results.json, copying to build directory"
        cp "$SOURCE_DIR/test-results.json" "$BUILD_DIR/test-results.json"
    else
        echo -e "${YELLOW}⚠${NC} No test-results.json found, creating empty results file"
        cat > "$BUILD_DIR/test-results.json" << 'EOF'
{"summary":{"total":0,"passed":0,"failed":0,"skipped":0,"duration":"0s","timestamp":""},"results":[]}
EOF
    fi

    echo ""
}

# Main execution
main() {
    log_info "Starting JSON Config Generator"
    echo "=============================="

    # Check dependencies
    if ! command -v python3 >/dev/null 2>&1; then
        log_error "Python 3 is required for JSON validation"
        exit 1
    fi

    if ! command -v jq >/dev/null 2>&1; then
        log_error "jq is required for JSON minification"
        exit 1
    fi

    # Load skip list
    load_skip_list

    # Run generation steps
    clean_build
    process_templates
    process_configs
    generate_website
    copy_test_results

    # Validate output before minification
    if validate_output; then
        # Minify JSON files to reduce size
        minify_json_files

        show_summary
        log_success "Generation completed successfully!"
        exit 0
    else
        log_error "Generation completed with errors"
        exit 1
    fi
}

# Run main function
main "$@"
