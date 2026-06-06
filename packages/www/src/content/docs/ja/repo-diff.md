---
title: "rdc repo diff"
description: "Copy-on-Write フォーク済みリポジトリ間の、暗号化されたイメージをブロックレベルで比較し、復号化なしで git スタイルのファイルレベルの差分を表示します"
category: Reference
subcategory: advanced
order: 40
language: ja
sourceHash: "c72fbcc13e7e77ed"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# rdc repo diff

`rdc repo diff` は、2 つの関連リポジトリ間でどのファイルが変更されたかを報告します。フォークとその親リポジトリ、または Copy-on-Write の共通の祖先を持つ任意の 2 つのリポジトリ間で比較できます。`--name <fork>` を指定すると、フォークとローカル設定に記録された親リポジトリとの差分を表示します。または `--base <repo>` を追加することで、任意の関連リポジトリと比較できます。このとき `--base` がベース（古い）側、`--name` がターゲット（新しい）側になります。このコマンドは読み取り専用で、イメージを復号化することはありません。リモートマシン上でブロックレベルで比較するため、かかるコストは変更されたブロック数に追従し、リポジトリサイズには追従しません。同じ編集を加えた 1 GB のリポジトリと 100 GB のリポジトリは同じ時間で処理できます。リポジトリ全体が変更された場合、ブロック数がサイズに応じてスケールするため、コストもスケールします。

## 使う場合

`repo diff` はフォークをプロモートする前に使うべきコマンドです。AI エージェントが本番フォークの中で暴走した場合、マージ前に実際にどのファイルが変更されたかを確認したいときは、`repo diff --name <fork> -m <machine>` で数秒でファイルリストを取得できます。本当に数秒です。ディザスタリカバリからの復旧後、復元されたフォークをそれが再現すべきスナップショットと比較することで、想定されたファイルセットが復旧され、他のドリフトがないことを確認できます。親リポジトリと並行して数週間実行されていたライブフォークについては、差分はマウントして両方のツリーを手作業で確認することなく、蓄積されたダイバージェンス（設定編集、ログ蓄積、スキーママイグレーション）を表示します。

関連性のないリポジトリ間では使用しないでください。両側が Copy-on-Write の共通の祖先を共有する必要があります。これは、比較が共有ブロック履歴に基づいているためです。またこれはバイナリ差分ツールではありません。`--content` はテキストファイルのみ行レベルの出力を生成し、バイナリは `Binary files differ` と報告します。

## コマンドリファレンス

### 概要

```bash
rdc repo diff --name <fork> -m <machine>            # フォークと親の差分を表示
rdc repo diff --name <fork> --base <repo> -m <machine>   # 任意の関連リポジトリとの差分を表示
```

### オプション

| オプション | 説明 | デフォルト |
|--------|-------------|---------|
| `--name <name>` | 検査対象のリポジトリ（ターゲット、新しい側）。必須。 | 必須 |
| `--base <name>` | 比較対象のリポジトリ（ベース、古い側）。`--name` の親にデフォルト設定されており、ローカル設定から解決されます。 | `--name` の親 |
| （フォーマットフラグなし） | 名前ステータス出力：変更されたファイルごとにカラー付きの `A`/`M`/`D`/`R` 文字と 1 行のサマリー。 | オン |
| `--name-only` | 変更されたパスを 1 行に 1 つ、ステータス文字なし。パイプフレンドリー。 | オフ |
| `--stat` | ファイルごとの変更量（バイトとブロック差分）合計行付き。 | オフ |
| `--content <path>` | 単一ファイルの統一 diff テキスト。テキストのみ。バイナリは `Binary files differ` と報告します。 | オフ |
| `--json` | エージェントとスクリプト向けの構造化出力。 | オフ |
| `--fast` | コンテンツハッシュ確認ステップをスキップし、ブロックフィルタを信頼します。高速ですが、ファイルを Modified として過剰に報告する可能性があります。 | オフ |
| `-m, --machine <name>` | ターゲットマシン。必須。 | 必須 |
| `--debug` | stderr への詳細な診断情報。 | オフ |
| `--skip-router-restart` | ルータ再起動ステップをスキップします。 | オフ |

## 例

### 親に対するデフォルトの名前ステータス

