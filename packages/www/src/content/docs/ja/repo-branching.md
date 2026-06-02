---
title: "Gitライクなブランチ管理"
description: "コピーオンライトフォークをgitコミットとして扱う：フォークをイミュータブルなコミットとして凍結し、ブランチに名前を付け、コミットを書き込み可能なフォークにチェックアウトし、履歴を確認し、実行中のリポジトリを変更することなくマージする。"
category: Reference
subcategory: advanced
order: 41
language: ja
sourceHash: "6ca18986dfd6e237"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

# Gitライクなブランチ管理

Rediaccリポジトリは、コピーオンライトフォークを基盤とするgitライクなバージョニングをサポートしています。各イミュータブルフォークは**コミット**です。バイト単位で安定した、マウントを拒否する凍結イメージです。ブランチはコミットを指す名前付きrefです。`rdc repo checkout`はコミットをリファリンクで書き込み可能なワーキングフォークにクローンし、`rdc repo merge`は実行中のリポジトリをその場で変更することなく2つの履歴ラインを結合します。

このモデルは2つのストアに対応しています。**マシンはオブジェクトストア**：コミットはデータストア上に存在するイミュータブルなフォークイメージです。**CLIコンフィグはrefストア**：ブランチ名、現在の`HEAD`、reflogはマシンではなくローカルコンフィグに存在します。これはgitが`.git/objects`と`.git/refs`の間で使用するのと同じ分割です。

## 使用する場面

フォークに名前を付ける価値が生まれたときにブランチを使用してください。AIエージェントが本番のフォークで動作し、結果が良好で、後で戻るかプロモートできる凍結された名前付きチェックポイントが欲しい場合：`rdc repo commit`で凍結し、`rdc repo branch`で名前を付けます。リスクのある移行の前に、ワーキングフォークをコミットして、絶対に変更されない正確なロールバックポイントを確保します（イミュータブルコミットはマウントを拒否するため、何も書き込めません）。2つのチェックポイントを比較するには、`rdc repo diff`がコピーオンライトの共通祖先を共有する任意の2つのコミット間で動作します。レビュー済みの作業ラインをターゲットフォークに戻すには、`rdc repo merge`がリファリンクのクローンで結果を構築してアトミックに入れ替えるため、実行中のターゲットがマージ中に破損することはありません。

`rdc repo fork`の代替として使い捨てのコピーだけが必要な場合には使わないでください。プレーンフォークは一時的なテスト単位として適切な単位です。コミットは、状態を保持、命名、またはリリースする価値があるときに有効です。

## コミットとフォークの関係

リポジトリはbtrfsプール上の1つのLUKSイメージファイルです。フォークはそのイメージの定数時間リファリンクであるため、1 GBのリポジトリと100 GBのリポジトリのフォークにかかるコストは同じです。**コミット**はイミュータブルとしてマークされたフォークです。renetはマウントを拒否し、イメージを永久にバイト安定した状態に保ちます。このバイト安定性が、コミットを信頼性の高いロールバックポイントおよびクロスマシンデルタプッシュの決定論的なベースにする理由です。

`rdc repo commit`はコミットメッセージ、作成者、タイムスタンプ、および親コミットをボリューム**内**（メタデータがプッシュ時にイメージと一緒に移動するよう）に記録し、ボリューム外にもミラーします（`rdc repo log`が何もアンロックせずに履歴を確認できるよう）。コミットしたワーキングフォークは変更されずそのまま維持されます。gitがコミット後にワーキングツリーをそのままにするのと同様です。

## コマンド

### rdc repo commit

マウントされたワーキングフォークを新しいイミュータブルコミットに凍結します。

```bash
rdc repo commit --name <fork> --message "<message>" -m <machine>
```

| オプション | 説明 | デフォルト |
|--------|-------------|---------|
| `--name <name>` | コミットするワーキングフォーク。マウントされている必要があります。必須。 | required |
| `--message <msg>` | コミットメッセージ。必須。 | required |
| `--author <author>` | コミットメタデータに記録されるコミット作成者。 | unset |
| `-m, --machine <name>` | ターゲットマシン。必須。 | required |
| `--debug` | stderrへの詳細な診断情報。 | off |

