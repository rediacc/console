---
title: Web Uygulaması
description: Rediacc ile web uygulaması mimarisi ve dağıtımını anlama
category: Reference
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

![Registration process walkthrough](/assets/videos/user-guide/01-01-registration.webm)
*(Video: Complete registration flow from start to finish)*

Rediacc platformunu kullanmaya başlamak için öncelikle bir hesap oluşturmanız gerekmektedir.

![Rediacc giriş sayfası - her zaman ayakta kalan altyapı](/assets/images/user-guide/01_login.png)
*(Resim 1: Ana giriş sayfası, Rediacc platformunun başlıca özelliklerini tanıtan açılış ekranı)*

1. Tarayıcıdan [https://www.rediacc.com/](https://www.rediacc.com/) adresine gidin.
2. Sayfanın sağ üst köşesinde **{{t:auth.login.signIn}}** düğmesini tıklayın.
3. Ücretsiz erişim için **Başlayın** veya bir demo için **Demo Talep Edin** seçeneğini seçin.

> **İpucu**: Hiçbir kredi kartı gerekmeden ücretsiz hesap oluşturabilirsiniz. 10 CPU çekirdeği ve sınırsız takımlar dahildir.

![Rediacc Giriş Yap formu - e-posta ve parola alanları](/assets/images/user-guide/02_register.png)
*(Resim 2: Mevcut kullanıcılar için Giriş Yap ekranı)*

4. Hesap yoksa **{{t:auth.login.register}}** bağlantısını tıklayarak yeni hesap oluşturun.

5. Açılan formda aşağıdaki bilgileri doldurun:
   - **{{t:auth.registration.organizationName}}**: Kuruluş adınızı girin
   - **{{t:auth.login.email}}**: Geçerli bir e-posta adresi girin
   - **{{t:auth.login.password}}**: En az 8 karakterli parola oluşturun
   - **{{t:auth.registration.passwordConfirm}}**: Aynı parolayı yeniden girin

![Hesap Oluştur modal - kayıt, doğrulama ve tamamlanma adımları](/assets/images/user-guide/03_create_account.png)
*(Resim 3: Yeni kullanıcı kaydı için adım adım form - Kayıt > Doğrulama > Tamamlanma)*

6. Kullanım koşulları ve gizlilik politikasını kabul etmek için kutucuğu işaretleyin.
7. **{{t:auth.registration.createAccount}}** düğmesine tıklayın.

> **İpucu**: Parola en az 8 karakter olmalı ve güçlü olması önerilir. Tüm alanlar zorunludur.

8. E-postanıza gelen 6 haneli doğrulama kodunu kutulara sırasıyla girin.
9. **{{t:auth.registration.verifyAccount}}** düğmesine tıklayın.

![Doğrulama kodu girişi - 6 haneli aktivasyon kodu](/assets/images/user-guide/04_verification_code.png)
*(Resim 4: Yöneticiye gönderilen aktivasyon kodunun girildiği pencere)*

> **İpucu**: Doğrulama kodu limitli süreli geçerlidir. Kodun gelmemesi durumunda spam klasörünü kontrol edin.

---

### 1.2 Giriş Yapma

![Sign in process walkthrough](/assets/videos/user-guide/01-02-login.webm)
*(Video: Complete sign in flow)*

Hesabınız oluşturulduktan sonra platforma giriş yapabilirsiniz.

1. **{{t:auth.login.email}}** alanını doldurun (kırmızı uyarı görünüyorsa gereklidir).
2. **{{t:auth.login.password}}** alanını doldurun.
3. **{{t:auth.login.signIn}}** düğmesine tıklayın.

![Giriş Yap formu - hata uyarısı ile zorunlu alanlar](/assets/images/user-guide/05_sign_in.png)
*(Resim 5: Giriş formu - hata mesajları kırmızı sınır ile işaretlenir)*

> **İpucu**: Hata mesajı "Bu alan gereklidir" ise boş alanları doldurun. Unutulan şifre için yöneticiyle iletişime geçin.

4. Başarılı girişten sonra **{{t:common.navigation.dashboard}}** ekranına yönlendirilirsiniz.

![Rediacc kontrol paneli - makine listesi ve sidebar menüsü](/assets/images/user-guide/06_dashboard.png)
*(Resim 6: Başarılı giriş sonrası ana dashboard - Sol sidebar'da Organizasyon, Makineler ve Ayarlar menüleri)*

> **İpucu**: Dashboard otomatik yenilenir. Taze bilgiler için sayfayı F5 ile yenileyebilirsiniz.

---

## 2. Arayüz Tanıtımı

Giriş yaptıktan sonra karşınıza çıkan ekran temel olarak şu bölümlerden oluşur:

- **{{t:common.navigation.organization}}**: Kullanıcılar, takımlar ve erişim kontrolü
- **{{t:common.navigation.machines}}**: Sunucu ve depo yönetimi
- **{{t:common.navigation.settings}}**: Profil ve sistem ayarları
- **{{t:common.navigation.storage}}**: Depolama alanları yönetimi
- **{{t:common.navigation.credentials}}**: Erişim kimlik bilgileri
- **{{t:common.navigation.queue}}**: İş kuyruğu yönetimi
- **{{t:common.navigation.audit}}**: Sistem denetim kayıtları

---

## 2.1 Organizasyon - Kullanıcılar

Kullanıcı yönetimi, organizasyonunuzdaki kişilerin platforma erişimini kontrol etmenizi sağlar.

### 2.1.1 Kullanıcı Ekleme

![Adding users walkthrough](/assets/videos/user-guide/02-01-01-user-create.webm)
*(Video: Creating a new user)*

1. Sol sidebar'da **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationUsers}}** seçeneğini tıklayın.
2. Tüm kullanıcıların listesini tablo formatında görüntüleyin.
3. Her kullanıcı satırı e-posta, durum ({{t:organization.users.status.active}}/{{t:organization.users.status.inactive}}), izin grubu ve son aktivite zamanını gösterir.

![Kullanıcılar yönetimi sayfası - aktif kullanıcılar listesi](/assets/images/user-guide/07_users.png)
*(Resim 7: Organizasyon altında Kullanıcılar bölümü - tüm kullanıcıların bilgileri görüntülenir)*

4. Sağ üst köşedeki **"+"** simgesine tıklayın.
5. **{{t:organization.users.modals.createTitle}}** düğmesine tıklayın ve açılan formu doldurun:
   - **{{t:organization.users.form.emailLabel}}**: Kullanıcının e-posta adresini girin
   - **{{t:organization.users.form.passwordLabel}}**: Geçici bir parola girin

![Kullanıcı oluşturma modal - e-posta ve parola alanları](/assets/images/user-guide/08_user_add.png)
*(Resim 8: Yeni kullanıcı eklemek için modal pencere - basit ve hızlı kullanıcı oluşturma formu)*

6. **{{t:common.actions.create}}** düğmesine tıklayın.

> **İpucu**: Oluşturulan kullanıcıya giriş bilgileri güvenli şekilde iletilmelidir. İlk girişinde parola değiştirmesi önerilir.

![Kullanıcı listesi - üç kullanıcı ile tam tablo görünümü](/assets/images/user-guide/09_user_list.png)
*(Resim 9: Kullanıcılar yönetimi sayfasında aktif ve pasif kullanıcıların tamamı)*

> **İpucu**: Sayfa otomatik 20 kayıt gösterir. Daha fazla kaydı görmek için sayfalama kullanın.

### 2.1.2 Kullanıcı İzinleri Atama

![User permissions walkthrough](/assets/videos/user-guide/02-01-02-user-permissions.webm)
*(Video: Assigning permission groups to users)*

Kullanıcılara belirli izin grupları atayarak erişim yetkilerini yönetebilirsiniz.

1. **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationUsers}}** sekmesinden bir kullanıcı seçin.
2. İşlemler sütunundaki kalkan simgesine tıklayın (**{{t:organization.access.tabs.permissions}}**).

