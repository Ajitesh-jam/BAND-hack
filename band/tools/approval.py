"""Human-approval via a desktop notification + one-click browser button.

When the reviewer approves and the change is merge-ready, the commander calls
``request_human_approval``. That:
  1. fires a macOS desktop notification, and
  2. opens a small local web page in the browser with an "Approve & merge" button.

Clicking the button posts the approval straight into the Band incident room (using
the commander's credentials) and closes the workflow — the human never has to type
"approve" in the chat. A reject button is also provided.

No third-party deps: a stdlib ThreadingHTTPServer runs in a daemon thread.
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

_lock = threading.Lock()
_server: ThreadingHTTPServer | None = None
_port: int = _DEFAULT_PORT
# token -> {summary, incident_id, room_id, status}
_pending: dict[str, dict[str, Any]] = {}


def _mentions_for(roles: list[str]) -> list[dict[str, Any]]:
    mentions: list[dict[str, Any]] = []
    for role in roles:
        try:
            creds = load_agent_config(role)
        except Exception:  # noqa: BLE001
            continue
        mentions.append(
            {"id": creds.agent_id, "handle": getattr(creds, "handle", None), "name": role}
        )
    return mentions


def _post_to_band(room_id: str, content: str, mention_roles: list[str]) -> None:
    """Post a message into the incident room as the commander."""
    creds = load_agent_config("commander")
    mentions = _mentions_for(mention_roles) or _mentions_for(["coder"])
    with BandAgentClient(creds.agent_id, creds.api_key) as client:
        client.send_message(room_id, content, mentions=mentions)


def _approve_message(rec: dict[str, Any]) -> str:
    inc = rec.get("incident_id") or "the change"
    return (
        f"\u2705 HUMAN APPROVED \u2014 {inc}.\n"
        f"The reviewed change is approved and merge-ready. "
        f"@coder open the PR (S8) if a GitHub token is configured and report; "
        f"otherwise the fix is merge-ready on its branch.\n"
        f"INCIDENT_RESOLVED \u2014 workflow complete."
    )


def _reject_message(rec: dict[str, Any]) -> str:
    inc = rec.get("incident_id") or "the change"
    return (
        f"\u274c HUMAN REJECTED \u2014 {inc}. The change was not approved. "
        f"ESCALATE \u2014 stopping the workflow; a human will follow up."
    )


def _decision_page(title: str, body: str) -> bytes:
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>{html.escape(title)}</title></head>
<body style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#0d1117;color:#e6edf3;
display:flex;align-items:center;justify-content:center;height:100vh;margin:0">
<div style="max-width:520px;text-align:center;padding:32px;background:#161b22;border-radius:14px;
border:1px solid #30363d">
<h2 style="margin-top:0">{html.escape(title)}</h2>
<p style="color:#9da7b3;line-height:1.5">{body}</p>
</div></body></html>""".encode()


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args: Any) -> None:  # silence default access logging
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
            token = parts[1]
            rec = _pending.get(token)
            if not rec:
                self._send(404, _decision_page("Not found", "This approval link is invalid or expired."))
                return
            if rec["status"] != "pending":
                self._send(
                    200,
                    _decision_page("Already decided", f"This change was already <b>{html.escape(rec['status'])}</b>."),
                )
                return
            self._send(200, _render_approval(token, rec))
            return
        self._send(404, _decision_page("Not found", "Unknown path."))

    def do_POST(self) -> None:  # noqa: N802
        parts = [p for p in self.path.split("?")[0].split("/") if p]
        if len(parts) == 3 and parts[0] == "a" and parts[2] in ("approve", "reject"):
            token, decision = parts[1], parts[2]
            rec = _pending.get(token)
            if not rec:
                self._send(404, b'{"ok":false,"error":"unknown token"}', "application/json")
                return
            if rec["status"] != "pending":
                self._send(200, b'{"ok":true,"status":"already_decided"}', "application/json")
                return
            rec["status"] = "approved" if decision == "approve" else "rejected"
            room_id = rec.get("room_id")
            if room_id:
                try:
                    msg = _approve_message(rec) if decision == "approve" else _reject_message(rec)
                    roles = ["coder", "commander"] if decision == "approve" else ["commander"]
                    _post_to_band(room_id, msg, roles)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Approval posted but Band message failed: %s", exc)
            self._send(200, json.dumps({"ok": True, "status": rec["status"]}).encode(), "application/json")
            return
        self._send(404, b'{"ok":false}', "application/json")


