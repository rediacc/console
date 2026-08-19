---
title: "Kubernetes"
description: "Rediaccのリポジトリの考え方でKubernetesを運用する: 実行中のクラスターを、そのデータごと、短いカットオーバーで別のマシンやデータセンターへフォークまたは移動できます。"
category: "Guides"
tags:
  - containers
  - migration
order: 6
language: ja
sourceHash: "22eef465dfd46ccf"
sourceCommit: "4401262fffbf29b9480dee8ecd209013e4b87f60"
---

# Kubernetes

Rediaccは、プラットフォームの他の部分が拠って立つリポジトリの考え方を維持したまま、Kubernetesを製品に取り込みます。差別化の主張は明確です。**実行中のクラスターを、そのデータごと、短いカットオーバーで別のマシンやデータセンターへフォークまたは移動できる**のです。これは停止・復元型のマイグレーションではなく、ゼロダウンタイムの魔法でもありません。ワークロードは移動先で再起動し、カットオーバーは秒単位で測定され、データは一緒に移動します。

Kubernetesは、認定Kubernetesディストリビューションである[k3s](https://k3s.io/)によって駆動されており、他のサーバー側バイナリと同じ方法でrenetに組み込まれています。

## オブジェクトモデル

Rediaccは、リポジトリの考え方が引き続き成り立つように、通常の「クラスターがすべてを包む」という図式を反転させます。

- **クラスターがコンテナです。** マシンはDockerリポジトリ(変更なし)や、クラスターをホストします。1台のマシン上のシングルノードクラスターは、クラスターレベルでも「1つのファイルがシステム全体を移動する」という物語を保ちます。クラスターの状態(k3sのデータディレクトリ: その組み込みデータストアとcontainerd)は、ノードごとにデータストアに支えられたcopy-on-writeイメージファイルに存在し、k3sの `--data-dir` はイメージのマウント内にバインドされます。
- **Kubernetesリポジトリはnamespaceです。** `rdc repo create <repo> -m <name>` は、そのクラスター内のKubernetes namespace `<repo>` を実行の場とするリポジトリを作成します。
- **永続ボリュームは別個のcopy-on-writeユニットです。** PVはCeph上のRBDイメージか、ローカルバックエンドではローカルPVプロビジョナーによる小さなデータストアイメージファイルです。1つの不透明なクラスターイメージ内のディレクトリになることは決してありません。内部のファイルシステムにはreflinkがないため、独立したリポジトリフォークには独立したPVイメージが必要です。

この分離こそが、両方の約束を同時に物理的に可能にしています。**常にcopy-on-writeなnamespaceフォーク**(各リポジトリのデータが独立してクローンされる)と、**クラスター全体の可搬性**(クラスターイメージと各PVイメージがまとめて移動する)です。

| 概念 | Dockerリポジトリ | Kubernetesリポジトリ |
|---|---|---|
| 実行の場 | 分離されたDockerデーモン | クラスター内のnamespace |
| 注入される環境変数 | `DOCKER_HOST` | `KUBECONFIG` |
| デプロイのラッパー | `renet compose` | `renet kube` |
| データの単位 | 1つのLUKSイメージ | クラスターイメージ + PVごとのイメージ |
| フォークの単位 | リポジトリのイメージ | namespace + そのPVクローン |
| 場所全体のクローン | (リポジトリが場所そのもの) | `rdc cluster fork` / `rdc cluster migrate` |

## クラスターの宣言と作成

クラスターは、プライベートネットワーク上の名前付きノードプールの集合です。まず設定内で宣言し、その後プロビジョニングします。

```bash
# プールを持つクラスターを宣言する(まだ何もプロビジョニングされていない)
rdc cluster create prod --declare-only \
  --provider my-linode \
  --pool ceph:ceph:3 \
  --pool k8s:k8s-server:3

# プールメンバーをプロビジョニングし、各ノードにrenetをブートストラップし、コンポーネント(まずCeph)をインストールする
rdc cluster create prod
```

プールのロールは `ceph`、`k8s-server`、`k8s-agent`、`hyperconverged` です(Cephのメモリターゲットとkubeletのeviction閾値がRAMを奪い合うため、明示的なopt-inです)。各プールはハードウェアの非対称性をプールごとのサイズとディスクパラメータとして持ちます。ディスク重視のCephノード、CPU/RAM重視のKubernetesノードです。

プールメンバーは `<cluster>-<pool>-<n>` として `resources.machines` に実体化され、バックリファレンスを持つため、**既存のあらゆる `-m` コマンドがそのまま使えます**。`rdc machine status`、`rdc term connect`、repoコマンド、バックアップ戦略はすべて、クラスターノードを通常のマシンとして扱います。

クラウドプロバイダーは、`rdc machine provision` が使うのと同じ `ProviderMapping` レジストリに従い、プライベートネットワークブロック(VLANかVPCか、スタンプするMTU、プライベートNICの命名)で拡張された形で[OpenTofu](https://opentofu.org/)経由でプロビジョニングします。ローカルKVMは `rdc ops` 経由で常に利用可能なテスト経路です。

```bash
# クラスターを確認する
rdc cluster status                 # すべてのクラスターを一覧表示
rdc cluster status prod     # 1つのクラスターの全設定

# プールを拡大・縮小する(マシンの追加/削除、ノードの参加/排出)
rdc cluster scale prod --pool k8s --count 5


# プロビジョニング済みメンバーを破棄し、設定からクラスターを削除する
rdc cluster destroy prod
```

### kubeconfigの取得

kubeconfigは設定ファイルには決して保存されません(サイズが大きく、ローテーションするためです)。SSH経由でオンデマンドに取得され、OpenTofuのworkdirや証明書キャッシュと同じ副次的な状態パターンに従って、`0600` パーミッションでローカルにキャッシュされます。

```bash
rdc cluster kubeconfig prod
# 表示: export KUBECONFIG=~/.config/rediacc/kube/prod.yaml
```

## Kubernetesリポジトリ

ターゲットフラグがランタイムを決定します。タイプフラグはありません。

```bash
# Dockerリポジトリ(変更なし): マシン上の分離されたDockerデーモン
rdc repo create shop -m server-1 --size 10G

# Kubernetesリポジトリ: クラスター内の namespace "shop" + そのストレージ
rdc repo create shop --datastore prod --size 10G
```

repoの各動詞は、リポジトリ単位の作業に対する単一のサーフェスです。ターゲット解決の漏斗を通じて、repoコマンド群のほぼ全体がクラスター対応になります。`fork`、`migrate`、`push`、`pull`、`up`、`down`、`resize`、`diff`、`commit`、`branch`、`checkout`、`merge`、`trim`、`cat`、`mount`、`sync`、`list`、`status`、`log` はすべて `--cluster` を受け付けます。クラスターターゲットは、そのコントロールノードと、リポジトリのnamespaceに固定されたKUBECONFIGコンテキストに解決されます。これは、マシンが `DOCKER_HOST` と作業ディレクトリに解決されるのと同じ類推です。

```bash
rdc repo sync upload shop --local ./config
rdc cluster kubeconfig prod           # KUBECONFIGをエクスポートし、そのままkubectlを使う
```

クラスターノードも `resources.machines` に実体化されるため、通常の `rdc term connect <cluster>-<pool>-<n>` で特定のノードにSSH接続できます。

### デュアルランタイムのRediaccfile

DockerとKubernetesの間の可搬性は、自動的なマニフェスト変換ではなく、規約の上に成り立っています。同じ `up()`・`down()` 関数の下で `renet compose` パスと `renet kube` パスの両方を提供するリポジトリは、データディレクトリの規約が同一であるため、どちらの方向にも自由に移行できます。renetはマシンターゲットでは `DOCKER_HOST` を、クラスターターゲットでは `KUBECONFIG` を注入します。`up()` はどちらが設定されているかを読み取り、それに応じて振り分けます。

```bash
up() {
  if [ -n "$KUBECONFIG" ]; then
    renet kube apply -f manifests/     # Kubernetesランタイム
  else
    renet compose -- up -d             # Dockerランタイム
  fi
}
```

ターゲットのランタイムを宣言していないリポジトリは、データ転送の段階の**後で**明確な拒否を受け取ります。イメージは移動しますが、デプロイの段階で、状態を壊す代わりに、そのリポジトリがKubernetes(またはDocker)のパスを宣言していないことが伝えられます。

## リポジトリのフォーク

Kubernetesリポジトリに対する `rdc repo fork` は、常にデータをコピーし、常に瞬時です。`--full` フラグやバリエーションはありません。

```bash
rdc repo fork shop --tag joseph
```

これにより同じクラスター内にnamespace `shop-joseph` が作成され、すべてのボリュームがcopy-on-writeでクローンされ(Ceph上ではRBDクローン、ローカルバックエンドではPVイメージファイルのreflink)、そこにワークロードがデプロイされます。フォークのURLは親のワイルドカード証明書の下で即座に有効になるため、新しい証明書やDNSレコードは発行されません。

移動先のエスカレーション:

- `--to-cluster <name>` は別の既存クラスターへフォークします。同じCephバックエンドの場合: RBDクローンはcopy-on-writeのままです。異なるバックエンドの場合: push機構がイメージを移動します。
- `--provider <p>` はまず新しいクラスターをプロビジョニングします。プール仕様はデフォルトでソースクラスターの形状を反映します(フラグで上書き可能)。

KVMテストラボで測定したところ、namespaceフォークは親ワークロードに触れることなく、約1〜5秒で完了し、2つのnamespaceは独立して分岐していきます。

## クラスター全体のフォークまたは移動

クラスター全体を対象とする操作は `rdc cluster` グループにあります。これらは異なるオブジェクト(すべてのリポジトリを含む場所全体)に作用するため、単一のリポジトリ名を取るコマンドでは表現できないからです。これがフラッグシップの物語です。

```bash
# クラスター全体を、そのリポジトリのデータごと、新しいクラスターへクローンする
rdc cluster fork prod --to spare --tag staging

# クラスター全体を、そのリポジトリのデータごと、別のマシンやデータセンターへ移動する
rdc cluster migrate prod --to spare
```

どちらも、クラスターイメージと各リポジトリのPVイメージのcopy-on-writeを協調させたのち、ノードのidentityを書き換えて、クローンまたは再配置されたクラスターが新しいアドレスで健全に起動するようにします。k3sはコントロールプレーンの状態を組み込みデータストアに保存するため、クラスターイメージそのものがスナップショットになります。整合性の順序はコントロールプレーン、次にPV、そしてエージェントの順です。

KVMテストラボでエンドツーエンドに測定した正直な数値です。

| 操作 | 内容 | 測定値 |
|---|---|---|
| namespaceフォーク | 1つのリポジトリのnamespaceとPVをその場でクローン | 約1〜5秒 |
| 単一イメージのRBDフォーク | Ceph上のPVクローンをcopy-on-write | 約5秒 |
| 2ノードクラスター全体のフォーク | ドレインし、コントロールプレーンとエージェントをreflinkし、identityを新しいIPへ書き換え、親は無変更のまま | 約46秒 |
| クロスマシンのクラスターマイグレーション | ホットプリコピー + 停止・再起動のカットオーバー | カットオーバー約16秒 |

デフォルトの整合性は**クラッシュコンシステントで参照整合性を保った**ものです。これは電源を落として入れ直したときと同じセマンティクスであり、ワークロードから見てもそう見えます。コピー中にワークロードのファイルシステムをフリーズすれば、アプリケーションコンシステントなスナップショットも利用できます。これは意図的に、ゼロダウンタイムとしては提示していません。「実行中のクラスターを、そのデータごとフォークする」という機能をそもそも提供している他社は存在しません。誠実な打ち出し方は、マーケティング上の絶対値ではなく、短く測定されたカットオーバーです。

## ストレージ: ceph-csiと永続ボリューム

Cephは、いかなるKubernetesクラスターの**外側**で、`ceph` プール上でrenetのcephadmフローによってプロビジョニングされ、クラスターはrenetがテンプレート化したceph-csiマニフェストを通じてそれを利用します。各クラスターインスタンス(および各フォーク)は、テナントごとの分離のプリミティブである独自のRBD/RADOS namespaceを取得します。ストレージはすべてのクラスターの下に存在するため、単純なDockerリポジトリやデータストアバックエンドも支えます。そしてクラスターフォークは、自身のストレージバックエンドをフォークするのではなく、Kubernetesの下でRBDイメージをクローンします。

ローカルバックエンド(Cephなし)では、renetのローカルPVプロビジョナーが各PVをデータストア内の小さなcopy-on-writeイメージファイルで裏付け、フォーク時にreflinkでクローンします。ディスク上のレイアウトとrenetコマンドについては[サーバーリファレンス](/ja/docs/server-reference)を参照してください。

## ディストリビューションの選択

ディストリビューションは、小さく実質的なインターフェース(install、join、kubeconfig、healthcheck、upgradeなど)を持つ抽象化です。

- **k3s**はデフォルトであり、唯一の組み込みディストリビューションです。Apache-2.0で、CNCF認定を受けた単一の再配置可能なバイナリであり、その組み込みのTraefikとServiceLBはどちらもRediaccプロキシに代わって無効化されています。その `--data-dir` は起動時にバインドされ、これはイメージのマウントパスが変わるクラスターフォークやマイグレーションにとってまさに必要なものです。k3sは `repoEmbeddable` としてフラグ付けされています。
- **external**は、自分のkubeconfigを持ち込む方式です。実質的な処理を行うのは `getKubeconfig` と `healthcheck` のみで、ライフサイクルの各動詞はエラーではなく第一級の「該当なし」という結果を返します。
- **RKE2**は、FIPS/CIS向け顧客のために計画されている3番目のバックエンドで、今回のリリースには含まれていません。

クラスターのフォークとマイグレーションは、`repoEmbeddable` でないディストリビューション上では、状態を壊す代わりに明確なエラーで実行を拒否します。クラスターの状態をデータストアイメージに組み込むには、起動時にバインドするdata-dirが必要だからです。

## レジストリ

2つの異なるイメージの課題に、2つのツールで対応します。

- **上流の課題**(Docker Hubのレート制限、拒否されるpull、オフライン): 埋め込みの[zot](https://zotregistry.dev/) pull-throughキャッシュがコントロールプール上で動作し、複数の上流(docker.io、ghcr.io、quay.io)に対して `sync.onDemand` を行います。他のバイナリと同じ方法でrenetに組み込まれており、opsのテストレジストリを置き換えるため、すべての実行でこれが実際に使われます。
- **クラスター内配布**: k3sの組み込みレジストリミラーにより、ノードはすでにpull済みのイメージをピアツーピアで共有できます。

配線はcontainerdの `certs.d/hosts.toml` とk3sの `registries.yaml` によって透過的かつ再起動不要です。クラスターイメージ内のリポジトリごとのcontainerdストアは、フォークとマイグレーションが使用する信頼の源泉であり続けます。レジストリはインターネットの手前にあるキャッシュにすぎず、決して状態そのものではありません。

## ネットワークとURL

Kubernetesリポジトリの URL はフラットなスキームに従い、namespaceのアイデンティティが最も左のラベルに折り込まれ、クラスターが2番目の安定したラベルになります。

```
{service}--{repo}.{cluster}.{machine}.{base}          Kubernetesリポジトリ (namespace = repo)
{service}--{repo}-{tag}.{cluster}.{machine}.{base}    フォーク (namespace = repo-tag)
```

すべてのnamespaceとすべてのフォークは親のワイルドカード証明書とDNSレコードを継承するため、フォークのURLは即座に有効になり、新しい証明書は新しいクラスターやリポジトリが作成されたときにのみ発行されます。ルーターは、`rediacc.*` アノテーション付きのServiceについてクラスターをポーリングすることでKubernetesサービスを発見します。これはDockerラベルを読み取ることのKubernetes版の類推です。ルーティングモデルについては[ネットワーキング](/ja/docs/networking)を、ストレージバックエンドについては[アーキテクチャ](/ja/docs/architecture)を参照してください。

## アトリビューション

Rediaccは複数のサードパーティバイナリ(k3s、zot、その他renetが組み込むもの)を伝達しています。バージョン、SPDXライセンス識別子、ソースアーカイブのURLはいつでも表示できます。

```bash
rdc credits
rdc credits --licenses    # リリースに同梱される THIRD_PARTY_LICENSES の全文
```
