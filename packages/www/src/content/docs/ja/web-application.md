---
title: Webアプリケーション
description: Rediaccを使用したWebアプリケーションのアーキテクチャと展開について理解する
category: Reference
order: 1
language: ja
sourceHash: "ee9dff9ac2c8bce1"
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

![Registration process walkthrough](/assets/videos/user-guide/01-01-registration.webm)
*(動画: Complete registration flow from start to finish)*

Rediaccプラットフォームの使用を開始するには、まずアカウントを作成する必要があります。

![Rediaccログインページ - 常時稼働インフラストラクチャ](/assets/images/user-guide/01_login.png)
*(図1: メインログインページ。Rediaccプラットフォームの主な機能を表示)*

1. ブラウザで[https://www.rediacc.com/](https://www.rediacc.com/)にアクセスします。
2. ページの右上にある**{{t:auth.login.signIn}}**ボタンをクリックします。
3. 無料アクセスには**はじめに**を、デモンストレーションには**デモをリクエスト**を選択します。

> **ヒント**: クレジットカード不要で無料アカウントを作成できます。10個のCPUコアと無制限のチームが含まれます。

![Rediacc サインインフォーム - メールとパスワードフィールド](/assets/images/user-guide/02_register.png)
*(図2: 既存ユーザー向けのサインイン画面)*

4. アカウントをお持ちでない場合は、**{{t:auth.login.register}}**リンクをクリックして新しいアカウントを作成します。

5. 開いたフォームに以下の情報を入力します:
   - **{{t:auth.registration.organizationName}}**: 組織名を入力
   - **{{t:auth.login.email}}**: 有効なメールアドレスを入力
   - **{{t:auth.login.password}}**: 8文字以上のパスワードを作成
   - **{{t:auth.registration.passwordConfirm}}**: 同じパスワードを再入力

![アカウント作成モーダル - 登録、検証、完了ステップ](/assets/images/user-guide/03_create_account.png)
*(図3: 新規ユーザー登録のステップバイステップフォーム - 登録 > 検証 > 完了)*

6. 利用規約とプライバシーポリシーに同意するチェックボックスをオンにします。
7. **{{t:auth.registration.createAccount}}**ボタンをクリックします。

> **ヒント**: パスワードは8文字以上で、強力なものにする必要があります。すべてのフィールドは必須です。

8. メールに送信された6桁の認証コードを順番にボックスに入力します。
9. **{{t:auth.registration.verifyAccount}}**ボタンをクリックします。

![認証コード入力 - 6桁のアクティベーションコード](/assets/images/user-guide/04_verification_code.png)
*(図4: 管理者に送信されたアクティベーションコードを入力するウィンドウ)*

> **ヒント**: 認証コードの有効期限は限られています。コードが届かない場合は、迷惑メールフォルダを確認してください。

---

### 1.2 サインイン

![Sign in process walkthrough](/assets/videos/user-guide/01-02-login.webm)
*(動画: Complete sign in flow)*

アカウントが作成されたら、プラットフォームにログインできます。

1. **{{t:auth.login.email}}**フィールドを入力します(赤い警告が表示される場合は必須)。
2. **{{t:auth.login.password}}**フィールドを入力します。
3. **{{t:auth.login.signIn}}**ボタンをクリックします。

![サインインフォーム - エラー警告付き必須フィールド](/assets/images/user-guide/05_sign_in.png)
*(図5: ログインフォーム - エラーメッセージは赤い枠で示されます)*

> **ヒント**: エラーメッセージに「このフィールドは必須です」と表示される場合は、空のフィールドを入力してください。パスワードを忘れた場合は管理者に連絡してください。

4. ログインに成功すると、**{{t:common.navigation.dashboard}}**画面にリダイレクトされます。

![Rediacc ダッシュボード - マシンリストとサイドバーメニュー](/assets/images/user-guide/06_dashboard.png)
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

![Adding users walkthrough](/assets/videos/user-guide/02-01-01-user-create.webm)
*(動画: Creating a new user)*

1. 左サイドバーの**{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationUsers}}**オプションをクリックします。
2. すべてのユーザーのリストをテーブル形式で表示します。
3. 各ユーザー行には、メール、ステータス（{{t:organization.users.status.active}}/{{t:organization.users.status.inactive}}）、権限グループ、最終アクティビティ時刻が表示されます。

![ユーザー管理ページ - アクティブユーザーリスト](/assets/images/user-guide/07_users.png)
*(図7: 組織配下のユーザーセクション - すべてのユーザーの情報が表示されます)*

4. 右上の**「+」**アイコンをクリックします。
5. **{{t:organization.users.modals.createTitle}}**ボタンをクリックし、開いたフォームに入力します:
   - **{{t:organization.users.form.emailLabel}}**: ユーザーのメールアドレスを入力
   - **{{t:organization.users.form.passwordLabel}}**: 一時パスワードを入力

![ユーザー作成モーダル - メールとパスワードフィールド](/assets/images/user-guide/08_user_add.png)
*(図8: 新規ユーザー追加用のモーダルウィンドウ - シンプルで迅速なユーザー作成フォーム)*

6. **{{t:common.actions.create}}**ボタンをクリックします。

> **ヒント**: ログイン認証情報は、作成されたユーザーに安全に伝える必要があります。初回ログイン時にパスワードを変更することをお勧めします。

![ユーザーリスト - 3人のユーザーを含む完全なテーブルビュー](/assets/images/user-guide/09_user_list.png)
*(図9: ユーザー管理ページのすべてのアクティブおよび非アクティブユーザー)*

> **ヒント**: ページには自動的に20件のレコードが表示されます。ページネーションを使用してさらに多くのレコードを表示できます。

### 2.1.2 ユーザー権限の割り当て

![User permissions walkthrough](/assets/videos/user-guide/02-01-02-user-permissions.webm)
*(動画: Assigning permission groups to users)*

特定の権限グループをユーザーに割り当てることで、アクセス権を管理できます。

1. **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationUsers}}**タブからユーザーを選択します。
2. アクション列のシールドアイコン(**{{t:organization.access.tabs.permissions}}**)をクリックします。

![権限管理 - シールド、ギア、削除アイコン](/assets/images/user-guide/10_users_permissions.png)
*(図10: ユーザーアクションのアイコン表示 - 各アイコンは異なるアクションを表します)*

