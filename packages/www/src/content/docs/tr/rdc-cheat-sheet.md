---
title: RDC CLI Hızlı Referans
description: "rdc komutları için hızlı referans: yapılandırmalar, depolar, makineler, senkronizasyon ve konteynerler. Tüm seçenekleri görmek için herhangi bir komuta --help ekleyin."
category: Guides
order: 3
language: tr
sourceHash: "d92987c4766d91ae"
sourceCommit: "70a4ca883754f1c0a7f4684c9fde02a5a01d3681"
---

# RDC CLI Hızlı Referans

Burada her `rdc` komutu listelenmemiştir, yalnızca her dağıtımda ortaya çıkan komutlar vardır. Tüm seçenekleri görmek için herhangi bir `rdc` komutunu `--help` ile çalıştırın. Kenar durumları ve nadiren kullanılan seçenekler tam referansta bulunmaktadır.

## Depo Yaşam Döngüsü

| Komut | Açıklama |
|-------|----------|
| `rdc repo create <repo> -m <machine>` | Bir makinede yeni depo oluştur |
| `rdc repo up <repo>@<machine>` | Depoyu dağıt veya güncelle |
| `rdc repo down <repo>@<machine>` | Depoyu durdur |
| `rdc repo delete <repo>@<machine>` | Depoyu sil |
| `rdc repo fork <repo>@<machine> --tag <tag>` | Depoyu çatalla (neredeyse anında, BTRFS reflink) |
| `rdc repo promote <repo>:<tag>` | Doğrulanmış bir fork'u üst deponun adıyla üretime yükselt |
| `rdc repo list` | Ad ve GUID ile tüm depoları listele |

## Depo Gizli Anahtarları

