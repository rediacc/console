# dpapi suite (agent/plans/PLAN-windows-lane.md D8 wave 2). The rdc verb that writes secure storage is
# `rdc doctor`: its "Secret store" check (packages/cli/src/commands/doctor-secret-store.ts) stores, reads
# back and removes a throwaway secret through getSecureStorage(), which on Windows is DPAPI through
# powershell.exe (packages/cli/src/utils/secure-storage.ts). A row with status ok and a value starting
# with "dpapi" is the pass; doctor's own exit code reflects every other row too, so it is not judged.
# The check runs twice: in the SSH session, and in the desktop session through a /IT task. Plan Risks:
# an OpenSSH key logon may not reach the user's DPAPI master key, and a red ssh-session beside a green
# desktop-session is that finding, a CLI defect of its own.

. (Join-Path $PSScriptRoot 'common.ps1')
$p = Initialize-RdcSuite 'dpapi'

function Get-RdcSecretStoreRow([string]$Text) {
    $start = $Text.IndexOf('{')
    $end = $Text.LastIndexOf('}')
    if ($start -lt 0 -or $end -le $start) { return $null }
    try { $doc = $Text.Substring($start, $end - $start + 1) | ConvertFrom-Json } catch { return $null }
    foreach ($section in $doc.PSObject.Properties) {
        foreach ($check in @($section.Value)) {
            if ($check -and $check.PSObject.Properties['name'] -and $check.name -eq 'Secret store') { return $check }
        }
    }
    return $null
}

function Write-RdcSecretStoreStep([string]$Id, [string]$Text, [string]$Context) {
    $row = Get-RdcSecretStoreRow $Text
    if ($null -eq $row) {
        Assert-RdcStep $Id $false "$Context printed no Secret store row: $Text"
        return
    }
    $ok = ($row.status -eq 'ok') -and ([string]$row.value -like 'dpapi*')
    Assert-RdcStep $Id $ok "$Context Secret store row: status=$($row.status), value=$($row.value)"
}

$r = Invoke-RdcCli -Name 'doctor-ssh' -Arguments @('doctor', '--output', 'json')
Write-RdcSecretStoreStep 'ssh-session' $r.Out "doctor in the SSH session (exit $($r.Rc)); stderr: $($r.Err.Trim())"

$json = Join-Path $script:RdcWork 'desktop.json'
$exitFile = Join-Path $script:RdcWork 'desktop.exit'
$cmdFile = Join-Path $script:RdcWork 'desktop.cmd'
$lines = @(Get-RdcDesktopPreamble) + @(
    "node $($p.bundle) doctor --output json > $json 2> $json.err",
    "echo exit=%ERRORLEVEL% > $exitFile"
)
Set-Content -Path $cmdFile -Value $lines -Encoding ASCII
$d = Invoke-RdcDesktop -Name 'dpapi' -Command $cmdFile -ExitFile $exitFile -TimeoutS 180
if ($d.Rc -eq -1) {
    Assert-RdcStep 'desktop-session' $false $d.Text
} else {
    Write-RdcSecretStoreStep 'desktop-session' (Read-RdcFile $json) "doctor in the desktop session (exit $($d.Rc))"
}

Complete-RdcSuite
