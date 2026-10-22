# Bot-consulat

Sends a Telegram message when a passport (Reisepass) appointment up to and including 26 November 2026 opens up on
https://www.cgtdus.com/booking-calendar/reisepass-5

It opens the booking page in headless Chromium every 5 minutes (GitHub Actions; runs can start late), reads the slots from
the calendar's own availability responses, and messages you about slots it hasn't announced before.

## Setup

1. **Create a Telegram bot**: message [@BotFather](https://t.me/BotFather), send `/newbot`, copy the token.
2. **Get your chat id**: send any message to your new bot, then open
   `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy `message.chat.id`.
3. In the GitHub repo, go to *Settings → Secrets and variables → Actions* and add the secrets
   `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.
   Only slots **up to and including 26 Nov 2026** are reported. To change that, add a repository
   variable `UNTIL_DATE` (e.g. `2026-12-15`).
   You only get a message when a new slot shows up. To also get a status message after every run
   (including "nothing found" and failures), add a variable `ALWAYS_NOTIFY` set to `true`.
4. Go to *Actions → Check passport appointments → Run workflow* and tick **debug** for the first run.
   The `debug` artifact contains a screenshot and the captured JSON, which shows whether the slots were read.

GitHub's scheduled runs can start a few minutes late, and they pause after 60 days without repository activity.
Keep the repository public: Actions minutes are free for public repos, while a private repo would need
about 8,600 minutes a month at this schedule (the free plan includes 2,000).

## Run locally

```sh
pip install -r requirements.txt
playwright install chromium
python checker.py --dry-run --until 2026-11-26 --debug debug
```

`--dry-run` prints the message instead of sending it. Run `python -m pytest` for the tests.
