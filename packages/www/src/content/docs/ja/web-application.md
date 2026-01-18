---
title: Webアプリケーション
description: Rediaccを使用したWebアプリケーションのアーキテクチャと展開について理解する
category: コアコンセプト
order: 1
language: ja
---

# Rediacc プラットフォーム ユーザーガイド

## 概要

**Rediacc**は、AI搭載のバックアップサービスを提供するクラウドプラットフォームです。

このガイドでは、[https://www.rediacc.com/](https://www.rediacc.com/)のWebインターフェースの基本的な使用方法を説明します。

### このガイドの目的

- 新規ユーザーがプラットフォームに素早く適応できるようにする
- 基本機能(リソース管理、バックアップ)をステップバイステップで説明する

---

## 1. アカウント作成とログイン

### 1.1 登録

Rediaccプラットフォームの使用を開始するには、まずアカウントを作成する必要があります。

![Rediaccログインページ - 常時稼働インフラストラクチャ](/assets/images/UserGuideEng/01_login.png)
*(図1: メインログインページ。Rediaccプラットフォームの主な機能を表示)*

1. ブラウザで[https://www.rediacc.com/](https://www.rediacc.com/)にアクセスします。
2. ページの右上にある**{{t:auth.login.signIn}}**ボタンをクリックします。
3. 無料アクセスには**Get Started**を、デモンストレーションには**Request Demo**を選択します。

> **ヒント**: クレジットカード不要で無料アカウントを作成できます。10個のCPUコアと無制限のチームが含まれます。

![Rediacc サインインフォーム - メールとパスワードフィールド](/assets/images/UserGuideEng/02_register.png)
*(図2: 既存ユーザー向けのサインイン画面)*

4. アカウントをお持ちでない場合は、**{{t:auth.login.register}}**リンクをクリックして新しいアカウントを作成します。

5. 開いたフォームに以下の情報を入力します:
   - **{{t:auth.registration.organizationName}}**: 組織名を入力
   - **{{t:auth.login.email}}**: 有効なメールアドレスを入力
   - **{{t:auth.login.password}}**: 8文字以上のパスワードを作成
   - **{{t:auth.registration.passwordConfirm}}**: 同じパスワードを再入力

![アカウント作成モーダル - 登録、検証、完了ステップ](/assets/images/UserGuideEng/03_create_account.png)
*(図3: 新規ユーザー登録のステップバイステップフォーム - 登録 > 検証 > 完了)*

6. 利用規約とプライバシーポリシーに同意するチェックボックスをオンにします。
7. **{{t:auth.registration.createAccount}}**ボタンをクリックします。

> **ヒント**: パスワードは8文字以上で、強力なものにする必要があります。すべてのフィールドは必須です。

8. メールに送信された6桁の認証コードを順番にボックスに入力します。
9. **{{t:auth.registration.verifyAccount}}**ボタンをクリックします。

![認証コード入力 - 6桁のアクティベーションコード](/assets/images/UserGuideEng/04_verification_code.png)
*(図4: 管理者に送信されたアクティベーションコードを入力するウィンドウ)*

> **ヒント**: 認証コードの有効期限は限られています。コードが届かない場合は、迷惑メールフォルダを確認してください。

---

### 1.2 サインイン

アカウントが作成されたら、プラットフォームにログインできます。

1. **{{t:auth.login.email}}**フィールドを入力します(赤い警告が表示される場合は必須)。
2. **{{t:auth.login.password}}**フィールドを入力します。
3. **{{t:auth.login.signIn}}**ボタンをクリックします。

![サインインフォーム - エラー警告付き必須フィールド](/assets/images/UserGuideEng/05_sign_in.png)
*(図5: ログインフォーム - エラーメッセージは赤い枠で示されます)*

> **ヒント**: エラーメッセージに「このフィールドは必須です」と表示される場合は、空のフィールドを入力してください。パスワードを忘れた場合は管理者に連絡してください。

4. ログインに成功すると、**{{t:common.navigation.dashboard}}**画面にリダイレクトされます。

![Rediacc ダッシュボード - マシンリストとサイドバーメニュー](/assets/images/UserGuideEng/06_dashboard.png)
*(図6: ログイン成功後のメインダッシュボード - 左サイドバーに組織、マシン、設定メニュー)*

> **ヒント**: ダッシュボードは自動更新されます。F5キーでページを更新して最新情報を取得できます。

---

## 2. インターフェース概要

ログイン後に表示される画面は、以下の主要セクションで構成されています:

- **{{t:common.navigation.organization}}**: ユーザー、チーム、アクセス制御
- **{{t:common.navigation.machines}}**: サーバーとリポジトリの管理
- **{{t:common.navigation.settings}}**: プロフィールとシステム設定
- **{{t:common.navigation.storage}}**: ストレージエリア管理
- **{{t:common.navigation.credentials}}**: アクセス認証情報
- **{{t:common.navigation.queue}}**: ジョブキュー管理
- **{{t:common.navigation.audit}}**: システム監査ログ

---

## 2.1 組織 - ユーザー

ユーザー管理では、組織内の人々に対するプラットフォームへのアクセスを制御できます。

### 2.1.1 ユーザーの追加

1. 左サイドバーの**{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationUsers}}**オプションをクリックします。
2. すべてのユーザーのリストをテーブル形式で表示します。
3. 各ユーザー行には、メール、ステータス（{{t:organization.users.status.active}}/{{t:organization.users.status.inactive}}）、権限グループ、最終アクティビティ時刻が表示されます。

![ユーザー管理ページ - アクティブユーザーリスト](/assets/images/UserGuideEng/07_users.png)
*(図7: 組織配下のユーザーセクション - すべてのユーザーの情報が表示されます)*

4. 右上の**「+」**アイコンをクリックします。
5. **{{t:organization.users.modals.createTitle}}**ボタンをクリックし、開いたフォームに入力します:
   - **{{t:organization.users.form.emailLabel}}**: ユーザーのメールアドレスを入力
   - **{{t:organization.users.form.passwordLabel}}**: 一時パスワードを入力

![ユーザー作成モーダル - メールとパスワードフィールド](/assets/images/UserGuideEng/08_user_add.png)
*(図8: 新規ユーザー追加用のモーダルウィンドウ - シンプルで迅速なユーザー作成フォーム)*

6. **{{t:common.actions.create}}**ボタンをクリックします。

> **ヒント**: ログイン認証情報は、作成されたユーザーに安全に伝える必要があります。初回ログイン時にパスワードを変更することをお勧めします。

![ユーザーリスト - 3人のユーザーを含む完全なテーブルビュー](/assets/images/UserGuideEng/09_user_list.png)
*(図9: ユーザー管理ページのすべてのアクティブおよび非アクティブユーザー)*

> **ヒント**: ページには自動的に20件のレコードが表示されます。ページネーションを使用してさらに多くのレコードを表示できます。

### 2.1.2 ユーザー権限の割り当て

特定の権限グループをユーザーに割り当てることで、アクセス権を管理できます。

1. **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationUsers}}**タブからユーザーを選択します。
2. アクション列のシールドアイコン(**Permissions**)をクリックします。

