---
title: "Hub"
description: "Kimlik doğrulamalı, kullanıcı başına Docker daemon'ı, çoklu şablon seçimi, CRIU checkpoint/geri yükleme, denetim günlükleri ve data-root çöp toplama özelliklerine sahip kullanıcı başına konteyner ortamları sağlar."
category: "Guides"
order: 14
language: tr
sourceHash: "6fa16a1c73af497e"
sourceCommit: "b997ae00deb9e814edaf2fc449f4d9e36cfafe81"
---

# Hub

Hub, OAuth kimlik doğrulamasının arkasında kullanıcı başına konteyner ortamları sağlar. Kullanıcılar tek bir URL'yi ziyaret eder, herhangi bir OAuth2 sağlayıcısıyla kimlik doğrular ve kişisel konteynerlerine şeffaf biçimde yönlendirilir. Konteynerler talep üzerine oluşturulur, her kullanıcı kendi izole Docker daemon'ını alır ve boşta kalan oturumlar anında devam ettirme için CRIU checkpoint ile kaydedilir.

Her şey `docker-compose.yml` etiketleri aracılığıyla yapılandırılır. Hub'ın kendisi, deponuzun Compose dosyasındaki `renet hub install` komutuyla oluşturulan bir ana bilgisayar systemd servisi olarak çalışır. Depolar davranışı tanımlar; Hub kimlik doğrulama, yönlendirme, yaşam döngüsü ve kullanıcı başına izolasyonu yönetir.

## Nasıl Çalışır

1. Kullanıcı `code.example.com` adresini ziyaret eder (veya `term.`, `desktop.` ya da yapılandırılmış herhangi bir ön eki).
2. Hub oturum çerezini kontrol eder. Yoksa kullanıcı yapılandırılmış OAuth2 sağlayıcısına (Nextcloud, Keycloak, GitHub vb.) yönlendirilir.
3. Kimlik doğrulamanın ardından Hub kullanıcıyı tanımlar ve konteynerini arar.
4. Konteyner yoksa Hub, ana bilgisayarda söz konusu kullanıcı için özel bir Docker daemon sağlar ve ardından konteynerini başlatır.
5. İstek, loopback ağı üzerinden kullanıcının konteynerine ters proxy ile iletilir.
6. Boşta kalan konteynerler CRIU checkpoint ile kaydedilir ve belleği serbest bırakmak için kullanıcı başına daemon durdurulur. Bir sonraki girişte daemon yeniden başlar ve CRIU konteyner durumunu saniyeler içinde geri yükler.

## Hızlı Başlangıç

Deponuzun `docker-compose.yml` dosyasına Hub'ı servis olarak ekleyin. Servis, Docker konteyneri yerine ana bilgisayar servisi olarak çalışması için `install_as=systemd` olarak işaretlenir (systemd kullanan kullanıcı başına daemon yönetimi için gereklidir).

```yaml
services:
  hub:
    env_file:
      - ./hub/.env
    command:
      - hub
      - start
      - --docker-socket=${DOCKER_SOCKET}
      - --network-id=${REDIACC_NETWORK_ID}
      - --port=7112
      - --base-domain=${HUB_DOMAIN:-example.com}
      - --workspace-dir=${REDIACC_WORKING_DIR}/devbox/workspaces
      - --idle-timeout=30m
      - --checkpoint
    labels:
      - "rediacc.install_as=systemd"

      # Rota eşleştirme: alt alan adı ön eki -> kullanıcı konteynerlerindeki port
      - "rediacc.hub.route.code=8080"
      - "rediacc.hub.route.term=7681"
      - "rediacc.hub.route.desktop=6080"

      # Konteyner şablonu
      - "rediacc.hub.image=ghcr.io/your-org/devcontainer:latest"
      - "rediacc.hub.command=start-desktop.sh & ttyd --writable --port 7681 bash & exec openvscode-server --host __SERVICE_IP__ --port 8080"
      - "rediacc.hub.user=vscode"
      - "rediacc.hub.docker=per-user"

      # Traefik rotaları (dosya sağlayıcı; rediacc-router da bu etiketleri okur)
      - "traefik.http.routers.hub-code.rule=Host(`code.${HUB_DOMAIN:-example.com}`)"
      - "traefik.http.routers.hub-code.entrypoints=websecure"
      - "traefik.http.routers.hub-code.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-code.loadbalancer.server.port=7112"
      - "traefik.http.routers.hub-term.rule=Host(`term.${HUB_DOMAIN:-example.com}`)"
      - "traefik.http.routers.hub-term.entrypoints=websecure"
      - "traefik.http.routers.hub-term.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-term.loadbalancer.server.port=7112"
      - "traefik.http.routers.hub-desktop.rule=Host(`desktop.${HUB_DOMAIN:-example.com}`)"
      - "traefik.http.routers.hub-desktop.entrypoints=websecure"
      - "traefik.http.routers.hub-desktop.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-desktop.loadbalancer.server.port=7112"
```

