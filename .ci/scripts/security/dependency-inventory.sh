#!/bin/bash
# dependency-inventory.sh - Enumerate every dependency across the six analyzed
# Rediacc packages (www, web, cli, desktop, account, renet) for the NIS2/CRA
# supply-chain SBOM. Each dependency is classified by level (direct vs
# transitive), tagged by type (dependencies/devDependencies/peer/optional for
# npm; direct/indirect for Go), and carries its full dependency chain(s) from
# the package root down to the dependency.
#
# npm chains come from the logical `npm ls --all --json` tree (each occurrence
# is one chain). Go chains are the shortest path from the main module through
# `go mod graph`; the complete Go edge list is included under the renet package
# so any longer chain can be reconstructed (full path enumeration in a module
# DAG is exponential, so it is intentionally not materialized).
#
# Usage:
#   dependency-inventory.sh [--format json|table] [--output PATH] [--max-chains N]
#
# Options:
#   --format FORMAT    Output format: json or table (default: table)
#   --output PATH      Write to PATH instead of stdout
#   --max-chains N     Max chains stored per dependency; 0 = unlimited
#                      (default: 25). Truncation is logged, never silent.
#   -h, --help         Show this help
#
# Requirements: jq, npm, go on PATH; installed node_modules (root workspace +
# private/account). Does not auto-install.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

FORMAT="table"
OUTPUT=""
MAX_CHAINS=25

while [[ $# -gt 0 ]]; do
    case "$1" in
    --format)
        FORMAT="$2"
        shift 2
        ;;
    --output)
        OUTPUT="$2"
        shift 2
        ;;
    --max-chains)
        MAX_CHAINS="$2"
        shift 2
        ;;
    -h | --help)
        sed -n '2,35p' "$0" | sed 's/^# \?//'
        exit 0
        ;;
    *)
        log_error "Unknown option: $1"
        exit 1
        ;;
    esac
done

case "$FORMAT" in
json | table) ;;
*)
    log_error "--format must be 'json' or 'table'"
    exit 1
    ;;
esac
[[ "$MAX_CHAINS" =~ ^[0-9]+$ ]] || {
    log_error "--max-chains must be a non-negative integer"
    exit 1
}

require_cmd jq npm go
[[ "$FORMAT" == "table" ]] && require_cmd column

REPO_ROOT="$(get_repo_root)"

# Scratch dir for per-package objects. Large JSON is exchanged via files/stdin,
# never argv (--argjson on a big value blows ARG_MAX).
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# The six packages. Format: name|relpath|mode (workspace|standalone).
NPM_PKGS=(
    "@rediacc/www|packages/www|workspace"
    "@rediacc/web|packages/web|workspace"
    "@rediacc/cli|packages/cli|workspace"
    "@rediacc/desktop|packages/desktop|workspace"
    "@rediacc/account|private/account|standalone"
)

# --- jq programs (kept as constants to avoid re-embedding) ---

