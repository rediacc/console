#!/bin/bash
# The tutorial pipeline itself: record, extract, scaffold, generate, video, media,
# watch, validate, and the two `all` aggregates.
#
# This is the module the operator's commands map onto one-for-one, which is why it is
# one module and not five: `./run.sh www tutorials <verb>` has exactly one function per
# verb, and a reader looking for what a verb does should find it in one file. What has
# been pulled OUT of it is everything that is not a verb -- the venv, the GPU probe,
# the render pool, the bridge, the R2 cache -- so that this file is the pipeline's
# control flow and its argument parsing, and nothing else.
#
# Part of the media pipeline extraction (W10). Moved out of run.sh byte for byte in
# phase 1, comments included; phase 2 deleted run.sh's copies, so this file is now the
# only definition of every name in it. Two gate tests cover it:
# .ci/scripts/test/gates/test-media-args.sh asserts that ownership and drives the
# argument parsers (the part with real branching), and
# .ci/scripts/test/gates/test-media-entry.sh drives every routed verb from a real
# ./run.sh invocation and requires it to arrive inside the function here that owns it.
#
# SOURCED, NEVER EXECUTED. Callers supply ROOT_DIR, the log_* helpers, and
# check_node_version/ensure_deps from .ci/lib/local-common.sh. It calls into every
# other .ci/media module, so media-entry.sh sources this one LAST.

