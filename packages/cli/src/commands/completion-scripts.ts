/**
 * The shell scripts `rdc completion` prints: one renderer per shell over the
 * completion model that completion.ts builds from the contract. bash and zsh
 * share one portable core; fish and pwsh carry their own.
 */

import type { CompletionModel, CompletionShell } from './completion.js';
import { shell, tablesOf } from './completion-tables.js';

// ── bash and zsh: one portable core ─────────────────────────────────────────

function shTable(fn: string, rows: [string, string[]][]): string {
  const cases = rows.map(([key, words]) => `    '${key}') _rdc_r='${words.join(' ')}' ;;`);
  return [`${fn}() {`, '  case $1 in', ...cases, "    *) _rdc_r='' ;;", '  esac', '}'].join('\n');
}

function shRunnable(keys: string[]): string {
  const cases = keys.map((key) => `    '${key}') return 0 ;;`);
  return ['_rdc_runnable() {', '  case $1 in', ...cases, '  esac', '  return 1', '}'].join('\n');
}

/**
 * The walker in the subset bash and zsh (under `emulate -L ksh`) share. It reads
 * the words before the cursor, leaves the candidates newline-separated in
 * `_rdc_out`, and sets `_rdc_wantfiles` when a path slot is open. A candidate
 * for `--flag=val` carries the `--flag=` prefix; the bash wrapper cuts what bash
 * already split off at COMP_WORDBREAKS.
 */
const SH_CORE = shell`_rdc_nl='
'

_rdc_add() {
  local w
  for w in $1; do
    case $w in
      "$2"*) _rdc_out="$_rdc_out$3$w$_rdc_nl" ;;
    esac
  done
}

_rdc_names() {
  local name="$2" dir file mtime var val head
  [ -n "$name" ] || name="$~{REDIACC_CONFIG:-rediacc}"
  case $~{OSTYPE:-} in
    darwin*) dir="$HOME/Library/Application Support/rediacc" ;;
    *) dir="$~{XDG_CONFIG_HOME:-$HOME/.config}/rediacc" ;;
  esac
  file="$dir/$name.json"
  _rdc_r=''
  [ -f "$file" ] || return 0
  mtime=$(stat -c %Y -- "$file" 2>/dev/null || stat -f %m -- "$file" 2>/dev/null)
  var="_rdc_cache_$1_$~{name//[^A-Za-z0-9_]/_}"
  eval "val=\$~{$var-}"
  head="$mtime|$file$_rdc_nl"
  case $val in
    "$head"*) _rdc_r="$~{val#"$head"}"; return 0 ;;
  esac
  # A failed lookup is not cached, so the next Tab asks again.
  _rdc_r=$(command rdc __complete --kind "$1" --config "$name" 2>/dev/null) || { _rdc_r=''; return 0; }
  eval "$var=\$head\$_rdc_r"
}

_rdc_values() {
  local s
  for s in $1; do
    case $s in
      @*) _rdc_names "$~{s#@}" "$3"; _rdc_add "$_rdc_r" "$2" "$4" ;;
      %file) _rdc_wantfiles=1 ;;
      *) _rdc_add "$s" "$2" "$4" ;;
    esac
  done
}

_rdc_takes() {
  local f
  _rdc_vflags "$1"
  for f in $_rdc_r $_rdc_gvflags; do
    [ "$f" = "$2" ] && return 0
  done
  return 1
}

_rdc_is_child() {
  local c
  _rdc_children "$1"
  for c in $_rdc_r; do
    [ "$c" = "$2" ] && return 0
  done
  return 1
}

_rdc_posspec() {
  local i="$2" count variadic
  _rdc_posinfo "$1"
  [ -n "$_rdc_r" ] || return 0
  count="$~{_rdc_r% *}"
  variadic="$~{_rdc_r#* }"
  if [ "$i" -ge "$count" ]; then
    [ "$variadic" = 1 ] || { _rdc_r=''; return 0; }
    i=$((count - 1))
  fi
  _rdc_pos "$1|$i"
}

_rdc_compute() {
  local cur="$1" npos=0 cfg='' pending='' w _rdc_r='' _rdc_p=rdc
  shift
  _rdc_out=''
  for w in "$@"; do
    if [ -n "$pending" ]; then
      [ "$pending" != --config ] || cfg="$w"
      pending=''
      continue
    fi
    case $w in
      --) return 0 ;;
      --*=*) [ "$~{w%%=*}" != --config ] || cfg="$~{w#*=}"; continue ;;
      -*) ! _rdc_takes "$_rdc_p" "$w" || pending="$w"; continue ;;
    esac
    if [ "$npos" -eq 0 ] && _rdc_is_child "$_rdc_p" "$w"; then
      _rdc_p="$_rdc_p $w"
    else
      npos=$((npos + 1))
    fi
  done
  if [ -n "$pending" ]; then
    _rdc_flagval "$_rdc_p|$pending"
    _rdc_values "$_rdc_r" "$cur" "$cfg" ''
    return 0
  fi
  case $cur in
    --*=*)
      _rdc_flagval "$_rdc_p|$~{cur%%=*}"
      _rdc_values "$_rdc_r" "$~{cur#*=}" "$cfg" "$~{cur%%=*}="
      return 0 ;;
    -*)
      _rdc_flags "$_rdc_p"
      _rdc_add "$_rdc_r $_rdc_gflags" "$cur" ''
      return 0 ;;
  esac
  if [ "$npos" -eq 0 ]; then
    _rdc_children "$_rdc_p"
    _rdc_add "$_rdc_r" "$cur" ''
  fi
  _rdc_runnable "$_rdc_p" || return 0
  _rdc_posspec "$_rdc_p" "$npos"
  _rdc_values "$_rdc_r" "$cur" "$cfg" ''
}`;