新しいコミットはローカルコンフィグに`immutable: true`として登録され、ワーキングフォークの`headCommit`がそれを指すように更新されます。イミュータブルなリポジトリのコミットは拒否されます。まず書き込み可能なフォークにチェックアウトしてください。

### rdc repo branch

ワーキングフォークの現在のコミットを指す名前付きブランチrefを作成します。

```bash
rdc repo branch --branch <name> --name <fork>
```

| オプション | 説明 | デフォルト |
|--------|-------------|---------|
| `--branch <branch>` | 新しいブランチの名前。必須。 | required |
| `--name <name>` | ブランチが指すワーキングフォーク。必須。 | required |

これはコンフィグのみの操作です。マシンでは何も実行されません。ブランチrefは名前をワーキングフォークの`headCommit`にマッピングするため、フォークには少なくとも1つのコミットが必要です。

### rdc repo checkout

イミュータブルコミット（またはブランチの先端）をリファリンクで新しい書き込み可能なワーキングフォークにクローンします。

```bash
rdc repo checkout --ref <commit> --tag <newFork> -m <machine>
rdc repo checkout --ref <branchName> --from <fork> --tag <newFork> -m <machine>
```

| オプション | 説明 | デフォルト |
|--------|-------------|---------|
| `--ref <commit\|branch>` | チェックアウトするコミットGUID、または`--from`が指定された場合のブランチ名。必須。 | required |
| `--tag <name>` | 新しい書き込み可能なワーキングフォークの名前。必須。 | required |
| `-m, --machine <name>` | ターゲットマシン。必須。 | required |
| `--from <workingFork>` | このワーキングフォークのブランチセットで`--ref`をブランチ名として解決します。 | direct commit |
| `--debug` | stderrへの詳細な診断情報。 | off |
| `--skip-router-restart` | ルーター再起動ステップをスキップします。 | off |

チェックアウトはフォークリファリンクパスを再利用するため、リポジトリサイズに関わらずほぼ瞬時で定数時間です。新しいワーキングフォークの`headCommit`はチェックアウトされたコミットに設定されます。

### rdc repo log

ワーキングフォークまたはコミットから到達可能なコミット履歴を確認します。

```bash
rdc repo log --name <fork> -m <machine>
```

| オプション | 説明 | デフォルト |
|--------|-------------|---------|
| `--name <name>` | 履歴確認を開始するワーキングフォークまたはコミット。必須。 | required |
| `-m, --machine <name>` | ターゲットマシン。必須。 | required |
| `--json` | コミット履歴をJSONとして出力します。 | off |
| `--debug` | stderrへの詳細な診断情報。 | off |

`log`は`rdc repo commit`によって記録された親チェーンを確認し、ボリューム外の状態ミラーを読み取るため、コミットはアンロックまたはマウントされません。読み取り専用です。

### rdc repo merge

ライブターゲットをその場で変更することなく、ソースコミットまたはフォークをターゲットワーキングフォークにマージします。

```bash
rdc repo merge --name <target> --from <source> -m <machine>
rdc repo merge --name <target> --from <source> --resolve theirs -m <machine>
```

| オプション | 説明 | デフォルト |
|--------|-------------|---------|
| `--name <name>` | マージ先のターゲットワーキングフォーク。必須。 | required |
| `--from <source>` | マージ元のソースコミットまたはフォーク。必須。 | required |
| `-m, --machine <name>` | ターゲットマシン。必須。 | required |
| `--force` | まずマウントまたは実行中のターゲットを停止してからマージします。ライブマウントを変更することはありません。 | off |
| `--resolve <ours\|theirs>` | ファイル単位の3方向マージ：ソースのファイル単位の変更をターゲットに適用し、両側で変更されたファイルにはソース版を保持（`ours`）または採用（`theirs`）します。全体イメージの取り込みには省略します。 | off |
| `--base <guid>` | 3方向マージの共通祖先コミット（`--resolve`と共に使用）。デフォルトはソースコミットの親、またはターゲットの現在のコミット。 | auto |
| `--debug` | stderrへの詳細な診断情報。 | off |

