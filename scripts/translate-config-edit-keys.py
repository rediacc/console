#!/usr/bin/env python3
"""
One-shot translator for the new `config field / edit / audit` CLI keys.

Replaces English placeholders in the 8 non-English cli.json files with
translations across all sections added by the 2025-Q2 config-edit refactor.

Run once after `npm run i18n:sync` has populated the placeholder structure.
Idempotent — running again just re-writes the same translated values.
"""

import json
import pathlib
import sys

ROOT = pathlib.Path("/home/muhammed/monorepo/console/packages/cli/src/i18n/locales")
LOCALES = ["ar", "de", "es", "fr", "ja", "ru", "tr", "zh"]

# Each entry maps a dotted key path to a dict of locale → translation.
# Interpolation markers `{{name}}`, `{{pointer}}`, etc. are preserved verbatim.
T = {
    # ─── commands.config.field ─────────────────────────────────────────────
    "commands.config.field.description": {
        "ar": "عمليات حقول التكوين المعنونة بالمؤشرات (get/set/unset/rotate/list). مؤشرات JSON (RFC 6901) مثل /credentials/cfDnsApiToken.",
        "de": "Feldoperationen der Konfiguration mit Pointer-Adressierung (get/set/unset/rotate/list). JSON-Pointer (RFC 6901), z. B. /credentials/cfDnsApiToken.",
        "es": "Operaciones de campos de configuración direccionados por puntero (get/set/unset/rotate/list). Punteros JSON (RFC 6901) como /credentials/cfDnsApiToken.",
        "fr": "Opérations sur les champs de configuration adressés par pointeur (get/set/unset/rotate/list). Pointeurs JSON (RFC 6901) tels que /credentials/cfDnsApiToken.",
        "ja": "ポインタ指定による設定フィールド操作(get/set/unset/rotate/list)。/credentials/cfDnsApiToken のような JSON Pointer(RFC 6901)を使用します。",
        "ru": "Операции над полями конфигурации по JSON-указателю (get/set/unset/rotate/list). Указатели JSON (RFC 6901), например /credentials/cfDnsApiToken.",
        "tr": "İşaretçi adresli yapılandırma alan işlemleri (get/set/unset/rotate/list). /credentials/cfDnsApiToken gibi JSON Pointer (RFC 6901).",
        "zh": "基于 JSON 指针(RFC 6901)的配置字段操作(get/set/unset/rotate/list),如 /credentials/cfDnsApiToken。",
    },
    "commands.config.field.get.description": {
        "ar": "قراءة قيمة تكوين واحدة بواسطة مؤشر JSON. تُخفى الحقول الحساسة إلا باستخدام --reveal (للمستخدمين البشريين فقط).",
        "de": "Einzelnen Konfigurationswert per JSON-Pointer lesen. Sensible Felder werden zensiert, außer mit --reveal (nur interaktiv).",
        "es": "Lee un único valor de configuración por puntero JSON. Los campos sensibles se redactan salvo con --reveal (solo humanos).",
        "fr": "Lire une valeur de configuration via un pointeur JSON. Les champs sensibles sont masqués sauf avec --reveal (humains uniquement).",
        "ja": "JSON ポインタで単一の設定値を読み取ります。機密フィールドは --reveal を指定しない限り秘匿されます(人間のみ)。",
        "ru": "Прочитать значение конфигурации по указателю JSON. Секретные поля скрываются, если не указан --reveal (только для человека).",
        "tr": "JSON Pointer ile tek bir yapılandırma değerini oku. --reveal olmadıkça hassas alanlar maskelenir (yalnızca insan).",
        "zh": "按 JSON 指针读取单个配置值。敏感字段默认脱敏,除非使用 --reveal(仅限人工)。",
    },
    "commands.config.field.get.optionReveal": {
        "ar": "إظهار النص الصريح للقيم الحساسة (طرفية تفاعلية فقط؛ يُسجَّل في التدقيق)",
        "de": "Klartext für sensible Werte anzeigen (nur interaktives TTY; Audit-Log)",
        "es": "Mostrar texto en claro de valores sensibles (solo TTY interactivo; auditado)",
        "fr": "Afficher les valeurs sensibles en clair (TTY interactif uniquement ; audité)",
        "ja": "機密値を平文で表示する(対話型 TTY のみ、監査ログに記録)",
        "ru": "Показать секретные значения в открытом виде (только интерактивный TTY; аудируется)",
        "tr": "Hassas değerleri açık metin olarak göster (yalnızca etkileşimli TTY; denetlenir)",
        "zh": "以明文显示敏感值(仅限交互式 TTY;记入审计日志)",
    },
    "commands.config.field.get.optionDigest": {
        "ar": "طباعة تلخيص SHA-256 بدلاً من القيمة (آمن للمشاركة مع العملاء الذكيين)",
        "de": "SHA-256-Prüfsumme statt des Werts ausgeben (ist für KI-Agenten freigegeben)",
        "es": "Imprimir el resumen SHA-256 en lugar del valor (seguro para compartir con agentes)",
        "fr": "Afficher l'empreinte SHA-256 au lieu de la valeur (sûr à partager avec des agents)",
        "ja": "値の代わりに SHA-256 ダイジェストを出力(エージェントに共有しても安全)",
        "ru": "Вывести дайджест SHA-256 вместо значения (безопасно для агентов)",
        "tr": "Değer yerine SHA-256 özetini yaz (ajanlarla paylaşmak için güvenli)",
        "zh": "输出 SHA-256 摘要而非数值(可安全地分享给代理)",
    },
    "commands.config.field.set.description": {
        "ar": "كتابة قيمة تكوين عند مؤشر JSON. المسارات الحساسة تتطلب --current (بوابة المعرفة).",
        "de": "Konfigurationswert an einem JSON-Pointer schreiben. Sensible Pfade erfordern --current (Wissensnachweis).",
        "es": "Escribir un valor de configuración en un puntero JSON. Los caminos sensibles requieren --current (puerta de conocimiento).",
        "fr": "Écrire une valeur de configuration à un pointeur JSON. Les chemins sensibles exigent --current (preuve de connaissance).",
        "ja": "JSON ポインタ位置に設定値を書き込みます。機密パスには --current(知識ゲート)が必要です。",
        "ru": "Записать значение конфигурации по JSON-указателю. Для секретных путей требуется --current (шлюз знаний).",
        "tr": "JSON Pointer konumuna yapılandırma değeri yaz. Hassas yollar --current gerektirir (bilgi kapısı).",
        "zh": "在 JSON 指针位置写入配置值。敏感路径需提供 --current(知识门控)。",
    },
    "commands.config.field.set.optionNew": {
        "ar": "القيمة الجديدة (تُفسَّر كـ JSON إذا بدأت بـ { [ \" أو true/false/null/رقم)",
        "de": "Neuer Wert (als JSON interpretiert, falls er mit {, [, \", true, false, null oder einer Zahl beginnt)",
        "es": "Valor nuevo (se interpreta como JSON si empieza con {, [, \", true, false, null o un número)",
        "fr": "Nouvelle valeur (interprétée comme JSON si elle commence par {, [, \", true, false, null ou un nombre)",
        "ja": "新しい値({, [, \", true/false/null, 数値で始まる場合は JSON として解釈)",
        "ru": "Новое значение (парсится как JSON, если начинается с {, [, \" или равно true/false/null/числу)",
        "tr": "Yeni değer ({, [, \", true/false/null veya sayı ile başlıyorsa JSON olarak ayrıştırılır)",
        "zh": "新值(若以 {、[、\" 开头或为 true/false/null/数字,则按 JSON 解析)",
    },
    "commands.config.field.set.optionCurrent": {
        "ar": "القيمة الصريحة الحالية - مطلوبة لتعديل المسارات الحساسة (إثبات بوابة المعرفة)",
        "de": "Aktueller Klartextwert — für Änderungen sensibler Pfade erforderlich (Wissensnachweis)",
        "es": "Valor actual en claro — obligatorio para mutar caminos sensibles (prueba de conocimiento)",
        "fr": "Valeur actuelle en clair — requise pour modifier les chemins sensibles (preuve de connaissance)",
        "ja": "現在の平文値 — 機密パスの変更に必須(知識ゲート証明)",
        "ru": "Текущее значение в открытом виде — обязательно для изменения секретных путей (доказательство знания)",
        "tr": "Mevcut açık metin değer — hassas yol değişikliklerinde gerekli (bilgi kapısı kanıtı)",
        "zh": "当前明文值 — 修改敏感路径时必填(知识门控证明)",
    },
    "commands.config.field.set.success": {
        "ar": "تم تعيين {{pointer}}",
        "de": "{{pointer}} gesetzt",
        "es": "Se estableció {{pointer}}",
        "fr": "{{pointer}} défini",
        "ja": "{{pointer}} を設定しました",
        "ru": "{{pointer}} установлен",
        "tr": "{{pointer}} ayarlandı",
        "zh": "已设置 {{pointer}}",
    },
    "commands.config.field.unset.description": {
        "ar": "حذف قيمة تكوين عند مؤشر JSON. المسارات الحساسة تتطلب --current.",
        "de": "Konfigurationswert an einem JSON-Pointer löschen. Sensible Pfade erfordern --current.",
        "es": "Eliminar un valor de configuración en un puntero JSON. Los caminos sensibles requieren --current.",
        "fr": "Supprimer une valeur de configuration à un pointeur JSON. Les chemins sensibles exigent --current.",
        "ja": "JSON ポインタ位置の設定値を削除。機密パスには --current が必要です。",
        "ru": "Удалить значение конфигурации по JSON-указателю. Для секретных путей требуется --current.",
        "tr": "JSON Pointer konumundaki yapılandırma değerini sil. Hassas yollar --current gerektirir.",
        "zh": "删除 JSON 指针位置的配置值。敏感路径需提供 --current。",
    },
    "commands.config.field.unset.optionCurrent": {
        "ar": "القيمة الصريحة الحالية - مطلوبة لحذف المسارات الحساسة",
        "de": "Aktueller Klartextwert — für Löschungen sensibler Pfade erforderlich",
        "es": "Valor actual en claro — obligatorio para eliminar caminos sensibles",
        "fr": "Valeur actuelle en clair — requise pour supprimer les chemins sensibles",
        "ja": "現在の平文値 — 機密パスの削除に必須",
        "ru": "Текущее значение в открытом виде — обязательно для удаления секретных путей",
        "tr": "Mevcut açık metin değer — hassas yol silmelerinde gerekli",
        "zh": "当前明文值 — 删除敏感路径时必填",
    },
    "commands.config.field.unset.success": {
        "ar": "تم إلغاء {{pointer}}",
        "de": "{{pointer}} entfernt",
        "es": "Se eliminó {{pointer}}",
        "fr": "{{pointer}} supprimé",
        "ja": "{{pointer}} を削除しました",
        "ru": "{{pointer}} удалён",
        "tr": "{{pointer}} kaldırıldı",
        "zh": "已取消 {{pointer}}",
    },
    "commands.config.field.rotate.description": {
        "ar": "تدوير قيمة حساسة دون --current. طرفية تفاعلية فقط؛ يُسجَّل بشكل بارز.",
        "de": "Einen sensiblen Wert ohne --current rotieren. Nur interaktives TTY; laut geloggt.",
        "es": "Rotar un valor sensible sin --current. Solo TTY interactivo; auditado con énfasis.",
        "fr": "Rotation d'une valeur sensible sans --current. TTY interactif uniquement ; audité en évidence.",
        "ja": "--current なしで機密値をローテーションします。対話型 TTY のみ、詳細に監査されます。",
        "ru": "Ротация секретного значения без --current. Только интерактивный TTY; подробно аудируется.",
        "tr": "Hassas bir değeri --current olmadan döndür. Yalnızca etkileşimli TTY; belirgin şekilde denetlenir.",
        "zh": "在不提供 --current 的情况下轮换敏感值。仅交互式 TTY;详尽审计。",
    },
    "commands.config.field.rotate.optionNew": {
        "ar": "قيمة جديدة",
        "de": "Neuer Wert",
        "es": "Valor nuevo",
        "fr": "Nouvelle valeur",
        "ja": "新しい値",
        "ru": "Новое значение",
        "tr": "Yeni değer",
        "zh": "新值",
    },
    "commands.config.field.rotate.success": {
        "ar": "تم تدوير {{pointer}}",
        "de": "{{pointer}} rotiert",
        "es": "Se rotó {{pointer}}",
        "fr": "{{pointer}} a été tourné",
        "ja": "{{pointer}} をローテーションしました",
        "ru": "{{pointer}} обновлён",
        "tr": "{{pointer}} döndürüldü",
        "zh": "已轮换 {{pointer}}",
    },
    "commands.config.field.list.description": {
        "ar": "سرد كل قالب مؤشر مسجّل مع نوعه وسياسة الالتزام/التشفير.",
        "de": "Alle registrierten Pointer-Vorlagen mit Art und Commit/Verschlüsselungs-Policy auflisten.",
        "es": "Listar cada plantilla de puntero registrada con su tipo y política de commit/encriptación.",
        "fr": "Lister chaque modèle de pointeur enregistré avec son type et sa politique de commit/chiffrement.",
        "ja": "登録済みのすべてのセンシティビティ・ポインタ・テンプレートと種類、commit/encrypt ポリシーを一覧表示。",
        "ru": "Показать все зарегистрированные шаблоны указателей с типом и политикой commit/шифрования.",
        "tr": "Kaydedilmiş tüm duyarlılık pointer şablonlarını türü ve commit/şifreleme politikasıyla listele.",
        "zh": "列出每个已注册的敏感字段指针模板及其类别和提交/加密策略。",
    },
    "commands.config.field.list.optionSensitive": {
        "ar": "عرض القوالب الحساسة فقط (غير العامة)",
        "de": "Nur sensible (nicht-öffentliche) Vorlagen anzeigen",
        "es": "Mostrar solo plantillas sensibles (no públicas)",
        "fr": "Afficher uniquement les modèles sensibles (non publics)",
        "ja": "機密(非パブリック)テンプレートのみ表示",
        "ru": "Показать только секретные (непубличные) шаблоны",
        "tr": "Yalnızca hassas (genel olmayan) şablonları göster",
        "zh": "仅显示敏感(非公开)模板",
    },
    "commands.config.field.list.optionOutput": {
        "ar": "صيغة الإخراج (json|table)",
        "de": "Ausgabeformat (json|table)",
        "es": "Formato de salida (json|table)",
        "fr": "Format de sortie (json|table)",
        "ja": "出力形式(json|table)",
        "ru": "Формат вывода (json|table)",
        "tr": "Çıktı biçimi (json|table)",
        "zh": "输出格式(json|table)",
    },
    # ─── commands.config.edit ──────────────────────────────────────────────
    "commands.config.edit.description": {
        "ar": "فتح التكوين الحالي في $EDITOR كإسقاط JSONC مُخفى. للمستخدمين البشريين فقط؛ يُرفض العملاء.",
        "de": "Aktive Konfiguration in $EDITOR als zensiertes JSONC öffnen. Nur für Menschen; Agenten werden abgelehnt.",
        "es": "Abre la configuración activa en $EDITOR como proyección JSONC redactada. Solo humanos; los agentes son rechazados.",
        "fr": "Ouvre la configuration active dans $EDITOR comme projection JSONC caviardée. Humains uniquement ; les agents sont refusés.",
        "ja": "アクティブな設定を秘匿された JSONC プロジェクションとして $EDITOR で開きます。人間のみ、エージェントは拒否されます。",
        "ru": "Открыть активную конфигурацию в $EDITOR как редактированную JSONC-проекцию. Только для человека; агенты отклоняются.",
        "tr": "Aktif yapılandırmayı $EDITOR içinde redakte edilmiş JSONC yansıması olarak aç. Yalnızca insan; ajanlar reddedilir.",
        "zh": "在 $EDITOR 中以脱敏后的 JSONC 投影打开当前配置。仅限人工;拒绝代理。",
    },
    "commands.config.edit.optionReveal": {
        "ar": "إظهار النص الصريح للقيم الحساسة (طرفية تفاعلية فقط؛ يُسجَّل)",
        "de": "Klartext für sensible Werte anzeigen (nur interaktives TTY; Audit-Log)",
        "es": "Mostrar texto en claro de valores sensibles (solo TTY interactivo; auditado)",
        "fr": "Afficher les valeurs sensibles en clair (TTY interactif uniquement ; audité)",
        "ja": "機密値を平文で表示(対話型 TTY のみ、監査ログに記録)",
        "ru": "Показать секретные значения в открытом виде (только интерактивный TTY; аудируется)",
        "tr": "Hassas değerleri açık metin olarak göster (yalnızca etkileşimli TTY; denetlenir)",
        "zh": "以明文显示敏感值(仅限交互式 TTY;记入审计日志)",
    },
    "commands.config.edit.optionDump": {
        "ar": "طباعة التكوين الحالي كـ JSONC إلى stdout بدلاً من فتح المحرر (للقراءة فقط؛ آمن للعملاء عند الإخفاء)",
        "de": "Aktuelle Konfiguration als JSONC an stdout ausgeben, statt den Editor zu öffnen (schreibgeschützt; für Agenten sicher, wenn zensiert)",
        "es": "Imprimir la configuración actual como JSONC en stdout en lugar de abrir el editor (solo lectura; seguro para agentes cuando está redactado)",
        "fr": "Afficher la configuration actuelle en JSONC sur stdout au lieu d'ouvrir l'éditeur (lecture seule ; sûr pour les agents si caviardé)",
        "ja": "エディタを開かず、現在の設定を JSONC として stdout に出力(読み取り専用。秘匿時はエージェントでも安全)",
        "ru": "Вывести текущую конфигурацию в stdout как JSONC вместо открытия редактора (только чтение; безопасно для агентов при редактировании)",
        "tr": "Editörü açmak yerine mevcut yapılandırmayı JSONC olarak stdout'a yaz (salt okunur; redakte edildiğinde ajanlar için güvenli)",
        "zh": "将当前配置以 JSONC 形式输出到 stdout,不打开编辑器(只读;脱敏时代理也可安全使用)",
    },
    "commands.config.edit.optionApply": {
        "ar": "تطبيق ملف JSONC معدّل (يتخطى إطلاق $EDITOR)",
        "de": "Eine bearbeitete JSONC-Datei anwenden (überspringt das Öffnen von $EDITOR)",
        "es": "Aplicar un archivo JSONC editado (omite el lanzamiento de $EDITOR)",
        "fr": "Appliquer un fichier JSONC modifié (saute le lancement de $EDITOR)",
        "ja": "編集済み JSONC ファイルを適用($EDITOR 起動をスキップ)",
        "ru": "Применить отредактированный файл JSONC (пропуская запуск $EDITOR)",
        "tr": "Düzenlenmiş JSONC dosyasını uygula ($EDITOR başlatmayı atlar)",
        "zh": "应用已编辑的 JSONC 文件(跳过启动 $EDITOR)",
    },
    "commands.config.edit.optionCurrentSecrets": {
        "ar": "ملف JSON يربط المؤشر → النص الصريح القديم لبوابة المعرفة عند --apply",
        "de": "JSON-Datei mit Pointer→alter-Klartext-Zuordnung für den Wissensnachweis bei --apply",
        "es": "Archivo JSON que mapea puntero→texto antiguo en claro para la puerta de conocimiento en --apply",
        "fr": "Fichier JSON mappant pointeur→ancien texte en clair pour la porte de connaissance sur --apply",
        "ja": "ポインタ → 旧平文 のマップ JSON ファイル。--apply 時の知識ゲート用",
        "ru": "JSON-файл, сопоставляющий указатель→старый открытый текст для шлюза знаний при --apply",
        "tr": "--apply için bilgi kapısında kullanılan pointer→eski açık metin eşlemesi JSON dosyası",
        "zh": "指针→旧明文 的 JSON 映射文件,用于 --apply 时的知识门控",
    },
    "commands.config.edit.optionEditor": {
        "ar": "أمر المحرر البديل (يتبع تسلسل git: --editor > $GIT_EDITOR > git config core.editor > $VISUAL > $EDITOR)",
        "de": "Editor-Befehl (folgt git-Reihenfolge: --editor > $GIT_EDITOR > git config core.editor > $VISUAL > $EDITOR)",
        "es": "Orden de editor (sigue la precedencia de git: --editor > $GIT_EDITOR > git config core.editor > $VISUAL > $EDITOR)",
        "fr": "Commande d'éditeur (suit la priorité git : --editor > $GIT_EDITOR > git config core.editor > $VISUAL > $EDITOR)",
        "ja": "エディタ コマンドの上書き(git と同じ優先順位: --editor > $GIT_EDITOR > git config core.editor > $VISUAL > $EDITOR)",
        "ru": "Команда редактора (следует порядку git: --editor > $GIT_EDITOR > git config core.editor > $VISUAL > $EDITOR)",
        "tr": "Editör komutu geçersiz kılma (git önceliğine uyar: --editor > $GIT_EDITOR > git config core.editor > $VISUAL > $EDITOR)",
        "zh": "编辑器命令(遵循 git 优先级:--editor > $GIT_EDITOR > git config core.editor > $VISUAL > $EDITOR)",
    },
    "commands.config.edit.bannerTitle": {
        "ar": "rdc config edit — {{name}} (v{{version}})",
        "de": "rdc config edit — {{name}} (v{{version}})",
        "es": "rdc config edit — {{name}} (v{{version}})",
        "fr": "rdc config edit — {{name}} (v{{version}})",
        "ja": "rdc config edit — {{name}} (v{{version}})",
        "ru": "rdc config edit — {{name}} (v{{version}})",
        "tr": "rdc config edit — {{name}} (v{{version}})",
        "zh": "rdc config edit — {{name}} (v{{version}})",
    },
    "commands.config.edit.bannerStrip": {
        "ar": "الأسطر التي تبدأ بـ // تُحذف عند الحفظ.",
        "de": "Zeilen, die mit // beginnen, werden beim Speichern entfernt.",
        "es": "Las líneas que comienzan con // se eliminan al guardar.",
        "fr": "Les lignes commençant par // sont supprimées lors de l'enregistrement.",
        "ja": "// で始まる行は保存時に削除されます。",
        "ru": "Строки, начинающиеся с //, удаляются при сохранении.",
        "tr": "// ile başlayan satırlar kaydedilirken kaldırılır.",
        "zh": "以 // 开头的行在保存时会被删除。",
    },
    "commands.config.edit.bannerReveal": {
        "ar": "--reveal نشط: القيم الحساسة مرئية. يُسجَّل في التدقيق.",
        "de": "--reveal aktiv: SENSIBLE WERTE SICHTBAR. Audit-Log aktiv.",
        "es": "--reveal activo: VALORES SENSIBLES VISIBLES. Auditado.",
        "fr": "--reveal actif : VALEURS SENSIBLES VISIBLES. Audité.",
        "ja": "--reveal 有効: 機密値が可視。監査ログに記録されます。",
        "ru": "--reveal активен: СЕКРЕТНЫЕ ЗНАЧЕНИЯ ВИДНЫ. Аудируется.",
        "tr": "--reveal etkin: HASSAS DEĞERLER GÖRÜNÜR. Denetleniyor.",
        "zh": "--reveal 已启用:敏感值可见。已记入审计。",
    },
    "commands.config.edit.bannerRedacted": {
        "ar": "تظهر الحقول الحساسة على شكل <redacted:KIND>:DIGEST وهي قوالب تعود ذاتياً بأمان.",
        "de": "Sensible Felder werden als <redacted:KIND>:DIGEST-Stubs angezeigt, die sicher unverändert zurücklaufen.",
        "es": "Los campos sensibles se muestran como marcadores <redacted:KIND>:DIGEST que se reintegran de forma segura.",
        "fr": "Les champs sensibles apparaissent comme des marqueurs <redacted:KIND>:DIGEST qui se réintègrent proprement.",
        "ja": "機密フィールドは <redacted:KIND>:DIGEST 形式のスタブとして表示され、安全に往復変換されます。",
        "ru": "Секретные поля показаны как <redacted:KIND>:DIGEST-заглушки, безопасно преобразующиеся обратно.",
        "tr": "Hassas alanlar <redacted:KIND>:DIGEST formunda stub olarak gösterilir ve güvenle gidip gelir.",
        "zh": "敏感字段以 <redacted:KIND>:DIGEST 占位符显示,可安全往返转换。",
    },
    "commands.config.edit.bannerRotateLine1": {
        "ar": "لتدوير سر: استبدل قالبه بالقيمة الصريحة الجديدة — سيُطلب منك",
        "de": "Zum Rotieren eines Geheimnisses: Ersetzen Sie den Stub durch den neuen Klartext — Sie werden",
        "es": "Para rotar un secreto: reemplaza el marcador con el nuevo valor en claro — se te pedirá",
        "fr": "Pour changer un secret : remplacez son marqueur par la nouvelle valeur en clair — il vous sera",
        "ja": "シークレットをローテーションするには、そのスタブを新しい平文に置き換えます。エディタを閉じた後、",
        "ru": "Для ротации секрета замените его заглушку новым открытым значением — вас попросят",
        "tr": "Bir sırrı döndürmek için: stub'ı yeni açık metin değerle değiştir — editörü kapattıktan",
        "zh": "要轮换秘密:用新的明文值替换其占位符 — 您将在",
    },
    "commands.config.edit.bannerRotateLine2": {
        "ar": "تأكيد كل عملية تدوير بعد إغلاق المحرر.",
        "de": "nach dem Schließen des Editors zur Bestätigung jeder Rotation aufgefordert.",
        "es": "confirmar cada rotación después de cerrar el editor.",
        "fr": "demandé de confirmer chaque rotation après la fermeture de l'éditeur.",
        "ja": "各ローテーションの確認を求められます。",
        "ru": "подтвердить каждую ротацию после закрытия редактора.",
        "tr": "sonra her döndürmeyi onaylamanız istenecektir.",
        "zh": "关闭编辑器后被要求确认每次轮换。",
    },
    "commands.config.edit.noChanges": {
        "ar": "لم يتم حفظ أي تغييرات؛ الإلغاء.",
        "de": "Keine Änderungen gespeichert; breche ab.",
        "es": "No se guardaron cambios; cancelando.",
        "fr": "Aucun changement enregistré ; abandon.",
        "ja": "変更は保存されませんでした。中止します。",
        "ru": "Изменения не сохранены; отмена.",
        "tr": "Değişiklik kaydedilmedi; iptal ediliyor.",
        "zh": "未保存任何更改;正在中止。",
    },
    "commands.config.edit.saved": {
        "ar": "تم حفظ التكوين \"{{name}}\"",
        "de": "Konfiguration „{{name}}\" gespeichert",
        "es": "Se guardó la configuración \"{{name}}\"",
        "fr": "Configuration « {{name}} » enregistrée",
        "ja": "設定「{{name}}」を保存しました",
        "ru": "Конфигурация «{{name}}» сохранена",
        "tr": "Yapılandırma \"{{name}}\" kaydedildi",
        "zh": "已保存配置“{{name}}”",
    },
    "commands.config.edit.applied": {
        "ar": "تم تطبيق {{path}}",
        "de": "{{path}} angewendet",
        "es": "Se aplicó {{path}}",
        "fr": "{{path}} appliqué",
        "ja": "{{path}} を適用しました",
        "ru": "Применён {{path}}",
        "tr": "{{path}} uygulandı",
        "zh": "已应用 {{path}}",
    },
    "commands.config.edit.rotatePromptHeader": {
        "ar": "أنت على وشك تدوير {{count}} حقل حساس:",
        "de": "Sie sind dabei, {{count}} sensible(s) Feld(er) zu rotieren:",
        "es": "Estás a punto de rotar {{count}} campo(s) sensible(s):",
        "fr": "Vous êtes sur le point de faire tourner {{count}} champ(s) sensible(s) :",
        "ja": "{{count}} 個の機密フィールドをローテーションしようとしています:",
        "ru": "Вы собираетесь ротировать {{count}} секретных полей:",
        "tr": "{{count}} hassas alanı döndürmek üzeresiniz:",
        "zh": "您即将轮换 {{count}} 个敏感字段:",
    },
    "commands.config.edit.rotatePromptBullet": {
        "ar": "  • {{pointer}}",
        "de": "  • {{pointer}}",
        "es": "  • {{pointer}}",
        "fr": "  • {{pointer}}",
        "ja": "  • {{pointer}}",
        "ru": "  • {{pointer}}",
        "tr": "  • {{pointer}}",
        "zh": "  • {{pointer}}",
    },
    "commands.config.edit.rotatePromptFooter": {
        "ar": "اكتب 'rotate' للتأكيد (أي شيء آخر يلغي): ",
        "de": "Tippen Sie 'rotate', um zu bestätigen (alles andere bricht ab): ",
        "es": "Escribe 'rotate' para confirmar (cualquier otra cosa cancela): ",
        "fr": "Tapez 'rotate' pour confirmer (tout autre texte annule) : ",
        "ja": "確認するには 'rotate' を入力してください(それ以外は中止): ",
        "ru": "Введите 'rotate' для подтверждения (иначе — отмена): ",
        "tr": "Onaylamak için 'rotate' yazın (başka her şey iptal): ",
        "zh": "键入 'rotate' 确认(其他输入将中止): ",
    },
    "commands.config.edit.rotateDeclined": {
        "ar": "تم الإلغاء؛ تم الحفاظ على المسودة في ملف المحرر المؤقت.",
        "de": "Abgebrochen; Entwurf in der Editor-Temp-Datei erhalten.",
        "es": "Cancelado; borrador conservado en el archivo temporal del editor.",
        "fr": "Annulé ; brouillon conservé dans le fichier temporaire de l'éditeur.",
        "ja": "中止しました。下書きはエディタの一時ファイルに保持されています。",
        "ru": "Отменено; черновик сохранён во временном файле редактора.",
        "tr": "İptal edildi; taslak editör geçici dosyasında korundu.",
        "zh": "已中止;草稿已保留在编辑器临时文件中。",
    },
    "commands.config.edit.abortAfterRetries": {
        "ar": "الإلغاء بعد {{count}} محاولات فاشلة. تم حفظ المسودة في: {{path}}",
        "de": "Abbruch nach {{count}} fehlgeschlagenen Versuchen. Entwurf gespeichert unter: {{path}}",
        "es": "Cancelando tras {{count}} intentos fallidos. Borrador guardado en: {{path}}",
        "fr": "Abandon après {{count}} tentatives infructueuses. Brouillon conservé à : {{path}}",
        "ja": "{{count}} 回の失敗後に中止します。下書きを保存: {{path}}",
        "ru": "Отмена после {{count}} неудачных попыток. Черновик сохранён в: {{path}}",
        "tr": "{{count}} başarısız denemeden sonra iptal ediliyor. Taslak şurada korundu: {{path}}",
        "zh": "在 {{count}} 次失败尝试后中止。草稿已保留于:{{path}}",
    },
    # ─── commands.config.audit ─────────────────────────────────────────────
    "commands.config.audit.description": {
        "ar": "فحص سجل تدقيق التكوين (JSONL متسلسل التجزئة في ~/.config/rediacc/audit.log.jsonl)",
        "de": "Konfigurations-Audit-Log inspizieren (hash-verkettete JSONL in ~/.config/rediacc/audit.log.jsonl)",
        "es": "Inspeccionar el registro de auditoría de configuración (JSONL encadenado por hash en ~/.config/rediacc/audit.log.jsonl)",
        "fr": "Inspecter le journal d'audit de configuration (JSONL chaîné par hachage dans ~/.config/rediacc/audit.log.jsonl)",
        "ja": "設定監査ログを確認(~/.config/rediacc/audit.log.jsonl のハッシュチェーン JSONL)",
        "ru": "Проверка журнала аудита конфигурации (JSONL с хеш-цепочкой в ~/.config/rediacc/audit.log.jsonl)",
        "tr": "Yapılandırma denetim günlüğünü incele (~/.config/rediacc/audit.log.jsonl konumunda hash zincirli JSONL)",
        "zh": "查看配置审计日志(~/.config/rediacc/audit.log.jsonl 中的哈希链 JSONL)",
    },
    "commands.config.audit.log.description": {
        "ar": "طباعة أحدث إدخالات التدقيق بصيغة JSON",
        "de": "Kürzliche Audit-Einträge als JSON ausgeben",
        "es": "Imprimir entradas de auditoría recientes como JSON",
        "fr": "Afficher les entrées d'audit récentes au format JSON",
        "ja": "最近の監査エントリを JSON として出力",
        "ru": "Вывести недавние записи аудита в формате JSON",
        "tr": "Son denetim girdilerini JSON olarak yaz",
        "zh": "以 JSON 格式打印最近的审计条目",
    },
    "commands.config.audit.log.optionSince": {
        "ar": "إظهار الإدخالات الأحدث من (مثال: '24h', '7d', طابع زمني ISO)",
        "de": "Nur Einträge nach (z. B. '24h', '7d', ISO-Zeitstempel)",
        "es": "Mostrar solo entradas posteriores a (ej.: '24h', '7d', timestamp ISO)",
        "fr": "Afficher les entrées postérieures à (ex. : '24h', '7d', horodatage ISO)",
        "ja": "指定より新しいエントリのみ表示(例: '24h', '7d', ISO タイムスタンプ)",
        "ru": "Показать только записи новее (например '24h', '7d', ISO-временная метка)",
        "tr": "Yalnızca belirtilen zamandan sonraki girdileri göster (örn.: '24h', '7d', ISO zaman damgası)",
        "zh": "仅显示指定时间之后的条目(例如 '24h'、'7d'、ISO 时间戳)",
    },
    "commands.config.audit.log.optionPath": {
        "ar": "تصفية حسب نمط مؤشر JSON (مثال: /credentials/*)",
        "de": "Nach JSON-Pointer-Glob filtern (z. B. /credentials/*)",
        "es": "Filtrar por patrón de puntero JSON (ej.: /credentials/*)",
        "fr": "Filtrer par motif de pointeur JSON (ex. : /credentials/*)",
        "ja": "JSON Pointer グロブでフィルタ(例: /credentials/*)",
        "ru": "Фильтровать по шаблону JSON-указателя (например /credentials/*)",
        "tr": "JSON Pointer glob'una göre filtrele (örn.: /credentials/*)",
        "zh": "按 JSON 指针通配符过滤(例如 /credentials/*)",
    },
    "commands.config.audit.log.optionActor": {
        "ar": "تصفية حسب نوع الفاعل (human|agent)",
        "de": "Nach Akteur-Typ filtern (human|agent)",
        "es": "Filtrar por tipo de actor (human|agent)",
        "fr": "Filtrer par type d'acteur (human|agent)",
        "ja": "アクターの種類でフィルタ(human|agent)",
        "ru": "Фильтровать по виду участника (human|agent)",
        "tr": "Aktör türüne göre filtrele (human|agent)",
        "zh": "按操作者类型过滤(human|agent)",
    },
    "commands.config.audit.tail.description": {
        "ar": "بث الإدخالات الجديدة أثناء كتابتها (Ctrl+C للإيقاف)",
        "de": "Neue Audit-Einträge live streamen (Ctrl+C zum Beenden)",
        "es": "Transmitir nuevas entradas a medida que se escriben (Ctrl+C para detener)",
        "fr": "Diffuser les nouvelles entrées en temps réel (Ctrl+C pour arrêter)",
        "ja": "新しいエントリを書き込まれた順にストリーム(Ctrl+C で停止)",
        "ru": "Стримить новые записи по мере появления (Ctrl+C — остановка)",
        "tr": "Yazıldıkça yeni denetim girdilerini akıt (durdurmak için Ctrl+C)",
        "zh": "实时输出新写入的审计条目(Ctrl+C 停止)",
    },
    "commands.config.audit.verify.description": {
        "ar": "التحقق من سلامة سلسلة تجزئة SHA-256 عبر جميع إدخالات التدقيق",
        "de": "Integrität der SHA-256-Hash-Kette über alle Audit-Einträge prüfen",
        "es": "Verificar la integridad de la cadena SHA-256 de todas las entradas de auditoría",
        "fr": "Vérifier l'intégrité de la chaîne SHA-256 de toutes les entrées d'audit",
        "ja": "すべての監査エントリにおける SHA-256 ハッシュチェーンの整合性を検証",
        "ru": "Проверить целостность SHA-256-цепочки по всем записям аудита",
        "tr": "Tüm denetim girdilerinde SHA-256 hash zincirinin bütünlüğünü doğrula",
        "zh": "验证所有审计条目上 SHA-256 哈希链的完整性",
    },
    "commands.config.audit.verify.chainOk": {
        "ar": "سلامة السلسلة مؤكدة عبر {{count}} إدخال.",
        "de": "Ketten-Integrität über {{count}} Einträge verifiziert.",
        "es": "Integridad de la cadena verificada en {{count}} entradas.",
        "fr": "Intégrité de la chaîne vérifiée sur {{count}} entrées.",
        "ja": "{{count}} エントリにわたりチェーン整合性を確認しました。",
        "ru": "Целостность цепочки проверена на {{count}} записях.",
        "tr": "{{count}} girdi boyunca zincir bütünlüğü doğrulandı.",
        "zh": "已对 {{count}} 条目验证链完整性。",
    },
    "commands.config.audit.verify.chainBroken": {
        "ar": "السلسلة مكسورة في السطر {{line}} — تم تلاعب في الملف أو تلفه.",
        "de": "Kette bei Zeile {{line}} unterbrochen — Datei wurde manipuliert oder ist beschädigt.",
        "es": "Cadena rota en la línea {{line}} — el archivo fue manipulado o está corrupto.",
        "fr": "Chaîne rompue à la ligne {{line}} — le fichier a été altéré ou corrompu.",
        "ja": "{{line}} 行目でチェーンが破損しました — ファイルが改ざんまたは破損しています。",
        "ru": "Цепочка прервана на строке {{line}} — файл был подделан или повреждён.",
        "tr": "Zincir {{line}} satırında kırık — dosya kurcalanmış veya bozulmuş.",
        "zh": "第 {{line}} 行的链断裂 — 文件已被篡改或损坏。",
    },
    # ─── errors.agent ──────────────────────────────────────────────────────
    "errors.agent.configEdit": {
        "ar": "المحرر التفاعلي محظور في بيئات العملاء.\n\nالبدائل:\n  • rdc config edit --dump > config.jsonc    (فحص مُخفى آمن)\n  • rdc config field set <pointer> --current <old> --new <new>\n  • rdc config edit --apply config.jsonc\n\nللتجاوز، حدد REDIACC_ALLOW_CONFIG_EDIT=<scope-glob> في الصدفة الأبوية\nقبل بدء العميل (يجب أن يظهر في سلالة العميل).",
        "de": "Interaktiver Editor ist in Agenten-Umgebungen blockiert.\n\nAlternativen:\n  • rdc config edit --dump > config.jsonc    (sichere, zensierte Inspektion)\n  • rdc config field set <pointer> --current <old> --new <new>\n  • rdc config edit --apply config.jsonc\n\nZum Überschreiben REDIACC_ALLOW_CONFIG_EDIT=<scope-glob> in der Elternshell setzen,\nBEVOR der Agent startet (muss in der Agent-Prozess-Ahnenkette erscheinen).",
        "es": "El editor interactivo está bloqueado en entornos de agente.\n\nAlternativas:\n  • rdc config edit --dump > config.jsonc    (inspección segura redactada)\n  • rdc config field set <pointer> --current <old> --new <new>\n  • rdc config edit --apply config.jsonc\n\nPara anularlo, define REDIACC_ALLOW_CONFIG_EDIT=<scope-glob> en el shell padre\nANTES de iniciar el agente (debe aparecer en la ascendencia del proceso).",
        "fr": "L'éditeur interactif est bloqué dans les environnements d'agent.\n\nAlternatives :\n  • rdc config edit --dump > config.jsonc    (inspection caviardée sûre)\n  • rdc config field set <pointer> --current <old> --new <new>\n  • rdc config edit --apply config.jsonc\n\nPour passer outre, définissez REDIACC_ALLOW_CONFIG_EDIT=<scope-glob> dans le shell parent\nAVANT de démarrer l'agent (doit apparaître dans l'arborescence du processus).",
        "ja": "対話型エディタはエージェント環境ではブロックされます。\n\n代替手段:\n  • rdc config edit --dump > config.jsonc    (安全な秘匿表示)\n  • rdc config field set <pointer> --current <old> --new <new>\n  • rdc config edit --apply config.jsonc\n\nオーバーライドするには、エージェントを起動する前に親シェルで\nREDIACC_ALLOW_CONFIG_EDIT=<scope-glob> を設定してください(エージェントの祖先プロセス内に存在する必要があります)。",
        "ru": "Интерактивный редактор заблокирован в агентных окружениях.\n\nАльтернативы:\n  • rdc config edit --dump > config.jsonc    (безопасный редактированный просмотр)\n  • rdc config field set <pointer> --current <old> --new <new>\n  • rdc config edit --apply config.jsonc\n\nДля обхода установите REDIACC_ALLOW_CONFIG_EDIT=<scope-glob> в родительской оболочке\nДО запуска агента (должно присутствовать в родословной процесса).",
        "tr": "Etkileşimli editör, ajan ortamlarında engellenir.\n\nAlternatifler:\n  • rdc config edit --dump > config.jsonc    (güvenli redakte inceleme)\n  • rdc config field set <pointer> --current <old> --new <new>\n  • rdc config edit --apply config.jsonc\n\nGeçersiz kılmak için ajanı başlatmadan ÖNCE üst shell'de\nREDIACC_ALLOW_CONFIG_EDIT=<scope-glob> tanımlayın (ajan proses ataları arasında görünmelidir).",
        "zh": "交互式编辑器在代理环境中被阻止。\n\n替代方案:\n  • rdc config edit --dump > config.jsonc    (安全的脱敏查看)\n  • rdc config field set <pointer> --current <old> --new <new>\n  • rdc config edit --apply config.jsonc\n\n如需覆盖,请在启动代理之前,在父 shell 中\n设置 REDIACC_ALLOW_CONFIG_EDIT=<scope-glob>(必须出现在代理进程祖先链中)。",
    },
    "errors.agent.configEditAncestry": {
        "ar": "المحرر التفاعلي محظور في بيئات العملاء (تم تعيين REDIACC_ALLOW_CONFIG_EDIT لكن فشل التحقق من السلالة — يجب تعيين التجاوز من الصدفة وليس من العميل).\n\nالبدائل:\n  • rdc config edit --dump > config.jsonc    (فحص مُخفى آمن)\n  • rdc config field set <pointer> --current <old> --new <new>\n  • rdc config edit --apply config.jsonc\n\nحدد REDIACC_ALLOW_CONFIG_EDIT=<scope-glob> في الصدفة الأبوية قبل بدء العميل.",
        "de": "Interaktiver Editor ist in Agenten-Umgebungen blockiert (REDIACC_ALLOW_CONFIG_EDIT gesetzt, Ahnenprüfung fehlgeschlagen — Override muss aus Ihrer Shell kommen, nicht vom Agenten).\n\nAlternativen:\n  • rdc config edit --dump > config.jsonc    (sichere, zensierte Inspektion)\n  • rdc config field set <pointer> --current <old> --new <new>\n  • rdc config edit --apply config.jsonc\n\nSetzen Sie REDIACC_ALLOW_CONFIG_EDIT=<scope-glob> in der Elternshell BEVOR der Agent startet.",
        "es": "El editor interactivo está bloqueado en entornos de agente (REDIACC_ALLOW_CONFIG_EDIT se estableció pero falló la verificación de ascendencia — el override debe venir del shell, no del agente).\n\nAlternativas:\n  • rdc config edit --dump > config.jsonc    (inspección segura redactada)\n  • rdc config field set <pointer> --current <old> --new <new>\n  • rdc config edit --apply config.jsonc\n\nDefine REDIACC_ALLOW_CONFIG_EDIT=<scope-glob> en el shell padre ANTES de iniciar el agente.",
        "fr": "L'éditeur interactif est bloqué dans les environnements d'agent (REDIACC_ALLOW_CONFIG_EDIT défini mais la vérification d'ascendance a échoué — l'override doit venir du shell, pas de l'agent).\n\nAlternatives :\n  • rdc config edit --dump > config.jsonc    (inspection caviardée sûre)\n  • rdc config field set <pointer> --current <old> --new <new>\n  • rdc config edit --apply config.jsonc\n\nDéfinissez REDIACC_ALLOW_CONFIG_EDIT=<scope-glob> dans le shell parent AVANT de démarrer l'agent.",
        "ja": "対話型エディタはエージェント環境ではブロックされます(REDIACC_ALLOW_CONFIG_EDIT は設定されましたが祖先検証に失敗 — オーバーライドはエージェントではなく親シェルから設定する必要があります)。\n\n代替手段:\n  • rdc config edit --dump > config.jsonc    (安全な秘匿表示)\n  • rdc config field set <pointer> --current <old> --new <new>\n  • rdc config edit --apply config.jsonc\n\nエージェントを起動する前に親シェルで REDIACC_ALLOW_CONFIG_EDIT=<scope-glob> を設定してください。",
        "ru": "Интерактивный редактор заблокирован в агентных окружениях (REDIACC_ALLOW_CONFIG_EDIT был установлен, но проверка родословной не пройдена — обход должен задаваться вашей оболочкой, а не агентом).\n\nАльтернативы:\n  • rdc config edit --dump > config.jsonc    (безопасный редактированный просмотр)\n  • rdc config field set <pointer> --current <old> --new <new>\n  • rdc config edit --apply config.jsonc\n\nЗадайте REDIACC_ALLOW_CONFIG_EDIT=<scope-glob> в родительской оболочке ДО запуска агента.",
        "tr": "Etkileşimli editör, ajan ortamlarında engellendi (REDIACC_ALLOW_CONFIG_EDIT ayarlandı ancak ata doğrulaması başarısız oldu — geçersiz kılma ajanınız tarafından değil kabuğunuz tarafından ayarlanmalıdır).\n\nAlternatifler:\n  • rdc config edit --dump > config.jsonc    (güvenli redakte inceleme)\n  • rdc config field set <pointer> --current <old> --new <new>\n  • rdc config edit --apply config.jsonc\n\nAjanı başlatmadan ÖNCE üst shell'de REDIACC_ALLOW_CONFIG_EDIT=<scope-glob> tanımlayın.",
        "zh": "交互式编辑器在代理环境中被阻止(REDIACC_ALLOW_CONFIG_EDIT 已设置但祖先验证失败 — 该覆盖必须由您的 shell 而不是代理设置)。\n\n替代方案:\n  • rdc config edit --dump > config.jsonc    (安全的脱敏查看)\n  • rdc config field set <pointer> --current <old> --new <new>\n  • rdc config edit --apply config.jsonc\n\n在启动代理之前在父 shell 中设置 REDIACC_ALLOW_CONFIG_EDIT=<scope-glob>。",
    },
    "errors.agent.fieldReveal": {
        "ar": "‏--reveal للحقل الحساس {{pointer}} محظور في بيئات العملاء. يجب على العملاء استخدام --digest. يمكن لمستخدم حقيقي في طرفية تفاعلية استخدام --reveal.",
        "de": "--reveal für das sensible Feld {{pointer}} ist in Agenten-Umgebungen blockiert. Agenten sollten --digest verwenden. Ein echter Benutzer an einem interaktiven Terminal kann --reveal ausführen.",
        "es": "--reveal para el campo sensible {{pointer}} está bloqueado en entornos de agente. Los agentes deben usar --digest. Un usuario real en un terminal interactivo puede usar --reveal.",
        "fr": "--reveal sur le champ sensible {{pointer}} est bloqué dans les environnements d'agent. Les agents doivent utiliser --digest. Un vrai utilisateur sur un terminal interactif peut utiliser --reveal.",
        "ja": "機密フィールド {{pointer}} の --reveal はエージェント環境ではブロックされます。エージェントは --digest を使用してください。対話型端末の実ユーザーは --reveal を使えます。",
        "ru": "--reveal для секретного поля {{pointer}} заблокирован в агентных окружениях. Агентам следует использовать --digest. Реальный пользователь в интерактивном терминале может использовать --reveal.",
        "tr": "Hassas {{pointer}} alanı için --reveal, ajan ortamlarında engellenir. Ajanlar --digest kullanmalıdır. Etkileşimli terminaldeki gerçek bir kullanıcı --reveal kullanabilir.",
        "zh": "在代理环境中禁止对敏感字段 {{pointer}} 使用 --reveal。代理应改用 --digest。真正用户在交互式终端可使用 --reveal。",
    },
    "errors.agent.showReveal": {
        "ar": "‏--reveal محظور في بيئات العملاء. استخدم `rdc config show` (مُخفى) أو `rdc config field get <pointer> --digest` للحصول على بصمة آمنة.",
        "de": "--reveal ist in Agenten-Umgebungen blockiert. Verwenden Sie `rdc config show` (zensiert) oder `rdc config field get <pointer> --digest` für einen sicheren Fingerabdruck.",
        "es": "--reveal está bloqueado en entornos de agente. Usa `rdc config show` (redactado) o `rdc config field get <pointer> --digest` para una huella segura.",
        "fr": "--reveal est bloqué dans les environnements d'agent. Utilisez `rdc config show` (caviardé) ou `rdc config field get <pointer> --digest` pour une empreinte sûre.",
        "ja": "--reveal はエージェント環境ではブロックされます。秘匿された `rdc config show` または `rdc config field get <pointer> --digest` を使用してください。",
        "ru": "--reveal заблокирован в агентных окружениях. Используйте `rdc config show` (редактированный) или `rdc config field get <pointer> --digest` для безопасного отпечатка.",
        "tr": "--reveal, ajan ortamlarında engellenir. Güvenli parmak izi için `rdc config show` (redakte) veya `rdc config field get <pointer> --digest` kullanın.",
        "zh": "在代理环境中禁止使用 --reveal。请使用 `rdc config show`(脱敏)或 `rdc config field get <pointer> --digest` 获取安全指纹。",
    },
    "errors.agent.revealRequiresTty": {
        "ar": "‏--reveal يتطلب طرفية تفاعلية؛ يُرفض طباعة القيمة الحساسة إلى أنبوب.",
        "de": "--reveal erfordert ein interaktives TTY; sensible Werte werden nicht an eine Pipe ausgegeben.",
        "es": "--reveal requiere un TTY interactivo; no se imprimirá un valor sensible en una tubería.",
        "fr": "--reveal nécessite un TTY interactif ; impossible d'envoyer une valeur sensible dans un tube.",
        "ja": "--reveal には対話型 TTY が必要です。機密値をパイプに出力することは拒否します。",
        "ru": "--reveal требует интерактивного TTY; отказ в печати секретного значения в канал.",
        "tr": "--reveal etkileşimli TTY gerektirir; hassas değer bir boruya yazılmayacak.",
        "zh": "--reveal 需要交互式 TTY;拒绝将敏感值打印到管道。",
    },
    "errors.agent.showRevealRequiresTty": {
        "ar": "‏--reveal يتطلب طرفية تفاعلية؛ يُرفض تمرير النص الصريح إلى وجهة غير تفاعلية.",
        "de": "--reveal erfordert ein interaktives TTY; Klartext wird nicht in eine Nicht-TTY-Senke geleitet.",
        "es": "--reveal requiere un TTY interactivo; no se enviará texto en claro a un destino sin TTY.",
        "fr": "--reveal nécessite un TTY interactif ; pas de texte en clair vers une cible non-TTY.",
        "ja": "--reveal には対話型 TTY が必要です。平文を非 TTY 先へ流すことは拒否します。",
        "ru": "--reveal требует интерактивного TTY; отказ перенаправлять открытый текст в не-TTY приёмник.",
        "tr": "--reveal etkileşimli TTY gerektirir; açık metin TTY olmayan bir hedefe aktarılmayacak.",
        "zh": "--reveal 需要交互式 TTY;拒绝将明文重定向到非 TTY 目标。",
    },
    "errors.agent.rotateRequiresTty": {
        "ar": "‏config field rotate يتطلب تأكيدًا في طرفية تفاعلية؛ يُرفض في السياق غير التفاعلي (حدد REDIACC_ALLOW_CONFIG_EDIT للتجاوز).",
        "de": "config field rotate erfordert eine interaktive TTY-Bestätigung; wird in nicht-interaktivem Kontext abgelehnt (setzen Sie REDIACC_ALLOW_CONFIG_EDIT zur Umgehung).",
        "es": "config field rotate requiere confirmación en un TTY interactivo; rechazado en contexto no interactivo (define REDIACC_ALLOW_CONFIG_EDIT para anular).",
        "fr": "config field rotate exige une confirmation interactive sur un TTY ; refusé en contexte non interactif (définissez REDIACC_ALLOW_CONFIG_EDIT pour passer outre).",
        "ja": "config field rotate には対話型 TTY による確認が必要です。非対話型では拒否されます(上書きには REDIACC_ALLOW_CONFIG_EDIT を設定)。",
        "ru": "config field rotate требует подтверждения в интерактивном TTY; отказ в неинтерактивном режиме (для обхода задайте REDIACC_ALLOW_CONFIG_EDIT).",
        "tr": "config field rotate, etkileşimli TTY onayı gerektirir; etkileşimli olmayan bağlamda reddedilir (geçersiz kılmak için REDIACC_ALLOW_CONFIG_EDIT tanımlayın).",
        "zh": "config field rotate 需要交互式 TTY 确认;在非交互式上下文中被拒绝(如需覆盖请设置 REDIACC_ALLOW_CONFIG_EDIT)。",
    },
    "errors.agent.rotateNotSensitive": {
        "ar": "المؤشر \"{{pointer}}\" ليس حقلاً حساساً؛ استخدم 'config field set' بدلاً من ذلك.",
        "de": "Pointer „{{pointer}}\" ist kein sensibles Feld; verwenden Sie 'config field set'.",
        "es": "El puntero \"{{pointer}}\" no es un campo sensible; usa 'config field set' en su lugar.",
        "fr": "Le pointeur « {{pointer}} » n'est pas un champ sensible ; utilisez 'config field set' à la place.",
        "ja": "ポインタ「{{pointer}}」は機密フィールドではありません。代わりに 'config field set' を使用してください。",
        "ru": "Указатель «{{pointer}}» не является секретным полем; используйте 'config field set'.",
        "tr": "Pointer \"{{pointer}}\" hassas bir alan değil; bunun yerine 'config field set' kullanın.",
        "zh": "指针“{{pointer}}”不是敏感字段;请改用 'config field set'。",
    },
    # ─── errors.precondition ───────────────────────────────────────────────
    "errors.precondition.mismatch": {
        "ar": "فشلت الشروط المسبقة لـ {{count}} مسار:\n{{details}}",
        "de": "Precondition fehlgeschlagen für {{count}} Pfad(e):\n{{details}}",
        "es": "Precondición fallida para {{count}} ruta(s):\n{{details}}",
        "fr": "Précondition échouée pour {{count}} chemin(s) :\n{{details}}",
        "ja": "{{count}} パスで事前条件失敗:\n{{details}}",
        "ru": "Предусловие не выполнено для {{count}} путей:\n{{details}}",
        "tr": "{{count}} yol için önkoşul başarısız:\n{{details}}",
        "zh": "{{count}} 条路径前置条件失败:\n{{details}}",
    },
    "errors.precondition.missing": {
        "ar": "المسار الحساس يتطلب --current (أو --rotate-secret)",
        "de": "Sensibler Pfad erfordert --current (oder --rotate-secret)",
        "es": "La ruta sensible requiere --current (o --rotate-secret)",
        "fr": "Le chemin sensible nécessite --current (ou --rotate-secret)",
        "ja": "機密パスには --current(または --rotate-secret)が必要です",
        "ru": "Секретный путь требует --current (или --rotate-secret)",
        "tr": "Hassas yol --current (veya --rotate-secret) gerektirir",
        "zh": "敏感路径需要 --current(或 --rotate-secret)",
    },
    "errors.precondition.kindMismatch": {
        "ar": "تغيّر نوع القيمة (المخزّن: {{stored}}، المُدَّعى: {{claimed}})",
        "de": "Werttyp geändert (gespeichert: {{stored}}, behauptet: {{claimed}})",
        "es": "El tipo de valor cambió (almacenado: {{stored}}, reclamado: {{claimed}})",
        "fr": "Le type de valeur a changé (stocké : {{stored}}, revendiqué : {{claimed}})",
        "ja": "値の種類が変わりました(保存: {{stored}}、申告: {{claimed}})",
        "ru": "Тип значения изменился (сохранённый: {{stored}}, заявленный: {{claimed}})",
        "tr": "Değer türü değişti (saklanan: {{stored}}, iddia edilen: {{claimed}})",
        "zh": "值类型已更改(已存储:{{stored}},声明:{{claimed}})",
    },
    "errors.precondition.digestMismatch": {
        "ar": "عدم تطابق تلخيص --current (المتوقع {{expected}}…، الفعلي {{got}}…)",
        "de": "--current-Prüfsummen-Mismatch (erwartet {{expected}}…, erhalten {{got}}…)",
        "es": "Desajuste de digest --current (se esperaba {{expected}}…, se obtuvo {{got}}…)",
        "fr": "Désaccord sur l'empreinte --current (attendu {{expected}}…, reçu {{got}}…)",
        "ja": "--current ダイジェスト不一致(期待値 {{expected}}…、実際 {{got}}…)",
        "ru": "Несоответствие дайджеста --current (ожидалось {{expected}}…, получено {{got}}…)",
        "tr": "--current özet uyuşmazlığı (beklenen {{expected}}…, alınan {{got}}…)",
        "zh": "--current 摘要不匹配(期望 {{expected}}…,实际 {{got}}…)",
    },
    "errors.precondition.currentSecretsRequired": {
        "ar": "{{pointer}}: تم تغيير الحقل الحساس دون --current؛ قدم --current-secrets <file> يربط المؤشر→القيمة القديمة",
        "de": "{{pointer}}: Sensibles Feld ohne --current geändert; geben Sie --current-secrets <file> mit pointer→alter-Wert-Zuordnung an",
        "es": "{{pointer}}: campo sensible cambiado sin --current; aporta --current-secrets <file> mapeando puntero→valor-antiguo",
        "fr": "{{pointer}} : champ sensible modifié sans --current ; fournissez --current-secrets <file> mappant pointeur→ancienne-valeur",
        "ja": "{{pointer}}: --current なしで機密フィールドが変更されました。ポインタ→旧値をマッピングした --current-secrets <file> を指定してください",
        "ru": "{{pointer}}: секретное поле изменено без --current; передайте --current-secrets <file> с сопоставлением указатель→старое-значение",
        "tr": "{{pointer}}: hassas alan --current olmadan değişti; pointer→eski-değer eşlemesi için --current-secrets <file> sağlayın",
        "zh": "{{pointer}}:未提供 --current 情况下更改了敏感字段;请提供 --current-secrets <file>,映射 pointer→旧值",
    },
    "errors.precondition.stubStillStub": {
        "ar": "{{pointer}}: لا تزال القيمة المعدَّلة تبدو قالب إخفاء لكنها لا تطابق التلخيص الحالي",
        "de": "{{pointer}}: Der bearbeitete Wert sieht noch wie ein Redaction-Stub aus, stimmt aber nicht mit der aktuellen Prüfsumme überein",
        "es": "{{pointer}}: el valor editado aún parece un marcador de redacción pero no coincide con el digest actual",
        "fr": "{{pointer}} : la valeur modifiée ressemble encore à un marqueur de caviardage mais ne correspond pas à l'empreinte actuelle",
        "ja": "{{pointer}}: 編集された値は秘匿スタブのように見えますが、現在のダイジェストと一致しません",
        "ru": "{{pointer}}: отредактированное значение всё ещё выглядит как заглушка редактирования, но не совпадает с текущим дайджестом",
        "tr": "{{pointer}}: düzenlenmiş değer hâlâ bir redaksiyon stub'u gibi görünüyor ancak mevcut özetle eşleşmiyor",
        "zh": "{{pointer}}:编辑后的值仍像脱敏占位符,但不匹配当前摘要",
    },
    "errors.precondition.rotationRequiresTty": {
        "ar": "{{pointer}}: تأكيد التدوير يتطلب طرفية تفاعلية (أو استخدم --current-secrets)",
        "de": "{{pointer}}: Rotations-Bestätigung erfordert interaktives TTY (oder verwenden Sie --current-secrets)",
        "es": "{{pointer}}: la confirmación de rotación requiere un TTY interactivo (o usa --current-secrets)",
        "fr": "{{pointer}} : la confirmation de rotation nécessite un TTY interactif (ou utilisez --current-secrets)",
        "ja": "{{pointer}}: ローテーションの確認には対話型 TTY が必要です(または --current-secrets を使用)",
        "ru": "{{pointer}}: подтверждение ротации требует интерактивного TTY (либо используйте --current-secrets)",
        "tr": "{{pointer}}: döndürme onayı etkileşimli TTY gerektirir (veya --current-secrets kullanın)",
        "zh": "{{pointer}}:轮换确认需要交互式 TTY(或使用 --current-secrets)",
    },
    # ─── errors.editor ─────────────────────────────────────────────────────
    "errors.editor.notFound": {
        "ar": "لم يتم تكوين محرر. حدد $GIT_EDITOR أو git config core.editor أو $VISUAL أو $EDITOR، أو مرر --editor.",
        "de": "Kein Editor konfiguriert. Setzen Sie $GIT_EDITOR, git config core.editor, $VISUAL oder $EDITOR, oder übergeben Sie --editor.",
        "es": "No se configuró un editor. Define $GIT_EDITOR, git config core.editor, $VISUAL o $EDITOR, o pasa --editor.",
        "fr": "Aucun éditeur configuré. Définissez $GIT_EDITOR, git config core.editor, $VISUAL ou $EDITOR, ou passez --editor.",
        "ja": "エディタが設定されていません。$GIT_EDITOR、git config core.editor、$VISUAL、$EDITOR を設定するか、--editor を指定してください。",
        "ru": "Редактор не настроен. Задайте $GIT_EDITOR, git config core.editor, $VISUAL или $EDITOR, либо передайте --editor.",
        "tr": "Yapılandırılmış editör yok. $GIT_EDITOR, git config core.editor, $VISUAL ya da $EDITOR tanımlayın veya --editor geçirin.",
        "zh": "未配置编辑器。请设置 $GIT_EDITOR、git config core.editor、$VISUAL 或 $EDITOR,或传入 --editor。",
    },
    "errors.editor.headlessRefused": {
        "ar": "استدعاء المحرر بلا رأس سيتوقف إلى الأبد: {{command}}. مرر --editor مع خيارات تفاعلية.",
        "de": "Headless-Editor-Aufruf würde ewig blockieren: {{command}}. Übergeben Sie --editor explizit mit interaktiven Flags.",
        "es": "La invocación sin cabeza del editor se bloquearía para siempre: {{command}}. Pasa --editor explícitamente con flags interactivos.",
        "fr": "L'invocation sans tête de l'éditeur bloquerait indéfiniment : {{command}}. Passez --editor explicitement avec des options interactives.",
        "ja": "ヘッドレス エディタ呼び出しは永久にブロックします: {{command}}。対話型フラグを付けて --editor を明示してください。",
        "ru": "Запуск редактора в headless-режиме заблокировал бы процесс навсегда: {{command}}. Передайте --editor с интерактивными флагами.",
        "tr": "Başlıksız editör çağrısı sonsuza dek bloklar: {{command}}. Etkileşimli bayraklarla --editor'ü açıkça geçirin.",
        "zh": "无头编辑器调用将永远阻塞:{{command}}。请显式传入带交互标志的 --editor。",
    },
    "errors.editor.spawnFailed": {
        "ar": "فشل إطلاق المحرر {{command}}: {{reason}}",
        "de": "Editor {{command}} konnte nicht gestartet werden: {{reason}}",
        "es": "No se pudo lanzar el editor {{command}}: {{reason}}",
        "fr": "Échec du lancement de l'éditeur {{command}} : {{reason}}",
        "ja": "エディタ {{command}} の起動に失敗しました: {{reason}}",
        "ru": "Не удалось запустить редактор {{command}}: {{reason}}",
        "tr": "Editör {{command}} başlatılamadı: {{reason}}",
        "zh": "启动编辑器 {{command}} 失败:{{reason}}",
    },
    "errors.editor.nonzeroExit": {
        "ar": "خرج المحرر {{command}} بالرمز {{code}}",
        "de": "Editor {{command}} mit Code {{code}} beendet",
        "es": "El editor {{command}} salió con código {{code}}",
        "fr": "L'éditeur {{command}} s'est terminé avec le code {{code}}",
        "ja": "エディタ {{command}} はコード {{code}} で終了しました",
        "ru": "Редактор {{command}} завершился с кодом {{code}}",
        "tr": "Editör {{command}} {{code}} koduyla çıktı",
        "zh": "编辑器 {{command}} 以退出码 {{code}} 终止",
    },
    # ─── errors.config ─────────────────────────────────────────────────────
    "errors.config.noActiveConfig": {
        "ar": "لا يوجد تكوين نشط",
        "de": "Keine aktive Konfiguration",
        "es": "No hay configuración activa",
        "fr": "Aucune configuration active",
        "ja": "アクティブな設定がありません",
        "ru": "Нет активной конфигурации",
        "tr": "Aktif yapılandırma yok",
        "zh": "没有激活的配置",
    },
    "errors.config.pointerNotFound": {
        "ar": "المؤشر \"{{pointer}}\" غير موجود",
        "de": "Pointer „{{pointer}}\" nicht gefunden",
        "es": "Puntero \"{{pointer}}\" no encontrado",
        "fr": "Pointeur « {{pointer}} » introuvable",
        "ja": "ポインタ「{{pointer}}」が見つかりません",
        "ru": "Указатель «{{pointer}}» не найден",
        "tr": "Pointer \"{{pointer}}\" bulunamadı",
        "zh": "未找到指针“{{pointer}}”",
    },
}


