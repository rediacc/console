---
title: "Hub"
description: "Otomatik provizyon, boşta kalma yönetimi ve checkpoint/geri yükleme ile kimlik doğrulamalı, kullanıcı bazlı konteyner ortamları sağlayın."
category: "Guides"
order: 14
language: tr
sourceHash: "1fc292d45411451c"
sourceCommit: "b41fcf7b6f7e7235c0b7ca008df638c9aec5985e"
---

# Hub

Hub, OAuth kimlik doğrulaması arkasında kullanıcı bazlı konteyner ortamları sağlar. Kullanıcılar tek bir URL'yi ziyaret eder, herhangi bir OAuth2 sağlayıcısı ile kimlik doğrulaması yapar ve şeffaf bir şekilde kişisel konteynerlerine yönlendirilir. Konteynerler talep üzerine oluşturulur ve otomatik olarak yönetilir.

Her şey `docker-compose.yml` etiketleri aracılığıyla yapılandırılır. Hub, konteynerlerin içinde ne çalıştığını bilmez ve umursamaz -- kimlik doğrulama, yönlendirme ve yaşam döngüsünü yönetir. Depolar davranışı tanımlar.

## Nasıl çalışır

![Hub Mimarisi](/img/hub-architecture.svg)

1. Bir kullanıcı `code.example.com` adresini ziyaret eder
2. Hub oturum çerezini kontrol eder. Yoksa, kullanıcı yapılandırılan OAuth2 sağlayıcısına (Nextcloud, Keycloak, GitHub, vb.) yönlendirilir
3. Kimlik doğrulamasının ardından Hub kullanıcıyı tanımlar ve konteynerini arar
4. Konteyner yoksa, yapılandırılan şablondan talep üzerine bir tane oluşturulur
5. İstek ters proxy aracılığıyla kullanıcının konteynerine iletilir
6. Hub, ana bilgisayar adına göre hangi porta proxy yapılacağını belirler (örneğin `code.` -> port 8080, `term.` -> port 7681)

Boşta kalan konteynerler otomatik olarak durdurulur veya bir sonraki girişte anında devam etmek için checkpoint (CRIU) ile kaydedilir.

## Hızlı başlangıç

Hub'ı deponuzun `docker-compose.yml` dosyasına servis olarak ekleyin:

```yaml
services:
  hub:
    image: ubuntu:24.04
    entrypoint: /usr/bin/renet
    command:
      - hub
      - start
      - --docker-socket=/var/run/rediacc/docker-${REDIACC_NETWORK_ID}.sock
      - --network-id=${REDIACC_NETWORK_ID}
      - --base-domain=${HUB_DOMAIN}
      - --workspace-dir=${REDIACC_WORKING_DIR}/workspaces
    env_file:
      - ./hub.env
    volumes:
      - /usr/lib/rediacc/renet/current/renet:/usr/bin/renet:ro
      - /var/run/rediacc/docker-${REDIACC_NETWORK_ID}.sock:/var/run/rediacc/docker-${REDIACC_NETWORK_ID}.sock
      - ./workspaces:${REDIACC_WORKING_DIR}/workspaces
    labels:
      - "traefik.enable=true"

      # Rota eşleme: alt alan adı öneki -> kullanıcı konteynerlerindeki port
      - "rediacc.hub.route.code=8080"
      - "rediacc.hub.route.term=7681"
      - "rediacc.hub.route.desktop=6080"

      # Konteyner şablonu
      - "rediacc.hub.image=ghcr.io/your-org/devcontainer:latest"
      - "rediacc.hub.command=start-desktop.sh & ttyd --writable --port 7681 bash & exec openvscode-server --host $${SERVICE_IP} --port 8080"
      - "rediacc.hub.user=vscode"

      # Traefik rotaları (alt alan adı başına bir tane)
      - "traefik.http.routers.hub-code.rule=Host(`code.${HUB_DOMAIN}`)"
      - "traefik.http.routers.hub-code.entrypoints=websecure"
      - "traefik.http.routers.hub-code.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-code.loadbalancer.server.port=7112"
      - "traefik.http.routers.hub-term.rule=Host(`term.${HUB_DOMAIN}`)"
      - "traefik.http.routers.hub-term.entrypoints=websecure"
      - "traefik.http.routers.hub-term.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-term.loadbalancer.server.port=7112"
      - "traefik.http.routers.hub-desktop.rule=Host(`desktop.${HUB_DOMAIN}`)"
      - "traefik.http.routers.hub-desktop.entrypoints=websecure"
      - "traefik.http.routers.hub-desktop.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-desktop.loadbalancer.server.port=7112"
```

