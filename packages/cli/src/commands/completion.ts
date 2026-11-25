/**
 * `rdc completion bash|zsh|fish|pwsh` and the hidden `rdc __complete`
 * (D9 of PLAN-console-command-line).
 *
 * The printed script carries every command, flag and choice word of the
 * contract, read through the command line core at print time, so static
 * completion runs in the shell alone. A value slot bound to a config-sourced
 * resource kind asks `rdc __complete --kind <k> [--config <n>]` for names, and
 * the script keeps each answer for the shell session, keyed on the config
 * file's mtime, so only the first lookup after a config change pays a CLI start.
 *
 * `__complete` reads the config file directly. cli.ts answers it from
 * {@link createCompleteProgram}, a program holding only this command, so the
 * full command tree is never built for it and it never reaches the contract.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import {
  CLI_CONTRACT,
  type CliContract,
  type ContractCommand,
  type ContractOption,
  type ContractPositional,
  RESOURCE_DISCOVERY,
  RESOURCE_KINDS,
  type ResourceKind,
} from '@rediacc/shared/cli-contract';
import { GLOBAL_OPTIONS, optionKinds, positionalKinds } from '@rediacc/shared/command-line';
import { childrenOf } from '@rediacc/shared/command-line/contract-index';
import { getConfigDir } from '@rediacc/shared/paths';
import { composeRef } from '@rediacc/shared/ref';
import { Command } from 'commander';
import { t } from '../i18n/index.js';
import { getEffectiveConfigName } from '../services/config/config-name.js';
import { writeStdout } from '../services/core/request-context.js';
import { ValidationError } from '../types/errors.js';
import { handleError } from '../utils/errors.js';

export const COMPLETE_COMMAND = '__complete';

export const COMPLETION_SHELLS = ['bash', 'zsh', 'fish', 'pwsh'] as const;
export type CompletionShell = (typeof COMPLETION_SHELLS)[number];

/** Kinds whose names live in the config file; the rest need a discovery command and get no names. */
export const CONFIG_KINDS: readonly ResourceKind[] = RESOURCE_KINDS.filter(
  (kind) => RESOURCE_DISCOVERY[kind].source === 'config'
);

// ── Static model ─────────────────────────────────────────────────────────

/**
 * One node of the command path tree, keyed `rdc`, `rdc repo`, `rdc repo fork`.
 * A value spec is a word list: a literal choice, `@<kind>` for the names of a
 * config kind, or `%file` for a path.
 */
export interface CompletionNode {
  key: string;
  children: string[];
  runnable: boolean;
  /** Long flags offered for completion. */
  flags: string[];
  /** Every spelling (long and short) of a value-taking flag, so the walker skips its value. */
  valueFlags: string[];
  /** Value spec per long flag, only for flags with one. */
  flagValues: [string, string[]][];
  /** Value spec per positional, in order. */
  positionals: string[][];
  variadic: boolean;
}

export interface CompletionModel {
  nodes: CompletionNode[];
  globalFlags: string[];
  globalValueFlags: string[];
}

const FILE_SPEC = '%file';
const SAFE_WORD = /^[A-Za-z0-9][A-Za-z0-9._:/+=,-]*$/;
const SAFE_FLAG = /^--?[A-Za-z0-9][A-Za-z0-9_-]*$/;

/** Every word lands unquoted-safe in four shell languages, so anything else is refused at print time. */
function checked(word: string, pattern: RegExp): string {
  if (!pattern.test(word)) {
    throw new ValidationError(t('commands.completion.errors.unsafeWord', { word }));
  }
  return word;
}

function kindWords(kinds: readonly ResourceKind[]): string[] {
  return kinds.filter((kind) => CONFIG_KINDS.includes(kind)).map((kind) => `@${kind}`);
}

function optionSpec(command: ContractCommand, option: ContractOption): string[] {
  const choices = (option.choices ?? []).map((c) => checked(c, SAFE_WORD));
  return [...choices, ...kindWords(optionKinds(command, option))];
}

function positionalSpec(positional: ContractPositional): string[] {
  if (positional.kind === 'file') return [FILE_SPEC];
  return kindWords(positionalKinds(positional));
}

function flagSpellings(option: ContractOption): string[] {
  const long = checked(`--${option.long}`, SAFE_FLAG);
  return option.short ? [long, checked(`-${option.short}`, SAFE_FLAG)] : [long];
}

