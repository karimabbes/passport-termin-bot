"""Watch a Wix Bookings calendar and send a Telegram message when slots open up.

The page is loaded in headless Chromium; the calendar widget fetches its
availability as JSON, and we read the slots straight out of those responses
instead of scraping the rendered calendar.
"""

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

DEFAULT_URL = "https://www.cgtdus.com/booking-calendar/reisepass-5?referral=service_list_widget"
LOCAL_TZ = ZoneInfo("Europe/Berlin")

# Wix availability endpoints (old and new APIs) all contain one of these.
AVAILABILITY_URL_HINTS = ("availability", "time-slots", "timeslots", "slots")

START_KEYS = ("localStartDate", "startDate", "start")


def find_slots(payload):
    """Return sorted ISO start times of every bookable slot found in a JSON payload.

    Walks the whole structure so it works with both the
    `availabilityEntries[].slot.startDate` and `timeSlots[].localStartDate` shapes.
    """
    found = set()

    def walk(node):
        if isinstance(node, dict):
            start = _start_of(node)
            if start and _is_bookable(node):
                found.add(start)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    return sorted(found)


def _start_of(node):
    for key in START_KEYS:
        value = node.get(key)
        if isinstance(value, str) and re.match(r"\d{4}-\d{2}-\d{2}T", value):
            return value
    slot = node.get("slot")
    if isinstance(slot, dict):
        return _start_of(slot)
    return None


def _is_bookable(node):
    if node.get("bookable") is False:
        return False
    if node.get("isFull") is True or node.get("full") is True:
        return False
    open_spots = node.get("openSpots", node.get("remainingCapacity"))
    if isinstance(open_spots, (int, float)) and open_spots <= 0:
        return False
    # Only count nodes that actually describe availability, not e.g. a service's creation date.
    return any(k in node for k in ("bookable", "openSpots", "remainingCapacity", "slot", "localStartDate"))


def within_window(slots, days, until=None, today=None):
    """Keep slots from today on, up to `days` ahead, or up to and including `until` when given."""
    today = today or date.today()
    if until:
        return [s for s in slots if today <= date.fromisoformat(s[:10]) <= until]
    limit = today + timedelta(days=days)
    return [s for s in slots if today <= date.fromisoformat(s[:10]) <= limit]


def fetch_slots(url, months, max_months=6, debug_dir=None):
    """Load `months` calendar months, then keep paging (up to `max_months`) until a free slot shows up."""
    from playwright.sync_api import sync_playwright

    slots = set()
    captured = []

    def on_response(response):
        if not any(h in response.url.lower() for h in AVAILABILITY_URL_HINTS):
            if debug_dir and "json" in response.headers.get("content-type", ""):
                print(f"  (other JSON) {response.url[:150]}")
            return
        try:
            payload = response.json()
        except Exception:
            return
        found = find_slots(payload)
        print(f"  availability response: {len(found)} slot(s) {found[:1]} from {response.url[:150]}")
        captured.append({"url": response.url, "body": payload})
        slots.update(found)

    def has_upcoming():
        return any(date.fromisoformat(s[:10]) >= date.today() for s in slots)

    def wait_for_availability(seen_before, timeout_s):
        """Wait until the calendar has fetched new availability data.

        Waiting for "networkidle" timed out on about half the checks, because the Wix site
        sometimes keeps background requests going long after the calendar has loaded.
        """
        for _ in range(timeout_s * 2):
            if len(captured) > seen_before:
                break
            page.wait_for_timeout(500)
        else:
            return False
        page.wait_for_timeout(2_000)  # the calendar fetches several ranges in parallel
        return True

    with sync_playwright() as p:
        launch = {"headless": True}
        if os.environ.get("CHROMIUM_PATH"):
            launch["executable_path"] = os.environ["CHROMIUM_PATH"]
        browser = p.chromium.launch(**launch)
        page = browser.new_page(locale="de-DE")
        page.on("response", on_response)
        page.goto(url, wait_until="domcontentloaded", timeout=90_000)
        if not wait_for_availability(0, 60):
            raise RuntimeError("the booking calendar did not load its availability within 60s")

        for loaded in range(1, max_months):
            if loaded >= months and has_upcoming():
                break
            seen_before = len(captured)
            if not _click_next_month(page):
                print("  could not find the next-month button")
                break
            print(f"  -> next month ({loaded + 1})")
            if not wait_for_availability(seen_before, 30):
                print("  next month did not load its availability")
                break

        if debug_dir:
            Path(debug_dir).mkdir(parents=True, exist_ok=True)
            page.screenshot(path=f"{debug_dir}/page.png", full_page=True)
            Path(f"{debug_dir}/responses.json").write_text(json.dumps(captured, indent=2))
        browser.close()

    return sorted(slots)