OAuth2 sağlayıcı kimlik bilgilerinizle `hub.env` dosyasını oluşturun:

```bash
HUB_DOMAIN=example.com
HUB_OAUTH_CLIENT_ID=your-client-id
HUB_OAUTH_CLIENT_SECRET=your-client-secret
HUB_OAUTH_AUTHORIZE_URL=https://auth.example.com/authorize
HUB_OAUTH_TOKEN_URL=https://auth.example.com/token
HUB_OAUTH_USERINFO_URL=https://auth.example.com/userinfo
HUB_OAUTH_USERINFO_PATH=preferred_username
HUB_SESSION_SECRET=64-character-hex-string
```

`rdc repo up` ile dağıtım yapın.

## Yapılandırma

Tüm Hub yapılandırması, Hub servisinin kendisindeki Compose etiketlerinde bulunur. Hub ikili dosyası içinde yapılandırma dosyası yoktur.

### Rota eşleme

Alt alan adı öneklerini kullanıcı konteynerlerindeki portlarla eşleyin. Hub bu etiketleri okuyarak her isteğin nereye yönlendirileceğini belirler.

| Etiket | Açıklama | Örnek |
|-------|-------------|---------|
| `rediacc.hub.route.{prefix}` | `{prefix}.{domain}` adresini kullanıcının konteynerindeki bu porta eşler | `rediacc.hub.route.code=8080` |

İstediğiniz kadar rota tanımlayabilirsiniz. Önek, ana bilgisayar adının ilk segmentiyle eşleştirilir:

```yaml
labels:
  - "rediacc.hub.route.code=8080"      # code.example.com -> :8080
  - "rediacc.hub.route.term=7681"      # term.example.com -> :7681
  - "rediacc.hub.route.desktop=6080"   # desktop.example.com -> :6080
  - "rediacc.hub.route.jupyter=8888"   # jupyter.example.com -> :8888
```

Her rotanın ayrıca Hub'ın portuna (7112) işaret eden eşleştirilmiş bir Traefik yönlendiricisine ihtiyacı vardır. Hub, kullanıcı bazlı yönlendirmeyi dahili olarak yönetir.

### Konteyner şablonu

Kullanıcı konteynerlerinin nasıl görüneceğini tanımlayın. Hub bu etiketleri okur ve bir kullanıcı için yeni bir konteyner oluştururken kullanır.

| Etiket | Açıklama | Varsayılan |
|-------|-------------|---------|
| `rediacc.hub.image` | Konteyner imajı | `--container-image` bayrağı değeri |
| `rediacc.hub.command` | Başlangıç komutu (bash -c uyumlu) | yok |
| `rediacc.hub.user` | Konteyner kullanıcısı (root olmayan önerilir) | `vscode` |
| `rediacc.hub.workspace` | Konteyner içindeki çalışma alanı bağlama noktası | `/workspace` |
| `rediacc.hub.shm_size` | Paylaşılan bellek boyutu (bayt) | `1073741824` (1 GB) |

`command` etiketi `${SERVICE_IP}` genişletmesini destekler; oluşturma sırasında konteynerin atanan loopback IP'si ile değiştirilir.

