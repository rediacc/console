# term suite (agent/plans/PLAN-windows-lane.md D8 wave 1), ported from the spike's win-term-sync-guard.ps1:
# inline `term connect -c` to the fleet worker (an ops VM, so exempt from the machine guard), and with
# --target hostinger to the hostinger fork under params.remoteConfig. The remote shell must evaluate the
# command: the output carries RDC-TERM-42, which the literal command text does not.

. (Join-Path $PSScriptRoot 'common.ps1')
$p = Initialize-RdcSuite 'term'
$probe = 'echo RDC-TERM-$((6*7))'

Test-RdcCli -Id 'fleet' -Arguments @('term', 'connect', $p.worker.name, '-c', $probe) -Match 'RDC-TERM-42'

if ($p.fork) {
    Test-RdcCli -Id 'fork' -Config $p.remoteConfig -Arguments @('term', 'connect', $p.fork, '-c', $probe) -Match 'RDC-TERM-42'
}

Complete-RdcSuite