`--name` のみを指定すると、フォークはローカル設定に記録された親と比較されます。ここではフォーク `test-1gb:fork1` に変更されたファイルが 1 つあります：

```bash
$ rdc repo diff --name test-1gb:fork1 -m hostinger
M  hello.txt

1 file changed: 0 added, 1 modified, 0 deleted, 0 renamed
```

### 明示的なベースに対する差分

`--base` を指定して、任意の関連リポジトリと比較します。`--base` がベース（古い）側、`--name` がターゲット（新しい）側です：

```bash
$ rdc repo diff --name test-1gb:fork1 --base test-1gb:latest -m hostinger
M  hello.txt

1 file changed: 0 added, 1 modified, 0 deleted, 0 renamed
```

### `--stat` による変更量の表示

`--stat` はファイルごとのバイト差分とブロック差分、および合計行を追加します：

```bash
$ rdc repo diff --name test-1gb:fork1 --stat -m hostinger
 hello.txt | +8 bytes, 1 block

1 file changed, 4096 bytes touched
```

### パスのみ、ツールへのパイプ

`--name-only` は 1 行に 1 パスを、ステータス文字なしで出力し、別のコマンドにフィードする準備ができています：

```bash
$ rdc repo diff --name test-1gb:fork1 --name-only -m hostinger | xargs -I{} echo "review: {}"
review: hello.txt
```

### 1 ファイルの行レベル差分

`--content` は単一のテキストファイルの統一 diff を生成します：

```bash
$ rdc repo diff --name test-1gb:fork1 --content hello.txt -m hostinger
--- a/hello.txt
+++ b/hello.txt
@@ -1 +1 @@
-the original line of text in the parent
+the original line of text in the parent, now edited
```

### jq による JSON フィルタリング

`--json` は stdout の構造化エンベロープを出力するため、`jq` にクリーンにパイプできます：

```bash
$ rdc repo diff --name test-1gb:fork1 --json -m hostinger | jq '.data.entries[] | select(.status=="M")'
{
  "status": "M",
  "path": "/hello.txt",
  "type": "file",
  "old_size": 53,
  "size": 61,
  "bytes_changed": 4096,
  "blocks_changed": 1,
  "inode": 13,
  "content_changed": true,
  "mode_changed": false,
  "uid_changed": false,
  "gid_changed": false
}
```

## 出力フォーマット

### 名前ステータス（デフォルト）

変更されたファイルごとにステータス文字とそのパスが表示されます。`A` は追加、`M` は変更、`D` は削除、`R` は名前変更（古いパス表示付き）です。サマリー行には各カテゴリの数が続きます。

### `--name-only`

1 行に 1 パス、ステータス文字なし、サマリーなし。ダウンストリームコマンドがクリーンなファイルリストを必要とする場合に使用します。

### `--stat`

各行にはファイルのバイト差分とブロック差分が記載されます。フッタは合計ファイル数と合計バイト数を報告します。これは変更がどこに重みを持つかを表示し、どのファイルが動いたかだけではなく。

### `--content <path>`

標準統一 diff（`---`/`+++` ヘッダ、`@@` ハンク）で 1 つのテキストファイル。バイナリファイルは `Binary files differ` と報告し、ハンクを生成しません。

### `--json`

完全な構造化結果。データは stdout に、進捗と診断は stderr に送信されるため、進捗が出力されている最中でも JSON は `jq` または別のパーサにクリーンにパイプできます。

## JSON スキーマ

CLI は renet の結果を標準エンベロープ（`success`、`command`、`data`、`errors`、`warnings`、`metrics`）でラップします。diff の結果は `data` に snake_case フィールドで記載されます：

```json
{
  "success": true,
  "command": "repo diff",
  "data": {
    "base": "<base-guid>",
    "target": "<target-guid>",
    "added": 0,
    "modified": 1,
    "deleted": 0,
    "renamed": 0,
    "strategy": "shared",
    "fast": false,
    "degraded": false,
    "block_size": 4096,
    "total_bytes_changed": 4096,
    "entries": [
      {
        "status": "M",
        "path": "/hello.txt",
        "type": "file",
        "old_size": 53,
        "size": 61,
        "bytes_changed": 4096,
        "blocks_changed": 1,
        "inode": 13,
        "content_changed": true,
        "mode_changed": false,
        "uid_changed": false,
        "gid_changed": false
      }
    ]
  }
}
```