# True if REDIACC_ALLOW_GRAND_REPO contains a `*` entry (machine-level wildcard).
# Accepts a single `*`, a comma-separated list, or a list with `*` mixed in
# (e.g. `repo1,*,repo2`). Whitespace around each entry is trimmed.
# Mirrors isGrandEnvWildcard() in packages/cli/src/utils/grand-env.ts.
_grand_env_is_wildcard() {
    local raw="${REDIACC_ALLOW_GRAND_REPO:-}"
    [[ -z "$raw" ]] && return 1
    local -a entries
    local IFS=','
    # read -ra splits on IFS without performing pathname expansion (critical:
    # a bare `*` in a for-loop would otherwise glob against the cwd).
    read -ra entries <<<"$raw"
    local entry
    for entry in "${entries[@]}"; do
        entry="${entry#"${entry%%[![:space:]]*}"}"
        entry="${entry%"${entry##*[![:space:]]}"}"
        [[ "$entry" == "*" ]] && return 0
    done
    return 1
}

# Compute hash of a tutorial script + shared helpers for change detection
_tutorial_script_hash() {
    local script="$1"
    local helpers="$ROOT_DIR/.ci/tutorials/lib/tutorial-helpers.sh"
    cat "$script" "$helpers" 2>/dev/null | "${MEDIA_SHA256[@]}" | awk '{print $1}'
}

# Recorded terminal geometry, single source of truth. Downstream is derived, not
# duplicated: the value is written into each cast header and every renderer reads
# it back (packages/www/scripts/lib/scenes/cast.ts). The width is a legibility
# choice, not a realism one -- the player shows the video at ~800px, so 107
# columns already lands near the readable floor.
TUTORIAL_COLS=107
TUTORIAL_ROWS=32

www_tutorials_record() {
    local force=false
    local keep_vms=false
    local name=""
    local tutorials_dir="$ROOT_DIR/.ci/tutorials"
    local output_dir="$ROOT_DIR/packages/www/public/assets/tutorials"
    local hash_file="$output_dir/.recording-hashes"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --force)
                force=true
                shift
                ;;
            --keep-vms)
                keep_vms=true
                shift
                ;;
            --max-idle-ms)
                export MAX_IDLE_MS="$2"
                shift 2
                ;;
            --max-idle-ms=*)
                export MAX_IDLE_MS="${1#*=}"
                shift
                ;;
            *)
                name="$1"
                shift
                ;;
        esac
    done

    # Tutorials use term connect / repo create which require direct machine access.
    # In AI agent sessions, the user must pre-set REDIACC_ALLOW_GRAND_REPO=* before
    # starting the agent so the CLI accepts the override as legitimate. We propagate
    # it to the bridge's rdc below.
    if [[ "${CLAUDECODE:-}" == "1" || "${GEMINI_CLI:-}" == "1" || "${COPILOT_CLI:-}" == "1" || "${REDIACC_AGENT:-}" == "1" || -n "${CURSOR_TRACE_ID:-}" ]]; then
        if ! _grand_env_is_wildcard; then
            log_error "Tutorial recording requires direct machine access, which is blocked in agent mode."
            log_error ""
            log_error "Set REDIACC_ALLOW_GRAND_REPO=* in your terminal BEFORE starting the agent session:"
            log_error "  export REDIACC_ALLOW_GRAND_REPO=*"
            log_error "  claude  # then run ./run.sh www tutorials record"
            exit 1
        fi
    fi

    # Load stored hashes
    local -A stored_hashes
    if [[ -f "$hash_file" ]]; then
        while IFS='=' read -r key val; do
            stored_hashes["$key"]="$val"
        done <"$hash_file"
    fi

    # Determine candidate scripts
    local candidates=()
    if [[ -n "$name" ]]; then
        # Accept either fully-qualified slug (tutorial-installation) or short name (installation)
        local script="$tutorials_dir/${name}.sh"
        if [[ ! -f "$script" ]]; then
            script="$tutorials_dir/tutorial-${name}.sh"
        fi
        [[ -f "$script" ]] || {
            log_error "Tutorial not found: $tutorials_dir/${name}.sh or tutorial-${name}.sh"
            exit 1
        }
        candidates+=("$script")
    else
        # Record in the DECLARED sequence, never alphabetically. The tutorials are a
        # stateful chain run against one shared cluster and nothing is reset between
        # them (.ci/tutorials/run-sequence.sh), so alphabetical order puts tutorial 11
        # (backup-restore) and 15 (branching) ahead of tutorial 4 (create-repo), which
        # then fails on the state they left behind. The order lives in the docs
        # frontmatter, the same single source of truth run-sequence.sh derives from.
        local docs_dir="$ROOT_DIR/packages/www/src/content/docs/en"
        local ordered_pairs=()
        local doc slug order
        for doc in "$docs_dir"/tutorial-*.mdx; do
            [[ -f "$doc" ]] || continue
            slug="$(basename "$doc" .mdx)"
            order="$(grep -m1 '^order:' "$doc" | tr -dc '0-9')"
            if [[ -z "$order" ]]; then
                log_error "Tutorial doc has no 'order:' frontmatter: $doc"
                exit 1
            fi
            ordered_pairs+=("$(printf '%03d %s' "$order" "$slug")")
        done
        # while-read, not mapfile: bash 3.2 compat, same pattern as run-sequence.sh.
        local _line
        while IFS= read -r _line; do
            [[ -n "$_line" ]] || continue
            local ordered_script="$tutorials_dir/${_line}.sh"
            if [[ ! -f "$ordered_script" ]]; then
                log_error "Tutorial doc ${_line}.mdx has no script $ordered_script"
                exit 1
            fi
            candidates+=("$ordered_script")
        done < <(printf '%s\n' "${ordered_pairs[@]}" | sort | awk '{print $2}')
        # A script with no doc would be silently skipped by the loop above; catch it.
        local script
        for script in "$tutorials_dir"/tutorial-*.sh; do
            [[ -f "$script" ]] || continue
            case " ${candidates[*]} " in
                *" $script "*) ;;
                *)
                    log_error "Tutorial script has no doc, so it has no place in the sequence: $script"
                    exit 1
                    ;;
            esac
        done
    fi

    # Filter by change detection (unless --force)
    local scripts_to_record=()
    for script in "${candidates[@]}"; do
        local base
        base="$(basename "$script" .sh)"
        if [[ "$force" == "true" ]]; then
            scripts_to_record+=("$script")
        else
            local current_hash
            current_hash="$(_tutorial_script_hash "$script")"
            if [[ "${stored_hashes[$base]:-}" != "$current_hash" ]]; then
                scripts_to_record+=("$script")
            else
                log_debug "Unchanged: $base (skipping)"
            fi
        fi
    done

    if [[ ${#scripts_to_record[@]} -eq 0 ]]; then
        log_info "No tutorial scripts changed, skipping recording"
        return 0
    fi

    # Provision the cluster (bridge + workers) and prepare host->bridge SSH.
    log_step "Provisioning VMs for tutorial recording..."
    provision_start

    # Recording runs INSIDE the bridge VM so the local host's ~/.config/rediacc is
    # never touched and the cast captures a pristine machine. Bootstrap the bridge
    # with node + asciinema + the dev rdc SEA + the tutorial scripts.
    _ensure_bridge_recording_tooling
    local bridge
    bridge="$(_bridge_ip)"

    # Stage shared app files (some tutorials consume /tmp/tutorial-app) and push
    # them to the bridge where the recording runs.
    mkdir -p /tmp/tutorial-app
    cat >/tmp/tutorial-app/Rediaccfile <<'TEOF'
#!/bin/bash
up() { renet compose -- up -d; }
down() { renet compose -- down; }
info() { renet compose -- ps; }
TEOF
    cat >/tmp/tutorial-app/docker-compose.yml <<'TEOF'
services:
  web:
    image: nginx:alpine
    ports:
      - "80:80"
TEOF
    _bridge_ssh 'mkdir -p /tmp/tutorial-app'
    _bridge_rsync /tmp/tutorial-app/ "${bridge}:/tmp/tutorial-app/"

    # Resolve the recording env from the live cluster (worker IPs + VM user/home).
    local worker1 worker2 vm_user vm_home
    worker1="$(_worker_ip 1)"
    worker2="$(_worker_ip 2)"
    vm_user="$(_bridge_ssh 'whoami')"
    vm_home="$(_bridge_ssh 'echo $HOME')"
    log_info "Recording on bridge $bridge as $vm_user → worker $worker1 (backup ${worker2:-none})"

    # Record each changed tutorial on the bridge, then pull the cast back. The
    # cast is the only handoff artifact; downstream stages read it unchanged.
    for script in "${scripts_to_record[@]}"; do
        local base
        base="$(basename "$script" .sh)"
        log_step "Recording on bridge: $base"
        # No TUTORIAL_RDC_CMD: use the real rdc in the bridge PATH (setting it to
        # "rdc" would self-recurse — guarded in tutorial-helpers.sh regardless).
        _bridge_ssh "cd /tmp/rec && \
            TUTORIAL_MACHINE_IP='$worker1' \
            TUTORIAL_MACHINE_USER='$vm_user' \
            TUTORIAL_SSH_KEY='$vm_home/.ssh/id_rsa' \
            TUTORIAL_BACKUP_HOST='$worker2' \
            TUTORIAL_BACKUP_USER='$vm_user' \
            REDIACC_ALLOW_GRAND_REPO='${REDIACC_ALLOW_GRAND_REPO:-}' \
            MAX_IDLE_MS='${MAX_IDLE_MS:-800}' \
            bash /tmp/rec/.ci/tutorials/record.sh \
                /tmp/rec/.ci/tutorials/${base}.sh \
                /tmp/rec/out/${base}.cast $TUTORIAL_COLS $TUTORIAL_ROWS"
        _bridge_rsync "${bridge}:/tmp/rec/out/${base}.cast" "$output_dir/${base}.cast"
        log_info "Pulled cast → $output_dir/${base}.cast"

        # Update stored hash
        stored_hashes["$base"]="$(_tutorial_script_hash "$script")"
    done

    # Teardown VMs (skip with --keep-vms when the video render stage needs
    # the cluster + staged repos right after recording).
    if [[ "$keep_vms" == "true" ]]; then
        log_info "--keep-vms: leaving the cluster running"
    else
        log_step "Tearing down VMs..."
        provision_stop
    fi

    # Persist hashes
    : >"$hash_file"
    for key in "${!stored_hashes[@]}"; do
        echo "${key}=${stored_hashes[$key]}" >>"$hash_file"
    done
}

www_tutorials_extract() {
    check_node_version
    ensure_deps
    log_step "Extracting cast markers to transcript scaffolds..."
    npm run transcripts:extract -w @rediacc/www
}

www_tutorials_scaffold_locales() {
    check_node_version
    ensure_deps
    log_step "Scaffolding locale transcript files..."
    npm run transcripts:scaffold-locales -w @rediacc/www
}

www_tutorials_generate() {
    check_node_version
    ensure_generative_repo
    ensure_python_installed
    ensure_audio_system_deps
    www_tutorial_audio_restore

    local clean_venv=false
    local destroy_venv=false
    local passthrough=()

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --clean-venv)
                clean_venv=true
                shift
                ;;
            --destroy-venv)
                destroy_venv=true
                shift
                ;;
            *)
                passthrough+=("$1")
                shift
                ;;
        esac
    done

    ensure_generative_venv "$clean_venv"
    ensure_deps

    export QWEN_TTS_PYTHON_BIN="$ROOT_DIR/private/generative/.venv/bin/python"

    log_step "Generating tutorial audio assets..."
    npm run tutorials:tts:generate -w @rediacc/www -- "${passthrough[@]}"

    www_tutorial_audio_upload

    if [[ "$destroy_venv" == "true" ]]; then
        log_step "Destroying generative Python environment..."
        rm -rf "$ROOT_DIR/private/generative/.venv"
    fi
}

