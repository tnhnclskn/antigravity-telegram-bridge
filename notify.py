import asyncio
import sys
from telegram import Bot
from config import settings


async def send_notification(message: str):
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    if not settings.ADMIN_USER_IDS:
        print("Error: ADMIN_USER_IDS is not set in .env")
        sys.exit(1)

    # Notify the first admin
    chat_id = settings.ADMIN_USER_IDS[0]
    await bot.send_message(chat_id=chat_id, text=message)
    print(f"Notification sent to {chat_id}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python notify.py 'Your message here'")
        sys.exit(1)

    message = " ".join(sys.argv[1:])
    asyncio.run(send_notification(message))