function commandFields(command: ContractCommand | undefined) {
  if (!command) {
    return { runnable: false, flags: [], valueFlags: [], flagValues: [], positionals: [] };
  }
  const flags = command.options.map((o) => checked(`--${o.long}`, SAFE_FLAG));
  const valueFlags = command.options.filter((o) => o.valueTaking).flatMap(flagSpellings);
  const flagValues = command.options
    .filter((o) => o.valueTaking)
    .map((o): [string, string[]] => [`--${o.long}`, optionSpec(command, o)])
    .filter(([, spec]) => spec.length > 0);
  return {
    runnable: true,
    flags,
    valueFlags,
    flagValues,
    positionals: command.positionals.map(positionalSpec),
  };
}

/** Every path prefix of the contract, root first, in contract order. */
function pathPrefixes(contract: CliContract): string[][] {
  const seen = new Set<string>();
  const prefixes: string[][] = [[]];
  for (const command of contract.commands) {
    for (let n = 1; n <= command.path.length; n++) {
      const prefix = command.path.slice(0, n);
      const key = prefix.join(' ');
      if (seen.has(key)) continue;
      seen.add(key);
      prefixes.push(prefix);
    }
  }
  return prefixes;
}

/** The static words of every shell script, read from the contract through the command line core. */
export function buildCompletionModel(contract: CliContract): CompletionModel {
  const byKey = new Map(contract.commands.map((c) => [c.pathKey, c]));
  const nodes = pathPrefixes(contract).map((prefix): CompletionNode => {
    const command = prefix.length > 0 ? byKey.get(prefix.join(' ')) : undefined;
    return {
      key: ['rdc', ...prefix].join(' '),
      children: childrenOf(contract, prefix).map((child) => checked(child.word, SAFE_WORD)),
      variadic: command?.positionals.at(-1)?.variadic ?? false,
      ...commandFields(command),
    };
  });
  return {
    nodes,
    globalFlags: GLOBAL_OPTIONS.map((o) => `--${o.long}`),
    globalValueFlags: GLOBAL_OPTIONS.filter((o) => o.valueTaking).flatMap((o) =>
      o.short ? [`--${o.long}`, `-${o.short}`] : [`--${o.long}`]
    ),
  };
}

/** Lookup tables shared by the renderers: key to a word list. */
interface Tables {
  children: [string, string[]][];
  runnable: string[];
  flags: [string, string[]][];
  valueFlags: [string, string[]][];
  flagValues: [string, string[]][];
  /** `count variadic` per runnable command with positionals. */
  posInfo: [string, string[]][];
  positionals: [string, string[]][];
}

function tablesOf(model: CompletionModel): Tables {
  const nonEmpty = (rows: [string, string[]][]) => rows.filter(([, words]) => words.length > 0);
  const nodes = model.nodes;
  return {
    children: nonEmpty(nodes.map((n) => [n.key, n.children])),
    runnable: nodes.filter((n) => n.runnable).map((n) => n.key),
    flags: nonEmpty(nodes.map((n) => [n.key, n.flags])),
    valueFlags: nonEmpty(nodes.map((n) => [n.key, n.valueFlags])),
    flagValues: nodes.flatMap((n) =>
      n.flagValues.map(([flag, spec]): [string, string[]] => [`${n.key}|${flag}`, spec])
    ),
    posInfo: nodes
      .filter((n) => n.positionals.length > 0)
      .map((n) => [n.key, [String(n.positionals.length), n.variadic ? '1' : '0']]),
    positionals: nodes.flatMap((n) =>
      n.positionals
        .map((spec, i): [string, string[]] => [`${n.key}|${i}`, spec])
        .filter(([, spec]) => spec.length > 0)
    ),
  };
}

/**
 * A shell source literal: written raw, with `$~{` standing for `${` so a
 * shell parameter expansion is never read as a template placeholder.
 */
function shell(strings: TemplateStringsArray): string {
  return String.raw({ raw: strings.raw }).replaceAll('$~{', '${');
}

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
  local cur="$1" _rdc_p=rdc npos=0 cfg='' pending='' w _rdc_r=''
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

export function renderCompletionScript(shell: CompletionShell, contract: CliContract): string {
  return RENDERERS[shell](buildCompletionModel(contract));
}

function parseShell(value: string): CompletionShell {
  const shell = COMPLETION_SHELLS.find((s) => s === value);
  if (!shell) {
    throw new ValidationError(
      t('commands.completion.errors.unknownShell', {
        shell: value,
        shells: COMPLETION_SHELLS.join(', '),
      })
    );
  }
  return shell;
}

