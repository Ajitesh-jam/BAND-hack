"""Human-approval via a compact Chrome toast + optional macOS banner.

Commander calls ``request_human_approval`` once per incident. Duplicate calls for the
same room+incident are ignored so the user is not spammed.
"""

from __future__ import annotations

import html
import json
import logging
import os
import secrets
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from band.agents.context import get_current_room
from band.client import BandAgentClient
from band.registry import load_agent_config

logger = logging.getLogger(__name__)

_DEFAULT_PORT = int(os.environ.get("APPROVAL_PORT", "8770"))
_TOAST_WIDTH = int(os.environ.get("APPROVAL_TOAST_WIDTH", "400"))
_TOAST_HEIGHT = int(os.environ.get("APPROVAL_TOAST_HEIGHT", "260"))

_lock = threading.Lock()
_server: ThreadingHTTPServer | None = None
_port: int = _DEFAULT_PORT
_pending: dict[str, dict[str, Any]] = {}
# (room_id, incident_id) -> token — one approval flow per incident per room
_sent: dict[tuple[str, str], str] = {}

_CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
)


def _mentions_for(roles: list[str]) -> list[dict[str, Any]]:
    mentions: list[dict[str, Any]] = []
    for role in roles:
        try:
            creds = load_agent_config(role)
        except Exception:  # noqa: BLE001
            continue
        mentions.append(
            {"id": creds.agent_id, "handle": creds.handle, "name": role}
        )
    return mentions


def _human_in_room(room_id: str) -> dict[str, Any] | None:
    """Find the human User participant so approval shows up for them in chat."""
    try:
        creds = load_agent_config("commander")
        with BandAgentClient(creds.agent_id, creds.api_key) as client:
            ctx = client.get_chat_context(room_id)
            if isinstance(ctx, dict):
                for key in ("participants", "members", "users"):
                    for p in ctx.get(key) or []:
                        if str(p.get("type", "")).lower() == "user":
                            return {
                                "id": p.get("id") or p.get("participant_id"),
                                "handle": p.get("handle"),
                                "name": p.get("name") or p.get("handle") or "human",
                            }
    except Exception as exc:  # noqa: BLE001
        logger.debug("Could not resolve human in room %s: %s", room_id, exc)
    return None


def _post_to_band(room_id: str, content: str, mention_roles: list[str]) -> None:
    creds = load_agent_config("commander")
    mentions = _mentions_for(mention_roles)
    human = _human_in_room(room_id)
    if human and human.get("id"):
        if not any(m.get("id") == human["id"] for m in mentions):
            mentions.insert(0, human)
    if not mentions:
        mentions = _mentions_for(["coder"])
    with BandAgentClient(creds.agent_id, creds.api_key) as client:
        client.send_message(room_id, content, mentions=mentions)
    logger.info("Posted approval message to room %s", room_id)


def _approve_message(rec: dict[str, Any]) -> str:
    inc = rec.get("incident_id") or "the change"
    return (
        f"HUMAN APPROVED (via notification) — {inc}.\n"
        f"@commander proceed to step C7: tell @github_agent to commit_and_push, "
        f"open_pull_request, and merge_pull_request using the branch and PR details "
        f"from the approval summary.\n"
        f"Do not post FEATURE_DONE until github_agent confirms merge."
    )


def _reject_message(rec: dict[str, Any]) -> str:
    inc = rec.get("incident_id") or "the change"
    return (
        f"HUMAN REJECTED (via notification) — {inc}.\n"
        f"ESCALATE — workflow stopped; follow up manually."
    )


