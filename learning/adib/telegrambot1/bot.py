import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext

TOKEN = "7840092563:AAE5GREtDI5rQj4IxWj9mlPG9lldY5vbJT0"

async def start(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text("Hello! I'm your bot. Send me a message, and I'll reply!")

async def echo(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text(f"You said: {update.message.text}")

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    print("Bot is running...")
    app.run_polling()

if __name__ == '__main__':
    main()