![İzin yönetimi - kalkan, çark ve sil simgeleri](/assets/images/user-guide/10_users_permissions.png)
*(Resim 10: Kullanıcı işlemlerinin simge gösterimi - her simge farklı bir işlemi temsil eder)*

3. Açılan formdan bir **{{t:organization.users.modals.permissionGroupLabel}}** seçin.
4. Kullanıcının yanında grubun kaç kullanıcı ve izin içerdiği gösterilir.
5. **{{t:organization.users.modals.assignTitle}}** düğmesine tıklayarak değişiklikleri kaydedin.

![İzin atama modal - Yöneticiler grubu](/assets/images/user-guide/11_user_permissions_form.png)
*(Resim 11: Seçili kullanıcıya izin grubu atamak için modal - açılır listeyle mevcut gruplar)*

> **İpucu**: Bazı izin grupları sistem tarafından sabitlenmiştir ve değiştirilemez.

### 2.1.3 Kullanıcı Aktivasyonu

![User activation walkthrough](/assets/videos/user-guide/02-01-03-user-activation.webm)
*(Video: Activating an inactive user)*

Devre dışı bırakılmış kullanıcıları tekrar aktif hale getirebilirsiniz.

1. **Kullanıcılar** listesinden pasif durumundaki kullanıcıyı bulun.
2. İşlemler sütunundaki kırmızı simgeyi tıklayın.

![Kullanıcı etkinleştirme - "Etkinleştir" tooltip görünümlü](/assets/images/user-guide/12_users_activation.png)
*(Resim 12: Pasif kullanıcıyı etkinleştirme işlemi)*

3. Onay penceresinde **{{t:common.general.yes}}** düğmesine tıklayın.

![Etkinleştir onay modal](/assets/images/user-guide/13_users_activation_confirm.png)
*(Resim 13: Kullanıcı etkinleştirme işleminin onaylanması için modal pencere)*

> **İpucu**: Bu işlem geri alınabilir. Kullanıcıyı pasif hale getirmek için aynı şekilde işlem yapabilirsiniz.

### 2.1.4 Kullanıcı Takibi (Trace)

![User trace walkthrough](/assets/videos/user-guide/02-01-04-user-trace.webm)
*(Video: Viewing user activity trace)*

Kullanıcı aktivitelerini izlemek için takip özelliğini kullanabilirsiniz.

1. Bir kullanıcı seçin ve işlemler sütunundaki çark simgesini tıklayın.
2. **{{t:common.actions.trace}}** seçeneğini tıklayarak kullanıcının aktivite geçmişini açın.

![Kullanıcı takip (Trace) - "Takip" tooltip ile işlem düğmesi](/assets/images/user-guide/14_users_trace.png)
*(Resim 14: Kullanıcı aktivitelerini takip etme seçeneği)*

3. Açılan ekranda kullanıcının geçmiş aktiviteleri listelenir.
4. En üstte istatistikler görüntülenir: Toplam Kayıt, Görülen Kayıt, Son Aktivite.
5. **{{t:common.actions.export}}** düğmesine tıklayın ve formatı seçin: **{{t:common.exportCSV}}** veya **{{t:common.exportJSON}}**.

![Denetim tarihi (Audit History) - Dışa Aktar seçenekleri](/assets/images/user-guide/15_user_trace_export.png)
*(Resim 15: Kullanıcının tam aktivite geçmişi - istatistikler, detaylar ve Dışa Aktar seçenekleri)*

> **İpucu**: Denetim verilerini düzenli olarak dışa aktararak güvenlik ve uyum kayıtlarını saklayın. CSV format Excel'de açılabilir.

---

## 2.2 Organizasyon - Takımlar

Takımlar, kullanıcıları gruplandırarak kaynaklara toplu erişim sağlamanıza olanak tanır.

### 2.2.1 Takım Oluşturma

![Creating teams walkthrough](/assets/videos/user-guide/02-02-01-team-create.webm)
*(Video: Creating a new team)*

1. **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationTeams}}** sekmesine gidin.
2. **"+"** düğmesine tıklayın.
3. **{{t:common.vaultEditor.fields.TEAM.name.label}}** alanına takımınızın adını girin.
4. **{{t:common.vaultEditor.vaultConfiguration}}** bölümünde **{{t:common.vaultEditor.fields.TEAM.SSH_PRIVATE_KEY.label}}** ve **{{t:common.vaultEditor.fields.TEAM.SSH_PUBLIC_KEY.label}}** alanlarını doldurun.

![Yeni takım oluşturma formu - takım adı ve SSH anahtarları](/assets/images/user-guide/16_teams_create.png)
*(Resim 16: "Private Team" içinde yeni bir takım oluşturma)*

5. **{{t:common.actions.create}}** düğmesine tıklayarak takımı kaydedin.

> **İpucu**: SSH anahtarları Bridge SSH kimlik doğrulaması için gereklidir. Eksik anahtar uyarısı alırsanız, her iki anahtarı da sağlayın.

### 2.2.2 Takım Düzenleme

![Team editing walkthrough](/assets/videos/user-guide/02-02-02-team-edit.webm)
*(Video: Editing team information)*

1. Takımlar listesinden düzenlemek istediğiniz takımın yanındaki kalem simgesine tıklayın.
2. **{{t:common.vaultEditor.fields.TEAM.name.label}}** alanında takımın adını gerekirse değiştirin.
3. **{{t:common.vaultEditor.vaultConfiguration}}** bölümünde SSH anahtarlarını güncelleyin.
4. **{{t:common.save}}** düğmesine tıklayarak değişiklikleri uygulayın.

![Takım düzenleme formu - mavi bilgi mesajı](/assets/images/user-guide/17_teams_edit_form.png)
*(Resim 17: Mevcut bir takımın bilgilerini düzenleme)*

> **İpucu**: Takım yapılandırması organizasyonel yapı için kullanılır. Değişiklikler tüm takım üyeleri için etkili olur.

### 2.2.3 Takım Üyeleri Yönetimi

![Team members management walkthrough](/assets/videos/user-guide/02-02-03-team-members.webm)
*(Video: Managing team members)*

1. Bir takım seçin ve kullanıcı simgesine tıklayın.
2. **{{t:organization.teams.manageMembers.currentTab}}** sekmesinde takıma zaten atanmış üyeleri görüntüleyin.
3. **{{t:organization.teams.manageMembers.addTab}}** sekmesine geçin.
4. E-posta adresi girin veya açılır listeden bir kullanıcı seçin.
5. **"+"** düğmesine tıklayarak üyeyi takıma ekleyin.