3. 開いたフォームから**{{t:organization.users.modals.permissionGroupLabel}}**を選択します。
4. グループ内のユーザー数と権限数がユーザーの横に表示されます。
5. **{{t:organization.users.modals.assignTitle}}**ボタンをクリックして変更を保存します。

![権限割り当てモーダル - 管理者グループ](/assets/images/user-guide/11_user_permissions_form.png)
*(図11: 選択したユーザーに権限グループを割り当てるモーダル - 利用可能なグループのドロップダウン)*

> **ヒント**: 一部の権限グループはシステムによって固定されており、変更できません。

### 2.1.3 ユーザーのアクティベーション

![User activation walkthrough](/assets/videos/user-guide/02-01-03-user-activation.webm)
*(動画: Activating an inactive user)*

無効化されたユーザーを再アクティベートできます。

1. **ユーザー**リストで非アクティブステータスの**ユーザー**を見つけます。
2. アクション列の赤いアイコンをクリックします。

![ユーザーアクティベーション - 「有効化」ツールチップビュー](/assets/images/user-guide/12_users_activation.png)
*(図12: 非アクティブユーザーの有効化)*

3. 確認ウィンドウで**{{t:common.general.yes}}**ボタンをクリックします。

![有効化確認モーダル](/assets/images/user-guide/13_users_activation_confirm.png)
*(図13: ユーザー有効化を確認するモーダルウィンドウ)*

> **ヒント**: このアクションは可逆的です。同じ方法でユーザーを無効化できます。

### 2.1.4 ユーザートレース

![User trace walkthrough](/assets/videos/user-guide/02-01-04-user-trace.webm)
*(動画: Viewing user activity trace)*

トレース機能を使用して、ユーザーのアクティビティを監視できます。

1. ユーザーを選択し、アクション列のギアアイコンをクリックします。
2. **{{t:common.actions.trace}}**オプションをクリックして、ユーザーのアクティビティ履歴を開きます。

![ユーザートレース - アクションボタン付き「トレース」ツールチップ](/assets/images/user-guide/14_users_trace.png)
*(図14: ユーザーアクティビティトレースオプション)*

3. ユーザーの過去のアクティビティが開いた画面にリスト表示されます。
4. 統計情報が上部に表示されます: 合計レコード、表示されたレコード、最終アクティビティ。
5. **{{t:common.actions.export}}**ボタンをクリックし、形式を選択します：**{{t:common.exportCSV}}**または**{{t:common.exportJSON}}**。

![監査履歴 - エクスポートオプション](/assets/images/user-guide/15_user_trace_export.png)
*(図15: ユーザーの完全なアクティビティ履歴 - 統計、詳細、エクスポートオプション)*

> **ヒント**: セキュリティとコンプライアンスの記録を維持するために、監査データを定期的にエクスポートしてください。CSV形式はExcelで開くことができます。

---

## 2.2 組織 - チーム

チームを使用すると、ユーザーをグループ化し、リソースへの一括アクセスを提供できます。

### 2.2.1 チームの作成

![Creating teams walkthrough](/assets/videos/user-guide/02-02-01-team-create.webm)
*(動画: Creating a new team)*

1. **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationTeams}}**タブに移動します。
2. **「+」**ボタンをクリックします。
3. **{{t:common.vaultEditor.fields.TEAM.name.label}}**フィールドにチーム名を入力します。
4. **{{t:common.vaultEditor.vaultConfiguration}}**セクションの**{{t:common.vaultEditor.fields.TEAM.SSH_PRIVATE_KEY.label}}**と**{{t:common.vaultEditor.fields.TEAM.SSH_PUBLIC_KEY.label}}**フィールドに入力します。

![新規チーム作成フォーム - チーム名とSSHキー](/assets/images/user-guide/16_teams_create.png)
*(図16: 「Private Team」内での新規チーム作成)*

5. **{{t:common.actions.create}}**ボタンをクリックしてチームを保存します。

> **ヒント**: SSHキーはBridge SSH認証に必要です。キー欠落の警告が表示された場合は、両方のキーを提供してください。

### 2.2.2 チームの編集

![Team editing walkthrough](/assets/videos/user-guide/02-02-02-team-edit.webm)
*(動画: Editing team information)*

1. チームリストで編集したいチームの横にある鉛筆アイコンをクリックします。
2. 必要に応じて**{{t:common.vaultEditor.fields.TEAM.name.label}}**フィールドでチーム名を変更します。
3. **{{t:common.vaultEditor.vaultConfiguration}}**セクションでSSHキーを更新します。
4. **{{t:common.save}}**ボタンをクリックして変更を適用します。

![チーム編集フォーム - 青い情報メッセージ](/assets/images/user-guide/17_teams_edit_form.png)
*(図17: 既存チームの情報編集)*

> **ヒント**: チーム構成は組織構造に使用されます。変更はすべてのチームメンバーに適用されます。

### 2.2.3 チームメンバー管理

![Team members management walkthrough](/assets/videos/user-guide/02-02-03-team-members.webm)
*(動画: Managing team members)*

1. チームを選択し、ユーザーアイコンをクリックします。
2. **{{t:organization.teams.manageMembers.currentTab}}**タブで、すでにチームに割り当てられているメンバーを確認します。
3. **{{t:organization.teams.manageMembers.addTab}}**タブに切り替えます。
4. メールアドレスを入力するか、ドロップダウンからユーザーを選択します。
5. **「+」**ボタンをクリックしてメンバーをチームに追加します。

![チームメンバー管理フォーム - 「現在のメンバー」と「メンバーを追加」タブ](/assets/images/user-guide/18_teams_members_form.png)
*(図18: チームメンバー管理パネル)*

> **ヒント**: 同じメンバーを複数のチームに割り当てることができます。

### 2.2.4 チームトレース

![Team trace walkthrough](/assets/videos/user-guide/02-02-04-team-trace.webm)
*(動画: Viewing team audit history)*

1. トレースするチームを選択します。
2. 時計/履歴アイコンをクリックします。
3. **{{t:resources.audit.title}}**モーダルで、合計レコード、表示されたレコード、最終アクティビティの数を確認します。
4. **{{t:common.actions.export}}**ボタンをクリックして、{{t:common.exportCSV}}または{{t:common.exportJSON}}形式でエクスポートします。

