"""
app.py - Flask web UI + Instagram welcome bot controller (single-file)

Usage:
    pip install flask instagrapi
    python app.py
Then open http://127.0.0.1:5000

Files created/used by the app:
 - uploaded session files saved to ./uploads/session.json
 - uploaded welcome messages saved to ./uploads/welcome_messages.txt
 - welcomed cache saved to ./welcomed_cache.json
"""

import os
import time
import json
import threading
from datetime import datetime
from flask import (
    Flask, request, render_template_string, redirect, url_for, flash, jsonify, send_file
)
from werkzeug.utils import secure_filename

# pip install instagrapi
from instagrapi import Client

# --------------- CONFIG ---------------
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
SESSION_PATH = os.path.join(UPLOAD_FOLDER, "session.json")
WELCOME_PATH = os.path.join(UPLOAD_FOLDER, "welcome_messages.txt")
WELCOME_CACHE = "welcomed_cache.json"
LOG_FILE = "bot_logs.txt"

# Flask app
app = Flask(__name__)
app.secret_key = "replace-with-a-secure-random-key"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB upload limit

# Bot runtime globals
bot_thread = None
bot_thread_lock = threading.Lock()
bot_stop_event = None
bot_task_id = None
bot_status = {"running": False, "task_id": None, "started_at": None, "last_ping": None}
bot_logs = []

# Simple helper for logs
def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    bot_logs.append(line)
    # trim logs kept in-memory to avoid memory growth
    if len(bot_logs) > 2000:
        del bot_logs[:500]
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line)

