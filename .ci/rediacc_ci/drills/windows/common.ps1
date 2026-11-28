# common.ps1: dot-sourced by every win:check suite (agent/plans/PLAN-windows-lane.md D7, D8).
#
# THE CONTRACT with the driver (.ci/rediacc_ci/drills/win_check.py). Every check prints one line
#   RDC-STEP {"id":"<suite>.<step>","rc":<int>,"expect":<int>|"nonzero","ok":<bool>,...}
# and a suite that ran to its end prints RDC-SUITE {"suite":"<suite>","steps":<n>}. The driver judges
# those lines and nothing else, so a check that prints no step line did not happen. A step that also
# asserts a pattern of the output carries "match"; a derived assertion (an equality, a parsed row) is a
# step with rc 0 or 1 against expect 0.
#
# THE RULES (findings lesson 8, Design D6). Windows PowerShell 5.1 turns a native program's stderr into
# error records, so every native call runs through cmd.exe with its stdout and stderr redirected to files
# under C:\rdc\work\<suite>, and its exit code comes from $LASTEXITCODE. No step pipes stdin into ssh.exe
# or reads its output through a pipe. Every address is a literal IPv4, except the guard suite's one hostname (see guard.ps1). The files stay ASCII, since 5.1
# reads a script without a BOM in the ANSI code page; a non-ASCII name is built from [char] codes.
#
# THE AGENT BOUNDARY. Every rdc call runs in a fresh cmd.exe that carries CLAUDECODE=1, an honest agent
# run. The guard suite also sets the overrides on that boundary, or on a nested cmd.exe below it.

$ErrorActionPreference = 'Continue'

$script:Rdc = $null
$script:RdcSuite = ''
$script:RdcSteps = 0
$script:RdcWork = ''
$script:RdcLast = $null

function Write-RdcLine([string]$Text) {
    [Console]::Out.WriteLine($Text)
    [Console]::Out.Flush()
}

# Read params.json (written by the driver), reset this suite's work folder and the process environment.
function Initialize-RdcSuite([string]$Name) {
    $script:RdcSuite = $Name
    $script:Rdc = Get-Content -Raw -Encoding UTF8 (Join-Path $PSScriptRoot 'params.json') | ConvertFrom-Json
    $script:RdcWork = Join-Path 'C:\rdc\work' $Name
    if (Test-Path $script:RdcWork) { Remove-Item -Recurse -Force $script:RdcWork }
    New-Item -ItemType Directory -Force $script:RdcWork | Out-Null
    $machinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = $machinePath + ';' + $userPath + ';' + $script:Rdc.renetDir
    $env:REDIACC_NO_PROVISION = '1'
    $env:PYTHONIOENCODING = 'utf-8'
    # The suite process itself is no agent and holds no override; each call's cmd.exe boundary decides.
    foreach ($var in 'CLAUDECODE', 'REDIACC_AGENT', 'REDIACC_ALLOW_GRAND_REPO', 'REDIACC_ALLOW_CLUSTER_OPS', 'REDIACC_CONFIG', 'REDIACC_SECRET_STORE') {
        Remove-Item "Env:$var" -ErrorAction SilentlyContinue
    }
    Write-RdcLine "win:check suite $Name, run $($script:Rdc.runId)"
    return $script:Rdc
}

# Printable ASCII only, whitespace folded, clipped: the step line must survive any console code page.
function ConvertTo-RdcAscii([string]$Text, [int]$Limit = 300) {
    if (-not $Text) { return '' }
    $sb = New-Object System.Text.StringBuilder
    foreach ($ch in $Text.ToCharArray()) {
        $code = [int]$ch
        if ($code -ge 32 -and $code -lt 127) { [void]$sb.Append($ch) }
        elseif ($code -eq 9 -or $code -eq 10 -or $code -eq 13) { [void]$sb.Append(' ') }
        else { [void]$sb.Append('?') }
    }
    $s = ($sb.ToString() -replace '\s+', ' ').Trim()
    if ($s.Length -gt $Limit) { $s = $s.Substring($s.Length - $Limit + 3); $s = '...' + $s }
    return $s
}