def apply_translations(locale: str) -> None:
    """Apply all translations for a given locale to its cli.json."""
    path = ROOT / locale / "cli.json"
    data = json.loads(path.read_text())

    updated = 0
    for dotted_key, per_locale in T.items():
        segments = dotted_key.split(".")
        cursor = data
        for seg in segments[:-1]:
            if seg not in cursor or not isinstance(cursor[seg], dict):
                print(f"  ! {locale}: {dotted_key} — parent path missing", file=sys.stderr)
                cursor = None
                break
            cursor = cursor[seg]
        if cursor is None:
            continue
        if locale not in per_locale:
            print(f"  ! {locale}: {dotted_key} — no translation provided", file=sys.stderr)
            continue
        translated = per_locale[locale]
        if cursor.get(segments[-1]) != translated:
            cursor[segments[-1]] = translated
            updated += 1

    if updated:
        # Re-sort keys recursively so the diff stays stable with i18n:sync.
        def sort_keys(obj):
            if isinstance(obj, dict):
                return {k: sort_keys(obj[k]) for k in sorted(obj.keys(), key=lambda s: s.lower())}
            if isinstance(obj, list):
                return [sort_keys(v) for v in obj]
            return obj

        data = sort_keys(data)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"  {locale}: {updated} keys translated")