![権限管理 - シールド、ギア、削除アイコン](/assets/images/UserGuideEng/10_users_permissions.png)
*(図10: ユーザーアクションのアイコン表示 - 各アイコンは異なるアクションを表します)*

3. 開いたフォームから**{{t:organization.users.modals.permissionGroupLabel}}**を選択します。
4. グループ内のユーザー数と権限数がユーザーの横に表示されます。
5. **{{t:organization.users.modals.assignTitle}}**ボタンをクリックして変更を保存します。

![権限割り当てモーダル - 管理者グループ](/assets/images/UserGuideEng/11_user_permissions_form.png)
*(図11: 選択したユーザーに権限グループを割り当てるモーダル - 利用可能なグループのドロップダウン)*

> **ヒント**: 一部の権限グループはシステムによって固定されており、変更できません。

### 2.1.3 ユーザーのアクティベーション

無効化されたユーザーを再アクティベートできます。

1. **ユーザー**リストで非アクティブステータスのユーザーを見つけます。
2. アクション列の赤いアイコンをクリックします。

![ユーザーアクティベーション - 「アクティベート」ツールチップビュー](/assets/images/UserGuideEng/12_users_activation.png)
*(図12: 非アクティブユーザーのアクティベート)*

3. 確認ウィンドウで**{{t:common.general.yes}}**ボタンをクリックします。

![アクティベーション確認モーダル](/assets/images/UserGuideEng/13_users_activation_confirm.png)
*(図13: ユーザーアクティベーションを確認するモーダルウィンドウ)*

> **ヒント**: このアクションは可逆的です。同じ方法でユーザーを無効化できます。

### 2.1.4 ユーザートレース

トレース機能を使用して、ユーザーのアクティビティを監視できます。

1. ユーザーを選択し、アクション列のギアアイコンをクリックします。
2. **{{t:common.actions.trace}}**オプションをクリックして、ユーザーのアクティビティ履歴を開きます。

![ユーザートレース - アクションボタン付き「トレース」ツールチップ](/assets/images/UserGuideEng/14_users_trace.png)
*(図14: ユーザーアクティビティトレースオプション)*

3. ユーザーの過去のアクティビティが開いた画面にリスト表示されます。
4. 統計情報が上部に表示されます: 合計レコード、表示されたレコード、最終アクティビティ。
5. **{{t:common.actions.export}}**ボタンをクリックし、形式を選択します：**{{t:common.exportCSV}}**または**{{t:common.exportJSON}}**。

![監査履歴 - エクスポートオプション](/assets/images/UserGuideEng/15_user_trace_export.png)
*(図15: ユーザーの完全なアクティビティ履歴 - 統計、詳細、エクスポートオプション)*

> **ヒント**: セキュリティとコンプライアンスの記録を維持するために、監査データを定期的にエクスポートしてください。CSV形式はExcelで開くことができます。

---

## 2.2 組織 - チーム

チームを使用すると、ユーザーをグループ化し、リソースへの一括アクセスを提供できます。

### 2.2.1 チームの作成

1. **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationTeams}}**タブに移動します。
2. **「+」**ボタンをクリックします。
3. **{{t:common.vaultEditor.fields.TEAM.name.label}}**フィールドにチーム名を入力します。
4. **{{t:common.vaultEditor.vaultConfiguration}}**セクションの**{{t:common.vaultEditor.fields.TEAM.SSH_PRIVATE_KEY.label}}**と**{{t:common.vaultEditor.fields.TEAM.SSH_PUBLIC_KEY.label}}**フィールドに入力します。

![新規チーム作成フォーム - チーム名とSSHキー](/assets/images/UserGuideEng/16_teams_create.png)
*(図16: 「Private Team」内での新規チーム作成)*

5. **{{t:common.actions.create}}**ボタンをクリックしてチームを保存します。

> **ヒント**: SSHキーはBridge SSH認証に必要です。キー欠落の警告が表示された場合は、両方のキーを提供してください。

### 2.2.2 チームの編集

1. チームリストで編集したいチームの横にある鉛筆アイコンをクリックします。
2. 必要に応じて**{{t:common.vaultEditor.fields.TEAM.name.label}}**フィールドでチーム名を変更します。
3. **{{t:common.vaultEditor.vaultConfiguration}}**セクションでSSHキーを更新します。
4. **{{t:common.save}}**ボタンをクリックして変更を適用します。

![チーム編集フォーム - 青い情報メッセージ](/assets/images/UserGuideEng/17_teams_edit_form.png)
*(図17: 既存チームの情報編集)*

> **ヒント**: チーム構成は組織構造に使用されます。変更はすべてのチームメンバーに適用されます。

### 2.2.3 チームメンバー管理