OAuth2 sağlayıcı kimlik bilgilerinizle `hub/.env` dosyasını oluşturun:

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

Ana bilgisayar systemd birimini yükleyin (bir kez, root gerektirir):

```bash
sudo renet hub install /path/to/docker-compose.yml
```

Bu, `install_as=systemd` servislerini okur ve şunları yazar:

- `/etc/systemd/system/rediacc-hub.service` (birim)
- `/etc/rediacc/hub/hub.labels.yaml` (şablon etiketleri)
- `/opt/rediacc/proxy/traefik/dynamic/rediacc-hub.yaml` (Traefik dosya sağlayıcı rotaları)

Ardından `systemctl daemon-reload && systemctl enable --now rediacc-hub`. Kaldırmak için: `sudo renet hub uninstall /path/to/docker-compose.yml`.

## Install Komutu Başvurusu

| Komut | Amaç |
|---------|---------|
| `sudo renet hub install <compose-file>` | Compose dosyasındaki `install_as=systemd` servislerini ana bilgisayar yapıtlarına çevirmek ve birimi başlatmak. |
| `sudo renet hub uninstall <compose-file>` | Servislerin tüm yapıtlarını durdurmak, devre dışı bırakmak ve kaldırmak. `<workspace>/<user>-docker/` altındaki data-root'lar korunur. |
| `sudo renet hub gc <workspace-dir>` | Terk edilmiş kullanıcı başına data-root'ları temizlemek (varsayılan: etkin daemon olmaksızın 30 günden eski). Bayraklar: `--max-age=30d`, `--dry-run`. |
| `renet hub status` | Çalışan Hub API'si aracılığıyla tüm konteynerlerin JSON durumu. |
| `renet hub stop <username>` | Belirli bir kullanıcının konteynerini durdurmak. |

## Yapılandırma

Tüm Hub yapılandırması Hub servisinin Compose etiketlerinde bulunur. Sırlar (OAuth client_secret, session_secret) etiketlere değil `hub/.env` dosyasına gider.

### Rota Eşleştirme

Alt alan adı ön eklerini kullanıcı konteynerlerindeki portlarla eşleştirin. Hub, her isteği nereye proxy'leyeceğini bilmek için bu etiketleri okur.

| Etiket | Açıklama | Örnek |
|-------|-------------|---------|
| `rediacc.hub.route.{prefix}` | `{prefix}.{domain}` adresini kullanıcının konteynerindeki bu porta eşler | `rediacc.hub.route.code=8080` |

```yaml
labels:
  - "rediacc.hub.route.code=8080"      # code.example.com -> :8080
  - "rediacc.hub.route.term=7681"      # term.example.com -> :7681
  - "rediacc.hub.route.desktop=6080"   # desktop.example.com -> :6080
  - "rediacc.hub.route.jupyter=8888"   # jupyter.example.com -> :8888
```

Her rota ayrıca Hub'ın portuna (7112) işaret eden eşleşen bir Traefik yönlendiricisi gerektirir. Hub, ana bilgisayar adına göre kullanıcı başına yönlendirmeyi dahili olarak yönetir.

### Konteyner Şablonu

Kullanıcı konteynerlerinin nasıl görüneceğini tanımlayın. Hub bu etiketleri okur ve yeni konteyner oluştururken kullanır.