def _decision_page(title: str, body: str) -> bytes:
    return _render_toast_shell(
        title=title,
        summary=body,
        token="",
        readonly=True,
    )


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args: Any) -> None:
        return

    def _send(self, code: int, body: bytes, content_type: str = "text/html") -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parts = [p for p in self.path.split("?")[0].split("/") if p]
        if len(parts) == 2 and parts[0] == "a":
            rec = _pending.get(parts[1])
            if not rec:
                self._send(404, _decision_page("Not found", "Invalid or expired link."))
                return
            if rec["status"] != "pending":
                self._send(
                    200,
                    _render_toast_shell(
                        title="Already decided",
                        summary=f"Status: {rec['status']}",
                        token=parts[1],
                        readonly=True,
                    ),
                )
                return
            self._send(200, _render_approval(parts[1], rec))
            return
        self._send(404, _decision_page("Not found", "Unknown path."))

    def do_POST(self) -> None:  # noqa: N802
        parts = [p for p in self.path.split("?")[0].split("/") if p]
        if len(parts) == 3 and parts[0] == "a" and parts[2] in ("approve", "reject"):
            token, decision = parts[1], parts[2]
            rec = _pending.get(token)
            if not rec or rec["status"] != "pending":
                self._send(200, b'{"ok":true,"status":"already_decided"}', "application/json")
                return
            rec["status"] = "approved" if decision == "approve" else "rejected"
            room_id = rec.get("room_id")
            if room_id:
                try:
                    msg = _approve_message(rec) if decision == "approve" else _reject_message(rec)
                    roles = ["github_agent", "commander"] if decision == "approve" else ["commander"]
                    _post_to_band(room_id, msg, roles)
                except Exception as exc:  # noqa: BLE001
                    logger.error("Failed to post approval to Band room %s: %s", room_id, exc)
                    rec["post_error"] = str(exc)
            self._send(200, json.dumps({"ok": True, "status": rec["status"]}).encode(), "application/json")
            return
        self._send(404, b'{"ok":false}', "application/json")


def _summary_preview(text: str, limit: int = 220) -> str:
    flat = " ".join((text or "").split())
    if len(flat) <= limit:
        return flat
    return flat[: limit - 1] + "…"


def _render_toast_shell(
    *,
    title: str,
    summary: str,
    token: str,
    readonly: bool = False,
) -> bytes:
    """Mobile-style push toast — bottom-right card, not a full-page modal."""
    inc = html.escape(title)
    body = html.escape(_summary_preview(summary))
    actions = ""
    script = ""
    if not readonly and token:
        actions = """
<div class="actions">
  <button id="no" class="btn reject" type="button">Reject</button>
  <button id="ok" class="btn approve" type="button">Approve &amp; merge</button>
</div>
<p id="msg" class="msg"></p>"""
        script = f"""
<script>
async function decide(k) {{
  const ok = document.getElementById('ok');
  const no = document.getElementById('no');
  if (ok) ok.disabled = true;
  if (no) no.disabled = true;
  const msg = document.getElementById('msg');
  if (msg) msg.textContent = 'Sending…';
  const r = await fetch('/a/{token}/' + k, {{method: 'POST'}});
  const j = await r.json();
  if (msg) {{
    msg.textContent = j.status === 'approved'
      ? 'Approved — returning to Band chat'
      : j.status === 'rejected'
      ? 'Rejected — returning to Band chat'
      : 'Done.';
  }}
  setTimeout(() => window.close(), 900);
}}
document.getElementById('ok')?.addEventListener('click', () => decide('approve'));
document.getElementById('no')?.addEventListener('click', () => decide('reject'));
if ('Notification' in window && Notification.permission === 'default') {{
  Notification.requestPermission();
}}
</script>"""

    page = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0d1117">
