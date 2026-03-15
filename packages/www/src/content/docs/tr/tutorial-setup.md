---
title: "Makine Kurulumu"
description: "Bir yapılandırma profili oluşturun, uzak bir makine kaydedin, SSH bağlantısını doğrulayın ve altyapı ayarlarını yapılandırın."
category: "Tutorials"
order: 2
language: tr
sourceHash: "04756cddd86e097c"
---

# Rediacc ile Makine Nasıl Kurulur

Her Rediacc dağıtımı bir yapılandırma profili ve kayıtlı bir makine ile başlar. Bu öğreticide, bir yapılandırma oluşturacak, uzak bir sunucu kaydedecek, SSH bağlantısını doğrulayacak, ortam tanılamalarını çalıştıracak ve altyapı ağını yapılandıracaksınız. Bitirdiğinizde, makineniz depo dağıtımları için hazır olacaktır.

## Ön Koşullar

- `rdc` CLI kurulu
- SSH üzerinden erişilebilir bir uzak sunucu (veya yerel VM)
- Sunucuya kimlik doğrulaması yapabilen bir SSH özel anahtarı

## Etkileşimli Kayıt

![Öğretici: Makine kurulumu ve yapılandırma](/assets/tutorials/setup-tutorial.cast)

### Adım 1: Yeni yapılandırma oluşturun

Bir yapılandırma profili makine tanımlarını, SSH kimlik bilgilerini ve altyapı ayarlarını saklar. Bu ortam için bir tane oluşturun.

```bash
rdc config init tutorial-demo --ssh-key ~/.ssh/id_ed25519
```

Bu, `~/.config/rediacc/tutorial-demo.json` konumunda adlandırılmış bir yapılandırma dosyası oluşturur.

### Adım 2: Yapılandırmaları görüntüleyin

Yeni profilin yapılandırma listesinde göründüğünü doğrulayın.

```bash
rdc config list
```

Tüm mevcut yapılandırmaları adaptör türü (yerel veya bulut) ve makine sayısı ile listeler.

### Adım 3: Makine ekleyin

IP adresi ve SSH kullanıcısıyla bir makine kaydedin. CLI, sunucunun host anahtarlarını `ssh-keyscan` aracılığıyla otomatik olarak alır ve saklar.

```bash
rdc config machine add bridge-vm --ip 192.168.111.1 --user muhammed --config tutorial-demo
```

### Adım 4: Makineleri görüntüleyin

Makinenin doğru şekilde kaydedildiğini onaylayın.

```bash
rdc config machine list --config tutorial-demo
```

Mevcut yapılandırmadaki tüm makineleri bağlantı ayrıntılarıyla gösterir.

### Adım 5: Varsayılan makineyi ayarlayın

Varsayılan bir makine ayarlamak, her komutta `-m bridge-vm` tekrarını önler.

```bash
rdc config set machine bridge-vm --config tutorial-demo
```

### Adım 6: Bağlantıyı test edin

Herhangi bir şey dağıtmadan önce, makinenin SSH üzerinden erişilebilir olduğunu doğrulayın.

```bash
rdc term bridge-vm -c "hostname"
rdc term bridge-vm -c "uptime"
```

Her iki komut da uzak makinede çalışır ve hemen sonuç döndürür. Herhangi biri başarısız olursa, SSH anahtarınızın doğru olduğunu ve sunucuya erişilebildiğini kontrol edin.

### Adım 7: Tanılama çalıştırın

```bash
rdc doctor
```

Yerel ortamınızı kontrol eder: CLI sürümü, Docker, renet ikili dosyası, yapılandırma durumu, SSH anahtarı ve sanallaştırma ön koşulları. Her kontrol **OK**, **Warning** veya **Error** bildirir.

### Adım 8: Altyapıyı yapılandırın

Halka açık hizmetler için makinenin ağ yapılandırmasına ihtiyacı vardır — harici IP'si, bir temel alan adı ve TLS için bir sertifika e-postası.

```bash
rdc config infra set bridge-vm \
  --public-ipv4 192.168.111.1 \
  --base-domain test.local \
  --cert-email admin@test.local
```

Yapılandırmayı doğrulayın:

```bash
rdc config infra show bridge-vm
```

Oluşturulan Traefik proxy yapılandırmasını `rdc config infra push bridge-vm` ile sunucuya dağıtın.

## Sorun Giderme

**"SSH key not found" veya "Permission denied (publickey)"**
`config init`'e geçirilen anahtar yolunun mevcut olduğunu ve sunucunun `authorized_keys` ile eşleştiğini doğrulayın. İzinleri kontrol edin: özel anahtar dosyası `600` olmalıdır (`chmod 600 ~/.ssh/id_ed25519`).

**SSH komutlarında "Connection refused"**
Sunucunun çalıştığını ve IP'nin doğru olduğunu onaylayın. Port 22'nin açık olduğunu kontrol edin: `nc -zv <ip> 22`. Standart olmayan bir port kullanıyorsanız, makine eklerken `--port` parametresini geçirin.

**"Host key verification failed"**
Saklanan host anahtarı sunucunun mevcut anahtarıyla eşleşmiyor. Bu, sunucu yeniden oluşturulduktan veya IP yeniden atandıktan sonra gerçekleşir. Anahtarı yenilemek için `rdc config machine scan-keys <machine>` komutunu çalıştırın.

## Sonraki Adımlar

Bir yapılandırma profili oluşturdunuz, bir makine kaydettiniz, bağlantıyı doğruladınız ve altyapı ağını yapılandırdınız. Uygulamaları dağıtmak için:

- [Makine Kurulumu](/tr/docs/setup) — tüm yapılandırma ve kurulum komutları için tam referans
- [Öğretici: Depo Yaşam Döngüsü](/tr/docs/tutorial-repos) — depo oluşturma, dağıtma ve yönetme
- [Hızlı Başlangıç](/tr/docs/quick-start) — konteynerleştirilmiş bir uygulamayı uçtan uca dağıtma