![監査履歴モーダル - DataBassTeamチーム](/assets/images/user-guide/19_teams_trace.png)
*(図19: チーム監査履歴の表示)*

> **ヒント**: 監査履歴はコンプライアンスとセキュリティ管理に重要です。

### 2.2.5 チームの削除

![Team deletion walkthrough](/assets/videos/user-guide/02-02-05-team-delete.webm)
*(動画: Deleting a team)*

1. 削除したいチームの横にあるゴミ箱(赤)アイコンをクリックします。
2. 確認ダイアログでチーム名が正しいことを確認します。
3. **{{t:common.general.yes}}**ボタンをクリックします。

![チーム削除確認ダイアログ](/assets/images/user-guide/20_teams_delete.png)
*(図20: チーム削除の確認)*

> **警告**: チームの削除は元に戻せません。削除する前にチームに重要なデータがないか確認してください。

---

## 2.3 組織 - アクセス制御

アクセス制御では、権限グループを作成してユーザー権限を一元管理できます。

### 2.3.1 権限グループの作成

![Permission group creation walkthrough](/assets/videos/user-guide/02-03-01-permission-create.webm)
*(動画: Creating a permission group)*

1. **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationAccess}}**タブに移動します。
2. **「+」**ボタンをクリックします。
3. **{{t:organization.access.modals.groupPlaceholder}}**フィールドに意味のある名前を入力します。
4. **{{t:common.actions.confirm}}**ボタンをクリックしてグループを作成します。

![権限グループ作成フォーム](/assets/images/user-guide/21_create_access.png)
*(図21: 新規権限グループの作成)*

> **ヒント**: 権限グループは同様の権限を持つユーザーを整理するために使用されます。グループ名は説明的に保ってください(例: 「管理者」、「読み取り専用」、「リポジトリマネージャー」)。

### 2.3.2 権限管理

![Permission management walkthrough](/assets/videos/user-guide/02-03-02-permission-manage.webm)
*(動画: Managing permissions for a group)*

1. 権限グループを選択し、**{{t:organization.access.modals.managePermissionsTitle}}**オプションをクリックします。
2. **{{t:organization.access.modals.currentPermissionsTab}}**タブでグループのアクセス権を確認します。
3. 各アクションの横にある赤い**{{t:common.delete}}**ボタンをクリックすることで、権限を取り消すことができます。
4. **{{t:organization.access.modals.addPermissionsTab}}**タブをクリックして、グループに新しい権限を追加します。

![権限管理パネル - 割り当てられた権限リスト](/assets/images/user-guide/22_access_permission.png)
*(図22: 権限グループの権限管理)*

> **ヒント**: 最小権限の原則に基づいて権限を付与してください。不要な権限を定期的に確認して削除してください。

---

## 2.4 マシン

マシンセクションでは、サーバーとリポジトリリソースを管理できます。

### 2.4.1 マシンの追加

![Adding machines walkthrough](/assets/videos/user-guide/02-04-01-machine-create.webm)
*(動画: Adding a new machine)*

1. 左メニューから**{{t:common.navigation.machines}}**タブに移動します。
2. 右上の**{{t:machines.createMachine}}**ボタンをクリックします。

![マシンページ - 「マシンの追加」ボタン](/assets/images/user-guide/23_machines_add.png)
*(図23: マシン管理ホームページ)*

3. 開いたフォームに入力します:
   - **{{t:machines.machineName}}**: 一意の名前を入力(例: 「server-01」)
   - **{{t:common.vaultEditor.fields.MACHINE.ip.label}}**: マシンのIPアドレスを入力(例: 192.168.111.11)
   - **{{t:common.vaultEditor.fields.MACHINE.datastore.label}}**: ストレージディレクトリを指定(例: /mnt/rediacc)
   - **{{t:common.vaultEditor.fields.MACHINE.user.label}}**: SSHユーザー名を入力
   - **{{t:common.vaultEditor.fields.MACHINE.port.label}}**: ポート番号を入力(デフォルト: 22)
   - **{{t:common.vaultEditor.fields.MACHINE.ssh_password.label}}**: パスワードを入力(オプション)

![マシン追加フォーム - すべてのフィールド](/assets/images/user-guide/24_machine_create.png)
*(図24: 新規マシン追加フォーム - マシン名、ネットワーク設定、SSH認証情報)*

4. **{{t:common.vaultEditor.testConnection.button}}**ボタンをクリックして接続を確認します。
5. テストが成功したら、**{{t:common.actions.create}}**ボタンをクリックします。

> **ヒント**: 「マシン作成後に自動的にセットアップを開始」オプションがチェックされている場合、マシンは自動的に追加のセットアップステップを実行します。

![マシン作成完了 - タスク追跡ウィンドウ](/assets/images/user-guide/25_machine_create_complete.png)
*(図25: マシンが正常に作成された後のタスク追跡ウィンドウ)*

6. ステージを確認します: **{{t:queue.trace.assigned}}** → **処理** → **{{t:queue.statusCompleted}}**
7. **{{t:common.actions.close}}**ボタンをクリックして操作を閉じます。

> **ヒント**: 「{{t:common.actions.refresh}}」ボタンをクリックして、最新のステータスを手動で確認できます。

### 2.4.2 接続テスト

![Connectivity test walkthrough](/assets/videos/user-guide/02-04-02-connectivity-test.webm)
*(動画: Running a connectivity test)*

既存のマシンの接続ステータスを確認できます。

1. **{{t:machines.connectivityTest}}**ボタンをクリックします。

![接続テストボタン](/assets/images/user-guide/26_connectivity_test_button.png)
*(図26: マシンアクションツールバーの接続テストボタン)*

2. テストするマシンのリストを確認します。
3. **{{t:machines.runTest}}**ボタンをクリックします。
4. 成功した結果は緑色で、失敗は赤色で表示されます。

![接続テストフォーム - マシンリスト](/assets/images/user-guide/27_connectivity_test_form.png)
*(図27: 接続テストフォーム - 選択したマシンのping機能)*

> **ヒント**: テストが失敗した場合は、マシンのIPアドレスとSSH設定を確認してください。

### 2.4.3 マシンリストの更新

