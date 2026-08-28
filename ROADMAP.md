# Antigravity Hub Bridge - Master Roadmap & Detaylı Geliştirme Planı

> **Sürüm:** 2.0 -> 3.0 Yol Haritası  
> **Hedef:** Antigravity CLI (`agy`) için bağımsız çalışan, çok kanallı (Web, Telegram, API), güvenli, görsel ve otonom bir AI Operasyon & Geliştirici Hub'ına dönüşüm.

---

## 🏗️ Faz 1: Çekirdek Motor, Etkileşim & Otonomi (Core & Interaction)

### 1.1. Çoklu Kullanıcı & Eşzamanlı İşlem Yöneticisi (Task Queue & Process Pool)
- **Hedef:** Birden fazla sekme, oturum veya Telegram kullanıcısının aynı anda bağımsız `agy` süreçleri koşturabilmesi.
- **Detaylar:**
  - Asenkron `TaskManager` ve Process Pool yapısı.
  - Arka planda çalışan uzun süreli görevlerin (`/goal`, büyük refactorler) web sekmesi kapansa dahi arka planda devam etmesi ve yeniden bağlanıldığında (`reconnect`) SSE akışına kaldığı yerden dahil olunması.
  - Süreç zaman aşımı (timeout), bellek limiti aşımı ve beklenmeyen çökmelerde otomatik kurtarma (`graceful recovery`).

### 1.2. İki Yönlü Onay Mekanizması (Human-in-the-Loop Approval)
- **Hedef:** `--dangerously-skip-permissions` dışında, kritik araçlar için kullanıcıdan web ve Telegram üzerinden anlık onay isteme.
- **Detaylar:**
  - `run_command`, `write_to_file`, `replace_file_content` çağrılarında "Onayla / Reddet / Düzenle" butonlu etkileşimli kart.
  - Telegram'da Inline Keyboard onay butonları (`✅ Onayla`, `❌ Reddet`).
  - WebUI üzerinde modal/banner ile canlı komut ve dosya diff önizlemesi.

### 1.3. Subagent Hiyerarşi Görselleştirmesi (Subagent Tree & Inspector)
- **Hedef:** Antigravity'nin çalıştırdığı alt ajanları (`invoke_subagent`) gerçek zamanlı takip etme.
- **Detaylar:**
  - Ana ajan ve türeyen subagent'ların (`self`, `research` vb.) durumunu, rolünü ve mesaj akışını gösteren canlı Tree Graph / Yan Sekme.
  - Her bir subagent'ın kendi iç log ve düşünme akışına tek tıkla odaklanabilme.

---

## 💻 Faz 2: Zengin Geliştirici Web Arayüzü (Advanced WebUI & IDE Tools)

### 2.1. Canlı Dosya Ağacı & Monaco Editor (Workspace Explorer)
- **Hedef:** Çalışma dizinindeki dosyaları arayüzden ayrılmadan inceleme ve düzenleme.
- **Detaylar:**
  - Sol/Sağ çekilebilir Dosya Ağacı (`Workspace File Tree`).
  - Monaco Editor (VSCode kalitesinde web editör) entegrasyonu ile kod görüntüleme ve anlık diff (`side-by-side diff view`).
  - Değiştirilen dosyaları yeşil/kırmızı gösterge ile takip etme.

### 2.2. Web Terminal / Shell Emülatörü (xterm.js)
- **Hedef:** Seçili workspace dizininde doğrudan bash komutları çalıştırabilme.
- **Detaylar:**
  - xterm.js + WebSocket tabanlı güvenli PTY web terminali.
  - AI ile aynı dizinde bağımsız terminal komutları (`git log`, `pytest`, `npm run build` vb.) koşturma.

### 2.3. Sesli Etkileşim & Voice Mode (Hands-free AI)
- **Hedef:** Tarayıcıdan ve mobilden sesli komut alıp sesli yanıt verebilme.
- **Detaylar:**
  - Web Speech API ve Whisper entegrasyonu ile Türkçe ses tanıma.
  - Yanıtların sesli sentezlenmesi (`Text-to-Speech`).

### 2.4. Prompt Şablonları & Slash Command Kütüphanesi
- **Hedef:** Sık kullanılan görevlerin tek tıkla tetiklenmesi.
- **Detaylar:**
  - `/plan`, `/goal`, `/review`, `/test`, `/fix-lint` butonları.
  - Özel prompt şablonu oluşturma, kaydetme ve çalışma alanına göre filtreleme.

---

## 📱 Faz 3: Çok Kanallı İletişim (Multi-Channel Expansion)

