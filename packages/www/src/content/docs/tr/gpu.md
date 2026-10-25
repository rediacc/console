---
title: "GPU"
description: "Bir repoya CDI aygıt izniyle GPU erişimi vermek: makinenin GPU'larını listelemek, aygıtları repo başına vermek ve geri almak, bir kartı özel olarak ayırmak ve WSL üzerinde çalışmak."
category: "Guides"
tags:
  - containers
  - operations
subcategory: workloads
order: 7
language: tr
sourceHash: "5a113ad69c52c63d"
---

# GPU

Bir repo GPU'ya yalnızca bir **aygıt izni** üzerinden ulaşır. Makine sahip olduğu GPU'ları adlandırılmış aygıtlar olarak yayımlar, operatör de bir repoya kullanabileceği adları verir. İzni olmayan repo GPU alamaz ve bir [fork](/tr/docs/repositories), ana reposunun izni olsa bile izinsiz başlar.

Adlar, Docker 25 ve sonrasının bir aygıtı ve bir konteynerin onu kullanmak için gereken her şeyi tanımlamakta kullandığı Container Device Interface (CDI) standardını izler. CDI adı `<vendor>/<class>=<device>` biçimindedir, örneğin `nvidia.com/gpu=all`.

## CDI izni nedir

Her repo, bir konteynere donanım bağlamanın her yolunu reddeden bir API geçidinin arkasında kendi Docker daemon'ını çalıştırır, dolayısıyla GPU'ya `docker run` bayraklarıyla ulaşılamaz. İzin tek kapıdır. Bir repo için tam bir CDI adı kaydeder ve geçit bundan sonra yalnızca o aygıtı adlandıran konteyner isteğini kabul eder.

- İzinler bir sonraki Docker isteğinden itibaren geçerlidir, daemon'ın yeniden başlatılması gerekmez.
- Bir izin tam olarak bir aygıtı adlandırır. `nvidia.com/gpu=all` vermek `nvidia.com/gpu=all` adını kabul eder, `nvidia.com/gpu=0` adını kabul etmez. Bir repoya tek kart vermek için o kartın adı verilir.
- İzin yazılırken makinedeki aygıt tanımlarıyla karşılaştırılır, bu yüzden yanlış yazılmış bir ad kaydedilmek yerine reddedilir.
- İzin, yapıldığı repoya aittir. Fork'ların ve kopyaların kendi izni gerekir.

## Makineyi hazırlama

`rdc machine setup <machine>` makinedeki GPU'ları algılar ve sonucu `/etc/rediacc/gpu/inventory.json` dosyasına kaydeder. Bir NVIDIA GPU varsa kurulum ayrıca NVIDIA Container Toolkit'i yükler ve CDI tanımını `/etc/cdi/nvidia.yaml` konumunda üretir. GPU'su olmayan makine de boş listelerle bir envanter dosyası alır.

Toolkit kurulumunu `renet setup` komutunun `--install-nvidia-toolkit` seçeneği belirler:

| Değer | Davranış |
|---|---|
| `auto` | Bir NVIDIA GPU varsa toolkit yüklenir. Varsayılan budur. |
| `true` | Toolkit her durumda yüklenir. |
| `false` | Toolkit atlanır ve NVIDIA tanımı üretilmez. |

Kurulum hiçbir konteyner çalışma zamanını yapılandırmaz, çünkü yalnızca `runc` kabul edilir. Toolkit yalnızca tanım için kullanılır ve tanım, sürücü değişikliklerini izlemesi için her kurulumda yeniden üretilir.

İki aygıt türü doğrudan Rediacc'ten gelir ve üreticinin kullanıcı alanı bileşenlerine ihtiyaç duymaz, çünkü yalnızca aygıt düğümlerini eşler:

| Tür | Aygıtlar | Kaynak |
|---|---|---|
| `rediacc.io/dri` | Her render düğümü için bir tane, örneğin `rediacc.io/dri=renderD128` | `/dev/dri/renderD<N>` |
| `rediacc.io/amd` | Bir AMD kartı için `gpu<N>` ve `all` | `/dev/kfd` artı kartın render düğümü |

NVIDIA aygıtları toolkit'in tanımından gelir: `nvidia.com/gpu=all` ve kart başına bir ad. AMD hesaplaması için konteyner imajında ROCm kullanıcı alanı gerekir, çünkü kurulum ROCm yüklemez.