<title>Band — {inc}</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{
  width: 100%; height: 100%;
  background: transparent;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  overflow: hidden;
}}
body {{
  display: flex;
  align-items: flex-end;
  justify-content: flex-end;
  padding: 12px;
}}
.toast {{
  width: min(100%, 380px);
  background: #161b22;
  color: #e6edf3;
  border: 1px solid #30363d;
  border-radius: 16px;
  box-shadow: 0 12px 40px rgba(0,0,0,.45), 0 2px 8px rgba(0,0,0,.25);
  overflow: hidden;
  animation: slideUp .28s ease-out;
}}
@keyframes slideUp {{
  from {{ transform: translateY(16px); opacity: 0; }}
  to {{ transform: translateY(0); opacity: 1; }}
}}
.head {{
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px 8px;
}}
.icon {{
  width: 28px; height: 28px; border-radius: 8px;
  background: linear-gradient(135deg, #238636, #1f6feb);
  display: flex; align-items: center; justify-content: center;
  font-size: 14px; font-weight: 700; color: #fff;
  flex-shrink: 0;
}}
.meta {{ min-width: 0; flex: 1; }}
.app {{ font-size: 11px; color: #8b949e; letter-spacing: .02em; text-transform: uppercase; }}
.title {{ font-size: 14px; font-weight: 600; line-height: 1.3; margin-top: 2px; }}
.body {{
  padding: 0 14px 12px;
  font-size: 13px; line-height: 1.45; color: #9da7b3;
  max-height: 72px; overflow: hidden;
}}
.actions {{
  display: flex; gap: 8px;
  padding: 0 12px 12px;
}}
.btn {{
  flex: 1; border: 0; border-radius: 10px;
  padding: 10px 12px; font-size: 13px; font-weight: 600;
  cursor: pointer;
}}
.btn:disabled {{ opacity: .55; cursor: default; }}
.approve {{ background: #238636; color: #fff; }}
.reject {{ background: #21262d; color: #e6edf3; border: 1px solid #30363d; }}
.msg {{ text-align: center; font-size: 12px; color: #8b949e; padding: 0 12px 10px; min-height: 16px; }}
</style>
</head>
<body>
<article class="toast" role="dialog" aria-label="Band approval">
  <div class="head">
    <div class="icon" aria-hidden="true">B</div>
    <div class="meta">
      <div class="app">Band Agents</div>
      <div class="title">{inc}</div>
    </div>
  </div>
  <div class="body">{body}</div>
  {actions}
</article>
{script}
</body></html>"""
    return page.encode()


def _render_approval(token: str, rec: dict[str, Any]) -> bytes:
    inc = str(rec.get("incident_id") or "Review ready")
    summary = str(rec.get("summary") or "")
    return _render_toast_shell(title=inc, summary=summary, token=token, readonly=False)


def _ensure_server() -> int:
    global _server, _port
    with _lock:
        if _server is not None:
            return _port
        for candidate in range(_DEFAULT_PORT, _DEFAULT_PORT + 20):
            try:
                srv = ThreadingHTTPServer(("127.0.0.1", candidate), _Handler)
                _server = srv
                _port = candidate
                threading.Thread(target=srv.serve_forever, daemon=True, name="approval-server").start()
                logger.info("Approval server on http://127.0.0.1:%d", candidate)
                return candidate
            except OSError:
                continue
        raise RuntimeError("No free port for approval server")


def _notify_once(title: str, subtitle: str, message: str) -> None:
    """Short macOS banner — the Chrome toast is the primary UI."""
    safe_title = title.replace('"', '\\"')
    safe_sub = subtitle.replace('"', '\\"')
    safe_msg = message.replace('"', '\\"')
    try:
        subprocess.run(
            [
                "osascript",
                "-e",
                f'display notification "{safe_msg}" with title "{safe_title}" subtitle "{safe_sub}" sound name "Pop"',
            ],
            check=False,
            capture_output=True,
            timeout=5,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("notification failed: %s", exc)


def _open_approval_toast(url: str) -> str:
    """Open a small Chrome app window (notification-style), not a full browser tab."""
    for chrome in _CHROME_CANDIDATES:
        if not os.path.isfile(chrome):
            continue
        try:
            subprocess.run(
                [
                    chrome,
                    f"--app={url}",
                    f"--window-size={_TOAST_WIDTH},{_TOAST_HEIGHT}",
                    "--disable-features=Translate",
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
                check=False,
                capture_output=True,
                timeout=5,
            )
            logger.info("Opened approval toast via Chrome app window")
            return "chrome_app"
        except Exception as exc:  # noqa: BLE001
            logger.debug("Chrome toast open failed: %s", exc)

    try:
        # Background tab fallback — page is still toast-sized visually
        subprocess.run(["open", "-g", url], check=False, capture_output=True, timeout=5)
        return "browser_tab"
    except Exception:  # noqa: BLE001
        return "none"


def request_human_approval(
    summary: str, incident_id: str = "", room_id: str | None = None
) -> dict[str, Any]:
    room = room_id or get_current_room() or ""
    key = (room, incident_id or summary[:80])
    if key in _sent and _sent[key] in _pending:
        return {
            "ok": True,
            "skipped": "already_sent",
            "approval_url": f"http://127.0.0.1:{_port}/a/{_sent[key]}",
            "incident_id": incident_id,
            "room_id": room or None,
            "note": "Approval already requested for this incident — use the existing link.",
        }

    port = _ensure_server()
    token = secrets.token_urlsafe(8)
    _pending[token] = {
        "summary": summary,
        "incident_id": incident_id,
        "room_id": room or None,
        "status": "pending",
    }
    _sent[key] = token
    url = f"http://127.0.0.1:{port}/a/{token}"
    label = incident_id or "Review ready"
    _notify_once("Band", label, "Approve or reject in the toast")
    mode = _open_approval_toast(url)
    if not room:
        logger.warning("request_human_approval: no room_id — click will not post to Band chat")
    return {
        "ok": True,
        "approval_url": url,
        "incident_id": incident_id,
        "room_id": room or None,
        "ui_mode": mode,
        "note": (
            "Compact approval toast opened (Chrome notification-style). "
            "Tap Approve or Reject — no full browser page."
        ),
    }
