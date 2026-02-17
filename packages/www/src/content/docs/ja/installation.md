---
title: "インストール"
description: "Linux、macOS、またはWindowsにRediacc CLIをインストールする。"
category: "Getting Started"
order: 1
language: ja
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

## Windows (WSL2)

RediaccはWindows上のWSL2内で動作します。WSL2がセットアップされていない場合：

```powershell
wsl --install
```

次に、WSL2のLinuxディストリビューション内で同じインストールスクリプトを実行します：

```bash
curl -fsSL https://get.rediacc.com | sh
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
