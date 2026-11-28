# sync suite (agent/plans/PLAN-windows-lane.md D8 wave 1), ported from the spike's win-term-sync-guard.ps1:
# `rdc tools install rsync` (the pinned MSYS2 rsync, findings P1), then a repo sync round trip against the
# hostinger fork (params.fork under params.remoteConfig, REDIACC_NO_PROVISION=1) with a folder name that
# holds a space and a file name that is not ASCII, byte-identical by SHA-256 both ways. It writes only
# under the fork's params.remoteDir and removes it, and the removal is a step of its own.

. (Join-Path $PSScriptRoot 'common.ps1')
$p = Initialize-RdcSuite 'sync'
$repo = $p.fork
$cfg = $p.remoteConfig
$dir = $p.remoteDir

Test-RdcCli -Id 'tools-install-rsync' -Arguments @('tools', 'install', 'rsync')

$up = Join-Path $script:RdcWork 'up'
$down = Join-Path $script:RdcWork 'down'
$spaced = Join-Path $up 'dir with space'
New-Item -ItemType Directory -Force $spaced, $down | Out-Null
$unicode = 'n' + [char]0x00FC + 'n' + [char]0x00EF + '-' + [char]0x65E5 + '.txt'
[IO.File]::WriteAllText((Join-Path $up 'probe.txt'), "win:check $($p.runId)`n")
[IO.File]::WriteAllText((Join-Path $spaced $unicode), "x $([guid]::NewGuid())`n")
[IO.File]::WriteAllBytes((Join-Path $up 'bytes.bin'), [byte[]](0..255))

Test-RdcCli -Id 'upload' -Config $cfg -Arguments @('repo', 'sync', 'upload', $repo, '--local', $up, '--remote', $dir)
Test-RdcCli -Id 'download' -Config $cfg -Arguments @('repo', 'sync', 'download', $repo, '--remote', $dir, '--local', $down)

function Get-RdcTreeHashes([string]$Root) {
    return @(Get-ChildItem -Recurse -File $Root | ForEach-Object {
        $_.FullName.Substring($Root.Length) + '|' + (Get-FileHash -Algorithm SHA256 $_.FullName).Hash
    } | Sort-Object)
}
$a = Get-RdcTreeHashes $up
$b = Get-RdcTreeHashes $down
$same = ($a.Count -eq 3) -and (($a -join "`n") -eq ($b -join "`n"))
Assert-RdcStep 'roundtrip-identical' $same "up $($a.Count) file(s), down $($b.Count) file(s); up: $($a -join '; '); down: $($b -join '; ')"

Test-RdcCli -Id 'cleanup' -Config $cfg -Arguments @('term', 'connect', $repo, '-c', "rm -rf $dir; test -e $dir || echo RDC-GONE") -Match 'RDC-GONE'

Complete-RdcSuite
