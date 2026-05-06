# Rediacc CLI Installer for Windows
#
# Quick install (downloads and runs this script):
#   irm https://www.rediacc.com/install.ps1 | iex
#
# Safer alternative (download first, inspect, then run):
#   Invoke-WebRequest -Uri https://www.rediacc.com/install.ps1 -OutFile install.ps1
#   Get-Content install.ps1  # inspect the script
#   .\install.ps1

$ErrorActionPreference = "Stop"

# Configuration (can be overridden via environment variables)
$ReleasesUrl = if ($env:REDIACC_RELEASES_URL) { $env:REDIACC_RELEASES_URL } else { "https://releases.rediacc.com" }
$ServerUrl = if ($env:REDIACC_SERVER_URL) { $env:REDIACC_SERVER_URL } else { "" }
$UserAgent = "Rediacc-Installer/1.0"

# Install layout: single binary at ${InstallDir}\rdc.exe. rdc update
# replaces the binary in place; rollback keeps a single rdc.old.exe sibling.
# No per-version dirs (previous layout stored versions\<V>\rdc.exe with a
# "keep last 5" prune that was never surfaced to users and caused version
# dir / binary version divergence after each rdc update).
$InstallDir = "$env:LOCALAPPDATA\rediacc\bin"
$LegacyVersionsDir = "$env:LOCALAPPDATA\rediacc\versions"
$StagedUpdateDir = "$env:LOCALAPPDATA\rediacc\cache\staged-update"
$ConfigDir = "$env:APPDATA\rediacc"

# Channel resolution. Order:
#   1. REDIACC_CHANNEL env var (explicit caller intent - wins).
#   2. Existing server.json::updateChannel (the channel `rdc update` uses).
#   3. Default 'stable'.
# Reading server.json on a re-install avoids the trap where install.ps1 picks
# `stable` while `rdc update` reads server.json::updateChannel=edge and jumps
# the binary on the very next invocation. Both paths now agree by default.
$Channel = if ($env:REDIACC_CHANNEL) {
    $env:REDIACC_CHANNEL
} else {
    $serverJson = Join-Path $ConfigDir "server.json"
    $existing = if (Test-Path $serverJson) {
        try { (Get-Content $serverJson -Raw | ConvertFrom-Json).updateChannel } catch { $null }
    } else { $null }
    if ($existing) { $existing } else { "stable" }
}

function Write-ColorOutput {
    param(
        [string]$Message,
        [string]$Color = "White"
    )
    Write-Host $Message -ForegroundColor $Color
}

function Get-Arch {
    if ([Environment]::Is64BitOperatingSystem) {
        if ($env:PROCESSOR_ARCHITECTURE -eq "ARM64") {
            return "arm64"
        }
        return "x64"
    }
    throw "Unsupported architecture: 32-bit systems are not supported"
}

# Clean up artefacts from the pre-collapse layout and from any in-flight
# background update the previous install might have staged. Unconditional
# to guarantee a fresh install produces exactly the new layout. Mirrors
# install.sh's cleanup_legacy_state.
function Remove-LegacyState {
    if (Test-Path $LegacyVersionsDir) {
        Remove-Item -Recurse -Force -Path $LegacyVersionsDir -ErrorAction SilentlyContinue
        Write-Host "Removed legacy $LegacyVersionsDir"
    }
    if (Test-Path $StagedUpdateDir) {
        Remove-Item -Recurse -Force -Path $StagedUpdateDir -ErrorAction SilentlyContinue
    }
}

# Persist channel + server config so `rdc update` honors the channel this
# install came from. Mirrors install.sh::write_install_config. Writes when
# EITHER a specific server was requested OR the channel differs from default.
# Windows config dir is %APPDATA%\rediacc per @rediacc/shared/paths getConfigDir().
function Write-InstallConfig {
    $DefaultChannel = "stable"
    if ([string]::IsNullOrEmpty($ServerUrl) -and $Channel -eq $DefaultChannel) {
        return
    }

    if (-not (Test-Path $ConfigDir)) {
        New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null
    }

    # Discover E2E public key and update channel from server (only when we
    # have a server to ask).
    $E2eKey = ""
    if (-not [string]::IsNullOrEmpty($ServerUrl)) {
        try {
            $Headers = @{"User-Agent" = $UserAgent}
            $ServerInfo = Invoke-RestMethod -Uri "$ServerUrl/account/api/v1/.well-known/server-info" -Headers $Headers -UseBasicParsing
            if ($ServerInfo.e2e.keys -and $ServerInfo.e2e.keys[0].publicKeySpki) {
                $E2eKey = $ServerInfo.e2e.keys[0].publicKeySpki
            }
            # Auto-detect channel from server ONLY when still on the default
            # channel AND REDIACC_CHANNEL env var was not explicitly set.
            # A channel baked by the worker rewrite (e.g. edge on a preview
            # host) or set explicitly must NOT be overridden.
            if ([string]::IsNullOrEmpty($env:REDIACC_CHANNEL) -and $Channel -eq $DefaultChannel) {
                if ($ServerInfo.updateChannel) {
                    $Channel = $ServerInfo.updateChannel
                    $script:Channel = $Channel
                }
            }
        } catch {
            # server-info unreachable; proceed without e2e key / detected channel
        }
    }

    $AccountServer = if (-not [string]::IsNullOrEmpty($ServerUrl)) { $ServerUrl } else { "https://www.rediacc.com" }
    $ConfigHash = [ordered]@{
        accountServer = $AccountServer
        updateChannel = $Channel
    }
    if (-not [string]::IsNullOrEmpty($E2eKey)) {
        $ConfigHash["e2ePublicKey"] = $E2eKey
    }
    if ($ReleasesUrl -ne "https://releases.rediacc.com") {
        $ConfigHash["releasesUrl"] = $ReleasesUrl
    }
    $ConfigJson = $ConfigHash | ConvertTo-Json -Compress
    $ConfigPath = Join-Path $ConfigDir "server.json"
    $TempConfigPath = Join-Path $ConfigDir "server.json.tmp"
    # Atomic write: tmp + Move-Item so an interrupted install cannot leave a
    # half-written server.json. UTF-8 no-BOM matches what the CLI reads
    # (server-config.ts uses JSON.parse on utf-8); Windows PowerShell 5.1's
    # default Set-Content encoding is UTF-16 which the CLI would reject.
    $Utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($TempConfigPath, $ConfigJson, $Utf8NoBom)
    Move-Item -Path $TempConfigPath -Destination $ConfigPath -Force

    Write-Host ""
    if (-not [string]::IsNullOrEmpty($ServerUrl)) {
        $ServerHost = [Uri]::new($ServerUrl).Host
        Write-ColorOutput "Configured for: $ServerHost (channel: $Channel)" -Color Green
    } else {
        Write-ColorOutput "Channel pinned: $Channel" -Color Green
    }
}

