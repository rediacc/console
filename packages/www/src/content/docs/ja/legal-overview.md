---
title: "コンプライアンス概要"
description: "Rediaccのセルフホスト型アーキテクチャがデータ保護、プライバシー、セキュリティコンプライアンス要件にどのように対応するか。"
category: "Legal"
order: 0
language: ja
sourceHash: "e20385eb9adfe180"
sourceCommit: "43aec6b89a55f69f994476d3a124e749d4d2223f"
---

Rediaccはお客様のインフラストラクチャ上で完全に動作します。環境クローン、バックアップ、デプロイの操作中、データがマシンから外に出ることはありません。お客様がデータ管理者とデータ処理者の両方であり続けます。サードパーティのSaaSがお客様のデータを扱うことはありません。

このセクションでは、Rediaccの技術的機能を主要なコンプライアンスフレームワークの要件にマッピングします。各ページは、公式法的テキストへの条項レベルの参照とともに、特定の規制を取り上げています。

## コンプライアンスマトリックス

| フレームワーク | 対象範囲 | Rediaccの主要機能 |
|-------------|---------|------------------|
| [GDPR](/ja/docs/legal-gdpr) | EUのデータ保護とプライバシー | 同一マシン上でのCoWクローン、LUKS2暗号化、ゼロ知識設定ストア、監査ログ、`rdc repo delete`による消去権 |
| [SOC 2](/ja/docs/legal-soc2) | サービス組織向けトラストサービス基準 | 保存時暗号化、ゼロ知識設定同期、ネットワーク分離、監査証跡、バックアップとリカバリ |
| [HIPAA](/ja/docs/legal-hipaa) | 米国の医療情報保護 | LUKS2暗号化、ゼロ知識設定ストア、SSHのみのアクセス、分離されたDocker daemon、伝送セキュリティ |
| [CCPA](/ja/docs/legal-ccpa) | カリフォルニア州消費者プライバシー権 | セルフホスト型（データの販売/共有なし）、ゼロ知識暗号化、暗号化削除、リポジトリごとのデータインベントリ |
| [ISO 27001](/ja/docs/legal-iso27001) | 情報セキュリティ管理統制 | 資産管理、暗号統制、ゼロ知識設定ストア、アクセス制御、運用セキュリティ |
| [PCI DSS](/ja/docs/legal-pci-dss) | ペイメントカードデータ保護 | アーキテクチャによるネットワークセグメンテーション、必須暗号化、監査ログ、セルフホストによるスコープ削減 |
| [NIS2とDORA](/ja/docs/legal-nis2-dora) | EUサイバーセキュリティと金融レジリエンス | サプライチェーンリスクの排除、CoWクローンによるレジリエンステスト、暗号化、インシデント検出 |
| [データ主権](/ja/docs/legal-data-sovereignty) | グローバルデータレジデンシー法（PIPL、LGPD、KVKK、PIPA等） | セルフホスト型 = データがお客様の管轄から出ることはありません。越境移転なし、十分性評価なし |

## アーキテクチャの基盤

このセクションのすべてのコンプライアンスフレームワークは、同じ技術的特性に基づいています：

- **保存時暗号化**: すべてのリポジトリはLUKS2 AES-256で暗号化されます。認証情報はオペレーターのローカル設定にのみ保存され、サーバーには保存されません。
- **ネットワーク分離**: 各リポジトリは独自のDocker daemon、ループバックIPサブネット（/26）、iptablesルールを持ちます。異なるリポジトリのコンテナは通信できません。
- **コピーオンライトクローン**: `rdc repo fork`はファイルシステムのreflink（`cp --reflink=always`）を使用します。データはネットワーク転送なしで同一マシン上に複製されます。
- **監査ログ**: 認証（ログイン、2FA、パスワード変更、セッション失効）、APIトークンのライフサイクル、設定ストア操作、サブスクリプション/ライセンスアクティビティをカバーする40以上のイベントタイプ。管理ダッシュボードと`rdc audit` CLIからアクセスできます。マシンレベルの操作（フォーク、バックアップ、デプロイ）はマシン自体でSSHとシステムログを介して処理されます。
- **暗号化バックアップ**: `rdc repo push/pull`はSSH経由でデータを転送します。バックアップ先はLUKS暗号化ボリュームを受け取ります。
- **ゼロ知識設定ストア**: デバイス間のオプションの暗号化設定同期。設定はアップロード前にクライアント側でAES-256-GCMで暗号化されます。サーバーは不透明なblobのみを保存します。サーバーはSSH鍵、認証情報、IPアドレス、平文の設定データを読み取ることができません。鍵導出はpasskey PRF extension + HKDFとドメイン分離を使用します。メンバーアクセスはX25519鍵交換で管理され、失効は即時です。