1. チームを選択し、ユーザーアイコンをクリックします。
2. **{{t:organization.teams.manageMembers.currentTab}}**タブで、すでにチームに割り当てられているメンバーを確認します。
3. **{{t:organization.teams.manageMembers.addTab}}**タブに切り替えます。
4. メールアドレスを入力するか、ドロップダウンからユーザーを選択します。
5. **「+」**ボタンをクリックしてメンバーをチームに追加します。

![チームメンバー管理フォーム - 「Current Members」と「Add Member」タブ](/assets/images/UserGuideEng/18_teams_members_form.png)
*(図18: チームメンバー管理パネル)*

> **ヒント**: 同じメンバーを複数のチームに割り当てることができます。

### 2.2.4 チームトレース

1. トレースするチームを選択します。
2. 時計/履歴アイコンをクリックします。
3. **{{t:resources.audit.title}}**モーダルで、合計レコード、表示されたレコード、最終アクティビティの数を確認します。
4. **{{t:common.actions.export}}**ボタンをクリックして、{{t:common.exportCSV}}または{{t:common.exportJSON}}形式でエクスポートします。

![監査履歴モーダル - DataBassTeamチーム](/assets/images/UserGuideEng/19_teams_trace.png)
*(図19: チーム監査履歴の表示)*

> **ヒント**: 監査履歴はコンプライアンスとセキュリティ管理に重要です。

### 2.2.5 チームの削除

1. 削除したいチームの横にあるゴミ箱(赤)アイコンをクリックします。
2. 確認ダイアログでチーム名が正しいことを確認します。
3. **{{t:common.general.yes}}**ボタンをクリックします。

![チーム削除確認ダイアログ](/assets/images/UserGuideEng/20_teams_delete.png)
*(図20: チーム削除の確認)*

> **警告**: チームの削除は元に戻せません。削除する前にチームに重要なデータがないか確認してください。

---

## 2.3 組織 - アクセス制御

アクセス制御では、権限グループを作成してユーザー権限を一元管理できます。

### 2.3.1 権限グループの作成

1. **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationAccess}}**タブに移動します。
2. **「+」**ボタンをクリックします。
3. **{{t:organization.access.modals.groupPlaceholder}}**フィールドに意味のある名前を入力します。
4. **{{t:common.actions.confirm}}**ボタンをクリックしてグループを作成します。

![権限グループ作成フォーム](/assets/images/UserGuideEng/21_create_access.png)
*(図21: 新規権限グループの作成)*

> **ヒント**: 権限グループは同様の権限を持つユーザーを整理するために使用されます。グループ名は説明的に保ってください(例: 「Admin」、「Read Only」、「Repository Manager」)。

### 2.3.2 権限管理

1. 権限グループを選択し、**{{t:organization.access.modals.managePermissionsTitle}}**オプションをクリックします。
2. **{{t:organization.access.modals.currentPermissionsTab}}**タブでグループのアクセス権を確認します。
3. 各アクションの横にある赤い**{{t:common.delete}}**ボタンをクリックすることで、権限を取り消すことができます。
4. **{{t:organization.access.modals.addPermissionsTab}}**タブをクリックして、グループに新しい権限を追加します。

![権限管理パネル - 割り当てられた権限リスト](/assets/images/UserGuideEng/22_access_permission.png)
*(図22: 権限グループの権限管理)*

> **ヒント**: 最小権限の原則に基づいて権限を付与してください。不要な権限を定期的に確認して削除してください。

---

## 2.4 マシン

マシンセクションでは、サーバーとリポジトリリソースを管理できます。

### 2.4.1 マシンの追加

1. 左メニューから**{{t:common.navigation.machines}}**タブに移動します。
2. 右上の**{{t:machines.createMachine}}**ボタンをクリックします。

![マシンページ - 「マシンの追加」ボタン](/assets/images/UserGuideEng/23_machines_add.png)
*(図23: マシン管理ホームページ)*

3. 開いたフォームに入力します:
   - **{{t:machines.machineName}}**: 一意の名前を入力(例: 「server-01」)
   - **{{t:common.vaultEditor.fields.MACHINE.ip.label}}**: マシンのIPアドレスを入力(例: 192.168.111.11)
   - **{{t:common.vaultEditor.fields.MACHINE.datastore.label}}**: ストレージディレクトリを指定(例: /mnt/rediacc)
   - **{{t:common.vaultEditor.fields.MACHINE.user.label}}**: SSHユーザー名を入力
   - **{{t:common.vaultEditor.fields.MACHINE.port.label}}**: ポート番号を入力(デフォルト: 22)
   - **{{t:common.vaultEditor.fields.MACHINE.ssh_password.label}}**: パスワードを入力(オプション)

![マシン追加フォーム - すべてのフィールド](/assets/images/UserGuideEng/24_machine_create.png)
*(図24: 新規マシン追加フォーム - マシン名、ネットワーク設定、SSH認証情報)*

4. **{{t:common.vaultEditor.testConnection.button}}**ボタンをクリックして接続を確認します。
5. テストが成功したら、**{{t:common.actions.create}}**ボタンをクリックします。

> **ヒント**: 「マシン作成後に自動的にセットアップを開始」オプションがチェックされている場合、マシンは自動的に追加のセットアップステップを実行します。

![マシン作成完了 - タスク追跡ウィンドウ](/assets/images/UserGuideEng/25_machine_create_complete.png)
*(図25: マシンが正常に作成された後のタスク追跡ウィンドウ)*

6. ステージを確認します: **Assigned** → **Processing** → **{{t:queue.statusCompleted}}**
7. **{{t:common.actions.close}}**ボタンをクリックして操作を閉じます。

> **ヒント**: 「{{t:common.actions.refresh}}」ボタンをクリックして、最新のステータスを手動で確認できます。

### 2.4.2 接続テスト

既存のマシンの接続ステータスを確認できます。

