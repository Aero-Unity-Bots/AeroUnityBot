import os
import uuid
import logging
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
import server

load_dotenv()
logging.basicConfig(level=logging.INFO)

API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WEB_SERVER_URL = os.getenv("WEB_SERVER_URL", "https://your-app.onrender.com")

bot = Client(
    "AeroUnityBotSession",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

@bot.on_message(filters.command("start"))
async def start_handler(client, message: Message):
    if len(message.command) > 1 and message.command[1].startswith("file_"):
        token = message.command[1].split("_")[1]
        file_data = server.FILE_DATABASE.get(token)
        if file_data and file_data.get("message"):
            # Forwards the exact original file back to the user
            await file_data["message"].copy(chat_id=message.chat.id)
            return
        else:
            await message.reply_text("❌ Sorry, this file link has expired or been revoked.")
            return

    await message.reply_text(
        "👋 **Welcome to Aero_Unity File-to-Link Bot!**\n\n"
        "Send me any file, video, or document (up to 4GB), and I will generate instant links!"
    )

@bot.on_message(filters.document | filters.video | filters.audio)
async def media_handler(client, message: Message):
    media = message.document or message.video or message.audio
    if not media:
        return

    file_name = getattr(media, "file_name", "media_file.mp4")
    file_size = getattr(media, "file_size", 0)
    file_size_formatted = f"{round(file_size / (1024 * 1024), 2)} MiB"

    token = uuid.uuid4().hex[:14]
    
    server.FILE_DATABASE[token] = {
        "message": message,
        "file_name": file_name,
        "file_size": file_size,
        "file_size_formatted": file_size_formatted
    }

    watch_url = f"{WEB_SERVER_URL}/watch/{token}"
    download_url = f"{WEB_SERVER_URL}/dl/{token}"
    share_url = f"https://t.me/{client.me.username}?start=file_{token}"

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("STREAM ↗", url=watch_url),
            InlineKeyboardButton("DOWNLOAD ↗", url=download_url)
        ],
        [
            InlineKeyboardButton("GET FILE ↗", url=share_url),
            InlineKeyboardButton("REVOKE FILE", callback_data=f"revoke_{token}")
        ],
        [
            InlineKeyboardButton("CLOSE", callback_data="close_msg")
        ]
    ])

    response_text = (
        f"📂 **Your Link Generated !**\n\n"
        f"📁 **FILE NAME :**\n`{file_name}`\n\n"
        f"📦 **FILE SIZE :** `{file_size_formatted}`\n\n"
        f"📥 **DOWNLOAD :** {download_url}\n\n"
        f"💻 **WATCH :** {watch_url}\n\n"
        f"🔗 **SHARE :** {share_url}"
    )

    await message.reply_text(response_text, reply_markup=keyboard, disable_web_page_preview=True)

@bot.on_callback_query(filters.regex("^close_msg$"))
async def close_callback(client, callback_query):
    await callback_query.message.delete()

@bot.on_callback_query(filters.regex("^revoke_"))
async def revoke_callback(client, callback_query):
    token = callback_query.data.split("_")[1]
    if token in server.FILE_DATABASE:
        del server.FILE_DATABASE[token]
    await callback_query.answer("File link has been revoked successfully!", show_alert=True)
    await callback_query.message.delete()

if __name__ == "__main__":
    bot.run()