def _click_next_month(page):
    selectors = (
        '[data-hook="next-arrow"]',
        '[data-hook*="next"]',
        'button[aria-label*="Nächste" i]',
        'button[aria-label*="next" i]',
        'button[aria-label*="suivant" i]',
    )
    for selector in selectors:
        button = page.locator(selector).first
        if button.count() and button.is_enabled():
            button.click()
            return True
    return False


def send_telegram(text):
    """Send to every chat in TELEGRAM_CHAT_ID (comma-separated); one bad id doesn't block the others."""
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_ids = [c.strip() for c in os.environ["TELEGRAM_CHAT_ID"].split(",") if c.strip()]
    failed = []
    for chat_id in chat_ids:
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
        try:
            urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data, timeout=30)
        except Exception as exc:
            print(f"sending to chat #{chat_ids.index(chat_id) + 1} failed: {exc}")
            failed.append(chat_id)
    if failed and len(failed) == len(chat_ids):
        raise RuntimeError("could not send the Telegram message to any chat")


def format_slot(slot):
    """Human-readable slot time in German local time; UTC timestamps are converted."""
    dt = datetime.fromisoformat(slot.replace("Z", "+00:00"))
    if dt.tzinfo:
        dt = dt.astimezone(LOCAL_TZ)
    return f"{dt:%a %d %b %Y, %H:%M}"


def format_message(slots, url):
    lines = ["🎉 New passport appointments available!", f"Next free: {format_slot(slots[0])}", ""]
    for s in slots[:20]:
        lines.append(f"• {format_slot(s)}")
    if len(slots) > 20:
        lines.append(f"… and {len(slots) - 20} more")
    lines += ["", url]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.environ.get("BOOKING_URL", DEFAULT_URL))
    parser.add_argument("--days", type=int, default=int(os.environ.get("LOOKAHEAD_DAYS", "14")),
                        help="only report slots within this many days")
    parser.add_argument("--until", type=date.fromisoformat, default=os.environ.get("UNTIL_DATE") or None,
                        help="only report slots up to and including this date (YYYY-MM-DD); overrides --days")
    parser.add_argument("--months", type=int, default=2, help="calendar months to load at least")
    parser.add_argument("--max-months", type=int, default=6,
                        help="keep loading months up to this many until a free slot is found")
    parser.add_argument("--state", default="state.json", help="remembers already-notified slots")
    parser.add_argument("--debug", metavar="DIR", help="save screenshot and captured JSON here")
    parser.add_argument("--dry-run", action="store_true", help="print instead of sending to Telegram")
    parser.add_argument("--always-notify", action="store_true",
                        default=os.environ.get("ALWAYS_NOTIFY", "").lower() in ("1", "true", "yes"),
                        help="also send a message when no new slots were found or the check failed")
    args = parser.parse_args()

    def notify(text):
        if args.dry_run or not os.environ.get("TELEGRAM_BOT_TOKEN"):
            print(text)
        else:
            send_telegram(text)

    window = f"until {args.until:%d %b %Y}" if args.until else f"in the next {args.days} days"
    try:
        all_slots = fetch_slots(args.url, args.months, args.max_months, args.debug)
    except Exception as exc:
        if args.always_notify:
            notify(f"❌ Check failed: {type(exc).__name__}: {str(exc)[:300]}")
        raise
    upcoming = [s for s in all_slots if date.fromisoformat(s[:10]) >= date.today()]
    slots = within_window(all_slots, args.days, args.until)
    print(f"{len(slots)} bookable slot(s) {window}")

    state_path = Path(args.state)
    seen = set(json.loads(state_path.read_text())) if state_path.exists() else set()
    new = [s for s in slots if s not in seen]

    if new:
        notify(format_message(new, args.url))
    elif args.always_notify:
        if upcoming:
            next_free = f"Next free appointment: {format_slot(upcoming[0])}"
        else:
            next_free = f"No free appointment at all in the next {args.max_months} calendar months."
        if slots:
            notify(f"ℹ️ No new appointments {window}; {len(slots)} already reported still free.\n{next_free}")
        else:
            notify(f"✅ Check done: no free appointments {window}.\n{next_free}")
    # Keep only slots still on offer, so a slot that reappears after being taken is reported again.
    state_path.write_text(json.dumps(slots))

if __name__ == "__main__":
    sys.exit(main())