| Etiket | Açıklama | Varsayılan |
|-------|-------------|---------|
| `rediacc.hub.image` | Konteyner imajı | `--container-image` bayrağının değeri |
| `rediacc.hub.command` | Başlatma komutu (bash -c uyumlu) | yok |
| `rediacc.hub.user` | Konteyner kullanıcısı (root olmayan önerilir) | `vscode` |
| `rediacc.hub.workspace` | Konteyner içindeki workspace bağlama noktası | `/workspace` |
| `rediacc.hub.shm_size` | Paylaşılan bellek boyutu (bayt cinsinden) | `1073741824` (1 GB) |
| `rediacc.hub.docker` | Kullanıcı başına özel dockerd sağlamak için `per-user` (şiddetle tavsiye edilir) | `""` |

`command` etiketi, konteynere atanan loopback IP için `${SERVICE_IP}` ve `__SERVICE_IP__` genişletmesini destekler (ikincisi Compose ön genişletmesini önler).

```yaml
labels:
  - "rediacc.hub.image=ghcr.io/my-org/dev-env:latest"
  - "rediacc.hub.command=exec jupyter lab --ip=__SERVICE_IP__ --port=8888 --no-browser"
  - "rediacc.hub.user=vscode"
  - "rediacc.hub.workspace=/workspace"
  - "rediacc.hub.docker=per-user"
```

### Kullanıcı Başına Docker Daemon

`rediacc.hub.docker=per-user` ayarlandığında, her kullanıcı ana bilgisayarda `/var/run/docker.sock` olarak konteynerinin içine bağlanan özel bir `dockerd` örneği alır. Bu şunları sağlar:

- Ayrıcalıklı konteynerler veya Docker-in-Docker olmadan kullanıcı ortamı içinde tam `docker ps`, `docker run`, `docker build`.
- Kullanıcılar arasında tam izolasyon (A kullanıcısı B kullanıcısının konteynerlerini veya imajlarını göremez).
- `<workspace-dir>/<user>-docker/.rediacc/docker/data` konumunda kullanıcı başına BTRFS data-root, oturumlar arasında korunarak önbelleğe alınan imajların boşta kalma checkpoint döngülerinden sağ çıkmasını sağlar.

Daemon'lar 32768'den başlayan özel bir ağ kimliği aralığında tahsis edilir. Her kullanıcının data-root'undaki bir `.networkid` işaretleyici dosyası, geri dönen kullanıcıların aynı daemon'ı bulması için atanan kimliği kaydeder.

### Kaynak Sınırları

Herhangi bir kullanıcının tüm ana bilgisayar kaynaklarını tüketmesini önlemek için kullanıcı başına kaynak sınırları belirleyin. Sınırlar hem kullanıcının konteynerine hem de kullanıcı başına dockerd örneğine uygulanır (systemd `CPUQuota=` / `MemoryMax=` aracılığıyla).

| Etiket | Açıklama | Örnek |
|-------|-------------|---------|
| `rediacc.hub.limits.cpu` | systemd CPUQuota değeri | `200%` (2 çekirdek) |
| `rediacc.hub.limits.memory` | systemd MemoryMax değeri | `8G` |

```yaml
labels:
  - "rediacc.hub.limits.cpu=200%"
  - "rediacc.hub.limits.memory=8G"
```

Daemon'lar `rediacc.slice` systemd dilimine yerleştirilir; böylece dilim düzeyindeki sınırlar miras alınır.

### Çoklu Şablon Desteği

Birden fazla ortam türü sunun. Kullanıcılar `https://code.example.com/_hub/login?template=python` adresini ziyaret ederek girişte bir şablon seçer (seçim OAuth durumu üzerinden aktarılır). Sonraki girişlerde şablon değiştirmek konteyneri yeniden oluşturur.

Şablonları `rediacc.hub.templates.<name>.<field>` etiketleriyle tanımlayın. Düz `rediacc.hub.image` / `rediacc.hub.command` / vb. etiketler, şablon seçmeyen kullanıcılar için örtük "varsayılan" şablonu tanımlamaya devam eder.

