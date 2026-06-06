---
title: システム要件
description: Rediaccを実行するためのシステム要件とサポートされているプラットフォーム。
category: Guides
order: 0
language: ja
sourceHash: "e84db3bb90270473"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# システム要件

ほとんどは標準的なLinuxサーバーのセットアップです。いくつかの詳細はRediaccの動作方法に固有なため、開始前に確認してください。

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

どのツールを使うべきか迷う場合は、[rdc vs renet](/en/docs/rdc-vs-renet) を参照してください。簡単に言うと、通常の操作には `rdc` を使用し、高度なサーバーサイドのタスクにのみ `renet` を直接使用してください。

### サポートされているオペレーティングシステム

リモートサーバーは `renet` バイナリを実行し、リポジトリごとに暗号化・隔離されたDockerデーモンをホストします。以下の5つのディストリビューションは、すべてのプルリクエストでCI上のBridge Workersマトリックスによってテストされており、公式にサポートされている唯一のものです：

| OS | バージョン | デフォルトカーネル | 備考 |
|----|---------|----------------|-------|
| Ubuntu | 24.04 LTS | 6.8 | 推奨。AppArmormがデフォルトで有効。 |
| Debian | 13 (Trixie) | 6.12 | Debian 12も動作します（カーネル6.1以上が必要）。 |
| Fedora | 43 | 6.12 | SELinuxがデフォルトでenforcing。 |
| openSUSE Leap | 16.0 | 6.4+ | AppArmormがデフォルトで有効。 |
| Oracle Linux | 10 | UEK 7+ | btrfsモジュールを保持するUEKを使用。SELinuxがデフォルトでenforcing。下記「なぜUEK？」を参照。 |

すべての行は `x86_64` です。`arm64` はビルドされますが、すべてのサーバーOSで継続的にテストされているわけではありません。特定のディストリビューションで必要な場合はIssueを開いてください。systemd、Dockerサポート、cryptsetupを備えた他のLinuxディストリビューションでも動作する可能性がありますが、公式にはサポートされておらず、アップグレード時に予告なく動作しなくなる場合があります。

#### なぜUEK？（そしてなぜRocky 10 / ストックRHEL 10はサポートされないのか）

Rediaccの暗号化ストレージバックエンドには、ツリー内の `btrfs` カーネルモジュールが必要です。**RHEL 10のストックカーネルにはそれが含まれていません**：`modprobe btrfs` は "Module btrfs not found" で失敗し、`dnf search btrfs` は何も返しません。Rocky Linux 10とAlmaLinux 10は同じカーネルを継承しているため、Rediaccサーバーとして動作させることができません。

Oracle Linux 10はデフォルトで **Unbreakable Enterprise Kernel (UEK)** を使用しており、btrfsが組み込まれています。これがサポートリストに載っている唯一のRHEL互換ターゲットです。RHELファミリーのサーバーを使用しなければならない場合は、UEK付きのOracle Linux 10を使用してください。（この決定の根拠は `.github/workflows/ct-tests.yml` のCI Bridge Workersマトリックスにあります。）

#### ワークステーション専用（CLIインストールターゲット）

`rdc` CLIはAlpine 3.19+（`gcompat`互換レイヤー付きのAPK、自動インストール）およびArch Linux（ローリング、pacman経由）にもクリーンにインストールできます。これらはクライアントサイドのインストールパスのみです（[インストール](/en/docs/installation)を参照）。`renet`サーバーターゲットとしてはサポートされていません。

### OSごとのセキュリティポリシー

リポジトリごとのDockerデーモンとリポジトリコンテナ自体は、すべてのサポート対象OSで**デフォルトのコンテナラベル**で実行されます。`rdc config machine setup` はカスタムSELinuxポリシーやAppArmorプロファイルをインストールしません。OSごとの動作：

- **Ubuntu 24.04、openSUSE Leap 16.0**：AppArmormがデフォルトで有効です。デフォルトのdocker-containerプロファイルが適用されます。追加のセットアップは不要です。
- **Fedora 43、Oracle Linux 10**：SELinuxがenforcing状態で実行されます。リポジトリごとのデーモンは、標準の `container_t` コンテキストでコンテナにラベルを付けます。カスタムSELinuxポリシーは不要です。
- **CRIU**（チェックポイント/リストア）は、`apparmor=unconfined` でAppArmorプロファイルをバイパスする唯一のケースです。アップストリームCRIUのAppArmormサポートがまだ安定していないためです。[Rediaccのルール](/en/docs/rules-of-rediacc)のCRIUに関する注記を参照してください。

SELinux AVCの拒否またはAppArmorの拒否でセットアップステップが失敗した場合は、[トラブルシューティング](/en/docs/troubleshooting)の「ディストリビューション固有のセットアップの問題」を参照してください。

### サーバーの前提条件

- `sudo`権限を持つユーザーアカウント（パスワードなしのsudo推奨）
- `~/.ssh/authorized_keys`にSSH公開鍵が追加済みであること
- 最低20 GBの空きディスク容量（ワークロードに応じてさらに必要）
- Dockerイメージ取得のためのインターネットアクセス（またはプライベートレジストリ）

### 自動インストール

`rdc config machine setup`コマンドは、リモートサーバーに以下をインストールします：

- **Docker** と **containerd**（コンテナランタイム）
- **cryptsetup**（LUKS ディスク暗号化）
- **renet** バイナリ（SFTP経由でアップロード）

これらを手動でインストールする必要はありません。

## ローカル仮想マシン（オプション）

`rdc ops` を使用してローカルでデプロイメントをテストする場合、ワークステーションに仮想化サポートが必要です：LinuxではKVM、macOSではQEMU。セットアップ手順とプラットフォームの詳細については、[実験的なVM](/en/docs/experimental-vms) ガイドを参照してください。