def _render_approval(token: str, rec: dict[str, Any]) -> bytes:
    inc = html.escape(str(rec.get("incident_id") or "Change"))
    summary = html.escape(str(rec.get("summary") or "")).replace("\n", "<br>")
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>Approve {inc}</title></head>
<body style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#0d1117;color:#e6edf3;
display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0">
<div style="max-width:640px;width:90%;padding:32px;background:#161b22;border-radius:14px;border:1px solid #30363d">
  <h2 style="margin-top:0">Review ready: {inc}</h2>
  <div style="background:#0d1117;border:1px solid #30363d;border-radius:10px;padding:16px;
       color:#c9d1d9;line-height:1.6;font-size:14px">{summary}</div>
  <div style="display:flex;gap:12px;margin-top:24px">
    <button id="ok" style="flex:1;padding:14px;border:0;border-radius:10px;background:#238636;color:#fff;
      font-size:15px;font-weight:600;cursor:pointer">Approve &amp; merge</button>
    <button id="no" style="flex:1;padding:14px;border:0;border-radius:10px;background:#da3633;color:#fff;
      font-size:15px;font-weight:600;cursor:pointer">Reject</button>
  </div>
  <p id="msg" style="text-align:center;color:#9da7b3;margin-top:18px"></p>
</div>
<script>
async function decide(kind) {{
  document.getElementById('ok').disabled = true;
  document.getElementById('no').disabled = true;
  document.getElementById('msg').textContent = 'Sending...';
  try {{
    const r = await fetch('/a/{token}/' + kind, {{method:'POST'}});
    const j = await r.json();
    document.getElementById('msg').textContent =
      (j.status === 'approved') ? '\u2705 Approved and sent to Band. You can close this tab.'
      : (j.status === 'rejected') ? '\u274c Rejected and sent to Band. You can close this tab.'
      : 'Done.';
  }} catch (e) {{ document.getElementById('msg').textContent = 'Error: ' + e; }}
}}
document.getElementById('ok').onclick = () => decide('approve');
document.getElementById('no').onclick = () => decide('reject');
</script>
</body></html>""".encode()


def _ensure_server() -> int:
    global _server, _port
    with _lock:
        if _server is not None:
            return _port
        port = _DEFAULT_PORT
        for candidate in range(_DEFAULT_PORT, _DEFAULT_PORT + 20):
            try:
                srv = ThreadingHTTPServer(("127.0.0.1", candidate), _Handler)
                port = candidate
                break
            except OSError:
                continue
        else:
            raise RuntimeError("No free port for approval server")
        _server = srv
        _port = port
        threading.Thread(target=srv.serve_forever, daemon=True, name="approval-server").start()
        logger.info("Approval server listening on http://127.0.0.1:%d", port)
        return port


def _notify(title: str, subtitle: str, message: str, url: str) -> None:
    """Best-effort macOS desktop notification + open the approval page in the browser."""
    try:
        subprocess.run(
            [
                "osascript", "-e",
                f'display notification "{message}" with title "{title}" '
                f'subtitle "{subtitle}" sound name "Glass"',
            ],
            check=False, capture_output=True, timeout=5,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("osascript notification failed: %s", exc)
    try:
        subprocess.run(["open", url], check=False, capture_output=True, timeout=5)
    except Exception as exc:  # noqa: BLE001
        logger.debug("could not open browser: %s", exc)


def request_human_approval(
    summary: str, incident_id: str = "", room_id: str | None = None
) -> dict[str, Any]:
    """Notify the human and open a one-click Approve/Reject page for the current room.

    The approval is posted back into the Band room automatically when clicked, so the
    human does not need to type anything in chat.
    """
    room = room_id or get_current_room()
    port = _ensure_server()
    token = secrets.token_urlsafe(8)
    _pending[token] = {
        "summary": summary,
        "incident_id": incident_id,
        "room_id": room,
        "status": "pending",
    }
    url = f"http://127.0.0.1:{port}/a/{token}"
    _notify(
        title="Band \u2014 approval needed",
        subtitle=incident_id or "Change ready to merge",
        message="Click to review & approve",
        url=url,
    )
    if not room:
        logger.warning("request_human_approval: no room_id; approval click cannot post to Band")
    return {
        "ok": True,
        "approval_url": url,
        "incident_id": incident_id,
        "room_id": room,
        "note": "Desktop notification sent and approval page opened in the browser.",
    }