![Machine list refresh walkthrough](/assets/videos/user-guide/02-04-03-machine-refresh.webm)
*(動画: Refreshing the machine list)*

**{{t:common.actions.refresh}}**ボタンをクリックしてマシンリストを更新します。

![更新ボタン](/assets/images/user-guide/28_refresh.png)
*(図28: マシンアクションツールバーの更新ボタン)*

### 2.4.4 マシンの詳細

![Machine details walkthrough](/assets/videos/user-guide/02-04-04-machine-details.webm)
*(動画: Viewing machine details)*

1. 詳細を表示したいマシンを選択します。
2. 目のアイコンボタン(**{{t:common.viewDetails}}**)をクリックします。

![詳細表示ボタン](/assets/images/user-guide/29_view_details_button.png)
*(図29: マシンアクション列の目のアイコン)*

3. 右側にマシン詳細パネルが開きます:
   - **ホスト名**: マシン名
   - **稼働時間**: 稼働時間
   - **{{t:queue.trace.operatingSystem}}**: OSとバージョン
   - **{{t:queue.trace.kernelVersion}}**: カーネルバージョン
   - **CPU**: プロセッサ情報
   - **システム時刻**: システムクロック

![マシン詳細パネル - システム情報](/assets/images/user-guide/30_machine_view_details.png)
*(図30: マシン詳細パネル - ホスト名、稼働時間、OS、カーネル、CPU情報)*

> **ヒント**: OSの互換性とリソースの可用性を確認するために、この情報を定期的に確認してください。

### 2.4.5 マシンの編集

![Machine editing walkthrough](/assets/videos/user-guide/02-04-05-machine-edit.webm)
*(動画: Editing machine settings)*

1. 編集したいマシンを選択します。
2. 鉛筆アイコンボタン(**{{t:common.actions.edit}}**)をクリックします。

![編集ボタン](/assets/images/user-guide/31_edit_button.png)
*(図31: マシンアクション列の鉛筆アイコン)*

3. 必要な変更を行います。
4. **{{t:common.vaultEditor.testConnection.button}}**ボタンをクリックします。
5. 接続が成功したら、**{{t:common.save}}**ボタンをクリックします。

![マシン編集フォーム](/assets/images/user-guide/32_edit_form.png)
*(図32: マシン編集フォーム - マシン名、リージョン、vault構成)*

> **ヒント**: 重要な設定を変更した後は、必ず「接続テスト」を実行してください。

### 2.4.6 マシントレース

![Machine trace walkthrough](/assets/videos/user-guide/02-04-06-machine-trace.webm)
*(動画: Viewing machine audit history)*

1. マシンを選択し、時計アイコンボタン(**{{t:common.actions.trace}}**)をクリックします。

![トレースボタン](/assets/images/user-guide/33_trace_button.png)
*(図33: マシンアクション列の時計アイコン)*

2. 監査履歴ウィンドウで操作を確認します:
   - **{{t:resources.audit.action}}**: 実行された操作のタイプ
   - **詳細**: 変更されたフィールド
   - **{{t:resources.audit.performedBy}}**: アクションを実行したユーザー
   - **タイムスタンプ**: 日付と時刻

![マシン監査履歴ウィンドウ](/assets/images/user-guide/34_trace_list.png)
*(図34: 監査履歴 - すべての変更のリスト)*

> **ヒント**: タイムスタンプ列をクリックして、時系列で変更を表示できます。

### 2.4.7 マシンの削除

![Machine deletion walkthrough](/assets/videos/user-guide/02-04-07-machine-delete.webm)
*(動画: Deleting a machine)*

1. 削除したいマシンを選択します。
2. ゴミ箱アイコンボタン(**{{t:common.delete}}**)をクリックします。

![削除ボタン](/assets/images/user-guide/35_delete_button.png)
*(図35: マシンアクション列のゴミ箱アイコン)*

3. 確認ウィンドウの**{{t:common.delete}}**ボタンをクリックします。

![マシン削除確認ウィンドウ](/assets/images/user-guide/36_delete_form.png)
*(図36: 「このマシンを削除してもよろしいですか?」確認ウィンドウ)*

> **警告**: マシンが削除されると、その上のすべてのリポジトリ定義も削除されます。このアクションは元に戻せません。

### 2.4.8 リモート操作

![Remote operations walkthrough](/assets/videos/user-guide/02-04-08-remote-hello.webm)
*(動画: Running remote operations on a machine)*

マシン上でさまざまなリモート操作を実行できます。

1. マシンを選択し、**{{t:common.actions.remote}}**ボタンをクリックします。
2. ドロップダウンメニューのオプションを確認します:
   - **{{t:machines.runAction}}**: マシン上で関数を実行
   - **{{t:common.vaultEditor.testConnection.button}}**: マシンにpingを実行

![リモートメニュー - サーバー上で実行と接続テスト](/assets/images/user-guide/37_remote_button.png)
*(図37: リモートボタン - 選択したマシン上での関数実行メニュー)*

> **ヒント**: 関数を実行する前に、「{{t:common.vaultEditor.testConnection.button}}」オプションを使用してマシンにアクセスできることを確認してください。

#### セットアップ

1. **{{t:machines.runAction}}**オプションを選択します。
2. **{{t:functions.availableFunctions}}**リストで**セットアップ**関数を見つけます。
3. 関数名をクリックして選択します。

![マシン関数リスト - セットアップ関数](/assets/images/user-guide/38_server_setup.png)
*(図38: セットアップ関数 - 必要なツールと構成でマシンを準備します)*

> **ヒント**: 新しいマシンをセットアップする際は、まず「セットアップ」関数を実行することをお勧めします。

#### 接続確認(こんにちは)

1. **{{t:machines.runAction}}** > **こんにちは**関数を選択します。
2. **{{t:common.actions.addToQueue}}**ボタンをクリックします。

![こんにちは関数選択](/assets/images/user-guide/39_remote_hello.png)
*(図39: Hello関数 - シンプルなテスト関数、ホスト名を返します)*

3. タスク追跡ウィンドウで結果を確認します。
4. **{{t:queue.trace.responseConsole}}**セクションでマシンの出力を確認します。

![こんにちは関数完了](/assets/images/user-guide/40_remote_hello_complete.png)
*(図40: Hello関数が正常に完了 - ホスト名レスポンス)*