![Takım üyelerini yönetme formu - "Mevcut Üyeler" ve "Üye Ekle" sekmeleri](/assets/images/user-guide/18_teams_members_form.png)
*(Resim 18: Takım üyelerini yönetme paneli)*

> **İpucu**: Aynı üyeyi birden fazla takıma atayabilirsiniz.

### 2.2.4 Takım Takibi

![Team trace walkthrough](/assets/videos/user-guide/02-02-04-team-trace.webm)
*(Video: Viewing team audit history)*

1. Takip etmek istediğiniz takımı seçin.
2. Saat/geçmiş simgesine tıklayın.
3. **{{t:resources.audit.title}}** penceresinde Toplam Kayıt, Görüntülenen Kayıt ve Son Aktivite sayılarını inceleyin.
4. {{t:common.exportCSV}} veya {{t:common.exportJSON}} formatında dışa aktarmak için **{{t:common.actions.export}}** düğmesine tıklayın.

![Denetim geçmişi modal - DataBassTeam takımı](/assets/images/user-guide/19_teams_trace.png)
*(Resim 19: Takım denetim geçmişini görüntüleme)*

> **İpucu**: Denetim geçmişi uyum ve güvenlik kontrolü için önemlidir.

### 2.2.5 Takım Silme

![Team deletion walkthrough](/assets/videos/user-guide/02-02-05-team-delete.webm)
*(Video: Deleting a team)*

1. Silmek istediğiniz takımın yanındaki çöp kutusu (kırmızı) simgesine tıklayın.
2. Onay iletişim kutusunda takım adının doğru olduğunu kontrol edin.
3. **{{t:common.general.yes}}** düğmesine tıklayın.

![Takım silme onay iletişim kutusu](/assets/images/user-guide/20_teams_delete.png)
*(Resim 20: Takım silme işlemi onayı)*

> **Dikkat**: Takım silme işlemi geri alınamaz. Silmeden önce takımda önemli veri olup olmadığını kontrol edin.

---

## 2.3 Organizasyon - Erişim Kontrolü

Erişim kontrolü, izin grupları oluşturarak kullanıcı yetkilerini merkezi olarak yönetmenizi sağlar.

### 2.3.1 İzin Grubu Oluşturma

![Permission group creation walkthrough](/assets/videos/user-guide/02-03-01-permission-create.webm)
*(Video: Creating a permission group)*

1. **{{t:common.navigation.organization}}** > **{{t:common.navigation.organizationAccess}}** sekmesine gidin.
2. **"+"** düğmesini tıklayın.
3. **{{t:organization.access.modals.groupPlaceholder}}** alanına anlamlı bir ad girin.
4. Grubu oluşturmak için **{{t:common.actions.confirm}}** düğmesine tıklayın.

![İzin grubu oluşturma formu](/assets/images/user-guide/21_create_access.png)
*(Resim 21: Yeni bir İzin Grubu oluşturma)*

> **İpucu**: İzin grupları, benzer izinlere sahip kullanıcıları organize etmek için kullanılır. Grup adlarını açıklayıcı tutun (örn: "Admin", "Okuma Yalnız", "Depo Yöneticisi").

### 2.3.2 İzin Yönetimi

![Permission management walkthrough](/assets/videos/user-guide/02-03-02-permission-manage.webm)
*(Video: Managing permissions for a group)*

1. Bir İzin Grubu seçin ve **{{t:organization.access.modals.managePermissionsTitle}}** seçeneğine tıklayın.
2. **{{t:organization.access.modals.currentPermissionsTab}}** sekmesinde grubun erişim haklarını görüntüleyin.
3. Her işlemin yanındaki kırmızı **{{t:common.delete}}** düğmesine tıklayarak bir izni geri alabilirsiniz.
4. Gruba yeni izinler eklemek için **{{t:organization.access.modals.addPermissionsTab}}** sekmesine tıklayın.

![İzin yönetimi paneli - atanmış izinler listesi](/assets/images/user-guide/22_access_permission.png)
*(Resim 22: İzin Grubu için İzinleri Yönetme)*

> **İpucu**: İzinleri en az yetki ilkesine göre verin. Gereksiz izinleri düzenli olarak gözden geçirin ve kaldırın.

---

## 2.4 Makineler

Makineler bölümü, sunucularınızı ve depo kaynaklarınızı yönetmenizi sağlar.

### 2.4.1 Makine Ekleme

![Adding machines walkthrough](/assets/videos/user-guide/02-04-01-machine-create.webm)
*(Video: Adding a new machine)*

1. Sol menüden **{{t:common.navigation.machines}}** sekmesine gidin.
2. Sağ üst köşedeki **{{t:machines.createMachine}}** düğmesine tıklayın.

![Makineler sayfası - "Makine Ekle" düğmesi](/assets/images/user-guide/23_machines_add.png)
*(Resim 23: Makineler yönetimi ana sayfası)*

3. Açılan formu doldurun:
   - **{{t:machines.machineName}}**: Benzersiz bir ad girin (ör: "sunucu-01")
   - **{{t:common.vaultEditor.fields.MACHINE.ip.label}}**: Makine IP adresini girin (ör: 192.168.111.11)
   - **{{t:common.vaultEditor.fields.MACHINE.datastore.label}}**: Depolama dizinini belirtin (ör: /mnt/rediacc)
   - **{{t:common.vaultEditor.fields.MACHINE.user.label}}**: SSH kullanıcı adını girin
   - **{{t:common.vaultEditor.fields.MACHINE.port.label}}**: Port numarasını girin (varsayılan: 22)
   - **{{t:common.vaultEditor.fields.MACHINE.ssh_password.label}}**: Parolayı girin (isteğe bağlı)

![Makine ekleme formu - tüm alanlar](/assets/images/user-guide/24_machine_create.png)
*(Resim 24: Yeni makine ekleme formu - makine adı, ağ ayarları, SSH kimlik bilgileri)*

4. **{{t:common.vaultEditor.testConnection.button}}** düğmesine tıklayarak bağlantıyı doğrulayın.
5. Test başarılı olduktan sonra **{{t:common.actions.create}}** düğmesine tıklayın.

> **İpucu**: "Otomatik olarak kurulumu makine oluşturduktan sonra başlat" seçeneği işaretlenirse, makine ek kurulum adımlarını otomatik gerçekleştirir.

![Makine oluşturma tamamlandı - görev takip penceresi](/assets/images/user-guide/25_machine_create_complete.png)
*(Resim 25: Makine başarıyla oluşturulduktan sonra görev takip penceresi)*

6. Aşamaları izleyin: **{{t:queue.trace.assigned}}** → **İşleniyor** → **{{t:queue.statusCompleted}}**
7. **{{t:common.actions.close}}** düğmesine tıklayarak işlemi sonlandırın.

> **İpucu**: "{{t:common.actions.refresh}}" düğmesine tıklayarak manuel olarak en son durumu kontrol edebilirsiniz.

### 2.4.2 Bağlantı Testi

![Connectivity test walkthrough](/assets/videos/user-guide/02-04-02-connectivity-test.webm)
*(Video: Running a connectivity test)*

Mevcut makinelerin bağlantı durumunu kontrol edebilirsiniz.