結果はリファリンクのクローンで構築され、クラッシュセーフなマーカーの背後でアトミックに入れ替えられるため、マージが中断されてもオリジナルのターゲットは無傷のままです。マウントまたは実行中のターゲットは`--force`なしでは拒否されます。`--force`はターゲットを入れ替え前にクリーンにシャットダウンします。

`--resolve`なしでは、マージは全体イメージの取り込み（ターゲットがソースになります）です。`--resolve`ありでは、ソースコミットの記録された親に対するファイル単位の3方向マージです。一方のみで変更されたファイルはその側から取得され、両側で変更されたファイルはフラグで解決されます。競合するパスが報告されます。

### rdc repo gc

マシン上のブランチまたはHEADから到達できないイミュータブルコミットオブジェクトをガベージコレクションします。

```bash
rdc repo gc -m <machine>            # ドライランプレビュー（デフォルト）
rdc repo gc --apply -m <machine>    # 到達不能なコミットを削除
```

| オプション | 説明 | デフォルト |
|--------|-------------|---------|
| `-m, --machine <name>` | コレクションするマシン。必須。 | required |
| `--apply` | 到達不能なコミットを実際に削除します（省略した場合はドライランプレビュー）。 | off |
| `--debug` | stderrへの詳細な診断情報。 | off |

到達可能性はローカルコンフィグ（refストア）から計算されます。各ブランチの先端とHEADを親チェーンをたどって到達可能なコミットのセットです。そのセット外のマシン上のイミュータブルコミットは到達不能です。マウントされたオブジェクトやワーキングフォークは収集されません。

### rdc repo fsck

マシン上に存在するオブジェクトに対してコンフィグのrefを検証します。

```bash
rdc repo fsck -m <machine>
```

| オプション | 説明 | デフォルト |
|--------|-------------|---------|
| `-m, --machine <name>` | チェックするマシン。必須。 | required |

ダングリングref（マシン上にオブジェクトのないGUIDを指すブランチの先端またはHEAD）と孤立コミット（どのrefにも到達されないマシン上のイミュータブルコミット）を報告します。読み取り専用です。孤立したものは`rdc repo gc --apply`で回収してください。

### イミュータブルフォーク

`rdc repo fork --immutable`は、新しいフォークを作成時に読み取り専用としてマークし、別の`commit`ステップなしにコミット相当のベースを生成します。

```bash
rdc repo fork --parent <name> --tag <tag> --immutable -m <machine>
```

イミュータブルフォークはマウントを拒否し、イメージを永久にバイト安定した状態に保ちます。これはクロスマシンデルタプッシュのための凍結ベースとして有用です。ベースは両端で同一である必要があります。変更を加えるには、書き込み可能なコピーにチェックアウト（または再フォーク）してください。

## 例

### ワーキングフォークをコミットする

```bash
$ rdc repo commit --name myapp:work --message "schema migration applied" -m server-1
Committed 4f3c2a1b9d8e: schema migration applied
```

### 明示的な作成者でコミットする

```bash
$ rdc repo commit --name myapp:work --message "nightly snapshot" --author ci-bot -m server-1
Committed 7a1b2c3d4e5f: nightly snapshot
```

### 現在のコミットにブランチ名を付ける

```bash
$ rdc repo branch --branch staging --name myapp:work
Branch "staging" -> 4f3c2a1b9d8e
```

### コミットを新しい書き込み可能なフォークにチェックアウトする

```bash
$ rdc repo checkout --ref 4f3c2a1b9d8e --tag rollback-test -m server-1
```

### ブランチの先端を名前でチェックアウトする

