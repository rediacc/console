# keys suite (agent/plans/PLAN-windows-lane.md D8 wave 1), ported from the spike's rdc-win-tests.ps1 and
# run-all.sh: a fresh config, machine add and scan-keys of the fleet worker, the stored host keys equal to
# what Linux ssh-keyscan reads (params.expectedHostKeys, scanned by the driver), and three negatives that
# must fail as NETWORK_ERROR (exit 6): an unreachable address, a closed port, and a TCP port that is not SSH.
# The config it leaves (params.config, the worker alone) is the one the guard, term and vscode suites use.

. (Join-Path $PSScriptRoot 'common.ps1')
$p = Initialize-RdcSuite 'keys'
$w = $p.worker
$net = (($w.ip -split '\.')[0..2]) -join '.'

# A config left by an earlier run goes first; its absence is not a finding, so this is no step.
$null = Invoke-RdcCli -Name 'config-delete' -Arguments @('config', 'delete', $p.config)

Test-RdcCli -Id 'config-init' -Arguments @('config', 'init', $p.config, '--ssh-key', $p.key)
Test-RdcCli -Id 'machine-add' -Arguments @('machine', 'add', $w.name, '--ip', $w.ip, '--user', $w.user)
Test-RdcCli -Id 'scan-keys' -Arguments @('machine', 'scan-keys', $w.name)

$got = @(Get-RdcKnownHosts $p.config $w.name)
$want = @($p.expectedHostKeys | Sort-Object -Unique)
$onlyLinux = @($want | Where-Object { $got -notcontains $_ })
$onlyWindows = @($got | Where-Object { $want -notcontains $_ })
Assert-RdcStep 'hostkeys-equal' ($got.Count -gt 0 -and $onlyLinux.Count -eq 0 -and $onlyWindows.Count -eq 0) `
    "windows config $($got.Count) key(s), linux ssh-keyscan $($want.Count); only-linux: $($onlyLinux -join ', '); only-windows: $($onlyWindows -join ', ')"

# The negatives: `machine add` records the machine and warns (exit 0), `machine scan-keys` fails with 6.
$negatives = @(
    @{ name = 'deadhost'; ip = "$net.199"; port = '22' },
    @{ name = 'closedport'; ip = $w.ip; port = '2' },
    @{ name = 'notssh'; ip = "$net.254"; port = '53' }
)
foreach ($n in $negatives) {
    Test-RdcCli -Id "add-$($n.name)" -Arguments @('machine', 'add', $n.name, '--ip', $n.ip, '--user', $w.user, '--port', $n.port)
    Test-RdcCli -Id "scan-$($n.name)" -Arguments @('machine', 'scan-keys', $n.name) -Expect 6
    $null = Invoke-RdcCli -Name "remove-$($n.name)" -Arguments @('machine', 'remove', $n.name, '--yes')
}

Complete-RdcSuite
