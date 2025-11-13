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
from utils.schemas import ClientMessage, NotificationMessage
from fastapi.middleware.cors import CORSMiddleware
from utils.db import (
    create_tables,
    save_session,
    get_session,
    get_pending_custom,
    update_session_state,
    delete_session,
)

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
SLASH_COMMAND_WEBHOOK_URL = os.getenv("SLASH_COMMAND_WEBHOOK_URL")

# Reuse a single Bot instance instead of creating a new application each time
bot = Bot(token=BOT_TOKEN)

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


async def clear_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear any pending custom message so the admin can handle new ones."""
    chat_id = update.effective_user.id
    session = await get_pending_custom(chat_id)
    if session:
        await delete_session(chat_id, session["message_id"])
        await update.message.reply_text("Pending message cleared. You can reply to a new one now.")
    else:
        await update.message.reply_text("No pending custom message to clear.")


ACCEPT_ACTION_MESSAGES = {
    "accept 1": "✅ Response 1 accepted and sent.",
    "accept 2": "✅ Response 2 accepted and sent.",
    "accept 3": "✅ Response 3 accepted and sent.",
    "accept_other": "✅ ✨ Other response accepted and sent.",
}


async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    message_id = query.message.message_id
    action = query.data

    pending = await get_pending_custom(chat_id)
    if pending and pending["message_id"] != message_id:
        await query.answer(
            "You already have a pending message. Use /clear to clear it before replying to something new.",
            show_alert=True,
        )
        return

    await query.answer()

    session = await get_session(chat_id, message_id)
    if not session:
        await query.edit_message_text("❌ No session found for this message.")
        return

    resume_url = session["resume_url"]

    if action in ACCEPT_ACTION_MESSAGES:
        updated_text = query.message.text + "\n\n" + ACCEPT_ACTION_MESSAGES[action]
        await query.edit_message_text(updated_text)
        await notify_n8n(user_id, decision=action, resume_url=resume_url)

    elif action == "reject":
        updated_text = query.message.text + "\n\n❌ AI response rejected. No reply will be sent."
        await query.edit_message_text(updated_text)
        await notify_n8n(user_id, decision="reject", resume_url=resume_url)

    elif action == "custom":
        updated_text = query.message.text + "\n\n📝 Please type your custom message now."
        await query.edit_message_text(updated_text)
        # Mark this session as awaiting a custom response from the admin.
        await update_session_state(
            chat_id,
            message_id,
            awaiting_custom=True,
        )

    # Cleanup
    if action != "custom":
        await delete_session(chat_id, message_id)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_user.id
    message = update.message.text

    session = await get_pending_custom(chat_id)
    if session:
        message_id = session["message_id"]
        resume_url = session["resume_url"]
        print(f"💬 Custom reply from {chat_id}: {message}")
        await update.message.reply_text("Thanks! Your message was sent.")
        await notify_n8n(chat_id, decision="custom", resume_url=resume_url, custom_reply=message)
        await delete_session(chat_id, message_id)
        return

    await update.message.reply_text("Please wait — we’ll send you messages here.")


async def forward_command_to_webhook(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    command_text = update.message.text or ""
    chat = update.effective_chat
    user = update.effective_user

    command_name, *rest = command_text.split(maxsplit=1)
    arguments = rest[0] if rest else ""

    payload = {
        "command": command_name,
        "arguments": arguments,
        "chat_id": chat.id if chat else None,
        "user": {
            "id": user.id if user else None,
            "username": user.username if user else None,
            "first_name": user.first_name if user else None,
            "last_name": user.last_name if user else None,
        },
    }

    if not SLASH_COMMAND_WEBHOOK_URL:
        await update.message.reply_text("No webhook configured for this command.")
        print("⚠️ SLASH_COMMAND_WEBHOOK_URL is not set. Command was not forwarded.")
        return

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(SLASH_COMMAND_WEBHOOK_URL, json=payload)
            response.raise_for_status()
        await update.message.reply_text("Command received. We'll get back to you soon.")
        print(f"✅ Forwarded command {command_name} to webhook")
    except httpx.HTTPError as exc:
        await update.message.reply_text("Failed to process this command. Please try again later.")
        print(f"❌ Failed to forward command {command_name}: {exc}")


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


# === FastAPI endpoint to trigger message ===
@app_api.post("/send-to-client")
async def send_to_client(data: ClientMessage):
    print(data)
    provider_buttons = [
        InlineKeyboardButton("1", callback_data="accept 1"),
        InlineKeyboardButton("2", callback_data="accept 2"),
        InlineKeyboardButton("3", callback_data="accept 3"),
        InlineKeyboardButton("✨ Other", callback_data="accept_other"),
    ]

    keyboard = [provider_buttons]

    keyboard.append([
        InlineKeyboardButton("❌ Reject", callback_data="reject"),
        InlineKeyboardButton("✍️ Custom", callback_data="custom"),
    ])

    reply_markup = InlineKeyboardMarkup(keyboard)

    full_text = (
        f"👤 {data.username}: {data.user_message}\n"
        f"🤖 AI replied: {data.ai_response}\n"
        f"------------------------------------\n"
        f"📞 Tel: {data.phone_number}\n"
        f"📱 Source: {data.source}"
    )

    msg = await bot.send_message(chat_id=data.chat_id, text=full_text, reply_markup=reply_markup)

    await save_session(
        data.chat_id,
        msg.message_id,
        data.resume_url,
        asyncio.get_running_loop().time(),
        awaiting_custom=False,
    )

    return {"status": "sent"}


@app_api.post("/send-notification")
async def send_notification(data: NotificationMessage):
    await send_telegram_message(data.chat_id, data.notification_message)
    return {"status": "sent"}



# === Run Telegram + FastAPI side-by-side ===
async def start_telegram_bot():
    bot_app = ApplicationBuilder().token(BOT_TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("clear", clear_pending))
    bot_app.add_handler(MessageHandler(filters.COMMAND, forward_command_to_webhook))
    bot_app.add_handler(CallbackQueryHandler(handle_button))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 Telegram bot running...")

    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling()
    # Updater.idle() was removed in python-telegram-bot v22.
    # Use an indefinitely waiting Event to keep the bot running.
    await asyncio.Event().wait()


def start_uvicorn():
    uvicorn.run(app_api, host="0.0.0.0", port=8000)


async def main():
    await create_tables()
    threading.Thread(target=start_uvicorn, daemon=True).start()
    await start_telegram_bot()


if __name__ == "__main__":
    asyncio.run(main())