1. **{{t:machines.connectivityTest}}** düğmesine tıklayın.

![Bağlantı Testi düğmesi](/assets/images/user-guide/26_connectivity_test_button.png)
*(Resim 26: Makine işlem araç çubuğunda Bağlantı Testi düğmesi)*

2. Test edilecek makinelerin listelendiğini görün.
3. **{{t:machines.runTest}}** düğmesine tıklayın.
4. Başarılı sonuçlar yeşil renkte, başarısızlıklar kırmızı renkte gösterilir.

![Bağlantı testi formu - makine listesi](/assets/images/user-guide/27_connectivity_test_form.png)
*(Resim 27: Bağlantı testi formu - seçili makineler için ping fonksiyonu)*

> **İpucu**: Eğer test başarısız olursa, makine IP adresini ve SSH ayarlarını kontrol edin.

### 2.4.3 Makine Listesini Yenileme

![Machine list refresh walkthrough](/assets/videos/user-guide/02-04-03-machine-refresh.webm)
*(Video: Refreshing the machine list)*

Makine listesini güncellemek için **{{t:common.actions.refresh}}** düğmesine tıklayın.

![Yenile düğmesi](/assets/images/user-guide/28_refresh.png)
*(Resim 28: Makine işlem araç çubuğundaki Yenile düğmesi)*

### 2.4.4 Makine Detayları

![Machine details walkthrough](/assets/videos/user-guide/02-04-04-machine-details.webm)
*(Video: Viewing machine details)*

1. Detaylarını görmek istediğiniz makineyi seçin.
2. Göz simgesi düğmesine (**{{t:common.viewDetails}}**) tıklayın.

![Detayları Görüntüle düğmesi](/assets/images/user-guide/29_view_details_button.png)
*(Resim 29: Makine işlem sütununda göz simgesi)*

3. Sağ tarafta makine detayları paneli açılır:
   - **Ana Bilgisayar Adı**: Makinenin adı
   - **Çalışma Süresi**: Çalışma süresi
   - **{{t:queue.trace.operatingSystem}}**: İşletim sistemi ve sürümü
   - **{{t:queue.trace.kernelVersion}}**: Çekirdek sürümü
   - **İşlemci**: İşlemci bilgileri
   - **Sistem Saati**: Sistem saati

![Makine detay paneli - sistem bilgileri](/assets/images/user-guide/30_machine_view_details.png)
*(Resim 30: Makine detay paneli - ana bilgisayar adı, çalışma süresi, işletim sistemi, çekirdek, işlemci bilgileri)*

> **İpucu**: İşletim sistemi uyumluluğunu ve kaynak yeterliliğini kontrol etmek için bu bilgileri düzenli olarak inceleyin.

### 2.4.5 Makine Düzenleme

![Machine editing walkthrough](/assets/videos/user-guide/02-04-05-machine-edit.webm)
*(Video: Editing machine settings)*

1. Düzenlemek istediğiniz makineyi seçin.
2. Kalem simgesi düğmesine (**{{t:common.actions.edit}}**) tıklayın.

![Düzenle düğmesi](/assets/images/user-guide/31_edit_button.png)
*(Resim 31: Makine işlem sütununda kalem simgesi)*

3. Gerekli değişiklikleri yapın.
4. **{{t:common.vaultEditor.testConnection.button}}** düğmesine tıklayın.
5. Bağlantı başarılı olunca **{{t:common.save}}** düğmesine tıklayın.

![Makine düzenleme formu](/assets/images/user-guide/32_edit_form.png)
*(Resim 32: Makine düzenleme formu - makine adı, bölge ve kasa yapılandırması)*

> **İpucu**: Kritik ayarları değiştirdikten sonra "Bağlantıyı Test Et" her zaman çalıştırın.

### 2.4.6 Makine Takibi

![Machine trace walkthrough](/assets/videos/user-guide/02-04-06-machine-trace.webm)
*(Video: Viewing machine audit history)*

1. Makineyi seçin ve saat simgesi düğmesine (**{{t:common.actions.trace}}**) tıklayın.

![Takip düğmesi](/assets/images/user-guide/33_trace_button.png)
*(Resim 33: Makine işlem sütununda saat simgesi)*

2. Denetim geçmişi penceresinde işlemleri inceleyin:
   - **{{t:resources.audit.action}}**: Gerçekleştirilen işlem türü
   - **Detaylar**: Değiştirilen alanlar
   - **{{t:resources.audit.performedBy}}**: İşlemi gerçekleştiren kullanıcı
   - **Zaman Damgası**: Tarih ve saat

![Makine denetim geçmişi penceresi](/assets/images/user-guide/34_trace_list.png)
*(Resim 34: Denetim geçmişi - tüm değişikliklerin listesi)*

> **İpucu**: Değişiklikleri zaman sırasına göre görüntülemek için Timestamp sütununa tıklayın.

### 2.4.7 Makine Silme

![Machine deletion walkthrough](/assets/videos/user-guide/02-04-07-machine-delete.webm)
*(Video: Deleting a machine)*

1. Silmek istediğiniz makineyi seçin.
2. Çöp kutusu simgesi düğmesine (**{{t:common.delete}}**) tıklayın.

![Sil düğmesi](/assets/images/user-guide/35_delete_button.png)
*(Resim 35: Makine işlem sütununda çöp kutusu simgesi)*

3. Onay penceresinde **{{t:common.delete}}** düğmesine tıklayın.

![Makine silme onay penceresi](/assets/images/user-guide/36_delete_form.png)
*(Resim 36: "Makineyi silmek istediğinize emin misiniz?" onay penceresi)*

> **Dikkat**: Makine silindiğinde, üzerindeki tüm depo tanımlamaları da kaldırılır. Bu işlem geri alınamaz.

### 2.4.8 Uzaktan İşlemler

![Remote operations walkthrough](/assets/videos/user-guide/02-04-08-remote-hello.webm)
*(Video: Running remote operations on a machine)*

Makineler üzerinde uzaktan çeşitli işlemler gerçekleştirebilirsiniz.

1. Makineyi seçin ve **{{t:common.actions.remote}}** düğmesine tıklayın.
2. Açılır menüde seçenekleri görün:
   - **{{t:machines.runAction}}**: Makine üzerinde fonksiyon çalıştır
   - **{{t:common.vaultEditor.testConnection.button}}**: Makineye ping at

![Uzak menüsü - Sunucuda Çalıştır ve Bağlantıyı Test Et](/assets/images/user-guide/37_remote_button.png)
*(Resim 37: Uzak düğmesi - seçili makinede fonksiyon çalıştırma menüsü)*

> **İpucu**: Fonksiyonları çalıştırmadan önce makinenin erişilebilir olduğunu doğrulamak için "{{t:common.vaultEditor.testConnection.button}}" seçeneğini kullanın.

#### Kurulum

1. **{{t:machines.runAction}}** seçeneğini seçin.
2. **{{t:functions.availableFunctions}}** listesinde **Kurulum** fonksiyonunu bulun.
3. Fonksiyon adına tıklayarak seçin.

![Makine fonksiyonları listesi - kurulum fonksiyonu](/assets/images/user-guide/38_server_setup.png)
*(Resim 38: Kurulum fonksiyonu - makineyi gerekli araçlar ve konfigürasyonlarla hazırlar)*