def main():
    print("Translating new config-edit CLI keys across 8 locales:")
    for locale in LOCALES:
        apply_translations(locale)

    # Validate interpolation markers survived.
    print("\nInterpolation marker validation:")
    errors = 0
    for dotted_key, per_locale in T.items():
        en_markers = sorted({m for m in re.findall(r"\{\{(\w+)\}\}", ENGLISH_MARKERS_SOURCE.get(dotted_key, ""))})
        for locale, translated in per_locale.items():
            locale_markers = sorted({m for m in re.findall(r"\{\{(\w+)\}\}", translated)})
            if en_markers != locale_markers:
                print(f"  ✗ {locale}: {dotted_key} markers {locale_markers} != en {en_markers}")
                errors += 1
    if errors == 0:
        print(f"  ✓ All {sum(len(v) for v in T.values())} translated strings preserved interpolation markers.")
    else:
        sys.exit(1)


import re  # noqa: E402
ENGLISH_MARKERS_SOURCE = {}

def _load_english_source():
    en_path = ROOT / "en" / "cli.json"
    data = json.loads(en_path.read_text())
    for dotted_key in T.keys():
        segments = dotted_key.split(".")
        cursor = data
        for seg in segments:
            if isinstance(cursor, dict) and seg in cursor:
                cursor = cursor[seg]
            else:
                cursor = None
                break
        if isinstance(cursor, str):
            ENGLISH_MARKERS_SOURCE[dotted_key] = cursor

_load_english_source()

if __name__ == "__main__":
    main()
