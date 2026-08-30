"""
Telegram Bot handlers and routing for Antigravity Bridge.
Manages conversations, streaming feedback, media handling, and admin controls.
"""

import asyncio

USER_LOCKS: dict[int, asyncio.Lock] = {}
import json
import logging
import os
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand,
    constants
)
from telegram.constants import ParseMode, ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

from config import settings
from database import db, get_codex_stats
from agy_client import agy_client, normalize_model_name
from formatter import (
    markdown_to_telegram_html,
    split_text_chunks,
    format_tool_status,
    format_cumulative_status_telegram,
    format_execution_stages_telegram,
    format_stats_footer,
    escape_html
)

logger = logging.getLogger(__name__)


# ---------------- Bot Commands Menu & Project Config ---------------- #

BOT_COMMANDS = [
    BotCommand("start", "Botu başlat ve oturum bilgilerini göster"),
    BotCommand("help", "Komutları ve kullanım bilgilerini göster"),
    BotCommand("projects", "Projeleri listele ve aktif projeyi seç"),
    BotCommand("newchat", "Yeni oturum başlat"),
    BotCommand("cancel", "Aktif işlemi iptal et"),
    BotCommand("status", "Hub ve oturum durumunu göster"),
    BotCommand("update", "Projeleri güncelle (git pull)"),
    BotCommand("restart", "Köprü servisini yeniden başlatır"),
    BotCommand("usage", "Kullanım ve token istatistikleri"),
    BotCommand("model", "Model seçimi"),
    BotCommand("effort", "Düşünme eforu ayarla"),
    BotCommand("workspace", "Çalışma dizinini görüntüle veya değiştir"),
    BotCommand("permissions", "Otonom araç izinlerini aç veya kapat"),
    BotCommand("history", "Son sohbet geçmişini göster"),
    BotCommand("daily", "Agentic OS günlük logları ve aktif konular özeti"),
    BotCommand("whitelist", "İzinli kullanıcıları yönet (admin)"),
]

PROJECTS_TO_UPDATE = [
    ("Agentic OS", "/root/Projects/agentic-os"),
    ("Agento CLI", "/root/Projects/agento-cli"),
    ("Antigravity Telegram Bridge", "/root/Projects/antigravity-telegram-bridge"),
]


async def check_pending_restart_notification(application: Application):
    """Check for pending restart notification, send message to user, and remove marker file."""
    restart_file = settings.PENDING_RESTART_FILE
    if not restart_file.exists():
        return

    try:
        content = restart_file.read_text(encoding="utf-8")
        data = json.loads(content)
        chat_id = data.get("chat_id")
        if chat_id:
            try:
                await application.bot.send_message(
                    chat_id=chat_id,
                    text="✅ <b>Sistem başarıyla yeniden başlatıldı ve köprü şu an aktif!</b>",
                    parse_mode=ParseMode.HTML
                )
                logger.info(f"Sent post-restart notification to chat_id={chat_id}")
            except Exception as send_err:
                logger.error(f"Failed to send post-restart notification to chat_id={chat_id}: {send_err}")
    except Exception as e:
        logger.error(f"Error reading pending restart file: {e}")
    finally:
        try:
            if restart_file.exists():
                restart_file.unlink()
                logger.info("Removed pending restart notification file.")
        except Exception as del_err:
            logger.error(f"Failed to remove pending restart file: {del_err}")


async def post_init(application: Application):
    """Post initialization hook to register bot commands menu with Telegram and notify pending restart."""
    try:
        await application.bot.set_my_commands(BOT_COMMANDS)
        logger.info("Telegram Bot commands menu registered successfully.")
    except Exception as e:
        logger.warning(f"Failed to register Telegram bot commands menu: {e}")

    await check_pending_restart_notification(application)


# ---------------- Security & Auth Decorator ---------------- #