> **İpucu**: Yeni bir makine kurulurken "Kurulum" fonksiyonunu ilk olarak çalıştırmanız önerilir.

#### Bağlantı Kontrolü (Merhaba)

1. **{{t:machines.runAction}}** > **Merhaba** fonksiyonunu seçin.
2. **{{t:common.actions.addToQueue}}** düğmesine tıklayın.

![Merhaba fonksiyonu seçimi](/assets/images/user-guide/39_remote_hello.png)
*(Resim 39: Merhaba fonksiyonu - basit test fonksiyonu, ana bilgisayar adını döndürür)*

3. Görev takip penceresinde sonuçları izleyin.
4. **{{t:queue.trace.responseConsole}}** bölümünde makinenin çıktısını görün.

![Merhaba fonksiyonu tamamlandı](/assets/images/user-guide/40_remote_hello_complete.png)
*(Resim 40: Merhaba fonksiyonu başarıyla tamamlandı - ana bilgisayar adı yanıtı)*

> **İpucu**: Hello fonksiyonu makine bağlantısını doğrulamak için ideal bir test fonksiyonudur.

#### Gelişmiş İşlemler

1. **{{t:common.actions.remote}}** > **{{t:machines.runAction}}** > **{{t:common.actions.advanced}}** yolunu izleyin.
2. Mevcut fonksiyonları görün: Kurulum, Hello, ping, ssh_test, uninstall
3. Gerekli fonksiyonu seçin ve **{{t:common.actions.addToQueue}}** düğmesine tıklayın.

![Gelişmiş fonksiyonlar listesi](/assets/images/user-guide/41_remote_advanced.png)
*(Resim 41: Advanced seçeneği - ileri seviye fonksiyonlar listesi)*

> **İpucu**: Advanced fonksiyonları kullanmadan önce makine kurulumunun tamamlandığından emin olun.

#### Hızlı Bağlantı Testi

![Uzak menüsü - Bağlantıyı Test Et](/assets/images/user-guide/42_connectivity_test.png)
*(Resim 42: Uzak menüsünden Bağlantıyı Test Et seçeneği)*

> **İpucu**: Makinede SSH veya ağ sorunları varsa, bu test ile sorunları hızlı bir şekilde belirleyebilirsiniz.

---

## 2.5 Depo Oluşturma ve İşlemleri

Depolar, yedekleme verilerinizin saklandığı temel birimlerdir.

### 2.5.1 Depo Oluşturma

![Repository creation walkthrough](/assets/videos/user-guide/02-05-01-repository-create.webm)
*(Video: Creating a new repository)*

1. **{{t:common.navigation.machines}}** sekmesinden bir makine seçin.
2. Sağ üst köşedeki **{{t:machines.createRepository}}** düğmesine tıklayın.

![Depo Oluştur düğmesi](/assets/images/user-guide/43_create_repo_add.png)
*(Resim 43: Makine deposu yönetimi ekranı - Depo Oluştur düğmesi)*

3. Formu doldurun:
   - **{{t:common.vaultEditor.fields.REPOSITORY.name.label}}**: Depo adını girin (örn., postgresql)
   - **{{t:resources.repositories.size}}**: Depo boyutunu girin (örn., 2GB)
   - **{{t:resources.repositories.repositoryGuid}}**: Otomatik oluşturulan kimlik bilgisini görüntüleyin
   - **{{t:resources.templates.selectTemplate}}**: Bir şablon seçin (örn., databases_postgresql)

![Depo oluşturma formu](/assets/images/user-guide/44_repo_form.png)
*(Resim 44: Depo oluşturma formu - depo adı, boyut ve şablon seçimi)*

4. **{{t:common.actions.create}}** düğmesine tıklayın.

> **İpucu**: Credential ID otomatik olarak oluşturulur, el ile değiştirilmemesi önerilir.

5. Görev takip penceresinde aşamaları izleyin: **{{t:queue.trace.assigned}}** → **İşleniyor** → **{{t:queue.statusCompleted}}**

![Depo oluşturma tamamlandı](/assets/images/user-guide/45_repo_complete.png)
*(Resim 45: Depo oluşturma işlemi kuyruğa alındı - görev izleme)*

6. **{{t:common.actions.close}}** düğmesine tıklayın.

> **İpucu**: Görev tipik olarak 1-2 dakika içinde tamamlanır.

![Depo listesi](/assets/images/user-guide/46_repo_list.png)
*(Resim 46: Oluşturulan depo listede görünür)*

### 2.5.2 Depo Fork İşlemi

![Repository fork walkthrough](/assets/videos/user-guide/02-05-02-repository-fork.webm)
*(Video: Forking a repository)*

Mevcut bir depoyu kopyalayarak yeni bir depo oluşturabilirsiniz.

1. Kopyalamak istediğiniz depoyu seçin.
2. **fx** (fonksiyon) menüsünü tıklayın.
3. **fork** seçeneğini tıklayın.

![fx menüsü - fork seçeneği](/assets/images/user-guide/47_fork_button.png)
*(Resim 47: Sağ taraftaki fx menüsü - depo işlemleri)*

4. **{{t:functions.functions.fork.params.tag.label}}** alanına yeni bir etiket girin (örn., 2025-12-06-20-37-08).
5. **{{t:common.actions.addToQueue}}** düğmesine tıklayın.

![Fork yapılandırma formu](/assets/images/user-guide/48_fork_form.png)
*(Resim 48: Fork işleminde deponun yeni etiketini belirleyin)*

6. **{{t:queue.statusCompleted}}** mesajını bekleyin ve **{{t:common.actions.close}}** butonuna tıklayın.

![Fork tamamlandı](/assets/images/user-guide/49_repo_completed.png)
*(Resim 49: Fork işlemi başarıyla tamamlandı)*

> **İpucu**: Etiketi varsayılan tarih-saat formatında oluşturmak iyi bir pratiktir. Fork işlemi orijinal depoyu etkilemez.

### 2.5.3 Depo Başlatma (Up)

![Repository up walkthrough](/assets/videos/user-guide/02-05-03-repository-up.webm)
*(Video: Starting a repository)*

Depoyu aktif hale getirmek için:

1. Depoyu seçin ve **fx** > **up** yolunu izleyin.

![Başlatma (Up) işlemi](/assets/images/user-guide/50_repo_up.png)
*(Resim 50: fx menüsünden "up" seçeneği - depoyu başlatma)*

2. **{{t:queue.statusCompleted}}** mesajını bekleyin.

![Başlatma tamamlandı](/assets/images/user-guide/51_repo_up_complete.png)
*(Resim 51: Depo başlatma işlemi tamamlandı)*

> **İpucu**: "Up" işlemi deponun tanımlı Docker hizmetlerini başlatır.

### 2.5.4 Depo Durdurma (Down)

![Repository down walkthrough](/assets/videos/user-guide/02-05-04-repository-down.webm)
*(Video: Stopping a repository)*

Aktif bir depoyu durdurmak için:

1. Depoyu seçin ve **fx** > **down** yolunu izleyin.

![Durdurma (Down) işlemi](/assets/images/user-guide/52_down_button.png)
*(Resim 52: fx menüsünden "down" seçeneği - depoyu kapatma)*

