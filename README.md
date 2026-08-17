# Railway M3U8/M3U Telegram Recording Bot

এই project একটি Telegram bot চালায়, যা `/record <minutes> <m3u8_or_m3u_url>` command নিয়ে stream record করে Telegram-এ পাঠায়। বড় ফাইলের জন্য `MAX_UPLOAD_MB = 1950` configured আছে। বড় upload চালাতে Railway project-এ **দুটি service** এবং local Telegram Bot API service-এর জন্য **persistent volume** লাগবে।

> আগের chat-এ প্রকাশিত token বা API credentials এই package-এ রাখা হয়নি। সেগুলো revoke করে নতুন credentials ব্যবহার করুন।

## Project files

| File | কাজ |
|---|---|
| `bot.py` | Telegram command এবং ffmpeg recording logic |
| `config.py` | Bot token, API ID/hash, limits, এবং API host |
| `Dockerfile` | Bot service-এর image |
| `Dockerfile.telegram-api` | Local Telegram Bot API service-এর image |
| `docker-compose.yml` | Local দুই-service reference setup |
| `start_api.py` | Local Docker testing launcher |
| `requirements.txt` | Python dependencies |

## Credentials

`config.py` খুলে নতুন credentials বসান। এগুলো chat বা public Git repository-তে পাঠাবেন না:

```python
BOT_TOKEN = "PASTE_NEW_BOTFATHER_TOKEN_HERE"
API_ID = 12345678
API_HASH = "PASTE_NEW_API_HASH_HERE"
MAX_UPLOAD_MB = 1950
USE_LOCAL_BOT_API = True
BOT_API_HOST = "http://telegram-api:8081"
```

`BOT_TOKEN` নিতে `@BotFather` ব্যবহার করুন। `API_ID` এবং `API_HASH` নিতে [my.telegram.org](https://my.telegram.org)-এর API development tools ব্যবহার করুন।

## Railway deployment

Railway-তে একই GitHub repository থেকে দুটি service তৈরি করুন। প্রথম service-এর নাম `telegram-api` দিন। এই service-এর Dockerfile হিসেবে `Dockerfile.telegram-api` নির্বাচন করুন। দ্বিতীয় service-এর নাম `bot` দিন এবং সাধারণ `Dockerfile` নির্বাচন করুন। Railway private networking-এর কারণে bot service `http://telegram-api:8081` address ব্যবহার করবে।

`Dockerfile.telegram-api`-এ placeholder আছে। Railway-তে API service-এর Dockerfile build করার আগে এই দুই line নিজের নতুন credentials দিয়ে বদলান:

```dockerfile
CMD ["telegram-bot-api", "--api-id=YOUR_NEW_API_ID", "--api-hash=YOUR_NEW_API_HASH", "--local"]
```

Bot service-এর source-এর `config.py`-তে নতুন `BOT_TOKEN`, `API_ID`, এবং `API_HASH` বসান। `BOT_API_HOST = "http://telegram-api:8081"` অপরিবর্তিত রাখুন।

`telegram-api` service-এর সঙ্গে Railway Volume attach করুন এবং mount path `/var/lib/telegram-bot-api` দিন। Recording-এর temporary files bot service-এর local filesystem-এ তৈরি হবে; দীর্ঘ recording এবং 1.95 GB file-এর জন্য bot service-এ যথেষ্ট ephemeral disk/RAM এবং Railway plan capacity নিশ্চিত করুন।

Deploy order হিসেবে আগে `telegram-api` service deploy করুন, তারপর `bot` service deploy করুন। Bot service-এর logs-এ `Bot is running` দেখা গেলে Telegram-এ test করুন:

```text
/start
/record 1 https://example.com/live.m3u8
```

সবকিছু ঠিক থাকলে ধীরে ধীরে duration বাড়ান:

```text
/record 5 https://example.com/live.m3u8
```

## Local Docker test

PC-তে Docker Desktop চালু করে project folder-এ `config.py`-তে `BOT_API_HOST = "http://127.0.0.1:8081"` সেট করুন। এরপর:

```bat
docker compose up telegram-api
```

অন্য terminal-এ:

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python bot.py
```

## Important limitations

1.95 GB হলো project-এর configured safety ceiling; actual file size stream bitrate এবং duration-এর উপর নির্ভর করবে। Telegram local Bot API server ছাড়া standard Bot API দিয়ে এই বড় upload কাজ করবে না। Local API service, volume, network, disk, এবং Railway plan capacity ঠিকভাবে configured থাকতে হবে।

শুধু public HTTP/HTTPS stream URL সমর্থিত। Login, cookie, referer, geo-blocking, বা DRM-নির্ভর stream কাজ নাও করতে পারে। DRM bypass করার কোনো ব্যবস্থা এই project-এ নেই।

## Security

Token এবং API hash কখনো public repository-তে commit করবেন না। Credentials প্রকাশ হয়ে গেলে BotFather-এ token revoke করুন এবং my.telegram.org থেকে নতুন API credentials ব্যবহার করুন।

## References

[1]: https://core.telegram.org/bots/api "Telegram Bot API official documentation"
[2]: https://github.com/tdlib/telegram-bot-api "Telegram Bot API server source repository"
[3]: https://docs.railway.com/volumes "Railway Volumes documentation"
[4]: https://docs.railway.com/guides/docker-compose "Railway Docker Compose deployment guide"
