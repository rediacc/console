---
title: Cursor セットアップガイド
description: .cursorrules とターミナル統合を使用して、Cursor IDEをRediaccインフラストラクチャと連携させる設定方法。
category: Guides
order: 32
language: ja
sourceHash: "6da857eb870d511e"
---

Cursorはターミナルコマンドと `.cursorrules` 設定ファイルを通じてRediaccと統合します。

## クイックセットアップ

1. CLIをインストール: `curl -fsSL https://www.rediacc.com/install.sh | bash`
2. [AGENTS.md テンプレート](/ja/docs/agents-md-template)をプロジェクトルートに `.cursorrules` としてコピー
3. プロジェクトをCursorで開く

Cursorは起動時に `.cursorrules` を読み込み、AI支援開発のコンテキストとして使用します。

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
rdc machine info prod-1 -o json
```

### 変更のデプロイ

Cursorに聞く: *「更新されたnextcloudの設定をデプロイして」*

Cursorがターミナルで実行:
```bash
rdc repo up nextcloud -m prod-1 --yes
```

### ログの表示

Cursorに聞く: *「最近のメールコンテナのログを見せて」*

Cursorがターミナルで実行:
```bash
rdc term prod-1 mail -c "docker logs mail-postfix --tail 100"
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