`--from`を使用すると、`--ref`の値は指定されたワーキングフォークのブランチ名として解決されます：

```bash
$ rdc repo checkout --ref staging --from myapp:work --tag staging-copy -m server-1
```

### 履歴を確認する

```bash
$ rdc repo log --name myapp:work -m server-1
commit 4f3c2a1b9d8e
  Author: ci-bot  Date: 2026-05-29T10:14:02Z
  schema migration applied
commit 9d8e7a1b2c3d
  Author: ci-bot  Date: 2026-05-28T22:01:55Z
  initial import
```

### JSONとして履歴を確認する

`--json`は構造化されたウォークを新しい順に出力します：

```bash
$ rdc repo log --name myapp:work --json -m server-1
{
  "success": true,
  "start": "4f3c2a1b9d8e",
  "entries": [
    {
      "guid": "4f3c2a1b9d8e",
      "message": "schema migration applied",
      "author": "ci-bot",
      "parent": "9d8e7a1b2c3d",
      "committed_at": "2026-05-29T10:14:02Z",
      "immutable": true
    }
  ]
}
```

### 2つのコミットをdiffする

`rdc repo diff`はコピーオンライトの共通祖先を共有するため、任意の2つのコミット間で動作します。1つのコミットをチェックアウトし、別のコミットとdiffします：

```bash
$ rdc repo checkout --ref 4f3c2a1b9d8e --tag review -m server-1
$ rdc repo diff --name review --base myapp:work -m server-1
M  db/schema.sql

1 file changed: 0 added, 1 modified, 0 deleted, 0 renamed
```

完全なdiffリファレンスは[rdc repo diff](/ja/docs/repo-diff)を参照してください。

### レビュー済みのラインをマージして戻す

```bash
$ rdc repo merge --name myapp:main --from myapp:work -m server-1
Merged myapp:work into myapp:main
```

### 実行中のターゲットにマージする

マウントまたは実行中のターゲットは`--force`なしでは拒否されます。`--force`は先にターゲットを停止します：

```bash
$ rdc repo merge --name myapp:main --from myapp:work --force -m server-1
Merged myapp:work into myapp:main
```

### ファイル単位の3方向マージ

同じコミットからチェックアウトした2つのフォーク（`feature`と`hotfix`）がそれぞれいくつかのファイルを変更しました。`--resolve theirs`はソース（`hotfix`）をターゲット（`feature`）に適用します。一方のみで変更されたファイルはその側から取得され、両側で変更されたファイルはソースに解決されます。ベースは共通祖先から自動検出されます（または`--base`で固定します）：

```bash
$ rdc repo merge --name myapp:feature --from myapp:hotfix --resolve theirs -m server-1
Merged myapp:hotfix into myapp:feature (three-way); 1 conflict(s) resolved --theirs: [config/app.yaml]
```

`config/app.yaml`は両側で変更されており、ソースに解決されました。`hotfix`のみが追加したファイルは適用され、`feature`のみが変更したファイルは保持されます。競合パスが報告されるため、レビューできます。

### イミュータブルベースを直接作成する

```bash
$ rdc repo fork --parent myapp --tag baseline-v1 --immutable -m server-1
```

## デルタプッシュとプル

イミュータブルでバイト安定なイメージは、**ブロックレベルのデルタ転送**の基盤でもあります。同じイミュータブルベースが2つのマシンに存在する場合、プッシュまたはプルはそのベースに対して変更されたブロックを計算し、暗号化されたイメージ全体をスキャンする代わりにそれだけを転送できます。変更されたブロックが少ない1 GBのリポジトリはメガバイト単位で転送されます。

通常、ベースを手動で指定する必要はありません。フルプッシュ後、CLIは両マシンにプッシュされたイメージをイミュータブルベースとして保持して記録するため、**次の**プッシュは自動的にデルタのみを送信します。フラグなしで、対象マシンに既に存在するフォークでも同様です。（既存フォークの*フル*再プッシュには`--force`が必要です。デルタを適用するのではなくイメージ全体を置き換えるためです。）特定のベースを固定するには`--delta-base <guid>`を使用し、変更されたブロックの検出方法を制御するには`--strategy <auto|physical|shared>`を使用します（`auto`はほぼすべてのケースで正しい選択です）。