1. **{{t:machines.connectivityTest}}**ボタンをクリックします。

![接続テストボタン](/assets/images/UserGuideEng/26_connectivity_test_button.png)
*(図26: マシンアクションツールバーの接続テストボタン)*

2. テストするマシンのリストを確認します。
3. **{{t:machines.runTest}}**ボタンをクリックします。
4. 成功した結果は緑色で、失敗は赤色で表示されます。

![接続テストフォーム - マシンリスト](/assets/images/UserGuideEng/27_connectivity_test_form.png)
*(図27: 接続テストフォーム - 選択したマシンのping機能)*

> **ヒント**: テストが失敗した場合は、マシンのIPアドレスとSSH設定を確認してください。

### 2.4.3 マシンリストの更新

**{{t:common.actions.refresh}}**ボタンをクリックしてマシンリストを更新します。

![更新ボタン](/assets/images/UserGuideEng/28_refresh.png)
*(図28: マシンアクションツールバーの更新ボタン)*

### 2.4.4 マシンの詳細

1. 詳細を表示したいマシンを選択します。
2. 目のアイコンボタン(**View Details**)をクリックします。

![詳細表示ボタン](/assets/images/UserGuideEng/29_view_details_button.png)
*(図29: マシンアクション列の目のアイコン)*

3. 右側にマシン詳細パネルが開きます:
   - **Hostname**: マシン名
   - **Uptime**: 稼働時間
   - **Operating System**: OSとバージョン
   - **Kernel**: カーネルバージョン
   - **CPU**: プロセッサ情報
   - **System Time**: システムクロック

![マシン詳細パネル - システム情報](/assets/images/UserGuideEng/30_machine_view_details.png)
*(図30: マシン詳細パネル - ホスト名、稼働時間、OS、カーネル、CPU情報)*

> **ヒント**: OSの互換性とリソースの可用性を確認するために、この情報を定期的に確認してください。

### 2.4.5 マシンの編集

1. 編集したいマシンを選択します。
2. 鉛筆アイコンボタン(**{{t:common.actions.edit}}**)をクリックします。

![編集ボタン](/assets/images/UserGuideEng/31_edit_button.png)
*(図31: マシンアクション列の鉛筆アイコン)*

3. 必要な変更を行います。
4. **{{t:common.vaultEditor.testConnection.button}}**ボタンをクリックします。
5. 接続が成功したら、**{{t:common.save}}**ボタンをクリックします。

![マシン編集フォーム](/assets/images/UserGuideEng/32_edit_form.png)
*(図32: マシン編集フォーム - マシン名、リージョン、vault構成)*

> **ヒント**: 重要な設定を変更した後は、必ず「接続テスト」を実行してください。

### 2.4.6 マシントレース

1. マシンを選択し、時計アイコンボタン(**{{t:common.actions.trace}}**)をクリックします。

![トレースボタン](/assets/images/UserGuideEng/33_trace_button.png)
*(図33: マシンアクション列の時計アイコン)*

2. 監査履歴ウィンドウで操作を確認します:
   - **{{t:resources.audit.action}}**: 実行された操作のタイプ
   - **Details**: 変更されたフィールド
   - **{{t:resources.audit.performedBy}}**: アクションを実行したユーザー
   - **{{t:resources.audit.timestamp}}**: 日付と時刻

![マシン監査履歴ウィンドウ](/assets/images/UserGuideEng/34_trace_list.png)
*(図34: 監査履歴 - すべての変更のリスト)*

> **ヒント**: タイムスタンプ列をクリックして、時系列で変更を表示できます。

### 2.4.7 マシンの削除

1. 削除したいマシンを選択します。
2. ゴミ箱アイコンボタン(**{{t:common.delete}}**)をクリックします。

![削除ボタン](/assets/images/UserGuideEng/35_delete_button.png)
*(図35: マシンアクション列のゴミ箱アイコン)*

3. 確認ウィンドウの**{{t:common.delete}}**ボタンをクリックします。

![マシン削除確認ウィンドウ](/assets/images/UserGuideEng/36_delete_form.png)
*(図36: 「このマシンを削除してもよろしいですか?」確認ウィンドウ)*

> **警告**: マシンが削除されると、その上のすべてのリポジトリ定義も削除されます。このアクションは元に戻せません。

### 2.4.8 リモート操作

マシン上でさまざまなリモート操作を実行できます。

1. マシンを選択し、**{{t:common.actions.remote}}**ボタンをクリックします。
2. ドロップダウンメニューのオプションを確認します:
   - **{{t:machines.runAction}}**: マシン上で関数を実行
   - **{{t:common.vaultEditor.testConnection.button}}**: マシンにpingを実行

![リモートメニュー - Run on ServerとTest Connection](/assets/images/UserGuideEng/37_remote_button.png)
*(図37: リモートボタン - 選択したマシン上での関数実行メニュー)*

> **ヒント**: 関数を実行する前に、「{{t:common.vaultEditor.testConnection.button}}」オプションを使用してマシンにアクセスできることを確認してください。

#### セットアップ

1. **{{t:machines.runAction}}**オプションを選択します。
2. **{{t:functions.availableFunctions}}**リストで**setup**関数を見つけます。
3. 関数名をクリックして選択します。

![マシン関数リスト - setup関数](/assets/images/UserGuideEng/38_server_setup.png)
*(図38: セットアップ関数 - 必要なツールと構成でマシンを準備します)*

> **ヒント**: 新しいマシンをセットアップする際は、まず「setup」関数を実行することをお勧めします。

#### 接続確認(Hello)

1. **{{t:machines.runAction}}** > **hello**関数を選択します。
2. **{{t:common.actions.addToQueue}}**ボタンをクリックします。

![Hello関数選択](/assets/images/UserGuideEng/39_remote_hello.png)
*(図39: Hello関数 - シンプルなテスト関数、ホスト名を返します)*