```yaml
labels:
  - "rediacc.hub.image=ghcr.io/my-org/dev-env:latest"
  - "rediacc.hub.command=exec jupyter lab --ip=$${SERVICE_IP} --port=8888 --no-browser"
  - "rediacc.hub.user=1000:1000"
  - "rediacc.hub.workspace=/home/jovyan/work"
```

> **İpucu:** Docker Compose tarafından ortam değişkenlerinin erken genişletilmesini önlemek için Compose etiketlerinde literal `$` için `$$` kullanın.

### Kaynak sınırları

Tek bir kullanıcının tüm ana bilgisayar kaynaklarını tüketmesini önlemek için kullanıcı bazlı kaynak sınırları belirleyin.

| Etiket | Açıklama | Örnek |
|-------|-------------|---------|
| `rediacc.hub.limits.cpu` | CPU sınırı (çekirdek) | `2` |
| `rediacc.hub.limits.memory` | Bellek sınırı | `4g` |

```yaml
labels:
  - "rediacc.hub.limits.cpu=2"
  - "rediacc.hub.limits.memory=4g"
```

### Yaşam döngüsü kancaları

Yaşam döngüsünün belirli noktalarında kullanıcı konteyneri içinde komutlar çalıştırın.

| Etiket | Ne zaman çalışır | Örnek |
|-------|-------------|---------|
| `rediacc.hub.hook.on_create` | Konteyner oluşturulduktan sonra (ilk giriş) | Depoları klonla, bağımlılıkları yükle |
| `rediacc.hub.hook.on_start` | Konteyner başlatıldıktan veya geri yüklendikten sonra | Sırları bağla, tokenları yenile |
| `rediacc.hub.hook.on_idle` | Konteyner durdurulmadan veya checkpoint oluşturulmadan önce | Durumu kaydet, değişiklikleri gönder |

```yaml
labels:
  - "rediacc.hub.hook.on_create=git clone https://github.com/org/repo /workspace/project"
  - "rediacc.hub.hook.on_start=echo Welcome back, $HUB_USER"
  - "rediacc.hub.hook.on_idle=cd /workspace && git stash"
```

### Checkpoint / Geri yükleme

Etkinleştirildiğinde, boşta kalan konteynerler durdurulmak yerine CRIU kullanılarak checkpoint olarak kaydedilir. Bir sonraki girişte konteyner saniyeler içinde checkpoint'ten geri yüklenir ve tam durum korunur: açık dosyalar, çalışan işlemler, terminal oturumları.

| Etiket | Açıklama | Varsayılan |
|-------|-------------|---------|
| `rediacc.hub.checkpoint` | Kullanıcı konteynerleri için CRIU checkpoint'i etkinleştir | `false` |

Hub'ı başlatırken `--checkpoint` de geçirin:

```yaml
command:
  - hub
  - start
  - --checkpoint
  - ...diğer bayraklar...
```

> **Not:** Checkpoint/geri yükleme, CRIU ikili dosyasının ana bilgisayarda mevcut olması ve konteynerin ana bilgisayar ağ modunda çalışması gerektirir (Rediacc servisleri için varsayılan).

### Erişim kontrolü

Hub'ı kimin kullanabileceğini ve kimin yönetici ayrıcalıklarını belirleyin.

| Etiket | Açıklama | Örnek |
|-------|-------------|---------|
| `rediacc.hub.allowed_groups` | Hub'ı kullanmasına izin verilen virgülle ayrılmış gruplar | `developers,ops` |
| `rediacc.hub.admin_users` | Virgülle ayrılmış yönetici kullanıcı adları | `alice,bob` |

Yönetici kullanıcılar panelde tüm konteynerleri görebilir ve yönetebilir. Normal kullanıcılar yalnızca kendilerinkini görür.

### Geçici mod

