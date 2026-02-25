---
title: システム要件
description: Rediaccを実行するためのシステム要件とサポートされているプラットフォーム。
category: Guides
order: 0
language: ja
sourceHash: 40a59ab9c9625911
---

# システム要件

どのツールを使うべきか迷う場合は、[rdc vs renet](/ja/docs/rdc-vs-renet) を参照してください。

Rediaccでデプロイする前に、ワークステーションとリモートサーバーが以下の要件を満たしていることを確認してください。

## ワークステーション（コントロールプレーン）

`rdc` CLIはワークステーション上で動作し、SSH経由でリモートサーバーをオーケストレーションします。

| プラットフォーム | 最小バージョン | 備考 |
|----------|----------------|-------|
| macOS | 12 (Monterey)+ | IntelおよびApple Siliconに対応 |
| Linux (x86_64) | 任意のモダンなディストリビューション | glibc 2.31+ (Ubuntu 20.04+, Debian 11+, Fedora 34+) |
| Windows | 10+ | PowerShellインストーラーによるネイティブサポート |

**追加要件：**
- SSHキーペア（例：`~/.ssh/id_ed25519` または `~/.ssh/id_rsa`）
- SSHポート（デフォルト：22）でリモートサーバーへのネットワークアクセス

## リモートサーバー（データプレーン）

`renet`バイナリはリモートサーバー上でroot権限で動作します。暗号化ディスクイメージ、隔離されたDockerデーモン、サービスオーケストレーションを管理します。

### サポートされているオペレーティングシステム

| OS | バージョン | アーキテクチャ |
|----|---------|-------------|
| Ubuntu | 24.04+ | x86_64 |
| Debian | 12+ | x86_64 |
| Fedora | 43+ | x86_64 |
| openSUSE Leap | 15.6+ | x86_64 |
| Alpine | 3.19+ | x86_64（gcompat が必要） |
| Arch Linux | ローリングリリース | x86_64 |

これらはCIでテスト済みのディストリビューションです。systemd、Dockerサポート、cryptsetupを備えた他のLinuxディストリビューションでも動作する可能性がありますが、公式にはサポートされていません。

### サーバーの前提条件

- `sudo`権限を持つユーザーアカウント（パスワードなしのsudo推奨）
- `~/.ssh/authorized_keys`にSSH公開鍵が追加済みであること
- 最低20 GBの空きディスク容量（ワークロードに応じてさらに必要）
- Dockerイメージ取得のためのインターネットアクセス（またはプライベートレジストリ）

### 自動インストール

`rdc config setup-machine`コマンドは、リモートサーバーに以下をインストールします：

- **Docker** と **containerd**（コンテナランタイム）
- **cryptsetup**（LUKS ディスク暗号化）
- **renet** バイナリ（SFTP経由でアップロード）

これらを手動でインストールする必要はありません。

## Local Virtual Machines (Optional)

If you want to test deployments locally using `rdc ops`, your workstation needs virtualization support: KVM on Linux or QEMU on macOS. See the [Experimental VMs](/ja/docs/experimental-vms) guide for setup steps and platform details.