3. タスク追跡ウィンドウで結果を確認します。
4. **{{t:queue.trace.responseConsole}}**セクションでマシンの出力を確認します。

![Hello関数完了](/assets/images/UserGuideEng/40_remote_hello_complete.png)
*(図40: Hello関数が正常に完了 - ホスト名レスポンス)*

> **ヒント**: hello関数は、マシンの接続を確認するのに最適です。

#### 高度な操作

1. **{{t:common.actions.remote}}** > **{{t:machines.runAction}}** > **{{t:common.actions.advanced}}**のパスに従います。
2. 利用可能な関数を確認します: setup、hello、ping、ssh_test、uninstall
3. 必要な関数を選択し、**{{t:common.actions.addToQueue}}**ボタンをクリックします。

![高度な関数リスト](/assets/images/UserGuideEng/41_remote_advanced.png)
*(図41: 高度なオプション - 高度な関数リスト)*

> **ヒント**: 高度な関数を使用する前に、マシンのセットアップが完了していることを確認してください。

#### クイック接続テスト

![リモートメニュー - Test Connection](/assets/images/UserGuideEng/42_connectivity_test.png)
*(図42: リモートメニューからのTest Connectionオプション)*

> **ヒント**: マシンにSSHまたはネットワークの問題がある場合、このテストで問題を素早く特定できます。

---

## 2.5 リポジトリの作成と操作

リポジトリは、バックアップデータが保存される基本的な単位です。

### 2.5.1 リポジトリの作成

1. **{{t:common.navigation.machines}}**タブからマシンを選択します。
2. 右上の**{{t:machines.createRepository}}**ボタンをクリックします。

![リポジトリ作成ボタン](/assets/images/UserGuideEng/43_create_repo_add.png)
*(図43: マシンリポジトリ管理画面 - リポジトリ作成ボタン)*

3. フォームに入力します:
   - **{{t:common.vaultEditor.fields.REPOSITORY.name.label}}**: リポジトリ名を入力します（例：postgresql）
   - **{{t:resources.repositories.size}}**: リポジトリサイズを入力します（例：2GB）
   - **{{t:resources.repositories.repositoryGuid}}**: 自動生成された認証情報を確認します
   - **{{t:resources.templates.selectTemplate}}**: テンプレートを選択します（例：databases_postgresql）

![リポジトリ作成フォーム](/assets/images/UserGuideEng/44_repo_form.png)
*(図44: リポジトリ作成フォーム - リポジトリ名、サイズ、テンプレート選択)*

4. **{{t:common.actions.create}}**ボタンをクリックします。

> **ヒント**: 認証情報IDは自動生成されます。手動で変更することはお勧めしません。

5. タスク追跡ウィンドウでステージを確認します: **Assigned** → **Processing** → **{{t:queue.statusCompleted}}**

![リポジトリ作成完了](/assets/images/UserGuideEng/45_repo_complete.png)
*(図45: リポジトリ作成がキューに入りました - タスク監視)*

6. **{{t:common.actions.close}}**ボタンをクリックします。

> **ヒント**: タスクは通常1〜2分以内に完了します。

![リポジトリリスト](/assets/images/UserGuideEng/46_repo_list.png)
*(図46: 作成されたリポジトリがリストに表示されます)*

### 2.5.2 リポジトリフォーク

既存のリポジトリをコピーして新しいリポジトリを作成できます。

1. コピーしたいリポジトリを選択します。
2. **fx**(関数)メニューをクリックします。
3. **fork**オプションをクリックします。

![fxメニュー - forkオプション](/assets/images/UserGuideEng/47_fork_button.png)
*(図47: 右側のfxメニュー - リポジトリ操作)*

4. **{{t:functions.functions.fork.params.tag.label}}**フィールドに新しいタグを入力します（例：2025-12-06-20-37-08）。
5. **{{t:common.actions.addToQueue}}**ボタンをクリックします。

![フォーク構成フォーム](/assets/images/UserGuideEng/48_fork_form.png)
*(図48: フォーク操作でリポジトリの新しいタグを指定)*

6. **{{t:queue.statusCompleted}}**メッセージを待ち、**{{t:common.actions.close}}**ボタンをクリックします。

![フォーク完了](/assets/images/UserGuideEng/49_repo_completed.png)
*(図49: フォーク操作が正常に完了)*

> **ヒント**: デフォルトの日時形式でタグを作成することは良い習慣です。フォーク操作は元のリポジトリに影響を与えません。

### 2.5.3 リポジトリUp

リポジトリをアクティベートするには:

1. リポジトリを選択し、**fx** > **up**パスに従います。

![Up操作](/assets/images/UserGuideEng/50_repo_up.png)
*(図50: fxメニューからの「up」オプション - リポジトリの起動)*

2. **{{t:queue.statusCompleted}}**メッセージを待ちます。

![Up完了](/assets/images/UserGuideEng/51_repo_up_complete.png)
*(図51: リポジトリ起動完了)*

> **ヒント**: 「Up」操作は、リポジトリで定義されたDockerサービスを起動します。

### 2.5.4 リポジトリDown

アクティブなリポジトリを停止するには:

1. リポジトリを選択し、**fx** > **down**パスに従います。

![Down操作](/assets/images/UserGuideEng/52_down_button.png)
*(図52: fxメニューからの「down」オプション - リポジトリのシャットダウン)*

2. **{{t:queue.statusCompleted}}**メッセージを待ちます。

![Down完了](/assets/images/UserGuideEng/53_down_completed.png)
*(図53: リポジトリシャットダウン完了)*

> **ヒント**: 「Down」操作は、リポジトリを安全にシャットダウンします。データは失われず、サービスのみが停止されます。

### 2.5.5 デプロイ

リポジトリを別の場所にデプロイするには:

1. リポジトリを選択し、**fx** > **deploy**パスに従います。

![Deploy操作](/assets/images/UserGuideEng/54_deploy_button.png)
*(図54: fxメニューからの「deploy」オプション)*

