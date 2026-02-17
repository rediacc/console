---
title: "Sorun Giderme"
description: "SSH, kurulum, depolar, servisler ve Docker ile ilgili yaygın sorunların çözümleri."
category: "Guides"
order: 10
language: tr
---

# Sorun Giderme

Yaygın sorunlar ve çözümleri. Şüphe durumunda, kapsamlı bir tanılama kontrolü yapmak için `rdc doctor` ile başlayın.

## SSH Bağlantısı Başarısız

- Manuel olarak bağlanabildiğinizi doğrulayın: `ssh -i ~/.ssh/id_ed25519 deploy@203.0.113.50`
- Host anahtarlarını yenilemek için `rdc context scan-keys server-1` komutunu çalıştırın
- SSH portunun eşleştiğini kontrol edin: `--port 22`
- Bağlantıyı test edin: `rdc machine test-connection --ip 203.0.113.50 --user deploy`

## Host Anahtarı Uyuşmazlığı

Bir sunucu yeniden kurulduysa veya SSH anahtarları değiştiyse, "host key verification failed" hatası görürsünüz:

```bash
rdc context scan-keys server-1
```

Bu komut yeni host anahtarlarını alır ve yapılandırmanızı günceller.

## Makine Kurulumu Başarısız

- SSH kullanıcısının şifresiz sudo erişimine sahip olduğundan emin olun veya gerekli komutlar için `NOPASSWD` yapılandırın
- Sunucudaki kullanılabilir disk alanını kontrol edin
- Ayrıntılı çıktı için `--debug` ile çalıştırın: `rdc context setup-machine server-1 --debug`

## Depo Oluşturma Başarısız

- Kurulumun tamamlandığını doğrulayın: veri deposu dizini mevcut olmalıdır
- Sunucudaki disk alanını kontrol edin
- renet ikili dosyasının yüklü olduğundan emin olun (gerekirse kurulumu yeniden çalıştırın)

## Servisler Başlatılamıyor

- Rediaccfile sözdizimini kontrol edin: geçerli Bash olmalıdır
- `docker compose` dosyalarının `network_mode: host` kullandığından emin olun
- Docker imajlarının erişilebilir olduğunu doğrulayın (`prep()` içinde `docker compose pull` kullanmayı düşünün)
- Deponun Docker soketi üzerinden konteyner günlüklerini kontrol edin:

```bash
rdc term server-1 my-app -c "docker logs <container-name>"
```

Veya tüm konteynerleri görüntüleyin:

```bash
rdc machine containers server-1
```

## İzin Reddedildi Hataları

- Depo işlemleri sunucuda root gerektirir (renet `sudo` ile çalışır)
- SSH kullanıcınızın `sudo` grubunda olduğunu doğrulayın
- Veri deposu dizininin doğru izinlere sahip olduğunu kontrol edin

## Docker Soket Sorunları

Her deponun kendi Docker daemon'u vardır. Docker komutlarını manuel olarak çalıştırırken doğru soketi belirtmeniz gerekir:

```bash
# rdc term kullanarak (otomatik yapılandırılmış):
rdc term server-1 my-app -c "docker ps"

# Veya soket ile manuel olarak:
docker -H unix:///var/run/rediacc/docker-2816.sock ps
```

`2816` değerini deponuzun ağ kimliği ile değiştirin (`config.json` veya `rdc repo status` içinde bulunabilir).

## Konteynerler Yanlış Docker Daemon'da Oluşturulmuş

Konteynerleriniz deponun izole daemon'u yerine ana sistemin Docker daemon'unda görünüyorsa, en yaygın neden Rediaccfile içinde `sudo docker` kullanımıdır.

`sudo` ortam değişkenlerini sıfırlar, bu nedenle `DOCKER_HOST` kaybolur ve Docker varsayılan olarak sistem soketini (`/var/run/docker.sock`) kullanır. Rediacc bunu otomatik olarak engeller, ancak karşılaşırsanız:

- **`docker` komutunu doğrudan kullanın** — Rediaccfile fonksiyonları zaten yeterli yetkilerle çalışır
- sudo kullanmanız gerekiyorsa, ortam değişkenlerini korumak için `sudo -E docker` kullanın
- Rediaccfile dosyanızı `sudo docker` komutları için kontrol edin ve `sudo` kısmını kaldırın

## Terminal Çalışmıyor

`rdc term` bir terminal penceresi açamıyorsa:

- Komutları doğrudan çalıştırmak için `-c` ile satır içi modu kullanın:
  ```bash
  rdc term server-1 -c "ls -la"
  ```
- Satır içi modda sorun varsa `--external` ile harici terminali zorlayın
- Linux'ta `gnome-terminal`, `xterm` veya başka bir terminal emülatörünün yüklü olduğundan emin olun

## Tanılama Çalıştırma

```bash
rdc doctor
```

Bu komut ortamınızı, renet kurulumunu, bağlam yapılandırmasını ve kimlik doğrulama durumunu kontrol eder. Her kontrol OK, Warning veya Error durumunu kısa bir açıklama ile bildirir.
