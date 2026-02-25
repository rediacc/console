---
title: "実験的VM"
description: "rdc opsを使用して、開発およびテスト用のローカルVMクラスターをプロビジョニングします。"
category: "Concepts"
order: 2
language: ja
sourceHash: fa4069c48c650a79
---

# 実験的VM

ワークステーション上にローカルVMクラスターをプロビジョニングし、開発やテストに使用できます。外部クラウドプロバイダーは不要です。

## 前提条件

`rdc ops` は**ローカルアダプター**が必要です。クラウドアダプターでは利用できません。

```bash
rdc ops check
```

## 概要

`rdc ops` コマンドを使用すると、実験用 VM クラスターをローカルで作成・管理できます。これは CI パイプラインで統合テストに使用されているものと同じインフラストラクチャであり、実践的な実験にご利用いただけるようになりました。

ユースケース：
- 外部VMプロバイダー（Linode、Vultrなど）なしでRediaccデプロイメントをテスト
- リポジトリ設定をローカルで開発・デバッグ
- 完全に分離された環境でプラットフォームを学習
- ワークステーション上で統合テストを実行

## プラットフォームサポート

| プラットフォーム | アーキテクチャ | バックエンド | ステータス |
|----------|-------------|---------|--------|
| Linux | x86_64 | KVM (libvirt) | CIでテスト済み |
| macOS | Intel | QEMU + HVF | CIでテスト済み |
| Linux | ARM64 | KVM (libvirt) | サポート済み（CIテストなし） |
| macOS | ARM (Apple Silicon) | QEMU + HVF | サポート済み（CIテストなし） |
| Windows | x86_64 / ARM64 | Hyper-V | 計画中 |

**Linux (KVM)** はlibvirtを使用し、ブリッジネットワーキングによるネイティブハードウェア仮想化を提供します。

**macOS (QEMU)** はAppleのHypervisor Framework（HVF）を搭載したQEMUを使用し、ユーザーモードネットワーキングとSSHポートフォワーディングにより、ネイティブに近いパフォーマンスを実現します。

**Windows (Hyper-V)** のサポートは計画中です。詳細は[issue #380](https://github.com/rediacc/console/issues/380)を参照してください。Windows Pro/Enterpriseが必要です。

## 前提条件とセットアップ

### Linux

```bash
# Install prerequisites automatically
rdc ops setup

# Or manually:
sudo apt install libvirt-daemon-system virtinst qemu-utils cloud-image-utils docker.io
sudo systemctl enable --now libvirtd
```

### macOS

```bash
# Install prerequisites automatically
rdc ops setup

# Or manually:
brew install qemu cdrtools
```

### セットアップの確認

```bash
rdc ops check
```

プラットフォーム固有のチェックを実行し、各前提条件の合否を報告します。

## クイックスタート

```bash
# 1. Check prerequisites
rdc ops check

# 2. Provision a minimal cluster (bridge + 1 worker)
rdc ops up --basic

# 3. Check VM status
rdc ops status

# 4. SSH into the bridge VM
rdc ops ssh 1

# 4b. Or run a command directly
rdc ops ssh 1 hostname

# 5. Tear down
rdc ops down
```

## クラスター構成

デフォルトでは、`rdc ops up`は以下をプロビジョニングします：

| VM | ID | 役割 |
|----|-----|------|
| ブリッジ | 1 | プライマリノード — Rediaccブリッジサービスを実行 |
| ワーカー1 | 11 | リポジトリデプロイメント用のワーカーノード |
| ワーカー2 | 12 | リポジトリデプロイメント用のワーカーノード |

`--basic`フラグを使用すると、ブリッジと最初のワーカーのみをプロビジョニングします（ID 1と11）。

`--skip-orchestration`を使用すると、Rediaccサービスを起動せずにVMのみをプロビジョニングします。VM層を分離してテストする場合に便利です。

## 設定

ブリッジVMはワーカーVMよりも小さいデフォルト値を使用します：

| VMの役割 | CPU | RAM | ディスク |
|---------|------|-----|------|
| ブリッジ | 1 | 1024 MB | 8 GB |
| ワーカー | 2 | 4096 MB | 16 GB |

環境変数でワーカーVMリソースを上書きできます：

| 変数 | デフォルト | 説明 |
|----------|---------|-------------|
| `VM_CPU` | 2 | ワーカーVM あたりのCPUコア数 |
| `VM_RAM` | 4096 | ワーカーVMあたりのRAM（MB） |
| `VM_DSK` | 16 | ワーカーVMあたりのディスクサイズ（GB） |
| `VM_NET_BASE` | 192.168.111 | ネットワークベース（KVMのみ） |
| `RENET_DATA_DIR` | ~/.renet | VMディスクと設定のデータディレクトリ |

## コマンドリファレンス

| コマンド | 説明 |
|---------|-------------|
| `rdc ops setup` | プラットフォームの前提条件をインストール（KVMまたはQEMU） |
| `rdc ops check` | 前提条件がインストールされ動作していることを確認 |
| `rdc ops up [options]` | VMクラスターをプロビジョニング |
| `rdc ops down` | すべてのVMを破棄しクリーンアップ |
| `rdc ops status` | すべてのVMのステータスを表示 |
| `rdc ops ssh <vm-id> [command...]` | VMにSSH接続、またはVM上でコマンドを実行 |

### `rdc ops up` オプション

| オプション | 説明 |
|--------|-------------|
| `--basic` | 最小構成のクラスター（ブリッジ + ワーカー1台） |
| `--lite` | VMプロビジョニングをスキップ（SSHキーのみ） |
| `--force` | 既存のVMを強制的に再作成 |
| `--parallel` | VMを並列でプロビジョニング |
| `--skip-orchestration` | VMのみ、Rediaccサービスなし |
| `--backend <kvm\|qemu>` | 自動検出されたバックエンドを上書き |
| `--os <name>` | OSイメージ（デフォルト：ubuntu-24.04） |
| `--debug` | 詳細な出力 |

## プラットフォームの違い

### Linux (KVM)
- libvirtを使用してVMのライフサイクルを管理
- ブリッジネットワーキング — VMは仮想ネットワーク上のIPを取得（192.168.111.x）
- VM IPへの直接SSH接続
- `/dev/kvm`とlibvirtdサービスが必要

### macOS (QEMU + HVF)
- PIDファイルで管理されるQEMUプロセスを使用
- SSHポートフォワーディングによるユーザーモードネットワーキング（localhost:222XX）
- 直接IPではなくフォワードされたポート経由でSSH接続
- `mkisofs`でCloud-init ISOを作成

## トラブルシューティング

### デバッグモード

任意のコマンドに`--debug`を追加すると詳細な出力が得られます：

```bash
rdc ops up --basic --debug
```

### よくある問題

**KVMが利用できない（Linux）**
- `/dev/kvm`が存在するか確認：`ls -la /dev/kvm`
- BIOS/UEFIで仮想化を有効にする
- カーネルモジュールをロード：`sudo modprobe kvm_intel`または`sudo modprobe kvm_amd`

**libvirtdが動作していない（Linux）**
```bash
sudo systemctl enable --now libvirtd
```

**QEMUが見つからない（macOS）**
```bash
brew install qemu cdrtools
```

**VMが起動しない**
- `~/.renet/disks/`のディスク容量を確認
- `rdc ops check`を実行してすべての前提条件を確認
- `rdc ops down`を実行してから`rdc ops up --force`を試す
