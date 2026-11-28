# vscode suite (agent/plans/PLAN-windows-lane.md D8 wave 2), ported from the spike's run-all.sh and
# vsc-desktop.cmd: `rdc vscode check` in the SSH session, then `rdc vscode connect <worker>` in the
# desktop session through vscode.cmd and a /IT task (a GUI program started over SSH lands in session 0).
# The verdict is the exit= line vscode.cmd writes; the driver keeps a screenshot of the VM as evidence
# only, so the suite leaves the window open for it, and the next run closes any VS Code left behind.

. (Join-Path $PSScriptRoot 'common.ps1')
$p = Initialize-RdcSuite 'vscode'

Test-RdcCli -Id 'check' -Arguments @('vscode', 'check')

Get-Process Code -ErrorAction SilentlyContinue | Stop-Process -Force
$exitFile = Join-Path $script:RdcWork 'connect.exit'
$command = (Join-Path $PSScriptRoot 'vscode.cmd') + " $($p.worker.name) $($p.config) $exitFile"
$d = Invoke-RdcDesktop -Name 'vscode' -Command $command -ExitFile $exitFile -TimeoutS 180
$log = Read-RdcFile "$exitFile.log"
Write-RdcStep -Id 'connect-desktop' -Rc $d.Rc -Expect 0 -Detail ("vscode connect $($p.worker.name): " + $log.Trim() + ' | ' + $d.Text.Trim())

if ($d.Rc -eq 0) { Start-Sleep -Seconds 20 }
Complete-RdcSuite
