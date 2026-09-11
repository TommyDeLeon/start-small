"""Launch start-small.

    python app.py            start on http://127.0.0.1:8765 and open the browser
    python app.py --no-open  start without opening the browser
    python app.py --port N   use another port
    python app.py --db PATH  use another database file

Ctrl+C stops it. Nothing runs in the background afterwards.
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from startsmall.server import serve  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="start-small: a low-friction way in.")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--db", default=os.path.join(ROOT, "data", "startsmall.db"))
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()

    try:
        httpd = serve(args.db, port=args.port)
    except OSError as e:
        print(f"Could not bind port {args.port}: {e}\nTry:  python app.py --port {args.port + 1}")
        return 1
    url = f"http://127.0.0.1:{args.port}/"
    print(f"start-small is running at {url}")
    print(f"progress is saved in {args.db}")
    print("Press Ctrl+C to stop.")
    if not args.no_open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped. Your progress is saved.")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