これらの機能の詳細については、[アーキテクチャ](/ja/docs/architecture)、[リポジトリ](/ja/docs/repositories)、[設定ストレージ](/ja/docs/config-storage)、[アカウントセキュリティ](/ja/docs/account-security)を参照してください。

## なぜ重要なのか

コンプライアンス違反は高額です。以下の執行事例は、Rediaccのアーキテクチャが構造的に防止する問題を含んでいます：

| インシデント | 罰金 | 何が問題だったか |
|------------|------|----------------|
| [Meta: EU-USデータ転送](https://www.dataprotection.ie/en/news-media/press-releases/Data-Protection-Commission-announces-conclusion-of-inquiry-into-Meta-Ireland) | 12億EUR | 適切な保護措置なしに個人データが国境を越えて転送された。セルフホストなら転送は発生しない。 |
| [Equifax: 暗号化されていないデータ](https://www.ftc.gov/news-events/news/press-releases/2019/07/equifax-pay-575-million-part-settlement-ftc-cfpb-states-related-2017-data-breach) | 7億USD | 1億4700万件のレコードが不十分なネットワークセグメンテーションで暗号化されずに保存された。LUKS2はオプションではなく必須。 |
| [Target: ラテラルムーブメント](https://oag.ca.gov/news/press-releases/attorney-general-becerra-target-settles-record-185-million-credit-card-data) | 1850万USD | 攻撃者がフラットネットワーク上でHVACベンダーから決済システムへ侵入。リポジトリごとの分離がこれを防止。 |
| [Anthem: 暗号化されていないPHI](https://www.hhs.gov/hipaa/for-professionals/compliance-enforcement/agreements/anthem/index.html) | 1600万USD | 7900万件の医療記録が暗号化されずに保存された。LUKS2 AES-256は常に有効。 |
| [Blackbaud: SaaS侵害の連鎖](https://www.sec.gov/newsroom/press-releases/2023-48) | 4950万USD | 1つのSaaSベンダーへのランサムウェアが13,000以上の顧客組織のデータを露出。セルフホストならベンダーの侵害がお客様のデータに到達できない。 |
| [British Airways: 不十分なセグメンテーション](https://www.edpb.europa.eu/news/national-news/2019/ico-statement-intention-fine-british-airways-ps18339m-under-gdpr-data_en) | 2000万GBP | 不十分なネットワーク制御により攻撃者が悪意のあるコードを注入。分離されたDocker daemonとiptablesがラテラルアクセスを防止。 |
| [Google: 消去権](https://www.edpb.europa.eu/news/national-news/2019/cnils-restricted-committee-imposes-financial-penalty-50-million-euros_en) | 5000万EUR | 分散システム全体でデータを完全に消去する困難さ。LUKS破棄による暗号消去は即時かつ完全。 |

## 重要な注意事項

これらのページは、コンプライアンス要件に関連するRediaccの技術的機能を説明しています。いかなる規制の遵守にも、単一のツールの範囲を超える組織的なポリシー、手順、スタッフトレーニング、場合によっては第三者監査が必要です。お客様の組織に固有のガイダンスについては、法務およびコンプライアンスチームにご相談ください。