Varsayılan olarak, kullanıcı çalışma alanları kalıcıdır (konteyner yeniden başlatmalarında hayatta kalır). Geçici mod her girişte temiz bir ortam sağlar ve demolar, eğitim veya CI için kullanışlıdır.

| Etiket | Açıklama | Varsayılan |
|-------|-------------|---------|
| `rediacc.hub.mode` | `persistent` veya `ephemeral` | `persistent` |

```yaml
labels:
  - "rediacc.hub.mode=ephemeral"
```

Geçici modda çalışma alanı tmpfs (RAM destekli) kullanır ve konteyner durdurulduğunda otomatik olarak kaldırılır.

### Çoklu şablon desteği

Birden fazla ortam türü sunun. Kullanıcılar ilk girişte şablonlarını seçebilir veya panel üzerinden değiştirebilir.

```yaml
labels:
  # Varsayılan şablon
  - "rediacc.hub.template.default=fulldev"

  # Tam geliştirme ortamı
  - "rediacc.hub.template.fulldev.image=ghcr.io/org/devcontainer:latest"
  - "rediacc.hub.template.fulldev.command=start-desktop.sh & ttyd ... & exec openvscode-server ..."
  - "rediacc.hub.template.fulldev.description=Full development environment with VS Code, terminal, and desktop"

  # Hafif seçenek
  - "rediacc.hub.template.lite.image=ghcr.io/org/devcontainer:lite"
  - "rediacc.hub.template.lite.command=exec openvscode-server --host $${SERVICE_IP} --port 8080"
  - "rediacc.hub.template.lite.description=VS Code only (lightweight, faster startup)"
```

## OAuth kurulumu

Hub herhangi bir standart OAuth2 sağlayıcısı ile çalışır. Yapılandırma Compose etiketleri değil, ortam değişkenleri aracılığıyla yapılır (sırlar etiketlerde olmamalıdır).

| Değişken | Açıklama | Gerekli |
|----------|-------------|----------|
| `HUB_OAUTH_CLIENT_ID` | OAuth2 istemci kimlik bilgisi | Evet |
| `HUB_OAUTH_CLIENT_SECRET` | OAuth2 istemci sırrı | Evet |
| `HUB_OAUTH_AUTHORIZE_URL` | Sağlayıcının yetkilendirme uç noktası | Evet |
| `HUB_OAUTH_TOKEN_URL` | Sağlayıcının token uç noktası | Evet |
| `HUB_OAUTH_USERINFO_URL` | Sağlayıcının kullanıcı bilgisi uç noktası | Evet |
| `HUB_OAUTH_USERINFO_PATH` | JSON yanıtından kullanıcı adını çıkaracak noktalı yol | Evet |
| `HUB_OAUTH_REDIRECT_URI` | Geri arama URL'sini geçersiz kıl (boşsa otomatik hesaplanır) | Hayır |
| `HUB_OAUTH_SCOPES` | Ek kapsamlar (boşlukla ayrılmış) | Hayır |
| `HUB_SESSION_SECRET` | Çerez imzalama için 32+ bayt onaltılık dize | Önerilen |

### Sağlayıcı örnekleri

**Nextcloud:**
```bash
HUB_OAUTH_AUTHORIZE_URL=https://cloud.example.com/apps/oauth2/authorize
HUB_OAUTH_TOKEN_URL=https://cloud.example.com/apps/oauth2/api/v1/token
HUB_OAUTH_USERINFO_URL=https://cloud.example.com/ocs/v2.php/cloud/user?format=json
HUB_OAUTH_USERINFO_PATH=ocs.data.id
```

**Keycloak:**
```bash
HUB_OAUTH_AUTHORIZE_URL=https://auth.example.com/realms/master/protocol/openid-connect/auth
HUB_OAUTH_TOKEN_URL=https://auth.example.com/realms/master/protocol/openid-connect/token
HUB_OAUTH_USERINFO_URL=https://auth.example.com/realms/master/protocol/openid-connect/userinfo
HUB_OAUTH_USERINFO_PATH=preferred_username
```