```bash
# 最初のプッシュはフル転送で、両端に再利用可能なベースを保持します。
$ rdc repo push --name myapp:work --to-machine backup-1 -m server-1

# ローカルで変更した後、次のプッシュは変更されたブロックのみを送信します。フラグ不要。
$ rdc repo push --name myapp:work --to-machine backup-1 -m server-1

# 明示的なベースを固定します（両マシンに存在するイミュータブルコミット）。
$ rdc repo push --name myapp:work --to-machine backup-1 --delta-base 4f3c2a1b9d8e -m server-1

# デルタはマシンソースからの逆方向（プル）でも動作します。
$ rdc repo pull --name myapp:work --from-machine backup-1 --delta-base 4f3c2a1b9d8e -m server-1

# --forceで既存のローカルリポジトリを（上書きして）再プルします。
$ rdc repo pull --name myapp:work --from-machine backup-1 --force -m server-1
```

デルタ転送はマシン間（FIEMAPベースを持つリモート）にのみ適用されます。クラウドオブジェクトストレージへのプッシュは常にフルイメージを転送します。ベースは両端でバイト同一である必要があります。イミュータブルコミットまたは`--immutable`フォークが保証するのがまさにこれです。

## JSONスキーマ

`rdc repo log --json`はrenetの結果を標準エンベロープでラップします。確認された履歴は`entries`に新しい順で格納されます：

| フィールド | 型 | 説明 |
|-------|------|-------------|
| `success` | boolean | ウォークが完了したかどうか。 |
| `start` | string | ウォークを開始したGUID。 |
| `entries` | array | コミットごとに1つのオブジェクト、新しい順。 |
| `entries[].guid` | string | コミットGUID。 |
| `entries[].message` | string | コミットメッセージ。空の場合は省略。 |
| `entries[].author` | string | コミット作成者。空の場合は省略。 |
| `entries[].parent` | string | 親コミットGUID。ルートでは省略。 |
| `entries[].committed_at` | string | RFC 3339コミットタイムスタンプ。未設定の場合は省略。 |
| `entries[].immutable` | boolean | コミットが読み取り専用としてマークされているかどうか（実際のコミットでは常にtrue）。 |

エンベロープフィールドと非TTY環境でJSONを出力する自動検出ルールについては、[JSON出力リファレンス](/ja/docs/ai-agents-json-output)を参照してください。

## 制限事項

- **refはローカルです。** ブランチ名、`HEAD`、reflogはマシンではなくCLIコンフィグに存在します。コミットを別のマシンにプッシュすると、コミットオブジェクトとそのボリューム内メタデータが送信されますが、ブランチrefはコンフィグ側の概念です。
- **コミットはマウントを拒否します。** それが目的です。イミュータビリティがコミットをバイト安定にします。コミットを実行または編集するには、まず書き込み可能なワーキングフォークにチェックアウトしてください。
- **マージ解決はファイルレベルであり、行レベルではありません。** 全体イメージの取り込み（`--resolve`なし）とファイル単位の3方向マージ（`--resolve ours|theirs`）の両方がサポートされています。3方向マージはフラグに従ってファイル全体単位で競合を解決します。ファイル内の行レベルのhunkやマージマーカーは生成されません。
- **履歴は親チェーンです。** `rdc repo log`はコミット時に記録された単一の`parent`リンクをたどります。クエリされたマシンにメタデータが存在しないコミットに到達すると停止します。

## 関連項目

- [rdc repo diff](/ja/docs/repo-diff). 関連する任意の2つのコミットまたはフォーク間のファイルレベルのdiff。
- [リポジトリ](/ja/docs/repositories). リポジトリの作成、フォーク、マウント、操作。
