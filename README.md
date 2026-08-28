# Antigravity Hub Bridge

> Google Antigravity CLI (`agy`) için çoklu arayüzlü (WebUI & Telegram), gerçek zamanlı akış (streaming) ve otonom araç destekli merkezi köprü uygulaması.

---

## 🌟 Özellikler

- **Modern WebUI Dashboard:**
  - FastAPI & TailwindCSS ile hazırlanmış responsive, karanlık temalı tek sayfa arayüzü.
  - **Gerçek Zamanlı Akış (Streaming):** Server-Sent Events (SSE) ve WebSocket ile anlık kelime ve token akışı.
  - **Düşünme / Akıl Yürütme (Thinking):** Genişletilebilir düşünme katmanı ile modelin ara akıl yürütme sürecini izleme.
  - **Canlı Araç Yürütme Kartları (Tool Badges):** `run_command`, `write_to_file`, `view_file` gibi araçların çalışma süresi ve argümanlarının anlık gösterimi.
  - **Zengin Markdown & Kod Vurgulama:** Highlight.js ile renklendirilmiş kod blokları ve tek tıkla kopyalama butonu.
  - **Çoklu Model ve Effort Seçimi:** `gemini-3.7-flash-high`, `gemini-3.1-pro-high`, `claude-sonnet-4-6` modelleri ile `low/medium/high` düşünme seviyeleri.
  - **Çalışma Alanı (Workspace) Değiştirici:** Dinamik dizin seçimi ve otomatik oturum yönetimi.
  - **Dosya & Medya Yükleme:** Görsel veya kod dosyalarını yükleyerek prompta iliştirme.
  - **Sistem & İzin Paneli:** CPU, RAM ve Disk kullanım göstergeleri ile Telegram/Web beyaz liste (whitelist) yönetimi.
- **Telegram Bot Köprüsü:**
  - Telegram üzerinden `/start`, `/new`, `/model`, `/effort`, `/workspace`, `/status` komutları ve anlık mesaj akışı.
- **Bağımsız Servis Mimarisi (`.env`):**
  - `ENABLE_WEBUI=true` / `ENABLE_TELEGRAM=false` ile servisleri tek tek veya birlikte çalıştırma esnekliği.

---

## 🚀 Hızlı Başlangıç

### 1. Kurulum ve Ortam Hazırlığı

```bash
cd /root/Projects/antigravity-hub-bridge
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

### 2. Yapılandırma (`.env`)

`.env.example` dosyasını `.env` olarak kopyalayın ve ayarlarınızı yapın:

```ini
# Servisleri Aç/Kapat
ENABLE_WEBUI=true
ENABLE_TELEGRAM=false

# WebUI Ayarları
WEBUI_HOST=0.0.0.0
WEBUI_PORT=8000
WEBUI_TITLE=Antigravity Hub
WEBUI_AUTH_ENABLED=false
WEBUI_PASSWORD=

# Telegram Bot (Opsiyonel)
TELEGRAM_BOT_TOKEN=your_bot_token_here
ALLOWED_USER_IDS=
ADMIN_USER_IDS=

# Antigravity CLI Ayarları
AGY_BIN_PATH=/root/.local/bin/agy
DEFAULT_WORKSPACE=/root/Projects/agentic-os
DEFAULT_MODEL=gemini-3.7-flash-high
DEFAULT_EFFORT=high
AUTO_APPROVE_PERMISSIONS=true
```

### 3. Çalıştırma

```bash
# Doğrudan çalıştırma
./venv/bin/python3 main.py

# Veya systemd servisi ile arka planda çalıştırma
./systemd/service.sh start
./systemd/service.sh status
```

---

## 🧪 Testler

```bash
./venv/bin/pytest -v
```