2. **{{t:queue.statusCompleted}}** mesajını bekleyin.

![Durdurma tamamlandı](/assets/images/user-guide/53_down_completed.png)
*(Resim 53: Depo durdurma işlemi tamamlandı)*

> **İpucu**: "Down" işlemi depoyu güvenli bir şekilde kapatır. Veri kaybı olmaz, sadece hizmetler durdurulur.

### 2.5.5 Dağıtım (Deploy)

![Repository deploy walkthrough](/assets/videos/user-guide/02-05-05-repository-deploy.webm)
*(Video: Deploying a repository)*

Depoyu farklı bir konuma dağıtmak için:

1. Depoyu seçin ve **fx** > **deploy** yolunu izleyin.

![Dağıtım (Deploy) işlemi](/assets/images/user-guide/54_deploy_button.png)
*(Resim 54: fx menüsünden "deploy" seçeneği)*

2. **{{t:functions.functions.fork.params.tag.label}}** alanına dağıtılacak sürümü girin.
3. **{{t:functions.functions.backup_deploy.params.machines.label}}** alanında hedef makineleri seçin.
4. **{{t:functions.checkboxOptions.overrideExistingFile}}** seçeneğini işaretleyin (uygulanabilirse).
5. **{{t:common.actions.addToQueue}}** butonuna tıklayın.

![Dağıtım formu](/assets/images/user-guide/55_deploy_form.png)
*(Resim 55: Deploy işlemini yapılandırma - tag, hedef makineler ve seçenekler)*

6. **{{t:queue.statusCompleted}}** mesajını bekleyin.

![Dağıtım tamamlandı](/assets/images/user-guide/56_deploy_completed.png)
*(Resim 56: Depo dağıtma tamamlandı)*

> **İpucu**: Deploy işlemi tamamlandıktan sonra hedef makinelerde depoyu başlatmak için "up" komutu çalıştırabilirsiniz.

### 2.5.6 Yedekleme (Backup)

![Repository backup walkthrough](/assets/videos/user-guide/02-05-06-repository-backup.webm)
*(Video: Backing up a repository)*

Depoyu yedeklemek için:

1. Depoyu seçin ve **fx** > **backup** yolunu izleyin.

![Yedekleme (Backup) işlemi](/assets/images/user-guide/57_backup_button.png)
*(Resim 57: fx menüsünden "backup" seçeneği)*

2. Formu doldurun:
   - **{{t:functions.functions.fork.params.tag.label}}**: Açıklayıcı bir ad girin (örn., backup01012025)
   - **{{t:functions.functions.backup_create.params.storages.label}}**: Yedekleme konumunu seçin
   - **{{t:functions.checkboxOptions.overrideExistingFile}}**: Seçeneği etkinleştirin veya devre dışı bırakın
   - **{{t:functions.functions.backup_deploy.params.checkpoint.label}}**: Ayarı inceleyin

![Yedekleme formu](/assets/images/user-guide/58_backup_form.png)
*(Resim 58: Yedekleme yapılandırma formu - hedef, dosya adı ve seçenekler)*

3. **{{t:common.actions.addToQueue}}** düğmesine tıklayın.

> **İpucu**: Yedekleme etiketi için anlaşılır bir ad kullanın. Büyük depolar için kontrol noktası etkinleştirmeyi düşünün.

4. **{{t:queue.statusCompleted}}** mesajını bekleyin.

![Yedekleme tamamlandı](/assets/images/user-guide/59_backup_completed.png)
*(Resim 59: Yedekleme görevi başarıyla tamamlandı)*

> **İpucu**: Tamamlandı durumuna ulaşmadan önce sabrıyla bekleyin; büyük yedeklemeler birkaç dakika alabilir.

### 2.5.7 Şablon Uygulama

![Template application walkthrough](/assets/videos/user-guide/02-05-07-repository-templates.webm)
*(Video: Applying a template to a repository)*

Depoya yeni bir şablon uygulamak için:

1. Depoyu seçin ve **fx** > **{{t:resources.templates.selectTemplate}}** yolunu izleyin.

![Şablonlar işlemi](/assets/images/user-guide/60_templates_button.png)
*(Resim 60: fx menüsünden "Şablonlar" seçeneği)*

2. Arama kutusuna yazarak şablonları filtreleyin.
3. İstediğiniz şablonu tıklayarak seçin (seçili şablon kalın çerçeve ile vurgulanır).
4. **{{t:common.actions.addToQueue}}** düğmesine tıklayın.

![Şablon seçim formu](/assets/images/user-guide/61_templates_form.png)
*(Resim 61: Kullanılabilir şablonları arama ve seçme)*

> **İpucu**: Şablonları hızlı bulmak için arama kutusunu kullanın. Şablon özelliklerini öğrenmek için "{{t:common.viewDetails}}" kullanın.

5. **{{t:queue.statusCompleted}}** mesajını bekleyin.

![Şablon uygulandı](/assets/images/user-guide/62_templates_completed.png)
*(Resim 62: Şablon uygulaması başarıyla tamamlandı)*

### 2.5.8 Bağlantıyı Kesme (Unmount)

![Repository unmount walkthrough](/assets/videos/user-guide/02-05-08-repository-unmount.webm)
*(Video: Unmounting a repository)*

Depo bağlantısını kesmek için:

1. Depoyu seçin ve **fx** > **{{t:common.actions.advanced}}** > **{{t:resources.repositories.unmount}}** yolunu izleyin.

![Bağlantıyı Kes işlemi](/assets/images/user-guide/63_unmount_button.png)
*(Resim 63: İleri menüdeki "Bağlantıyı Kes" seçeneği)*

2. **{{t:queue.statusCompleted}}** mesajını bekleyin.

![Bağlantı kesildi](/assets/images/user-guide/64_unmount_completed.png)
*(Resim 64: Bağlantı kesme işlemi tamamlandı)*

> **İpucu**: Bağlantıyı kesmeden önce depo üzerinde etkin işlem olmadığından emin olun. Bağlantı kesme sonrasında depo erişilir olmaktan çıkar.

### 2.5.9 Genişletme (Expand)

![Repository expand walkthrough](/assets/videos/user-guide/02-05-09-repository-expand.webm)
*(Video: Expanding repository size)*

Depo boyutunu artırmak için:

1. Depoyu seçin ve **fx** > **{{t:common.actions.advanced}}** > **{{t:functions.functions.repository_expand.name}}** yolunu izleyin.

![Genişletme işlemi](/assets/images/user-guide/65_expand_button.png)
*(Resim 65: İleri menüdeki "Genişlet" seçeneği)*

2. **{{t:functions.functions.repository_expand.params.size.label}}** alanına istediğiniz boyutu girin.
3. Sağ taraftaki açılır menüden birim seçin (GB, TB).
4. **{{t:common.actions.addToQueue}}** düğmesine tıklayın.

![Genişletme formu](/assets/images/user-guide/66_expand_form.png)
*(Resim 66: Depo boyutunu artırmak için yeni boyut parametresi)*

> **İpucu**: Mevcut boyuttan küçük bir değer girmeyin. Depo genişletme sırasında hizmet kesilmez.