def authorized_only(func):
    """Decorator to ensure only whitelisted users can use bot features."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if not user:
            return

        user_id = user.id
        is_allowed = await db.is_whitelisted(user_id)

        # Check if first user auto-whitelisting is triggered
        total_whitelisted = await db.count_whitelisted_users()
        if not is_allowed and total_whitelisted == 0 and settings.AUTO_WHITELIST_FIRST_USER:
            await db.add_whitelisted_user(
                user_id=user_id,
                username=user.username,
                full_name=user.full_name,
                role="admin"
            )
            is_allowed = True
            logger.info(f"Auto-whitelisted first user {user_id} (@{user.username}) as Admin.")

        if not is_allowed:
            logger.warning(f"Unauthorized access attempt from User ID: {user_id} (@{user.username})")
            if update.message:
                denied_msg = (
                    "⛔ <b>Yetkisiz Erişim</b>\n\n"
                    "Bu bot özel bir <b>Google Antigravity CLI</b> köprüsüdür.\n"
                    f"Telegram ID'niz: <code>{user_id}</code>\n\n"
                    "Lütfen sistem yöneticisinden erişim izni talep ediniz."
                )
                await update.message.reply_text(denied_msg, parse_mode=ParseMode.HTML)
            return

        return await func(update, context, *args, **kwargs)
    return wrapper


# ---------------- Command Handlers ---------------- #

@authorized_only
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    user = update.effective_user
    session = await db.get_session(user.id)
    is_admin = await db.is_admin(user.id)

    conv_id = session.get("conversation_id") or "Yeni Oturum (Henüz başlatılmadı)"
    model = normalize_model_name(session.get("model") or settings.DEFAULT_MODEL)
    effort = session.get("effort") or settings.DEFAULT_EFFORT
    workspace = session.get("workspace") or settings.DEFAULT_WORKSPACE

    welcome_text = (
        f"🤖 <b>Antigravity CLI Telegram Köprüsüne Hoş Geldiniz!</b>\n\n"
        f"Merhaba <b>{escape_html(user.first_name)}</b>,\n"
        f"Doğrudan bu sohbete yazacağınız tüm mesajlar sunucunuzdaki <b>Antigravity CLI (agy)</b> ortamına aktarılır "
        f"ve yapay zeka yanıtları anlık olarak size iletilir.\n\n"
        f"📋 <b>Aktif Oturum Bilgileri:</b>\n"
        f"• <b>Kullanıcı ID:</b> <code>{user.id}</code> {'(👑 Admin)' if is_admin else ''}\n"
        f"• <b>Model:</b> <code>{escape_html(model)}</code>\n"
        f"• <b>Düşünme Seviyesi:</b> <code>{escape_html(effort)}</code>\n"
        f"• <b>Çalışma Dizini:</b> <code>{escape_html(workspace)}</code>\n"
        f"• <b>Oturum ID:</b> <code>{escape_html(conv_id)}</code>\n\n"
        f"💡 <i>Hemen bir soru sorabilir, kod yazdırabilir veya komut verebilirsiniz.</i>"
    )

    keyboard = [
        [
            InlineKeyboardButton("🆕 Yeni Oturum", callback_data="cmd_new"),
            InlineKeyboardButton("📁 Projeler", callback_data="cmd_projects"),
        ],
        [
            InlineKeyboardButton("⚙️ Durum", callback_data="cmd_status"),
            InlineKeyboardButton("📊 Kullanım", callback_data="cmd_usage"),
        ],
        [
            InlineKeyboardButton("🧠 Model Seç", callback_data="cmd_models"),
            InlineKeyboardButton("🎯 Düşünme Seviyesi", callback_data="cmd_efforts"),
        ],
        [
            InlineKeyboardButton("🔄 Güncelle", callback_data="cmd_update"),
            InlineKeyboardButton("⚡ Yeniden Başlat", callback_data="cmd_restart"),
        ],
        [
            InlineKeyboardButton("📖 Yardım & Komutlar", callback_data="cmd_help")
        ]
    ]

    await update.message.reply_text(
        welcome_text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


@authorized_only
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    help_text = (
        "📚 <b>Antigravity Telegram Köprüsü Komut Kılavuzu</b>\n\n"
        "<b>Temel Komutlar:</b>\n"
        "• <code>/start</code> - Başlangıç ekranı ve oturum özeti\n"
        "• <code>/projects</code> - Projeleri listeler, seçilen projeye geçer ve yeni oturum açar\n"
        "• <code>/newchat</code>, <code>/new</code>, <code>/reset</code>, <code>/clear</code> - Mevcut sohbet bağlamını sıfırlar ve yeni oturum açar\n"
        "• <code>/status</code> - Aktif oturum, model, sunucu ve sistem kaynak durumu\n"
        "• <code>/usage</code> - Token, mesaj ve oturum kullanım istatistikleri (Antigravity & Codex)\n"
        "• <code>/update</code> - Yerel projeleri günceller (git pull --rebase)\n"
        "• <code>/restart</code> - Köprü servisini yeniden başlatır\n"
        "• <code>/stop</code>, <code>/cancel</code> - Çalışan Antigravity sürecini durdurur\n"
        "• <code>/model [isim]</code> - Kullanılan yapay zeka modelini görüntüler veya değiştirir\n"
        "• <code>/effort [low|medium|high]</code> - Düşünme / Akıl yürütme seviyesini ayarlar\n"
        "• <code>/workspace [yol]</code> - Antigravity çalışma dizinini görüntüler veya ayarlar\n"
        "• <code>/permissions [on|off]</code> - Otonom araç çalıştırma onayını açar/kapatır\n"
        "• <code>/history</code> - Son konuşma geçmişini listeler\n\n"
        "<b>Yönetici Komutları (Admin):</b>\n"
        "• <code>/whitelist list</code> - İzinli kullanıcıları listeler\n"
        "• <code>/whitelist add &lt;id&gt; [isim]</code> - Yeni kullanıcıya izin verir\n"
        "• <code>/whitelist remove &lt;id&gt;</code> - Kullanıcı iznini kaldırır\n\n"
        "📸 <b>Medya Desteği:</b>\n"
        "Fotoğraf, kod dosyası veya belge gönderdiğinizde otomatik olarak çalışma alanına kaydedilir ve agy'ye aktarılır."
    )
    if update.message:
        await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)
    elif update.callback_query:
        await update.callback_query.message.reply_text(help_text, parse_mode=ParseMode.HTML)


@authorized_only
async def new_session_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset conversation and start a new session."""
    user = update.effective_user
    await db.reset_session(user.id)
    msg = "🔄 <b>Sohbet oturumu sıfırlandı!</b>\nYeni bir Antigravity konuşması başlatıldı."
    if update.message:
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
    elif update.callback_query:
        await update.callback_query.answer("Oturum sıfırlandı!")
        await update.callback_query.message.reply_text(msg, parse_mode=ParseMode.HTML)


@authorized_only
async def update_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pull latest changes for all related projects via git pull --rebase."""
    target_msg = update.message or (update.callback_query.message if update.callback_query else None)
    if not target_msg:
        return

    status_msg = await target_msg.reply_text(
        "🔄 <b>Projeler güncelleniyor...</b>\n<i>Lütfen bekleyin (git pull --rebase)...</i>",
        parse_mode=ParseMode.HTML
    )

    results = []
    for name, path in PROJECTS_TO_UPDATE:
        if not os.path.exists(path):
            results.append(f"📁 <b>{escape_html(name)}:</b>\n❌ <i>Dizin bulunamadı ({escape_html(path)})</i>")
            continue

        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "pull", "--rebase",
                cwd=path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            out_str = stdout.decode("utf-8", errors="replace").strip()
            err_str = stderr.decode("utf-8", errors="replace").strip()

            if proc.returncode == 0:
                if "Already up to date." in out_str or ("Current branch" in out_str and "is up to date" in out_str):
                    status_line = "✅ <b>Güncel</b> (Değişiklik yok)"
                else:
                    first_lines = "\n".join(out_str.splitlines()[:4])
                    status_line = f"🚀 <b>Güncellendi!</b>\n<pre>{escape_html(first_lines)}</pre>"
            else:
                combined_err = err_str or out_str or f"Exit code {proc.returncode}"
                first_err = "\n".join(combined_err.splitlines()[:3])
                status_line = f"❌ <b>Hata:</b>\n<code>{escape_html(first_err)}</code>"

            results.append(f"📁 <b>{escape_html(name)}</b> (<code>{escape_html(os.path.basename(path))}</code>):\n{status_line}")
        except Exception as e:
            results.append(f"📁 <b>{escape_html(name)}:</b>\n❌ <b>Hata:</b> <code>{escape_html(str(e))}</code>")

    reply_text = "🔄 <b>Git Güncelleme Raporu:</b>\n\n" + "\n\n".join(results)
    await status_msg.edit_text(reply_text, parse_mode=ParseMode.HTML)


@authorized_only
async def restart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Prompt confirmation before restarting the antigravity-hub service."""
    active_count = agy_client.get_active_count()
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚠️ Evet, Zorla Yeniden Başlat", callback_data="restart_confirm"),
            InlineKeyboardButton("❌ İptal", callback_data="restart_cancel")
        ]
    ])

    msg_text = (
        f"⚠️ <b>Yeniden Başlatma Onayı</b>\n\n"
        f"Şu anda {active_count} aktif işlem devam ediyor. "
        f"Botu yeniden başlatmak tüm işlemleri kesecektir. Emin misiniz?"
    )

    target_msg = update.message or (update.callback_query.message if update.callback_query else None)
    if target_msg:
        await target_msg.reply_text(
            msg_text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )


