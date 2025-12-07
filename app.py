import os
import time
import signal
import threading
import uuid
import requests
import re

# Fixed TikTok link (hardcoded as requested)
FIXED_URL = "https://vm.tiktok.com/ZNRd9XevX/"

# Optional quantities (kept for compatibility; Zefame backend sends fixed lots per order)
MIN_QTY = int(os.environ.get("TIKTOK_MIN_SEND", "100"))
MAX_QTY = int(os.environ.get("TIKTOK_MAX_SEND", "500"))

# Use the REAL API from your backend (no mocks)
from tiktok_services import ZefameService  # type: ignore
from tiktok_services import BACKEND_API  # type: ignore

# Graceful shutdown flag
_shutdown = {"stop": False}

# Exclude Followers by service id
FOLLOWERS_SERVICE_ID = 228

# Labels for nicer logs
SERVICE_LABELS = {
    229: "VIEWS",
    232: "LIKES",
    235: "SHARES",
    236: "FAVORITES",
    228: "FOLLOWERS",
}


def _handle_signal(signum, frame):
    print(f"[INFO] Received signal {signum}; stopping scheduler after current actions.")
    _shutdown["stop"] = True


def parse_timer_seconds(timer_str: str, default_on_success: int = 300, default_on_fail: int = 60, success: bool = True) -> int:
    """Parse timer string like '5m' or '45s' into seconds; fall back to defaults."""
    timer_str = (timer_str or "").strip().lower()
    if timer_str.endswith("m"):
        try:
            return int(float(timer_str[:-1]) * 60)
        except Exception:
            pass
    if timer_str.endswith("s"):
        try:
            return int(float(timer_str[:-1]))
        except Exception:
            pass
    return default_on_success if success else default_on_fail


def parse_wait_message(message: str) -> int:
    """Parse backend wait messages like:
    - 'Attendez encore 4 minutes et 34 secondes'
    - 'Wait another 3 minutes and 10 seconds'
    Returns seconds to wait (>= 0)."""
    if not message:
        return 0
    msg = message.lower()
    # French patterns
    m = re.search(r"attendez encore\s*(\d+)\s*minute[s]?\s*et\s*(\d+)\s*seconde[s]?", msg)
    if m:
        mins = int(m.group(1))
        secs = int(m.group(2))
        return mins * 60 + secs
    m = re.search(r"attendez encore\s*(\d+)\s*minute[s]?", msg)
    if m:
        mins = int(m.group(1))
        return mins * 60
    m = re.search(r"attendez encore\s*(\d+)\s*seconde[s]?", msg)
    if m:
        secs = int(m.group(1))
        return secs
    # English patterns
    m = re.search(r"wait another\s*(\d+)\s*minute[s]?\s*and\s*(\d+)\s*second[s]?", msg)
    if m:
        mins = int(m.group(1))
        secs = int(m.group(2))
        return mins * 60 + secs
    m = re.search(r"wait another\s*(\d+)\s*minute[s]?", msg)
    if m:
        mins = int(m.group(1))
        return mins * 60
    m = re.search(r"wait another\s*(\d+)\s*second[s]?", msg)
    if m:
        secs = int(m.group(1))
        return secs
    # Fallback: extract any minutes/seconds mentions
    m_min = re.search(r"(\d+)\s*minute", msg)
    m_sec = re.search(r"(\d+)\s*second", msg)
    total = 0
    if m_min:
        total += int(m_min.group(1)) * 60
    if m_sec:
        total += int(m_sec.group(1))
    return total


