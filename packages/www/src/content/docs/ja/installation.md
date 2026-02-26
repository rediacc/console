---
title: "インストール"
description: "Linux、macOS、またはWindowsにRediacc CLIをインストールする。"
category: "Guides"
order: 1
language: ja
sourceHash: "2cb00a8aeec6988c"
---

# インストール

ワークステーションに`rdc` CLIをインストールします。手動でインストールする必要があるのはこのツールだけです — その他はリモートマシンのセットアップ時にすべて自動的に処理されます。

## LinuxとmacOS

インストールスクリプトを実行します：

```bash
curl -fsSL https://get.rediacc.com | sh
```

これにより`rdc`バイナリが`$HOME/.local/bin/`にダウンロードされます。このディレクトリがPATHに含まれていることを確認してください：

```bash
export PATH="$HOME/.local/bin:$PATH"
```

この行をシェルプロファイル（`~/.bashrc`、`~/.zshrc`など）に追加して、永続的に設定します。

## Windows

PowerShellでインストールスクリプトを実行します：

```powershell
irm https://www.rediacc.com/install.ps1 | iex
```

これにより、`rdc.exe`バイナリが`%LOCALAPPDATA%\rediacc\bin\`にダウンロードされます。このディレクトリがPATHに含まれていることを確認してください。インストーラーは、まだ含まれていない場合に追加するよう案内します。

## Alpine Linux (APK)

```bash
# Add the repository
echo "https://www.rediacc.com/apk/x86_64" | sudo tee -a /etc/apk/repositories

# Install
sudo apk update
sudo apk add --allow-untrusted rediacc-cli
```

注: `gcompat` パッケージ（glibc 互換レイヤー）は依存関係として自動的にインストールされます。

## Arch Linux (Pacman)

```bash
# Add the repository to /etc/pacman.conf
echo "[rediacc]
SigLevel = Optional TrustAll
Server = https://www.rediacc.com/archlinux/\$arch" | sudo tee -a /etc/pacman.conf

# Install
sudo pacman -Sy rediacc-cli
```

## インストールの確認

```bash
rdc --version
```

インストールされたバージョン番号が表示されるはずです。

## アップデート

`rdc`を最新バージョンに更新するには：

```bash
rdc update
```

インストールせずにアップデートを確認するには：

```bash
rdc update --check-only
```

アップデート後に以前のバージョンに戻すには：

```bash
rdc update rollback
```

### Remote Binary Updates

When you run commands against a remote machine, the CLI automatically provisions the matching `renet` binary. If the binary is updated, the route server (`rediacc-router`) is restarted automatically so it picks up the new version.

The restart is transparent and causes **no downtime**:

- The route server restarts in ~1–2 seconds.
- During that window, Traefik continues serving traffic using its last known routing configuration. No routes are dropped.
- Traefik picks up the new configuration on its next poll cycle (within 5 seconds).
- **Existing client connections (HTTP, TCP, UDP) are not affected.** The route server is a configuration provider — it is not in the data path. Traefik handles all traffic directly.
- Your application containers are not touched — only the system-level route server process is restarted.

To skip the automatic restart, pass `--skip-router-restart` to any command, or set the `RDC_SKIP_ROUTER_RESTART=1` environment variable.