## GPU'ları listeleme

```bash
rdc machine gpu list <machine>
rdc machine gpu list <machine> -o json
```

Tablo her GPU'yu adı, sürücü sürümü ve belleğiyle, platformu (yerel veya WSL), envanterin yaşını ve verilebilecek her CDI aygıt adını gösterir. `-o json`, envanteri makinede kayıtlı olduğu hâliyle yazdırır. Geçerli izinler makineden canlı okunur.

## Verme ve geri alma

```bash
rdc repo gpu grant <repo-ref> --device nvidia.com/gpu=all
rdc repo gpu revoke <repo-ref> --device nvidia.com/gpu=all
```

`<repo-ref>` bir repo adıdır, isteğe bağlı olarak makineyle birlikte, örneğin `gpu-a@wsl-gpu`. Her iki komut da farklı `--device` değerleriyle tekrarlanabilir. İzinden sonra o repodaki bir konteyner aygıtla başlar:

```bash
docker run --rm --device nvidia.com/gpu=all ubuntu:24.04 nvidia-smi -L
```

Aynı konteyner izni olmayan bir repoda reddedilir ve ileti eksik izni adlandırır.

## Özel izinler

```bash
rdc repo gpu grant <repo-ref> --device nvidia.com/gpu=0 --exclusive
```

Özel izin, bir aygıtı tek bir repoya ayırır. Aynı adı başka bir repo tutuyorsa reddedilir ve izin sürdüğü sürece o adın başka bir repoya verilmesi reddedilir. Denetim izin verilirken, makinedeki tüm izinleri kapsayan bir kilit altında yapılır.

Özel izin bir rezervasyondur, zamanlayıcı değildir. İzin verilen aynı repodaki iki konteyner kartı yine paylaşır.

## Reddedilen yazımlar

GPU'ya giden diğer her yol, izin olsun olmasın reddedilmeye devam eder. CDI biçimi bunların her birinin yerini alır.

| Reddedilen | Bunun yerine |
|---|---|
| `docker run --gpus all` | `docker run --device nvidia.com/gpu=all` |
| Compose'da `runtime: nvidia` | `devices: [nvidia.com/gpu=all]` |
| Compose'da `deploy.resources.reservations.devices` | `devices: [nvidia.com/gpu=all]` |
| Compose'da `gpus: all` | `devices: [nvidia.com/gpu=all]` |
| Ham `/dev/dri` veya `/dev/kfd` aygıtları ya da `/dev` altında bir bind | `rediacc.io/dri=renderD128` veya `rediacc.io/amd=gpu0` |
| Aygıt cgroup kuralları | Aygıt için bir CDI izni |

İzin verilmiş bir aygıtı kullanan Compose servisi şöyle görünür:

```yaml
services:
  inference:
    image: ubuntu:24.04
    command: nvidia-smi -L
    devices:
      - nvidia.com/gpu=all
```

`group_add` ile `video` veya `render` gibi bir grup eklemek kabul edilir ama hiçbir şey vermez, çünkü grup, repoya verilmemiş bir aygıta erişim açmaz.

## WSL

WSL2'de Windows sürücüsü GPU'yu `/dev/dxg` ve `/usr/lib/wsl/lib` altındaki kitaplıklar üzerinden sağlar. Makine platformunu `wsl` olarak bildirir ve kurulum NVIDIA tanımını WSL biçiminde üretir:

```bash
nvidia-ctk cdi generate --mode=wsl --output=/etc/cdi/nvidia.yaml
```

Sürücü Windows tarafında durur, bu yüzden oradaki bir güncelleme `rdc machine setup` bir sonraki çalıştığında alınır. Verme, listeleme ve geri alma komutları yerel bir makinedekiyle aynı çalışır.

## Yerel NVIDIA

Yerel bir NVIDIA makinesinde toolkit'in `nvidia-cdi-refresh` servisi tanımı kurulumdan, sürücü değişikliğinden ve açılıştan sonra yeniden üretir. Kurulum onu, bir reponun Docker daemon'ının okuduğu tek tanım dizini olan `/etc/cdi/nvidia.yaml` konumuna yönlendirir. `nvidia-persistenced` çalışıyorsa soketi repo daemon'larına görünür kılınır, çünkü tanım onu konteynerlere bağlar.