```yaml
labels:
  # ?template=... atlandığında varsayılan şablon.
  - "rediacc.hub.template=fulldev"

  # Zengin VS Code + masaüstü + terminal ortamı.
  - "rediacc.hub.templates.fulldev.image=ghcr.io/org/devcontainer:latest"
  - "rediacc.hub.templates.fulldev.command=start-desktop.sh & ttyd --writable --port 7681 bash --login & exec openvscode-server --host __SERVICE_IP__ --port 8080 --without-connection-token"
  - "rediacc.hub.templates.fulldev.user=vscode"

  # Yalnızca VS Code, hafif.
  - "rediacc.hub.templates.lite.image=ghcr.io/org/devcontainer:lite"
  - "rediacc.hub.templates.lite.command=exec openvscode-server --host __SERVICE_IP__ --port 8080"
  - "rediacc.hub.templates.lite.user=vscode"

  # Python'a özgü ortam.
  - "rediacc.hub.templates.python.image=python:3.12-slim"
  - "rediacc.hub.templates.python.command=pip install jupyterlab && exec jupyter lab --ip=__SERVICE_IP__ --port=8888"
  - "rediacc.hub.templates.python.user=1000:1000"
```

### Yaşam Döngüsü Kancaları

Yaşam döngüsü noktalarında kullanıcı konteyneri içinde komutlar çalıştırın. Kancalar konteyner kullanıcısı olarak çalışır (root değil).

| Etiket | Ne Zaman Çalışır | Örnek |
|-------|-------------|---------|
| `rediacc.hub.hook.on_create` | Konteyner oluşturulduktan sonra (ilk giriş) | Depo klonlama, bağımlılık yükleme |
| `rediacc.hub.hook.checkpoint.pre_dump` | Boşta kalan bir oturumun CRIU checkpoint'inden önce | Checkpoint'e alınamayan daemon'ları durdurmak (X server, dbus) |
| `rediacc.hub.hook.checkpoint.post_restore` | CRIU geri yüklemesinden sonra | pre_dump'ta durdurulan daemon'ları yeniden başlatmak |

```yaml
labels:
  - "rediacc.hub.hook.on_create=git clone https://github.com/org/repo /workspace/project"
  - "rediacc.hub.hook.checkpoint.pre_dump=start-desktop.sh stop"
  - "rediacc.hub.hook.checkpoint.post_restore=start-desktop.sh"
```

### Checkpoint / Geri Yükleme

`--checkpoint` ayarlandığında, boşta kalan kullanıcı konteynerleri CRIU ile checkpoint alınır ve belleği serbest bırakmak için kullanıcı başına daemon durdurulur. Bir sonraki girişte daemon yeniden başlar ve CRIU, açık dosyaları, çalışan süreçleri ve terminal oturumlarını koruyarak konteyner durumunu diskten saniyeler içinde geri yükler. Tipik sürdürme süresi, iş yükünden bağımsız olarak birkaç saniyedir.

| Etiket | Açıklama | Varsayılan |
|-------|-------------|---------|
| `rediacc.hub.checkpoint` | Kullanıcı konteynerleri için CRIU checkpoint'i etkinleştir | `false` |

Hub komutuna `--checkpoint` ve sıfır olmayan bir `--idle-timeout` (örneğin `30m`) ekleyin. Checkpoint dizinleri `<workspace-dir>/<user>/.checkpoint/` konumundadır.

Bir kullanıcı için CRIU art arda 3 kez başarısız olursa, o kullanıcı için checkpoint devre dışı bırakılır ve yedek strateji durdurma ve yeniden oluşturma olur.

### Geçici Mod

Varsayılan olarak, kullanıcı çalışma alanları kalıcıdır (yeniden başlatmadan sonra da devam eder). Geçici mod, demolar, eğitim veya CI için kullanışlı olan her girişte temiz bir ortam sağlar.

| Etiket | Açıklama | Varsayılan |
|-------|-------------|---------|
| `rediacc.hub.mode` | `persistent` veya `ephemeral` | `persistent` |

Geçici modda çalışma alanı tmpfs (RAM destekli) kullanır ve konteyner durdurulduğunda otomatik olarak kaldırılır.

### Boşta Kalma Zaman Aşımı

| Bayrak | Açıklama | Varsayılan |
|------|-------------|---------|
| `--idle-timeout=<dur>` | Belirtilen süreden daha uzun boşta kalan konteynerleri durdur/checkpoint al | `0` (devre dışı) |

