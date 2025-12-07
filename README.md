# TikTok Continuous Runner (Real API, Every 5 Minutes)

A zero-interaction, continuous worker that calls your real backend API to send the fixed TikTok link to all services (except Followers) every 5 minutes.

- Fixed link hardcoded in `main.py`:
```
FIXED_URL = "https://vm.tiktok.com/ZNRd9XevX/"
```
- Followers (service id 228) is excluded automatically (by ID, and you can also exclude by name if needed).
- No stats checker is included.

## Backend Integration (Zefame)
This runner expects your real backend module `tiktok_services.py` to be present in the repository (or otherwise importable at runtime) with a class `ZefameService` exposing:
- `get_available_services()` → returns a list of services with fields like `id`, `name`, `available`, etc.
- `boost(url, service_id, session_id, stop_flag, job_status, job_lock, min_qty, max_qty)` → performs the send/boost for a service and returns `(success: bool, message: str)`.

In `main.py` we import it directly:
```python
from tiktok_services import ZefameService
```
Ensure your `tiktok_services.py` (with ZefameService) is included in the same directory or otherwise in PYTHONPATH so the import succeeds on Render.

## Configuration (env)
- `TIKTOK_MIN_SEND` (default 100)
- `TIKTOK_MAX_SEND` (default 500)
- `TIKTOK_INTERVAL_SECS` (default 300 = 5 minutes)
- `TIKTOK_MAX_CYCLES` (default 0 = run forever)

## Requirements
Add any real backend dependencies your `tiktok_services.py` needs to `requirements.txt` (for example, `requests`). The file is minimal by default to avoid unnecessary packages.

## Run locally
```bash
python main.py
```
(Press Ctrl+C to stop. If the import of `tiktok_services` fails locally, place your backend file next to `main.py`.)

## Deploy to Render (Worker)
1. Push this folder to a GitHub repo.
2. In Render, create a new Worker from the repo.
3. Render will use `render.yaml`. If not, set:
   - Build: `pip install -r requirements.txt`
   - Start: `python main.py`
4. Configure environment variables as needed.

The process runs indefinitely, waking up every 5 minutes to submit the link to all eligible services except Followers.
