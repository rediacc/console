---
title: RDC CLI Hızlı Referans
description: >-
  Tüm rdc komutları için hızlı referans; yapılandırmalar, depolar, makineler,
  senkronizasyon, konteynerler ve daha fazlası.
category: Guides
order: 3
language: tr
sourceHash: c552951bebd937b0
sourceCommit: 35b53352026ae87fb6800c7fed10b793223ca1da
---

# RDC CLI Hızlı Referans

En sık kullanılan `rdc` komutları için hızlı referans. Tüm seçenekleri görmek için herhangi bir komutu `--help` ile çalıştırın.

## Depo Yaşam Döngüsü

| Komut | Açıklama |
|-------|----------|
| `rdc repo create --name <repo> -m <machine>` | Bir makinede yeni depo oluştur |
| `rdc repo up --name <repo> -m <machine>` | Depoyu dağıt veya güncelle |
| `rdc repo down --name <repo> -m <machine>` | Depoyu durdur |
| `rdc repo delete --name <repo> -m <machine>` | Depoyu sil |
| `rdc repo fork --parent <repo> --tag <tag> -m <machine>` | Depoyu çatalla (neredeyse anında, BTRFS reflink) |
| `rdc repo takeover --name <repo> -m <machine>` | Mevcut bir deponun sahipliğini al |
| `rdc config repository list` | Ad ve GUID ile tüm depoları listele |

## Yedekleme ve Geri Yükleme

| Komut | Açıklama |
|-------|----------|
| `rdc repo push --name <repo> -m <machine> --to <storage>` | Depo yedeklemesini depolamaya gönder |
| `rdc repo push --to <storage> -m <machine>` | Tüm depoları depolamaya gönder |
| `rdc repo pull --name <repo> -m <machine> --from <storage>` | Depoyu depolamadan geri yükle |
| `rdc repo pull --from <storage> -m <machine>` | Tüm depoları depolamadan geri yükle |
| `rdc repo push ... --bwlimit <limit>` | Gönderme sırasında rsync bant genişliğini sınırla (örn. `10M`) |
| `rdc repo pull ... --bwlimit <limit>` | Alma sırasında rsync bant genişliğini sınırla |
| `rdc repo push ... --checkpoint` | Göndermeden önce konteynerlerde kontrol noktası oluştur |
| `rdc repo backup list --from <storage> -m <machine>` | Depolamadaki mevcut yedeklemeleri listele |
| `rdc storage browse --name <storage>` | Depolama içeriğine göz at |

## Depo Taşıma

| Komut | Açıklama |
|-------|----------|
| `rdc repo migrate --name <repo> --from <machine> --to <machine>` | Depoyu makineler arasında taşı |
| `rdc repo migrate ... --provision` | Aktarmadan önce hedefe hazırlık yap |
| `rdc repo migrate ... --checkpoint` | Taşımadan önce kontrol noktası oluştur |
| `rdc repo migrate ... --skip-dns` | Taşıma sonrası DNS güncellemesini atla |
| `rdc repo migrate ... --bwlimit <limit>` | Aktarım bant genişliğini sınırla |

## Yedekleme Stratejileri

| Komut | Açıklama |
|-------|----------|
| `rdc config backup-strategy set --name <name> --destination <storage> --cron <expr> --mode <hot\|cold> --enable` | Adlandırılmış yedekleme stratejisi oluştur veya güncelle |
| `rdc config backup-strategy list` | Tanımlanmış tüm yedekleme stratejilerini listele |
| `rdc config backup-strategy show --name <name>` | Strateji ayrıntılarını göster |
| `rdc config backup-strategy remove --name <name>` | Stratejiyi kaldır |
| `rdc config machine set <machine> --backup-strategies <s1,s2>` | Stratejileri bir makineye bağla |

## Yedekleme İşlemleri