`entries[]` の各オブジェクトは 1 つの変更されたパスを説明します：

| フィールド | 型 | 説明 |
|-------|------|-------------|
| `status` | `A` \| `M` \| `D` \| `R` | 追加、変更、削除、または名前変更。 |
| `path` | string | ターゲット側（削除の場合はベース側）のパス。 |
| `old_path` | string | 以前のパス。名前変更時にのみ存在します。 |
| `type` | `file` \| `dir` \| `symlink` \| `other` | エントリの種類。 |
| `old_size` | number | ベース側のサイズ（バイト）。 |
| `size` | number | ターゲット側のサイズ（バイト）。 |
| `bytes_changed` | number | 異なるバイト数。ブロク単位に四捨五入。 |
| `blocks_changed` | number | 変更されたブロック数。 |
| `inode` | number | inode 番号。名前変更検出に使用。 |
| `content_changed` | boolean | ファイルのコンテンツ（メタデータだけではなく）が変更されたかどうか。 |
| `mode_changed` | boolean | ファイルモードが変更されたかどうか。true の場合 `old_mode`/`new_mode` が存在します。 |
| `uid_changed` | boolean | 所有者が変更されたかどうか。true の場合 `old_uid`/`new_uid` が存在します。 |
| `gid_changed` | boolean | グループが変更されたかどうか。true の場合 `old_gid`/`new_gid` が存在します。 |
| `old_target` / `new_target` | string | シンボリックリンク先。変更されたシンボリックリンク用に存在します。 |

エンベロープフィールドと非 TTY 環境で JSON を出力する自動検出ルールについては、[JSON 出力リファレンス](/ja/docs/ai-agents-json-output)を参照してください。

## 仕組み

リポジトリは btrfs プール上の LUKS2 イメージファイルであり、フォークはそのイメージの定時間リフリンクです。`repo diff` は FIEMAP 経由でブロックレベルで 2 つの暗号化イメージを比較し、ファイルシステムメタデータのみを読み取り、何も復号化しません。変更されたシーファーテキストオフセットを LUKS データオフセットでシフトして ext4 デバイスオフセットを取得し、各ファイルの ext4 エクステントマップを通じてそのオフセットをファイル名にマップしバックします。両方のマウント上の inode アイデンティティウォークの最終段階は、結果を追加、変更、削除、および名前変更エントリに調整します。作業が変更されたブロック数で制限されるため、差分はリポジトリサイズから独立しており、ライブマウントをその場で再利用するため、実行中のリポジトリを妨害することはありません。完全なメカニズムは[暗号化ディスクイメージの Git diff](/ja/blog/git-diff-for-encrypted-disk-images)で説明されています。

## 制限事項

- **関連フォークのみ。** 両側が Copy-on-Write の共通の祖先を共有する必要があります。関連のないリポジトリ間には意味のあるブロックレベルの比較はありません。
- **名前変更検出は inode ベース。** ファイルは同じ inode が新しいパスに表示される場合に名前変更として報告されます。削除してから再作成（新しい inode）は、名前変更ではなく削除プラス追加エントリとして表示されます。
- **`--content` はテキストのみ。** テキストファイルの行レベルハンクを生成します。バイナリは `Binary files differ` と報告します。
- **`--fast` は Modified を過剰報告する可能性があります。** ブロックフィルタを信頼し、コンテンツハッシュ確認をスキップするため、コンテンツを変更せずにブロックが移動したファイルは Modified として表示される可能性があります。
- **エクステント ウォーク時間はサイズではなくフラグメンテーションに応じてスケール。** ファイルシステムのフラグメンテーションが多い場合、マップするエクステントが多くなり、変更のバイト量が少ない場合でも ウォークが長くなります。

## 関連項目

- [rdc repo fork](/ja/docs/repositories). このコマンドが diff する Copy-on-Write フォークを作成します。
- [rdc repo status](/ja/docs/repositories). 単一のリポジトリの現在の状態。
- [rdc repo cat](/ja/docs/repositories). リポジトリから単一ファイルを読み取ります。