www_tutorials_video() {
    check_node_version
    ensure_deps
    ensure_audio_system_deps
    www_tutorial_audio_restore

    local name=""
    local lang=""
    local jobs=1
    local passthrough=()
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --lang)
                lang="$2"
                shift 2
                ;;
            --lang=*)
                lang="${1#*=}"
                shift
                ;;
            --jobs)
                jobs="$2"
                shift 2
                ;;
            --jobs=*)
                jobs="${1#*=}"
                shift
                ;;
            --keep-temp | --captions-only | --debug | --refresh-browser-cache | --no-browser-cache)
                passthrough+=("$1")
                shift
                ;;
            *)
                name="$1"
                shift
                ;;
        esac
    done

    if ! [[ "$jobs" =~ ^[0-9]+$ ]] || [[ "$jobs" -lt 1 ]]; then
        log_error "--jobs must be a positive integer, got: $jobs"
        exit 1
    fi

    local pairs=()
    local pair
    while IFS= read -r pair; do
        pairs+=("$pair")
    done < <(_tutorial_render_pairs "$name" "$lang")

    log_step "Compiling tutorial videos (${#pairs[@]} pair(s), --jobs $jobs)..."
    local failure_prefix="/tmp/_tut_video_failures.$$"
    rm -f "${failure_prefix}".*

    _tutorial_video_pool "$jobs" "$failure_prefix" "${passthrough[@]}" < <(printf '%s\n' "${pairs[@]}")

    if compgen -G "${failure_prefix}.*" >/dev/null; then
        log_error "Failed tutorials:"
        cat "${failure_prefix}".* >&2
        rm -f "${failure_prefix}".*
        return 1
    fi
}

