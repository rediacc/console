---
title: "Config Storage (Rediacc Provider)"
description: "ゼロ知識暗号化により、デバイス間やチーム間でCLI設定を安全に同期します。"
category: "Guides"
order: 9
language: ja
sourceHash: "459f12eb33547c13"
sourceCommit: "12bf0959ad816cdab93fb6410a22e4694d1a7635"
---

# Config Storage

Rediacc Config Storageプロバイダーは、ゼロ知識暗号化によりデバイス間やチーム間でCLI設定を同期します。SSHキー、マシンIP、認証情報はマシンを離れる前にクライアント側で暗号化されます -- Rediaccの運営者でさえデータを読むことはできません。

## 前提条件

- **PRFサポート付きのパスキープロバイダー**: Bitwarden、iCloud KeychainまたはWindows Hello
- **2FAが有効** 組織のオーナー/管理者向け（ストアの設定とメンバー管理に必要）
- **アカウントサブスクリプション** config storageが有効であること

## クイックスタート

```bash
# Set up config storage (opens browser for passkey registration)
rdc store add my-config --type rediacc

# Push your current config to the server
rdc store push --store my-config

# Pull config on another device (after setup)
rdc store pull --store my-config

# Sync (pull newer, then push)
rdc store sync --store my-config
```

## セットアップ

### デスクトップ（ブラウザあり）

```bash
rdc store add my-config --type rediacc
```

1. ブラウザウィンドウがRediaccアカウントポータルに開きます
2. パスキーを登録します（Bitwarden/iCloud/Windows Helloのポップアップ）
3. パスキーのPRF拡張が暗号化キーを導出します
4. キーはOSネイティブのセキュアストレージに保存されます（Keychain/keyctl/DPAPI）
5. 完了 -- 覚えるパスワードはありません

### ヘッドレスサーバー（ブラウザなし）

```bash
rdc store add my-config --type rediacc --headless
```

1. CLIがデバイスコード付きのURLを表示します
2. スマートフォンまたはノートPCでそのURLを開きます
3. ブラウザでパスキー登録を完了します
4. CLIがセキュアリレー経由で暗号化キーを自動的に受信します
5. ゼロ知識が保持されます -- サーバーは不透明な暗号化blobをリレーするだけです

### カスタムサーバーURL

```bash
rdc store add my-config --type rediacc --server-url https://account.yourcompany.com
```

## Push & Pull

セットアップ後、pushとpullはパスワードやプロンプトなしで動作します：

```bash
# Push current config
rdc store push --store my-config

# Pull from server
rdc store pull --store my-config

# Sync all configured stores
rdc store sync --all

# List configured stores
rdc store list
```

各操作は1回使用後に自己破壊するローテーショントークンを使用します。静的な認証情報はありません。

## チーム管理

チームメンバーは`/account/config-storage/members`のWebポータルで管理されます。

### メンバーの追加

1. 管理者がconfig storageメンバーページを開きます
2. "Add Member"をクリックします（2FAが必要）
3. 管理者のブラウザが新しいメンバー用にチーム暗号化キーを暗号化します
4. 新しいメンバーがログインして招待を受け入れます
5. 両者が同じ設定をpush/pullできるようになります

### メンバーの削除

1. 管理者がメンバーの横の"Remove"をクリックします（2FAが必要）
2. メンバーの暗号化キーが即座に削除されます
3. 30秒以内に、メンバーは暗号化された設定へのすべてのアクセスを失います

キーローテーションは不要です -- サーバーは削除されたメンバーへの復号キーの提供を単に停止します。

## セキュリティ特性

| 特性 | 方法 |
|------|------|
| **ゼロ知識** | クライアントが送信前に暗号化；サーバーは不透明なblobのみを参照 |
| **マスターパスワード不要** | パスキーの生体認証がパスワードを完全に置き換え |
| **分割キー導出** | CEKにはpasskey_secret（クライアント）+ server_secret（サーバー）の両方が必要 |
| **ローテーショントークン** | 各APIコールが新しいトークンを生成；古いものは無効化 |
| **IPバインディング** | トークンは初回使用時にクライアントIPにバインド |
| **三重暗号化** | SDK（時間制限付き）+ CEK（クライアント）+ 組織パスフレーズ（サーバー） |
| **即時失効** | 削除されたメンバーへのSDK提供を停止；最大30秒の遅延 |
| **改ざん検出** | 暗号化blob上のHMAC；毎回のpullで検証 |

完全なセキュリティアーキテクチャについては、[Security Guide](/docs/SECURITY-CONFIG-STORAGE.md)を参照してください。

## トラブルシューティング

### "Passkey must support PRF extension"

パスキープロバイダーがPRF拡張をサポートしていません。以下を使用してください：
- Bitwarden（デスクトップアプリまたはブラウザ拡張機能）
- iCloud Keychain（macOS/iOSのSafari）
- Windows Hello

### "Two-factor authentication required"

組織のオーナーと管理者はconfig storageを設定する前に2FAを有効にする必要があります。Account Settings -> Security -> Enable 2FAに進んでください。

### "Version conflict"

別のチームメンバーがより新しいバージョンをプッシュしました。まずプルしてください：
```bash
rdc store pull --store my-config
# Resolve any conflicts
rdc store push --store my-config
```

### "Config token expired"

トークンは24時間の非アクティブ後に期限切れになります。任意のコマンドを実行して更新してください：
```bash
rdc store sync --store my-config
```

### "passkey_secret not found in secure storage"

暗号化キーがOSのセキュアストレージから失われました（Linuxでの再起動、キーチェーンのリセット）。セットアップを再実行してください：
```bash
rdc store add my-config --type rediacc
```
