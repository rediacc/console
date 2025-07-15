#!/usr/bin/env python3
import json
import os

# Define the distributed storage translations for each language
translations = {
    "es": {
        "resourceTabs": {
            "distributedStorage": "Almacenamiento Distribuido"
        },
        "distributedStorage": {
            "clusterName": "Nombre del Clúster",
            "createCluster": "Crear Almacenamiento Distribuido",
            "editCluster": "Editar Clúster",
            "deleteCluster": "Eliminar Clúster",
            "confirmDelete": "¿Está seguro de que desea eliminar el clúster de almacenamiento distribuido \"{{clusterName}}\"? Esta acción no se puede deshacer.",
            "noDistributedStorage": "No se encontraron clústeres de almacenamiento distribuido en este equipo",
            "deleteSuccess": "Clúster de almacenamiento distribuido eliminado exitosamente",
            "deleteError": "Error al eliminar el clúster de almacenamiento distribuido",
            "createSuccess": "Clúster de almacenamiento distribuido creado exitosamente",
            "queueItemCreated": "Función de almacenamiento distribuido encolada exitosamente",
            "placeholders": {
                "enterClusterName": "Ingrese el nombre del clúster",
                "selectNodes": "Seleccione al menos 3 nodos",
                "enterPoolName": "Ingrese el nombre del pool (p.ej., rbd)",
                "enterPoolSize": "Ingrese el tamaño del pool (p.ej., 100G)",
                "enterOsdDevice": "Ingrese la ruta del dispositivo OSD (p.ej., /dev/sdb)",
                "enterRbdPrefix": "Ingrese el prefijo de imagen RBD"
            },
            "fields": {
                "nodes": "Nodos de Almacenamiento",
                "nodesHelp": "Seleccione al menos 3 máquinas para formar el clúster de almacenamiento distribuido. Más nodos proporcionan mejor redundancia y rendimiento.",
                "poolName": "Nombre del Pool",
                "poolNameHelp": "Nombre para el pool de almacenamiento. Se recomienda 'rbd' por defecto para almacenamiento de bloques. Use solo letras, números, guiones y guiones bajos.",
                "poolPgNum": "Grupos de Ubicación",
                "poolPgNumHelp": "Número de grupos de ubicación para distribución de datos. El valor predeterminado de 128 funciona bien para la mayoría de los clústeres. Use valores más altos para clústeres más grandes.",
                "poolSize": "Tamaño del Pool",
                "poolSizeHelp": "Capacidad total de almacenamiento a asignar para este pool (p.ej., 100G, 1T). Se distribuirá entre todos los nodos.",
                "osdDevice": "Dispositivo OSD",
                "osdDeviceHelp": "Dispositivo de bloque a usar para OSD en cada nodo (p.ej., /dev/sdb). Debe ser la misma ruta de dispositivo en todos los nodos seleccionados.",
                "rbdImagePrefix": "Prefijo de Imagen RBD",
                "rbdImagePrefixHelp": "Prefijo para nombres de imagen RBD. Se recomienda 'rediacc_disk' por defecto. Se usa al crear dispositivos de bloque para repositorios.",
                "healthCheckTimeout": "Tiempo de Espera de Verificación de Salud (segundos)",
                "healthCheckTimeoutHelp": "Tiempo máximo de espera para verificaciones de salud del clúster (60-3600 segundos). El valor predeterminado de 300 segundos (5 minutos) es adecuado para la mayoría de las implementaciones.",
                "status": "Estado",
                "nodeCount": "Cantidad de Nodos"
            },
            "status": {
                "healthy": "Saludable",
                "warning": "Advertencia",
                "error": "Error",
                "provisioning": "Aprovisionando",
                "unknown": "Desconocido"
            },
            "functionsFor": "Funciones para {{name}}",
            "distributedStorageFunctions": "Funciones de Almacenamiento Distribuido"
        },
        "common": {
            "vaultEditor": {
                "fields": {
                    "DISTRIBUTEDSTORAGE": {
                        "description": "Configuración del clúster de almacenamiento distribuido para almacenamiento basado en Ceph",
                        "ceph_dashboard_credentials": {
                            "label": "Credenciales del Panel",
                            "description": "Credenciales para acceder al panel de Ceph",
                            "url": {
                                "label": "URL del Panel",
                                "description": "URL para acceder a la interfaz del panel de Ceph"
                            },
                            "username": {
                                "label": "Nombre de Usuario",
                                "description": "Nombre de usuario para autenticación del panel"
                            },
                            "password": {
                                "label": "Contraseña",
                                "description": "Contraseña para autenticación del panel"
                            }
                        },
                        "ceph_config": {
                            "label": "Configuración de Ceph",
                            "description": "Opciones avanzadas de configuración de Ceph para personalización del clúster",
                            "monitors": {
                                "label": "IPs de Monitores",
                                "description": "Direcciones IP de los nodos monitores de Ceph"
                            },
                            "auth_config": {
                                "label": "Configuración de Autenticación",
                                "description": "Configuración adicional de autenticación de Ceph"
                            },
                            "custom_settings": {
                                "label": "Configuración Personalizada",
                                "description": "Parámetros de configuración personalizados de Ceph"
                            }
                        },
                        "monitoring": {
                            "label": "Monitoreo",
                            "description": "Configuración de monitoreo y alertas para el clúster",
                            "prometheus_endpoint": {
                                "label": "Endpoint de Prometheus",
                                "description": "URL para el endpoint de métricas de Prometheus"
                            },
                            "alert_rules": {
                                "label": "Reglas de Alerta",
                                "description": "Reglas de alerta personalizadas para monitoreo del clúster"
                            }
                        }
                    }
                }
            }
        }
    },
    "fr": {
        "resourceTabs": {
            "distributedStorage": "Stockage Distribué"
        },
        "distributedStorage": {
            "clusterName": "Nom du Cluster",
            "createCluster": "Créer un Stockage Distribué",
            "editCluster": "Modifier le Cluster",
            "deleteCluster": "Supprimer le Cluster",
            "confirmDelete": "Êtes-vous sûr de vouloir supprimer le cluster de stockage distribué \"{{clusterName}}\" ? Cette action ne peut pas être annulée.",
            "noDistributedStorage": "Aucun cluster de stockage distribué trouvé dans cette équipe",
            "deleteSuccess": "Cluster de stockage distribué supprimé avec succès",
            "deleteError": "Échec de la suppression du cluster de stockage distribué",
            "createSuccess": "Cluster de stockage distribué créé avec succès",
            "queueItemCreated": "Fonction de stockage distribué mise en file d'attente avec succès",
            "placeholders": {
                "enterClusterName": "Entrez le nom du cluster",
                "selectNodes": "Sélectionnez au moins 3 nœuds",
                "enterPoolName": "Entrez le nom du pool (ex: rbd)",
                "enterPoolSize": "Entrez la taille du pool (ex: 100G)",
                "enterOsdDevice": "Entrez le chemin du périphérique OSD (ex: /dev/sdb)",
                "enterRbdPrefix": "Entrez le préfixe d'image RBD"
            },
            "fields": {
                "nodes": "Nœuds de Stockage",
                "nodesHelp": "Sélectionnez au moins 3 machines pour former le cluster de stockage distribué. Plus de nœuds offrent une meilleure redondance et performance.",
                "poolName": "Nom du Pool",
                "poolNameHelp": "Nom pour le pool de stockage. 'rbd' par défaut est recommandé pour le stockage de blocs. Utilisez uniquement des lettres, chiffres, tirets et underscores.",
                "poolPgNum": "Groupes de Placement",
                "poolPgNumHelp": "Nombre de groupes de placement pour la distribution des données. La valeur par défaut de 128 convient à la plupart des clusters. Utilisez des valeurs plus élevées pour les clusters plus importants.",
                "poolSize": "Taille du Pool",
                "poolSizeHelp": "Capacité totale de stockage à allouer pour ce pool (ex: 100G, 1T). Sera distribuée entre tous les nœuds.",
                "osdDevice": "Périphérique OSD",
                "osdDeviceHelp": "Périphérique de bloc à utiliser pour l'OSD sur chaque nœud (ex: /dev/sdb). Doit être le même chemin sur tous les nœuds sélectionnés.",
                "rbdImagePrefix": "Préfixe d'Image RBD",
                "rbdImagePrefixHelp": "Préfixe pour les noms d'images RBD. 'rediacc_disk' par défaut est recommandé. Utilisé lors de la création de périphériques de blocs pour les dépôts.",
                "healthCheckTimeout": "Délai de Vérification de Santé (secondes)",
                "healthCheckTimeoutHelp": "Temps maximum d'attente pour les vérifications de santé du cluster (60-3600 secondes). La valeur par défaut de 300 secondes (5 minutes) convient à la plupart des déploiements.",
                "status": "Statut",
                "nodeCount": "Nombre de Nœuds"
            },
            "status": {
                "healthy": "Sain",
                "warning": "Avertissement",
                "error": "Erreur",
                "provisioning": "Provisionnement",
                "unknown": "Inconnu"
            },
            "functionsFor": "Fonctions pour {{name}}",
            "distributedStorageFunctions": "Fonctions de Stockage Distribué"
        },
        "common": {
            "vaultEditor": {
                "fields": {
                    "DISTRIBUTEDSTORAGE": {
                        "description": "Configuration du cluster de stockage distribué pour le stockage basé sur Ceph",
                        "ceph_dashboard_credentials": {
                            "label": "Identifiants du Tableau de Bord",
                            "description": "Identifiants pour accéder au tableau de bord Ceph",
                            "url": {
                                "label": "URL du Tableau de Bord",
                                "description": "URL pour accéder à l'interface du tableau de bord Ceph"
                            },
                            "username": {
                                "label": "Nom d'Utilisateur",
                                "description": "Nom d'utilisateur pour l'authentification du tableau de bord"
                            },
                            "password": {
                                "label": "Mot de Passe",
                                "description": "Mot de passe pour l'authentification du tableau de bord"
                            }
                        },
                        "ceph_config": {
                            "label": "Configuration Ceph",
                            "description": "Options de configuration avancées de Ceph pour la personnalisation du cluster",
                            "monitors": {
                                "label": "IPs des Moniteurs",
                                "description": "Adresses IP des nœuds moniteurs Ceph"
                            },
                            "auth_config": {
                                "label": "Configuration d'Authentification",
                                "description": "Configuration d'authentification Ceph supplémentaire"
                            },
                            "custom_settings": {
                                "label": "Paramètres Personnalisés",
                                "description": "Paramètres de configuration Ceph personnalisés"
                            }
                        },
                        "monitoring": {
                            "label": "Surveillance",
                            "description": "Configuration de surveillance et d'alerte pour le cluster",
                            "prometheus_endpoint": {
                                "label": "Point de Terminaison Prometheus",
                                "description": "URL pour le point de terminaison des métriques Prometheus"
                            },
                            "alert_rules": {
                                "label": "Règles d'Alerte",
                                "description": "Règles d'alerte personnalisées pour la surveillance du cluster"
                            }
                        }
                    }
                }
            }
        }
    },
    "de": {
        "resourceTabs": {
            "distributedStorage": "Verteilter Speicher"
        },
        "distributedStorage": {
            "clusterName": "Cluster-Name",
            "createCluster": "Verteilten Speicher erstellen",
            "editCluster": "Cluster bearbeiten",
            "deleteCluster": "Cluster löschen",
            "confirmDelete": "Sind Sie sicher, dass Sie den verteilten Speichercluster \"{{clusterName}}\" löschen möchten? Diese Aktion kann nicht rückgängig gemacht werden.",
            "noDistributedStorage": "Keine verteilten Speichercluster in diesem Team gefunden",
            "deleteSuccess": "Verteilter Speichercluster erfolgreich gelöscht",
            "deleteError": "Fehler beim Löschen des verteilten Speicherclusters",
            "createSuccess": "Verteilter Speichercluster erfolgreich erstellt",
            "queueItemCreated": "Verteilte Speicherfunktion erfolgreich in die Warteschlange gestellt",
            "placeholders": {
                "enterClusterName": "Cluster-Namen eingeben",
                "selectNodes": "Mindestens 3 Knoten auswählen",
                "enterPoolName": "Pool-Namen eingeben (z.B. rbd)",
                "enterPoolSize": "Pool-Größe eingeben (z.B. 100G)",
                "enterOsdDevice": "OSD-Gerätepfad eingeben (z.B. /dev/sdb)",
                "enterRbdPrefix": "RBD-Bildpräfix eingeben"
            },
            "fields": {
                "nodes": "Speicherknoten",
                "nodesHelp": "Wählen Sie mindestens 3 Maschinen aus, um den verteilten Speichercluster zu bilden. Mehr Knoten bieten bessere Redundanz und Leistung.",
                "poolName": "Pool-Name",
                "poolNameHelp": "Name für den Speicherpool. Standard 'rbd' wird für Blockspeicher empfohlen. Verwenden Sie nur Buchstaben, Zahlen, Bindestriche und Unterstriche.",
                "poolPgNum": "Platzierungsgruppen",
                "poolPgNumHelp": "Anzahl der Platzierungsgruppen für die Datenverteilung. Der Standardwert 128 funktioniert gut für die meisten Cluster. Verwenden Sie höhere Werte für größere Cluster.",
                "poolSize": "Pool-Größe",
                "poolSizeHelp": "Gesamte Speicherkapazität, die diesem Pool zugewiesen werden soll (z.B. 100G, 1T). Wird auf alle Knoten verteilt.",
                "osdDevice": "OSD-Gerät",
                "osdDeviceHelp": "Blockgerät für OSD auf jedem Knoten (z.B. /dev/sdb). Muss auf allen ausgewählten Knoten derselbe Gerätepfad sein.",
                "rbdImagePrefix": "RBD-Bildpräfix",
                "rbdImagePrefixHelp": "Präfix für RBD-Bildnamen. Standard 'rediacc_disk' wird empfohlen. Wird beim Erstellen von Blockgeräten für Repositories verwendet.",
                "healthCheckTimeout": "Gesundheitsprüfungs-Timeout (Sekunden)",
                "healthCheckTimeoutHelp": "Maximale Wartezeit für Cluster-Gesundheitsprüfungen (60-3600 Sekunden). Der Standardwert von 300 Sekunden (5 Minuten) ist für die meisten Bereitstellungen geeignet.",
                "status": "Status",
                "nodeCount": "Knotenanzahl"
            },
            "status": {
                "healthy": "Gesund",
                "warning": "Warnung",
                "error": "Fehler",
                "provisioning": "Bereitstellung",
                "unknown": "Unbekannt"
            },
            "functionsFor": "Funktionen für {{name}}",
            "distributedStorageFunctions": "Verteilte Speicherfunktionen"
        },
        "common": {
            "vaultEditor": {
                "fields": {
                    "DISTRIBUTEDSTORAGE": {
                        "description": "Konfiguration des verteilten Speicherclusters für Ceph-basierten Speicher",
                        "ceph_dashboard_credentials": {
                            "label": "Dashboard-Anmeldedaten",
                            "description": "Anmeldedaten für den Zugriff auf das Ceph-Dashboard",
                            "url": {
                                "label": "Dashboard-URL",
                                "description": "URL für den Zugriff auf die Ceph-Dashboard-Oberfläche"
                            },
                            "username": {
                                "label": "Benutzername",
                                "description": "Benutzername für die Dashboard-Authentifizierung"
                            },
                            "password": {
                                "label": "Passwort",
                                "description": "Passwort für die Dashboard-Authentifizierung"
                            }
                        },
                        "ceph_config": {
                            "label": "Ceph-Konfiguration",
                            "description": "Erweiterte Ceph-Konfigurationsoptionen für die Cluster-Anpassung",
                            "monitors": {
                                "label": "Monitor-IPs",
                                "description": "IP-Adressen der Ceph-Monitor-Knoten"
                            },
                            "auth_config": {
                                "label": "Authentifizierungskonfiguration",
                                "description": "Zusätzliche Ceph-Authentifizierungskonfiguration"
                            },
                            "custom_settings": {
                                "label": "Benutzerdefinierte Einstellungen",
                                "description": "Benutzerdefinierte Ceph-Konfigurationsparameter"
                            }
                        },
                        "monitoring": {
                            "label": "Überwachung",
                            "description": "Überwachungs- und Alarmkonfiguration für den Cluster",
                            "prometheus_endpoint": {
                                "label": "Prometheus-Endpunkt",
                                "description": "URL für den Prometheus-Metriken-Endpunkt"
                            },
                            "alert_rules": {
                                "label": "Alarmregeln",
                                "description": "Benutzerdefinierte Alarmregeln für die Clusterüberwachung"
                            }
                        }
                    }
                }
            }
        }
    },
    "ja": {
        "resourceTabs": {
            "distributedStorage": "分散ストレージ"
        },
        "distributedStorage": {
            "clusterName": "クラスター名",
            "createCluster": "分散ストレージを作成",
            "editCluster": "クラスターを編集",
            "deleteCluster": "クラスターを削除",
            "confirmDelete": "分散ストレージクラスター「{{clusterName}}」を削除してもよろしいですか？この操作は元に戻せません。",
            "noDistributedStorage": "このチームに分散ストレージクラスターが見つかりません",
            "deleteSuccess": "分散ストレージクラスターが正常に削除されました",
            "deleteError": "分散ストレージクラスターの削除に失敗しました",
            "createSuccess": "分散ストレージクラスターが正常に作成されました",
            "queueItemCreated": "分散ストレージ機能が正常にキューに追加されました",
            "placeholders": {
                "enterClusterName": "クラスター名を入力",
                "selectNodes": "少なくとも3つのノードを選択",
                "enterPoolName": "プール名を入力（例：rbd）",
                "enterPoolSize": "プールサイズを入力（例：100G）",
                "enterOsdDevice": "OSDデバイスパスを入力（例：/dev/sdb）",
                "enterRbdPrefix": "RBDイメージプレフィックスを入力"
            },
            "fields": {
                "nodes": "ストレージノード",
                "nodesHelp": "分散ストレージクラスターを形成するために少なくとも3台のマシンを選択してください。ノードが多いほど、冗長性とパフォーマンスが向上します。",
                "poolName": "プール名",
                "poolNameHelp": "ストレージプールの名前。ブロックストレージにはデフォルトの'rbd'が推奨されます。文字、数字、ハイフン、アンダースコアのみを使用してください。",
                "poolPgNum": "配置グループ",
                "poolPgNumHelp": "データ分散のための配置グループ数。デフォルトの128はほとんどのクラスターで適切に機能します。大規模なクラスターにはより高い値を使用してください。",
                "poolSize": "プールサイズ",
                "poolSizeHelp": "このプールに割り当てる総ストレージ容量（例：100G、1T）。すべてのノードに分散されます。",
                "osdDevice": "OSDデバイス",
                "osdDeviceHelp": "各ノードでOSDに使用するブロックデバイス（例：/dev/sdb）。選択したすべてのノードで同じデバイスパスである必要があります。",
                "rbdImagePrefix": "RBDイメージプレフィックス",
                "rbdImagePrefixHelp": "RBDイメージ名のプレフィックス。デフォルトの'rediacc_disk'が推奨されます。リポジトリ用のブロックデバイスを作成する際に使用されます。",
                "healthCheckTimeout": "ヘルスチェックタイムアウト（秒）",
                "healthCheckTimeoutHelp": "クラスターヘルスチェックの最大待機時間（60〜3600秒）。デフォルトの300秒（5分）はほとんどのデプロイメントに適しています。",
                "status": "ステータス",
                "nodeCount": "ノード数"
            },
            "status": {
                "healthy": "正常",
                "warning": "警告",
                "error": "エラー",
                "provisioning": "プロビジョニング中",
                "unknown": "不明"
            },
            "functionsFor": "{{name}}の機能",
            "distributedStorageFunctions": "分散ストレージ機能"
        },
        "common": {
            "vaultEditor": {
                "fields": {
                    "DISTRIBUTEDSTORAGE": {
                        "description": "Cephベースのストレージ用の分散ストレージクラスター構成",
                        "ceph_dashboard_credentials": {
                            "label": "ダッシュボード認証情報",
                            "description": "Cephダッシュボードへのアクセス認証情報",
                            "url": {
                                "label": "ダッシュボードURL",
                                "description": "Cephダッシュボードインターフェースへのアクセス用URL"
                            },
                            "username": {
                                "label": "ユーザー名",
                                "description": "ダッシュボード認証用のユーザー名"
                            },
                            "password": {
                                "label": "パスワード",
                                "description": "ダッシュボード認証用のパスワード"
                            }
                        },
                        "ceph_config": {
                            "label": "Ceph構成",
                            "description": "クラスターカスタマイズ用の高度なCeph構成オプション",
                            "monitors": {
                                "label": "モニターIP",
                                "description": "CephモニターノードのIPアドレス"
                            },
                            "auth_config": {
                                "label": "認証構成",
                                "description": "追加のCeph認証構成"
                            },
                            "custom_settings": {
                                "label": "カスタム設定",
                                "description": "カスタムCeph構成パラメータ"
                            }
                        },
                        "monitoring": {
                            "label": "監視",
                            "description": "クラスターの監視とアラート構成",
                            "prometheus_endpoint": {
                                "label": "Prometheusエンドポイント",
                                "description": "Prometheusメトリクスエンドポイント用URL"
                            },
                            "alert_rules": {
                                "label": "アラートルール",
                                "description": "クラスター監視用のカスタムアラートルール"
                            }
                        }
                    }
                }
            }
        }
    },
    "zh": {
        "resourceTabs": {
            "distributedStorage": "分布式存储"
        },
        "distributedStorage": {
            "clusterName": "集群名称",
            "createCluster": "创建分布式存储",
            "editCluster": "编辑集群",
            "deleteCluster": "删除集群",
            "confirmDelete": "您确定要删除分布式存储集群"{{clusterName}}"吗？此操作无法撤销。",
            "noDistributedStorage": "在此团队中未找到分布式存储集群",
            "deleteSuccess": "分布式存储集群删除成功",
            "deleteError": "删除分布式存储集群失败",
            "createSuccess": "分布式存储集群创建成功",
            "queueItemCreated": "分布式存储功能已成功加入队列",
            "placeholders": {
                "enterClusterName": "输入集群名称",
                "selectNodes": "选择至少3个节点",
                "enterPoolName": "输入池名称（例如：rbd）",
                "enterPoolSize": "输入池大小（例如：100G）",
                "enterOsdDevice": "输入OSD设备路径（例如：/dev/sdb）",
                "enterRbdPrefix": "输入RBD映像前缀"
            },
            "fields": {
                "nodes": "存储节点",
                "nodesHelp": "选择至少3台机器来组成分布式存储集群。更多节点提供更好的冗余和性能。",
                "poolName": "池名称",
                "poolNameHelp": "存储池的名称。对于块存储，建议使用默认的'rbd'。仅使用字母、数字、连字符和下划线。",
                "poolPgNum": "放置组",
                "poolPgNumHelp": "用于数据分布的放置组数量。默认值128适用于大多数集群。对于较大的集群使用更高的值。",
                "poolSize": "池大小",
                "poolSizeHelp": "为此池分配的总存储容量（例如：100G、1T）。将分布在所有节点上。",
                "osdDevice": "OSD设备",
                "osdDeviceHelp": "每个节点上用于OSD的块设备（例如：/dev/sdb）。必须在所有选定节点上是相同的设备路径。",
                "rbdImagePrefix": "RBD映像前缀",
                "rbdImagePrefixHelp": "RBD映像名称的前缀。建议使用默认的'rediacc_disk'。在为存储库创建块设备时使用。",
                "healthCheckTimeout": "健康检查超时（秒）",
                "healthCheckTimeoutHelp": "集群健康检查的最大等待时间（60-3600秒）。默认值300秒（5分钟）适合大多数部署。",
                "status": "状态",
                "nodeCount": "节点数量"
            },
            "status": {
                "healthy": "健康",
                "warning": "警告",
                "error": "错误",
                "provisioning": "配置中",
                "unknown": "未知"
            },
            "functionsFor": "{{name}}的功能",
            "distributedStorageFunctions": "分布式存储功能"
        },
        "common": {
            "vaultEditor": {
                "fields": {
                    "DISTRIBUTEDSTORAGE": {
                        "description": "基于Ceph存储的分布式存储集群配置",
                        "ceph_dashboard_credentials": {
                            "label": "仪表板凭据",
                            "description": "访问Ceph仪表板的凭据",
                            "url": {
                                "label": "仪表板URL",
                                "description": "访问Ceph仪表板界面的URL"
                            },
                            "username": {
                                "label": "用户名",
                                "description": "仪表板身份验证的用户名"
                            },
                            "password": {
                                "label": "密码",
                                "description": "仪表板身份验证的密码"
                            }
                        },
                        "ceph_config": {
                            "label": "Ceph配置",
                            "description": "用于集群自定义的高级Ceph配置选项",
                            "monitors": {
                                "label": "监视器IP",
                                "description": "Ceph监视器节点的IP地址"
                            },
                            "auth_config": {
                                "label": "认证配置",
                                "description": "其他Ceph认证配置"
                            },
                            "custom_settings": {
                                "label": "自定义设置",
                                "description": "自定义Ceph配置参数"
                            }
                        },
                        "monitoring": {
                            "label": "监控",
                            "description": "集群的监控和警报配置",
                            "prometheus_endpoint": {
                                "label": "Prometheus端点",
                                "description": "Prometheus指标端点的URL"
                            },
                            "alert_rules": {
                                "label": "警报规则",
                                "description": "集群监控的自定义警报规则"
                            }
                        }
                    }
                }
            }
        }
    },
    "ru": {
        "resourceTabs": {
            "distributedStorage": "Распределенное хранилище"
        },
        "distributedStorage": {
            "clusterName": "Имя кластера",
            "createCluster": "Создать распределенное хранилище",
            "editCluster": "Редактировать кластер",
            "deleteCluster": "Удалить кластер",
            "confirmDelete": "Вы уверены, что хотите удалить кластер распределенного хранилища \"{{clusterName}}\"? Это действие нельзя отменить.",
            "noDistributedStorage": "В этой команде не найдено кластеров распределенного хранилища",
            "deleteSuccess": "Кластер распределенного хранилища успешно удален",
            "deleteError": "Не удалось удалить кластер распределенного хранилища",
            "createSuccess": "Кластер распределенного хранилища успешно создан",
            "queueItemCreated": "Функция распределенного хранилища успешно поставлена в очередь",
            "placeholders": {
                "enterClusterName": "Введите имя кластера",
                "selectNodes": "Выберите минимум 3 узла",
                "enterPoolName": "Введите имя пула (например, rbd)",
                "enterPoolSize": "Введите размер пула (например, 100G)",
                "enterOsdDevice": "Введите путь устройства OSD (например, /dev/sdb)",
                "enterRbdPrefix": "Введите префикс образа RBD"
            },
            "fields": {
                "nodes": "Узлы хранения",
                "nodesHelp": "Выберите минимум 3 машины для формирования кластера распределенного хранилища. Больше узлов обеспечивает лучшую избыточность и производительность.",
                "poolName": "Имя пула",
                "poolNameHelp": "Имя для пула хранения. Рекомендуется 'rbd' по умолчанию для блочного хранилища. Используйте только буквы, цифры, дефисы и подчеркивания.",
                "poolPgNum": "Группы размещения",
                "poolPgNumHelp": "Количество групп размещения для распределения данных. Значение по умолчанию 128 хорошо работает для большинства кластеров. Используйте более высокие значения для больших кластеров.",
                "poolSize": "Размер пула",
                "poolSizeHelp": "Общая емкость хранилища для выделения этому пулу (например, 100G, 1T). Будет распределена между всеми узлами.",
                "osdDevice": "Устройство OSD",
                "osdDeviceHelp": "Блочное устройство для использования OSD на каждом узле (например, /dev/sdb). Должен быть одинаковый путь устройства на всех выбранных узлах.",
                "rbdImagePrefix": "Префикс образа RBD",
                "rbdImagePrefixHelp": "Префикс для имен образов RBD. Рекомендуется 'rediacc_disk' по умолчанию. Используется при создании блочных устройств для репозиториев.",
                "healthCheckTimeout": "Тайм-аут проверки здоровья (секунды)",
                "healthCheckTimeoutHelp": "Максимальное время ожидания проверок здоровья кластера (60-3600 секунд). Значение по умолчанию 300 секунд (5 минут) подходит для большинства развертываний.",
                "status": "Статус",
                "nodeCount": "Количество узлов"
            },
            "status": {
                "healthy": "Здоровый",
                "warning": "Предупреждение",
                "error": "Ошибка",
                "provisioning": "Подготовка",
                "unknown": "Неизвестно"
            },
            "functionsFor": "Функции для {{name}}",
            "distributedStorageFunctions": "Функции распределенного хранилища"
        },
        "common": {
            "vaultEditor": {
                "fields": {
                    "DISTRIBUTEDSTORAGE": {
                        "description": "Конфигурация кластера распределенного хранилища для хранилища на основе Ceph",
                        "ceph_dashboard_credentials": {
                            "label": "Учетные данные панели",
                            "description": "Учетные данные для доступа к панели управления Ceph",
                            "url": {
                                "label": "URL панели",
                                "description": "URL для доступа к интерфейсу панели управления Ceph"
                            },
                            "username": {
                                "label": "Имя пользователя",
                                "description": "Имя пользователя для аутентификации панели"
                            },
                            "password": {
                                "label": "Пароль",
                                "description": "Пароль для аутентификации панели"
                            }
                        },
                        "ceph_config": {
                            "label": "Конфигурация Ceph",
                            "description": "Расширенные параметры конфигурации Ceph для настройки кластера",
                            "monitors": {
                                "label": "IP-адреса мониторов",
                                "description": "IP-адреса узлов мониторов Ceph"
                            },
                            "auth_config": {
                                "label": "Конфигурация аутентификации",
                                "description": "Дополнительная конфигурация аутентификации Ceph"
                            },
                            "custom_settings": {
                                "label": "Пользовательские настройки",
                                "description": "Пользовательские параметры конфигурации Ceph"
                            }
                        },
                        "monitoring": {
                            "label": "Мониторинг",
                            "description": "Конфигурация мониторинга и оповещений для кластера",
                            "prometheus_endpoint": {
                                "label": "Конечная точка Prometheus",
                                "description": "URL для конечной точки метрик Prometheus"
                            },
                            "alert_rules": {
                                "label": "Правила оповещений",
                                "description": "Пользовательские правила оповещений для мониторинга кластера"
                            }
                        }
                    }
                }
            }
        }
    },
    "ar": {
        "resourceTabs": {
            "distributedStorage": "التخزين الموزع"
        },
        "distributedStorage": {
            "clusterName": "اسم العنقود",
            "createCluster": "إنشاء تخزين موزع",
            "editCluster": "تحرير العنقود",
            "deleteCluster": "حذف العنقود",
            "confirmDelete": "هل أنت متأكد من أنك تريد حذف عنقود التخزين الموزع \"{{clusterName}}\"؟ لا يمكن التراجع عن هذا الإجراء.",
            "noDistributedStorage": "لم يتم العثور على عناقيد تخزين موزعة في هذا الفريق",
            "deleteSuccess": "تم حذف عنقود التخزين الموزع بنجاح",
            "deleteError": "فشل حذف عنقود التخزين الموزع",
            "createSuccess": "تم إنشاء عنقود التخزين الموزع بنجاح",
            "queueItemCreated": "تم وضع وظيفة التخزين الموزع في قائمة الانتظار بنجاح",
            "placeholders": {
                "enterClusterName": "أدخل اسم العنقود",
                "selectNodes": "حدد 3 عقد على الأقل",
                "enterPoolName": "أدخل اسم المجموعة (مثل: rbd)",
                "enterPoolSize": "أدخل حجم المجموعة (مثل: 100G)",
                "enterOsdDevice": "أدخل مسار جهاز OSD (مثل: /dev/sdb)",
                "enterRbdPrefix": "أدخل بادئة صورة RBD"
            },
            "fields": {
                "nodes": "عقد التخزين",
                "nodesHelp": "حدد 3 أجهزة على الأقل لتشكيل عنقود التخزين الموزع. المزيد من العقد توفر تكرارًا وأداءً أفضل.",
                "poolName": "اسم المجموعة",
                "poolNameHelp": "اسم مجموعة التخزين. يُنصح بـ 'rbd' الافتراضي للتخزين الكتلي. استخدم الأحرف والأرقام والشرطات والشرطات السفلية فقط.",
                "poolPgNum": "مجموعات التوضع",
                "poolPgNumHelp": "عدد مجموعات التوضع لتوزيع البيانات. القيمة الافتراضية 128 تعمل بشكل جيد لمعظم العناقيد. استخدم قيمًا أعلى للعناقيد الأكبر.",
                "poolSize": "حجم المجموعة",
                "poolSizeHelp": "سعة التخزين الإجمالية المخصصة لهذه المجموعة (مثل: 100G، 1T). سيتم توزيعها عبر جميع العقد.",
                "osdDevice": "جهاز OSD",
                "osdDeviceHelp": "جهاز الكتلة لاستخدامه لـ OSD على كل عقدة (مثل: /dev/sdb). يجب أن يكون نفس مسار الجهاز على جميع العقد المحددة.",
                "rbdImagePrefix": "بادئة صورة RBD",
                "rbdImagePrefixHelp": "بادئة لأسماء صور RBD. يُنصح بـ 'rediacc_disk' الافتراضي. يُستخدم عند إنشاء أجهزة كتلة للمستودعات.",
                "healthCheckTimeout": "مهلة فحص الصحة (ثواني)",
                "healthCheckTimeoutHelp": "الوقت الأقصى للانتظار لفحوصات صحة العنقود (60-3600 ثانية). القيمة الافتراضية 300 ثانية (5 دقائق) مناسبة لمعظم التوزيعات.",
                "status": "الحالة",
                "nodeCount": "عدد العقد"
            },
            "status": {
                "healthy": "صحي",
                "warning": "تحذير",
                "error": "خطأ",
                "provisioning": "التوفير",
                "unknown": "غير معروف"
            },
            "functionsFor": "وظائف لـ {{name}}",
            "distributedStorageFunctions": "وظائف التخزين الموزع"
        },
        "common": {
            "vaultEditor": {
                "fields": {
                    "DISTRIBUTEDSTORAGE": {
                        "description": "تكوين عنقود التخزين الموزع للتخزين القائم على Ceph",
                        "ceph_dashboard_credentials": {
                            "label": "بيانات اعتماد لوحة التحكم",
                            "description": "بيانات الاعتماد للوصول إلى لوحة تحكم Ceph",
                            "url": {
                                "label": "عنوان URL للوحة التحكم",
                                "description": "عنوان URL للوصول إلى واجهة لوحة تحكم Ceph"
                            },
                            "username": {
                                "label": "اسم المستخدم",
                                "description": "اسم المستخدم لمصادقة لوحة التحكم"
                            },
                            "password": {
                                "label": "كلمة المرور",
                                "description": "كلمة المرور لمصادقة لوحة التحكم"
                            }
                        },
                        "ceph_config": {
                            "label": "تكوين Ceph",
                            "description": "خيارات تكوين Ceph المتقدمة لتخصيص العنقود",
                            "monitors": {
                                "label": "عناوين IP للمراقبين",
                                "description": "عناوين IP لعقد مراقبي Ceph"
                            },
                            "auth_config": {
                                "label": "تكوين المصادقة",
                                "description": "تكوين مصادقة Ceph الإضافي"
                            },
                            "custom_settings": {
                                "label": "الإعدادات المخصصة",
                                "description": "معاملات تكوين Ceph المخصصة"
                            }
                        },
                        "monitoring": {
                            "label": "المراقبة",
                            "description": "تكوين المراقبة والتنبيه للعنقود",
                            "prometheus_endpoint": {
                                "label": "نقطة نهاية Prometheus",
                                "description": "عنوان URL لنقطة نهاية مقاييس Prometheus"
                            },
                            "alert_rules": {
                                "label": "قواعد التنبيه",
                                "description": "قواعد التنبيه المخصصة لمراقبة العنقود"
                            }
                        }
                    }
                }
            }
        }
    },
    "tr": {
        "resourceTabs": {
            "distributedStorage": "Dağıtık Depolama"
        },
        "distributedStorage": {
            "clusterName": "Küme Adı",
            "createCluster": "Dağıtık Depolama Oluştur",
            "editCluster": "Kümeyi Düzenle",
            "deleteCluster": "Kümeyi Sil",
            "confirmDelete": "\"{{clusterName}}\" dağıtık depolama kümesini silmek istediğinizden emin misiniz? Bu işlem geri alınamaz.",
            "noDistributedStorage": "Bu takımda dağıtık depolama kümesi bulunamadı",
            "deleteSuccess": "Dağıtık depolama kümesi başarıyla silindi",
            "deleteError": "Dağıtık depolama kümesi silinemedi",
            "createSuccess": "Dağıtık depolama kümesi başarıyla oluşturuldu",
            "queueItemCreated": "Dağıtık depolama işlevi başarıyla kuyruğa alındı",
            "placeholders": {
                "enterClusterName": "Küme adını girin",
                "selectNodes": "En az 3 düğüm seçin",
                "enterPoolName": "Havuz adını girin (örn: rbd)",
                "enterPoolSize": "Havuz boyutunu girin (örn: 100G)",
                "enterOsdDevice": "OSD cihaz yolunu girin (örn: /dev/sdb)",
                "enterRbdPrefix": "RBD görüntü önekini girin"
            },
            "fields": {
                "nodes": "Depolama Düğümleri",
                "nodesHelp": "Dağıtık depolama kümesini oluşturmak için en az 3 makine seçin. Daha fazla düğüm daha iyi yedeklilik ve performans sağlar.",
                "poolName": "Havuz Adı",
                "poolNameHelp": "Depolama havuzu için ad. Blok depolama için varsayılan 'rbd' önerilir. Yalnızca harf, rakam, tire ve alt çizgi kullanın.",
                "poolPgNum": "Yerleştirme Grupları",
                "poolPgNumHelp": "Veri dağıtımı için yerleştirme grubu sayısı. Varsayılan 128 değeri çoğu küme için iyi çalışır. Daha büyük kümeler için daha yüksek değerler kullanın.",
                "poolSize": "Havuz Boyutu",
                "poolSizeHelp": "Bu havuz için ayrılacak toplam depolama kapasitesi (örn: 100G, 1T). Tüm düğümlere dağıtılacaktır.",
                "osdDevice": "OSD Cihazı",
                "osdDeviceHelp": "Her düğümde OSD için kullanılacak blok cihazı (örn: /dev/sdb). Seçilen tüm düğümlerde aynı cihaz yolu olmalıdır.",
                "rbdImagePrefix": "RBD Görüntü Öneki",
                "rbdImagePrefixHelp": "RBD görüntü adları için önek. Varsayılan 'rediacc_disk' önerilir. Depolar için blok cihazları oluştururken kullanılır.",
                "healthCheckTimeout": "Sağlık Kontrolü Zaman Aşımı (saniye)",
                "healthCheckTimeoutHelp": "Küme sağlık kontrolleri için maksimum bekleme süresi (60-3600 saniye). Varsayılan 300 saniye (5 dakika) çoğu dağıtım için uygundur.",
                "status": "Durum",
                "nodeCount": "Düğüm Sayısı"
            },
            "status": {
                "healthy": "Sağlıklı",
                "warning": "Uyarı",
                "error": "Hata",
                "provisioning": "Hazırlanıyor",
                "unknown": "Bilinmiyor"
            },
            "functionsFor": "{{name}} için İşlevler",
            "distributedStorageFunctions": "Dağıtık Depolama İşlevleri"
        },
        "common": {
            "vaultEditor": {
                "fields": {
                    "DISTRIBUTEDSTORAGE": {
                        "description": "Ceph tabanlı depolama için dağıtık depolama kümesi yapılandırması",
                        "ceph_dashboard_credentials": {
                            "label": "Kontrol Paneli Kimlik Bilgileri",
                            "description": "Ceph kontrol paneline erişim için kimlik bilgileri",
                            "url": {
                                "label": "Kontrol Paneli URL'si",
                                "description": "Ceph kontrol paneli arayüzüne erişim için URL"
                            },
                            "username": {
                                "label": "Kullanıcı Adı",
                                "description": "Kontrol paneli kimlik doğrulaması için kullanıcı adı"
                            },
                            "password": {
                                "label": "Şifre",
                                "description": "Kontrol paneli kimlik doğrulaması için şifre"
                            }
                        },
                        "ceph_config": {
                            "label": "Ceph Yapılandırması",
                            "description": "Küme özelleştirmesi için gelişmiş Ceph yapılandırma seçenekleri",
                            "monitors": {
                                "label": "İzleyici IP'leri",
                                "description": "Ceph izleyici düğümlerinin IP adresleri"
                            },
                            "auth_config": {
                                "label": "Kimlik Doğrulama Yapılandırması",
                                "description": "Ek Ceph kimlik doğrulama yapılandırması"
                            },
                            "custom_settings": {
                                "label": "Özel Ayarlar",
                                "description": "Özel Ceph yapılandırma parametreleri"
                            }
                        },
                        "monitoring": {
                            "label": "İzleme",
                            "description": "Küme için izleme ve uyarı yapılandırması",
                            "prometheus_endpoint": {
                                "label": "Prometheus Uç Noktası",
                                "description": "Prometheus metrikleri uç noktası için URL"
                            },
                            "alert_rules": {
                                "label": "Uyarı Kuralları",
                                "description": "Küme izleme için özel uyarı kuralları"
                            }
                        }
                    }
                }
            }
        }
    }
}

