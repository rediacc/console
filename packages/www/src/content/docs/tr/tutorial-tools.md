---
title: "Araçlar"
description: "SSH terminal erişimi, dosya senkronizasyonu, VS Code entegrasyonu ve CLI güncelleme komutlarını kullanın."
category: "Tutorials"
order: 5
language: tr
sourceHash: "f581499837e09360"
---

# Rediacc ile Terminal, Senkronizasyon ve VS Code Araçları Nasıl Kullanılır

CLI, günlük işlemler için üretkenlik araçları içerir: SSH terminal erişimi, rsync ile dosya senkronizasyonu, VS Code uzaktan geliştirme ve CLI güncellemeleri. Bu öğreticide, uzak komutlar çalıştıracak, dosyaları bir depoya senkronize edecek, VS Code entegrasyonunu kontrol edecek ve CLI sürümünüzü doğrulayacaksınız.

## Ön Koşullar

- Yapılandırması başlatılmış `rdc` CLI kurulu
- Çalışan bir deposu olan hazırlanmış bir makine (bkz. [Öğretici: Depo Yaşam Döngüsü](/tr/docs/tutorial-repos))

## Etkileşimli Kayıt

![Tutorial: Tools](/assets/tutorials/tools-tutorial.cast)

### Adım 1: Bir makineye bağlanın

Etkileşimli bir oturum açmadan SSH üzerinden uzak bir makinede satır içi komutlar çalıştırın.

```bash
rdc term server-1 -c "hostname"
rdc term server-1 -c "uptime"
```

`-c` bayrağı tek bir komutu çalıştırır ve çıktıyı döndürür. Etkileşimli bir SSH oturumu açmak için `-c`'yi atlayın.

### Adım 2: Bir depoya bağlanın

Bir deponun izole Docker ortamında komut çalıştırmak için:

```bash
rdc term server-1 my-app -c "docker ps"
```

Bir depoya bağlanıldığında, `DOCKER_HOST` otomatik olarak deponun izole Docker soketine ayarlanır. Herhangi bir Docker komutu yalnızca o deponun konteynerlerine karşı çalışır.

### Adım 3: Dosya senkronizasyonunu önizleyin (deneme çalıştırma)

Dosyaları aktarmadan önce nelerin değişeceğini önizleyin.

```bash
rdc sync upload -m server-1 -r my-app --local ./src --dry-run
```

`--dry-run` bayrağı, gerçekte hiçbir şey yüklemeden yeni dosyaları, değişen dosyaları ve toplam aktarım boyutunu gösterir.

### Adım 4: Dosyaları yükleyin

Yerel makinenizden uzak depo bağlama noktasına dosyaları aktarın.

```bash
rdc sync upload -m server-1 -r my-app --local ./src
```

Dosyalar SSH üzerinden rsync ile aktarılır. Sonraki yüklemelerde yalnızca değişen dosyalar gönderilir.

### Adım 5: Yüklenen dosyaları doğrulayın

Deponun bağlama dizinini listeleyerek dosyaların ulaştığını onaylayın.

```bash
rdc term server-1 my-app -c "ls -la"
```

### Adım 6: VS Code entegrasyon kontrolü

VS Code ile uzaktan geliştirme yapmak için gerekli bileşenlerin kurulu olduğunu doğrulayın.

```bash
rdc vscode check
```

VS Code kurulumunuzu, Remote SSH eklentisini ve SSH yapılandırmasını kontrol eder. Eksik ön koşulları çözmek için çıktıyı takip edin, ardından `rdc vscode <machine> [repo]` ile bağlanın.

### Adım 7: CLI güncellemelerini kontrol edin

```bash
rdc update --check-only
```

CLI'nin daha yeni bir sürümünün mevcut olup olmadığını bildirir. Güncellemeyi yüklemek için `--check-only` olmadan `rdc update` komutunu çalıştırın.

## Sorun Giderme

**Dosya senkronizasyonu sırasında "rsync: command not found"**
Hem yerel makinenize hem de uzak sunucuya rsync kurun. Debian/Ubuntu'da: `sudo apt install rsync`. macOS'ta: rsync varsayılan olarak dahildir.

**Senkronizasyon yüklemesi sırasında "Permission denied"**
SSH kullanıcınızın depo bağlama dizinine yazma erişimi olduğunu doğrulayın. Depo bağlama noktaları, makine kaydı sırasında belirtilen kullanıcıya aittir.

**"VS Code Remote SSH extension not found"**
VS Code marketplace'ten eklentiyi kurun: Microsoft'un "Remote - SSH" eklentisini arayın. Kurduktan sonra VS Code'u yeniden başlatın ve `rdc vscode check` komutunu tekrar çalıştırın.

## Sonraki Adımlar

Uzak komutlar çalıştırdınız, dosyaları senkronize ettiniz, VS Code entegrasyonunu kontrol ettiniz ve CLI güncellemelerini doğruladınız. Verilerinizi korumak için:

- [Tools](/tr/docs/tools) — terminal, senkronizasyon, VS Code ve güncelleme komutları için tam referans
- [Öğretici: Yedekleme ve Ağ](/tr/docs/tutorial-backup) — yedekleme planlaması ve ağ yapılandırması
- [Hizmetler](/tr/docs/services) — Rediaccfile referansı ve hizmet ağları
