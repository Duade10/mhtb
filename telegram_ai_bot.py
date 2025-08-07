import os
import asyncio
import threading
from dotenv import load_dotenv
from fastapi import FastAPI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import (
    ApplicationBuilder, ContextTypes, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters
)
import httpx
import uvicorn
from utils.schemas import ClientMessage
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Reuse a single Bot instance instead of creating a new application each time
bot = Bot(token=BOT_TOKEN)

# === Memory stores ===
pending_custom_reply = {}     # { chat_id: { message_id: { resume_url, ... } } }

# === FastAPI app ===
app_api = FastAPI()

app_api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Or restrict to specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# === Telegram handlers ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text(f"Welcome! I’ll send you messages to accept or reject: {user_id}")
    print(f"✅ User started bot: {user_id}")


async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    message_id = query.message.message_id
    action = query.data

    if chat_id not in pending_custom_reply or message_id not in pending_custom_reply[chat_id]:
        await query.edit_message_text("❌ No session found for this message.")
        return

    session = pending_custom_reply[chat_id][message_id]
    resume_url = session["resume_url"]

    if action == "accept":
        updated_text = query.message.text + "\n\n✅ AI response accepted and sent."
        await query.edit_message_text(updated_text)
        await notify_n8n(user_id, decision="accept", resume_url=resume_url)

    elif action == "reject":
        updated_text = query.message.text + "\n\n❌ AI response rejected. No reply will be sent."
        await query.edit_message_text(updated_text)
        await notify_n8n(user_id, decision="reject", resume_url=resume_url)

    elif action == "custom":
        updated_text = query.message.text + "\n\n📝 Please type your custom message now."
        await query.edit_message_text(updated_text)
        session["awaiting_custom"] = True

    # Cleanup
    if action != "custom":
        del pending_custom_reply[chat_id][message_id]
        if not pending_custom_reply[chat_id]:
            del pending_custom_reply[chat_id]


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_user.id
    message = update.message.text

    if chat_id in pending_custom_reply:
        for message_id, session in list(pending_custom_reply[chat_id].items()):
            if session.get("awaiting_custom"):
                resume_url = session["resume_url"]
                print(f"💬 Custom reply from {chat_id}: {message}")
                await update.message.reply_text("Thanks! Your message was sent.")
                await notify_n8n(chat_id, decision="custom", resume_url=resume_url, custom_reply=message)
                del pending_custom_reply[chat_id][message_id]
                if not pending_custom_reply[chat_id]:
                    del pending_custom_reply[chat_id]
                return

    await update.message.reply_text("Please wait — we’ll send you messages here.")


# === Send message to user ===
async def send_telegram_message(chat_id, message, reply_markup=None):
    try:
        await bot.send_message(chat_id=chat_id, text=message, reply_markup=reply_markup)
    except Exception as e:
        print(f"❌ Telegram error: {e}")


# === Notify n8n webhook ===
async def notify_n8n(user_id, decision, resume_url, custom_reply=None):
    payload = {
        "user_id": user_id,
        "decision": decision,
        "custom_reply": custom_reply
    }
    try:
        async with httpx.AsyncClient() as client:
            await client.post(resume_url, json=payload)
        print("✅ Notified n8n")
    except Exception as e:
        print(f"❌ Failed to notify n8n: {e}")


# === Timeout handler ===
async def timeout_checker():
    while True:
        await asyncio.sleep(60)  # check every 60 seconds
        now = asyncio.get_running_loop().time()

        for chat_id, messages in list(pending_custom_reply.items()):
            for message_id, session in list(messages.items()):
                timestamp = session.get("timestamp")
                if timestamp and now - timestamp > 300:  # 5 minutes
                    print(f"⏱ Timeout for user {chat_id}")
                    await notify_n8n(chat_id, decision="timeout", resume_url=session["resume_url"])
                    del messages[message_id]
            if not messages:
                pending_custom_reply.pop(chat_id, None)


# === FastAPI endpoint to trigger message ===
@app_api.post("/send-to-client")
async def send_to_client(data: ClientMessage):
    print(data)
    keyboard = [
        [
            InlineKeyboardButton("✅ Accept", callback_data="accept"),
            InlineKeyboardButton("❌ Reject", callback_data="reject"),
            InlineKeyboardButton("📝 Custom Message", callback_data="custom")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    full_text = (
        f"👤 {data.username}: {data.user_message}\n"
        f"🤖 AI replied: {data.ai_response}\n"
        f"------------------------------------\n"
        f"📞 Tel: {data.phone_number}\n"
        f"📱 Source: {data.source}"
    )

    msg = await bot.send_message(chat_id=data.chat_id, text=full_text, reply_markup=reply_markup)

    if data.chat_id not in pending_custom_reply:
        pending_custom_reply[data.chat_id] = {}

    pending_custom_reply[data.chat_id][msg.message_id] = {
        "resume_url": data.resume_url,
        "original_text": full_text,
        "timestamp": asyncio.get_running_loop().time(),
        "awaiting_custom": False
    }

    return {"status": "sent"}



# === Run Telegram + FastAPI side-by-side ===
async def start_telegram_bot():
    bot_app = ApplicationBuilder().token(BOT_TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CallbackQueryHandler(handle_button))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 Telegram bot running...")
    await asyncio.gather(
        bot_app.run_polling(),
        timeout_checker()
    )


def start_uvicorn():
    uvicorn.run(app_api, host="0.0.0.0", port=8000)


def main():
    import nest_asyncio
    nest_asyncio.apply()
    threading.Thread(target=start_uvicorn, daemon=True).start()
    asyncio.run(start_telegram_bot())


if __name__ == "__main__":
    main()