export function registerCompletionCommand(program: Command): void {
  program
    .command('completion')
    .summary(t('commands.completion.descriptionShort'))
    .description(t('commands.completion.description'))
    .argument('<shell>', t('commands.completion.shellArgument'))
    .action((shell: string) => {
      try {
        writeStdout(renderCompletionScript(parseShell(shell), CLI_CONTRACT));
      } catch (error) {
        handleError(error);
      }
    });
}

// ── __complete: names from the local config file ───────────────────────────

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function parseConfigKind(value: string): ResourceKind {
  const kind = CONFIG_KINDS.find((k) => k === value);
  if (!kind) {
    throw new ValidationError(
      t('commands.completion.errors.unknownKind', { kind: value, kinds: CONFIG_KINDS.join(', ') })
    );
  }
  return kind;
}

function readConfigFile(file: string): Record<string, unknown> {
  let text: string;
  try {
    text = readFileSync(file, 'utf-8');
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error;
    throw new ValidationError(t('commands.completion.errors.configMissing', { path: file }));
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    // The parser's message may quote the file's text, which can hold tokens: name only the file.
    throw new ValidationError(
      t('commands.completion.errors.configInvalid', { path: file, error: 'not valid JSON' })
    );
  }
  if (!isRecord(parsed)) {
    throw new ValidationError(
      t('commands.completion.errors.configInvalid', { path: file, error: typeof parsed })
    );
  }
  return parsed;
}

/** Every repository ref: the bare family name for the grand tag, `name:tag` for a fork. */
function repoRefs(families: Record<string, unknown>, file: string): string[] {
  return Object.entries(families).flatMap(([family, record]) => {
    if (!isRecord(record) || !isRecord(record.tags)) {
      throw new ValidationError(
        t('commands.completion.errors.configInvalid', { path: file, error: family })
      );
    }
    const grand = record.grand;
    return Object.keys(record.tags).map((tag) =>
      composeRef(family, tag === grand ? undefined : tag)
    );
  });
}

/** Names of one config-sourced kind in a parsed config file. */
export function resourceNames(
  config: Record<string, unknown>,
  kind: ResourceKind,
  file: string
): string[] {
  const source = RESOURCE_DISCOVERY[kind];
  if (source.source !== 'config') return [];
  const resources = isRecord(config.resources) ? config.resources : {};
  const family = resources[source.family];
  if (family === undefined) {
    // A remote config keeps its resources on the server; the local file is only a pointer.
    if (isRecord(config.remote)) {
      throw new ValidationError(t('commands.completion.errors.remoteConfig', { path: file }));
    }
    return [];
  }
  if (!isRecord(family)) {
    throw new ValidationError(
      t('commands.completion.errors.configInvalid', { path: file, error: source.family })
    );
  }
  return kind === 'repo' ? repoRefs(family, file) : Object.keys(family);
}

/** A config name is one file stem: no path separator and no leading dot (so no `..`), so the lookup stays in the config dir. */
const PLAIN_CONFIG_NAME = /^(?!\.)[^/\\\0]+$/;

/** The names `rdc __complete` prints: the config file is `<config dir>/<name>.json`. */
export function completeNames(options: { kind: string; config?: string }): string[] {
  const kind = parseConfigKind(options.kind);
  const name = options.config ?? getEffectiveConfigName();
  if (!PLAIN_CONFIG_NAME.test(name)) {
    throw new ValidationError(
      t('commands.completion.errors.configInvalid', {
        path: name,
        error: 'not a plain config name',
      })
    );
  }
  const file = join(getConfigDir(), `${name}.json`);
  return resourceNames(readConfigFile(file), kind, file);
}

/** True when this process was started as `rdc __complete ...`. */
export function isCompleteInvocation(argv: readonly string[]): boolean {
  return argv[2] === COMPLETE_COMMAND;
}

/** A program holding only `__complete`, so a name lookup never builds the full command tree. */
export function createCompleteProgram(): Command {
  const program = new Command('rdc');
  program
    .command(COMPLETE_COMMAND, { hidden: true })
    .summary(t('commands.completion.complete.descriptionShort'))
    .requiredOption('--kind <kind>', t('commands.completion.complete.kindOption'))
    .option('--config <name>', t('commands.completion.complete.configOption'))
    .action((options: { kind: string; config?: string }) => {
      try {
        const names = completeNames(options);
        writeStdout(names.map((name) => `${name}\n`).join(''));
      } catch (error) {
        handleError(error);
      }
    });
  return program;
}
