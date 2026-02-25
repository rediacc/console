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
$UserAgent = "Rediacc-Installer/1.0"
$InstallDir = "$env:LOCALAPPDATA\rediacc\bin"
$VersionsDir = "$env:LOCALAPPDATA\rediacc\versions"
$MaxVersions = 5

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

function Install-RDC {
    Write-Host "Setting up Rediacc CLI..."
    Write-Host ""

    $Arch = Get-Arch
    $BinaryName = "rdc-win-$Arch.exe"

    Write-Host "Detected: Windows ($Arch)"

    # Get latest version
    Write-Host "Fetching latest version..."
    try {
        $Headers = @{"User-Agent" = $UserAgent}
        $Latest = Invoke-RestMethod "$ReleasesUrl/cli/latest.json" -Headers $Headers
    }
    catch {
        throw "Failed to fetch version information: $_"
    }

    $Version = $Latest.version
    if (-not $Version) {
        throw "Could not determine latest version"
    }

    Write-Host "Latest version: v$Version"

    $DownloadUrl = "$ReleasesUrl/cli/v$Version/$BinaryName"
    $ChecksumUrl = "$DownloadUrl.sha256"

    # Create directories
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
    New-Item -ItemType Directory -Force -Path "$VersionsDir\$Version" | Out-Null

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

    # Install binary
    $VersionPath = "$VersionsDir\$Version\rdc.exe"
    Move-Item -Force $TempFile $VersionPath

    # Copy to install directory (symlinks require admin on Windows)
    Copy-Item -Force $VersionPath "$InstallDir\rdc.exe"

    # Cleanup old versions (keep last MaxVersions)
    $OldVersions = Get-ChildItem $VersionsDir -Directory -ErrorAction SilentlyContinue |
        Sort-Object CreationTime -Descending |
        Select-Object -Skip $MaxVersions

    foreach ($OldVersion in $OldVersions) {
        Remove-Item -Path $OldVersion.FullName -Recurse -Force -ErrorAction SilentlyContinue
    }

    # Success message
    Write-Host ""
    Write-ColorOutput "Rediacc CLI successfully installed!" -Color Green
    Write-Host ""
    Write-Host "  Version:  v$Version"
    Write-Host "  Location: $InstallDir\rdc.exe"
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

    Write-Host ""
    Write-ColorOutput "Installation complete!" -Color Green
}

# Run installation
Install-RDC
