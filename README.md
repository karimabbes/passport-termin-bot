# Bot-consulat

Sends a Telegram message when a passport (Reisepass) appointment up to and including 26 November 2026 opens up on
https://www.cgtdus.com/booking-calendar/reisepass-5

It opens the booking page in headless Chromium every 5 minutes (GitHub Actions), reads the slots from
the calendar's own availability responses, and messages you about slots it hasn't announced before.
GitHub's scheduler often skips frequent cron runs, so each run keeps checking for about 5.5 hours and
then starts the next run itself; an hourly cron restarts the chain if it ever stops.

## Setup

1. **Create a Telegram bot**: message [@BotFather](https://t.me/BotFather), send `/newbot`, copy the token.
2. **Get your chat id**: send any message to your new bot, then open
   `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy `message.chat.id`.
3. In the GitHub repo, go to *Settings → Secrets and variables → Actions* and add the secrets
   `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.
   To notify several people, each one sends the bot a message, and you put all their chat ids in
   `TELEGRAM_CHAT_ID` separated by commas, e.g. `111111111,222222222`.
   Only slots **up to and including 26 Nov 2026** are reported. To change that, add a repository
   variable `UNTIL_DATE` (e.g. `2026-12-15`).
   Every check also sends a status message (including "nothing found" and failures). To only get a
   message when a new slot shows up, add a variable `ALWAYS_NOTIFY` set to `false`.
   To check more or less often, add a variable `CHECK_EVERY_MINUTES` (default `5`).
4. Go to *Actions → Check passport appointments → Run workflow* and tick **debug** for the first run.
   The `debug` artifact contains a screenshot and the captured JSON, which shows whether the slots were read.

Keep the repository public: the bot keeps a runner busy around the clock, which is free for public
repos but far beyond the 2,000 free minutes a month of a private one. GitHub pauses the hourly cron
after 60 days without repository activity. To stop the bot, disable the workflow in the Actions tab.

## Run locally

```sh
pip install -r requirements.txt
playwright install chromium
python checker.py --dry-run --until 2026-11-26 --debug debug
```

`--dry-run` prints the message instead of sending it. Run `python -m pytest` for the tests.