`0` konteynerlerin sonsuza kadar çalışmasını sağlar. Pratik bir değer `30m`'dir: boşta kalan kullanıcılar yarım saat sonra belleği serbest bırakır ve geri dönen kullanıcılar CRIU aracılığıyla saniyeler içinde devam eder.

### Erişim Kontrolü

| Değişken | Açıklama |
|----------|-------------|
| `HUB_ALLOWED_GROUPS` | Hub'ı kullanmaya izin verilen virgülle ayrılmış gruplar (sağlayıcınız grup taleplerini açığa çıkardığında) |
| `HUB_ADMIN_USERS` | Virgülle ayrılmış yönetici kullanıcı adları. Yöneticiler panoda diğer kullanıcıların konteynerlerini görebilir ve kontrol edebilir. |

## Denetim Günlüğü

Kullanıcı başına daemon'daki her kullanıcı tarafından başlatılan konteyner/imaj olayı (create, start, stop, destroy, kill, pull, push) `/var/log/rediacc/hub/<user>.log` dosyasına satır sınırlı JSON kaydı olarak eklenir:

```json
{"ts":"2026-04-16T05:53:12Z","user":"alice","net_id":32768,"type":"container","action":"start","resource":"abc123...","attrs":{"image":"hello-world:latest","name":"happy_pike"}}
```

Girişler CRIU checkpoint/geri yüklemesinden sağ çıkar (denetim akışı geri yüklemede yeniden silahlanır). Disk kullanımını sınırlamak için `logrotate` kullanın; örnek yapılandırma:

```
/var/log/rediacc/hub/*.log {
  daily
  rotate 30
  compress
  missingok
  notifempty
  copytruncate
}
```

## Panel

Hub, `/_hub/dashboard` adresinde self-servis bir panel içerir. Şunları gösterir:

- Durumlarıyla birlikte tüm çalışan ortamlar
- Seçilen şablon
- Servis bağlantıları (kod, terminal, masaüstü veya başka herhangi bir rotayı tek tıklamayla açmak için)
- Boşta kalma zamanlayıcıları
- Kullanıcı başına disk kullanımı, çalışan konteyner sayısı ve imaj sayısı
- Yöneticiler tüm konteynerleri görür; normal kullanıcılar yalnızca kendi konteynerlerini görür

İstatistikler her 30 saniyede bir örneklenir.

### Data-Root Çöp Toplama

Kullanıcı başına data-root'lar uzun süreli çalışan ana bilgisayarlarda birikir. Terk edilenleri temizlemek için `renet hub gc` zamanlayın. Bir systemd zamanlayıcısı iyi çalışır:

```ini
# /etc/systemd/system/rediacc-hub-gc.service
[Unit]
Description=Rediacc Hub data-root GC

[Service]
Type=oneshot
ExecStart=/usr/lib/rediacc/renet/current/renet hub gc /mnt/rediacc/mounts/<repo-guid>/devbox/workspaces --max-age=30d
```

```ini
# /etc/systemd/system/rediacc-hub-gc.timer
[Unit]
Description=Daily Rediacc Hub GC

[Timer]
OnCalendar=daily
RandomizedDelaySec=1h
Persistent=true

[Install]
WantedBy=timers.target
```

`--dry-run` silmeden adayları günlüğe kaydeder. `.networkid` işaretleyici dosyası `--max-age`'den eski VE kayıtlı daemon artık ana bilgisayarda yapılandırılmamış olduğunda data-root uygundur.

## OAuth Kurulumu

Hub, herhangi bir standart OAuth2 sağlayıcısıyla çalışır. Yapılandırma ortam değişkenleri aracılığıyla yapılır.

| Değişken | Açıklama | Gerekli |
|----------|-------------|----------|
| `HUB_OAUTH_CLIENT_ID` | OAuth2 istemci kimliği | Evet |
| `HUB_OAUTH_CLIENT_SECRET` | OAuth2 istemci sırrı | Evet |
| `HUB_OAUTH_AUTHORIZE_URL` | Sağlayıcının yetkilendirme uç noktası | Evet |
| `HUB_OAUTH_TOKEN_URL` | Sağlayıcının token uç noktası | Evet |
| `HUB_OAUTH_USERINFO_URL` | Sağlayıcının userinfo uç noktası | Evet |
| `HUB_OAUTH_USERINFO_PATH` | JSON yanıtından kullanıcı adını çıkarmak için nokta yolu | Evet |
| `HUB_OAUTH_REDIRECT_URI` | Geri arama URL'sini geçersiz kıl (boşsa otomatik hesaplanır) | Hayır |
| `HUB_OAUTH_SCOPES` | Ek kapsamlar (boşlukla ayrılmış) | Hayır |
| `HUB_SESSION_SECRET` | Çerez imzalama için 32+ bayt onaltılık dize | Önerilir |