@authorized_only
async def usage_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display Antigravity and Codex usage statistics."""
    stats = await db.get_usage_stats()
    codex_stats = get_codex_stats()

    lines = [
        "📊 <b>Antigravity & Codex Kullanım İstatistikleri</b>\n",
        "🤖 <b>Antigravity / Hub Köprüsü:</b>",
        f"• <b>Toplam Oturum:</b> <code>{stats['total_sessions']}</code>",
        f"• <b>Toplam Mesaj:</b> <code>{stats['total_messages']}</code> (👤 {stats['user_messages']} / 🤖 {stats['assistant_messages']})",
        f"• <b>Son 24 Saat Mesajı:</b> <code>{stats['messages_24h']}</code>",
        f"• <b>Tahmini Toplam Token:</b> <code>{stats['total_tokens_est']:,}</code>",
        f"• <b>Son 24 Saat Token:</b> <code>{stats['tokens_24h_est']:,}</code>",
        f"• <b>Ortalama Yanıt Süresi:</b> <code>{stats['avg_latency']}s</code> ({stats['recorded_latencies_count']} kayıt)",
        "",
        "🧬 <b>Codex Ortamı:</b>"
    ]

    if codex_stats.get("exists"):
        lines.extend([
            f"• <b>Dizin Boyutu:</b> <code>{codex_stats['total_size_mb']} MB</code> ({codex_stats['files_count']} dosya)",
            f"• <b>Toplam Log Kaydı:</b> <code>{codex_stats['logs_count']:,}</code>",
            f"• <b>Oturum (Thread) Sayısı:</b> <code>{codex_stats['threads_count']}</code>",
            f"• <b>Dizin Yolu:</b> <code>{escape_html(codex_stats['path'])}</code>"
        ])
    else:
        lines.append(f"• <i>Codex dizini ({escape_html(codex_stats['path'])}) bulunamadı.</i>")

    reply_text = "\n".join(lines)

    keyboard = [
        [
            InlineKeyboardButton("🔄 Yenile", callback_data="cmd_usage"),
            InlineKeyboardButton("⚙️ Durum", callback_data="cmd_status")
        ]
    ]

    if update.message:
        await update.message.reply_text(reply_text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    elif update.callback_query:
        await update.callback_query.message.reply_text(reply_text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))



@authorized_only
async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel currently running task."""
    user = update.effective_user
    cancelled = agy_client.cancel_task(user.id)
    if cancelled:
        await update.message.reply_text("🛑 <b>Çalışan görev iptal edildi.</b>", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text("ℹ️ Şu anda çalışan aktif bir görev bulunmuyor.", parse_mode=ParseMode.HTML)


@authorized_only
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display detailed status card."""
    user = update.effective_user
    session = await db.get_session(user.id)

    # Disk & System info
    total, used, free = shutil.disk_usage("/")
    free_gb = free // (2**30)
    total_gb = total // (2**30)

    conv_id = session.get("conversation_id") or "Yok (İlk mesajda oluşturulacak)"
    model = normalize_model_name(session.get("model") or settings.DEFAULT_MODEL)
    effort = session.get("effort") or settings.DEFAULT_EFFORT
    workspace = session.get("workspace") or settings.DEFAULT_WORKSPACE
    auto_approve = "Açık (Otonom)" if session.get("auto_approve") else "Kapalı"

    status_text = (
        "📊 <b>Antigravity Köprüsü Sistem Durumu</b>\n\n"
        f"👤 <b>Kullanıcı:</b> {escape_html(user.full_name)} (<code>{user.id}</code>)\n"
        f"🤖 <b>Aktif Model:</b> <code>{escape_html(model)}</code>\n"
        f"🧠 <b>Düşünme Seviyesi:</b> <code>{escape_html(effort)}</code>\n"
        f"📂 <b>Çalışma Alanı:</b> <code>{escape_html(workspace)}</code>\n"
        f"🛡 <b>Otonom Onay:</b> {auto_approve}\n"
        f"💬 <b>Aktif Oturum UUID:</b> <code>{escape_html(conv_id)}</code>\n"
        f"💾 <b>Sunucu Diski:</b> {free_gb} GB boş / {total_gb} GB toplam\n"
        f"⚡ <b>CLI Yolu:</b> <code>{escape_html(settings.AGY_BIN_PATH)}</code>"
    )

    keyboard = [
        [
            InlineKeyboardButton("🔄 Sıfırla", callback_data="cmd_new"),
            InlineKeyboardButton("🧠 Model Değiştir", callback_data="cmd_models"),
        ],
        [
            InlineKeyboardButton("⚡ Yeniden Başlat", callback_data="cmd_restart"),
        ]
    ]

    if update.message:
        await update.message.reply_text(status_text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    elif update.callback_query:
        await update.callback_query.message.reply_text(status_text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))


@authorized_only
async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View or switch model."""
    user = update.effective_user
    args = context.args

    if args:
        new_model = normalize_model_name(args[0].strip())
        await db.update_session(user.id, model=new_model)
        await update.message.reply_text(
            f"✅ <b>Model değiştirildi:</b> <code>{escape_html(new_model)}</code>",
            parse_mode=ParseMode.HTML
        )
        return

    # If no args, show interactive selector
    models = await agy_client.get_available_models()
    session = await db.get_session(user.id)
    current_model = normalize_model_name(session.get("model") or settings.DEFAULT_MODEL)

    keyboard = []
    for m in models:
        prefix = "✅ " if m == current_model else ""
        keyboard.append([InlineKeyboardButton(f"{prefix}{m}", callback_data=f"set_model:{m}")])

    text = f"🤖 <b>Kullanılabilir Modeller</b>\nŞu anki model: <code>{escape_html(current_model)}</code>\n\nAşağıdan seçim yapabilirsiniz:"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))


