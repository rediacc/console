# run.ps1 -- the Windows entry point. It runs ./run.sh inside WSL and gets out of the way.
#
# WHY WSL AND NOT A CONTAINER. Two designs were drafted for this launcher: a
# `docker run` shim and this one. The driver contract picked the WSL launcher
# (docs/ci-overhaul/08-driver-contract.md section 2, "run.ps1 design"), and the
# reason is that this repository's toolchain is already provisioned INSIDE WSL by
# .ci/bootstrap.sh and ./run.sh setup. A docker-run launcher would need its own
# image, its own bind mounts and its own answer for the docker-group re-exec that
# .ci/lib/local-common.sh performs -- a second, differently-broken environment to
# keep in step with the first. This launcher has no environment of its own at all.
#
# WHY NOT A ONE-LINER. `wsl.exe ./run.sh` alone is wrong in three ways that each
# present as something other than "the launcher is wrong":
#
#   1. WORKING DIRECTORY. Without `--cd` the command runs in the WSL user's home,
#      so `./run.sh` is not found and the error names the script, not the cwd.
#   2. THE UNC CASE. When the checkout lives in the WSL filesystem, Explorer and
#      PowerShell see it as \\wsl.localhost\<distro>\home\... and `--cd` on that
#      UNC path does not resolve to the Linux path it denotes. It is translated
#      back below, which also tells us WHICH distro holds the checkout.
#   3. THE EXIT CODE. PowerShell does not propagate a native command's exit code
#      by itself, so a failed gate run would return success to whatever called
#      this file -- the exact class of defect the CI overhaul exists to remove.

$ErrorActionPreference = 'Stop'

# THE OTHER HALF OF POINT 3, and it only bites on PowerShell 7.4 and later. There
# `$PSNativeCommandUseErrorActionPreference` defaults to $true, so a native command
# exiting non-zero under `ErrorActionPreference = 'Stop'` raises a TERMINATING error:
# the `exit $LASTEXITCODE` at the bottom is never reached and every distinct failure
# collapses to 1. A gate run that fails with 2 (an unusable devbox refusing to
# degrade) would arrive as 1, which is a different verdict. Turned off explicitly and
# only around the native call; the preference variable does not exist on 5.1, and
# assigning it there is harmless.
$PSNativeCommandUseErrorActionPreference = $false

if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    [Console]::Error.WriteLine('run.ps1: wsl.exe was not found. This repository builds and tests inside WSL; install it with `wsl --install`.')
    exit 1
}

# The distro is only pinned when the UNC path names one. On a checkout under the
# Windows filesystem we deliberately take the user's default distro rather than
# guessing: a wrong `-d` is a confusing failure, an absent one is the documented
# default.
$distro = $null
$target = $PSScriptRoot

if ($target -match '^\\\\wsl(?:\$|\.localhost)\\([^\\]+)\\(.*)$') {
    $distro = $Matches[1]
    $target = '/' + ($Matches[2] -replace '\\', '/')
}

$wslArgs = @()
if ($distro) { $wslArgs += @('-d', $distro) }
$wslArgs += @('--cd', $target, '--', './run.sh')
$wslArgs += $args

& wsl.exe @wslArgs

# `exit $LASTEXITCODE` and not `exit`. See point 3 in the header: this line is
# the whole reason the launcher is a file rather than an alias.
exit $LASTEXITCODE
