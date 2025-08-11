# 🧠 MrHost.ai Telegram Bot

This is a FastAPI + Telegram bot integration built to support a human-in-the-loop review system for MrHost.ai. It allows a human admin to review AI-generated responses and approve, reject, or customize the reply before sending it to the customer.

---

## 🚀 Features

- Accepts messages from an AI automation system (e.g. n8n)
- Sends AI-generated replies to a Telegram admin for approval
- Supports three admin actions:
  - ✅ Accept (send as-is)
  - ❌ Reject (send nothing)
  - 📝 Custom (admin provides a replacement)
- Notifies n8n via a webhook with the admin’s decision
- Sessions remain active until the admin responds

---

## 📦 Tech Stack

- Python 3.10+
- [FastAPI](https://fastapi.tiangolo.com/)
- [python-telegram-bot](https://docs.python-telegram-bot.org/)
- [httpx](https://www.python-httpx.org/)
- [dotenv](https://pypi.org/project/python-dotenv/)

---

## 🔧 Environment Variables

Create a `.env` file with the following:

```env
BOT_TOKEN=your_telegram_bot_token
```

Get your token from @BotFather after creating a bot.

## ▶️ How to Run Locally
```bash
git clone https://github.com/yourusername/mrhost-bot.git
cd mrhost-bot

python -m venv env
source env/bin/activate   # or `env\\Scripts\\activate` on Windows

pip install -r requirements.txt

python telegram_ai_bot.py
```