# Recursive walker: flatten an npm ls tree map into one record per occurrence,
# each carrying its full ancestor chain. Expects the dependency map as input.
JQ_WALK='
def walk($chain):
  to_entries[] | .key as $n | .value as $v |
  ($chain + [$n + "@" + ($v.version // "unknown")]) as $c |
  {name:$n, version:($v.version//null), depth:($c|length), chain:$c},
  (($v.dependencies // {}) | walk($c));
'

# Collect the set (object of key->true) of name@version present in a tree map.
JQ_KEYSET='
def kw: to_entries[] | .key as $n | .value as $v |
  ($n + "@" + ($v.version // "unknown")),
  (($v.dependencies // {}) | kw);
reduce (ROOTEXPR // {} | kw) as $k ({}; .[$k]=true)
'

# Build one npm package object. Args: name relpath mode. Emits JSON to stdout.
build_npm_package() {
    local name="$1" relpath="$2" mode="$3"
    local dir="$REPO_ROOT/$relpath"
    local tree_all tree_prod rootexpr nm_dir

    if [[ "$mode" == "workspace" ]]; then
        nm_dir="$REPO_ROOT/node_modules"
        rootexpr='.dependencies["'"$name"'"].dependencies'
    else
        nm_dir="$dir/node_modules"
        rootexpr='.dependencies'
    fi

    if [[ ! -d "$nm_dir" ]]; then
        log_error "$name: $nm_dir missing. Run 'npm install' (+ 'npm run install:natives') first."
        return 1
    fi

    if [[ "$mode" == "workspace" ]]; then
        tree_all="$(cd "$REPO_ROOT" && npm ls --all --json --workspace "$name" 2>/dev/null || true)"
        tree_prod="$(cd "$REPO_ROOT" && npm ls --all --json --omit=dev --workspace "$name" 2>/dev/null || true)"
    else
        tree_all="$(cd "$dir" && npm ls --all --json 2>/dev/null || true)"
        tree_prod="$(cd "$dir" && npm ls --all --json --omit=dev 2>/dev/null || true)"
    fi

    if ! jq empty >/dev/null 2>&1 <<<"$tree_all"; then
        log_error "$name: npm ls produced invalid JSON"
        return 1
    fi

    local prodset types deps
    if jq empty >/dev/null 2>&1 <<<"$tree_prod"; then
        prodset="$(jq -c "${JQ_KEYSET/ROOTEXPR/$rootexpr}" <<<"$tree_prod")"
    else
        prodset='{}'
    fi

    types="$(jq -c '
        def sect($o;$l): ($o // {} | keys | map({key:.,value:$l}) | from_entries);
        sect(.devDependencies;"devDependencies") + sect(.peerDependencies;"peerDependencies")
        + sect(.optionalDependencies;"optionalDependencies") + sect(.dependencies;"dependencies")
    ' "$dir/package.json")"

    deps="$(jq -c \
        --argjson prodset "$prodset" --argjson types "$types" --argjson maxc "$MAX_CHAINS" \
        "$JQ_WALK"'
        [ ('"$rootexpr"' // {}) | walk([]) ]
        | group_by(.name + "@" + (.version // "null"))
        | map(
            (.[0].name) as $name | (.[0].version) as $version |
            ([.[].depth]|min) as $depth |
            ([.[].chain]|unique) as $allc | ($allc|length) as $total |
            (if $depth==1 then "direct" else "transitive" end) as $level |
            ($name + "@" + ($version // "unknown")) as $key |
            { name:$name, version:$version, level:$level, depth:$depth,
              type:(if $level=="direct" then ($types[$name] // "dependencies") else "transitive" end),
              internal: ($name|startswith("@rediacc/")),
              prodReachable: ($prodset[$key] // false),
              chains: (if $maxc>0 then $allc[0:$maxc] else $allc end),
              totalChains:$total, chainsTruncated: ($maxc>0 and $total>$maxc) }
          )
        | sort_by(.level, .depth, .name)
    ' <<<"$tree_all")"

    # Surface any chain truncation (no silent caps).
    while IFS= read -r line; do
        [[ -n "$line" ]] && log_warn "$name: chains capped for $line"
    done < <(jq -r '.[] | select(.chainsTruncated) | "\(.name)@\(.version // "?") (\(.totalChains) chains)"' <<<"$deps")

    jq -c --arg name "$name" --arg path "$relpath" '
        { name:$name, path:$path, ecosystem:"npm",
          counts:{ direct:(map(select(.level=="direct"))|length),
                   transitive:(map(select(.level=="transitive"))|length),
                   total:length },
          dependencies:. }' <<<"$deps"
}

# Build the renet Go package object. Emits JSON to stdout.
build_go_package() {
    local dir="$REPO_ROOT/private/renet"
    local main_mod modules edges bfs deps

    main_mod="$(cd "$dir" && go list -m 2>/dev/null)"
    modules="$(cd "$dir" && go list -m -json all 2>/dev/null | jq -s -c '.')"
    edges="$(cd "$dir" && go mod graph 2>/dev/null || true)"

    # BFS from the main module: shortest depth + reconstructed chain per node.
    # Chain excludes the main module and starts at the direct dependency
    # (depth 1), matching npm chain semantics.
    bfs="$(awk -v root="$main_mod" '
        { adjc[$1]++; adj[$1,adjc[$1]]=$2 }
        END {
            head=1; tail=0;
            q[++tail]=root; seen[root]=1; depth[root]=0; pred[root]="";
            while (head<=tail) {
                u=q[head++]; n=adjc[u];
                for (i=1;i<=n;i++) {
                    v=adj[u,i];
                    if (!(v in seen)) { seen[v]=1; depth[v]=depth[u]+1; pred[v]=u; q[++tail]=v }
                }
            }
            for (v in seen) {
                if (v==root) continue;
                chain=""; x=v;
                while (x!="" && x!=root) { chain=(chain=="" ? x : x","chain); x=pred[x] }
                print v"\t"depth[v]"\t"chain;
            }
        }
    ' <<<"$edges" | jq -R -s -c '
        split("\n") | map(select(length>0)) | map(split("\t"))
        | map({key:.[0], value:{depth:(.[1]|tonumber), chain:(.[2]|split(","))}})
        | from_entries')"

    deps="$(jq -c --argjson bfs "$bfs" '
        map(select(.Main != true))
        | map(
            (.Path + "@" + (.Version // "unknown")) as $key |
            ($bfs[$key]) as $b |
            { name:.Path, version:(.Version//null),
              level:(if .Indirect==true then "transitive" else "direct" end),
              depth:($b.depth // (if .Indirect==true then null else 1 end)),
              type:(if .Indirect==true then "indirect" else "direct" end),
              internal:false,
              prodReachable:true,
              chains:(if $b.chain then [$b.chain] else [] end),
              totalChains:(if $b.chain then 1 else 0 end),
              chainsTruncated:false }
          )
        | sort_by(.level, (.depth // 999), .name)' <<<"$modules")"

    jq -R -s -c 'split("\n")|map(select(length>0))|map(split(" ")|{from:.[0],to:.[1]})' <<<"$edges" >"$WORK/go_edges.json"

    jq -c --slurpfile edges "$WORK/go_edges.json" '
        { name:"renet", path:"private/renet", ecosystem:"go",
          counts:{ direct:(map(select(.level=="direct"))|length),
                   transitive:(map(select(.level=="transitive"))|length),
                   total:length },
          dependencies:., edges:$edges[0] }' <<<"$deps"
}

render_table() {
    local doc="$1" np i tab
    tab="$(printf '\t')"
    np="$(jq '.packages|length' <<<"$doc")"
    # Render each package block separately so `column` aligns only that block's
    # uniform TSV rows (mixing the long "===" header lines in confuses widths).
    for ((i = 0; i < np; i++)); do
        echo ""
        jq -r --argjson i "$i" '.packages[$i] |
            "=== \(.name) [\(.ecosystem)]  direct=\(.counts.direct) transitive=\(.counts.transitive) total=\(.counts.total) ==="' <<<"$doc"
        jq -r --argjson i "$i" '.packages[$i] |
            (["LEVEL","DEPTH","TYPE","INTERNAL","PRODREACH","NAME","VERSION"] | @tsv),
            (.dependencies[] | [.level, (.depth|tostring), .type, (.internal|tostring), (.prodReachable|tostring), .name, (.version//"?")] | @tsv)
        ' <<<"$doc" | column -t -s "$tab"
    done
    echo ""
    jq -r '.summary | "SUMMARY  packages=\(.packagesAnalyzed)  records=\(.totals.records)  unique=\(.totals.uniqueByNameVersion)  external=\(.totals.externalUniqueByNameVersion)  npm=\(.byEcosystem.npm)  go=\(.byEcosystem.go)  direct=\(.byLevel.direct)  transitive=\(.byLevel.transitive)"' <<<"$doc"
    echo "(full dependency chains available via --format json)"
}

main() {
    local entry nm pth md doc generated i=0
    local objfiles=()

    for entry in "${NPM_PKGS[@]}"; do
        IFS='|' read -r nm pth md <<<"$entry"
        log_step "Analyzing $nm ($pth)"
        build_npm_package "$nm" "$pth" "$md" >"$WORK/pkg_$i.json"
        objfiles+=("$WORK/pkg_$i.json")
        i=$((i + 1))
    done

    log_step "Analyzing renet (private/renet)"
    build_go_package >"$WORK/pkg_$i.json"
    objfiles+=("$WORK/pkg_$i.json")

    generated="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    # jq -s slurps each per-package file into one array (.).
    doc="$(jq -s --arg gen "$generated" --argjson maxc "$MAX_CHAINS" '
        { generatedAt:$gen,
          tool:{ name:"dependency-inventory.sh", maxChains:$maxc },
          summary:{
            packagesAnalyzed:length,
            totals:{ records:([.[].dependencies|length]|add // 0),
                     uniqueByNameVersion:([.[].dependencies[]|(.name+"@"+(.version//"unknown"))]|unique|length),
                     externalUniqueByNameVersion:([.[].dependencies[]|select(.internal|not)|(.name+"@"+(.version//"unknown"))]|unique|length) },
            byEcosystem:{ npm:([.[]|select(.ecosystem=="npm").dependencies[]]|length),
                          go:([.[]|select(.ecosystem=="go").dependencies[]]|length) },
            byLevel:{ direct:([.[].dependencies[]|select(.level=="direct")]|length),
                      transitive:([.[].dependencies[]|select(.level=="transitive")]|length) } },
          packages:. }' "${objfiles[@]}")"

    if [[ "$FORMAT" == "json" ]]; then
        if [[ -n "$OUTPUT" ]]; then
            jq . <<<"$doc" >"$OUTPUT"
            log_info "Wrote JSON inventory to $OUTPUT"
        else
            jq . <<<"$doc"
        fi
    else
        if [[ -n "$OUTPUT" ]]; then
            render_table "$doc" >"$OUTPUT"
            log_info "Wrote table inventory to $OUTPUT"
        else
            render_table "$doc"
        fi
    fi
}

main "$@"
