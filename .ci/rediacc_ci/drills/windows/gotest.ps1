# gotest suite (agent/plans/PLAN-windows-lane.md D8 revised, WL27): the renet packages whose tests only mean
# something on Windows, cross-compiled by the driver with `GOOS=windows go test -c` and staged under
# params.gotestDir as <name>.test.exe. The in-process ssh transport and errno_windows.go (WSAE* codes) compile
# and run only there. One step per binary, named after the binary: rc 0 against expect 0, and the output must
# carry a "--- PASS" line and no "--- FAIL" line, so a binary that ran no test cannot pass.

. (Join-Path $PSScriptRoot 'common.ps1')
$p = Initialize-RdcSuite 'gotest'

$binaries = @()
if (Test-Path $p.gotestDir) { $binaries = @(Get-ChildItem -Path $p.gotestDir -Filter '*.test.exe' | Sort-Object Name) }
Assert-RdcStep 'binaries' ($binaries.Count -gt 0) "$($binaries.Count) test binary(ies) in $($p.gotestDir)"

foreach ($bin in $binaries) {
    $name = $bin.Name -replace '\.test\.exe$', ''
    $base = Join-Path $script:RdcWork $name
    $r = Invoke-RdcNative -Name $name -Line "cd /d $($p.gotestDir)&& $($bin.FullName) -test.v -test.count=1 -test.timeout=300s > $base.out 2> $base.err"
    $passed = ($r.Out -match '--- PASS') -and -not ($r.Out -match '--- FAIL')
    $tail = ($r.Err.Trim() + ' | ' + $r.Out.Trim())
    Write-RdcStep -Id $name -Rc $r.Rc -Expect 0 -Ms $r.Ms -Match $passed -Detail "$($bin.Name): $tail"
}
Complete-RdcSuite