5. **{{t:queue.statusCompleted}}** mesajını bekleyin.

![Genişletme tamamlandı](/assets/images/user-guide/67_expand_completed.png)
*(Resim 67: Depo genişletme işlemi tamamlandı)*

### 2.5.10 Yeniden Adlandırma

![Repository rename walkthrough](/assets/videos/user-guide/02-05-10-repository-rename.webm)
*(Video: Renaming a repository)*

Depo adını değiştirmek için:

1. Depoyu seçin ve **fx** > **{{t:common.actions.rename}}** yolunu izleyin.

![Yeniden Adlandırma işlemi](/assets/images/user-guide/68_rename_button.png)
*(Resim 68: fx menüsünden "Yeniden Adlandır" seçeneği)*

2. Yeni depo adını yazın.
3. **{{t:common.save}}** düğmesine tıklayın.

![Yeniden Adlandırma formu](/assets/images/user-guide/69_rename_form.png)
*(Resim 69: Yeni depo adını girmek için diyalog)*

> **İpucu**: Depo adları, depo türünü ve amacını yansıtacak şekilde anlamlı olmalıdır. Özel karakterlerden kaçının.

### 2.5.11 Depo Silme

![Repository deletion walkthrough](/assets/videos/user-guide/02-05-11-repository-delete.webm)
*(Video: Deleting a repository)*

Depoyu kalıcı olarak silmek için:

1. Depoyu seçin ve **fx** > **{{t:resources.repositories.deleteRepository}}** yolunu izleyin.

![Depoyu Sil işlemi](/assets/images/user-guide/70_delete_repo_button.png)
*(Resim 70: fx menüsünden "Depoyu Sil" seçeneği - kırmızı)*

2. Onay penceresinde **{{t:common.delete}}** butonuna tıklayın.

> **Dikkat**: Depo silme işlemi geri alınamaz. Silmeden önce depo verilerinin yedeklenmiş olduğundan emin olun.

### 2.5.12 Depo Detayları

![Repository details walkthrough](/assets/videos/user-guide/02-05-12-repository-details.webm)
*(Video: Viewing repository details)*

Depo hakkında ayrıntılı bilgi almak için:

1. Depoyu seçin.
2. Göz simgesine (**{{t:common.viewDetails}}**) tıklayın.

![Detayları Görüntüle düğmesi](/assets/images/user-guide/71_repo_view_button.png)
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

![Depo detay paneli](/assets/images/user-guide/72_repo_details_view.png)
*(Resim 72: Seçilen depo hakkındaki kapsamlı bilgiler)*

> **İpucu**: Bu panelde gösterilen tüm bilgiler referans amaçlıdır. Depo işlemleri için fx menüsündeki seçenekleri kullanın.

---

## 2.6 Depo Bağlantı İşlemleri

Depolara farklı yöntemlerle bağlanabilirsiniz.

### 2.6.1 Masaüstü Uygulaması ile Bağlantı

![Desktop connection walkthrough](/assets/videos/user-guide/02-06-01-desktop-connection.webm)
*(Video: Connecting via desktop application)*

1. Depo satırında **{{t:resources.localActions.local}}** düğmesine tıklayın.

![Yerel bağlantı düğmesi](/assets/images/user-guide/73_repo_connection_local.png)
*(Resim 73: Depo satırında "Yerel" düğmesi - masaüstü uygulaması erişimi)*

2. Açılır menüden erişim yöntemini seçin:
   - **{{t:resources.localActions.openInDesktop}}**: Grafiksel arayüz ile erişim
   - **{{t:resources.localCommandBuilder.vscodeTab}}**: Kod editöründe aç
   - **{{t:common.terminal.terminal}}**: Komut satırı ile erişim
   - **{{t:resources.localActions.showCLICommands}}**: Komut satırı araçları

![Bağlantı seçenekleri menüsü](/assets/images/user-guide/74_repo_connection.png)
*(Resim 74: Depo bağlantısı menüsü - farklı erişim yolları)*

> **İpucu**: VS Code ile çalışıyorsanız, "{{t:resources.localCommandBuilder.vscodeTab}}" seçeneği en hızlı entegrasyonu sağlar.

3. Tarayıcı izin istediğinde **{{t:common.vscodeSelection.open}}** düğmesine tıklayın.

![Masaüstü uygulaması açma izni](/assets/images/user-guide/75_desktop_open_page.png)
*(Resim 75: Tarayıcı masaüstü uygulamasını açma izni istiyor)*

> **İpucu**: Masaüstü uygulamasını her açışta izin vermek istemiyorsanız, "Her zaman izin ver" seçeneğini işaretleyin.

---

## 2.7 Ayarlar

Ayarlar bölümünden profil ve sistem ayarlarınızı yönetebilirsiniz.

### 2.7.1 Parola Değiştirme

![Password change walkthrough](/assets/videos/user-guide/02-07-03-password-change.webm)
*(Video: Changing your password)*

1. Sol menüden **{{t:common.navigation.settings}}** > **{{t:common.navigation.settingsProfile}}** sekmesine gidin.

![Profil ayarları sayfası](/assets/images/user-guide/76_profiles_button.png)
*(Resim 76: Ayarlar → Profil sayfası - kişisel vault ayarları)*

2. **{{t:settings.personal.changePassword.submit}}** düğmesine tıklayın.

![Parola Değiştir düğmesi](/assets/images/user-guide/77_profiles_change_button.png)
*(Resim 77: Kişisel ayarlar bölümünde "Parola Değiştir" düğmesi)*

3. Yeni parolanızı girin. Parola gereksinimleri:
   - En az 8 karakter uzunluğunda
   - Büyük ve küçük harfler içermeli
   - En az bir sayı içermeli
   - En az bir özel karakter içermeli

4. **{{t:settings.personal.changePassword.confirmPasswordLabel}}** alanına aynı parolayı tekrar girin.
5. **{{t:settings.personal.changePassword.submit}}** düğmesine tıklayın.

![Parola değiştirme formu](/assets/images/user-guide/78_profiles_change_form.png)
*(Resim 78: Parola Değiştir formu - güvenlik gereksinimleri görünür)*

> **İpucu**: Güçlü bir parola oluştururken rastgele kombinasyonlar kullanın.

---

## 2.8 Depolama

Depolama bölümü, yedekleme verilerinizin saklanacağı fiziksel alanları yönetmenizi sağlar.

### 2.8.1 Depolama Ekleme

![Storage creation walkthrough](/assets/videos/user-guide/02-08-01-storage-create.webm)
*(Video: Adding a storage location)*

1. Sol menüden **{{t:common.navigation.storage}}** sekmesine gidin.
2. **{{t:resources.storage.createStorage}}** düğmesine tıklayın.

![Depolama Ekle düğmesi](/assets/images/user-guide/79_storage_add_button.png)
*(Resim 79: Depolama yönetim sayfası - "Depolama Ekle" düğmesi)*

3. Formu doldurun:
   - **{{t:common.vaultEditor.fields.STORAGE.name.label}}**: Açıklayıcı bir ad girin
   - **{{t:common.vaultEditor.fields.STORAGE.provider.label}}**: Seçin (örn., s3)
   - **{{t:common.vaultEditor.fields.STORAGE.description.label}}**: İsteğe bağlı açıklama ekleyin
   - **{{t:common.vaultEditor.fields.STORAGE.noVersioning.label}}**: İsteğe bağlı
   - **{{t:common.vaultEditor.fields.STORAGE.parameters.label}}**: rclone bayrakları (örn., --transfers 4)

