---
title: "GPU"
description: "CDI デバイスグラントでリポジトリに GPU へのアクセスを与える方法です。マシンの GPU の一覧表示、リポジトリごとのデバイスの付与と取り消し、カードの専有予約、WSL での利用を扱います。"
category: "Guides"
tags:
  - containers
  - operations
subcategory: workloads
order: 7
language: ja
sourceHash: "1eeb1e646bd914d2"
sourceCommit: "80854ab96b06bee39cceae6b259e9efbc342f93a"
---

# GPU

リポジトリが GPU を使えるのは、**デバイスグラント**を通した場合だけです。マシンは搭載している GPU を名前付きデバイスとして公開し、オペレーターがリポジトリに使用を認める名前を付与します。グラントのないリポジトリには GPU が割り当てられず、[フォーク](/ja/docs/repositories)は、親にグラントがあっても、グラントなしで始まります。

名前は Container Device Interface (CDI) に従います。CDI は Docker 25 以降が、デバイスと、コンテナがそれを使うために必要なすべてを記述するために使う標準です。CDI 名は `<vendor>/<class>=<device>` の形式で、たとえば `nvidia.com/gpu=all` です。

## CDI グラントとは

各リポジトリは、ハードウェアをコンテナに接続するあらゆる方法を拒否する API ゲートの背後で、専用の Docker デーモンを実行します。そのため、`docker run` のフラグでは GPU に到達できません。グラントが唯一の入口です。グラントは 1 つのリポジトリに対して正確な CDI 名を記録し、ゲートはそのデバイスだけを指名するコンテナリクエストを受け付けます。

- グラントは次の Docker リクエストから有効になり、デーモンの再起動は不要です。
- グラントは正確に 1 つのデバイスを指名します。`nvidia.com/gpu=all` を付与すると `nvidia.com/gpu=all` が許可され、`nvidia.com/gpu=0` は許可されません。リポジトリに 1 枚のカードだけを与えるには、そのカードの名前を付与します。
- グラントは書き込み時にマシン上のデバイス仕様と照合されるため、綴りを誤った名前は記録されずに拒否されます。
- グラントは、付与されたリポジトリに属します。フォークやコピーには、それぞれ独自のグラントが必要です。

## マシンのセットアップ

`rdc machine setup <machine>` はマシンの GPU を検出し、結果を `/etc/rediacc/gpu/inventory.json` に記録します。NVIDIA GPU がある場合、セットアップは NVIDIA Container Toolkit もインストールし、CDI 仕様を `/etc/cdi/nvidia.yaml` に生成します。GPU のないマシンにも、空のリストを持つインベントリファイルが作られます。

ツールキットのインストールは、`renet setup` のオプション `--install-nvidia-toolkit` で制御します。

| 値 | 動作 |
|---|---|
| `auto` | NVIDIA GPU がある場合にツールキットをインストールします。既定値です。 |
| `true` | 常にツールキットをインストールします。 |
| `false` | ツールキットを省略し、NVIDIA 仕様を生成しません。 |

許可されるのは `runc` だけなので、セットアップはコンテナランタイムを設定しません。ツールキットは仕様の生成にだけ使われ、仕様はドライバーの変更に追従するようセットアップのたびに再生成されます。

2 種類のデバイスは Rediacc 自身が提供します。デバイスノードを対応付けるだけなので、ベンダーのユーザー空間コンポーネントは不要です。

| 種類 | デバイス | 由来 |
|---|---|---|
| `rediacc.io/dri` | レンダーノードごとに 1 つ。例: `rediacc.io/dri=renderD128` | `/dev/dri/renderD<N>` |
| `rediacc.io/amd` | AMD カード 1 枚ごとの `gpu<N>` と `all` | `/dev/kfd` とそのカードのレンダーノード |

NVIDIA のデバイスはツールキットの仕様から得られます。`nvidia.com/gpu=all` と、カードごとに 1 つの名前です。AMD の計算には、コンテナイメージ内の ROCm ユーザー空間が必要です。セットアップは ROCm をインストールしません。

## GPU の一覧表示