# Narrate one language at a time on the GPU, and emit each language's render work to
# STDOUT the moment that language is finished and validated. Everything else goes to
# stderr, including all TTS output, so a stray Python print() can never be mistaken for
# a work item.
_tutorial_media_producer() {
    local name="$1"
    local tts_flags="$2"
    local failure_prefix="$3"
    shift 3
    local langs=("$@")

    local gen_dir="$ROOT_DIR/private/generative"
    local idx=0
    local l
    for l in "${langs[@]}"; do
        idx=$((idx + 1))
        log_step "narrating [$idx/${#langs[@]}] $l (GPU)" >&2

        # Invoked directly rather than through www_tutorials_generate ON PURPOSE. That
        # function calls www_tutorial_audio_restore first, which pulls PUBLISHED audio
        # from R2 and would overwrite narration we just generated, and
        # www_tutorial_audio_upload last, which publishes. This orchestrator generates
        # and renders only; publishing stays an explicit, separate operator decision.
        if ! (
            cd "$gen_dir" &&
                PYTHONPATH=src .venv/bin/python -m tutorial_tts.cli \
                    --repo-root "$ROOT_DIR" --lang "$l" \
                    ${name:+--cast "$name"} $tts_flags
        ) >&2; then
            log_error "narration failed for $l — skipping its renders, continuing to the next language"
            echo "narration: $l" >"${failure_prefix}.tts.${idx}"
            continue
        fi

        # Readiness gate. Not a done-marker written by the producer: this re-derives
        # every transcript hash, step count, replay range and wordTimings ordering from
        # the artifacts, and fails closed when nothing matched. Dispatching renders only
        # AFTER the narration process has exited is also what makes any intermediate
        # state of its timeline writes unobservable.
        if ! node "$ROOT_DIR/packages/www/scripts/validate-tutorial-audio.js" \
            --lang "$l" ${name:+--cast "$name"} --quiet >&2; then
            log_error "validation failed for $l — skipping its renders, continuing to the next language"
            echo "validation: $l" >"${failure_prefix}.val.${idx}"
            continue
        fi

        log_info "$l narrated and validated — dispatching its renders (CPU)" >&2
        _tutorial_render_pairs "$name" "$l"
    done
}

