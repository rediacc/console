---
title: "インストール"
description: "Linux、macOS、またはWindowsにRediacc CLIをインストールする。"
category: "Guides"
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

## Windows

PowerShellでインストールスクリプトを実行します：

```powershell
irm https://www.rediacc.com/install.ps1 | iex
```

これにより、`rdc.exe`バイナリが`%LOCALAPPDATA%\rediacc\bin\`にダウンロードされます。このディレクトリがPATHに含まれていることを確認してください。インストーラーは、まだ含まれていない場合に追加するよう案内します。

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
