---
title: "インストール"
description: "Linux、macOS、またはWindowsにRediacc CLIをインストールします。"
category: "Guides"
order: 1
language: ja
sourceHash: "f67060ce45e1dc96"
sourceCommit: "58fce41a73c6abc64260fe5e71afd23d17f56cde"
---

# インストール

ワークステーションに `rdc` CLIをインストールします。手動でインストールが必要なツールはこれだけです -- リモートマシンのセットアップ時に、それ以外はすべて自動的に処理されます。

## クイックインストール

### LinuxとmacOS

```bash
curl -fsSL https://www.rediacc.com/install.sh | bash
```

このコマンドは `rdc` バイナリを `$HOME/.local/bin/` にダウンロードします。このディレクトリがPATHに含まれていることを確認してください:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

永続化するには、この行をシェルプロファイル (`~/.bashrc`、`~/.zshrc` など) に追加してください。

### Windows

PowerShellで実行:

```powershell
irm https://www.rediacc.com/install.ps1 | iex
```

このコマンドは `rdc.exe` を `%LOCALAPPDATA%\rediacc\bin\` にダウンロードします。必要に応じて、インストーラーがPATHへの追加を案内します。

## パッケージマネージャー

### APT (Debian / Ubuntu)

```bash
curl -fsSL https://releases.rediacc.com/apt/stable/gpg.key | sudo gpg --dearmor -o /usr/share/keyrings/rediacc.gpg
echo "deb [signed-by=/usr/share/keyrings/rediacc.gpg] https://releases.rediacc.com/apt/stable stable main" | sudo tee /etc/apt/sources.list.d/rediacc.list
sudo apt-get update && sudo apt-get install rediacc-cli
```

### DNF (Fedora / RHEL)

```bash
sudo curl -fsSL https://releases.rediacc.com/rpm/stable/rediacc.repo -o /etc/yum.repos.d/rediacc.repo
sudo dnf install rediacc-cli
```

### APK (Alpine Linux)

```bash
echo "https://releases.rediacc.com/apk/stable" | sudo tee -a /etc/apk/repositories
sudo apk update
sudo apk add --allow-untrusted rediacc-cli
```

注意: `gcompat` パッケージ (glibc互換レイヤー) は依存関係として自動的にインストールされます。

### Pacman (Arch Linux)

```bash
echo "[rediacc]
SigLevel = Optional TrustAll
Server = https://releases.rediacc.com/archlinux/stable/\$arch" | sudo tee -a /etc/pacman.conf

sudo pacman -Sy rediacc-cli
```

## Docker

CLIをコンテナとしてプルして実行:

```bash
docker pull ghcr.io/rediacc/elite/cli:stable

docker run --rm ghcr.io/rediacc/elite/cli:stable --version
```

便利なエイリアスを作成:

```bash
alias rdc='docker run --rm -it -v $(pwd):/workspace ghcr.io/rediacc/elite/cli:stable'
```

利用可能なDockerタグ:

| タグ | 説明 |
|------|------|
| `:stable` | 最新の安定版リリース (推奨) |
| `:edge` | 最新のエッジリリース |
| `:0.8.4` | 固定バージョン (不変) |
| `:latest` | `:stable` のエイリアス |

## インストールの確認

```bash
rdc --version
```

## アップデート

最新バージョンに更新:

```bash
rdc update
```

インストールせずにアップデートを確認:

```bash
rdc update --check-only
```

現在のアップデート状況を表示:

```bash
rdc update --status
```

前のバージョンにロールバック:

```bash
rdc update --rollback
```

## リリースチャンネル

Rediaccはチャンネルベースのリリースシステムを使用しています。チャンネルは、CLIの更新、パッケージマネージャーのインストール、Dockerプルで受け取るバージョンを決定します。

| チャンネル | 説明 | 更新タイミング |
|------------|------|----------------|
| `stable` | 本番環境向けリリース | 7日間のソーク期間後にedgeから昇格 |
| `edge` | 最新の機能と修正 | mainへのマージごと |
| `pr-N` | PRプレビュービルド | プルリクエストごとに自動 |

### チャンネルの切り替え

```bash
rdc update --channel edge      # エッジチャンネルに切り替え
rdc update --channel stable    # 安定版チャンネルに戻る
```

エッジチャンネルから直接インストール:

```bash
REDIACC_CHANNEL=edge curl -fsSL https://www.rediacc.com/install.sh | bash
```

パッケージマネージャーの場合、リポジトリURLの `stable` を `edge` に置き換えてください:

```bash
# APT edge
echo "deb [signed-by=/usr/share/keyrings/rediacc.gpg] https://releases.rediacc.com/apt/edge stable main" | sudo tee /etc/apt/sources.list.d/rediacc.list

# Docker edge
docker pull ghcr.io/rediacc/elite/cli:edge
```

### チャンネルの仕組み

チャンネルはすべての配信方法に統一的に適用されます:

- **インストールスクリプト**: 環境変数 `REDIACC_CHANNEL` でチャンネルを選択
- **パッケージリポジトリ**: `releases.rediacc.com/{フォーマット}/{チャンネル}/`
- **Dockerタグ**: `ghcr.io/rediacc/elite/cli:{チャンネル}`
- **CLIアップデート**: `rdc update` はインストール時に設定されたチャンネルを確認

### PRプレビューの自動設定

PRプレビューデプロイメント (例: `pr-420.rediacc.workers.dev`) からインストールすると、チャンネルとアカウントサーバーが自動的に設定されます:

- CLIバイナリが `pr-420` チャンネルからダウンロードされます
- `rdc update` が `pr-420` チャンネルの更新を確認します
- すべてのアカウント/サブスクリプションコマンドがPRプレビューサーバーに接続します
- プレビューサイトのDockerコマンドが `cli:pr-420` を表示します

手動設定は不要です。インストールスクリプトがURLからデプロイメントコンテキストを検出します。

## リモートバイナリの更新

リモートマシンに対してコマンドを実行すると、CLIは対応する `renet` バイナリを自動的にプロビジョニングします。バイナリが更新されると、新しいバージョンを取得するためにルートサーバー (`rediacc-router`) が自動的に再起動されます。

再起動は透過的で、**ダウンタイムは発生しません**:

- ルートサーバーは約1-2秒で再起動します。
- その間、Traefikは最後に認識したルーティング設定を使用してトラフィックの処理を継続します。ルートが失われることはありません。
- Traefikは次のポーリングサイクル (5秒以内) で新しい設定を取得します。
- **既存のクライアント接続 (HTTP、TCP、UDP) は影響を受けません。** ルートサーバーは設定プロバイダーであり、データパス上にはありません。Traefikがすべてのトラフィックを直接処理します。
- アプリケーションコンテナには一切触れません -- システムレベルのルートサーバープロセスのみが再起動されます。

自動再起動をスキップするには、任意のコマンドに `--skip-router-restart` を渡すか、環境変数 `RDC_SKIP_ROUTER_RESTART=1` を設定してください。