function Install-RDC {
    Write-Host "Setting up Rediacc CLI..."
    Write-Host ""

    Remove-LegacyState

    $Arch = Get-Arch
    $BinaryName = "rdc-win-$Arch.exe"

    Write-Host "Detected: Windows ($Arch)"

    # Get latest version from channel
    Write-Host "Fetching latest version (channel: $Channel)..."
    try {
        $Headers = @{"User-Agent" = $UserAgent}
        $Latest = Invoke-RestMethod "$ReleasesUrl/cli/$Channel/latest.json" -Headers $Headers
    }
    catch {
        throw "Failed to fetch version information: $_"
    }

    $Version = $Latest.version
    if (-not $Version) {
        throw "Could not determine latest version"
    }

    Write-Host "Latest version: v$Version"

    # Release channels serve from the immutable versioned path. PR/preview
    # channels only exist under the channel path (see upload-to-r2.sh).
    if ($Channel -eq 'stable' -or $Channel -eq 'edge') {
        $DownloadUrl = "$ReleasesUrl/cli/v$Version/$BinaryName"
    } else {
        $DownloadUrl = "$ReleasesUrl/cli/$Channel/$BinaryName"
    }
    $ChecksumUrl = "$DownloadUrl.sha256"

    # Create install dir
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

    # Download binary
    Write-Host "Downloading rdc v$Version..."
    $TempFile = [System.IO.Path]::GetTempFileName()
    $Headers = @{"User-Agent" = $UserAgent}
    try {
        Invoke-WebRequest -Uri $DownloadUrl -OutFile $TempFile -UseBasicParsing -Headers $Headers
    }
    catch {
        Remove-Item -Path $TempFile -Force -ErrorAction SilentlyContinue
        throw "Failed to download binary from $DownloadUrl`: $_"
    }

    # Download and verify checksum
    Write-Host "Verifying checksum..."
    try {
        $ChecksumContent = (Invoke-WebRequest -Uri $ChecksumUrl -UseBasicParsing -Headers $Headers).Content
        $ExpectedSha = ($ChecksumContent -split '\s+')[0].ToLower()
    }
    catch {
        Remove-Item -Path $TempFile -Force -ErrorAction SilentlyContinue
        throw "Failed to download checksum from $ChecksumUrl`: $_"
    }

    $ActualSha = (Get-FileHash -Path $TempFile -Algorithm SHA256).Hash.ToLower()

    if ($ExpectedSha -ne $ActualSha) {
        Remove-Item -Path $TempFile -Force -ErrorAction SilentlyContinue
        throw "Checksum verification failed. Expected: $ExpectedSha, Got: $ActualSha"
    }

    Write-Host "Checksum verified."

    # Install binary atomically. Remove a stale .old sibling first so
    # `rdc update --rollback` cannot point at a pre-install binary.
    $BinaryPath = Join-Path $InstallDir "rdc.exe"
    $OldPath = Join-Path $InstallDir "rdc.old.exe"
    Remove-Item -Path $OldPath -Force -ErrorAction SilentlyContinue
    Move-Item -Force $TempFile $BinaryPath

    # Success message
    Write-Host ""
    Write-ColorOutput "Rediacc CLI successfully installed!" -Color Green
    Write-Host ""
    Write-Host "  Version:  v$Version"
    Write-Host "  Location: $BinaryPath"
    Write-Host ""
    Write-Host "  Next:   Run 'rdc --help' to get started"
    Write-Host "  Update: Run 'rdc update' to update to the latest version"

    # PATH check
    $UserPath = [Environment]::GetEnvironmentVariable("PATH", "User")
    if ($UserPath -notlike "*$InstallDir*") {
        Write-Host ""
        Write-ColorOutput "Note: $InstallDir is not in your PATH" -Color Yellow
        Write-Host ""
        Write-Host "  Add it by running:"
        Write-Host ""
        Write-Host "  `$env:PATH += `";$InstallDir`"; [Environment]::SetEnvironmentVariable('PATH', `$env:PATH, 'User')"
    }

    Write-InstallConfig

    Write-Host ""
    Write-ColorOutput "Installation complete!" -Color Green
}

# Run installation
Install-RDC