2. **{{t:functions.functions.fork.params.tag.label}}**フィールドにデプロイするバージョンを入力します。
3. **{{t:functions.functions.backup_deploy.params.machines.label}}**フィールドでターゲットマシンを選択します。
4. **{{t:functions.checkboxOptions.overrideExistingFile}}**オプションをチェックします（該当する場合）。
5. **{{t:common.actions.addToQueue}}**ボタンをクリックします。

![Deployフォーム](/assets/images/UserGuideEng/55_deploy_form.png)
*(図55: デプロイ操作の構成 - タグ、ターゲットマシン、オプション)*

6. **{{t:queue.statusCompleted}}**メッセージを待ちます。

![Deploy完了](/assets/images/UserGuideEng/56_deploy_completed.png)
*(図56: リポジトリデプロイ完了)*

> **ヒント**: デプロイ操作が完了したら、「up」コマンドを実行してターゲットマシンでリポジトリを起動できます。

### 2.5.6 バックアップ

リポジトリをバックアップするには:

1. リポジトリを選択し、**fx** > **backup**パスに従います。

![Backup操作](/assets/images/UserGuideEng/57_backup_button.png)
*(図57: fxメニューからの「backup」オプション)*

2. フォームに入力します:
   - **{{t:functions.functions.fork.params.tag.label}}**: 説明的な名前を入力します（例：backup01012025）
   - **{{t:functions.functions.backup_create.params.storages.label}}**: バックアップの場所を選択します
   - **{{t:functions.checkboxOptions.overrideExistingFile}}**: オプションを有効または無効にします
   - **{{t:functions.functions.backup_deploy.params.checkpoint.label}}**: 設定を確認します

![Backupフォーム](/assets/images/UserGuideEng/58_backup_form.png)
*(図58: バックアップ構成フォーム - ターゲット、ファイル名、オプション)*

3. **{{t:common.actions.addToQueue}}**ボタンをクリックします。

> **ヒント**: バックアップタグには説明的な名前を使用してください。大規模なリポジトリの場合は、チェックポイントを有効にすることを検討してください。

4. **{{t:queue.statusCompleted}}**メッセージを待ちます。

![Backup完了](/assets/images/UserGuideEng/59_backup_completed.png)
*(図59: バックアップタスクが正常に完了)*

> **ヒント**: 完了ステータスに達するまで辛抱強く待ってください。大規模なバックアップには数分かかる場合があります。

### 2.5.7 テンプレートの適用

リポジトリに新しいテンプレートを適用するには:

1. リポジトリを選択し、**fx** > **Templates**パスに従います。

![Templates操作](/assets/images/UserGuideEng/60_templates_button.png)
*(図60: fxメニューからの「Templates」オプション)*

2. 検索ボックスに入力してテンプレートをフィルタリングします。
3. 目的のテンプレートをクリックして選択します(選択したテンプレートは太い枠で強調表示されます)。
4. **{{t:common.actions.addToQueue}}**ボタンをクリックします。

![テンプレート選択フォーム](/assets/images/UserGuideEng/61_templates_form.png)
*(図61: 利用可能なテンプレートの検索と選択)*

> **ヒント**: 検索ボックスを使用してテンプレートをすばやく検索します。テンプレートの機能について詳しくは「{{t:common.viewDetails}}」を使用してください。

5. **{{t:queue.statusCompleted}}**メッセージを待ちます。

![テンプレート適用完了](/assets/images/UserGuideEng/62_templates_completed.png)
*(図62: テンプレート適用が正常に完了)*

### 2.5.8 アンマウント

リポジトリを切断するには:

1. リポジトリを選択し、**fx** > **{{t:common.actions.advanced}}** > **{{t:resources.repositories.unmount}}**のパスに従います。

![Unmount操作](/assets/images/UserGuideEng/63_unmount_button.png)
*(図63: 高度なメニューの「Unmount」オプション)*

2. **{{t:queue.statusCompleted}}**メッセージを待ちます。

![Unmount完了](/assets/images/UserGuideEng/64_unmount_completed.png)
*(図64: アンマウント操作完了)*

> **ヒント**: アンマウントする前に、リポジトリ上にアクティブな操作がないことを確認してください。アンマウント後、リポジトリにアクセスできなくなります。

### 2.5.9 拡張

リポジトリサイズを増やすには:

1. リポジトリを選択し、**fx** > **{{t:common.actions.advanced}}** > **{{t:functions.functions.repository_expand.name}}**のパスに従います。

![Expand操作](/assets/images/UserGuideEng/65_expand_button.png)
*(図65: 高度なメニューの「Expand」オプション)*

2. **{{t:functions.functions.repository_expand.params.size.label}}**フィールドに希望のサイズを入力します。
3. 右側のドロップダウンから単位を選択します(GB、TB)。
4. **{{t:common.actions.addToQueue}}**ボタンをクリックします。

![Expandフォーム](/assets/images/UserGuideEng/66_expand_form.png)
*(図66: リポジトリサイズを増やすための新しいサイズパラメータ)*

> **ヒント**: 現在のサイズより小さい値を入力しないでください。リポジトリ拡張中にサービスは中断されません。

5. **{{t:queue.statusCompleted}}**メッセージを待ちます。

![Expand完了](/assets/images/UserGuideEng/67_expand_completed.png)
*(図67: リポジトリ拡張完了)*

### 2.5.10 名前変更

リポジトリ名を変更するには:

1. リポジトリを選択し、**fx** > **{{t:common.actions.rename}}**のパスに従います。

![Rename操作](/assets/images/UserGuideEng/68_rename_button.png)
*(図68: fxメニューからの「Rename」オプション)*

2. 新しいリポジトリ名を入力します。
3. **{{t:common.save}}**ボタンをクリックします。

![Renameフォーム](/assets/images/UserGuideEng/69_rename_form.png)
*(図69: 新しいリポジトリ名を入力するダイアログ)*