# One step line. $Expect is an exit code or 'nonzero'; $Match, when given, must be $true for the step to pass.
function Write-RdcStep {
    param(
        [Parameter(Mandatory = $true)][string]$Id,
        [int]$Rc,
        $Expect = 0,
        [string]$Detail = '',
        [int]$Ms = 0,
        $Match = $null
    )
    if ($Expect -is [string]) {
        if ($Expect -ne 'nonzero') { throw "Write-RdcStep ${Id}: expect '$Expect' is neither an exit code nor 'nonzero'" }
        $ok = ($Rc -ne 0)
    } else {
        $Expect = [int]$Expect
        $ok = ($Rc -eq $Expect)
    }
    $line = [ordered]@{ id = "$($script:RdcSuite).$Id"; rc = $Rc; expect = $Expect; ok = $ok; ms = $Ms; detail = (ConvertTo-RdcAscii $Detail) }
    if ($null -ne $Match) {
        $line['match'] = [bool]$Match
        if (-not $Match) { $line['ok'] = $false }
    }
    $script:RdcSteps++
    Write-RdcLine ('RDC-STEP ' + ($line | ConvertTo-Json -Compress))
}

# A derived assertion: rc 0 when $Condition holds, 1 otherwise, against expect 0.
function Assert-RdcStep([string]$Id, [bool]$Condition, [string]$Detail) {
    Write-RdcStep -Id $Id -Rc ([int](-not $Condition)) -Expect 0 -Detail $Detail
}

# The end line; the driver counts the step lines against it.
function Complete-RdcSuite {
    Write-RdcLine ('RDC-SUITE ' + ([ordered]@{ suite = $script:RdcSuite; steps = $script:RdcSteps } | ConvertTo-Json -Compress))
    exit 0
}

# Quote one argument for a cmd.exe command line that node parses with the C runtime's rules.
function ConvertTo-RdcCmdArg([string]$Arg) {
    if ($Arg -eq '') { return '""' }
    if ($Arg -match '[\s"&|<>^(),;=!*]') { return '"' + ($Arg -replace '"', '\"') + '"' }
    return $Arg
}

function Read-RdcFile([string]$Path) {
    if (Test-Path $Path) { return [IO.File]::ReadAllText($Path) }
    return ''
}

# Run "$Line > <name>.out 2> <name>.err" in a fresh cmd.exe; $Line may itself start a nested cmd.exe.
function Invoke-RdcNative {
    param([Parameter(Mandatory = $true)][string]$Name, [Parameter(Mandatory = $true)][string]$Line)
    $base = Join-Path $script:RdcWork $Name
    $sw = [Diagnostics.Stopwatch]::StartNew()
    & cmd.exe /d /s /c $Line
    $rc = $LASTEXITCODE
    $sw.Stop()
    $result = [pscustomobject]@{
        Rc  = $rc
        Out = (Read-RdcFile "$base.out")
        Err = (Read-RdcFile "$base.err")
        Ms  = [int]$sw.ElapsedMilliseconds
    }
    $script:RdcLast = $result
    return $result
}

function ConvertTo-RdcSetLine($Vars) {
    return (@($Vars.Keys | ForEach-Object { "set $_=$($Vars[$_])" }) -join '&& ')
}

# rdc under a cmd.exe boundary: $Boundary (default CLAUDECODE=1) is set on the boundary, $Inner on a nested
# cmd.exe below it. REDIACC_CONFIG names $Config.
function Invoke-RdcCli {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [string[]]$Arguments,
        [string]$Config = '',
        $Boundary = $null,
        $Inner = $null
    )
    if (-not $Config) { $Config = $script:Rdc.config }
    if ($null -eq $Boundary) { $Boundary = [ordered]@{ CLAUDECODE = '1' } }
    $base = Join-Path $script:RdcWork $Name
    $argLine = (@($Arguments | ForEach-Object { ConvertTo-RdcCmdArg $_ }) -join ' ')
    $node = "node $($script:Rdc.bundle) $argLine > $base.out 2> $base.err"
    $outer = "set REDIACC_CONFIG=$Config"
    if ($Boundary.Count) { $outer += '&& ' + (ConvertTo-RdcSetLine $Boundary) }
    if ($null -ne $Inner -and $Inner.Count) {
        $line = "$outer&& cmd /d /s /c `"$(ConvertTo-RdcSetLine $Inner)&& $node`""
    } else {
        $line = "$outer&& $node"
    }
    return (Invoke-RdcNative -Name $Name -Line $line)
}

# rdc as a step: its exit code against $Expect, and $Match (a regex) against stdout and stderr when given.
function Test-RdcCli {
    param(
        [Parameter(Mandatory = $true)][string]$Id,
        [string[]]$Arguments,
        $Expect = 0,
        [string]$Match = '',
        [string]$Config = '',
        $Boundary = $null,
        $Inner = $null
    )
    $r = Invoke-RdcCli -Name $Id -Arguments $Arguments -Config $Config -Boundary $Boundary -Inner $Inner
    $matched = $null
    if ($Match) { $matched = [bool](($r.Out + "`n" + $r.Err) -match $Match) }
    $tail = ($r.Err.Trim() + ' | ' + $r.Out.Trim())
    Write-RdcStep -Id $Id -Rc $r.Rc -Expect $Expect -Ms $r.Ms -Match $matched -Detail ("rdc $($Arguments -join ' '): $tail")
}