function shData(model: CompletionModel): string {
  const tables = tablesOf(model);
  return [
    `_rdc_gflags='${model.globalFlags.join(' ')}'`,
    `_rdc_gvflags='${model.globalValueFlags.join(' ')}'`,
    shTable('_rdc_children', tables.children),
    shRunnable(tables.runnable),
    shTable('_rdc_flags', tables.flags),
    shTable('_rdc_vflags', tables.valueFlags),
    shTable('_rdc_flagval', tables.flagValues),
    shTable('_rdc_posinfo', tables.posInfo),
    shTable('_rdc_pos', tables.positionals),
  ].join('\n\n');
}

const BASH_WRAPPER = shell`_rdc_bash() {
  local line="$~{COMP_LINE:0:COMP_POINT}" cur='' pre='' bw w _rdc_out='' _rdc_wantfiles=''
  local -a words
  read -ra words <<< "$line"
  case $line in
    *[[:space:]]) ;;
    *) cur="$~{words[$~{#words[@]}-1]}"; unset "words[$~{#words[@]}-1]" ;;
  esac
  _rdc_compute "$cur" "$~{words[@]:1}"
  bw="$~{COMP_WORDS[COMP_CWORD]}"
  case $cur in
    *"$bw") pre="$~{cur%"$bw"}" ;;
  esac
  COMPREPLY=()
  while IFS= read -r w; do
    [ -n "$w" ] && COMPREPLY+=("$~{w#"$pre"}")
  done <<< "$_rdc_out"
  if [ -n "$_rdc_wantfiles" ]; then
    while IFS= read -r w; do
      [ -n "$w" ] && COMPREPLY+=("$w")
    done <<< "$(compgen -f -- "$bw")"
  fi
}

complete -F _rdc_bash rdc`;

const ZSH_WRAPPER = shell`_rdc_zsh_compute() {
  emulate -L ksh
  _rdc_compute "$@"
}

_rdc_zsh() {
  local cur="$~{words[CURRENT]}" _rdc_out='' _rdc_wantfiles=''
  local -a before cands
  before=("$~{(@)words[2,CURRENT-1]}")
  _rdc_zsh_compute "$cur" "$~{before[@]}"
  cands=("$~{(@f)_rdc_out}")
  cands=("$~{(@)cands:#}")
  (( $~{#cands} )) && compadd -- "$~{cands[@]}"
  [[ -n $_rdc_wantfiles ]] && _files
  return 0
}

if ! (( $+functions[compdef] )); then
  autoload -Uz compinit && compinit
fi
compdef _rdc_zsh rdc`;

function renderBash(model: CompletionModel): string {
  return [
    '# rdc completion for bash. Load: eval "$(rdc completion bash)"',
    shData(model),
    SH_CORE,
    BASH_WRAPPER,
    '',
  ].join('\n\n');
}