@authorized_only
async def effort_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View or switch reasoning effort."""
    user = update.effective_user
    args = context.args

    if args:
        new_effort = args[0].strip().lower()
        if new_effort not in ("low", "medium", "high"):
            await update.message.reply_text("❌ Geçersiz seviye. Seçenekler: <code>low</code>, <code>medium</code>, <code>high</code>", parse_mode=ParseMode.HTML)
            return
        await db.update_session(user.id, effort=new_effort)
        await update.message.reply_text(f"✅ <b>Düşünme seviyesi ayarlandı:</b> <code>{new_effort}</code>", parse_mode=ParseMode.HTML)
        return

    session = await db.get_session(user.id)
    current = session.get("effort", settings.DEFAULT_EFFORT)
    keyboard = [
        [
            InlineKeyboardButton(f"{'✅ ' if current == 'high' else ''}High (Derin Akıl Yürütme)", callback_data="set_effort:high"),
        ],
        [
            InlineKeyboardButton(f"{'✅ ' if current == 'medium' else ''}Medium (Dengeli)", callback_data="set_effort:medium"),
        ],
        [
            InlineKeyboardButton(f"{'✅ ' if current == 'low' else ''}Low (Hızlı)", callback_data="set_effort:low"),
        ]
    ]
    await update.message.reply_text("🎯 <b>Düşünme Seviyesi (Reasoning Effort) Seçin:</b>", parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))


def get_available_projects() -> List[Dict[str, str]]:
    """Scan PROJECTS_DIR for subdirectories and return a list of available projects."""
    projects_dir = Path(settings.PROJECTS_DIR)
    projects: List[Dict[str, str]] = []

    if projects_dir.exists() and projects_dir.is_dir():
        for item in sorted(projects_dir.iterdir()):
            if item.is_dir() and not item.name.startswith("."):
                display_name = item.name.replace("-", " ").replace("_", " ").title()
                projects.append({
                    "name": display_name,
                    "slug": item.name,
                    "path": str(item.resolve())
                })

    if not projects:
        for name, path in PROJECTS_TO_UPDATE:
            projects.append({
                "name": name,
                "slug": os.path.basename(path),
                "path": str(Path(path).resolve())
            })

    return projects


@authorized_only
async def projects_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List available projects and switch active workspace with session reset."""
    user = update.effective_user
    args = context.args if context else None
    projects = get_available_projects()
    session = await db.get_session(user.id)
    current_workspace = str(Path(session.get("workspace", settings.DEFAULT_WORKSPACE)).resolve())

    target_msg = update.message or (update.callback_query.message if update.callback_query else None)

    # If argument provided, switch workspace directly
    has_args = isinstance(args, (list, tuple)) and len(args) > 0 and isinstance(args[0], str)
    if has_args:
        query_str = args[0].strip().lower()
        matched = next(
            (p for p in projects if p["slug"].lower() == query_str or p["name"].lower() == query_str or query_str in p["path"].lower()),
            None
        )
        if matched:
            await db.update_session(user.id, workspace=matched["path"], conversation_id=None)
            msg = (
                f"📁 <b>Aktif Proje Değiştirildi!</b>\n\n"
                f"• <b>Proje:</b> <code>{escape_html(matched['name'])}</code>\n"
                f"• <b>Dizin:</b> <code>{escape_html(matched['path'])}</code>\n"
                f"• <b>Oturum:</b> Sıfırlandı (Yeni oturum hazır)\n\n"
                f"💡 <i>Artık bu proje üzerinde çalışmaya başlayabilirsiniz.</i>"
            )
            if target_msg:
                await target_msg.reply_text(msg, parse_mode=ParseMode.HTML)
            return
        else:
            err_msg = f"❌ <code>{escape_html(args[0])}</code> adında bir proje bulunamadı."
            if target_msg:
                await target_msg.reply_text(err_msg, parse_mode=ParseMode.HTML)
            return

    # Interactive inline keyboard for projects
    keyboard = []
    for p in projects:
        is_active = (current_workspace == str(Path(p["path"]).resolve()))
        prefix = "✅ " if is_active else "📁 "
        keyboard.append([
            InlineKeyboardButton(f"{prefix}{p['name']}", callback_data=f"select_project:{p['slug']}")
        ])

    text = (
        "📁 <b>Kullanılabilir Projeler</b>\n\n"
        f"Mevcut Çalışma Alanı: <code>{escape_html(current_workspace)}</code>\n\n"
        "Çalışmak istediğiniz projeyi seçin (Seçtiğinizde yeni oturum başlatılır):"
    )

    reply_markup = InlineKeyboardMarkup(keyboard)
    if target_msg:
        await target_msg.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)


@authorized_only
async def workspace_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View or set workspace directory."""
    user = update.effective_user
    args = context.args

    if args:
        target_dir = os.path.abspath(args[0].strip())
        if not os.path.isdir(target_dir):
            await update.message.reply_text(f"❌ Dizin bulunamadı: <code>{escape_html(target_dir)}</code>", parse_mode=ParseMode.HTML)
            return
        await db.update_session(user.id, workspace=target_dir)
        await update.message.reply_text(f"✅ <b>Çalışma dizini güncellendi:</b> <code>{escape_html(target_dir)}</code>", parse_mode=ParseMode.HTML)
        return

    session = await db.get_session(user.id)
    current_ws = session.get("workspace", settings.DEFAULT_WORKSPACE)
    await update.message.reply_text(
        f"📂 <b>Mevcut Çalışma Alanı:</b> <code>{escape_html(current_ws)}</code>\n\n"
        f"Değiştirmek için: <code>/workspace &lt;dizin_yolu&gt;</code>",
        parse_mode=ParseMode.HTML
    )


@authorized_only
async def permissions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle auto-approve permissions."""
    user = update.effective_user
    args = context.args

    session = await db.get_session(user.id)
    current = bool(session.get("auto_approve", 1))

    if args:
        val = args[0].lower() in ("on", "1", "true", "evet", "acik", "açık")
        await db.update_session(user.id, auto_approve=1 if val else 0)
        state_str = "Açık (Otonom Araç Çalıştırma)" if val else "Kapalı"
        await update.message.reply_text(f"🛡 <b>Otonom Onay:</b> {state_str}", parse_mode=ParseMode.HTML)
        return

    # Toggle
    new_val = not current
    await db.update_session(user.id, auto_approve=1 if new_val else 0)
    state_str = "Açık (Otonom Araç Çalıştırma)" if new_val else "Kapalı"
    await update.message.reply_text(f"🛡 <b>Otonom Onay durumu değiştirildi:</b> {state_str}", parse_mode=ParseMode.HTML)



