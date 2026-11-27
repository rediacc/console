# guard suite (agent/plans/PLAN-windows-lane.md D8 wave 1), ported from the spike's win-term-sync-guard.ps1:
# the agent guard's Windows path, where the CLI verifies an override by reading the ancestors' environment
# blocks through `renet process-ancestry`. The target `guardprobe` is the hostname params.guardHost, which
# the bake's hosts file points at the fleet worker: a hostname is never exempt as an ops VM, so the full
# guard applies, while the box behind it is the disposable fleet VM.
#   refused-without-override          CLAUDECODE=1 on the boundary, no override: exit 2, the guard's message
#   allowed-with-override-on-boundary the override set on the boundary itself: exit 0
#   refused-override-below-boundary   the override set on a nested cmd.exe below the boundary: exit 2
#   process-ancestry                  renet reads CLAUDECODE and the override from the boundary's block

. (Join-Path $PSScriptRoot 'common.ps1')
$p = Initialize-RdcSuite 'guard'
$w = $p.worker

$addresses = @()
try { $addresses = @([System.Net.Dns]::GetHostAddresses($p.guardHost) | ForEach-Object { $_.IPAddressToString }) } catch { $addresses = @() }
Assert-RdcStep 'hosts-entry' ($addresses -contains $w.ip) "$($p.guardHost) resolves to [$($addresses -join ', ')], want $($w.ip)"

Test-RdcCli -Id 'machine-add' -Arguments @('machine', 'add', 'guardprobe', '--ip', $p.guardHost, '--user', $w.user)

$probe = @('term', 'connect', 'guardprobe', '-c', 'hostname')
$agent = [ordered]@{ CLAUDECODE = '1' }
$overridden = [ordered]@{ CLAUDECODE = '1'; REDIACC_ALLOW_GRAND_REPO = '*'; REDIACC_ALLOW_CLUSTER_OPS = '*' }
$refusal = [regex]::Escape('Direct machine access to "guardprobe"')

Test-RdcCli -Id 'refused-without-override' -Arguments $probe -Boundary $agent -Expect 2 -Match $refusal
Test-RdcCli -Id 'allowed-with-override-on-boundary' -Arguments $probe -Boundary $overridden -Expect 0
Test-RdcCli -Id 'refused-override-below-boundary' -Arguments $probe -Boundary $agent -Inner ([ordered]@{ REDIACC_ALLOW_GRAND_REPO = '*' }) -Expect 2 -Match $refusal

$base = Join-Path $script:RdcWork 'process-ancestry'
$r = Invoke-RdcNative -Name 'process-ancestry' -Line "set CLAUDECODE=1&& set REDIACC_ALLOW_GRAND_REPO=*&& renet process-ancestry --keys CLAUDECODE,REDIACC_ALLOW_GRAND_REPO > $base.out 2> $base.err"
$seen = $false
try {
    foreach ($a in @(($r.Out | ConvertFrom-Json).ancestors)) {
        if ($a.env -and $a.env.PSObject.Properties['CLAUDECODE'] -and $a.env.CLAUDECODE -eq '1' -and
            $a.env.PSObject.Properties['REDIACC_ALLOW_GRAND_REPO'] -and $a.env.REDIACC_ALLOW_GRAND_REPO -eq '*') { $seen = $true }
    }
} catch { $seen = $false }
Write-RdcStep -Id 'process-ancestry' -Rc $r.Rc -Expect 0 -Ms $r.Ms -Match $seen -Detail ("renet process-ancestry: " + $r.Err.Trim() + ' | ' + $r.Out.Trim())

$null = Invoke-RdcCli -Name 'remove-guardprobe' -Arguments @('machine', 'remove', 'guardprobe', '--yes')
Complete-RdcSuite
