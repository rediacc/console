---
title: "Kurulum Sonrası"
description: "Rediacc icin otomatik baslatma yapilandirmasi, baglam yapisi ve sorun giderme."
category: "Getting Started"
order: 3
language: tr
---

# Kurulum Sonrası

[Adım Adım Rehber](/tr/docs/guide) tamamlandıktan sonra, bu sayfa otomatik başlatma yapılandırmasını, bağlam yapılandırma dosyasını ve yaygın sorunların giderilmesini kapsar.

## Önyükleme Sırasında Otomatik Başlatma

Varsayılan olarak, bir sunucu yeniden başlatıldıktan sonra depoların manuel olarak bağlanması ve başlatılması gerekir. **Otomatik başlatma**, depoların sunucu açılışında otomatik olarak bağlanmasını, Docker'ın başlatılmasını ve Rediaccfile `up()` fonksiyonunun çalıştırılmasını yapılandırır.

### Nasıl Çalışır

Bir depo için otomatik başlatmayı etkinleştirdiğinizde:

1. 256 baytlık rastgele bir LUKS anahtar dosyası oluşturulur ve deponun LUKS slot 1'ine eklenir (slot 0, kullanıcı parolası olarak kalır).
2. Anahtar dosyası, `{datastore}/.credentials/keys/{guid}.key` konumunda `0600` izinleriyle (yalnızca root) saklanır.
3. Açılışta tüm etkinleştirilmiş depoları bağlayan ve servislerini başlatan bir systemd servisi (`rediacc-autostart`) kurulur.

Sistem kapatma veya yeniden başlatma sırasında, servis tüm servisleri düzgün bir şekilde durdurur (Rediaccfile `down()`), Docker daemon'larını kapatır ve LUKS birimlerini kapatır.

> **Güvenlik notu:** Otomatik başlatmayı etkinleştirmek, sunucu diskinde bir LUKS anahtar dosyası saklar. Sunucuya root erişimi olan herkes, parola girmeden depoyu bağlayabilir. Bu, kolaylık (otomatik açılış) ve güvenlik (manuel parola girişi gerektirme) arasında bir ödünleşimdir. Bunu kendi tehdit modelinize göre değerlendirin.

### Otomatik Başlatmayı Etkinleştirme

```bash
rdc repo autostart enable my-app -m server-1
```

Depo parolası sorulacaktır. Bu, anahtar dosyasının LUKS birimine eklenmesini yetkilendirmek için gereklidir.

### Tüm Depolar İçin Otomatik Başlatmayı Etkinleştirme

```bash
rdc repo autostart enable-all -m server-1
```

### Otomatik Başlatmayı Devre Dışı Bırakma

```bash
rdc repo autostart disable my-app -m server-1
```

Bu, anahtar dosyasını kaldırır ve LUKS slot 1'i siler. Depo artık açılışta otomatik olarak bağlanmayacaktır.

### Otomatik Başlatma Durumunu Listeleme

```bash
rdc repo autostart list -m server-1
```

Hangi depoların otomatik başlatmasının etkin olduğunu ve systemd servisinin kurulu olup olmadığını gösterir.

## Bağlam Yapılandırmasını Anlama

Tüm bağlam yapılandırması `~/.rediacc/config.json` dosyasında saklanır. Rehberi tamamladıktan sonra bu dosyanın nasıl göründüğüne dair açıklamalı bir örnek:

```json
{
  "contexts": {
    "production": {
      "name": "production",
      "mode": "local",
      "apiUrl": "local://",
      "ssh": {
        "privateKeyPath": "/home/you/.ssh/id_ed25519"
      },
      "machines": {
        "prod-1": {
          "ip": "203.0.113.50",
          "user": "deploy",
          "port": 22,
          "datastore": "/mnt/rediacc",
          "knownHosts": "203.0.113.50 ssh-ed25519 AAAA..."
        }
      },
      "repositories": {
        "webapp": {
          "repositoryGuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
          "credential": "base64-encoded-random-passphrase",
          "networkId": 2816
        }
      }
    }
  }
}
```

**Temel alanlar:**

| Alan | Açıklama |
|------|----------|
| `mode` | Yerel mod için `"local"`, S3 destekli bağlamlar için `"s3"`. |
| `apiUrl` | `"local://"` yerel modu belirtir (uzak API yok). |
| `ssh.privateKeyPath` | Tüm makine bağlantıları için kullanılan SSH özel anahtarının yolu. |
| `machines.<name>.knownHosts` | Sunucu kimliğini doğrulamak için `ssh-keyscan`'den alınan SSH host anahtarları. |
| `repositories.<name>.repositoryGuid` | Sunucudaki şifrelenmiş disk imajını tanımlayan UUID. |
| `repositories.<name>.credential` | LUKS şifreleme parolası. **Sunucuda saklanmaz.** |
| `repositories.<name>.networkId` | IP alt ağını belirleyen ağ kimliği (2816 + n*64). Otomatik atanır. |

> Bu dosya hassas veriler (SSH anahtar yolları, LUKS kimlik bilgileri) içerir. `0600` izinleriyle (yalnızca sahip okuma/yazma) saklanır. Paylaşmayın veya sürüm kontrolüne eklemeyin.

## Sorun Giderme

### SSH Bağlantısı Başarısız Oluyor

- Manuel olarak bağlanabildiğinizi doğrulayın: `ssh -i ~/.ssh/id_ed25519 deploy@203.0.113.50`
- Host anahtarlarını yenilemek için `rdc context scan-keys server-1` komutunu çalıştırın
- SSH portunun eşleştiğini kontrol edin: `--port 22`

### Makine Hazırlama Başarısız Oluyor

- Kullanıcının parolasız sudo erişimine sahip olduğundan emin olun veya gerekli komutlar için `NOPASSWD` yapılandırın
- Sunucudaki kullanılabilir disk alanını kontrol edin
- Ayrıntılı çıktı için `--debug` ile çalıştırın: `rdc context setup-machine server-1 --debug`

### Depo Oluşturma Başarısız Oluyor

- Hazırlığın tamamlandığını doğrulayın: veri deposu dizini mevcut olmalıdır
- Sunucudaki disk alanını kontrol edin
- renet ikili dosyasının kurulu olduğundan emin olun (gerekirse hazırlığı tekrar çalıştırın)

### Servisler Başlatılamıyor

- Rediaccfile söz dizimini kontrol edin: geçerli Bash olmalıdır
- `docker compose` dosyalarının `network_mode: host` kullandığından emin olun
- Docker imajlarının erişilebilir olduğunu doğrulayın (`prep()` içinde `docker compose pull` kullanmayı düşünün)
- Konteyner günlüklerini kontrol edin: sunucuya SSH ile bağlanın ve `docker -H unix:///var/run/rediacc/docker-{networkId}.sock logs {container}` komutunu kullanın

### İzin Reddedildi Hataları

- Depo işlemleri sunucuda root gerektirir (renet `sudo` ile çalışır)
- Kullanıcınızın `sudo` grubunda olduğunu doğrulayın
- Veri deposu dizininin doğru izinlere sahip olup olmadığını kontrol edin

### Tanılama Çalıştırma

Sorunları teşhis etmek için yerleşik doctor komutunu kullanın:

```bash
rdc doctor
```

Bu komut ortamınızı, renet kurulumunu, bağlam yapılandırmasını ve kimlik doğrulama durumunu kontrol eder.
