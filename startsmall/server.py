"""Local HTTP server: JSON API + static UI. Stdlib http.server, loopback only.

Routes (all JSON):
  GET  /api/home
  POST /api/session/start        {mode: small|micro, activity_id?}
  POST /api/session/serve        {session_id, activity_id, is_variation?, is_review?}
  POST /api/attempt              {session_id, activity_id, answer, self_check?}
  POST /api/hint                 {session_id, activity_id, level}
  POST /api/feedback             {session_id, activity_id, signal}
  POST /api/session/finish       {session_id, enjoyment?, frustration?}
  POST /api/run                  {code, stdin?}          free-form run of the learner's code
  GET  /api/evaluation
  GET  /api/collection
  GET  /api/tasks  POST /api/tasks  POST /api/tasks/<id>/start|done|delete|update
  GET  /api/settings  POST /api/settings
  GET  /api/ai/status
  POST /api/ai/explain           {activity_id, tried:[...]}
  POST /api/ai/react             {activity_id, text}
  GET  /api/tracks
  GET  /api/health
"""
from __future__ import annotations

import json
import mimetypes
import os
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from . import ai, content, runner
from .engine import Engine
from .store import Store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(ROOT, "static")


class App:
    def __init__(self, db_path: str):
        self.store = Store(db_path)
        self.lock = threading.Lock()
        self.engine = Engine(self.store)
        self.started_at = time.time()

    def reload_engine(self):
        self.engine = Engine(self.store)


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        server_version = "start-small/0.1"

        def log_message(self, fmt, *args):  # quiet by default
            if os.environ.get("STARTSMALL_DEBUG"):
                super().log_message(fmt, *args)

        # ---- plumbing ----
        def _json(self, code: int, payload) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if n <= 0:
                return {}
            raw = self.rfile.read(min(n, 2_000_000))
            try:
                return json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                return {}

        def _static(self, path: str) -> None:
            if path in ("", "/"):
                path = "/index.html"
            safe = os.path.normpath(path.lstrip("/")).replace("\\", "/")
            if safe.startswith("..") or os.path.isabs(safe):
                return self._json(404, {"error": "not found"})
            full = os.path.join(STATIC, safe)
            if not os.path.isfile(full):
                return self._json(404, {"error": "not found"})
            ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
            with open(full, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text/") or "javascript" in ctype else ""))
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)

        # ---- routing ----
        def do_GET(self):
            p = urlparse(self.path).path
            try:
                if p.startswith("/api/"):
                    with app.lock:
                        return self._json(200, self._get_api(p))
                return self._static(p)
            except KeyError as e:
                return self._json(404, {"error": f"unknown id {e}"})
            except Exception:  # noqa: BLE001 - never leave the UI hanging
                traceback.print_exc()
                return self._json(500, {"error": "server error", "detail": traceback.format_exc()[-800:]})

        def do_POST(self):
            p = urlparse(self.path).path
            body = self._body()
            try:
                with app.lock:
                    return self._json(200, self._post_api(p, body))
            except KeyError as e:
                return self._json(404, {"error": f"unknown id {e}"})
            except ValueError as e:
                return self._json(400, {"error": str(e)})
            except Exception:  # noqa: BLE001
                traceback.print_exc()
                return self._json(500, {"error": "server error", "detail": traceback.format_exc()[-800:]})

        def _get_api(self, p: str):
            e = app.engine
            if p == "/api/home":
                return e.home()
            if p == "/api/health":
                return {"ok": True, "uptime": round(time.time() - app.started_at), "db": app.store.path}
            if p == "/api/evaluation":
                return e.evaluation()
            if p == "/api/collection":
                return {"items": app.store.list_collection()}
            if p == "/api/tasks":
                return {"tasks": app.store.list_tasks()}
            if p == "/api/settings":
                return app.store.get_settings()
            if p == "/api/ai/status":
                return ai.status()
            if p == "/api/tracks":
                return {"tracks": content.available_tracks(), "current": e.track.id,
                        "concepts": [{"id": c, "title": e.track.concepts[c]["title"],
                                      "status": app.store.concept_state(c)["status"]} for c in e.track.concept_order]}
            raise KeyError(p)

        def _post_api(self, p: str, b: dict):
            e = app.engine
            s = app.store
            if p == "/api/session/start":
                mode = b.get("mode", "small")
                if mode not in ("small", "micro", "task"):
                    raise ValueError("bad mode")
                return e.start(mode, b.get("activity_id"))
            if p == "/api/session/serve":
                return e.serve(int(b["session_id"]), b["activity_id"], bool(b.get("is_variation")), bool(b.get("is_review")))
            if p == "/api/session/next":
                return e.serve_next(int(b["session_id"]))
            if p == "/api/attempt":
                return e.submit(int(b["session_id"]), b["activity_id"], b.get("answer", ""), b.get("self_check"))
            if p == "/api/hint":
                return e.hint(int(b["session_id"]), b["activity_id"], int(b.get("level", 1)))
            if p == "/api/feedback":
                return e.feedback(int(b["session_id"]), b["activity_id"], b.get("signal", ""))
            if p == "/api/session/finish":
                return e.finish(int(b["session_id"]), b.get("enjoyment"), b.get("frustration"))
            if p == "/api/run":
                code = str(b.get("code", ""))[:20000]
                return runner.run_program(code, stdin_text=str(b.get("stdin", ""))[:2000])
            if p == "/api/settings":
                new = s.set_settings(b)
                if "current_track" in b:
                    app.reload_engine()
                return new
            if p == "/api/tasks":
                title = (b.get("title") or "").strip()
                nxt = (b.get("next_action") or "").strip()
                stop = (b.get("stop_when") or "").strip()
                if not (title and nxt and stop):
                    raise ValueError("title, next_action and stop_when are all required")
                tid = s.add_task(title, nxt, stop, b.get("minutes", 5))
                return {"id": tid, "tasks": s.list_tasks()}
            if p.startswith("/api/tasks/"):
                parts = p.split("/")
                tid = int(parts[3]); action = parts[4] if len(parts) > 4 else ""
                if action == "start":
                    s.task_started(tid); s.log("task_start", {"task": tid})
                    sid = s.start_session("task")
                    return {"session_id": sid, "tasks": s.list_tasks()}
                if action == "done":
                    s.update_task(tid, done_at=time.time()); s.log("task_done", {"task": tid})
                    if b.get("session_id"):
                        s.bump_session(int(b["session_id"])); s.end_session(int(b["session_id"]))
                    return {"tasks": s.list_tasks()}
                if action == "delete":
                    s.delete_task(tid)
                    return {"tasks": s.list_tasks()}
                if action == "update":
                    s.update_task(tid, **{k: b[k] for k in ("title", "next_action", "stop_when", "minutes") if k in b})
                    return {"tasks": s.list_tasks()}
                raise KeyError(p)
            if p == "/api/ai/explain":
                st = s.get_settings()
                if not st.get("ai_enabled"):
                    return {"ok": False, "error": "AI help is off in Settings."}
                a = e.track.activity(b["activity_id"])
                return ai.explain_differently(st["ai_model"], a, b.get("tried") or [])
            if p == "/api/ai/react":
                st = s.get_settings()
                if not st.get("ai_enabled"):
                    return {"ok": False, "error": "AI help is off in Settings."}
                a = e.track.activity(b["activity_id"])
                return ai.react_to_explanation(st["ai_model"], a, str(b.get("text", ""))[:2000])
            raise KeyError(p)

    return Handler


def serve(db_path: str, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    app = App(db_path)
    httpd = ThreadingHTTPServer((host, port), make_handler(app))
    httpd.daemon_threads = True
    return httpd