| Komut | Açıklama |
|-------|----------|
| `rdc machine backup schedule -m <machine>` | Bağlı stratejileri systemd zamanlayıcı olarak dağıt |
| `rdc machine backup schedule -m <machine> --dry-run` | Dağıtmadan zamanlayıcı birimlerini önizle (tokenlar gizli) |
| `rdc machine backup now -m <machine>` | Bağlı tüm stratejileri hemen çalıştır |
| `rdc machine backup now -m <machine> --strategy <name>` | Belirli bir stratejiyi hemen çalıştır |
| `rdc machine backup status -m <machine>` | Zamanlayıcı durumunu ve son iş sonuçlarını göster |
| `rdc machine backup status -m <machine> --strategy <name>` | Belirli bir stratejinin durumunu göster |
| `rdc machine backup cancel -m <machine>` | Çalışan yedeklemeleri iptal et |
| `rdc machine backup cancel -m <machine> --strategy <name>` | Belirli bir çalışan yedeklemeyi iptal et |

## Makine Yönetimi

| Komut | Açıklama |
|-------|----------|
| `rdc machine query --name <machine>` | Tam makine durumu (sistem, konteynerler, servisler, depolar, ağ) |
| `rdc machine query --name <machine> --system` | Yalnızca sistem bilgisi |
| `rdc machine query --name <machine> --containers` | Yalnızca konteyner listesi |
| `rdc machine query --name <machine> --repositories` | Yalnızca depo listesi |
| `rdc machine query --name <machine> --services` | Yalnızca servis listesi |
| `rdc machine query --name <machine> --network` | Yalnızca ağ bilgisi |
| `rdc machine query --name <machine> --block-devices` | Yalnızca blok cihaz bilgisi |
| `rdc machine list` | Yapılandırmadaki tüm makineleri listele |
| `rdc config machine setup --name <machine>` | İlk makine hazırlığını çalıştır |
| `rdc machine prune --name <machine>` | Makineden kullanılmayan kaynakları kaldır |
| `rdc machine deprovision --name <machine>` | Makineyi tamamen kaldır |
| `rdc machine vault-status --name <machine>` | LUKS vault durumunu göster |

## Terminal ve Senkronizasyon

| Komut | Açıklama |
|-------|----------|
| `rdc term connect -m <machine>` | Makineye SSH terminali aç |
| `rdc term connect -m <machine> -r <repo>` | Depoya SSH terminali aç (DOCKER_HOST ayarlar) |
| `rdc term connect -m <machine> -c "<command>"` | Makinede komut çalıştır |
| `rdc repo sync upload -m <machine> -r <repo> --local <paths...>` | Bir dosyayı, dizini veya birden çok kaynağı depoya yükle |
| `rdc repo sync download -m <machine> -r <repo> --local <dir>` | Depo dizinini yerele indir |
| `rdc repo sync download -m <machine> -r <repo> --remote-file <path> --local <dir>` | Tek bir uzak dosyayı yerel bir dizine indir |
| `rdc vscode connect -m <machine> -r <repo>` | VS Code Remote SSH oturumu aç |

## Yapılandırma

| Komut | Açıklama |
|-------|----------|
| `rdc config init --name <name>` | Adlandırılmış yapılandırma dosyası oluştur |
| `rdc config machine add --name <machine> --host <host> --user <user>` | Yapılandırmaya makine ekle |
| `rdc config storage import --file rclone.conf` | rclone yapılandırmasından depolama sağlayıcıları içe aktar |
| `rdc config storage list` | Yapılandırılmış depolama sağlayıcılarını listele |
| `rdc config backup-strategy set ...` | Adlandırılmış yedekleme stratejisi tanımla |
| `rdc --config <name> <command>` | Adlandırılmış yapılandırma dosyası kullan |

## Hata Ayıklama ve Doğrudan Erişim

| Komut | Açıklama |
|-------|----------|
| `rdc term connect -m <machine> -r <repo> -c "docker ps"` | Depodaki konteynerleri listele |
| `rdc term connect -m <machine> -r <repo> -c "docker logs <name>"` | Konteyner günlüklerini al |
| `rdc term connect -m <machine> -r <repo> -c "docker exec <name> <cmd>"` | Konteynerde komut çalıştır |
| `rdc term connect -m <machine> -r <repo> -c "docker restart <name>"` | Konteyneri yeniden başlat |
