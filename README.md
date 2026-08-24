# 🚀 Antigravity CLI Telegram Köprüsü (Bridge)

Antigravity CLI (`agy`) ortamınızı doğrudan **Telegram** üzerinden yönetmenizi, mesajlaşmanızı ve kod geliştirme süreçlerinizi uzaktan kontrol etmenizi sağlayan yüksek performanslı ve tam özellikli bir köprü (bridge) uygulamasıdır.

Linux `systemd --user` servisi olarak arka planda sürekli (daemon) çalışacak şekilde tasarlanmıştır.

---

## 🌟 Temel Özellikler

- 💬 **Tam İki Yönlü Köprü**: Telegram üzerinden yazdığınız her mesaj `agy` CLI oturumuna aktarılır, AI yanıtı (ve araç çalıştırma çıktıları) anında Telegram'a iletilir.
- 🧠 **Kesintisiz Sohbet Bağlamı (Session Continuity)**: Kullanıcı bazlı oturum yönetimi sayesinde Antigravity konuşma geçmişinizi (`--conversation <UUID>`) hatırlar.
- ⚡ **Canlı İlerleme ve Araç Durum Bildirimi (Live Streaming)**: Antigravity düşünürken veya araç çalıştırırken (örneğin komut çalıştırma `run_command`, dosya düzenleme `write_to_file`, arama `grep_search`) Telegram'da canlı durum bildirimi ve yazıyor (`typing`) animasyonu sunar.
- 🛡 **Güvenlik & Beyaz Liste (Whitelist)**: Sunucunuzu yetkisiz erişimlere karşı korumak için Telegram ID bazlı yetkilendirme sistemi içerir. İlk `/start` komutunu gönderen kişi otomatik olarak Admin yapılır (veya `.env` dosyasından ID tanımlanabilir).
- 📸 **Medya ve Dosya Desteği**: Telegram'dan gönderilen fotoğraflar, kaynak kod dosyaları ve belgeler otomatik olarak indirilip çalışma alanına eklenir ve Antigravity'ye aktarılır.
- 🔄 **Otonom Araç Çalıştırma (Permissions)**: Terminal onaylarına takılmadan araçların otonom çalışması için `--dangerously-skip-permissions` desteği (`/permissions on/off`).
- 🤖 **Dinamik Model ve Akıl Yürütme Seçimi**: `/model` komutu ile modeller (`gemini-3.7-flash-high`, `gemini-3.1-pro-high`, `claude-sonnet-4-6`, vb.) ve `/effort` komutu ile düşünme seviyesi anında değiştirilebilir.
- ✂️ **Akıllı Mesaj Bölücü (Smart HTML Chunker)**: Telegram'ın 4096 karakter sınırını aşan uzun kod veya analiz yanıtlarını kod bloklarını (`<pre><code>`) bozmadan akıllıca böler.
- ⚙️ **systemd --user Entegrasyonu**: Sunucu yeniden başlasa dahi kesintisiz çalışacak şekilde `systemctl --user` servisi ve yönetim betikleri hazırlandı.

---

## 📁 Proje Yapısı

```
/root/antigravity-telegram-bridge/
├── config.py             # Yapılandırma ve ortam değişkenleri yönetimi
├── database.py           # SQLite asenkron veritabanı (oturumlar, yetkiler, geçmiş)
├── agy_client.py         # agy CLI alt süreç (subprocess) ve JSON stream yöneticisi
├── formatter.py          # Telegram HTML biçimlendirici ve akıllı mesaj bölücü
├── telegram_bot.py       # Telegram bot komut, mesaj, medya ve callback yönlendiricileri
├── main.py               # Ana uygulama giriş noktası ve graceful shutdown
├── requirements.txt      # Python bağımlılıkları
├── pytest.ini            # Test yapılandırması
├── .env                  # Aktif ortam değişkenleri
├── .env.example          # Örnek ortam şablonu
├── data/
│   ├── bridge.db         # SQLite veritabanı
│   └── attachments/      # İndirilen medya ve dosya ekleri
├── systemd/
│   ├── antigravity-telegram.service  # systemd user servis dosyası
│   ├── install.sh                    # Tek tıkla kurulum ve servisi başlatma betiği
│   ├── uninstall.sh                  # Servisi kaldırma betiği
│   └── service.sh                    # status, start, stop, restart, logs kontrol yardımcısı
└── tests/
    ├── test_formatter.py # Biçimlendirici ve chunker testleri
    ├── test_database.py  # Veritabanı ve oturum testleri
    └── test_agy_client.py# agy istemci testleri
```