@authorized_only
async def daily_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display Agentic OS daily log and active threads summary."""
    target_msg = update.message or (update.callback_query.message if update.callback_query else None)
    if not target_msg:
        return

    args = context.args if context else None
    target_date = args[0].strip() if (args and len(args) > 0) else None

    # Implement summary fetch logic
    base_path = Path("/root/Projects/agentic-os")
    daily_dir = base_path / "daily"
    threads_file = base_path / "companion" / "Threads.md"
    
    if not daily_dir.exists():
        summary_text = "❌ <b>Agentic OS dizini veya daily/ klasörü bulunamadı.</b>"
    else:
        selected_file = None
        log_date = target_date

        if target_date:
            candidate = daily_dir / f"{target_date}.md"
            if candidate.exists():
                selected_file = candidate
                log_date = target_date
        
        if not selected_file:
            from datetime import datetime, timezone
            today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            candidate = daily_dir / f"{today_str}.md"
            if candidate.exists():
                selected_file = candidate
                log_date = today_str
            else:
                md_files = sorted([f for f in daily_dir.glob("*.md") if f.name != ".gitkeep"], key=lambda x: x.name, reverse=True)
                if md_files:
                    selected_file = md_files[0]
                    log_date = selected_file.stem

        if not selected_file or not selected_file.exists():
            summary_text = "ℹ️ <b>Henüz bir günlük log kaydı bulunamadı.</b>"
        else:
            try:
                text_content = selected_file.read_text(encoding="utf-8").strip()
            except Exception as e:
                text_content = f"❌ <b>Log dosyası okunamadı:</b> {str(e)}"

            threads_summary = ""
            if threads_file.exists():
                try:
                    threads_content = threads_file.read_text(encoding="utf-8")
                    active_threads = []
                    for line in threads_content.splitlines():
                        if line.startswith("### Thread:"):
                            active_threads.append(line.replace("### Thread:", "• <b>").strip() + "</b>")
                        elif line.startswith("**Status:**") and active_threads:
                            status_part = line.split("|", 1)[0].replace("**Status:**", "").strip()
                            active_threads[-1] += f" ({escape_html(status_part)})"
                    if active_threads:
                        threads_summary = "\n\n🧵 <b>Aktif Konular (Threads):</b>\n" + "\n".join(active_threads[:5])
                except Exception:
                    pass

            from formatter import markdown_to_telegram_html
            formatted_html = markdown_to_telegram_html(text_content)
            if len(formatted_html) > 3000:
                formatted_html = formatted_html[:2900] + "\n\n<i>... (kalan kısım kırpıldı)</i>"

            summary_text = f"📅 <b>Agentic OS Günlük Özeti ({escape_html(log_date)})</b>\n\n{formatted_html}{threads_summary}"

    chunks = split_text_chunks(summary_text, max_chars=settings.MAX_TELEGRAM_MESSAGE_LEN)
    for i, chunk in enumerate(chunks):
        try:
            await target_msg.reply_text(chunk, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        except Exception:
            import re
            plain = re.sub(r"<[^>]+>", "", chunk)
            await target_msg.reply_text(plain, disable_web_page_preview=True)


@authorized_only
async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View recent message history."""
    user = update.effective_user
    history = await db.get_history(user.id, limit=6)
    if not history:
        await update.message.reply_text("📜 Henüz bir sohbet geçmişi kaydedilmemiş.", parse_mode=ParseMode.HTML)
        return

    lines = ["📜 <b>Son Sohbet Geçmişi:</b>\n"]
    for item in history:
        role_icon = "👤 <b>Siz:</b>" if item["role"] == "user" else "🤖 <b>Yaver AI:</b>"
        snippet = item["content"][:120].replace("\n", " ")
        if len(item["content"]) > 120:
            snippet += "..."
        lines.append(f"{role_icon} {escape_html(snippet)}")

    await update.message.reply_text("\n\n".join(lines), parse_mode=ParseMode.HTML)


