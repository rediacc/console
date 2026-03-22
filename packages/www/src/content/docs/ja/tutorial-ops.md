---
title: "ローカルVM プロビジョニング"
description: "CLIを使用してローカルVMクラスターをプロビジョニングし、SSH経由でコマンドを実行し、クリーンアップします。"
category: "Tutorials"
order: 1
language: ja
sourceHash: "2fdc49f796b03e18"
---

# Rediaccでローカル VMをプロビジョニングする方法

本番環境にデプロイする前にローカルでインフラストラクチャをテストすることで、時間を節約し、設定ミスを防ぐことができます。このチュートリアルでは、ワークステーション上に最小構成のVMクラスターをプロビジョニングし、接続を確認し、SSH経由でコマンドを実行し、すべてを破棄します。完了すると、再現可能なローカル開発環境が得られます。

## 前提条件

- ハードウェア仮想化が有効なLinuxまたはmacOSワークステーション
- `rdc` CLIがインストールされ、ローカルアダプターで構成が初期化されていること
- KVM/libvirt（Linux）またはQEMU（macOS）がインストールされていること — セットアップ手順は[実験的VM](/ja/docs/experimental-vms)を参照

## インタラクティブ録画

![Tutorial: rdc ops provisioning](/assets/tutorials/ops-tutorial.cast)

### ステップ1: システム要件の確認

プロビジョニングの前に、ワークステーションに仮想化サポートと必要なパッケージがインストールされていることを確認します。

```bash
rdc ops check
```

Rediaccはハードウェア仮想化（VT-x/AMD-V）、必要なパッケージ（libvirt、QEMU）、およびネットワーク構成を確認します。VMを作成する前に、すべてのチェックに合格する必要があります。

### ステップ2: 最小構成のVMクラスターをプロビジョニング

```bash
rdc ops up --basic --skip-orchestration
```

2つのVMクラスターを作成します：**ブリッジ**VM（1 CPU、1024 MB RAM、8 GBディスク）と**ワーカー**VM（2 CPU、4096 MB RAM、16 GBディスク）。`--skip-orchestration`フラグはRediaccプラットフォームのプロビジョニングをスキップし、SSHアクセスのみの素のVMを提供します。

> **注意:** 初回のプロビジョニングではベースイメージのダウンロードが行われるため、時間がかかります。以降の実行ではキャッシュされたイメージが再利用されます。

### ステップ3: クラスターステータスの確認

```bash
rdc ops status
```

クラスター内の各VMの状態を表示します — IPアドレス、リソース割り当て、実行ステータス。両方のVMが実行中として表示されるはずです。

### ステップ4: VM上でコマンドを実行

```bash
rdc ops ssh 1 hostname
rdc ops ssh 1 uname -a
```

ブリッジVM（ID `1`）上でSSH経由でコマンドを実行します。VM IDの後に任意のコマンドを渡せます。対話的なシェルの場合は、コマンドを省略します：`rdc ops ssh 1`。

### ステップ5: クラスターの破棄

作業が完了したら、すべてのVMを破棄してリソースを解放します。

```bash
rdc ops down
```

すべてのVMを削除し、ネットワークをクリーンアップします。クラスターは`rdc ops up`でいつでも再プロビジョニングできます。

## トラブルシューティング

**"KVM not available"または"hardware virtualization not supported"**
BIOS/UEFI設定で仮想化が有効になっていることを確認してください。Linuxでは`lscpu | grep Virtualization`で確認できます。WSL2では、ネストされた仮想化に特定のカーネルフラグが必要です。

**"libvirt daemon not running"**
libvirtサービスを起動してください：`sudo systemctl start libvirtd`。macOSでは、HomebrewでQEMUがインストールされていることを確認してください：`brew install qemu`。

**"Insufficient memory for VM allocation"**
基本クラスターには少なくとも6 GBの空きRAMが必要です（1 GBブリッジ + 4 GBワーカー + オーバーヘッド）。他のリソース集約型アプリケーションを閉じるか、VMの仕様を縮小してください。

## 次のステップ

ローカルVMクラスターをプロビジョニングし、SSH経由でコマンドを実行し、破棄しました。実際のインフラストラクチャをデプロイするには：

- [実験的VM](/ja/docs/experimental-vms) — `rdc ops`コマンド、VM構成、プラットフォームサポートの完全なリファレンス
- [チュートリアル：マシンセットアップ](/ja/docs/tutorial-setup) — リモートマシンの登録とインフラストラクチャの構成
- [クイックスタート](/ja/docs/quick-start) — コンテナ化されたサービスをエンドツーエンドでデプロイ