def run_scheduler():
    # Get service catalog
    catalog = ZefameService.get_available_services() or []
    if not catalog:
        print("No services available; retrying in 30s...")
        time.sleep(30)
        return

    # Build service map with names and timers; exclude followers and unavailable
    services = {}
    for s in catalog:
        try:
            sid = int(s.get("id"))
        except Exception:
            continue
        if sid == FOLLOWERS_SERVICE_ID:
            continue
        if not bool(s.get("available", False)):
            continue
        services[sid] = {
            "name": s.get("name") or SERVICE_LABELS.get(sid, f"SERVICE_{sid}"),
            "timer": s.get("timer") or "",
        }

    if not services:
        print("No eligible services after filtering; retrying in 60s...")
        time.sleep(60)
        return

    print(f"Found {len(services)} eligible services. Scheduler is active...")

    # Resolve videoId once
    video_id = ZefameService.parse_video_id(FIXED_URL)
    if not video_id:
        print("[ERROR] Could not resolve videoId from the fixed URL. Retrying in 30s...")
        time.sleep(30)
        return

    # Next run timestamp per service id
    next_run = {sid: 0.0 for sid in services.keys()}

    while not _shutdown["stop"]:
        now = time.time()
        did_any = False
        for sid, meta in services.items():
            if now < next_run.get(sid, 0.0):
                continue

            label = SERVICE_LABELS.get(sid, (meta.get("name") or f"SERVICE_{sid}")).upper()
            try:
                attempt_ts = time.strftime('%Y-%m-%d %H:%M:%S')
                print(f'[{label}] Attempt @ {attempt_ts}')
                payload = {
                    "action": "order",
                    "service": sid,
                    "link": FIXED_URL,
                    "uuid": str(uuid.uuid4()),
                    "videoId": video_id,
                }
                resp = requests.post(BACKEND_API, data=payload, timeout=20)
                data = resp.json()
                success = bool(data.get("success"))
                order_id = (data.get("data") or {}).get("orderId")
                msg = data.get("message")
                if success:
                    print(f"[{label}] ✅ Sent. orderId={order_id}")
                else:
                    # Show remaining wait if provided by backend message
                    wait_hint = parse_wait_message(msg)
                    if wait_hint > 0:
                        mins = wait_hint // 60
                        secs = wait_hint % 60
                        print(f"[{label}] ❌ Not yet available. Retry in ~{mins}m {secs}s (msg: {msg})")
                    else:
                        print(f"[{label}] ❌ Order failed: {msg}")

                # Reschedule based on backend hint or service timer
                next_avail = (data.get("data") or {}).get("nextAvailable")
                if isinstance(next_avail, (int, float)) and next_avail > now:
                    next_run[sid] = float(next_avail)
                    eta = int(max(0, next_run[sid] - time.time()))
                    print(f'[{label}] Next run @ ' + time.strftime('%H:%M:%S', time.localtime(next_run[sid])) + f' (in ~{eta//60}m {eta%60}s)')
                else:
                    # Prefer explicit wait parsed from message if failure indicated scheduling
                    parsed_wait = 0 if success else parse_wait_message(msg)
                    if parsed_wait and parsed_wait > 0:
                        next_run[sid] = now + max(30, parsed_wait)  # ensure at least 60s cadence

                        # Log the exact next run time and ETA
                        eta = int(max(0, next_run[sid] - time.time()))
                        print(f'[{label}] Next run @ ' + time.strftime('%H:%M:%S', time.localtime(next_run[sid])) + f' (in ~{eta//60}m {eta%60}s)')
                    else:
                        delay = parse_timer_seconds(meta.get("timer") or "", success=success)
                        next_run[sid] = now + max(30, delay)  # attempt at least every minute

                # Log the exact next run time and ETA
                eta = int(max(0, next_run[sid] - time.time()))
                print(f'[{label}] Next run @ ' + time.strftime('%H:%M:%S', time.localtime(next_run[sid])) + f' (in ~{eta//60}m {eta%60}s)')

                did_any = True
            except Exception as e:
                print(f"[{label}] ❌ Order error: {e}")
                # Backoff on error
                next_run[sid] = now + 30

        if _shutdown["stop"]:
            break
        # Avoid tight loop; check every second for due services
        if not did_any:
            time.sleep(1)


def main():
    # Handle SIGTERM/SIGINT
    try:
        signal.signal(signal.SIGTERM, _handle_signal)
        signal.signal(signal.SIGINT, _handle_signal)
    except Exception:
        pass

    print("=== TikTok Continuous Runner (Per-service scheduler) ===")
    print("Fixed URL:", FIXED_URL)
    print("Excluding Followers (service id 228)")

    try:
        run_scheduler()
    except Exception as e:
        print("[FATAL] Scheduler exception:", e)
    print("Exiting continuous runner.")


if __name__ == "__main__":
    main()