> **ヒント**: Hello関数は、マシンの接続を確認するのに最適です。

#### 高度な操作

1. **{{t:common.actions.remote}}** > **{{t:machines.runAction}}** > **{{t:common.actions.advanced}}**のパスに従います。
2. 利用可能な関数を確認します: セットアップ、Hello、ping、ssh_test、uninstall
3. 必要な関数を選択し、**{{t:common.actions.addToQueue}}**ボタンをクリックします。

![高度な関数リスト](/assets/images/user-guide/41_remote_advanced.png)
*(図41: 高度なオプション - 高度な関数リスト)*

> **ヒント**: 高度な関数を使用する前に、マシンのセットアップが完了していることを確認してください。

#### クイック接続テスト

![リモートメニュー - 接続テスト](/assets/images/user-guide/42_connectivity_test.png)
*(図42: リモートメニューからの接続テストオプション)*

> **ヒント**: マシンにSSHまたはネットワークの問題がある場合、このテストで問題を素早く特定できます。

---

## 2.5 リポジトリの作成と操作

リポジトリは、バックアップデータが保存される基本的な単位です。

### 2.5.1 リポジトリの作成

![Repository creation walkthrough](/assets/videos/user-guide/02-05-01-repository-create.webm)
*(動画: Creating a new repository)*

1. **{{t:common.navigation.machines}}**タブからマシンを選択します。
2. 右上の**{{t:machines.createRepository}}**ボタンをクリックします。

![リポジトリ作成ボタン](/assets/images/user-guide/43_create_repo_add.png)
*(図43: マシンリポジトリ管理画面 - リポジトリ作成ボタン)*

3. フォームに入力します:
   - **{{t:common.vaultEditor.fields.REPOSITORY.name.label}}**: リポジトリ名を入力します（例：postgresql）
   - **{{t:resources.repositories.size}}**: リポジトリサイズを入力します（例：2GB）
   - **{{t:resources.repositories.repositoryGuid}}**: 自動生成された認証情報を確認します
   - **{{t:resources.templates.selectTemplate}}**: テンプレートを選択します（例：databases_postgresql）

![リポジトリ作成フォーム](/assets/images/user-guide/44_repo_form.png)
*(図44: リポジトリ作成フォーム - リポジトリ名、サイズ、テンプレート選択)*

4. **{{t:common.actions.create}}**ボタンをクリックします。

> **ヒント**: 認証情報IDは自動生成されます。手動で変更することはお勧めしません。

5. タスク追跡ウィンドウでステージを確認します: **{{t:queue.trace.assigned}}** → **処理** → **{{t:queue.statusCompleted}}**

![リポジトリ作成完了](/assets/images/user-guide/45_repo_complete.png)
*(図45: リポジトリ作成がキューに入りました - タスク監視)*

6. **{{t:common.actions.close}}**ボタンをクリックします。

> **ヒント**: タスクは通常1〜2分以内に完了します。

![リポジトリリスト](/assets/images/user-guide/46_repo_list.png)
*(図46: 作成されたリポジトリがリストに表示されます)*

### 2.5.2 リポジトリフォーク

![Repository fork walkthrough](/assets/videos/user-guide/02-05-02-repository-fork.webm)
*(動画: Forking a repository)*

既存のリポジトリをコピーして新しいリポジトリを作成できます。

1. コピーしたいリポジトリを選択します。
2. **fx**(関数)メニューをクリックします。
3. **fork**オプションをクリックします。

![fxメニュー - forkオプション](/assets/images/user-guide/47_fork_button.png)
*(図47: 右側のfxメニュー - リポジトリ操作)*

4. **{{t:functions.functions.fork.params.tag.label}}**フィールドに新しいタグを入力します（例：2025-12-06-20-37-08）。
5. **{{t:common.actions.addToQueue}}**ボタンをクリックします。

![フォーク構成フォーム](/assets/images/user-guide/48_fork_form.png)
*(図48: フォーク操作でリポジトリの新しいタグを指定)*

6. **{{t:queue.statusCompleted}}**メッセージを待ち、**{{t:common.actions.close}}**ボタンをクリックします。

![フォーク完了](/assets/images/user-guide/49_repo_completed.png)
*(図49: フォーク操作が正常に完了)*

> **ヒント**: デフォルトの日時形式でタグを作成することは良い習慣です。フォーク操作は元のリポジトリに影響を与えません。

### 2.5.3 リポジトリUp

![Repository up walkthrough](/assets/videos/user-guide/02-05-03-repository-up.webm)
*(動画: Starting a repository)*

リポジトリをアクティベートするには:

1. リポジトリを選択し、**fx** > **up**パスに従います。

![Up操作](/assets/images/user-guide/50_repo_up.png)
*(図50: fxメニューからの「up」オプション - リポジトリの起動)*

2. **{{t:queue.statusCompleted}}**メッセージを待ちます。

![Up完了](/assets/images/user-guide/51_repo_up_complete.png)
*(図51: リポジトリ起動完了)*

> **ヒント**: 「Up」操作は、リポジトリで定義されたDockerサービスを起動します。

### 2.5.4 リポジトリDown

![Repository down walkthrough](/assets/videos/user-guide/02-05-04-repository-down.webm)
*(動画: Stopping a repository)*

アクティブなリポジトリを停止するには:

1. リポジトリを選択し、**fx** > **down**パスに従います。

![Down操作](/assets/images/user-guide/52_down_button.png)
*(図52: fxメニューからの「down」オプション - リポジトリのシャットダウン)*

2. **{{t:queue.statusCompleted}}**メッセージを待ちます。

![Down完了](/assets/images/user-guide/53_down_completed.png)
*(図53: リポジトリシャットダウン完了)*

> **ヒント**: 「Down」操作は、リポジトリを安全にシャットダウンします。データは失われず、サービスのみが停止されます。

### 2.5.5 デプロイ

![Repository deploy walkthrough](/assets/videos/user-guide/02-05-05-repository-deploy.webm)
*(動画: Deploying a repository)*

リポジトリを別の場所にデプロイするには:

1. リポジトリを選択し、**fx** > **deploy**パスに従います。

![Deploy操作](/assets/images/user-guide/54_deploy_button.png)
*(図54: fxメニューからの「deploy」オプション)*