function renderZsh(model: CompletionModel): string {
  return [
    '#compdef rdc',
    '# rdc completion for zsh. Load: eval "$(rdc completion zsh)"',
    shData(model),
    SH_CORE,
    ZSH_WRAPPER,
    '',
  ].join('\n\n');
}

// ── fish ─────────────────────────────────────────────────────────────────

function fishTable(fn: string, rows: [string, string[]][]): string {
  const cases = rows.map(
    ([key, words]) => `        case '${key}'\n            printf '%s\\n' ${words.join(' ')}`
  );
  return [`function ${fn}`, '    switch $argv[1]', ...cases, '    end', 'end'].join('\n');
}

function fishRunnable(keys: string[]): string {
  const cases = keys.map((key) => `        case '${key}'\n            return 0`);
  return [
    'function __rdc_runnable',
    '    switch $argv[1]',
    ...cases,
    '    end',
    '    return 1',
    'end',
  ].join('\n');
}

const FISH_CORE = shell`if test (uname) = Darwin
    set -g __rdc_darwin 1
end

function __rdc_add
    set -l cur $argv[1]
    set -l pre $argv[2]
    set -e argv[1..2]
    set -l n (string length -- "$cur")
    for w in $argv
        set -l head (string sub -l $n -- "$w")
        if test "$head" = "$cur"
            echo "$pre$w"
        end
    end
end

function __rdc_names
    set -l kind $argv[1]
    set -l name $argv[2]
    test -n "$name"; or set name $REDIACC_CONFIG
    test -n "$name"; or set name rediacc
    set -l dir
    if set -q __rdc_darwin
        set dir "$HOME/Library/Application Support/rediacc"
    else if set -q XDG_CONFIG_HOME; and test -n "$XDG_CONFIG_HOME"
        set dir "$XDG_CONFIG_HOME/rediacc"
    else
        set dir "$HOME/.config/rediacc"
    end
    set -l file "$dir/$name.json"
    test -f "$file"; or return 0
    set -l mtime (stat -c %Y -- "$file" 2>/dev/null; or stat -f %m -- "$file" 2>/dev/null)
    set -l slot (string replace -ra '[^A-Za-z0-9_]' _ -- "$kind"_"$name")
    set -l keyvar __rdc_cachekey_$slot
    set -l var __rdc_cache_$slot
    set -l stamp
    set -q $keyvar; and set stamp $$keyvar
    if test "$stamp" = "$mtime|$file"
        test (count $$var) -gt 0; and printf '%s\n' $$var
        return 0
    end
    # A failed lookup is not cached, so the next Tab asks again.
    set -l names (command rdc __complete --kind $kind --config $name 2>/dev/null); or return 0
    set -g $var $names
    set -g $keyvar "$mtime|$file"
    test (count $names) -gt 0; and printf '%s\n' $names
end

function __rdc_values
    set -l cur $argv[1]
    set -l cfg $argv[2]
    set -l pre $argv[3]
    set -e argv[1..3]
    for s in $argv
        switch $s
            case '@*'
                __rdc_add "$cur" "$pre" (__rdc_names (string sub -s 2 -- $s) "$cfg")
            case '%file'
                __fish_complete_path "$cur"
            case '*'
                __rdc_add "$cur" "$pre" $s
        end
    end
end

function __rdc_posspec
    set -l info (__rdc_posinfo $argv[1])
    test (count $info) -eq 2; or return 0
    set -l i $argv[2]
    if test $i -ge $info[1]
        test $info[2] = 1; or return 0
        set i (math $info[1] - 1)
    end
    __rdc_pos "$argv[1]|$i"
end

function __rdc_complete
    set -l tokens (commandline -opc)
    set -l cur (commandline -ct)
    set -e tokens[1]
    set -l cpath rdc
    set -l npos 0
    set -l cfg ''
    set -l pending ''
    for w in $tokens
        if test -n "$pending"
            test "$pending" = --config; and set cfg $w
            set pending ''
            continue
        end
        if test "$w" = --
            return 0
        end
        if string match -q -- '--*=*' $w
            set -l parts (string split -m1 = -- $w)
            test "$parts[1]" = --config; and set cfg $parts[2]
            continue
        end
        if string match -q -- '-*' $w
            if contains -- $w (__rdc_vflags $cpath) $__rdc_gvflags
                set pending $w
            end
            continue
        end
        if test $npos -eq 0; and contains -- $w (__rdc_children $cpath)
            set cpath "$cpath $w"
        else
            set npos (math $npos + 1)
        end
    end
    if test -n "$pending"
        __rdc_values "$cur" "$cfg" '' (__rdc_flagval "$cpath|$pending")
        return 0
    end
    if string match -q -- '--*=*' "$cur"
        set -l parts (string split -m1 = -- "$cur")
        __rdc_values "$parts[2]" "$cfg" "$parts[1]=" (__rdc_flagval "$cpath|$parts[1]")
        return 0
    end
    if string match -q -- '-*' "$cur"
        __rdc_add "$cur" '' (__rdc_flags $cpath) $__rdc_gflags
        return 0
    end
    if test $npos -eq 0
        __rdc_add "$cur" '' (__rdc_children $cpath)
    end
    __rdc_runnable $cpath; or return 0
    __rdc_values "$cur" "$cfg" '' (__rdc_posspec $cpath $npos)
end

complete -c rdc -e
complete -c rdc -f -a '(__rdc_complete)'`;