Yalnızca dağıtım sırasında yazılabilen kimlik bilgileri. `get` komutu yalnızca özeti döndürür. Değer hiçbir zaman döndürülmez. Tam kılavuz için [Depolar § Gizli Anahtarlar](/en/docs/repositories#secrets) bölümüne bakın.

| Komut | Açıklama |
|-------|----------|
| `rdc repo secret set <repo> --key <KEY> --value <val> [--mode env\|file] --current ""` | Yeni bir gizli anahtar oluştur (`--current ""` ilk yazma için) |
| `rdc repo secret set <repo> --key <KEY> --value <val> --current <prev>` | Mevcut bir gizli anahtarın üzerine yaz (şifre tarzı ön koşul) |
| `rdc repo secret set <repo> --key <KEY> --value <val> --rotate-secret` | Önceki değeri doğrulamadan üzerine yaz (denetim günlüğüne rotasyon olarak kaydedilir) |
| `rdc repo secret list <repo>` | Gizli anahtar adlarını ve iletim modlarını listele (hiçbir zaman değerleri, hiçbir zaman özetleri değil) |
| `rdc repo secret get <repo> --key <KEY>` | Gizli anahtar özetini ve modunu göster (hiçbir zaman düz metin değer yok) |
| `rdc repo secret unset <repo> --key <KEY> --current <prev>` | Bir gizli anahtarı sil |
| `rdc repo secret unset <repo> --key <KEY> --rotate-secret` | Önceki değeri doğrulamadan sil |

> Çatallar hiçbir gizli anahtar devralmaz. Bunları çatal üzerinde açıkça `rdc repo secret set <repo>:<tag>` komutu ile ayarlayın.

## Yedekleme ve Geri Yükleme

| Komut | Açıklama |
|-------|----------|
| `rdc repo push <repo>@<machine> --to <storage>` | Depo yedeklemesini depolamaya gönder |
| `rdc repo pull <repo>@<machine> --from <storage>` | Depoyu depolamadan geri yükle |
| `rdc repo push ... --bwlimit <limit>` | Gönderme sırasında rsync bant genişliğini sınırla (örn. `10M`) |
| `rdc repo pull ... --bwlimit <limit>` | Alma sırasında rsync bant genişliğini sınırla |
| `rdc repo push ... --checkpoint` | Göndermeden önce konteynerlerde kontrol noktası oluştur |
| `rdc backup list --storage <storage> | Depolamadaki mevcut yedeklemeleri listele |
| `rdc storage browse <storage>` | Depolama içeriğine göz at |

## Depo Taşıma

| Komut | Açıklama |
|-------|----------|
| `rdc repo migrate <repo>@<machine> --to <machine>` | Depoyu makineler arasında taşı |
| `rdc repo migrate ... --provision` | Aktarmadan önce hedefe hazırlık yap |
| `rdc repo migrate ... --checkpoint` | Taşımadan önce kontrol noktası oluştur |
| `rdc repo migrate ... --skip-dns` | Taşıma sonrası DNS güncellemesini atla |
| `rdc repo migrate ... --bwlimit <limit>` | Aktarım bant genişliğini sınırla |

## Yedekleme Stratejileri

| Komut | Açıklama |
|-------|----------|
| `rdc backup strategy set <name> --destination <storage> --cron <expr> --mode <hot\|cold> --enable` | Adlandırılmış yedekleme stratejisi oluştur veya güncelle |
| `rdc backup strategy list` | Tanımlanmış tüm yedekleme stratejilerini listele |
| `rdc backup strategy show <name>` | Strateji ayrıntılarını göster |
| `rdc backup strategy remove <name>` | Stratejiyi kaldır |
| `rdc backup schedule -m <machine>` | Yapılandırılmış yedekleme stratejilerini bir makineye dağıt |

## Yedekleme İşlemleri

| Komut | Açıklama |
|-------|----------|
| `rdc backup schedule -m <machine>` | Bağlı stratejileri systemd zamanlayıcı olarak dağıt |
| `rdc backup schedule -m <machine> --dry-run` | Dağıtmadan zamanlayıcı birimlerini önizle (tokenlar gizli) |
| `rdc backup run -m <machine>` | Bağlı tüm stratejileri hemen çalıştır |
| `rdc backup run <name> -m <machine>` | Belirli bir stratejiyi hemen çalıştır |
| `rdc backup status -m <machine>` | Zamanlayıcı durumunu ve son iş sonuçlarını göster |
| `rdc backup status <name> -m <machine>` | Belirli bir stratejinin durumunu göster |
| `rdc backup cancel -m <machine>` | Çalışan yedeklemeleri iptal et |
| `rdc backup cancel <name> -m <machine>` | Belirli bir çalışan yedeklemeyi iptal et |

## Makine Yönetimi

| Komut | Açıklama |
|-------|----------|
| `rdc machine status <machine>` | Tam makine durumu (sistem, konteynerler, servisler, depolar, ağ) |
| `rdc machine status <machine> --system` | Yalnızca sistem bilgisi |
| `rdc machine status <machine> --containers` | Yalnızca konteyner listesi |
| `rdc machine status <machine> --repositories` | Yalnızca depo listesi |
| `rdc machine status <machine> --services` | Yalnızca servis listesi |
| `rdc machine status <machine> --network` | Yalnızca ağ bilgisi |
| `rdc machine status <machine> --block-devices` | Yalnızca blok cihaz bilgisi |
| `rdc machine list` | Yapılandırmadaki tüm makineleri listele |
| `rdc machine setup <machine>` | İlk makine hazırlığını çalıştır |
| `rdc machine prune <machine>` | Makineden kullanılmayan kaynakları kaldır |
| `rdc machine deprovision <machine>` | Makineyi tamamen kaldır |

## Terminal ve Senkronizasyon

| Komut | Açıklama |
|-------|----------|
| `rdc term connect <machine>` | Makineye SSH terminali aç |
| `rdc term connect <repo>@<machine>` | Depoya SSH terminali aç (DOCKER_HOST ayarlar) |
| `rdc term connect <machine> -c "<command>"` | Makinede komut çalıştır |
| `rdc repo sync upload <repo>@<machine> --local <paths...>` | Bir veya daha fazla yerel dosya/dizini depoya yükle |
| `rdc repo sync upload <repo>@<machine> --local <file> --remote-file <path>` | Tek bir yerel dosyayı belirli bir uzak yola yükle |
| `rdc repo sync download <repo>@<machine> --local <dir>` | Depo dizinini yerel olarak indir |
| `rdc repo sync download <repo>@<machine> --remote-file <path> --local <dir>` | Tek bir uzak dosyayı yerel bir dizine indir |
| `rdc vscode connect <repo>@<machine>` | VS Code Remote SSH oturumunu aç |

## Yapılandırma

| Komut | Açıklama |
|-------|----------|
| `rdc config init <name>` | Adlandırılmış yapılandırma dosyası oluştur |
| `rdc machine add <machine> --ip <host> --user <user>` | Yapılandırmaya makine ekle |
| `rdc storage import rclone.conf` | rclone yapılandırmasından depolama sağlayıcıları içe aktar |
| `rdc storage list` | Yapılandırılmış depolama sağlayıcılarını listele |
| `rdc backup strategy set ...` | Adlandırılmış yedekleme stratejisi tanımla |
| `rdc --config <name> <command>` | Adlandırılmış yapılandırma dosyası kullan |

## Hata Ayıklama ve Doğrudan Erişim

| Komut | Açıklama |
|-------|----------|
| `rdc term connect <repo>@<machine> -c "docker ps"` | Depodaki konteynerleri listele |
| `rdc term connect <repo>@<machine> -c "docker logs <name>"` | Konteyner günlüklerini al |
| `rdc term connect <repo>@<machine> -c "docker exec <name> <cmd>"` | Konteynerde komut çalıştır |
| `rdc term connect <repo>@<machine> -c "docker restart <name>"` | Konteyneri yeniden başlat |
