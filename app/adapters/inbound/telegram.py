"""Telegram channel (WhatsApp stand-in).

Production: Telegram POSTs updates to /telegram/webhook (see app.adapters.inbound.http).
Local: `python -m app.adapters.inbound.telegram` runs long polling, no public URL needed.
"""

from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from app.adapters.inbound.agent import reply
from app.config import get_settings

WEB_ONLY = (
    "Para khipear (transferir o pagar) entra al chat web: ahí confirmas con un botón. / "
    "Para khipear (transferir ou pagar), entre no chat web: lá você confirma com um botão."
)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    result = await reply(update.message.text, thread_id=f"telegram-{update.effective_chat.id}")
    # Khipear needs the Confirmar button, which only the web chat has: the proposal just expires.
    await update.message.reply_text(WEB_ONLY if result["confirmation"] else result["reply"])


def build_application() -> Application:
    app = Application.builder().token(get_settings().telegram_bot_token).updater(None).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    return app


if __name__ == "__main__":
    polling = Application.builder().token(get_settings().telegram_bot_token).build()
    polling.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    polling.run_polling()