@authorized_only
async def whitelist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin whitelist management."""
    user = update.effective_user
    if not await db.is_admin(user.id):
        await update.message.reply_text("⛔ Bu komutu sadece bot yöneticileri kullanabilir.", parse_mode=ParseMode.HTML)
        return

    args = context.args
    if not args or args[0] == "list":
        users = await db.get_whitelisted_users()
        msg_lines = ["📋 <b>İzinli Kullanıcılar:</b>\n"]
        for u in users:
            admin_badge = "👑 Admin" if u.get("role") == "admin" else "👤 Kullanıcı"
            name = u.get("full_name") or u.get("username") or "Bilinmiyor"
            msg_lines.append(f"• <code>{u['user_id']}</code> - {escape_html(name)} ({admin_badge})")
        await update.message.reply_text("\n".join(msg_lines), parse_mode=ParseMode.HTML)
        return

    action = args[0].lower()
    if action == "add" and len(args) >= 2:
        try:
            target_id = int(args[1])
            target_name = args[2] if len(args) > 2 else None
            await db.add_whitelisted_user(target_id, full_name=target_name, added_by=user.id)
            await update.message.reply_text(f"✅ Kullanıcı <code>{target_id}</code> izin listesine eklendi.", parse_mode=ParseMode.HTML)
        except ValueError:
            await update.message.reply_text("❌ Geçersiz kullanıcı ID'si.", parse_mode=ParseMode.HTML)
    elif action == "remove" and len(args) >= 2:
        try:
            target_id = int(args[1])
            await db.remove_whitelisted_user(target_id)
            await update.message.reply_text(f"🗑 Kullanıcı <code>{target_id}</code> listeden çıkarıldı.", parse_mode=ParseMode.HTML)
        except ValueError:
            await update.message.reply_text("❌ Geçersiz kullanıcı ID'si.", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(
            "ℹ️ <b>Kullanım:</b>\n"
            "• <code>/whitelist list</code>\n"
            "• <code>/whitelist add &lt;id&gt; [isim]</code>\n"
            "• <code>/whitelist remove &lt;id&gt;</code>",
            parse_mode=ParseMode.HTML
        )


# ---------------- Callback Queries ---------------- #

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle interactive inline keyboard clicks."""
    query = update.callback_query
    if not query:
        return
    await query.answer()

    user_id = query.from_user.id
    if not await db.is_whitelisted(user_id):
        await query.message.reply_text("⛔ Yetkiniz bulunmuyor.")
        return

    data = query.data or ""
    if data == "cmd_new":
        await db.reset_session(user_id)
        await query.edit_message_text("🔄 <b>Yeni oturum başlatıldı!</b>", parse_mode=ParseMode.HTML)
    elif data == "cmd_projects":
        await projects_command(update, context)
    elif data == "cmd_status":
        await status_command(update, context)
    elif data == "cmd_help":
        await help_command(update, context)
    elif data == "cmd_usage":
        await usage_command(update, context)
    elif data == "cmd_update":
        await update_command(update, context)
    elif data == "cmd_restart":
        await restart_command(update, context)
    elif data == "restart_confirm":
        chat_id = query.message.chat_id if query.message else user_id
        if chat_id:
            try:
                settings.PENDING_RESTART_FILE.parent.mkdir(parents=True, exist_ok=True)
                restart_data = {
                    "chat_id": chat_id,
                    "timestamp": time.time(),
                }
                settings.PENDING_RESTART_FILE.write_text(json.dumps(restart_data), encoding="utf-8")
                logger.info(f"Saved pending restart notification info for chat_id={chat_id}")
            except Exception as e:
                logger.error(f"Failed to save pending restart file: {e}")

        try:
            await query.edit_message_text(
                "🔄 <b>Köprü servisi yeniden başlatılıyor...</b>",
                parse_mode=ParseMode.HTML
            )
        except Exception as edit_err:
            logger.warning(f"Failed to edit message for restart confirmation: {edit_err}")

        uid = os.getuid() if hasattr(os, "getuid") else 0
        xdg_env = f"export XDG_RUNTIME_DIR=/run/user/{uid}; " if os.path.exists(f"/run/user/{uid}") else ""
        restart_cmd = f"sleep 1 && {xdg_env}(systemctl --user restart antigravity-hub.service || systemctl --user restart antigravity-telegram.service || systemctl restart antigravity-hub.service) &"
        os.system(restart_cmd)
    elif data == "restart_cancel":
        await query.edit_message_text(
            "❌ <b>Yeniden başlatma iptal edildi.</b>",
            parse_mode=ParseMode.HTML
        )
    elif data == "cmd_models":
        models = await agy_client.get_available_models()
        session = await db.get_session(user_id)
        current = normalize_model_name(session.get("model") or settings.DEFAULT_MODEL)
        kb = [[InlineKeyboardButton(f"{'✅ ' if m == current else ''}{m}", callback_data=f"set_model:{m}")] for m in models]
        await query.message.reply_text("🤖 <b>Model Seçin:</b>", parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb))
    elif data == "cmd_efforts":
        session = await db.get_session(user_id)
        current = session.get("effort", settings.DEFAULT_EFFORT)
        kb = [
            [InlineKeyboardButton(f"{'✅ ' if current == 'high' else ''}High (Derin Akıl Yürütme)", callback_data="set_effort:high")],
            [InlineKeyboardButton(f"{'✅ ' if current == 'medium' else ''}Medium (Dengeli)", callback_data="set_effort:medium")],
            [InlineKeyboardButton(f"{'✅ ' if current == 'low' else ''}Low (Hızlı)", callback_data="set_effort:low")]
        ]
        await query.message.reply_text("🎯 <b>Düşünme Seviyesi Seçin:</b>", parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(kb))
    elif data.startswith("set_model:"):
        model_name = normalize_model_name(data.split(":", 1)[1])
        await db.update_session(user_id, model=model_name)
        await query.edit_message_text(f"✅ <b>Model güncellendi:</b> <code>{escape_html(model_name)}</code>", parse_mode=ParseMode.HTML)
    elif data.startswith("set_effort:"):
        effort_name = data.split(":", 1)[1]
        await db.update_session(user_id, effort=effort_name)
        await query.edit_message_text(f"✅ <b>Düşünme seviyesi güncellendi:</b> <code>{escape_html(effort_name)}</code>", parse_mode=ParseMode.HTML)
    elif data.startswith("select_project:"):
        project_slug = data.split(":", 1)[1]
        projects = get_available_projects()
        selected = next((p for p in projects if p["slug"] == project_slug or p["path"] == project_slug), None)
        if selected:
            await db.update_session(user_id, workspace=selected["path"], conversation_id=None)
            reply_text = (
                f"📁 <b>Aktif Proje Değiştirildi!</b>\n\n"
                f"• <b>Proje:</b> <code>{escape_html(selected['name'])}</code>\n"
                f"• <b>Dizin:</b> <code>{escape_html(selected['path'])}</code>\n"
                f"• <b>Oturum:</b> Sıfırlandı (Yeni oturum hazır)\n\n"
                f"💡 <i>Artık bu proje üzerinde çalışmaya başlayabilirsiniz.</i>"
            )
            await query.edit_message_text(reply_text, parse_mode=ParseMode.HTML)
        else:
            await query.edit_message_text("❌ Seçilen proje bulunamadı.", parse_mode=ParseMode.HTML)


# ---------------- Message & Media Handler ---------------- #

async def send_typing_periodically(chat_id: int, bot, stop_event: asyncio.Event):
    """Send typing chat action every 4 seconds until stop_event is set."""
    while not stop_event.is_set():
        try:
            await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception:
            pass
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=4.0)
        except asyncio.TimeoutError:
            pass


class TelegramLiveUpdater:
    """
    Manages throttled live message editing for Telegram to provide instant feedback
    while respecting Telegram API rate limits (typically ~1 edit per second per chat).
    """
    def __init__(self, message_obj: Any, interval: float = 1.2):
        self.message_obj = message_obj
        self.interval = max(0.01, interval)
        self.last_edit_time = 0.0
        self.target_text = ""
        self.last_sent_text = ""
        self.pending_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self._closed = False

    async def update(self, text: str):
        """Update live status message with immediate first edit and throttled subsequent edits."""
        if self._closed or not text or text == self.last_sent_text:
            return

        self.target_text = text
        now = time.time()
        time_since_last = now - self.last_edit_time

        if time_since_last >= self.interval:
            # Can edit immediately
            if self.pending_task and not self.pending_task.done():
                self.pending_task.cancel()
                self.pending_task = None
            await self._apply_edit(text)
        else:
            # Throttled: schedule trailing update if not already scheduled
            if self.pending_task is None or self.pending_task.done():
                delay = max(0.05, self.interval - time_since_last)
                self.pending_task = asyncio.create_task(self._delayed_edit(delay))

    async def _delayed_edit(self, delay: float):
        try:
            await asyncio.sleep(delay)
            if not self._closed and self.target_text and self.target_text != self.last_sent_text:
                await self._apply_edit(self.target_text)
        except asyncio.CancelledError:
            pass

    async def _apply_edit(self, text: str):
        async with self._lock:
            if self._closed or not text or text == self.last_sent_text:
                return
            try:
                await self.message_obj.edit_text(text, parse_mode=ParseMode.HTML)
                self.last_sent_text = text
                self.last_edit_time = time.time()
            except Exception as e:
                err_str = str(e).lower()
                if "not modified" in err_str:
                    self.last_sent_text = text
                elif "can't parse entities" in err_str or "unsupported start tag" in err_str:
                    try:
                        plain_text = re.sub(r"<[^>]+>", "", text)
                        await self.message_obj.edit_text(plain_text)
                        self.last_sent_text = text
                        self.last_edit_time = time.time()
                    except Exception:
                        pass
                else:
                    logger.debug(f"Live status edit failed/skipped: {e}")

    async def close(self):
        """Close updater and cancel any pending timers."""
        self._closed = True
        if self.pending_task and not self.pending_task.done():
            self.pending_task.cancel()
            self.pending_task = None