# Process each language
languages = ["es", "fr", "de", "ja", "zh", "ru", "ar", "tr"]
base_dir = "/home/muhammed/monorepo/console/src/i18n/locales"

for lang in languages:
    # Update resources.json
    resources_path = f"{base_dir}/{lang}/resources.json"
    with open(resources_path, 'r', encoding='utf-8') as f:
        resources_data = json.load(f)
    
    # Add distributedStorage to resourceTabs
    if 'resourceTabs' in resources_data:
        resources_data['resourceTabs']['distributedStorage'] = translations[lang]['resourceTabs']['distributedStorage']
    
    # Add distributedStorage section
    resources_data['distributedStorage'] = translations[lang]['distributedStorage']
    
    # Write back resources.json
    with open(resources_path, 'w', encoding='utf-8') as f:
        json.dump(resources_data, f, ensure_ascii=False, indent=2)
    
    # Update common.json
    common_path = f"{base_dir}/{lang}/common.json"
    with open(common_path, 'r', encoding='utf-8') as f:
        common_data = json.load(f)
    
    # Add DISTRIBUTEDSTORAGE to vaultEditor.fields
    if 'vaultEditor' in common_data and 'fields' in common_data['vaultEditor']:
        common_data['vaultEditor']['fields']['DISTRIBUTEDSTORAGE'] = translations[lang]['common']['vaultEditor']['fields']['DISTRIBUTEDSTORAGE']
    
    # Write back common.json
    with open(common_path, 'w', encoding='utf-8') as f:
        json.dump(common_data, f, ensure_ascii=False, indent=2)
    
    print(f"Updated {lang} translations")

print("All translations updated successfully!")