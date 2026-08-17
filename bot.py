import asyncio
import ipaddress
import logging
import os
import re
import socket
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes

import config

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
LOGGER = logging.getLogger("m3u8-record-bot")


def is_allowed(update: Update) -> bool:
    allowed = getattr(config, "ALLOWED_USER_IDS", set())
    return not allowed or (update.effective_user and update.effective_user.id in allowed)


def is_public_http_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False
        # Avoid accidentally using the bot as a localhost/private-network fetcher.
        addresses = socket.getaddrinfo(parsed.hostname, None)
        for item in addresses:
            addr = ipaddress.ip_address(item[4][0])
            if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
                return False
        return True
    except (ValueError, socket.gaierror):
        return False


async def resolve_input_url(url: str) -> str:
    """Resolve a regular remote .m3u playlist to its first non-comment entry.
    HLS .m3u8 URLs are passed directly to ffmpeg because they are live playlists.
    """
    if not url.lower().split("?", 1)[0].endswith(".m3u"):
        return url

    timeout = aiohttp.ClientTimeout(total=20)
    headers = {"User-Agent": "Mozilla/5.0 m3u8-record-bot"}
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        async with session.get(url) as response:
            response.raise_for_status()
            text = await response.text(errors="ignore")

    base = url.rsplit("/", 1)[0] + "/"
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("http://") or line.startswith("https://"):
            candidate = line
        else:
            from urllib.parse import urljoin
            candidate = urljoin(base, line)
        if is_public_http_url(candidate):
            return candidate
    raise ValueError("The M3U playlist did not contain a usable public HTTP(S) stream URL.")


async def run_ffmpeg(source: str, output: Path, seconds: int) -> None:
    command = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", source,
        "-t", str(seconds),
        "-map", "0:v:0?", "-map", "0:a:0?",
        "-c", "copy",
        "-movflags", "+faststart",
        str(output),
    ]
    LOGGER.info("Starting recording: %s seconds", seconds)
    process = await asyncio.create_subprocess_exec(
        *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=seconds + config.FFMPEG_TIMEOUT_BUFFER_SECONDS,
        )
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        raise RuntimeError("Recording timed out before ffmpeg completed.")
    if process.returncode != 0:
        details = stderr.decode("utf-8", errors="replace")[-1200:]
        raise RuntimeError(f"ffmpeg could not record this stream. {details}")
    if not output.exists() or output.stat().st_size == 0:
        raise RuntimeError("No video data was received from the stream.")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return
    await update.message.reply_text(
        "ব্যবহার: /record <minutes> <m3u8_or_m3u_url>\n"
        "উদাহরণ: /record 5 https://example.com/live.m3u8\n\n"
        f"সর্বোচ্চ সময়: {config.MAX_MINUTES} মিনিট।"
    )


async def record(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        await update.message.reply_text("আপনার এই bot ব্যবহারের অনুমতি নেই।")
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "সঠিক ফরম্যাট:\n/record <minutes> <m3u8_or_m3u_url>"
        )
        return

    try:
        minutes = int(context.args[0])
        source_url = context.args[1].strip()
    except ValueError:
        await update.message.reply_text("Minutes অবশ্যই পূর্ণসংখ্যা হতে হবে।")
        return

    if minutes < 1 or minutes > config.MAX_MINUTES:
        await update.message.reply_text(
            f"Minutes 1 থেকে {config.MAX_MINUTES}-এর মধ্যে দিন।"
        )
        return
    if not is_public_http_url(source_url):
        await update.message.reply_text("শুধু public HTTP/HTTPS stream URL ব্যবহার করুন।")
        return

    status = await update.message.reply_text(
        f"রেকর্ডিং শুরু হচ্ছে ({minutes} মিনিট)। Bot চালু রাখুন..."
    )
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.RECORD_VIDEO)

    work_dir = Path(tempfile.mkdtemp(prefix="m3u8_record_"))
    output = work_dir / "recording.mp4"
    try:
        resolved_url = await resolve_input_url(source_url)
        await run_ffmpeg(resolved_url, output, minutes * 60)
        size_mb = output.stat().st_size / (1024 * 1024)
        if size_mb > config.MAX_UPLOAD_MB:
            raise RuntimeError(
                f"ভিডিওর আকার {size_mb:.1f} MB হয়েছে; configured maximum "
                f"{config.MAX_UPLOAD_MB} MB অতিক্রম করেছে। ছোট duration দিন।"
            )

        await status.edit_text(f"রেকর্ড শেষ হয়েছে ({size_mb:.1f} MB)। পাঠানো হচ্ছে...")
        await update.message.reply_video(
            # A local Bot API server can accept the local file path directly.
            video=str(output),
            caption=f"Recorded video — {minutes} minute(s)",
            supports_streaming=True,
            read_timeout=180,
            write_timeout=180,
            connect_timeout=30,
            pool_timeout=30,
        )
        await status.delete()
    except Exception as exc:
        LOGGER.exception("Recording failed")
        await status.edit_text(f"রেকর্ড করা যায়নি: {exc}")
    finally:
        try:
            for child in work_dir.iterdir():
                child.unlink(missing_ok=True)
            work_dir.rmdir()
        except OSError:
            LOGGER.warning("Could not remove temporary directory %s", work_dir)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    LOGGER.exception("Unhandled bot error", exc_info=context.error)


def main() -> None:
    token = config.BOT_TOKEN.strip()
    if not token or token.startswith("PASTE_"):
        raise SystemExit("Edit config.py and paste your BotFather token first.")

    builder = Application.builder().token(token)
    if config.USE_LOCAL_BOT_API:
        builder = (
            builder
            .base_url(f"{config.BOT_API_HOST}/bot/")
            .base_file_url(f"{config.BOT_API_HOST}/file/bot/")
        )
    application = builder.build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", start))
    application.add_handler(CommandHandler("record", record))
    application.add_error_handler(error_handler)
    LOGGER.info("Bot is running. Press Ctrl+C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