> **ヒント**: リポジトリ名は、リポジトリのタイプと目的を反映する意味のあるものにする必要があります。特殊文字は避けてください。

### 2.5.11 リポジトリの削除

リポジトリを完全に削除するには:

1. リポジトリを選択し、**fx** > **{{t:resources.repositories.deleteRepository}}**のパスに従います。

![Delete Repository操作](/assets/images/UserGuideEng/70_delete_repo_button.png)
*(図70: fxメニューからの「Delete Repository」オプション - 赤)*

2. 確認ウィンドウの**{{t:common.delete}}**ボタンをクリックします。

> **警告**: リポジトリの削除は元に戻せません。削除する前にリポジトリデータがバックアップされていることを確認してください。

### 2.5.12 リポジトリの詳細

リポジトリに関する詳細情報を取得するには:

1. リポジトリを選択します。
2. 目のアイコン(**View Details**)をクリックします。

![詳細表示ボタン](/assets/images/UserGuideEng/71_repo_view_button.png)
*(図71: リポジトリ詳細を開く目のアイコン)*

3. 詳細パネルの情報を確認します:
   - **Repository name**とタイプ
   - **Team**: 所属するチーム
   - **Machine**: 配置されているマシン
   - **Vault Version**: 暗号化バージョン
   - **Repository GUID**: 一意の識別子
   - **Status**: マウント/アンマウントステータス
   - **Image Size**: 合計サイズ
   - **Last Modified**: 最終更新日

![リポジトリ詳細パネル](/assets/images/UserGuideEng/72_repo_details_view.png)
*(図72: 選択したリポジトリに関する包括的な情報)*

> **ヒント**: このパネルに表示されるすべての情報は参照用です。リポジトリ操作にはfxメニューオプションを使用してください。

---

## 2.6 リポジトリ接続操作

さまざまな方法を使用してリポジトリに接続できます。

### 2.6.1 デスクトップアプリケーション接続

1. リポジトリ行の**{{t:resources.localActions.local}}**ボタンをクリックします。

![ローカル接続ボタン](/assets/images/UserGuideEng/73_repo_connection_local.png)
*(図73: リポジトリ行の「Local」ボタン - デスクトップアプリケーションアクセス)*

2. ドロップダウンメニューからアクセス方法を選択します:
   - **{{t:resources.localActions.openInDesktop}}**: グラフィカルインターフェースでアクセス
   - **{{t:resources.localCommandBuilder.vscodeTab}}**: コードエディタで開く
   - **{{t:common.terminal.terminal}}**: コマンドラインでアクセス
   - **{{t:resources.localActions.showCLICommands}}**: コマンドラインツール

![接続オプションメニュー](/assets/images/UserGuideEng/74_repo_connection.png)
*(図74: リポジトリ接続メニュー - 異なるアクセスパス)*

> **ヒント**: VS Codeで作業している場合、「{{t:resources.localCommandBuilder.vscodeTab}}」オプションが最速の統合を提供します。

3. ブラウザが許可を求めたとき、**Open**ボタンをクリックします。

![デスクトップアプリケーション開く許可](/assets/images/UserGuideEng/75_desktop_open_page.png)
*(図75: デスクトップアプリケーションを開く許可をブラウザが要求)*

> **ヒント**: デスクトップアプリケーションを開くたびに許可を与えたくない場合は、「Always allow」オプションをチェックしてください。

---

## 2.7 設定

設定セクションから、プロフィールとシステム設定を管理できます。

### 2.7.1 パスワード変更

1. 左メニューから**{{t:common.navigation.settings}}** > **{{t:common.navigation.settingsProfile}}**タブに移動します。

![プロフィール設定ページ](/assets/images/UserGuideEng/76_profiles_button.png)
*(図76: 設定 → プロフィールページ - 個人vault設定)*

2. **{{t:settings.personal.changePassword.submit}}**ボタンをクリックします。

![パスワード変更ボタン](/assets/images/UserGuideEng/77_profiles_change_button.png)
*(図77: 個人設定セクションの「Change Password」ボタン)*

3. 新しいパスワードを入力します。パスワード要件:
   - 8文字以上
   - 大文字と小文字を含む必要がある
   - 少なくとも1つの数字を含む必要がある
   - 少なくとも1つの特殊文字を含む必要がある

4. **{{t:settings.personal.changePassword.confirmPasswordLabel}}**フィールドに同じパスワードを再入力します。
5. **{{t:settings.personal.changePassword.submit}}**ボタンをクリックします。

![パスワード変更フォーム](/assets/images/UserGuideEng/78_profiles_change_form.png)
*(図78: パスワード変更フォーム - セキュリティ要件が表示)*

> **ヒント**: 強力なパスワードを作成する際は、ランダムな組み合わせを使用してください。

---

## 2.8 ストレージ

ストレージセクションでは、バックアップデータが保存される物理的なエリアを管理できます。

### 2.8.1 ストレージの追加

1. 左メニューから**{{t:common.navigation.storage}}**タブに移動します。
2. **{{t:resources.storage.createStorage}}**ボタンをクリックします。

![ストレージ追加ボタン](/assets/images/UserGuideEng/79_storage_add_button.png)
*(図79: ストレージ管理ページ - 「Add Storage」ボタン)*

3. フォームに入力します:
   - **{{t:common.vaultEditor.fields.STORAGE.name.label}}**: 説明的な名前を入力します
   - **{{t:common.vaultEditor.fields.STORAGE.provider.label}}**: 選択します（例：s3）
   - **{{t:common.vaultEditor.fields.STORAGE.description.label}}**: オプションの説明を追加します
   - **{{t:common.vaultEditor.fields.STORAGE.noVersioning.label}}**: オプション
   - **{{t:common.vaultEditor.fields.STORAGE.parameters.label}}**: rcloneフラグ（例：--transfers 4）

![ストレージ作成フォーム](/assets/images/UserGuideEng/80_storage_form.png)
*(図80: ストレージ追加フォーム - 名前、プロバイダー、説明、パラメータ)*

