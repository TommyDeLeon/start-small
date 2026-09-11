"""Optional, opt-in reminder. Run it yourself; the app never schedules anything.

    python remind.py

Shows ONE dismissible message box ("Your prepared two-minute step is ready")
and exits. It stays silent when:
  * reminders are off in Settings (the default)
  * the current hour is inside quiet hours
  * you already practised today
  * it already reminded you today
If you want it daily, add it to Windows Task Scheduler yourself — that is a
deliberate manual step, so nothing here creates startup persistence.
"""
from __future__ import annotations

import os
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from startsmall.store import Store  # noqa: E402

DB = os.path.join(ROOT, "data", "startsmall.db")


def in_quiet_hours(hour: int, quiet: list[int]) -> bool:
    start, end = quiet
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end  # wraps midnight


def main() -> int:
    if not os.path.exists(DB):
        print("No data yet — open the app first.")
        return 0
    store = Store(DB)
    s = store.get_settings()
    if not s.get("reminders_enabled"):
        print("Reminders are off in Settings. Nothing shown.")
        return 0
    now = time.localtime()
    if in_quiet_hours(now.tm_hour, s.get("quiet_hours", [22, 8])):
        print("Quiet hours. Nothing shown.")
        return 0
    today = time.strftime("%Y-%m-%d")
    last = store.last_attempt_at()
    if last and time.strftime("%Y-%m-%d", time.localtime(last)) == today:
        print("Already practised today. Nothing shown.")
        return 0
    for e in reversed(store.events_since(time.time() - 86400)):
        if e["kind"] == "reminder" and time.strftime("%Y-%m-%d", time.localtime(e["at"])) == today:
            print("Already reminded today. Nothing shown.")
            return 0
    store.log("reminder")
    msg = f"Cue: {s.get('cue')}.\n\nYour prepared two-minute step is ready.\nOpen start-small when you like — or not. No streak to protect."
    if os.name == "nt":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, msg, "start small", 0x40)  # info icon, one OK button
    else:
        print(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
