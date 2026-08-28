# Antigravity Hub Bridge - Sağlam & Odaklı Chat Sistemi Planı

> **Hedef:** Fazlalıklardan (file tree, terminal, onay modalı vb.) arındırılmış, yalnızca **kusursuz, hızlı, kararlı ve şeffaf bir Antigravity AI Sohbet Deneyimi**.

---

## 🎯 Temel Odak Noktaları

```
+-------------------------------------------------------------------------+
|                         ANTIGRAVITY CHAT HUB                            |
|                                                                         |
|  [ Gezinti & Geçmiş ]      [ Canlı Chat & Akış Akranı ]   [ Oturum ]    |
|  - Eski Sohbetler Listesi  - Anlık Token / Metin Akışı    - Model Seçimi|
|  - Oturum Değiştirme       - 🧠 Düşünme Katmanı (Thinking)- Effort       |
|  - Yeni Sohbet Açma        - ⚙️ Canlı Araç Kartları (Tools)- Workspace   |
|  - Sohbet Silme            - Zengin Markdown & Kod Kopyala- Dosya Ekle  |
|                            - Kesintisiz Geçmiş Geri Yükleme             |
+-------------------------------------------------------------------------+
```

---

## 🧱 1. Canlı Akış & Şeffaf Süreç Gösterimi (Live Streaming & Tool Cards)

- **Anlık Metin Akışı (SSE):** Modelin ürettiği kelimeler gecikmesiz, anında ekrana düşer.
- **🧠 Düşünme / Akıl Yürütme (Thinking Drawer):** Modelin arka planda ne düşündüğü, kaç saniye düşündüğü açılır/kapanır akordeon içinde şık bir şekilde akar.
- **⚙️ Canlı Araç Yürütme Kartları (Live Tool Badges):**
  - Model bir komut çalıştırdığında (`run_command: git status`), dosya okuduğunda (`view_file: config.py`) veya yazdığında (`write_to_file`) anlık dönen spinner ile kart ekrana düşer.
  - Araç bittiğinde geçen süre (`⏱️ 0.8s`) ve başarı durumu (`✅`) net şekilde gösterilir.
- **Zengin Markdown & Kod Blokları:** Syntax-highlighting, dil etiketi ve tek tıkla `Kopyala` butonu.
- **Görev Durdurma (Cancel/Stop):** Model uzun bir çıktı üretirken veya işlem yaparken tek tıkla `Durdur` butonuna basılarak `agy` süreci temiz bir şekilde sonlandırılır.

---

## 📜 2. Kusursuz Sohbet Geçmişi & Oturum Sürekliliği (Conversation History & Continuity)

- **Geçmiş Sohbetler Listesi:** Sol menüde / drawer'da her konuşmanın başlığı (ilk mesaj özeti), son aktivite zamanı ve ID'si listelenir.
- **Bağlamı Koruyarak Devam Etme:** Eski bir sohbete tıklandığında:
  - O oturumdaki tüm mesajlar, düşünme blokları ve araç kartları geçmişten eksiksiz geri yüklenir.
  - Yeni mesaj yazıldığında Antigravity `--conversation <id>` parametresiyle önceki sohbetin bağlamından devam eder.
- **Yeni Sohbet (`/new`):** Tek tıkla hafızayı sıfırlayıp temiz bir konuşma oturumu başlatır.
- **Sohbet Silme / Temizleme:** İstenmeyen eski konuşmaları tek tek veya topluca silebilme.

---

## ⚙️ 3. Pratik Oturum & Model Ayarları (Session Config)

- **Model Seçici:** `gemini-3.7-flash-high` (hızlı/önerilen), `gemini-3.1-pro-high` (derin analiz), `claude-sonnet-4-6` vb. arasında tek tıkla geçiş.
- **Düşünme Seviyesi (Effort):** `low`, `medium`, `high` butonları ile modelin ne kadar derin düşüneceğini anında ayarlama.
- **Çalışma Dizini (Workspace):** Antigravity'nin çalışacağı proje klasörünü belirleme (`/root/Projects/...`).
- **Dosya & Medya Ekleme:** Sürükle-bırak veya ataç ikonu ile görsel ve kod dosyası yükleyip prompta iliştirme.

---

## 🛡️ 4. Kaya Gibi Sağlam Altyapı & Dayanıklılık (Reliability & Robustness)

- **SQLite WAL Modu:** Eşzamanlı yazma/okuma kilitlemelerini önleyen sağlam veritabanı altyapısı.
- **Otomatik Şema Senkronizasyonu:** Tablo ve sütun güncellemelerinde sıfır hata ve otomatik migrasyon.
- **Token Tabanlı Magic Link Girişi:** Şifresiz, tek tıkla güvenli URL erişimi (`?token=...`).
- **Hafif & Hızlı:** Sıfır ağır bağımlılık; mobilde ve masaüstünde yağ gibi akan arayüz (`h-[100dvh]`).

---

## 🚀 Uygulama Adımları

1. **Adım 1:** Geçmiş konuşmaları yüklerken `thinking` bloklarını ve `tool` kartlarını geçmiş kayıtlarından da formatlı ve eksiksiz geri yükleme desteğini güçlendirmek.
2. **Adım 2:** Sol menüdeki konuşma listesine "Sohbeti Sil" (Delete chat) butonu ve arama/filtreleme eklemek.
3. **Adım 3:** Akış sırasında oluşabilecek olası ağ kopmalarında otomatik yeniden bağlanma (Auto-reconnect) ve UI hata yakalama katmanını mükemmelleştirmek.
4. **Adım 4:** Tüm akışları uçtan uca testlerle (%100 yeşil) doğrulamak ve servisi canlı tutmak.