function renderFish(model: CompletionModel): string {
  const tables = tablesOf(model);
  return [
    '# rdc completion for fish. Load: rdc completion fish | source',
    `set -g __rdc_gflags ${model.globalFlags.join(' ')}`,
    `set -g __rdc_gvflags ${model.globalValueFlags.join(' ')}`,
    fishTable('__rdc_children', tables.children),
    fishRunnable(tables.runnable),
    fishTable('__rdc_flags', tables.flags),
    fishTable('__rdc_vflags', tables.valueFlags),
    fishTable('__rdc_flagval', tables.flagValues),
    fishTable('__rdc_posinfo', tables.posInfo),
    fishTable('__rdc_pos', tables.positionals),
    FISH_CORE,
    '',
  ].join('\n\n');
}

// ── PowerShell ───────────────────────────────────────────────────────────────

function pwshTable(name: string, rows: [string, string[]][]): string {
  const lines = rows.map(([key, words]) => `$__rdc.${name}['${key}'] = '${words.join(' ')}'`);
  return [`$__rdc.${name} = [hashtable]::new([StringComparer]::Ordinal)`, ...lines].join('\n');
}

const PWSH_CORE = shell`function global:__RdcWords([string]$text) {
    if ($text) { return @($text -split ' ' | Where-Object { $_ }) }
    return @()
}

function global:__RdcAdd([string]$cur, [string]$pre, [string[]]$words) {
    foreach ($w in $words) {
        if ($w -and $w.StartsWith($cur, [StringComparison]::Ordinal)) { $pre + $w }
    }
}

function global:__RdcNames([string]$kind, [string]$name) {
    if (-not $name) { $name = $env:REDIACC_CONFIG }
    if (-not $name) { $name = 'rediacc' }
    if ($env:OS -eq 'Windows_NT') { $dir = Join-Path $env:APPDATA 'rediacc' }
    elseif ($IsMacOS) { $dir = Join-Path $HOME 'Library/Application Support/rediacc' }
    elseif ($env:XDG_CONFIG_HOME) { $dir = Join-Path $env:XDG_CONFIG_HOME 'rediacc' }
    else { $dir = Join-Path $HOME '.config/rediacc' }
    $file = Join-Path $dir "$name.json"
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { return @() }
    $stamp = '{0}|{1}' -f (Get-Item -LiteralPath $file).LastWriteTimeUtc.Ticks, $file
    $slot = "$kind|$name"
    $hit = $global:__RdcNameCache[$slot]
    if ($hit -and $hit.Stamp -eq $stamp) { return $hit.Names }
    # A failed lookup is not cached, so the next Tab asks again.
    $names = @(& rdc __complete --kind $kind --config $name 2>$null)
    if ($LASTEXITCODE -ne 0) { return @() }
    $global:__RdcNameCache[$slot] = @{ Stamp = $stamp; Names = $names }
    return $names
}

function global:__RdcValues([string]$spec, [string]$cur, [string]$cfg, [string]$pre) {
    foreach ($s in (__RdcWords $spec)) {
        if ($s.StartsWith('@')) { __RdcAdd $cur $pre @(__RdcNames $s.Substring(1) $cfg) }
        elseif ($s -ceq '%file') {
            [System.Management.Automation.CompletionCompleters]::CompleteFilename($cur) |
                ForEach-Object { $_.CompletionText }
        }
        else { __RdcAdd $cur $pre @($s) }
    }
}

function global:__RdcPosSpec([string]$path, [int]$i) {
    $info = @(__RdcWords $__rdc.PosInfo[$path])
    if ($info.Count -ne 2) { return '' }
    $count = [int]$info[0]
    if ($i -ge $count) {
        if ($info[1] -ne '1') { return '' }
        $i = $count - 1
    }
    return $__rdc.Pos["$path|$i"]
}

function global:__RdcComplete([string]$cur, [string[]]$before) {
    $path = 'rdc'; $npos = 0; $cfg = ''; $pending = ''
    foreach ($w in $before) {
        if ($pending) {
            if ($pending -ceq '--config') { $cfg = $w }
            $pending = ''
            continue
        }
        if ($w -ceq '--') { return }
        if ($w -clike '--*=*') {
            $parts = $w.Split('=', 2)
            if ($parts[0] -ceq '--config') { $cfg = $parts[1] }
            continue
        }
        if ($w.StartsWith('-')) {
            $takes = @(__RdcWords $__rdc.ValueFlags[$path]) + @(__RdcWords $__rdc.GlobalValueFlags)
            if ($takes -ccontains $w) { $pending = $w }
            continue
        }
        if ($npos -eq 0 -and (@(__RdcWords $__rdc.Children[$path]) -ccontains $w)) { $path = "$path $w" }
        else { $npos++ }
    }
    if ($pending) { return __RdcValues $__rdc.FlagValues["$path|$pending"] $cur $cfg '' }
    if ($cur -clike '--*=*') {
        $parts = $cur.Split('=', 2)
        return __RdcValues $__rdc.FlagValues["$path|$($parts[0])"] $parts[1] $cfg "$($parts[0])="
    }
    if ($cur.StartsWith('-')) {
        return __RdcAdd $cur '' (@(__RdcWords $__rdc.Flags[$path]) + @(__RdcWords $__rdc.GlobalFlags))
    }
    if ($npos -eq 0) { __RdcAdd $cur '' @(__RdcWords $__rdc.Children[$path]) }
    if ($__rdc.Runnable.Contains($path)) { __RdcValues (__RdcPosSpec $path $npos) $cur $cfg '' }
}

Register-ArgumentCompleter -Native -CommandName rdc -ScriptBlock {
    param($wordToComplete, $commandAst, $cursorPosition)
    $before = @($commandAst.CommandElements |
        Select-Object -Skip 1 |
        Where-Object { $_.Extent.EndOffset -lt $cursorPosition } |
        ForEach-Object { $_.Extent.Text })
    __RdcComplete ([string]$wordToComplete) $before | ForEach-Object {
        [System.Management.Automation.CompletionResult]::new($_, $_, 'ParameterValue', $_)
    }
}`;