# The `<type> <key>` pairs a config stores for one machine (resources.machines.<name>.knownHosts).
function Get-RdcKnownHosts([string]$ConfigName, [string]$Machine) {
    $path = Join-Path $env:APPDATA ("rediacc\" + $ConfigName + '.json')
    if (-not (Test-Path $path)) { return @() }
    try { $cfg = Get-Content -Raw -Encoding UTF8 $path | ConvertFrom-Json } catch { return @() }
    $machines = $null
    if ($cfg.PSObject.Properties['resources'] -and $cfg.resources.PSObject.Properties['machines']) { $machines = $cfg.resources.machines }
    if ($null -eq $machines -or -not $machines.PSObject.Properties[$Machine]) { return @() }
    $entry = $machines.PSObject.Properties[$Machine].Value
    if (-not $entry.PSObject.Properties['knownHosts']) { return @() }
    $keys = @()
    foreach ($line in ([string]$entry.knownHosts -split "`n")) {
        $parts = @($line.Trim() -split '\s+' | Where-Object { $_ })
        if ($parts.Count -ge 3 -and $parts[1] -match '^(ssh-|ecdsa-|sk-)') { $keys += "$($parts[1]) $($parts[2])" }
        elseif ($parts.Count -eq 2 -and $parts[0] -match '^(ssh-|ecdsa-|sk-)') { $keys += "$($parts[0]) $($parts[1])" }
    }
    return @($keys | Sort-Object -Unique)
}

# The lines of a .cmd that runs in the desktop session with the stock PATH read from the registry, not the
# SSH session's environment. The caller appends its own command lines.
function Get-RdcDesktopPreamble {
    return @(
        '@echo off',
        'for /f "tokens=2,*" %%a in (''reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path ^| find "Path"'') do set MPATH=%%b',
        'for /f "tokens=2,*" %%a in (''reg query "HKCU\Environment" /v Path 2^>nul ^| find "Path"'') do set UPATH=%%b',
        ('call set PATH=%MPATH%;%UPATH%;' + $script:Rdc.renetDir),
        'set REDIACC_NO_PROVISION=1',
        'set CLAUDECODE=1'
    )
}

# Run $Command in the logged-on desktop session through a one-shot /IT scheduled task (a GUI program started
# over SSH lands in session 0), and wait for its "exit=<code>" line in $ExitFile. Rc is -1 when the line
# never came: the desktop session is not logged on (permanent autologon is a bake step) or the task failed.
function Invoke-RdcDesktop {
    param([string]$Name, [string]$Command, [string]$ExitFile, [int]$TimeoutS = 180)
    Remove-Item $ExitFile -ErrorAction SilentlyContinue
    $task = "rdc-wincheck-$Name"
    & schtasks.exe /create /f /tn $task /sc once /st 23:59 /it /ru $env:USERNAME /tr $Command | Out-Null
    if ($LASTEXITCODE -ne 0) { return [pscustomobject]@{ Rc = -1; Text = "schtasks /create exited $LASTEXITCODE" } }
    & schtasks.exe /run /tn $task | Out-Null
    $deadline = (Get-Date).AddSeconds($TimeoutS)
    $text = ''
    while ((Get-Date) -lt $deadline) {
        $text = Read-RdcFile $ExitFile
        if ($text -match 'exit=(-?\d+)') { break }
        Start-Sleep -Seconds 2
    }
    & schtasks.exe /delete /f /tn $task | Out-Null
    if ($text -match 'exit=(-?\d+)') { return [pscustomobject]@{ Rc = [int]$Matches[1]; Text = $text } }
    return [pscustomobject]@{ Rc = -1; Text = "no exit= line in $ExitFile within $TimeoutS s; is the desktop session logged on?" }
}