```bash
rdc machine gpu list <machine>
rdc machine gpu list <machine> -o json
```

表には、各 GPU の名前、ドライバーのバージョン、メモリ、プラットフォーム (ネイティブまたは WSL)、インベントリの経過時間、付与できるすべての CDI デバイス名が表示されます。`-o json` は、マシンに記録されたとおりのインベントリを出力します。現在有効なグラントは、マシンからリアルタイムで読み取られます。

## 付与と取り消し

```bash
rdc repo gpu grant <repo-ref> --device nvidia.com/gpu=all
rdc repo gpu revoke <repo-ref> --device nvidia.com/gpu=all
```

`<repo-ref>` はリポジトリ名で、`gpu-a@wsl-gpu` のようにマシンを付けることもできます。どちらのコマンドも、異なる `--device` の値で繰り返せます。グラントの後は、そのリポジトリのコンテナがデバイス付きで起動します。

```bash
docker run --rm --device nvidia.com/gpu=all ubuntu:24.04 nvidia-smi -L
```

グラントのないリポジトリでは同じコンテナが拒否され、メッセージに不足しているグラントが示されます。

## 専有グラント

```bash
rdc repo gpu grant <repo-ref> --device nvidia.com/gpu=0 --exclusive
```

専有グラントは、デバイスを 1 つのリポジトリ専用に予約します。別のリポジトリが同じ名前を保持している場合は拒否され、専有グラントが有効な間は、その名前を他のリポジトリに付与することも拒否されます。この確認は、マシン上のすべてのグラントにかかるロックの下で、付与時に行われます。

専有グラントは予約であり、スケジューラーではありません。グラントを受けた同じリポジトリ内の 2 つのコンテナは、引き続きカードを共有します。

## 拒否される記述

GPU に到達する他の方法は、グラントの有無にかかわらず拒否されたままです。CDI 形式がそれぞれの代わりになります。

| 拒否されるもの | 代わりに使うもの |
|---|---|
| `docker run --gpus all` | `docker run --device nvidia.com/gpu=all` |
| Compose の `runtime: nvidia` | `devices: [nvidia.com/gpu=all]` |
| Compose の `deploy.resources.reservations.devices` | `devices: [nvidia.com/gpu=all]` |
| Compose の `gpus: all` | `devices: [nvidia.com/gpu=all]` |
| 生の `/dev/dri` や `/dev/kfd` デバイス、または `/dev` 配下の bind | `rediacc.io/dri=renderD128` または `rediacc.io/amd=gpu0` |
| デバイス cgroup ルール | そのデバイスへの CDI グラント |

付与されたデバイスを使う Compose サービスは次のようになります。

```yaml
services:
  inference:
    image: ubuntu:24.04
    command: nvidia-smi -L
    devices:
      - nvidia.com/gpu=all
```

`group_add` で `video` や `render` などのグループを追加することは受け付けられますが、何も付与しません。グループは、リポジトリに付与されていないデバイスへのアクセスを開かないためです。

## WSL

WSL2 では、Windows のドライバーが `/dev/dxg` と `/usr/lib/wsl/lib` 配下のライブラリを通して GPU を提供します。マシンはプラットフォームを `wsl` と報告し、セットアップは NVIDIA 仕様を WSL 形式で生成します。

```bash
nvidia-ctk cdi generate --mode=wsl --output=/etc/cdi/nvidia.yaml
```

ドライバーは Windows 側にあるため、そこでの更新は次回の `rdc machine setup` で反映されます。付与、一覧表示、取り消しのコマンドは、ネイティブのマシンと同じように動作します。

## ネイティブ NVIDIA

ネイティブの NVIDIA マシンでは、ツールキットの `nvidia-cdi-refresh` サービスが、インストール、ドライバーの変更、起動の後に仕様を再生成します。セットアップはこれを `/etc/cdi/nvidia.yaml` に向けます。これは、リポジトリの Docker デーモンが読む唯一の仕様ディレクトリです。`nvidia-persistenced` が動作している場合、仕様がそのソケットをコンテナにマウントするため、ソケットはリポジトリのデーモンから見えるようになります。