**GitHub:**
```bash
HUB_OAUTH_AUTHORIZE_URL=https://github.com/login/oauth/authorize
HUB_OAUTH_TOKEN_URL=https://github.com/login/oauth/access_token
HUB_OAUTH_USERINFO_URL=https://api.github.com/user
HUB_OAUTH_USERINFO_PATH=login
HUB_OAUTH_SCOPES=read:user
```

`HUB_OAUTH_USERINFO_PATH`, JSON yanıtına noktayla ayrılmış bir yoldur. Nextcloud'un `{"ocs":{"data":{"id":"alice"}}}` gibi iç içe geçmiş nesneleri için `ocs.data.id` kullanın.

## Panel

Hub, `/_hub/dashboard` adresinde self-servis bir panel içerir. Gösterilen bilgiler:

- Durumlarıyla birlikte çalışan tüm ortamlar
- Servis bağlantıları (kod, terminal veya masaüstünü açmak için tek tıkla)
- Boşta kalma zamanlayıcıları ve kaynak kullanımı
- Başlatma/durdurma kontrolleri
- Yönetici kullanıcılar tüm konteynerleri görebilir ve yönetebilir

Kimlik doğrulaması yaptıktan sonra `https://code.example.com/_hub/dashboard` adresini ziyaret ederek panele erişin.

## Örnekler

### Geliştirme ortamı (VS Code + Terminal + Masaüstü)

OpenVSCode Server, web terminali (ttyd) ve noVNC masaüstü ile tam bir geliştirme ortamı:

```yaml
labels:
  - "rediacc.hub.route.code=8080"
  - "rediacc.hub.route.term=7681"
  - "rediacc.hub.route.desktop=6080"
  - "rediacc.hub.image=ghcr.io/your-org/devcontainer:latest"
  - "rediacc.hub.command=start-desktop.sh & ttyd --writable --port 7681 bash & exec openvscode-server --host $${SERVICE_IP} --port 8080 --without-connection-token"
  - "rediacc.hub.user=vscode"
  - "rediacc.hub.limits.cpu=2"
  - "rediacc.hub.limits.memory=4g"
  - "rediacc.hub.hook.on_create=git clone https://github.com/org/project /workspace/project"
```

### Jupyter Notebook ortamı

JupyterLab ile veri bilimi ortamı:

```yaml
labels:
  - "rediacc.hub.route.notebook=8888"
  - "rediacc.hub.image=jupyter/datascience-notebook:latest"
  - "rediacc.hub.command=exec jupyter lab --ip=$${SERVICE_IP} --port=8888 --no-browser --NotebookApp.token='' --NotebookApp.password=''"
  - "rediacc.hub.user=1000:100"
  - "rediacc.hub.workspace=/home/jovyan/work"
  - "rediacc.hub.limits.cpu=4"
  - "rediacc.hub.limits.memory=8g"
```

### Basit web uygulaması

Bir web çerçevesi için tek servisli ortam:

```yaml
labels:
  - "rediacc.hub.route.app=3000"
  - "rediacc.hub.image=node:22-alpine"
  - "rediacc.hub.command=cd /workspace && npm install && exec npm run dev -- --host $${SERVICE_IP}"
  - "rediacc.hub.user=1000:1000"
  - "rediacc.hub.mode=ephemeral"
```

## İlgili kılavuzlar

- [**Servisler**](/tr/docs/services) -- Rediaccfile yaşam döngüsü, Compose desenleri
- [**Ağ**](/tr/docs/networking) -- Docker etiketleri, Traefik yönlendirme, TLS sertifikaları
- [**Yedekleme ve geri yükleme**](/tr/docs/backup-restore) -- Çalışma alanı kalıcılığı ve kurtarma
- [**Geliştirme ortamları**](/tr/docs/development-environments) -- Geliştirme ortamları için üretim klonlama