# Save/load welcomed cache to persist between restarts
def load_welcomed_cache():
    if os.path.exists(WELCOME_CACHE):
        try:
            with open(WELCOME_CACHE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_welcomed_cache(cache_set):
    try:
        with open(WELCOME_CACHE, "w", encoding="utf-8") as f:
            json.dump(list(cache_set), f)
    except Exception as e:
        log(f"Error saving welcomed cache: {e}")

# ---------------- Bot worker ----------------
def instagram_bot_worker(task_id, cfg, stop_event):
    """
    cfg is a dict:
    {
      "username": str or None,
      "password": str or None,
      "session_file": path or None,
      "group_ids": [str,...],
      "welcome_mode": "file"|"single"|"split_by_line",
      "welcome_file": path or None,
      "single_message": str or None,
      "delay": float (seconds between messages),
      "poll_interval": float (seconds between checks of new members)
    }
    """
    log(f"Task {task_id}: starting bot")
    bot_status["running"] = True
    bot_status["task_id"] = task_id
    bot_status["started_at"] = datetime.now().isoformat()
    cl = Client()

    # Load session if exists
    try:
        if cfg.get("session_file") and os.path.exists(cfg["session_file"]):
            try:
                with open(cfg["session_file"], "r", encoding="utf-8") as f:
                    settings = json.load(f)
                cl.set_settings(settings)
                log("Loaded session settings from uploaded file.")
                # try login using saved settings
                cl.login(cfg.get("username") or "", cfg.get("password") or "")
                log("Session login OK (via settings).")
            except Exception as e:
                log(f"Saved session load failed: {e}. Will attempt fresh login if credentials provided.")
        elif os.path.exists(SESSION_PATH):
            try:
                with open(SESSION_PATH, "r", encoding="utf-8") as f:
                    settings = json.load(f)
                cl.set_settings(settings)
                cl.login(cfg.get("username") or "", cfg.get("password") or "")
                log("Loaded local session.json and logged in.")
            except Exception as e:
                log(f"Local session load failed: {e}")
        else:
            log("No session available.")
    except Exception as e:
        log(f"Session handling error: {e}")

    # If not logged in, try fresh login with username/password
    try:
        if not cl.authenticated:
            if cfg.get("username") and cfg.get("password"):
                log("Attempting fresh login with username & password...")
                cl.login(cfg["username"], cfg["password"])
                # save session to SESSION_PATH
                try:
                    with open(SESSION_PATH, "w", encoding="utf-8") as f:
                        json.dump(cl.get_settings(), f)
                    log("Saved new session to " + SESSION_PATH)
                except Exception as e:
                    log(f"Failed to save session: {e}")
            else:
                log("Not authenticated and no credentials supplied. Bot cannot proceed.")
                bot_status["running"] = False
                return
        else:
            log("Already authenticated.")
    except Exception as e:
        log(f"Login failed: {e}")
        bot_status["running"] = False
        return

    # Prepare welcome messages
    welcome_messages = []
    try:
        mode = cfg.get("welcome_mode", "file")
        if mode == "file":
            path = cfg.get("welcome_file") or WELCOME_PATH
            if path and os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                # messages separated by '==='
                welcome_messages = [m.strip() for m in content.split("===") if m.strip()]
                log(f"Loaded {len(welcome_messages)} messages from file.")
            else:
                log("Welcome file not found.")
        elif mode == "single":
            single = cfg.get("single_message") or ""
            # split by newline into multiple messages
            welcome_messages = [line.strip() for line in single.splitlines() if line.strip()]
            log(f"Using single-message input broken into {len(welcome_messages)} messages.")
        elif mode == "split_by_line":
            path = cfg.get("welcome_file") or WELCOME_PATH
            if path and os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                # send each non-empty line separately:
                welcome_messages = [line.strip() for line in content.splitlines() if line.strip()]
                log(f"Loaded {len(welcome_messages)} lines as messages from file.")
            else:
                log("Welcome file not found (split_by_line).")
        else:
            log("Unknown welcome_mode; no messages loaded.")
    except Exception as e:
        log(f"Error preparing welcome messages: {e}")

    if not welcome_messages:
        log("No welcome messages to send. Stopping bot.")
        bot_status["running"] = False
        return

    # Prepare group ids
    group_ids = cfg.get("group_ids", [])
    if isinstance(group_ids, str):
        group_ids = [g.strip() for g in group_ids.split(",") if g.strip()]
    log(f"Configured group IDs: {group_ids}")

    # Load welcomed cache
    welcomed = load_welcomed_cache()

    delay = float(cfg.get("delay", 2))
    poll_interval = float(cfg.get("poll_interval", 6))
    log(f"Delay between messages: {delay}s, poll interval: {poll_interval}s")

    # Helper to send messages for a user in a thread
    def send_messages_to_thread(thread_id, target_username, target_user_pk=None):
        for m in welcome_messages:
            if stop_event.is_set():
                return
            msg = m.replace("{username}", target_username)
            try:
                # instagrapi direct_send expects thread_ids or user ids; we attempt with thread id first
                cl.direct_send(msg, thread_ids=[thread_id])
                log(f"Sent to @{target_username} in thread {thread_id}: {msg[:60]}")
            except Exception as e:
                # fallback: try with user id if available
                try:
                    if target_user_pk:
                        cl.direct_send(msg, user_ids=[target_user_pk])
                        log(f"Fallback: sent to @{target_username} by user id.")
                    else:
                        log(f"Send failed for @{target_username} in thread {thread_id}: {e}")
                except Exception as e2:
                    log(f"Final send error for @{target_username}: {e2}")
            time.sleep(delay)

    # MAIN LOOP: poll threads, find users, welcome new ones
    try:
        while not stop_event.is_set():
            bot_status["last_ping"] = datetime.now().isoformat()
            for thread_id in group_ids:
                if stop_event.is_set():
                    break
                try:
                    # fetch thread
                    thread = cl.direct_thread(thread_id)
                    users = getattr(thread, "users", []) or []
                    for user in users:
                        if stop_event.is_set():
                            break
                        username = getattr(user, "username", None) or str(getattr(user, "pk", "unknown"))
                        user_pk = getattr(user, "pk", None)
                        # don't welcome self
                        if username == cfg.get("username"):
                            continue
                        # check welcomed set
                        key = f"{thread_id}::{username}"
                        if key not in welcomed:
                            log(f"New user detected: @{username} in thread {thread_id}")
                            # send welcome messages (each message separately as requested)
                            send_messages_to_thread(thread_id, username, target_user_pk=user_pk)
                            welcomed.add(key)
                            save_welcomed_cache(welcomed)
                        else:
                            # already welcomed
                            pass
                except Exception as e:
                    log(f"Error reading thread {thread_id}: {e}")
            # sleep poll interval
            for _ in range(int(max(1, poll_interval))):
                if stop_event.is_set():
                    break
                time.sleep(1)
    except Exception as e:
        log(f"Worker loop exception: {e}")
    finally:
        # cleanup
        try:
            bot_status["running"] = False
            bot_status["task_id"] = None
            log(f"Task {task_id}: stopped.")
        except Exception:
            pass


# --------------- Flask routes & UI ---------------
INDEX_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Insta Multi Welcome Bot - Control Panel</title>
  <style>
    /* Neon + background */
    body {
      margin: 0;
      font-family: Inter, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial;
      min-height: 100vh;
      background: radial-gradient(circle at 10% 10%, rgba(0,255,200,0.06), transparent 10%),
                  linear-gradient(120deg, rgba(10,10,30,1), rgba(5,5,20,1));
      color: #e6f7ff;
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 40px;
    }
    .card {
      width: 100%;
      max-width: 980px;
      background: rgba(8,10,20,0.7);
      border-radius: 16px;
      box-shadow: 0 10px 40px rgba(0,0,0,0.6);
      padding: 26px;
      border: 1px solid rgba(255,255,255,0.03);
      position: relative;
      overflow: hidden;
    }
    .neon-title {
      font-size: 28px;
      font-weight: 700;
      letter-spacing: 0.6px;
      color: #00f6ff;
      text-shadow:
         0 0 6px rgba(0,246,255,0.25),
         0 0 20px rgba(0,246,255,0.12);
      margin-bottom: 6px;
      display: inline-block;
    }
    .subtitle { color: #9fd8e8; margin-bottom: 20px; display:block; }
    form .row { display:flex; gap:12px; margin-bottom:12px; }
    label { font-size:13px; color:#bfeffc; width:160px; }
    input[type="text"], input[type="password"], textarea, select {
      flex:1;
      padding:10px 12px;
      border-radius:8px;
      border:1px solid rgba(255,255,255,0.05);
      background: rgba(255,255,255,0.02);
      color: #eafcff;
      font-size:14px;
    }
    .small { width:160px; }
    button {
      background: linear-gradient(90deg,#00f6ff,#7a4cff);
      border: none;
      padding:10px 14px;
      color:#001218;
      font-weight:700;
      border-radius:10px;
      cursor:pointer;
    }
    .btn-danger { background: linear-gradient(90deg,#ff5f6d,#ffc371); color:#111; }
    .panel { margin-top:18px; display:flex; gap:18px; }
    .panel > div { flex:1; background: rgba(255,255,255,0.02); padding:12px; border-radius:10px; min-height:150px; }
    pre { white-space:pre-wrap; word-break:break-word; font-size:13px; color:#dff8ff; }
    .muted { color:#8bbfcc; font-size:13px; }
    .note { font-size:13px; color:#b8f3ff; margin-top:8px;}
    .separator { height:1px; background: rgba(255,255,255,0.03); margin:12px 0; }
    .footer { margin-top:12px; font-size:12px; color:#9fd8e8; }
    /* animated background lines */
    .bg-lines {
      position:absolute; inset:0; pointer-events:none; opacity:0.06;
      background-image: repeating-linear-gradient(90deg, rgba(255,255,255,0.02) 0 1px, transparent 1px 40px);
      transform: skewY(-3deg);
    }
  </style>
</head>
<body>
  <div class="card">
    <div class="bg-lines"></div>
    <div style="display:flex;justify-content:space-between;align-items:center;">
      <div>
        <div class="neon-title">INSTA MULTI WELCOME BOT</div>
        <div class="subtitle">Upload session.json • Upload welcome file • Start / Stop • Multi-group • 24/7</div>
      </div>
      <div class="muted">Status:
        {% if status.running %}
          <strong style="color:#aaffc7"> Running ({{ status.task_id }})</strong>
        {% else %}
          <strong style="color:#ffd6d6">Stopped</strong>
        {% endif %}
      </div>
    </div>

    <div class="separator"></div>

    <form id="controlForm" method="post" action="/start" enctype="multipart/form-data">
      <div class="row">
        <label>Instagram Username</label>
        <input name="username" type="text" placeholder="username (optional if session.json uploaded)" />
      </div>

      <div class="row">
        <label>Password</label>
        <input name="password" type="password" placeholder="password (only for fresh login)" />
      </div>

      <div class="row">
        <label>Upload session.json</label>
        <input name="session_file" type="file" accept=".json" />
      </div>

      <div class="row">
        <label>Upload welcome_messages.txt</label>
        <input name="welcome_file" type="file" accept=".txt" />
      </div>

      <div class="row">
        <label>Or paste single welcome message</label>
        <textarea name="single_message" rows="3" placeholder="Type message here. Use {username} placeholder. New lines become separate messages."></textarea>
      </div>

      <div class="row">
        <label>Welcome mode</label>
        <select name="welcome_mode">
          <option value="file">File (use === to separate messages)</option>
          <option value="single">Single message (split by newline)</option>
          <option value="split_by_line">Split by line (each line = message)</option>
        </select>
      </div>

      <div class="row">
        <label>Group Chat IDs (comma separated)</label>
        <input name="group_ids" type="text" placeholder="e.g. 24632887389663044, 123456789012345" />
      </div>

      <div class="row">
        <label>Delay between messages (sec)</label>
        <input name="delay" type="text" value="2" class="small" />
        <label style="width:120px">Poll interval (sec)</label>
        <input name="poll_interval" type="text" value="6" class="small" />
      </div>

      <div style="display:flex;gap:12px;margin-top:12px;">
        <button type="submit">Start Bot</button>
        <button formaction="/stop" formmethod="post" class="btn-danger">Stop Bot</button>
        <a href="/download_sample" style="text-decoration:none"><button type="button">Download sample welcome file</button></a>
      </div>
    </form>

    <div class="panel">
      <div>
        <h4 style="margin:6px 0">Logs</h4>
        <pre id="logs">{{ logs }}</pre>
      </div>
      <div>
        <h4 style="margin:6px 0">Runtime Info</h4>
        <div class="note"><b>Task ID:</b> {{ status.task_id or '—' }}</div>
        <div class="note"><b>Started at:</b> {{ status.started_at or '—' }}</div>
        <div class="note"><b>Last ping:</b> {{ status.last_ping or '—' }}</div>
        <div class="note"><b>Welcomed cache size:</b> {{ welcomed_count }}</div>
      </div>
    </div>

    <div class="footer">Tip: Use private server, keep credentials safe. Replace background image in CSS if desired.</div>
  </div>

  <script>
    // Poll logs every 4s
    setInterval(() => {
      fetch("/status").then(r => r.json()).then(data => {
        document.getElementById("logs").innerText = data.logs.join("\\n");
      }).catch(e => {});
    }, 4000);
  </script>
</body>
</html>
"""

@app.route("/")
def index():
    # show last 200 log lines
    small_logs = bot_logs[-400:]
    welcomed = load_welcomed_cache()
    return render_template_string(
        INDEX_HTML,
        logs="\n".join(small_logs[::-1]) if small_logs else "No logs yet.",
        status=bot_status,
        welcomed_count=len(welcomed)
    )

@app.route("/download_sample")
def download_sample():
    sample = (
        "Hey @{username} 👋 Welcome to the group! 🚀\n"
        "===\n"
        "🎉 @{username}, glad to have you here! 🥳\n"
        "===\n"
        "Welcome, @{username}!\n"
        "▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒\n"
        "🚀 Let's make this place awesome!\n"
    )
    path = os.path.join(UPLOAD_FOLDER, "sample_welcome.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(sample)
    return send_file(path, as_attachment=True, download_name="welcome_messages_sample.txt")

@app.route("/start", methods=["POST"])
def start_bot():
    global bot_thread, bot_stop_event, bot_task_id

    # if already running, return
    if bot_status.get("running"):
        flash("Bot already running", "info")
        return redirect(url_for("index"))

    username = request.form.get("username") or ""
    password = request.form.get("password") or ""
    group_ids = request.form.get("group_ids") or ""
    delay = request.form.get("delay") or "2"
    poll_interval = request.form.get("poll_interval") or "6"
    welcome_mode = request.form.get("welcome_mode") or "file"
    single_message = request.form.get("single_message") or ""

    # handle file uploads
    session_file_path = None
    if "session_file" in request.files:
        f = request.files["session_file"]
        if f and f.filename:
            fname = secure_filename(f.filename)
            dest = os.path.join(app.config["UPLOAD_FOLDER"], "uploaded_session.json")
            f.save(dest)
            session_file_path = dest
            log(f"Uploaded session file saved to {dest}")

    welcome_file_path = None
    if "welcome_file" in request.files:
        f = request.files["welcome_file"]
        if f and f.filename:
            fname = secure_filename(f.filename)
            dest = os.path.join(app.config["UPLOAD_FOLDER"], "uploaded_welcome.txt")
            f.save(dest)
            welcome_file_path = dest
            log(f"Uploaded welcome file saved to {dest}")

    # if welcome file not uploaded but a server-side welcome file exists, use that
    if not w
