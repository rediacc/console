---
title: Cursor セットアップガイド
description: .cursorrules とターミナル統合を使用して、Cursor IDE を Rediacc インフラストラクチャと連携させる設定方法。
category: Guides
order: 32
language: ja
sourceHash: "b5e835461de00400"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

手短に言うと: `.cursorrules` が Rediacc のコンテキストを Cursor の AI に読み込ませ、ターミナルが実際のマシンに対して `rdc` コマンドを実行できるようにします。

## クイックセットアップ

1. CLIをインストール: `curl -fsSL https://www.rediacc.com/install.sh | bash`
2. [AGENTS.md テンプレート](/ja/docs/agents-md-template)をプロジェクトルートに `.cursorrules` としてコピー
3. プロジェクトをCursorで開く

Cursor は起動時に `.cursorrules` を読み込みます。ポイントは、コンテキストウィンドウには上限があるため、汎用的な定型文ではなく、実際に使用するマシンやリポジトリに絞った内容にしておくことです。

## .cursorrules の設定

プロジェクトルートにRediaccインフラストラクチャのコンテキストを含む `.cursorrules` を作成してください。完全版は [AGENTS.md テンプレート](/ja/docs/agents-md-template) を参照してください。

含めるべき主要なセクション:

- CLIツール名（`rdc`）とインストール方法
- `--output json` フラグ付きの一般的なコマンド
- アーキテクチャ概要（リポジトリの分離、Docker デーモン）
- 用語ルール（モードではなくアダプター）

## ターミナル統合

Cursorは統合ターミナルを通じて `rdc` コマンドを実行できます。一般的なパターン:

### ステータスの確認

Cursorに聞く: *「本番サーバーのステータスを確認して」*

Cursorがターミナルで実行:
```bash
rdc machine query --name prod-1 -o json
```

### 変更のデプロイ

Cursorに聞く: *「更新されたnextcloudの設定をデプロイして」*

Cursorがターミナルで実行:
```bash
rdc repo up --name nextcloud -m prod-1 --yes
```

### ログの表示

Cursorに聞く: *「最近のメールコンテナのログを見せて」*

Cursorがターミナルで実行:
```bash
rdc term connect -m prod-1 -r mail -c "docker logs mail-postfix --tail 100"
```

## ワークスペース設定

チームプロジェクトの場合、Rediacc固有のCursor設定を `.cursor/settings.json` に追加してください:

```json
{
  "terminal.defaultProfile": "bash",
  "ai.customInstructions": "Use rdc CLI for all infrastructure operations. Always use --output json when parsing results."
}
```

## ヒント

- CursorのComposerモードは複数ステップのインフラストラクチャタスクに適しています
- Cursorチャットで `@terminal` を使用すると、最近のターミナル出力を参照できます
- `rdc agent capabilities` コマンドでCursorに完全なコマンドリファレンスを提供できます
- `.cursorrules` と `CLAUDE.md` ファイルを組み合わせると、AIツール間の互換性が最大化されます