---

## 🚀 Hızlı Başlangıç

### 1. Kurulum ve Servisi Başlatma
Servisi kurmak ve `systemctl --user` üzerinde aktif hale getirmek için:

```bash
cd /root/antigravity-telegram-bridge
bash systemd/install.sh
```

Bu betik:
1. Python sanal ortamını (`venv`) oluşturur.
2. Gerekli tüm bağımlılıkları yükler.
3. `systemd/antigravity-telegram.service` dosyasını `~/.config/systemd/user/` altına yerleştirir.
4. SSH oturumu kapansa bile botun arka planda çalışmaya devam etmesi için `loginctl enable-linger` ayarını yapar.
5. Servisi `systemctl --user enable --now antigravity-telegram.service` ile başlatır.

---

## 🛠 Servis Yönetimi (`service.sh`)

Kolay yönetim için `systemd/service.sh` betiğini kullanabilirsiniz:

```bash
# Durumu kontrol etme
/root/antigravity-telegram-bridge/systemd/service.sh status

# Canlı logları izleme (Ctrl+C ile çıkılır)
/root/antigravity-telegram-bridge/systemd/service.sh logs

# Servisi yeniden başlatma
/root/antigravity-telegram-bridge/systemd/service.sh restart

# Servisi durdurma
/root/antigravity-telegram-bridge/systemd/service.sh stop

# Servisi başlatma
/root/antigravity-telegram-bridge/systemd/service.sh start
```

Doğrudan `systemctl` ile kullanmak isterseniz:
```bash
systemctl --user status antigravity-telegram.service
journalctl --user -u antigravity-telegram.service -f
```

---

## 📱 Telegram Komutları

| Komut | Açıklama |
| :--- | :--- |
| `/start` | Başlangıç menüsü, oturum özeti ve hızlı ayar butonları |
| `/new`, `/reset`, `/clear` | Mevcut sohbet bağlamını sıfırlar ve temiz bir oturum başlatır |
| `/status` | Aktif model, çalışma dizini, disk durumu ve oturum ID bilgileri |
| `/model [model_adi]` | Kullanılan modeli görüntüler veya değiştirir (Butonlu menü) |
| `/effort [low\|medium\|high]` | Akıl yürütme (reasoning) derinliğini ayarlar |
| `/workspace [dizin]` | Antigravity'nin çalışacağı dizini görüntüler/değiştirir |
| `/permissions [on\|off]` | Otonom araç çalıştırma onayını açar/kapatır |
| `/cancel`, `/stop` | O sırada yürütülen Antigravity görevini durdurur |
| `/history` | Son mesaj geçmişini listeler |
| `/whitelist list` | *(Admin)* İzinli kullanıcıları listeler |
| `/whitelist add <id>` | *(Admin)* Yeni bir Telegram ID'sine erişim izni verir |
| `/whitelist remove <id>` | *(Admin)* Bir kullanıcının erişim iznini kaldırır |
| `/help` | Komut kılavuzunu görüntüler |

---

## ⚙️ Yapılandırma (`.env`)

Ayar parametreleri `/root/antigravity-telegram-bridge/.env` dosyasında bulunur:

```ini
# Telegram Bot Token
TELEGRAM_BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN_HERE

# İzinli kullanıcı ID'leri (Boş bırakılırsa ilk /start atan kişi Admin olur)
ALLOWED_USER_IDS=
ADMIN_USER_IDS=
AUTO_WHITELIST_FIRST_USER=true

# Antigravity CLI yolu ve Varsayılan Dizin
AGY_BIN_PATH=/root/.local/bin/agy
DEFAULT_WORKSPACE=/root

# Varsayılan Model ve Düşünme Seviyesi
DEFAULT_MODEL=gemini-3.7-flash-high
DEFAULT_EFFORT=high

# Otonom Araç Çalıştırma
AUTO_APPROVE_PERMISSIONS=true

# Canlı Güncellemeler
STREAM_UPDATES=true
STREAM_EDIT_INTERVAL=1.5
LOG_LEVEL=INFO
```

---

## 🧪 Testleri Çalıştırma

Tüm birim (unit) testlerini çalıştırmak için:

```bash
cd /root/antigravity-telegram-bridge
venv/bin/pytest -v
```
