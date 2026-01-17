---
title: Web Uygulaması
description: Rediacc ile web uygulaması mimarisi ve dağıtımını anlama
category: Core Concepts
order: 1
language: tr
---

# Rediacc Platformu Kullanım Kılavuzu

## Genel Bakış

**Rediacc**, yapay zeka destekli yedekleme hizmetleri sunan bir bulut platformudur.

Bu kılavuz, [https://www.rediacc.com/](https://www.rediacc.com/) adresindeki web arayüzünün temel kullanımını anlatır.

### Bu Kılavuzun Amacı

- Yeni kullanıcıların platforma hızlı şekilde adapte olmasını sağlamak
- Temel işlevleri (kaynak yönetimi, yedekleme) adım adım açıklamak

---

## 1. Hesap Oluşturma ve Giriş

### 1.1 Kayıt Olma

Rediacc platformunu kullanmaya başlamak için öncelikle bir hesap oluşturmanız gerekmektedir.

![Rediacc giriş sayfası - her zaman ayakta kalan altyapı](/assets/images/UserGuideEng/01_login.png)
*(Resim 1: Ana giriş sayfası, Rediacc platformunun başlıca özelliklerini tanıtan açılış ekranı)*

1. Tarayıcıdan [https://www.rediacc.com/](https://www.rediacc.com/) adresine gidin.
2. Sayfanın sağ üst köşesinde **Giriş Yap** düğmesini tıklayın.
3. Ücretsiz başlamak için **Başla** düğmesini, demo için **Demo Rezervasyonu** seçeneğini kullanın.

> **İpucu**: Hiçbir kredi kartı gerekmeden ücretsiz hesap oluşturabilirsiniz. 10 CPU çekirdeği ve sınırsız takımlar dahildir.

![Rediacc Giriş Yap formu - e-posta ve parola alanları](/assets/images/UserGuideEng/02_register.png)
*(Resim 2: Mevcut kullanıcılar için Giriş Yap ekranı)*

4. Hesap yoksa **Kayıt** bağlantısını tıklayarak yeni hesap oluşturun.

5. Açılan formda aşağıdaki bilgileri doldurun:
   - **Şirket Adı**: Kuruluş adınızı girin
   - **E-posta**: Geçerli bir e-posta adresi girin
   - **Parola**: En az 8 karakterli parola oluşturun
   - **Parola Tekrarı**: Aynı parolayı yeniden girin

![Hesap Oluştur modal - kayıt, doğrulama ve tamamlanma adımları](/assets/images/UserGuideEng/03_create_account.png)
*(Resim 3: Yeni kullanıcı kaydı için adım adım form - Kayıt > Doğrulama > Tamamlanma)*

6. Kullanım koşulları ve gizlilik politikasını kabul etmek için kutucuğu işaretleyin.
7. **Hesap Oluştur** düğmesine tıklayın.

> **İpucu**: Parola en az 8 karakter olmalı ve güçlü olması önerilir. Tüm alanlar zorunludur.

8. E-postanıza gelen 6 haneli doğrulama kodunu kutulara sırasıyla girin.
9. **Hesabı Doğrula** düğmesine tıklayın.

![Doğrulama kodu girişi - 6 haneli aktivasyon kodu](/assets/images/UserGuideEng/04_verification_code.png)
*(Resim 4: Yöneticiye gönderilen aktivasyon kodunun girildiği pencere)*

> **İpucu**: Doğrulama kodu limitli süreli geçerlidir. Kodun gelmemesi durumunda spam klasörünü kontrol edin.

---

### 1.2 Giriş Yapma

Hesabınız oluşturulduktan sonra platforma giriş yapabilirsiniz.

1. **E-posta** alanını doldurun (kırmızı uyarı görünüyorsa gereklidir).
2. **Parola** alanını doldurun.
3. **Giriş Yap** düğmesine tıklayın.

![Giriş Yap formu - hata uyarısı ile zorunlu alanlar](/assets/images/UserGuideEng/05_sign_in.png)
*(Resim 5: Giriş formu - hata mesajları kırmızı sınır ile işaretlenir)*

> **İpucu**: Hata mesajı "Bu alan gereklidir" ise boş alanları doldurun. Unutulan şifre için yöneticiyle iletişime geçin.

4. Başarılı girişten sonra **Dashboard** ekranına yönlendirilirsiniz.

![Rediacc kontrol paneli - makine listesi ve sidebar menüsü](/assets/images/UserGuideEng/06_dashboard.png)
*(Resim 6: Başarılı giriş sonrası ana dashboard - Sol sidebar'da Organizasyon, Makineler ve Ayarlar menüleri)*

> **İpucu**: Dashboard otomatik yenilenir. Taze bilgiler için sayfayı F5 ile yenileyebilirsiniz.

---

## 2. Arayüz Tanıtımı

Giriş yaptıktan sonra karşınıza çıkan ekran temel olarak şu bölümlerden oluşur:

- **Organizasyon**: Kullanıcılar, takımlar ve erişim kontrolü
- **Makineler**: Sunucu ve depo yönetimi
- **Ayarlar**: Profil ve sistem ayarları
- **Depolama**: Depolama alanları yönetimi
- **Kimlik Bilgileri**: Erişim kimlik bilgileri
- **Kuyruk**: İş kuyruğu yönetimi
- **Denetim**: Sistem denetim kayıtları

---

## 2.1 Organizasyon - Kullanıcılar

Kullanıcı yönetimi, organizasyonunuzdaki kişilerin platforma erişimini kontrol etmenizi sağlar.

### 2.1.1 Kullanıcı Ekleme

1. Sol sidebar'da **Organizasyon** > **Kullanıcılar** seçeneğini tıklayın.
2. Tüm kullanıcıların listesini tablo formatında görüntüleyin.
3. Her kullanıcının yanında e-posta, durum (Aktif/Pasif), izin grubu ve son aktivite zamanı yer alır.

![Kullanıcılar yönetimi sayfası - aktif kullanıcılar listesi](/assets/images/UserGuideEng/07_users.png)
*(Resim 7: Organizasyon altında Kullanıcılar bölümü - tüm kullanıcıların bilgileri görüntülenir)*

4. Sağ üst köşedeki **"+"** simgesine tıklayın.
5. **Kullanıcı Oluştur** düğmesine tıklayın ve açılan formu doldurun:
   - **E-posta**: Kullanıcının e-posta adresini girin
   - **Parola**: Geçici bir parola girin

![Kullanıcı oluşturma modal - e-posta ve parola alanları](/assets/images/UserGuideEng/08_user_add.png)
*(Resim 8: Yeni kullanıcı eklemek için modal pencere - basit ve hızlı kullanıcı oluşturma formu)*

6. **Oluştur** düğmesine tıklayın.

> **İpucu**: Oluşturulan kullanıcıya giriş bilgileri güvenli şekilde iletilmelidir. İlk girişinde parola değiştirmesi önerilir.

![Kullanıcı listesi - üç kullanıcı ile tam tablo görünümü](/assets/images/UserGuideEng/09_user_list.png)
*(Resim 9: Kullanıcılar yönetimi sayfasında aktif ve pasif kullanıcıların tamamı)*

> **İpucu**: Sayfa otomatik 20 kayıt gösterir. Daha fazla kaydı görmek için sayfalama kullanın.

### 2.1.2 Kullanıcı İzinleri Atama

Kullanıcılara belirli izin grupları atayarak erişim yetkilerini yönetebilirsiniz.

1. **Organizasyon** > **Kullanıcılar** sekmesinden bir kullanıcı seçin.
2. İşlemler sütunundaki kalkan simgesine tıklayın (**İzinler**).

![İzin yönetimi - kalkan, çark ve sil simgeleri](/assets/images/UserGuideEng/10_users_permissions.png)
*(Resim 10: Kullanıcı işlemlerinin simge gösterimi - her simge farklı bir işlemi temsil eder)*

3. Açılan formdan bir **İzin Grubu** seçin.
4. Kullanıcının yanında grubun kaç kullanıcı ve izin içerdiği gösterilir.
5. **İzin Ata** düğmesine tıklayarak değişiklikleri kaydedin.

![İzin atama modal - Yöneticiler grubu](/assets/images/UserGuideEng/11_user_permissions_form.png)
*(Resim 11: Seçili kullanıcıya izin grubu atamak için modal - açılır listeyle mevcut gruplar)*

> **İpucu**: Bazı izin grupları sistem tarafından sabitlenmiştir ve değiştirilemez.

### 2.1.3 Kullanıcı Aktivasyonu

Devre dışı bırakılmış kullanıcıları tekrar aktif hale getirebilirsiniz.

1. **Kullanıcılar** listesinden pasif (Inactive) durumundaki kullanıcıyı bulun.
2. İşlemler sütunundaki kırmızı simgeyi tıklayın.

![Kullanıcı etkinleştirme - "Etkinleştir" tooltip görünümlü](/assets/images/UserGuideEng/12_users_activation.png)
*(Resim 12: Pasif kullanıcıyı etkinleştirme işlemi)*

3. Onay penceresinde **Evet** düğmesine tıklayın.

![Etkinleştir onay modal](/assets/images/UserGuideEng/13_users_activation_confirm.png)
*(Resim 13: Kullanıcı etkinleştirme işleminin onaylanması için modal pencere)*

> **İpucu**: Bu işlem geri alınabilir. Kullanıcıyı pasif hale getirmek için aynı şekilde işlem yapabilirsiniz.

### 2.1.4 Kullanıcı Takibi (Trace)

Kullanıcı aktivitelerini izlemek için takip özelliğini kullanabilirsiniz.

1. Bir kullanıcı seçin ve işlemler sütunundaki çark simgesini tıklayın.
2. **Takip** seçeneğini tıklayarak kullanıcının aktivite geçmişini açın.

![Kullanıcı takip (Trace) - "Takip" tooltip ile işlem düğmesi](/assets/images/UserGuideEng/14_users_trace.png)
*(Resim 14: Kullanıcı aktivitelerini takip etme seçeneği)*

3. Açılan ekranda kullanıcının geçmiş aktiviteleri listelenir.
4. En üstte istatistikler görüntülenir: Toplam Kayıt, Görülen Kayıt, Son Aktivite.
5. **Dışa Aktar** düğmesini tıklayın ve format seçin: **CSV** veya **JSON**.

![Denetim tarihi (Audit History) - Dışa Aktar seçenekleri](/assets/images/UserGuideEng/15_user_trace_export.png)
*(Resim 15: Kullanıcının tam aktivite geçmişi - istatistikler, detaylar ve Dışa Aktar seçenekleri)*

> **İpucu**: Denetim verilerini düzenli olarak dışa aktararak güvenlik ve uyum kayıtlarını saklayın. CSV format Excel'de açılabilir.

---

## 2.2 Organizasyon - Takımlar

Takımlar, kullanıcıları gruplandırarak kaynaklara toplu erişim sağlamanıza olanak tanır.

### 2.2.1 Takım Oluşturma

1. **Organizasyon** > **Takımlar** sekmesine gidin.
2. **"+"** düğmesine tıklayın.
3. **Takım Adı** alanına takımınızın adını girin.
4. **Kasa Yapılandırması** bölümünde **SSH Özel Anahtarı** ve **SSH Genel Anahtarı** alanlarını doldurun.

![Yeni takım oluşturma formu - takım adı ve SSH anahtarları](/assets/images/UserGuideEng/16_teams_create.png)
*(Resim 16: "Private Team" içinde yeni bir takım oluşturma)*

5. **Oluştur** düğmesine tıklayarak takımı kaydedin.

> **İpucu**: SSH anahtarları Bridge SSH kimlik doğrulaması için gereklidir. Eksik anahtar uyarısı alırsanız, her iki anahtarı da sağlayın.

### 2.2.2 Takım Düzenleme

1. Takımlar listesinden düzenlemek istediğiniz takımın yanındaki kalem simgesine tıklayın.
2. **Takım Adı** alanında takımın adını gerekirse değiştirin.
3. **Kasa Yapılandırması** bölümünde SSH anahtarlarını güncelleyin.
4. **Kaydet** düğmesine tıklayarak değişiklikleri uygulayın.

![Takım düzenleme formu - mavi bilgi mesajı](/assets/images/UserGuideEng/17_teams_edit_form.png)
*(Resim 17: Mevcut bir takımın bilgilerini düzenleme)*

> **İpucu**: Takım yapılandırması organizasyonel yapı için kullanılır. Değişiklikler tüm takım üyeleri için etkili olur.

### 2.2.3 Takım Üyeleri Yönetimi

1. Bir takım seçin ve kullanıcı simgesine tıklayın.
2. **Mevcut Üyeler** sekmesinde takıma zaten atanmış üyeleri görüntüleyin.
3. **Üye Ekle** sekmesine geçin.
4. E-posta adresi girin veya açılır listeden bir kullanıcı seçin.
5. **"+"** düğmesine tıklayarak üyeyi takıma ekleyin.

![Takım üyelerini yönetme formu - "Mevcut Üyeler" ve "Üye Ekle" sekmeleri](/assets/images/UserGuideEng/18_teams_members_form.png)
*(Resim 18: Takım üyelerini yönetme paneli)*

> **İpucu**: Aynı üyeyi birden fazla takıma atayabilirsiniz.

### 2.2.4 Takım Takibi

1. Takip etmek istediğiniz takımı seçin.
2. Saat/geçmiş simgesine tıklayın.
3. **Denetim Geçmişi** modalında Toplam Kayıtlar, Görülen Kayıtlar ve Son Aktivite sayılarını inceleyin.
4. **Dışa Aktar** düğmesine tıklayarak CSV veya JSON formatında dışa aktarın.

![Denetim geçmişi modal - DataBassTeam takımı](/assets/images/UserGuideEng/19_teams_trace.png)
*(Resim 19: Takım denetim geçmişini görüntüleme)*

> **İpucu**: Denetim geçmişi uyum ve güvenlik kontrolü için önemlidir.

### 2.2.5 Takım Silme

1. Silmek istediğiniz takımın yanındaki çöp kutusu (kırmızı) simgesine tıklayın.
2. Onay iletişim kutusunda takım adının doğru olduğunu kontrol edin.
3. **Evet** düğmesine tıklayın.

![Takım silme onay iletişim kutusu](/assets/images/UserGuideEng/20_teams_delete.png)
*(Resim 20: Takım silme işlemi onayı)*

> **Dikkat**: Takım silme işlemi geri alınamaz. Silmeden önce takımda önemli veri olup olmadığını kontrol edin.

---

## 2.3 Organizasyon - Erişim Kontrolü

Erişim kontrolü, izin grupları oluşturarak kullanıcı yetkilerini merkezi olarak yönetmenizi sağlar.

### 2.3.1 İzin Grubu Oluşturma

1. **Organizasyon** > **Erişim Kontrolü** sekmesine gidin.
2. **"+"** düğmesini tıklayın.
3. **Grup adı girin** alanına anlamlı bir ad yazın.
4. **Tamam** düğmesine tıklayarak grubu oluşturun.

![İzin grubu oluşturma formu](/assets/images/UserGuideEng/21_create_access.png)
*(Resim 21: Yeni bir İzin Grubu oluşturma)*

> **İpucu**: İzin grupları, benzer izinlere sahip kullanıcıları organize etmek için kullanılır. Grup adlarını açıklayıcı tutun (örn: "Admin", "Okuma Yalnız", "Depo Yöneticisi").

### 2.3.2 İzin Yönetimi

1. Bir İzin Grubunu seçerek **İzinleri Yönet** seçeneğine tıklayın.
2. **Mevcut İzinler** sekmesinde grubun erişim yetkilerini görüntüleyin.
3. Her işlemin yanındaki kırmızı **Sil** düğmesine tıklayarak bir izni geri alabilirsiniz.
4. **İzin Ekle** sekmesine tıklayarak gruba yeni izinler ekleyin.

![İzin yönetimi paneli - atanmış izinler listesi](/assets/images/UserGuideEng/22_access_permission.png)
*(Resim 22: İzin Grubu için İzinleri Yönetme)*

> **İpucu**: İzinleri en az yetki ilkesine göre verin. Gereksiz izinleri düzenli olarak gözden geçirin ve kaldırın.

---

## 2.4 Makineler

Makineler bölümü, sunucularınızı ve depo kaynaklarınızı yönetmenizi sağlar.

### 2.4.1 Makine Ekleme

1. Sol menüden **Makineler** sekmesine gidin.
2. Sağ üst köşedeki **Makine Ekle** düğmesine tıklayın.

![Makineler sayfası - "Makine Ekle" düğmesi](/assets/images/UserGuideEng/23_machines_add.png)
*(Resim 23: Makineler yönetimi ana sayfası)*

3. Açılan formu doldurun:
   - **Makine Adı**: Benzersiz bir ad girin (ör: "sunucu-01")
   - **IP Adresi**: Makine IP adresini girin (ör: 192.168.111.11)
   - **Datastore Yolu**: Depolama dizinini belirtin (ör: /mnt/rediacc)
   - **Kullanıcı Adı**: SSH kullanıcı adını girin
   - **SSH Port**: Port numarasını girin (varsayılan: 22)
   - **SSH Parolası**: Parolayı girin (isteğe bağlı)

![Makine ekleme formu - tüm alanlar](/assets/images/UserGuideEng/24_machine_create.png)
*(Resim 24: Yeni makine ekleme formu - makine adı, ağ ayarları, SSH kimlik bilgileri)*

4. **Bağlantıyı Test Et** düğmesine tıklayarak bağlantıyı doğrulayın.
5. Test başarılı olduktan sonra **Oluştur** düğmesine tıklayın.

> **İpucu**: "Otomatik olarak kurulumu makine oluşturduktan sonra başlat" seçeneği işaretlenirse, makine ek kurulum adımlarını otomatik gerçekleştirir.

![Makine oluşturma tamamlandı - görev takip penceresi](/assets/images/UserGuideEng/25_machine_create_complete.png)
*(Resim 25: Makine başarıyla oluşturulduktan sonra görev takip penceresi)*

6. Aşamaları izleyin: **Atandı** → **İşleniyor** → **Tamamlandı**
7. **Kapat** düğmesine tıklayarak işlemi sonlandırın.

> **İpucu**: "Yenile" düğmesine tıklayarak manuel olarak en son durumu kontrol edebilirsiniz.

### 2.4.2 Bağlantı Testi

Mevcut makinelerin bağlantı durumunu kontrol edebilirsiniz.

1. **Bağlantı Testi** düğmesine tıklayın.

![Bağlantı Testi düğmesi](/assets/images/UserGuideEng/26_connectivity_test_button.png)
*(Resim 26: Makine işlem araç çubuğunda Bağlantı Testi düğmesi)*

2. Test edilecek makinelerin listelendiğini görün.
3. **Test Et** düğmesine tıklayın.
4. Başarılı sonuçlar yeşil renkte, başarısızlıklar kırmızı renkte gösterilir.

![Bağlantı testi formu - makine listesi](/assets/images/UserGuideEng/27_connectivity_test_form.png)
*(Resim 27: Bağlantı testi formu - seçili makineler için ping fonksiyonu)*

> **İpucu**: Eğer test başarısız olursa, makine IP adresini ve SSH ayarlarını kontrol edin.

### 2.4.3 Makine Listesini Yenileme

Makine listesini güncellemek için **Yenile** düğmesine tıklayın.

![Yenile düğmesi](/assets/images/UserGuideEng/28_refresh.png)
*(Resim 28: Makine işlem araç çubuğundaki Yenile düğmesi)*

### 2.4.4 Makine Detayları

1. Detaylarını görmek istediğiniz makineyi seçin.
2. Göz simgesi düğmesine (**Detayları Görüntüle**) tıklayın.

![Detayları Görüntüle düğmesi](/assets/images/UserGuideEng/29_view_details_button.png)
*(Resim 29: Makine işlem sütununda göz simgesi)*

3. Sağ tarafta makine detayları paneli açılır:
   - **Hostname**: Makinenin adı
   - **Uptime**: Çalışma süresi
   - **Operating System**: İşletim sistemi ve sürümü
   - **Kernel**: Kernel sürümü
   - **CPU**: İşlemci bilgileri
   - **System Time**: Sistem saati

![Makine detay paneli - sistem bilgileri](/assets/images/UserGuideEng/30_machine_view_details.png)
*(Resim 30: Makine detay paneli - hostname, uptime, OS, kernel, CPU bilgileri)*

> **İpucu**: İşletim sistemi uyumluluğunu ve kaynak yeterliliğini kontrol etmek için bu bilgileri düzenli olarak inceleyin.

### 2.4.5 Makine Düzenleme

1. Düzenlemek istediğiniz makineyi seçin.
2. Kalem simgesi düğmesine (**Düzenle**) tıklayın.

![Düzenle düğmesi](/assets/images/UserGuideEng/31_edit_button.png)
*(Resim 31: Makine işlem sütununda kalem simgesi)*

3. Gerekli değişiklikleri yapın.
4. **Bağlantıyı Test Et** düğmesine tıklayın.
5. Bağlantı başarılı olunca **Kaydet** düğmesine tıklayın.

![Makine düzenleme formu](/assets/images/UserGuideEng/32_edit_form.png)
*(Resim 32: Makine düzenleme formu - makine adı, bölge ve kasa yapılandırması)*

> **İpucu**: Kritik ayarları değiştirdikten sonra "Bağlantıyı Test Et" her zaman çalıştırın.

### 2.4.6 Makine Takibi

1. Makineyi seçin ve saat simgesi düğmesine (**Takip**) tıklayın.

![Takip düğmesi](/assets/images/UserGuideEng/33_trace_button.png)
*(Resim 33: Makine işlem sütununda saat simgesi)*

2. Denetim geçmişi penceresinde işlemleri inceleyin:
   - **Action (İşlem)**: Yapılan işlem türü
   - **Details (Detaylar)**: Değişen alanlar
   - **Performed By (Yapan)**: İşlemi yapan kullanıcı
   - **Timestamp (Zaman)**: Tarih ve saat

![Makine denetim geçmişi penceresi](/assets/images/UserGuideEng/34_trace_list.png)
*(Resim 34: Denetim geçmişi - tüm değişikliklerin listesi)*

> **İpucu**: Değişiklikleri zaman sırasına göre görüntülemek için Timestamp sütununa tıklayın.

### 2.4.7 Makine Silme

1. Silmek istediğiniz makineyi seçin.
2. Çöp kutusu simgesi düğmesine (**Sil**) tıklayın.

![Sil düğmesi](/assets/images/UserGuideEng/35_delete_button.png)
*(Resim 35: Makine işlem sütununda çöp kutusu simgesi)*

3. Onay penceresinde **Sil** düğmesine tıklayın.

![Makine silme onay penceresi](/assets/images/UserGuideEng/36_delete_form.png)
*(Resim 36: "Makineyi silmek istediğinize emin misiniz?" onay penceresi)*

> **Dikkat**: Makine silindiğinde, üzerindeki tüm depo tanımlamaları da kaldırılır. Bu işlem geri alınamaz.

### 2.4.8 Uzaktan İşlemler

Makineler üzerinde uzaktan çeşitli işlemler gerçekleştirebilirsiniz.

1. Makineyi seçin ve **Uzak** düğmesine tıklayın.
2. Açılır menüde seçenekleri görün:
   - **Sunucuda Çalıştır**: Makinede fonksiyon çalıştırma
   - **Bağlantıyı Test Et**: Makineye ping gönderme

![Uzak menüsü - Sunucuda Çalıştır ve Bağlantıyı Test Et](/assets/images/UserGuideEng/37_remote_button.png)
*(Resim 37: Uzak düğmesi - seçili makinede fonksiyon çalıştırma menüsü)*

> **İpucu**: Fonksiyon çalıştırmadan önce "Bağlantıyı Test Et" seçeneğini kullanarak makinenin erişilebilir olduğunu doğrulayın.

#### Kurulum (Setup)

1. **Sunucuda Çalıştır** seçeneğini seçin.
2. **Mevcut Fonksiyonlar** listesinde **setup** fonksiyonunu bulun.
3. Fonksiyon adına tıklayarak seçin.

![Makine fonksiyonları listesi - setup fonksiyonu](/assets/images/UserGuideEng/38_server_setup.png)
*(Resim 38: Setup fonksiyonu - makineyi gerekli araçlar ve konfigürasyonlarla hazırlar)*

> **İpucu**: Yeni bir makine kurulurken "setup" fonksiyonunu ilk olarak çalıştırmanız önerilir.

#### Bağlantı Kontrolü (Hello)

1. **Sunucuda Çalıştır** > **hello** fonksiyonunu seçin.
2. **Kuyruğa Ekle** düğmesine tıklayın.

![Hello fonksiyonu seçimi](/assets/images/UserGuideEng/39_remote_hello.png)
*(Resim 39: Hello fonksiyonu - basit test fonksiyonu, hostname'i döndürür)*

3. Görev takip penceresinde sonuçları izleyin.
4. **Response (Console)** bölümünde makinenin çıktısını görün.

![Hello fonksiyonu tamamlandı](/assets/images/UserGuideEng/40_remote_hello_complete.png)
*(Resim 40: Hello fonksiyonu başarıyla tamamlandı - hostname yanıtı)*

> **İpucu**: Hello fonksiyonu makine bağlantısını doğrulamak için ideal bir test fonksiyonudur.

#### Gelişmiş İşlemler

1. **Uzak** > **Sunucuda Çalıştır** > **Gelişmiş** yolunu izleyin.
2. Mevcut fonksiyonları görün: setup, hello, ping, ssh_test, uninstall
3. Gerekli fonksiyonu seçin ve **Kuyruğa Ekle** düğmesine tıklayın.

![Gelişmiş fonksiyonlar listesi](/assets/images/UserGuideEng/41_remote_advanced.png)
*(Resim 41: Advanced seçeneği - ileri seviye fonksiyonlar listesi)*

> **İpucu**: Advanced fonksiyonları kullanmadan önce makine kurulumunun tamamlandığından emin olun.

#### Hızlı Bağlantı Testi

![Uzak menüsü - Bağlantıyı Test Et](/assets/images/UserGuideEng/42_connectivity_test.png)
*(Resim 42: Uzak menüsünden Bağlantıyı Test Et seçeneği)*

> **İpucu**: Makinede SSH veya ağ sorunları varsa, bu test ile sorunları hızlı bir şekilde belirleyebilirsiniz.

---

## 2.5 Depo Oluşturma ve İşlemleri

Depolar, yedekleme verilerinizin saklandığı temel birimlerdir.

### 2.5.1 Depo Oluşturma

1. **Makineler** sekmesinden bir makine seçin.
2. Sağ üst köşedeki **Depo Oluştur** düğmesine tıklayın.

![Depo Oluştur düğmesi](/assets/images/UserGuideEng/43_create_repo_add.png)
*(Resim 43: Makine deposu yönetimi ekranı - Depo Oluştur düğmesi)*

3. Formu doldurun:
   - **Repository Name**: Depo adını yazın (örn: postgresql)
   - **Size**: Depo boyutunu girin (örn: 2GB)
   - **Credential ID**: Otomatik oluşturulan kimlik bilgisini görün
   - **Select Template**: Şablon seçin (örn: databases_postgresql)

![Depo oluşturma formu](/assets/images/UserGuideEng/44_repo_form.png)
*(Resim 44: Depo oluşturma formu - depo adı, boyut ve şablon seçimi)*

4. **Oluştur** düğmesine tıklayın.

> **İpucu**: Credential ID otomatik olarak oluşturulur, el ile değiştirilmemesi önerilir.

5. Görev takip penceresinde aşamaları izleyin: **Atandı** → **İşleniyor** → **Tamamlandı**

![Depo oluşturma tamamlandı](/assets/images/UserGuideEng/45_repo_complete.png)
*(Resim 45: Depo oluşturma işlemi kuyruğa alındı - görev izleme)*

6. **Kapat** düğmesine tıklayın.

> **İpucu**: Görev tipik olarak 1-2 dakika içinde tamamlanır.

![Depo listesi](/assets/images/UserGuideEng/46_repo_list.png)
*(Resim 46: Oluşturulan depo listede görünür)*

### 2.5.2 Depo Fork İşlemi

Mevcut bir depoyu kopyalayarak yeni bir depo oluşturabilirsiniz.

1. Kopyalamak istediğiniz depoyu seçin.
2. **fx** (fonksiyon) menüsünü tıklayın.
3. **fork** seçeneğini tıklayın.

![fx menüsü - fork seçeneği](/assets/images/UserGuideEng/47_fork_button.png)
*(Resim 47: Sağ taraftaki fx menüsü - depo işlemleri)*

4. **Tag ID** alanına yeni etiket yazın (örn: 2025-12-06-20-37-08).
5. **Kuyruğa Ekle** düğmesine tıklayın.

![Fork yapılandırma formu](/assets/images/UserGuideEng/48_fork_form.png)
*(Resim 48: Fork işleminde deponun yeni etiketini belirleyin)*

6. **Tamamlandı** mesajını bekleyin ve **Kapat** butonuna tıklayın.

![Fork tamamlandı](/assets/images/UserGuideEng/49_repo_completed.png)
*(Resim 49: Fork işlemi başarıyla tamamlandı)*

> **İpucu**: Etiketi varsayılan tarih-saat formatında oluşturmak iyi bir pratiktir. Fork işlemi orijinal depoyu etkilemez.

### 2.5.3 Depo Başlatma (Up)

Depoyu aktif hale getirmek için:

1. Depoyu seçin ve **fx** > **up** yolunu izleyin.

![Başlatma (Up) işlemi](/assets/images/UserGuideEng/50_repo_up.png)
*(Resim 50: fx menüsünden "up" seçeneği - depoyu başlatma)*

2. **Tamamlandı** mesajını bekleyin.

![Başlatma tamamlandı](/assets/images/UserGuideEng/51_repo_up_complete.png)
*(Resim 51: Depo başlatma işlemi tamamlandı)*

> **İpucu**: "Up" işlemi deponun tanımlı Docker hizmetlerini başlatır.

### 2.5.4 Depo Durdurma (Down)

Aktif bir depoyu durdurmak için:

1. Depoyu seçin ve **fx** > **down** yolunu izleyin.

![Durdurma (Down) işlemi](/assets/images/UserGuideEng/52_down_button.png)
*(Resim 52: fx menüsünden "down" seçeneği - depoyu kapatma)*

2. **Tamamlandı** mesajını bekleyin.

![Durdurma tamamlandı](/assets/images/UserGuideEng/53_down_completed.png)
*(Resim 53: Depo durdurma işlemi tamamlandı)*

> **İpucu**: "Down" işlemi depoyu güvenli bir şekilde kapatır. Veri kaybı olmaz, sadece hizmetler durdurulur.

### 2.5.5 Dağıtım (Deploy)

Depoyu farklı bir konuma dağıtmak için:

1. Depoyu seçin ve **fx** > **deploy** yolunu izleyin.

![Dağıtım (Deploy) işlemi](/assets/images/UserGuideEng/54_deploy_button.png)
*(Resim 54: fx menüsünden "deploy" seçeneği)*

2. **Tag ID** alanına dağıtılacak sürümü girin.
3. **Target Machines** alanında hedef makineleri seçin.
4. **Override existing file** seçeneğini işaretleyin (varsa).
5. **Kuyruğa Ekle** butonuna tıklayın.

![Dağıtım formu](/assets/images/UserGuideEng/55_deploy_form.png)
*(Resim 55: Deploy işlemini yapılandırma - tag, hedef makineler ve seçenekler)*

6. **Tamamlandı** mesajını bekleyin.

![Dağıtım tamamlandı](/assets/images/UserGuideEng/56_deploy_completed.png)
*(Resim 56: Depo dağıtma tamamlandı)*

> **İpucu**: Deploy işlemi tamamlandıktan sonra hedef makinelerde depoyu başlatmak için "up" komutu çalıştırabilirsiniz.

### 2.5.6 Yedekleme (Backup)

Depoyu yedeklemek için:

1. Depoyu seçin ve **fx** > **backup** yolunu izleyin.

![Yedekleme (Backup) işlemi](/assets/images/UserGuideEng/57_backup_button.png)
*(Resim 57: fx menüsünden "backup" seçeneği)*

2. Formu doldurun:
   - **Yedekleme Etiketi**: Tanımlayıcı ad yazın (örn: backup01012025)
   - **Hedef Depolama Sistemleri**: Yedekleme konumunu seçin
   - **Mevcut Dosyayı Üzerine Yaz**: Seçeneği açın veya kapatın
   - **Kontrol Noktasını Etkinleştir**: Ayarı gözden geçirin

![Yedekleme formu](/assets/images/UserGuideEng/58_backup_form.png)
*(Resim 58: Yedekleme yapılandırma formu - hedef, dosya adı ve seçenekler)*

3. **Kuyruğa Ekle** düğmesine tıklayın.

> **İpucu**: Yedekleme etiketi için anlaşılır bir ad kullanın. Büyük depolar için kontrol noktası etkinleştirmeyi düşünün.

4. **Tamamlandı** mesajını bekleyin.

![Yedekleme tamamlandı](/assets/images/UserGuideEng/59_backup_completed.png)
*(Resim 59: Yedekleme görevi başarıyla tamamlandı)*

> **İpucu**: Tamamlandı durumuna ulaşmadan önce sabrıyla bekleyin; büyük yedeklemeler birkaç dakika alabilir.

### 2.5.7 Şablon Uygulama

Depoya yeni bir şablon uygulamak için:

1. Depoyu seçin ve **fx** > **Şablonlar** yolunu izleyin.

![Şablonlar işlemi](/assets/images/UserGuideEng/60_templates_button.png)
*(Resim 60: fx menüsünden "Şablonlar" seçeneği)*

2. Arama kutusuna yazarak şablonları filtreleyin.
3. İstediğiniz şablonu tıklayarak seçin (seçili şablon kalın çerçeve ile vurgulanır).
4. **Kuyruğa Ekle** düğmesine tıklayın.

![Şablon seçim formu](/assets/images/UserGuideEng/61_templates_form.png)
*(Resim 61: Kullanılabilir şablonları arama ve seçme)*

> **İpucu**: Şablonları hızlıca bulmak için arama kutusunu kullanın. "Detayları Görüntüle" ile şablon özellikleri hakkında bilgi edinin.

5. **Tamamlandı** mesajını bekleyin.

![Şablon uygulandı](/assets/images/UserGuideEng/62_templates_completed.png)
*(Resim 62: Şablon uygulaması başarıyla tamamlandı)*

### 2.5.8 Bağlantıyı Kesme (Unmount)

Depo bağlantısını kesmek için:

1. Depoyu seçin ve **fx** > **Gelişmiş** > **Bağlantıyı Kes** yolunu izleyin.

![Bağlantıyı Kes işlemi](/assets/images/UserGuideEng/63_unmount_button.png)
*(Resim 63: İleri menüdeki "Bağlantıyı Kes" seçeneği)*

2. **Tamamlandı** mesajını bekleyin.

![Bağlantı kesildi](/assets/images/UserGuideEng/64_unmount_completed.png)
*(Resim 64: Bağlantı kesme işlemi tamamlandı)*

> **İpucu**: Bağlantıyı kesmeden önce depo üzerinde etkin işlem olmadığından emin olun. Bağlantı kesme sonrasında depo erişilir olmaktan çıkar.

### 2.5.9 Genişletme (Expand)

Depo boyutunu artırmak için:

1. Depoyu seçin ve **fx** > **Gelişmiş** > **Genişlet** yolunu izleyin.

![Genişletme işlemi](/assets/images/UserGuideEng/65_expand_button.png)
*(Resim 65: İleri menüdeki "Genişlet" seçeneği)*

2. **Yeni Boyut** alanına istediğiniz boyutu girin.
3. Sağ taraftaki açılır menüden birim seçin (GB, TB).
4. **Kuyruğa Ekle** düğmesine tıklayın.

![Genişletme formu](/assets/images/UserGuideEng/66_expand_form.png)
*(Resim 66: Depo boyutunu artırmak için yeni boyut parametresi)*

> **İpucu**: Mevcut boyuttan küçük bir değer girmeyin. Depo genişletme sırasında hizmet kesilmez.

5. **Tamamlandı** mesajını bekleyin.

![Genişletme tamamlandı](/assets/images/UserGuideEng/67_expand_completed.png)
*(Resim 67: Depo genişletme işlemi tamamlandı)*

### 2.5.10 Yeniden Adlandırma

Depo adını değiştirmek için:

1. Depoyu seçin ve **fx** > **Yeniden Adlandır** yolunu izleyin.

![Yeniden Adlandırma işlemi](/assets/images/UserGuideEng/68_rename_button.png)
*(Resim 68: fx menüsünden "Yeniden Adlandır" seçeneği)*

2. Yeni depo adını yazın.
3. **Kaydet** düğmesine tıklayın.

![Yeniden Adlandırma formu](/assets/images/UserGuideEng/69_rename_form.png)
*(Resim 69: Yeni depo adını girmek için diyalog)*

> **İpucu**: Depo adları, depo türünü ve amacını yansıtacak şekilde anlamlı olmalıdır. Özel karakterlerden kaçının.

### 2.5.11 Depo Silme

Depoyu kalıcı olarak silmek için:

1. Depoyu seçin ve **fx** > **Depoyu Sil** yolunu izleyin.

![Depoyu Sil işlemi](/assets/images/UserGuideEng/70_delete_repo_button.png)
*(Resim 70: fx menüsünden "Depoyu Sil" seçeneği - kırmızı)*

2. Onay penceresinde **Sil** butonuna tıklayın.

> **Dikkat**: Depo silme işlemi geri alınamaz. Silmeden önce depo verilerinin yedeklenmiş olduğundan emin olun.

### 2.5.12 Depo Detayları

Depo hakkında ayrıntılı bilgi almak için:

1. Depoyu seçin.
2. Göz simgesine (**Detayları Görüntüle**) tıklayın.

![Detayları Görüntüle düğmesi](/assets/images/UserGuideEng/71_repo_view_button.png)
*(Resim 71: Depo detaylarını açmak için göz simgesi)*

3. Detay panelinde bilgileri inceleyin:
   - **Depo adı** ve türü
   - **Team**: Ait olduğu takım
   - **Machine**: Bulunduğu makina
   - **Vault Version**: Şifreleme sürümü
   - **Repository GUID**: Benzersiz kimlik
   - **Status**: Bağlı/Bağlı değil durumu
   - **Image Size**: Toplam boyut
   - **Last Modified**: Son değiştirilme tarihi

![Depo detay paneli](/assets/images/UserGuideEng/72_repo_details_view.png)
*(Resim 72: Seçilen depo hakkındaki kapsamlı bilgiler)*

> **İpucu**: Bu panelde gösterilen tüm bilgiler referans amaçlıdır. Depo işlemleri için fx menüsündeki seçenekleri kullanın.

---

## 2.6 Depo Bağlantı İşlemleri

Depolara farklı yöntemlerle bağlanabilirsiniz.

### 2.6.1 Masaüstü Uygulaması ile Bağlantı

1. Depo satırında **Yerel** düğmesine tıklayın.

![Yerel bağlantı düğmesi](/assets/images/UserGuideEng/73_repo_connection_local.png)
*(Resim 73: Depo satırında "Yerel" düğmesi - masaüstü uygulaması erişimi)*

2. Açılır menüden erişim yöntemini seçin:
   - **Masaüstü Uygulaması**: Grafik arayüzle erişim
   - **VS Code**: Kod editöründe açma
   - **Terminal**: Komut satırında erişim
   - **CLI Komutları**: Komut satırı araçları

![Bağlantı seçenekleri menüsü](/assets/images/UserGuideEng/74_repo_connection.png)
*(Resim 74: Depo bağlantısı menüsü - farklı erişim yolları)*

> **İpucu**: VS Code ile çalışıyorsanız "VS Code" seçeneği en hızlı entegrasyonu sağlar.

3. Tarayıcı izin istediğinde **Aç** düğmesini tıklayın.

![Masaüstü uygulaması açma izni](/assets/images/UserGuideEng/75_desktop_open_page.png)
*(Resim 75: Tarayıcı masaüstü uygulamasını açma izni istiyor)*

> **İpucu**: Masaüstü uygulamasını her açışta izin vermek istemiyorsanız, "Her zaman izin ver" seçeneğini işaretleyin.

---

## 2.7 Ayarlar

Ayarlar bölümünden profil ve sistem ayarlarınızı yönetebilirsiniz.

### 2.7.1 Parola Değiştirme

1. Sol menüden **Ayarlar** > **Profil** sekmesine gidin.

![Profil ayarları sayfası](/assets/images/UserGuideEng/76_profiles_button.png)
*(Resim 76: Ayarlar → Profil sayfası - kişisel vault ayarları)*

2. **Parola Değiştir** düğmesine tıklayın.

![Parola Değiştir düğmesi](/assets/images/UserGuideEng/77_profiles_change_button.png)
*(Resim 77: Kişisel ayarlar bölümünde "Parola Değiştir" düğmesi)*

3. Yeni parolanızı girin. Parola gereksinimleri:
   - En az 8 karakter uzunluğunda
   - Büyük ve küçük harfler içermeli
   - En az bir sayı içermeli
   - En az bir özel karakter içermeli

4. **Yeni Parolayı Onayla** alanına aynı parolayı tekrar girin.
5. **Parola Değiştir** düğmesine tıklayın.

![Parola değiştirme formu](/assets/images/UserGuideEng/78_profiles_change_form.png)
*(Resim 78: Parola Değiştir formu - güvenlik gereksinimleri görünür)*

> **İpucu**: Güçlü bir parola oluştururken rastgele kombinasyonlar kullanın.

---

## 2.8 Depolama

Depolama bölümü, yedekleme verilerinizin saklanacağı fiziksel alanları yönetmenizi sağlar.

### 2.8.1 Depolama Ekleme

1. Sol menüden **Depolama** sekmesine gidin.
2. **Depolama Ekle** düğmesine tıklayın.

![Depolama Ekle düğmesi](/assets/images/UserGuideEng/79_storage_add_button.png)
*(Resim 79: Depolama yönetim sayfası - "Depolama Ekle" düğmesi)*

3. Formu doldurun:
   - **Depolama Adı**: Açıklayıcı bir ad girin
   - **Depolama Sağlayıcısı**: Seçin (örn: s3)
   - **Açıklama**: Opsiyonel açıklama ekleyin
   - **Versiyonlamayı Devre Dışı Bırak**: İsteğe bağlı
   - **Ek Parametreler**: rclone bayrakları (örn: --transfers 4)

![Depolama oluşturma formu](/assets/images/UserGuideEng/80_storage_form.png)
*(Resim 80: Depolama Ekle formu - ad, sağlayıcı, açıklama ve parametreler)*

4. **Oluştur** düğmesine tıklayın.

> **İpucu**: Ek Parametreler, depolama performansını optimize etmek için rclone bayraklarını kabul eder.

---

## 2.9 Kimlik Bilgileri

Kimlik bilgileri bölümü, depolarınızın erişim bilgilerini güvenli şekilde yönetmenizi sağlar.

### 2.9.1 Kimlik Bilgisi Düzenleme

1. Sol menüden **Kimlik Bilgileri** sekmesine gidin.
2. Düzenlemek istediğiniz kaydı seçin.
3. **Düzenle** düğmesine tıklayın.

![Kimlik Bilgileri listesi](/assets/images/UserGuideEng/81_credentials.png)
*(Resim 81: Kimlik Bilgileri sayfası - depo adları, takımları ve yönetim düğmeleri)*

4. Gerekirse **Depo Adını** değiştirin.
5. **Kaydet** düğmesiyle kaydedin.

![Kimlik bilgisi düzenleme formu](/assets/images/UserGuideEng/82_credentials_form.png)
*(Resim 82: Depo Adını Düzenle formu - vault yapılandırması alanları)*

> **İpucu**: Kimlik bilgileri şifrelenmiş halde depolanır ve sadece dağıtım sırasında decrypt edilir.

### 2.9.2 Kimlik Bilgisi Takibi

1. Takip etmek istediğiniz kaydı seçin.
2. **Takip** düğmesine tıklayın.

![Takip düğmesi](/assets/images/UserGuideEng/83_credentials_trace_button.png)
*(Resim 83: Kimlik Bilgileri tablosunda "Takip" düğmesi)*

3. Denetim geçmişini inceleyin.
4. **Dışa Aktar** düğmesinden format seçin: **CSV** veya **JSON**.

![Kimlik bilgisi denetim geçmişi](/assets/images/UserGuideEng/84_credentials_list_export.png)
*(Resim 84: Kimlik Bilgileri listesi - Dışa Aktar seçenekleri)*

> **İpucu**: Takip özelliği, güvenlik denetim amaçları için kimlik bilgilerinin kullanım izini sağlar.

### 2.9.3 Kimlik Bilgisi Silme

1. Silmek istediğiniz kaydı seçin.
2. Kırmızı **Sil** düğmesine tıklayın.

![Sil düğmesi](/assets/images/UserGuideEng/85_credentials_delete.png)
*(Resim 85: Kimlik Bilgileri sayfasında kırmızı "Sil" düğmesi)*

3. Onay penceresinde **Sil** düğmesine tıklayın.

![Silme onayı](/assets/images/UserGuideEng/86_credentials_delete_confirm.png)
*(Resim 86: Silme onayı diyaloğu - işlem geri alınamaz uyarısı)*

> **Dikkat**: Silmeden önce, kimlik bilgisinin başka makinelerde veya işlemlerde kullanılmadığından emin olun. Kritik kimlik bilgilerini silmeden önce yedek kopyasının olduğundan emin olun.

---

## 2.10 Kuyruk

Kuyruk bölümü, sistemde bekleyen ve tamamlanan işlemleri takip etmenizi sağlar.

### 2.10.1 Kuyruk İşlemleri

1. Sol menüden **Kuyruk** sekmesine tıklayın.

![Kuyruk sayfası](/assets/images/UserGuideEng/87_queue_button.png)
*(Resim 87: Kuyruk sayfası - filtreleme seçenekleri ve durum sekmeleri)*

2. Kuyruk öğelerini filtrelemek için:
   - **Takım**, **Makine**, **Bölge** ve **Köprü** filtrelerini kullanın
   - **Tarih aralığını** belirtin
   - **Sadece Eski Öğeler** seçeneğini işaretleyin

3. Durum sekmelerinde ayrıntıları görüntüleyin:
   - **Etkin**: İşlenmekte olan görevler
   - **Tamamlanan**: Başarıyla tamamlanan görevler
   - **İptal Edilen**: İptal edilen görevler
   - **Başarısız**: Başarısız görevler

4. **Dışa Aktar** düğmesinden format seçin: **CSV** veya **JSON**.

![Kuyruk dışa aktarımı](/assets/images/UserGuideEng/88_queue_export.png)
*(Resim 88: Kuyruk listesi - Dışa Aktar seçenekleri)*

> **İpucu**: "Sadece Eski Öğeler" seçeneği, uzun süredir işlenmekte olan görevleri bulmada yardımcı olur. Düzenli olarak kuyruk geçmişini dışa aktararak, görev yürütme trendlerini analiz edebilirsiniz.

---

## 2.11 Denetim

Denetim bölümü, sistemde yapılan tüm işlemlerin kayıtlarını tutar.

### 2.11.1 Denetim Kayıtları

1. Sol menüden **Denetim** sekmesine tıklayın.

![Denetim listesi](/assets/images/UserGuideEng/89_audit_list.png)
*(Resim 89: Denetim sayfası - tüm sistem işlemlerinin ayrıntılı kaydı)*

2. Denetim kayıtlarını filtreleyin:
   - **Tarih Aralığı**: Belirli dönem için filtreleme
   - **Varlık Türü**: İstek, Makine, Kuyruk vb. filtreleme
   - **Arama**: Sözel arama yapma

3. Her kaydın bilgilerini inceleyin:
   - **Zaman Damgası**: İşlemin gerçekleştiği tarih ve saat
   - **Aksiyon**: Yapılan işlem (Oluştur, Düzenle, Sil vb.)
   - **Varlık Türü**: İşlemi alan nesne türü
   - **Varlık Adı**: Belirli nesne tanımlayıcısı
   - **Kullanıcı**: İşlemi gerçekleştiren kullanıcı
   - **Detaylar**: İşleme ilişkin ek bilgiler

4. **Dışa Aktar** düğmesinden format seçin: **CSV** veya **JSON**.

![Denetim dışa aktarımı](/assets/images/UserGuideEng/90_audit_export.png)
*(Resim 90: Denetim kaydı dışa aktarma - CSV ve JSON seçenekleri)*

> **İpucu**: Denetim kaydı, güvenlik ve uyumluluk amaçlarında tüm sistem aktivitesini izlemek için kritik önem taşır. Düzenli olarak denetim kaydını dışa aktarın ve güvenli bir konumda saklayın.

---

**© 2025 Rediacc Platformu – Tüm Hakları Saklıdır.**