function renderPwsh(model: CompletionModel): string {
  const tables = tablesOf(model);
  const runnable = tables.runnable.map((key) => `[void]$__rdc.Runnable.Add('${key}')`);
  return [
    '# rdc completion for PowerShell. Load: rdc completion pwsh | Out-String | Invoke-Expression',
    [
      '$global:__rdc = @{}',
      '$global:__RdcNameCache = @{}',
      `$__rdc.GlobalFlags = '${model.globalFlags.join(' ')}'`,
      `$__rdc.GlobalValueFlags = '${model.globalValueFlags.join(' ')}'`,
      '$__rdc.Runnable = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)',
      ...runnable,
    ].join('\n'),
    pwshTable('Children', tables.children),
    pwshTable('Flags', tables.flags),
    pwshTable('ValueFlags', tables.valueFlags),
    pwshTable('FlagValues', tables.flagValues),
    pwshTable('PosInfo', tables.posInfo),
    pwshTable('Pos', tables.positionals),
    PWSH_CORE,
    '',
  ].join('\n\n');
}

const RENDERERS: Record<CompletionShell, (model: CompletionModel) => string> = {
  bash: renderBash,
  zsh: renderZsh,
  fish: renderFish,
  pwsh: renderPwsh,
};

/** The completion script of `shell` for `model`. */
export function renderModelScript(shell: CompletionShell, model: CompletionModel): string {
  return RENDERERS[shell](model);
}