### Sağlayıcı Örnekleri

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

`HUB_OAUTH_USERINFO_PATH`, JSON yanıtına giden noktayla ayrılmış bir yoldur. Nextcloud'un `{"ocs":{"data":{"id":"alice"}}}` gibi iç içe nesneler için `ocs.data.id` kullanın.

## Örnekler

### Geliştirme Ortamı (VS Code + Terminal + Masaüstü)

OpenVSCode Server, web terminali (ttyd) ve noVNC masaüstü içeren tam geliştirme ortamı. Kullanıcılar kendi Docker daemon'larını içeride alır.

```yaml
services:
  hub:
    env_file:
      - ./hub/.env
    command:
      - hub
      - start
      - --docker-socket=${DOCKER_SOCKET}
      - --network-id=${REDIACC_NETWORK_ID}
      - --port=7112
      - --base-domain=${HUB_DOMAIN}
      - --workspace-dir=${REDIACC_WORKING_DIR}/devbox/workspaces
      - --idle-timeout=30m
      - --checkpoint
    labels:
      - "rediacc.install_as=systemd"
      - "rediacc.hub.route.code=8080"
      - "rediacc.hub.route.term=7681"
      - "rediacc.hub.route.desktop=6080"
      - "rediacc.hub.image=ghcr.io/your-org/devcontainer:latest"
      - "rediacc.hub.command=start-desktop.sh & ttyd --writable --port 7681 bash --login & exec openvscode-server --host __SERVICE_IP__ --port 8080 --without-connection-token"
      - "rediacc.hub.user=vscode"
      - "rediacc.hub.docker=per-user"
      - "rediacc.hub.limits.cpu=200%"
      - "rediacc.hub.limits.memory=8G"
      - "rediacc.hub.checkpoint=true"
      - "rediacc.hub.hook.checkpoint.pre_dump=start-desktop.sh stop"
      - "rediacc.hub.hook.checkpoint.post_restore=start-desktop.sh"
      # ... Her ön ek için Traefik yönlendiricileri ...
```

### Jupyter Notebook Ortamı

JupyterLab ile veri bilimi ortamı:

```yaml
labels:
  - "rediacc.install_as=systemd"
  - "rediacc.hub.route.notebook=8888"
  - "rediacc.hub.image=jupyter/datascience-notebook:latest"
  - "rediacc.hub.command=exec jupyter lab --ip=__SERVICE_IP__ --port=8888 --no-browser --NotebookApp.token='' --NotebookApp.password=''"
  - "rediacc.hub.user=1000:100"
  - "rediacc.hub.workspace=/home/jovyan/work"
  - "rediacc.hub.limits.cpu=400%"
  - "rediacc.hub.limits.memory=16G"
```

### Basit Web Uygulaması (Geçici)

Her girişte sıfırdan başlayan tek servisli ortam:

```yaml
labels:
  - "rediacc.install_as=systemd"
  - "rediacc.hub.route.app=3000"
  - "rediacc.hub.image=node:22-alpine"
  - "rediacc.hub.command=cd /workspace && npm install && exec npm run dev -- --host __SERVICE_IP__"
  - "rediacc.hub.user=1000:1000"
  - "rediacc.hub.mode=ephemeral"
```

## İlgili Kılavuzlar

- [**Servisler**](/tr/docs/services) -- Rediaccfile yaşam döngüsü, Compose desenleri
- [**Ağ**](/tr/docs/networking) -- Docker etiketleri, Traefik yönlendirme, TLS sertifikaları
- [**Yedekleme ve Geri Yükleme**](/tr/docs/backup-restore) -- Çalışma alanı kalıcılığı ve kurtarma
- [**Geliştirme Ortamları**](/tr/docs/development-environments) -- Geliştirme ortamları için üretim klonlama