2. **{{t:functions.functions.fork.params.tag.label}}**フィールドにデプロイするバージョンを入力します。
3. **{{t:functions.functions.backup_deploy.params.machines.label}}**フィールドでターゲットマシンを選択します。
4. **{{t:functions.checkboxOptions.overrideExistingFile}}**オプションをチェックします（該当する場合）。
5. **{{t:common.actions.addToQueue}}**ボタンをクリックします。

![Deployフォーム](/assets/images/user-guide/55_deploy_form.png)
*(図55: デプロイ操作の構成 - タグ、ターゲットマシン、オプション)*

6. **{{t:queue.statusCompleted}}**メッセージを待ちます。

![Deploy完了](/assets/images/user-guide/56_deploy_completed.png)
*(図56: リポジトリデプロイ完了)*

> **ヒント**: デプロイ操作が完了したら、「up」コマンドを実行してターゲットマシンでリポジトリを起動できます。

### 2.5.6 バックアップ

![Repository backup walkthrough](/assets/videos/user-guide/02-05-06-repository-backup.webm)
*(動画: Backing up a repository)*

リポジトリをバックアップするには:

1. リポジトリを選択し、**fx** > **backup**パスに従います。

![Backup操作](/assets/images/user-guide/57_backup_button.png)
*(図57: fxメニューからの「backup」オプション)*

2. フォームに入力します:
   - **{{t:functions.functions.fork.params.tag.label}}**: 説明的な名前を入力します（例：backup01012025）
   - **{{t:functions.functions.backup_create.params.storages.label}}**: バックアップの場所を選択します
   - **{{t:functions.checkboxOptions.overrideExistingFile}}**: オプションを有効または無効にします
   - **{{t:functions.functions.backup_deploy.params.checkpoint.label}}**: 設定を確認します

![Backupフォーム](/assets/images/user-guide/58_backup_form.png)
*(図58: バックアップ構成フォーム - ターゲット、ファイル名、オプション)*

3. **{{t:common.actions.addToQueue}}**ボタンをクリックします。

> **ヒント**: バックアップタグには説明的な名前を使用してください。大規模なリポジトリの場合は、チェックポイントを有効にすることを検討してください。

4. **{{t:queue.statusCompleted}}**メッセージを待ちます。

![Backup完了](/assets/images/user-guide/59_backup_completed.png)
*(図59: バックアップタスクが正常に完了)*

> **ヒント**: 完了ステータスに達するまで辛抱強く待ってください。大規模なバックアップには数分かかる場合があります。

### 2.5.7 テンプレートの適用

![Template application walkthrough](/assets/videos/user-guide/02-05-07-repository-templates.webm)
*(動画: Applying a template to a repository)*

リポジトリに新しいテンプレートを適用するには:

1. リポジトリを選択し、**fx** > **{{t:resources.templates.selectTemplate}}**パスに従います。

![テンプレート操作](/assets/images/user-guide/60_templates_button.png)
*(図60: fxメニューからの「テンプレート」オプション)*

2. 検索ボックスに入力してテンプレートをフィルタリングします。
3. 目的のテンプレートをクリックして選択します(選択したテンプレートは太い枠で強調表示されます)。
4. **{{t:common.actions.addToQueue}}**ボタンをクリックします。

![テンプレート選択フォーム](/assets/images/user-guide/61_templates_form.png)
*(図61: 利用可能なテンプレートの検索と選択)*

> **ヒント**: 検索ボックスを使用してテンプレートをすばやく検索します。テンプレートの機能について詳しくは{{t:common.viewDetails}}を使用してください。

5. **{{t:queue.statusCompleted}}**メッセージを待ちます。

![テンプレート適用完了](/assets/images/user-guide/62_templates_completed.png)
*(図62: テンプレート適用が正常に完了)*

### 2.5.8 アンマウント

![Repository unmount walkthrough](/assets/videos/user-guide/02-05-08-repository-unmount.webm)
*(動画: Unmounting a repository)*

リポジトリを切断するには:

1. リポジトリを選択し、**fx** > **{{t:common.actions.advanced}}** > **{{t:resources.repositories.unmount}}**のパスに従います。

![Unmount操作](/assets/images/user-guide/63_unmount_button.png)
*(図63: 高度なメニューの「アンマウント」オプション)*

2. **{{t:queue.statusCompleted}}**メッセージを待ちます。

![Unmount完了](/assets/images/user-guide/64_unmount_completed.png)
*(図64: アンマウント操作完了)*

> **ヒント**: アンマウントする前に、リポジトリ上にアクティブな操作がないことを確認してください。アンマウント後、リポジトリにアクセスできなくなります。

### 2.5.9 拡張

![Repository expand walkthrough](/assets/videos/user-guide/02-05-09-repository-expand.webm)
*(動画: Expanding repository size)*

リポジトリサイズを増やすには:

1. リポジトリを選択し、**fx** > **{{t:common.actions.advanced}}** > **{{t:functions.functions.repository_expand.name}}**のパスに従います。

![Expand操作](/assets/images/user-guide/65_expand_button.png)
*(図65: 高度なメニューの「拡張」オプション)*

2. **{{t:functions.functions.repository_expand.params.size.label}}**フィールドに希望のサイズを入力します。
3. 右側のドロップダウンから単位を選択します(GB、TB)。
4. **{{t:common.actions.addToQueue}}**ボタンをクリックします。

![Expandフォーム](/assets/images/user-guide/66_expand_form.png)
*(図66: リポジトリサイズを増やすための新しいサイズパラメータ)*

> **ヒント**: 現在のサイズより小さい値を入力しないでください。リポジトリ拡張中にサービスは中断されません。

5. **{{t:queue.statusCompleted}}**メッセージを待ちます。

![Expand完了](/assets/images/user-guide/67_expand_completed.png)
*(図67: リポジトリ拡張完了)*

### 2.5.10 名前変更

![Repository rename walkthrough](/assets/videos/user-guide/02-05-10-repository-rename.webm)
*(動画: Renaming a repository)*

リポジトリ名を変更するには:

1. リポジトリを選択し、**fx** > **{{t:common.actions.rename}}**のパスに従います。

![Rename操作](/assets/images/user-guide/68_rename_button.png)
*(図68: fxメニューからの「名前変更」オプション)*