# Narrate on the GPU and render on the CPU AT THE SAME TIME.
#
# The two halves of tutorial media production use disjoint hardware: narration is a
# VoxCPM2 job that saturates the GPU, rendering is headless Chrome plus a software
# x264 encode. Running them in sequence leaves one of the two idle throughout, so the
# wall clock is sum(narrate) + sum(render). Overlapping makes it
# sum(narrate) + render(last language) -- roughly 45% off across 13 languages when the
# two halves cost about the same.
#
# Correctness rests on three things that are enforced elsewhere, not on scheduling luck:
# the GPU lease in tutorial_tts/gpu_lock.py means a second narration can never co-reside
# with the first; timelines are written with os.replace, so a render reading one while
# another language is being narrated sees whole JSON or nothing; and the per-language
# validation gate refuses to dispatch renders for narration that did not finish clean.
www_tutorials_media() {
    check_node_version
    ensure_generative_repo
    ensure_python_installed
    ensure_audio_system_deps

    local name=""
    local langs_csv=""
    local jobs=""
    local clean_venv=false
    local tts_flags=""
    local passthrough=()

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --langs) langs_csv="$2" && shift 2 ;;
            --langs=*) langs_csv="${1#*=}" && shift ;;
            --jobs) jobs="$2" && shift 2 ;;
            --jobs=*) jobs="${1#*=}" && shift ;;
            --clean-venv) clean_venv=true && shift ;;
            --subtitle | --force | --resubtitle | --keep-wav)
                tts_flags="$tts_flags $1"
                shift
                ;;
            --keep-temp | --captions-only | --debug | --refresh-browser-cache | --no-browser-cache)
                passthrough+=("$1")
                shift
                ;;
            *) name="$1" && shift ;;
        esac
    done

    ensure_generative_venv "$clean_venv"
    ensure_deps

    local langs=()
    if [[ -n "$langs_csv" ]]; then
        IFS=',' read -r -a langs <<<"$langs_csv"
    else
        local d
        for d in "$ROOT_DIR/packages/www/src/data/tutorial-timeline"/*/; do
            [[ -d "$d" ]] || continue
            langs+=("$(basename "$d")")
        done
    fi
    if [[ ${#langs[@]} -eq 0 ]]; then
        log_error "No languages to process."
        return 1
    fi

    if [[ -z "$jobs" ]]; then
        jobs="$(_tutorial_auto_jobs)"
    fi
    if ! [[ "$jobs" =~ ^[0-9]+$ ]] || [[ "$jobs" -lt 1 ]]; then
        log_error "--jobs must be a positive integer, got: $jobs"
        return 1
    fi

    # Hardware encoding stays OFF. h264_nvenc would put the render back on the very
    # device the narration job needs, which is the entire premise of overlapping them.
    if [[ "${RDC_TUTORIAL_HWENC:-0}" == "1" ]]; then
        log_warn "RDC_TUTORIAL_HWENC=1 was set; forcing it to 0 so renders stay off the GPU"
    fi
    export RDC_TUTORIAL_HWENC=0

    # Deliberately NOT calling www_tutorial_audio_restore. It pulls published narration
    # from R2 and would overwrite exactly what this run is about to generate.
    log_step "Tutorial media: narrating ${#langs[@]} language(s) on GPU, rendering on CPU with --jobs $jobs"

    local failure_prefix="/tmp/_tut_media_failures.$$"
    rm -f "${failure_prefix}".*

    _tutorial_media_producer "$name" "$tts_flags" "$failure_prefix" "${langs[@]}" |
        _tutorial_video_pool "$jobs" "$failure_prefix" "${passthrough[@]}"

    if compgen -G "${failure_prefix}.*" >/dev/null; then
        log_error "Failures:"
        cat "${failure_prefix}".* >&2
        rm -f "${failure_prefix}".*
        return 1
    fi
    log_info "Tutorial media complete for: ${langs[*]}"
}

# Emit each (tutorial, lang) pair to STDOUT the moment THAT PAIR's narration is final.
#
# The unit of readiness is the PAIR, not the language: tutorial_tts/cli.py finishes one
# (lang, cast) completely -- synthesis, the deferred alignment barrier, then an atomic
# os.replace of the timeline -- before starting the next. A per-language trigger left the
# CPU idle at load 2.4 for ~20 minutes while 13 already-narrated tutorials sat unrendered.
#
# STDOUT IS THE WORK QUEUE. Every diagnostic goes to stderr (log_step/log_info/log_error
# already do); one stray echo here becomes a bogus render.
#
# The emit-once memo is keyed by the pair's TIMELINE MTIME, and that key choice is doing
# two jobs at once:
#   - no duplicate dispatch while a render is in flight (the pair is still stale, because
#     its mp4 is not written yet, so it is still listed every round);
#   - no hot spin on a pair that keeps failing to render (it stays stale forever, and
#     without the memo it would be re-listed and re-dispatched as fast as the loop turns,
#     never reaching the idle sleep).
# Re-narration bumps the mtime, which changes the key, so a genuinely UPDATED pair IS
# re-emitted. That self-correction is the whole reason readiness is read from artifacts
# rather than from bookkeeping, and it must survive any change here.
_tutorial_watch_producer() {
    local poll="$1"
    local once="$2"
    local langs_csv="$3"
    local queue_file="$4"

    local timeline_root="$ROOT_DIR/packages/www/src/data/tutorial-timeline"
    declare -A emitted=()
    local round=0

    while :; do
        round=$((round + 1))

        # Sample narration liveness BEFORE listing, never after. A pair that lands
        # between the two samples must be caught by the NEXT list rather than lost to a
        # "nothing stale, nothing running" verdict reached on stale evidence.
        #
        # `ps -eo cmd` plus a bracketed pattern, never `pgrep -f`: pgrep -f matches THIS
        # shell, whose own command line contains the pattern, and has already produced a
        # false "alive" verdict in this pipeline. The output is captured into a variable
        # first because `ps | grep -q` under `set -o pipefail` can come back 141 -- grep -q
        # closes the pipe, ps takes SIGPIPE -- which reads as "not running".
        local ps_out narrating=0
        ps_out="$(ps -eo cmd 2>/dev/null || true)"
        if grep -q '[t]utorial_tts\.cli' <<<"$ps_out"; then
            narrating=1
        fi

        # The ONE readiness predicate, asked the narrow question. Failure stops the watch:
        # it refuses on an empty tree on purpose, and a daemon that treated "the predicate
        # broke" as "nothing to do" would idle forever looking healthy.
        if ! _tutorial_render_pairs "" "$langs_csv" --stale-only --require-provider voxcpm2 >"$queue_file"; then
            log_error "readiness predicate failed — stopping the watch instead of guessing"
            return 1
        fi

        local emitted_now=0 stale_now=0
        local t l key mtime timeline
        while IFS=$'\t' read -r t l; do
            [[ -n "$t" && -n "$l" ]] || continue
            stale_now=$((stale_now + 1))
            timeline="$timeline_root/$l/$t.json"
            mtime="$(media_mtime "$timeline" 2>/dev/null || echo 0)"
            key="$l/$t@$mtime"
            [[ -n "${emitted[$key]:-}" ]] && continue
            emitted["$key"]=1
            emitted_now=$((emitted_now + 1))
            printf '%s\t%s\n' "$t" "$l"
        done <"$queue_file"

        if [[ "$emitted_now" -gt 0 ]]; then
            log_info "round $round: dispatched $emitted_now newly-ready pair(s) of $stale_now stale"
        fi

        if [[ "$once" == "true" ]]; then
            return 0
        fi

        # Done when there is nothing new to dispatch AND no narrator is left to produce
        # any. Anything still stale at this point has already been emitted, so the pool's
        # final `wait` drains it; stopping here rather than on stale_now == 0 is what keeps
        # a permanently-failing pair from holding the daemon open forever.
        if [[ "$emitted_now" -eq 0 && "$narrating" -eq 0 ]]; then
            log_info "nothing new to render and no tutorial_tts.cli running — producer done after $round round(s)"
            return 0
        fi

        sleep "$poll"
    done
}

# Render each (tutorial, language) pair as soon as that pair's narration is final.
#
# Renders ONLY. It never narrates, and it deliberately does not go through
# www_tutorials_video or www_tutorials_generate: both call www_tutorial_audio_restore,
# which pulls PUBLISHED audio down from R2 and would overwrite exactly the fresh local
# narration this watch exists to consume.
#
# It also never touches the GPU lease. That lease (tutorial_tts/gpu_lock.py) is taken
# LAZILY by the TTS engine at its first real model load; wrapping a renderer in it
# self-deadlocks, which has already happened once in tts_bridge.py.
www_tutorials_watch() {
    # Preflight output is forced onto stderr because stdout belongs to the work queue.
    # ensure_deps shells out to `npm install`, whose "up to date, audited 1105 packages"
    # chatter goes to stdout -- 12 lines of it landed in the --dry-run pair list before
    # this redirect existed, which is exactly the shape of a bogus render.
    {
        check_node_version
        ensure_deps
        ensure_audio_system_deps
    } >&2

    local langs_csv=""
    local jobs=""
    local poll=30
    local once=false
    local dry_run=false
    local passthrough=()

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --langs) langs_csv="$2" && shift 2 ;;
            --langs=*) langs_csv="${1#*=}" && shift ;;
            --jobs) jobs="$2" && shift 2 ;;
            --jobs=*) jobs="${1#*=}" && shift ;;
            --poll) poll="$2" && shift 2 ;;
            --poll=*) poll="${1#*=}" && shift ;;
            --once) once=true && shift ;;
            --dry-run) dry_run=true && shift ;;
            --keep-temp | --captions-only | --debug | --refresh-browser-cache | --no-browser-cache)
                passthrough+=("$1")
                shift
                ;;
            *)
                log_error "Unknown watch option: $1"
                log_info "Usage: ./run.sh www tutorials watch [--jobs N] [--langs a,b] [--poll N] [--once] [--dry-run]"
                return 1
                ;;
        esac
    done

    if [[ -z "$jobs" ]]; then
        jobs="$(_tutorial_auto_jobs)"
    fi
    if ! [[ "$jobs" =~ ^[0-9]+$ ]] || [[ "$jobs" -lt 1 ]]; then
        log_error "--jobs must be a positive integer, got: $jobs"
        return 1
    fi
    if ! [[ "$poll" =~ ^[0-9]+$ ]] || [[ "$poll" -lt 1 ]]; then
        log_error "--poll must be a positive integer (seconds), got: $poll"
        return 1
    fi

    # Repo-local and session-agnostic, so a watch started from one shell is inspectable
    # from any other. artifacts/ is gitignored.
    local watch_dir="$ROOT_DIR/artifacts/tutorial-render-watch"
    mkdir -p "$watch_dir"
    local lock_file="$watch_dir/watch.lock"
    local pid_file="$watch_dir/watch.pid"
    local queue_file="$watch_dir/queue.txt"
    local log_file
    log_file="$watch_dir/watch-$(date -u +%Y%m%dT%H%M%SZ).log"

    # SINGLE INSTANCE, enforced by the kernel. The per-tutorial flock inside
    # _tutorial_video_render_one serialises two renders of the SAME tutorial; it does
    # nothing to stop two daemons from both deciding to rewrite the same mp4. The kernel
    # lock is the truth and is released when the holder dies, so a killed watch leaves
    # nothing to clean up. The pid file is observability only -- written after the lock is
    # held, and only ever read to name the holder in this error.
    exec 9>"$lock_file"
    if ! flock -n 9; then
        local holder=""
        [[ -f "$pid_file" ]] && holder="$(cat "$pid_file" 2>/dev/null || true)"
        log_error "another tutorial render watch already holds $lock_file (pid ${holder:-unknown})"
        log_info "wait for it to drain, or stop it, before starting a second one"
        return 1
    fi
    echo "$$" >"$pid_file"

    # Everything diagnostic in this pipeline is on stderr (log_step/log_info/log_error
    # all are), so tee'ing stderr once here captures the WHOLE run -- header included --
    # while still showing it live in the foreground. stdout is untouched because it is the
    # work queue: under --dry-run the pair list must stay clean enough to diff.
    exec 2> >(tee -a "$log_file" >&2)

    # Hardware encoding stays OFF: h264_nvenc would put the render back on the very
    # device the narration needs, which is the entire premise of overlapping them.
    if [[ "${RDC_TUTORIAL_HWENC:-0}" == "1" ]]; then
        log_warn "RDC_TUTORIAL_HWENC=1 was set; forcing it to 0 so renders stay off the GPU"
    fi
    export RDC_TUTORIAL_HWENC=0

    local failure_prefix="$watch_dir/failures.$$"
    rm -f "${failure_prefix}".*

    log_step "Tutorial render watch: --jobs $jobs, --poll ${poll}s${langs_csv:+, langs $langs_csv}"
    log_info "pid $$, lock $lock_file, log $log_file"

    local status=0
    if [[ "$dry_run" == "true" ]]; then
        # The producer's stdout IS the work queue, so printing it is the dry run: the pool
        # is never started and not one render is dispatched.
        _tutorial_watch_producer "$poll" "$once" "$langs_csv" "$queue_file" || status=$?
    else
        _tutorial_watch_producer "$poll" "$once" "$langs_csv" "$queue_file" |
            _tutorial_video_pool "$jobs" "$failure_prefix" "${passthrough[@]}" || status=$?
    fi

    rm -f "$pid_file"

    if compgen -G "${failure_prefix}.*" >/dev/null; then
        log_error "Render failures (recorded and NOT retried — re-narrate the pair to make it eligible again):"
        cat "${failure_prefix}".* >&2
        rm -f "${failure_prefix}".*
        status=1
    fi

    if [[ "$status" -ne 0 ]]; then
        return "$status"
    fi
    log_info "Tutorial render watch finished cleanly"
}

www_tutorials_validate() {
    check_node_version
    ensure_deps
    log_step "Validating tutorial cast output..."
    npm run validate:tutorial-cast-output -w @rediacc/www
    log_step "Validating tutorial transcripts..."
    npm run validate:tutorial-transcripts -w @rediacc/www
    log_step "Validating tutorial audio..."
    npm run validate:tutorial-audio -w @rediacc/www
    # Web<->video parity (cast markers vs storyboard vs transcript vs MDX, incl.
    # card.commandFull). Mirrors CI's check:ci-tutorial-parity so local runs catch drift.
    log_step "Checking tutorial web/video parity..."
    npm run check:ci-tutorial-parity
}

www_tutorials_all() {
    # Split args: --lang / --keep-temp / --clean-venv / --destroy-venv only flow
    # to the steps that understand them. Everything else is treated as a
    # tutorial-name positional and passed to record + generate + video.
    local lang_args=()
    local audio_args=()
    local video_args=()
    local record_args=()
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --lang)
                lang_args+=("$1" "$2")
                shift 2
                ;;
            --lang=*)
                lang_args+=("$1")
                shift
                ;;
            --keep-temp)
                video_args+=("$1")
                shift
                ;;
            --clean-venv | --destroy-venv | --subtitle)
                audio_args+=("$1")
                shift
                ;;
            --force)
                record_args+=("$1")
                shift
                ;;
            --max-idle-ms)
                record_args+=("$1" "$2")
                shift 2
                ;;
            --max-idle-ms=*)
                record_args+=("$1")
                shift
                ;;
            *)
                record_args+=("$1")
                shift
                ;;
        esac
    done

    log_step "Running full tutorial pipeline..."
    www_tutorials_record ${record_args[@]+"${record_args[@]}"}
    www_tutorials_extract
    www_tutorials_scaffold_locales
    www_tutorials_generate ${audio_args[@]+"${audio_args[@]}"} ${lang_args[@]+"${lang_args[@]}"}
    www_tutorials_video ${video_args[@]+"${video_args[@]}"} ${lang_args[@]+"${lang_args[@]}"}
    www_tutorials_validate
    log_info "Tutorial pipeline complete!"
}

www_all() {
    log_step "Running full www asset pipeline..."
    www_tutorials_all "$@"
    log_info "All www assets generated!"
}