4. **{{t:common.actions.create}}**ボタンをクリックします。

> **ヒント**: 追加パラメータは、ストレージパフォーマンスを最適化するためのrcloneフラグを受け入れます。

---

## 2.9 認証情報

認証情報セクションでは、リポジトリのアクセス情報を安全に管理できます。

### 2.9.1 認証情報の編集

1. 左メニューから**{{t:common.navigation.credentials}}**タブに移動します。
2. 編集したいレコードを選択します。
3. **{{t:common.actions.edit}}**ボタンをクリックします。

![認証情報リスト](/assets/images/UserGuideEng/81_credentials.png)
*(図81: 認証情報ページ - リポジトリ名、チーム、管理ボタン)*

4. 必要に応じて**{{t:common.vaultEditor.fields.REPOSITORY.name.label}}**を変更します。
5. **{{t:common.save}}**ボタンで保存します。

![認証情報編集フォーム](/assets/images/UserGuideEng/82_credentials_form.png)
*(図82: リポジトリ名編集フォーム - vault構成フィールド)*

> **ヒント**: 認証情報は暗号化されて保存され、デプロイ時にのみ復号化されます。

### 2.9.2 認証情報トレース

1. トレースするレコードを選択します。
2. **{{t:common.actions.trace}}**ボタンをクリックします。

![トレースボタン](/assets/images/UserGuideEng/83_credentials_trace_button.png)
*(図83: 認証情報テーブルの「Trace」ボタン)*

3. 監査履歴を確認します。
4. **{{t:common.actions.export}}**ボタンから形式を選択します：**{{t:common.exportCSV}}**または**{{t:common.exportJSON}}**。

![認証情報監査履歴](/assets/images/UserGuideEng/84_credentials_list_export.png)
*(図84: 認証情報リスト - エクスポートオプション)*

> **ヒント**: トレース機能は、セキュリティ監査目的で認証情報の使用状況を追跡します。

### 2.9.3 認証情報の削除

1. 削除したいレコードを選択します。
2. 赤い**{{t:common.delete}}**ボタンをクリックします。

![削除ボタン](/assets/images/UserGuideEng/85_credentials_delete.png)
*(図85: 認証情報ページの赤い「Delete」ボタン)*

3. 確認ウィンドウの**{{t:common.delete}}**ボタンをクリックします。

![削除確認](/assets/images/UserGuideEng/86_credentials_delete_confirm.png)
*(図86: 削除確認ダイアログ - 元に戻せないアクション警告)*

> **警告**: 削除する前に、認証情報が他のマシンや他の操作で使用されていないことを確認してください。削除する前に重要な認証情報のバックアップがあることを確認してください。

---

## 2.10 キュー

キューセクションでは、システム内の保留中および完了した操作を追跡できます。

### 2.10.1 キュー操作

1. 左メニューから**{{t:common.navigation.queue}}**タブをクリックします。

![キューページ](/assets/images/UserGuideEng/87_queue_button.png)
*(図87: キューページ - フィルタリングオプションとステータスタブ)*

2. キューアイテムをフィルタリングするには:
   - **{{t:queue.trace.team}}**、**{{t:queue.trace.machine}}**、**{{t:queue.trace.region}}**、**{{t:queue.trace.bridge}}**フィルターを使用
   - **{{t:system.audit.filters.dateRange}}**を指定します
   - **{{t:queue.filters.onlyStale}}**オプションをチェックします

3. ステータスタブで詳細を表示:
   - **{{t:queue.statusActive}}**: 処理中のタスク
   - **{{t:queue.statusCompleted}}**: 正常に完了したタスク
   - **{{t:queue.statusCancelled}}**: キャンセルされたタスク
   - **{{t:queue.statusFailed}}**: 失敗したタスク

4. **{{t:common.actions.export}}**ボタンから形式を選択します：**{{t:common.exportCSV}}**または**{{t:common.exportJSON}}**。

![キューエクスポート](/assets/images/UserGuideEng/88_queue_export.png)
*(図88: キューリスト - エクスポートオプション)*

> **ヒント**: 「{{t:queue.filters.onlyStale}}」オプションは、長時間処理中のタスクを見つけるのに役立ちます。タスク実行傾向を分析するために、キュー履歴を定期的にエクスポートしてください。

---

## 2.11 監査

監査セクションは、システムで実行されたすべての操作の記録を保持します。

### 2.11.1 監査レコード

1. 左メニューから**{{t:common.navigation.audit}}**タブをクリックします。

![監査リスト](/assets/images/UserGuideEng/89_audit_list.png)
*(図89: 監査ページ - すべてのシステム操作の詳細な記録)*

2. 監査レコードをフィルタリング:
   - **日付範囲**: 特定の期間でフィルタリング
   - **エンティティタイプ**: リクエスト、マシン、キューなどでフィルタリング
   - **検索**: テキスト検索を実行

3. 各レコードの情報を確認:
   - **Timestamp**: 操作の日付と時刻
   - **Action**: 操作のタイプ(作成、編集、削除など)
   - **Entity Type**: 影響を受けたオブジェクトのタイプ
   - **Entity Name**: 特定のオブジェクト識別子
   - **User**: 操作を実行したユーザー
   - **Details**: 操作に関する追加情報

4. **{{t:common.actions.export}}**ボタンから形式を選択します：**{{t:common.exportCSV}}**または**{{t:common.exportJSON}}**。

![監査エクスポート](/assets/images/UserGuideEng/90_audit_export.png)
*(図90: 監査レコードエクスポート - CSVとJSONオプション)*

> **ヒント**: 監査レコードは、セキュリティとコンプライアンスの目的でシステムのすべてのアクティビティを追跡するために重要です。監査レコードを定期的にエクスポートし、安全な場所に保管してください。

---

**© 2025 Rediacc Platform – All Rights Reserved.**