2. 新しいリポジトリ名を入力します。
3. **{{t:common.save}}**ボタンをクリックします。

![Renameフォーム](/assets/images/user-guide/69_rename_form.png)
*(図69: 新しいリポジトリ名を入力するダイアログ)*

> **ヒント**: リポジトリ名は、リポジトリのタイプと目的を反映する意味のあるものにする必要があります。特殊文字は避けてください。

### 2.5.11 リポジトリの削除

![Repository deletion walkthrough](/assets/videos/user-guide/02-05-11-repository-delete.webm)
*(動画: Deleting a repository)*

リポジトリを完全に削除するには:

1. リポジトリを選択し、**fx** > **{{t:resources.repositories.deleteRepository}}**のパスに従います。

![リポジトリ削除操作](/assets/images/user-guide/70_delete_repo_button.png)
*(図70: fxメニューからの「リポジトリを削除」オプション - 赤)*

2. 確認ウィンドウの**{{t:common.delete}}**ボタンをクリックします。

> **警告**: リポジトリの削除は元に戻せません。削除する前にリポジトリデータがバックアップされていることを確認してください。

### 2.5.12 リポジトリの詳細

![Repository details walkthrough](/assets/videos/user-guide/02-05-12-repository-details.webm)
*(動画: Viewing repository details)*

リポジトリに関する詳細情報を取得するには:

1. リポジトリを選択します。
2. 目のアイコン(**{{t:common.viewDetails}}**)をクリックします。

![詳細表示ボタン](/assets/images/user-guide/71_repo_view_button.png)
*(図71: リポジトリ詳細を開く目のアイコン)*

3. 詳細パネルの情報を確認します:
   - **リポジトリ名**とタイプ
   - **チーム**: 所属するチーム
   - **マシン**: 配置されているマシン
   - **Vaultバージョン**: 暗号化バージョン
   - **リポジトリGUID**: 一意の識別子
   - **ステータス**: マウント/アンマウントステータス
   - **イメージサイズ**: 合計サイズ
   - **最終更新日**: 最終更新日

![リポジトリ詳細パネル](/assets/images/user-guide/72_repo_details_view.png)
*(図72: 選択したリポジトリに関する包括的な情報)*

> **ヒント**: このパネルに表示されるすべての情報は参照用です。リポジトリ操作にはfxメニューオプションを使用してください。

---

## 2.6 リポジトリ接続操作

さまざまな方法を使用してリポジトリに接続できます。

### 2.6.1 デスクトップアプリケーション接続

![Desktop connection walkthrough](/assets/videos/user-guide/02-06-01-desktop-connection.webm)
*(動画: Connecting via desktop application)*

1. リポジトリ行の**{{t:resources.localActions.local}}**ボタンをクリックします。

![ローカル接続ボタン](/assets/images/user-guide/73_repo_connection_local.png)
*(図73: リポジトリ行の「ローカル」ボタン - デスクトップアプリケーションアクセス)*

2. ドロップダウンメニューからアクセス方法を選択します:
   - **{{t:resources.localActions.openInDesktop}}**: グラフィカルインターフェースでアクセス
   - **{{t:resources.localCommandBuilder.vscodeTab}}**: コードエディタで開く
   - **{{t:common.terminal.terminal}}**: コマンドラインでアクセス
   - **{{t:resources.localActions.showCLICommands}}**: コマンドラインツール

![接続オプションメニュー](/assets/images/user-guide/74_repo_connection.png)
*(図74: リポジトリ接続メニュー - 異なるアクセスパス)*

> **ヒント**: VS Codeで作業している場合、「{{t:resources.localCommandBuilder.vscodeTab}}」オプションが最速の統合を提供します。

3. ブラウザが許可を求めたとき、**{{t:common.vscodeSelection.open}}**ボタンをクリックします。

![デスクトップアプリケーション開く許可](/assets/images/user-guide/75_desktop_open_page.png)
*(図75: デスクトップアプリケーションを開く許可をブラウザが要求)*

> **ヒント**: デスクトップアプリケーションを開くたびに許可を与えたくない場合は、「常に許可」オプションをチェックしてください。

---

## 2.7 設定

設定セクションから、プロフィールとシステム設定を管理できます。

### 2.7.1 パスワード変更

![Password change walkthrough](/assets/videos/user-guide/02-07-03-password-change.webm)
*(動画: Changing your password)*

1. 左メニューから**{{t:common.navigation.settings}}** > **{{t:common.navigation.settingsProfile}}**タブに移動します。

![プロフィール設定ページ](/assets/images/user-guide/76_profiles_button.png)
*(図76: 設定 → プロフィールページ - 個人vault設定)*

2. **{{t:settings.personal.changePassword.submit}}**ボタンをクリックします。

![パスワード変更ボタン](/assets/images/user-guide/77_profiles_change_button.png)
*(図77: 個人設定セクションの「パスワードを変更」ボタン)*

3. 新しいパスワードを入力します。パスワード要件:
   - 8文字以上
   - 大文字と小文字を含む必要がある
   - 少なくとも1つの数字を含む必要がある
   - 少なくとも1つの特殊文字を含む必要がある

4. **{{t:settings.personal.changePassword.confirmPasswordLabel}}**フィールドに同じパスワードを再入力します。
5. **{{t:settings.personal.changePassword.submit}}**ボタンをクリックします。

![パスワード変更フォーム](/assets/images/user-guide/78_profiles_change_form.png)
*(図78: パスワード変更フォーム - セキュリティ要件が表示)*

> **ヒント**: 強力なパスワードを作成する際は、ランダムな組み合わせを使用してください。

---

## 2.8 ストレージ

ストレージセクションでは、バックアップデータが保存される物理的なエリアを管理できます。

### 2.8.1 ストレージの追加

![Storage creation walkthrough](/assets/videos/user-guide/02-08-01-storage-create.webm)
*(動画: Adding a storage location)*

1. 左メニューから**{{t:common.navigation.storage}}**タブに移動します。
2. **{{t:resources.storage.createStorage}}**ボタンをクリックします。

![ストレージ追加ボタン](/assets/images/user-guide/79_storage_add_button.png)
*(図79: ストレージ管理ページ - 「ストレージを追加」ボタン)*