### 3.1. Telegram Gelişmiş Medya & Ses Entegrasyonu
- **Hedef:** Telegram'da tam multimedya desteği.
- **Detaylar:**
  - Sesli mesajları (Voice message) Whisper ile yazıya döküp `agy`ye iletme.
  - AI tarafından üretilen görselleri ve kod dosyalarını Telegram'da indirilebilir ek olarak gönderme.
  - Canlı ilerleme çubuğu ve etkileşimli buton menüleri.

### 3.2. Discord / Slack Bot Eklentisi (Opsiyonel)
- **Hedef:** Ekipler için Discord/Slack kanallarında Antigravity desteği.
- **Detaylar:**
  - `ENABLE_DISCORD=true` ve `ENABLE_SLACK=true` bayrakları.
  - Kanal içinde `@Antigravity` mention ile görev atama.

### 3.3. Webhook & CI/CD Entegrasyonu
- **Hedef:** GitHub / GitLab / Plesk olaylarında otomatik görev tetikleme.
- **Detaylar:**
  - `POST /api/webhooks/github` uç noktası (örneğin: yeni PR açıldığında otomatik kod incelemesi yaptırma).

---

## 🛡️ Faz 4: Güvenlik, Denetim & RBAC (Security & Governance)

### 4.1. Rol Tabanlı Yetkilendirme (RBAC)
- **Hedef:** Çok kullanıcılı güvenli ortam.
- **Detaylar:**
  - **Roller:** Admin (Tam yetki + Terminal + Ayarlar), Developer (Prompt + İzinli Dizinler), Viewer (Sadece Okuma).
  - Çalışma alanı bazlı yetki kısıtlaması (her kullanıcı sadece kendi projelerini görebilir).

### 4.2. Güvenlik Duvarı & Tehlikeli Komut Koruması
- **Hedef:** Yıkıcı operasyonların önlenmesi.
- **Detaylar:**
  - Kara listeli regex kuralları (`rm -rf /`, `mkfs`, `fdisk`, `drop database`).
  - Riskli komutlarda zorunlu 2FA veya çift onay eşiği.

### 4.3. Tam Denetim Kaydı & Audit Log (Audit Trail)
- **Hedef:** Yapılan tüm işlemlerin kanıtlı kaydı.
- **Detaylar:**
  - Verilen her prompt, tetiklenen her tool, üretilen her diff ve oturum süresinin SQLite / JSONL olarak kaydedilmesi.
  - Güvenlik olayları ve yetkisiz erişim denemelerinin loglanması.

---

## 🚀 Faz 5: DevOps, Ölçeklenme & Canlıya Alım (DevOps & Production)

### 5.1. Docker & Containerization
- **Hedef:** Tek komutla her sunucuda izole kurulum.
- **Detaylar:**
  - `Dockerfile` ve `docker-compose.yml` (WebUI + agy CLI + SQLite/Redis).
  - Port, volume ve ortam değişkeni izolasyonu.

### 5.2. Nginx Reverse Proxy & Otomatik SSL
- **Hedef:** Özel alan adı üzerinden HTTPS erişimi.
- **Detaylar:**
  - Nginx vhost konfigürasyonu (WebSocket, SSE ve chunked transfer desteği ile).
  - Certbot Let's Encrypt SSL kurulum şablonu.

### 5.3. Otomatik Yedekleme & Health Monitoring
- **Hedef:** Kesintisiz süreklilik.
- **Detaylar:**
  - SQLite WAL ve attachments dizininin periyodik otomatik yedeklenmesi (`cron` / script).
  - `/api/health` izleme ve servis çöktüğünde otomatik ayağa kaldırma (`systemd restart`).

---

## 📊 Faz Özeti & Uygulama Sırası

| Faz | Kapsam | Öncelik | Tahmini Efor |
|---|---|---|---|
| **Faz 1** | Çoklu Görev Kuyruğu + Human-in-the-Loop Onay + Subagent İzleme | 🔥 Çok Yüksek | 1-2 Gün |
| **Faz 2** | Dosya Ağacı & Monaco Editor + Web Terminal + Prompt Kütüphanesi | ⚡ Yüksek | 2-3 Gün |
| **Faz 3** | Telegram Ses/Medya + Webhook Trigger API | 🎯 Orta | 1-2 Gün |
| **Faz 4** | RBAC Yetkilendirme + Tehlikeli Komut Filtresi + Audit Log | 🛡️ Yüksek | 1-2 Gün |
| **Faz 5** | Docker Compose + Nginx/SSL + Otomatik Yedekleme | 🚀 Tamamlayıcı | 1 Gün |
