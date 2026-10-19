from telegram import Update
from telegram.ext import ContextTypes

from nepse_sense.config import settings


def is_authorized(user_id: int) -> bool:
    return user_id in settings.allowed_telegram_ids


async def authorization_filter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if update.effective_user is None:
        return False
    if not is_authorized(update.effective_user.id):
        from nepse_sense.logging import logger

        logger.info(
            f"Unauthorized attempt from user_id={update.effective_user.id} "
            f"username={update.effective_user.username}"
        )
        if update.message:
            await update.message.reply_text(
                "Unauthorized. Access denied. Your user ID has been logged."
            )
        return False
    return True