@authorized_only
async def handle_incoming_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text, photos, and document messages from authorized users."""
    message = update.message
    if not message:
        return

    user = update.effective_user
    chat_id = message.chat_id
    user_id = user.id

    # 1. Check for direct plain text command shortcuts before acquiring user lock
    if message.text and not (message.photo or message.document or message.voice or message.audio):
        raw_cmd = message.text.strip().lower()
        if raw_cmd in ("restart", "reboot", "reload", "yeniden başlat", "yeniden baslat", "/restart", "/reboot", "/reload"):
            await restart_command(update, context)
            return
        elif raw_cmd in ("status", "durum", "/status", "/durum"):
            await status_command(update, context)
            return
        elif raw_cmd in ("help", "yardim", "yardım", "/help", "/yardim", "/yardım"):
            await help_command(update, context)
            return
        elif raw_cmd in ("projects", "project", "projeler", "proje", "/projects", "/project"):
            await projects_command(update, context)
            return
        elif raw_cmd in ("update", "guncelle", "güncelle", "/update", "/guncelle", "/güncelle"):
            await update_command(update, context)
            return
        elif raw_cmd in ("reset", "clear", "new", "yeni", "newchat", "/reset", "/clear", "/new", "/newchat"):
            await new_session_command(update, context)
            return
        elif raw_cmd in ("usage", "istatistik", "stats", "/usage", "/istatistik", "/stats"):
            await usage_command(update, context)
            return

    # 2. Implement User Queue with Lock
    user_lock = USER_LOCKS.setdefault(user_id, asyncio.Lock())
    if user_lock.locked():
        await message.reply_text(
            "⏳ <b>Mesajınız kuyruğa alındı, aktif işlem bitince işlenecek.</b>",
            parse_mode=ParseMode.HTML
        )
    
    async with user_lock:

        # 3. Extract prompt and handle attachments
        prompt_text = message.text or message.caption or ""
        attachment_paths = []
        ts = int(time.time())

        # Handle Photo
        if message.photo:
            photo = message.photo[-1]
            file_obj = await photo.get_file()
            dest_file = settings.TEMP_MEDIA_DIR / f"photo_{user_id}_{ts}_{file_obj.file_unique_id}.jpg"
            await file_obj.download_to_drive(dest_file)
            attachment_paths.append(str(dest_file.resolve()))
            logger.info(f"Downloaded photo attachment to {dest_file}")

        # Handle Document
        if message.document:
            doc = message.document
            file_obj = await doc.get_file()
            filename = doc.file_name or f"doc_{file_obj.file_unique_id}"
            dest_file = settings.TEMP_MEDIA_DIR / f"{user_id}_{ts}_{filename}"
            await file_obj.download_to_drive(dest_file)
            attachment_paths.append(str(dest_file.resolve()))
            logger.info(f"Downloaded document attachment to {dest_file}")

        # Handle Voice
        if message.voice:
            voice = message.voice
            file_obj = await voice.get_file()
            dest_file = settings.TEMP_MEDIA_DIR / f"voice_{user_id}_{ts}_{file_obj.file_unique_id}.ogg"
            await file_obj.download_to_drive(dest_file)
            attachment_paths.append(str(dest_file.resolve()))
            logger.info(f"Downloaded voice attachment to {dest_file}")

        # Handle Audio
        if message.audio:
            audio = message.audio
            file_obj = await audio.get_file()
            filename = audio.file_name or f"audio_{file_obj.file_unique_id}.mp3"
            dest_file = settings.TEMP_MEDIA_DIR / f"audio_{user_id}_{ts}_{filename}"
            await file_obj.download_to_drive(dest_file)
            attachment_paths.append(str(dest_file.resolve()))
            logger.info(f"Downloaded audio attachment to {dest_file}")

        # Construct final prompt with attachment notes if present
        if attachment_paths:
            attachments_note = "\n".join(f"Ekli dosya/medya: {p}" for p in attachment_paths)
            if prompt_text:
                prompt_text = f"{prompt_text}\n\n{attachments_note}"
            else:
                prompt_text = attachments_note

            if not prompt_text:
                prompt_text = f"Please inspect the attached file(s):\n{attachments_note}"

        if not prompt_text.strip():
            await message.reply_text("ℹ️ Lütfen bir mesaj veya dosya gönderin.")
            return

        # 3. Get user session configuration
        session = await db.get_session(user_id)
        conversation_id = session.get("conversation_id")
        model = session.get("model") or settings.DEFAULT_MODEL
        effort = session.get("effort") or settings.DEFAULT_EFFORT
        workspace = session.get("workspace") or settings.DEFAULT_WORKSPACE
        auto_approve = bool(session.get("auto_approve", 1))

        # 4. Send initial progress message & start typing background task
        status_msg = await message.reply_text(
            "🧠 <i>Düşünülüyor ve hazırlanıyor...</i>",
            parse_mode=ParseMode.HTML
        )

        stop_typing = asyncio.Event()
        typing_task = asyncio.create_task(send_typing_periodically(chat_id, context.bot, stop_typing))

        live_updater = TelegramLiveUpdater(
            message_obj=status_msg,
            interval=settings.STREAM_EDIT_INTERVAL
        )
        live_updater.last_sent_text = "🧠 <i>Düşünülüyor ve hazırlanıyor...</i>"

        accumulated_response = ""
        final_result_data = None
        executed_tools: List[Dict[str, Any]] = []

        try:
            # 5. Stream response from Antigravity CLI
            async for event in agy_client.run_prompt_stream(
                user_id=user_id,
                prompt=prompt_text,
                conversation_id=conversation_id,
                workspace=workspace,
                model=model,
                effort=effort,
                auto_approve=auto_approve
            ):
                event_type = event.get("type")

                if event_type == "init":
                    new_conv_id = event.get("conversation_id")
                    if new_conv_id and new_conv_id != conversation_id:
                        conversation_id = new_conv_id
                        await db.update_session(user_id, conversation_id=new_conv_id)

                elif event_type == "step_update":
                    step_type = event.get("step_type")
                    tool_name = event.get("tool_name")
                    state = event.get("state", "running")
                    tool_info = event.get("tool_info", {})
                    duration = event.get("duration_seconds")

                    if tool_name:
                        # Match the most recent running tool with the same name and arguments
                        existing = next(
                            (t for t in reversed(executed_tools)
                             if t.get("tool_name") == tool_name
                             and t.get("tool_info") == tool_info
                             and t.get("state") in ("running", "active", "ACTIVE")),
                            None
                        )
                        if not existing:
                            existing = next(
                                (t for t in reversed(executed_tools)
                                 if t.get("tool_name") == tool_name
                                 and t.get("tool_info") == tool_info),
                                None
                            )

                        if existing:
                            existing["state"] = state
                            if duration is not None:
                                existing["duration_seconds"] = duration
                        else:
                            executed_tools.append({
                                "tool_name": tool_name,
                                "tool_info": tool_info,
                                "state": state,
                                "duration_seconds": duration
                            })

                        current_status = format_cumulative_status_telegram(executed_tools)
                        await live_updater.update(current_status)

                elif event_type == "result":
                    final_result_data = event
                    accumulated_response = event.get("response", "")
                    res_conv_id = event.get("conversation_id")
                    if res_conv_id:
                        conversation_id = res_conv_id
                        await db.update_session(user_id, conversation_id=res_conv_id)

                elif event_type == "error":
                    err_text = event.get("error", "Bilinmeyen hata")
                    accumulated_response = f"⚠️ <b>Hata:</b>\n<code>{escape_html(err_text)}</code>"

        except Exception as e:
            logger.exception(f"Error processing prompt for user {user_id}")
            accumulated_response = f"❌ <b>Bir hata oluştu:</b>\n<code>{escape_html(str(e))}</code>"
        finally:
            await live_updater.close()
            stop_typing.set()
            await typing_task

        # 6. Format and deliver the response
        if not accumulated_response.strip():
            accumulated_response = "<i>(Antigravity boş yanıt döndürdü)</i>"

        # Save to history with tool metadata, usage, and latency duration
        metadata_dict = {}
        if executed_tools:
            metadata_dict["tools"] = executed_tools
        if final_result_data:
            if "usage" in final_result_data and final_result_data["usage"]:
                metadata_dict["usage"] = final_result_data["usage"]
            if "duration_seconds" in final_result_data and final_result_data["duration_seconds"] is not None:
                metadata_dict["duration_seconds"] = final_result_data["duration_seconds"]

        metadata_str = json.dumps(metadata_dict) if metadata_dict else None
        await db.add_history(user_id, conversation_id, "user", prompt_text)
        await db.add_history(user_id, conversation_id, "assistant", accumulated_response, metadata=metadata_str)

        # 6a. Finalize the stages status message
        if executed_tools:
            stages_summary = format_execution_stages_telegram(executed_tools)
            if stages_summary:
                if len(stages_summary) > 3800:
                    stages_summary = stages_summary[:3750] + "\n... (kısaltıldı)"
                try:
                    await status_msg.edit_text(stages_summary, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
                except Exception as e:
                    logger.warning(f"Failed to edit status message with HTML stages: {e}")
                    try:
                        plain_stages = re.sub(r"<[^>]+>", "", stages_summary)
                        await status_msg.edit_text(plain_stages[:3800], disable_web_page_preview=True)
                    except Exception:
                        pass
        else:
            # If no tools were executed, delete the temporary 'Thinking...' progress message
            try:
                await status_msg.delete()
            except Exception:
                pass

        # 6b. Convert markdown to Telegram HTML for the final result text
        formatted_html = markdown_to_telegram_html(accumulated_response)

        # Add footer if stats are available
        if final_result_data:
            duration = final_result_data.get("duration_seconds", 0.0)
            usage = final_result_data.get("usage")
            footer = format_stats_footer(duration, usage)
            formatted_html += f"\n\n<blockquote>{escape_html(footer)}</blockquote>"

        # Split into message chunks safe for Telegram (<= 3800 chars)
        chunks = split_text_chunks(formatted_html, max_chars=settings.MAX_TELEGRAM_MESSAGE_LEN)

        # Send final result as a BRAND NEW message so it triggers a fresh notification & sound
        for chunk in chunks:
            try:
                await message.reply_text(chunk, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            except Exception as e:
                logger.warning(f"HTML reply failed for chunk, falling back to plain text: {e}")
                plain_chunk = re.sub(r"<[^>]+>", "", chunk) or chunk
                try:
                    await message.reply_text(plain_chunk, disable_web_page_preview=True)
                except Exception as fallback_err:
                    logger.error(f"Fallback plain text reply failed: {fallback_err}")


# ---------------- Application Setup ---------------- #

def build_application() -> Application:
    """Build and configure the Telegram Application."""
    settings.validate()

    application = (
        Application.builder()
        .token(settings.TELEGRAM_BOT_TOKEN)
        .concurrent_updates(True)
        .post_init(post_init)
        .build()
    )

    # Command handlers
    application.add_handler(CommandHandler(["start", "basla"], start_command))
    application.add_handler(CommandHandler(["help", "yardim"], help_command))
    application.add_handler(CommandHandler(["projects", "project", "projeler", "proje"], projects_command))
    application.add_handler(CommandHandler(["newchat", "new", "reset", "clear", "yeni", "sifirla"], new_session_command))
    application.add_handler(CommandHandler(["cancel", "stop", "dur", "iptal"], cancel_command))
    application.add_handler(CommandHandler(["status", "durum"], status_command))
    application.add_handler(CommandHandler(["update", "guncelle"], update_command))
    application.add_handler(CommandHandler(["restart", "reboot", "reload", "yenidenbaslat"], restart_command))
    application.add_handler(CommandHandler(["usage", "istatistik", "stats"], usage_command))
    application.add_handler(CommandHandler(["model", "models"], model_command))
    application.add_handler(CommandHandler(["effort", "efor"], effort_command))
    application.add_handler(CommandHandler(["workspace", "cwd", "dir", "dizin"], workspace_command))
    application.add_handler(CommandHandler(["permissions", "permission", "auto", "izin", "izinler"], permissions_command))
    application.add_handler(CommandHandler(["history", "gecmis"], history_command))
    application.add_handler(CommandHandler(["daily", "gunluk"], daily_command))
    application.add_handler(CommandHandler(["whitelist", "izinli"], whitelist_command))

    # Interactive UI callbacks
    application.add_handler(CallbackQueryHandler(callback_handler))

    # Message & Media handler
    application.add_handler(
        MessageHandler(
            (filters.TEXT | filters.PHOTO | filters.Document.ALL | filters.VOICE | filters.AUDIO) & ~filters.COMMAND,
            handle_incoming_message
        )
    )

    return application
