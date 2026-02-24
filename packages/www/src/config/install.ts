import { SITE_URL } from './constants';

export type Platform = 'linux' | 'macos' | 'windows';

export type InstallMethod =
  | 'quick'
  | 'binary'
  | 'docker'
  | 'apt'
  | 'dnf'
  | 'apk'
  | 'pacman'
  | 'homebrew';

export const PLATFORMS: {
  key: Platform;
  iconId: 'linux' | 'apple' | 'windows';
  labelKey: string;
}[] = [
  { key: 'linux', iconId: 'linux', labelKey: 'hero.install.tabs.linux' },
  { key: 'macos', iconId: 'apple', labelKey: 'hero.install.tabs.macos' },
  { key: 'windows', iconId: 'windows', labelKey: 'hero.install.tabs.windows' },
];

export const QUICK_INSTALL_COMMANDS: Record<Platform, string> = {
  linux: `curl -fsSL ${SITE_URL}/install.sh | bash`,
  macos: 'brew install rediacc/tap/rediacc-cli',
  windows: `irm ${SITE_URL}/install.ps1 | iex`,
};

export const QUICK_INSTALL_UNIX = `# Linux / macOS\ncurl -fsSL ${SITE_URL}/install.sh | bash`;
export const QUICK_INSTALL_WIN = `# Windows (PowerShell)\nirm ${SITE_URL}/install.ps1 | iex`;

export const BINARY_COMMANDS: Record<Platform, string> = {
  linux: `# Linux x64
curl -fsSL https://releases.rediacc.com/cli/latest/rdc-linux-x64 -o rdc
chmod +x rdc && sudo mv rdc /usr/local/bin/

# Linux ARM64
curl -fsSL https://releases.rediacc.com/cli/latest/rdc-linux-arm64 -o rdc
chmod +x rdc && sudo mv rdc /usr/local/bin/`,
  macos: `# macOS (Apple Silicon)
curl -fsSL https://releases.rediacc.com/cli/latest/rdc-mac-arm64 -o rdc
chmod +x rdc && sudo mv rdc /usr/local/bin/

# macOS (Intel)
curl -fsSL https://releases.rediacc.com/cli/latest/rdc-mac-x64 -o rdc
chmod +x rdc && sudo mv rdc /usr/local/bin/`,
  windows: `# Windows x64 (PowerShell) - installs to standard location
$installDir = "$env:LOCALAPPDATA\\rediacc\\bin"; New-Item -ItemType Directory -Force -Path $installDir | Out-Null
Invoke-WebRequest -Uri https://releases.rediacc.com/cli/latest/rdc-win-x64.exe -OutFile "$installDir\\rdc.exe"
# Add to PATH: [Environment]::SetEnvironmentVariable("PATH", $env:PATH + ";$installDir", "User")

# Windows ARM64 (PowerShell) - installs to standard location
$installDir = "$env:LOCALAPPDATA\\rediacc\\bin"; New-Item -ItemType Directory -Force -Path $installDir | Out-Null
Invoke-WebRequest -Uri https://releases.rediacc.com/cli/latest/rdc-win-arm64.exe -OutFile "$installDir\\rdc.exe"
# Add to PATH: [Environment]::SetEnvironmentVariable("PATH", $env:PATH + ";$installDir", "User")`,
};

export const DOCKER_COMMANDS = `# Pull the image
docker pull ghcr.io/rediacc/elite/cli:latest

# Run a command
docker run --rm ghcr.io/rediacc/elite/cli:latest --version

# Create an alias for convenience
alias rdc='docker run --rm -it -v $(pwd):/workspace ghcr.io/rediacc/elite/cli:latest'`;

export const APT_COMMANDS = `curl -fsSL ${SITE_URL}/apt/gpg.key | sudo gpg --dearmor -o /usr/share/keyrings/rediacc.gpg
echo "deb [signed-by=/usr/share/keyrings/rediacc.gpg] ${SITE_URL}/apt stable main" | sudo tee /etc/apt/sources.list.d/rediacc.list
sudo apt-get update && sudo apt-get install rediacc-cli`;

export const DNF_COMMANDS = `sudo curl -fsSL ${SITE_URL}/rpm/rediacc.repo -o /etc/yum.repos.d/rediacc.repo
sudo dnf install rediacc-cli`;

export const APK_COMMANDS = `# Add the repository
echo "${SITE_URL}/apk/x86_64" | sudo tee -a /etc/apk/repositories

# Install (unsigned repo — use --allow-untrusted)
sudo apk update
sudo apk add --allow-untrusted rediacc-cli`;

export const PACMAN_COMMANDS = `# Add the repository to /etc/pacman.conf
echo "[rediacc]
SigLevel = Optional TrustAll
Server = ${SITE_URL}/archlinux/\\$arch" | sudo tee -a /etc/pacman.conf

# Install
sudo pacman -Sy rediacc-cli`;

export const HOMEBREW_COMMAND = 'brew install rediacc/tap/rediacc-cli';

export interface MethodMeta {
  id: InstallMethod;
  featured: boolean;
  platforms: Platform[];
  anchor: string;
}

export const METHOD_META: MethodMeta[] = [
  { id: 'quick', featured: true, platforms: ['linux', 'macos', 'windows'], anchor: 'quick' },
  { id: 'binary', featured: false, platforms: ['linux', 'macos', 'windows'], anchor: 'binary' },
  { id: 'docker', featured: false, platforms: ['linux', 'macos', 'windows'], anchor: 'docker' },
  { id: 'apt', featured: false, platforms: ['linux'], anchor: 'apt' },
  { id: 'dnf', featured: false, platforms: ['linux'], anchor: 'dnf' },
  { id: 'apk', featured: false, platforms: ['linux'], anchor: 'apk' },
  { id: 'pacman', featured: false, platforms: ['linux'], anchor: 'pacman' },
  { id: 'homebrew', featured: false, platforms: ['linux', 'macos'], anchor: 'homebrew' },
];

export function detectPlatform(): Platform {
  if (typeof window === 'undefined') return 'linux';
  const ua = navigator.userAgent.toLowerCase();
  if (ua.includes('win')) return 'windows';
  if (ua.includes('mac')) return 'macos';
  return 'linux';
}