![Depolama oluşturma formu](/assets/images/user-guide/80_storage_form.png)
*(Resim 80: Depolama Ekle formu - ad, sağlayıcı, açıklama ve parametreler)*

4. **{{t:common.actions.create}}** düğmesine tıklayın.

> **İpucu**: Ek Parametreler, depolama performansını optimize etmek için rclone bayraklarını kabul eder.

---

## 2.9 Kimlik Bilgileri

Kimlik bilgileri bölümü, depolarınızın erişim bilgilerini güvenli şekilde yönetmenizi sağlar.

### 2.9.1 Kimlik Bilgisi Düzenleme

![Credential editing walkthrough](/assets/videos/user-guide/02-09-01-credential-edit.webm)
*(Video: Editing credentials)*

1. Sol menüden **{{t:common.navigation.credentials}}** sekmesine gidin.
2. Düzenlemek istediğiniz kaydı seçin.
3. **{{t:common.actions.edit}}** düğmesine tıklayın.

![Kimlik Bilgileri listesi](/assets/images/user-guide/81_credentials.png)
*(Resim 81: Kimlik Bilgileri sayfası - depo adları, takımları ve yönetim düğmeleri)*

4. Gerekirse **{{t:common.vaultEditor.fields.REPOSITORY.name.label}}** alanını değiştirin.
5. **{{t:common.save}}** düğmesiyle kaydedin.

![Kimlik bilgisi düzenleme formu](/assets/images/user-guide/82_credentials_form.png)
*(Resim 82: Depo Adını Düzenle formu - vault yapılandırması alanları)*

> **İpucu**: Kimlik bilgileri şifrelenmiş halde depolanır ve sadece dağıtım sırasında decrypt edilir.

### 2.9.2 Kimlik Bilgisi Takibi

![Credential trace walkthrough](/assets/videos/user-guide/02-09-02-credential-trace.webm)
*(Video: Viewing credential audit history)*

1. Takip etmek istediğiniz kaydı seçin.
2. **{{t:common.actions.trace}}** düğmesine tıklayın.

![Takip düğmesi](/assets/images/user-guide/83_credentials_trace_button.png)
*(Resim 83: Kimlik Bilgileri tablosunda "Takip" düğmesi)*

3. Denetim geçmişini inceleyin.
4. **{{t:common.actions.export}}** düğmesinden formatı seçin: **{{t:common.exportCSV}}** veya **{{t:common.exportJSON}}**.

![Kimlik bilgisi denetim geçmişi](/assets/images/user-guide/84_credentials_list_export.png)
*(Resim 84: Kimlik Bilgileri listesi - Dışa Aktar seçenekleri)*

> **İpucu**: Takip özelliği, güvenlik denetim amaçları için kimlik bilgilerinin kullanım izini sağlar.

### 2.9.3 Kimlik Bilgisi Silme

![Credential deletion walkthrough](/assets/videos/user-guide/02-09-03-credential-delete.webm)
*(Video: Deleting a credential)*

1. Silmek istediğiniz kaydı seçin.
2. Kırmızı **{{t:common.delete}}** düğmesine tıklayın.

![Sil düğmesi](/assets/images/user-guide/85_credentials_delete.png)
*(Resim 85: Kimlik Bilgileri sayfasında kırmızı "Sil" düğmesi)*

3. Onay penceresinde **{{t:common.delete}}** düğmesine tıklayın.

![Silme onayı](/assets/images/user-guide/86_credentials_delete_confirm.png)
*(Resim 86: Silme onayı diyaloğu - işlem geri alınamaz uyarısı)*

> **Dikkat**: Silmeden önce, kimlik bilgisinin başka makinelerde veya işlemlerde kullanılmadığından emin olun. Kritik kimlik bilgilerini silmeden önce yedek kopyasının olduğundan emin olun.

---

## 2.10 Kuyruk

Kuyruk bölümü, sistemde bekleyen ve tamamlanan işlemleri takip etmenizi sağlar.

### 2.10.1 Kuyruk İşlemleri

![Queue operations walkthrough](/assets/videos/user-guide/02-10-01-queue-operations.webm)
*(Video: Managing queue operations)*

1. Sol menüden **{{t:common.navigation.queue}}** sekmesine tıklayın.

![Kuyruk sayfası](/assets/images/user-guide/87_queue_button.png)
*(Resim 87: Kuyruk sayfası - filtreleme seçenekleri ve durum sekmeleri)*

2. Kuyruk öğelerini filtrelemek için:
   - **{{t:queue.trace.team}}**, **{{t:queue.trace.machine}}**, **{{t:queue.trace.region}}** ve **{{t:queue.trace.bridge}}** filtrelerini kullanın
   - **{{t:system.audit.filters.dateRange}}** belirtin
   - **{{t:queue.filters.onlyStale}}** seçeneğini işaretleyin

3. Durum sekmelerinde ayrıntıları görüntüleyin:
   - **{{t:queue.statusActive}}**: İşlenmekte olan görevler
   - **{{t:queue.statusCompleted}}**: Başarıyla tamamlanan görevler
   - **{{t:queue.statusCancelled}}**: İptal edilen görevler
   - **{{t:queue.statusFailed}}**: Başarısız görevler

4. **{{t:common.actions.export}}** düğmesinden bir format seçin: **{{t:common.exportCSV}}** veya **{{t:common.exportJSON}}**.

![Kuyruk dışa aktarımı](/assets/images/user-guide/88_queue_export.png)
*(Resim 88: Kuyruk listesi - Dışa Aktar seçenekleri)*

> **İpucu**: "{{t:queue.filters.onlyStale}}" seçeneği uzun süredir işlenmekte olan görevleri bulmanıza yardımcı olur. Görev yürütme eğilimlerini analiz etmek için kuyruk geçmişini düzenli olarak dışa aktarın.

---

## 2.11 Denetim

Denetim bölümü, sistemde yapılan tüm işlemlerin kayıtlarını tutar.

### 2.11.1 Denetim Kayıtları

![Audit records walkthrough](/assets/videos/user-guide/02-11-01-audit-records.webm)
*(Video: Viewing system audit records)*

1. Sol menüden **{{t:common.navigation.audit}}** sekmesine tıklayın.

![Denetim listesi](/assets/images/user-guide/89_audit_list.png)
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

4. **{{t:common.actions.export}}** düğmesinden bir format seçin: **{{t:common.exportCSV}}** veya **{{t:common.exportJSON}}**.

![Denetim dışa aktarımı](/assets/images/user-guide/90_audit_export.png)
*(Resim 90: Denetim kaydı dışa aktarma - CSV ve JSON seçenekleri)*

> **İpucu**: Denetim kaydı, güvenlik ve uyumluluk amaçlarında tüm sistem aktivitesini izlemek için kritik önem taşır. Düzenli olarak denetim kaydını dışa aktarın ve güvenli bir konumda saklayın.

---

**© 2025 Rediacc Platformu – Tüm Hakları Saklıdır.**