3. フォームに入力します:
   - **{{t:common.vaultEditor.fields.STORAGE.name.label}}**: 説明的な名前を入力します
   - **{{t:common.vaultEditor.fields.STORAGE.provider.label}}**: 選択します（例：s3）
   - **{{t:common.vaultEditor.fields.STORAGE.description.label}}**: オプションの説明を追加します
   - **{{t:common.vaultEditor.fields.STORAGE.noVersioning.label}}**: オプション
   - **{{t:common.vaultEditor.fields.STORAGE.parameters.label}}**: rcloneフラグ（例：--transfers 4）

![ストレージ作成フォーム](/assets/images/user-guide/80_storage_form.png)
*(図80: ストレージ追加フォーム - 名前、プロバイダー、説明、パラメータ)*

4. **{{t:common.actions.create}}**ボタンをクリックします。

> **ヒント**: 追加パラメータは、ストレージパフォーマンスを最適化するためのrcloneフラグを受け入れます。

---

## 2.9 認証情報

認証情報セクションでは、リポジトリのアクセス情報を安全に管理できます。

### 2.9.1 認証情報の編集

![Credential editing walkthrough](/assets/videos/user-guide/02-09-01-credential-edit.webm)
*(動画: Editing credentials)*

1. 左メニューから**{{t:common.navigation.credentials}}**タブに移動します。
2. 編集したいレコードを選択します。
3. **{{t:common.actions.edit}}**ボタンをクリックします。

![認証情報リスト](/assets/images/user-guide/81_credentials.png)
*(図81: 認証情報ページ - リポジトリ名、チーム、管理ボタン)*

4. 必要に応じて**{{t:common.vaultEditor.fields.REPOSITORY.name.label}}**を変更します。
5. **{{t:common.save}}**ボタンで保存します。

![認証情報編集フォーム](/assets/images/user-guide/82_credentials_form.png)
*(図82: リポジトリ名編集フォーム - vault構成フィールド)*

> **ヒント**: 認証情報は暗号化されて保存され、デプロイ時にのみ復号化されます。

### 2.9.2 認証情報トレース

![Credential trace walkthrough](/assets/videos/user-guide/02-09-02-credential-trace.webm)
*(動画: Viewing credential audit history)*

1. トレースするレコードを選択します。
2. **{{t:common.actions.trace}}**ボタンをクリックします。

![トレースボタン](/assets/images/user-guide/83_credentials_trace_button.png)
*(図83: 認証情報テーブルの「トレース」ボタン)*

3. 監査履歴を確認します。
4. **{{t:common.actions.export}}**ボタンから形式を選択します：**{{t:common.exportCSV}}**または**{{t:common.exportJSON}}**。

![認証情報監査履歴](/assets/images/user-guide/84_credentials_list_export.png)
*(図84: 認証情報リスト - エクスポートオプション)*

> **ヒント**: トレース機能は、セキュリティ監査目的で認証情報の使用状況を追跡します。

### 2.9.3 認証情報の削除

![Credential deletion walkthrough](/assets/videos/user-guide/02-09-03-credential-delete.webm)
*(動画: Deleting a credential)*

1. 削除したいレコードを選択します。
2. 赤い**{{t:common.delete}}**ボタンをクリックします。

![削除ボタン](/assets/images/user-guide/85_credentials_delete.png)
*(図85: 認証情報ページの赤い「削除」ボタン)*

3. 確認ウィンドウの**{{t:common.delete}}**ボタンをクリックします。

![削除確認](/assets/images/user-guide/86_credentials_delete_confirm.png)
*(図86: 削除確認ダイアログ - 元に戻せないアクション警告)*

> **警告**: 削除する前に、認証情報が他のマシンや他の操作で使用されていないことを確認してください。削除する前に重要な認証情報のバックアップがあることを確認してください。

---

## 2.10 キュー

キューセクションでは、システム内の保留中および完了した操作を追跡できます。

### 2.10.1 キュー操作

![Queue operations walkthrough](/assets/videos/user-guide/02-10-01-queue-operations.webm)
*(動画: Managing queue operations)*

1. 左メニューから**{{t:common.navigation.queue}}**タブをクリックします。

![キューページ](/assets/images/user-guide/87_queue_button.png)
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

![キューエクスポート](/assets/images/user-guide/88_queue_export.png)
*(図88: キューリスト - エクスポートオプション)*

> **ヒント**: 「{{t:queue.filters.onlyStale}}」オプションは、長時間処理中のタスクを見つけるのに役立ちます。タスク実行傾向を分析するために、キュー履歴を定期的にエクスポートしてください。

---

## 2.11 監査

監査セクションは、システムで実行されたすべての操作の記録を保持します。

### 2.11.1 監査レコード

![Audit records walkthrough](/assets/videos/user-guide/02-11-01-audit-records.webm)
*(動画: Viewing system audit records)*

1. 左メニューから**{{t:common.navigation.audit}}**タブをクリックします。

![監査リスト](/assets/images/user-guide/89_audit_list.png)
*(図89: 監査ページ - すべてのシステム操作の詳細な記録)*

2. 監査レコードをフィルタリング:
   - **日付範囲**: 特定の期間でフィルタリング
   - **エンティティタイプ**: リクエスト、マシン、キューなどでフィルタリング
   - **検索**: テキスト検索を実行

3. 各レコードの情報を確認:
   - **タイムスタンプ**: 操作の日付と時刻
   - **アクション**: 操作のタイプ(作成、編集、削除など)
   - **エンティティタイプ**: 影響を受けたオブジェクトのタイプ
   - **エンティティ名**: 特定のオブジェクト識別子
   - **ユーザー**: 操作を実行したユーザー
   - **詳細**: 操作に関する追加情報

4. **{{t:common.actions.export}}**ボタンから形式を選択します：**{{t:common.exportCSV}}**または**{{t:common.exportJSON}}**。

![監査エクスポート](/assets/images/user-guide/90_audit_export.png)
*(図90: 監査レコードエクスポート - CSVとJSONオプション)*

> **ヒント**: 監査レコードは、セキュリティとコンプライアンスの目的でシステムのすべてのアクティビティを追跡するために重要です。監査レコードを定期的にエクスポートし、安全な場所に保管してください。

---

**© 2025 Rediacc Platform – All Rights Reserved.**
