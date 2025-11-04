# app.py
# Insta Multi Welcome Bot — Working backend + Blue Neon Orbitron UI (single file)
# Usage:
#   pip install -r requirements.txt
#   python app.py
# For Render: Procfile -> web: python app.py

import os
import time
import json
import threading
from datetime import datetime
from flask import Flask, request, render_template_string, jsonify, send_file
from werkzeug.utils import secure_filename

from instagrapi import Client

# ---------- CONFIG ----------
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
SESSION_PATH = os.path.join(UPLOAD_FOLDER, "session.json")
WELCOME_PATH = os.path.join(UPLOAD_FOLDER, "welcome_messages.txt")
WELCOMED_CACHE = os.path.join(UPLOAD_FOLDER, "welcomed_cache.json")
LOG_FILE = os.path.join(UPLOAD_FOLDER, "bot_logs.txt")

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "replace-this-with-a-secure-key")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB

# runtime globals
bot_thread = None
bot_thread_lock = threading.Lock()
bot_stop_event = None
bot_status = {"running": False, "task_id": None, "started_at": None, "last_ping": None}
bot_logs = []

# ---------- helpers ----------
def now_iso():
    return datetime.now().isoformat()

def append_log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    bot_logs.append(line)
    if len(bot_logs) > 2000:
        del bot_logs[:500]
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line)

def load_welcomed_cache():
    try:
        if os.path.exists(WELCOMED_CACHE):
            with open(WELCOMED_CACHE, "r", encoding="utf-8") as f:
                arr = json.load(f)
                return set(arr)
    except Exception as e:
        append_log(f"Failed to load welcomed cache: {e}")
    return set()

def save_welcomed_cache(s):
    try:
        with open(WELCOMED_CACHE, "w", encoding="utf-8") as f:
            json.dump(list(s), f)
    except Exception as e:
        append_log(f"Failed to save welcomed cache: {e}")

# ---------- bot worker ----------
def instagram_bot_worker(task_id, cfg, stop_event):
    """
    cfg contains:
      username, password, session_file (optional), group_ids (list or csv string),
      welcome_mode ('file'|'single'|'split_by_line'), welcome_file (path), single_message,
      delay (float), poll_interval (float)
    """
    append_log(f"Task {task_id}: starting bot")
    bot_status["running"] = True
    bot_status["task_id"] = task_id
    bot_status["started_at"] = now_iso()

    cl = Client()

    # try load uploaded session if provided
    try:
        sess_path = cfg.get("session_file")
        if sess_path and os.path.exists(sess_path):
            try:
                with open(sess_path, "r", encoding="utf-8") as f:
                    settings = json.load(f)
                # instagrapi set_settings (older) or load_settings usage; use set_settings if available
                try:
                    cl.set_settings(settings)
                except Exception:
                    try:
                        cl.load_settings(sess_path)
                    except Exception:
                        pass
                append_log("Loaded session settings from uploaded file.")
                # Try login to validate (may be no-op)
                try:
                    cl.login(cfg.get("username") or "", cfg.get("password") or "")
                    append_log("Session validated via login attempt.")
                except Exception:
                    append_log("Login attempt after loading session settings failed (may still be authenticated).")
            except Exception as e:
                append_log(f"Saved session load failed: {e}. Will attempt fresh login if credentials provided.")
        elif os.path.exists(SESSION_PATH):
            try:
                # try load settings file created by instagrapi
                try:
                    cl.load_settings(SESSION_PATH)
                except Exception:
                    with open(SESSION_PATH, "r", encoding="utf-8") as f:
                        settings = json.load(f)
                    try:
                        cl.set_settings(settings)
                    except Exception:
                        pass
                # try login (may reuse session)
                try:
                    cl.login(cfg.get("username") or "", cfg.get("password") or "")
                    append_log("Loaded local session.json and attempted login.")
                except Exception:
                    append_log("Local session load: login after settings failed (session might still be valid).")
            except Exception as e:
                append_log(f"Local session load failed: {e}")
        else:
            append_log("No session file available on disk or provided upload.")
    except Exception as e:
        append_log(f"Session handling error: {e}")

    # ensure authentication (try fresh)
    try:
        # some versions have cl.authenticated, else we try to login if credentials provided
        authenticated = False
        try:
            authenticated = getattr(cl, "authenticated", False)
        except Exception:
            authenticated = False

        if not authenticated:
            if cfg.get("username") and cfg.get("password"):
                append_log("Attempting fresh login with provided credentials...")
                cl.login(cfg["username"], cfg["password"])
                # save session
                try:
                    cl.dump_settings(SESSION_PATH)
                    append_log(f"Saved new session to {SESSION_PATH}")
                except Exception as e:
                    append_log(f"Failed to save session: {e}")
            else:
                append_log("Not authenticated and no credentials supplied. Bot cannot proceed.")
                bot_status["running"] = False
                return
        else:
            append_log("Client authenticated (reused session).")
    except Exception as e:
        append_log(f"Login failed: {e}")
        bot_status["running"] = False
        return

    # prepare welcome messages
    welcome_messages = []
    try:
        mode = cfg.get("welcome_mode", "file")
        if mode == "file":
            path = cfg.get("welcome_file") or WELCOME_PATH
            if path and os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                welcome_messages = [m.strip() for m in content.split("===") if m.strip()]
                append_log(f"Loaded {len(welcome_messages)} messages from file.")
            else:
                append_log("Welcome file not found for mode 'file'.")
        elif mode == "single":
            single = cfg.get("single_message") or ""
            welcome_messages = [line.strip() for line in single.splitlines() if line.strip()]
            append_log(f"Using single-message input broken into {len(welcome_messages)} messages.")
        elif mode == "split_by_line":
            path = cfg.get("welcome_file") or WELCOME_PATH
            if path and os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                welcome_messages = [line.strip() for line in content.splitlines() if line.strip()]
                append_log(f"Loaded {len(welcome_messages)} lines as messages from file.")
            else:
                append_log("Welcome file not found (split_by_line).")
        else:
            append_log("Unknown welcome_mode; no messages loaded.")
    except Exception as e:
        append_log(f"Error preparing welcome messages: {e}")

    if not welcome_messages:
        append_log("No welcome messages to send. Stopping bot.")
        bot_status["running"] = False
        return

    # prepare group ids
    group_ids = cfg.get("group_ids", [])
    if isinstance(group_ids, str):
        group_ids = [g.strip() for g in group_ids.split(",") if g.strip()]
    append_log(f"Configured group IDs: {group_ids}")

    welcomed = load_welcomed_cache()

    delay = float(cfg.get("delay", 2))
    poll_interval = float(cfg.get("poll_interval", 6))
    append_log(f"Delay between messages: {delay}s, poll interval: {poll_interval}s")

    # helper to send messages
    def send_messages_to_thread(thread_id, target_username, target_user_pk=None):
        for m in welcome_messages:
            if stop_event.is_set():
                return
            msg = m.replace("{username}", target_username)
            try:
                cl.direct_send(msg, thread_ids=[thread_id])
                append_log(f"Sent to @{target_username} in thread {thread_id}: {msg[:60]}")
            except Exception as e:
                try:
                    if target_user_pk:
                        cl.direct_send(msg, user_ids=[target_user_pk])
                        append_log(f"Fallback: sent to @{target_username} by user id.")
                    else:
                        append_log(f"Send failed for @{target_username} in thread {thread_id}: {e}")
                except Exception as e2:
                    append_log(f"Final send error for @{target_username}: {e2}")
            time.sleep(delay)

    # main loop
    try:
        while not stop_event.is_set():
            bot_status["last_ping"] = now_iso()
            for thread_id in group_ids:
                if stop_event.is_set():
                    break
                try:
                    thread = cl.direct_thread(thread_id)
                    users = getattr(thread, "users", []) or []
                    for user in users:
                        if stop_event.is_set():
                            break
                        username = getattr(user, "username", None) or str(getattr(user, "pk", "unknown"))
                        user_pk = getattr(user, "pk", None)
                        if username == cfg.get("username"):
                            continue
                        key = f"{thread_id}::{username}"
                        if key not in welcomed:
                            append_log(f"New user detected: @{username} in thread {thread_id}")
                            send_messages_to_thread(thread_id, username, target_user_pk=user_pk)
                            welcomed.add(key)
                            save_welcomed_cache(welcomed)
                except Exception as e:
                    append_log(f"Error reading thread {thread_id}: {e}")
            # responsive sleep
            slept = 0.0
            while slept < poll_interval:
                if stop_event.is_set():
                    break
                time.sleep(0.5)
                slept += 0.5
    except Exception as e:
        append_log(f"Worker loop exception: {e}")
    finally:
        try:
            bot_status["running"] = False
            bot_status["task_id"] = None
            append_log(f"Task {task_id}: stopped.")
        except Exception:
            pass

# ---------- UI: Blue Neon Orbitron design ----------
PAGE_HTML = r'''
<!doctype html>
<html lang="en"><head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>INSTA MULTI WELCOME BOT</title>
  <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&display=swap" rel="stylesheet">
  <style>
    :root{
      --bg1:#020217; --bg2:#03102a;
      --neon:#00f6ff; --accent:#7a4cff;
    }
    *{box-sizing:border-box}
    body{
      margin:0; min-height:100vh; font-family: 'Orbitron', monospace;
      background: radial-gradient(circle at 10% 10%, rgba(0,246,255,0.03), transparent 8%),
                  linear-gradient(120deg,var(--bg1),var(--bg2));
      color:#dff8ff; display:flex; align-items:center; justify-content:center; padding:24px;
    }
    .card{ width:100%; max-width:980px; background:rgba(8,10,20,0.8); padding:26px; border-radius:16px; box-shadow:0 10px 40px rgba(0,0,0,0.6); border:1px solid rgba(255,255,255,0.03); position:relative; overflow:hidden;}
    .title { font-size:28px; font-weight:900; color:var(--neon); text-shadow:0 0 12px rgba(0,246,255,0.12); margin-bottom:6px;}
    .subtitle { color:#9fd8e8; margin-bottom:18px;}
    .row{ display:flex; gap:12px; margin-bottom:12px; align-items:center; }
    label{ width:220px; color:#bfeffc; font-size:13px; }
    input, textarea, select { flex:1; padding:10px 12px; border-radius:8px; border:1px solid rgba(255,255,255,0.05); background: rgba(255,255,255,0.02); color:#eafcff; font-size:14px;}
    textarea{ min-height:90px; resize:vertical;}
    .small{ width:160px; }
    button{ padding:10px 14px; border-radius:10px; border:none; cursor:pointer; font-weight:700; color:#001218; background:linear-gradient(90deg,var(--neon),var(--accent)); }
    .btn-stop{ background:linear-gradient(90deg,#ff5f6d,#ffc371); color:#111; }
    .panel{ margin-top:18px; display:flex; gap:18px; }
    .panel>div{ flex:1; background: rgba(255,255,255,0.02); padding:12px; border-radius:10px; min-height:150px; }
    pre{ white-space:pre-wrap; word-break:break-word; font-size:13px; color:#dff8ff; background:transparent; border:none; }
    .muted{ color:#8bbfcc; font-size:13px; }
    .note{ font-size:13px; color:#b8f3ff; margin-top:8px;}
    .bg-lines{ position:absolute; inset:0; pointer-events:none; opacity:0.06; background-image: repeating-linear-gradient(90deg, rgba(255,255,255,0.02) 0 1px, transparent 1px 40px); transform:skewY(-3deg); }
    .footer{ margin-top:12px; font-size:12px; color:#9fd8e8; text-align:center;}
    @media (max-width:980px){ .row{ display:block; } label{ width:100%; margin-bottom:6px; } }
  </style>
</head>
<body>
  <div class="card">
    <div class="bg-lines"></div>
    <div style="display:flex;justify-content:space-between;align-items:center;">
      <div>
        <div class="title">INSTA MULTI WELCOME BOT</div>
        <div class="subtitle">Blue Neon • Orbitron • Auto-session • Multi-group</div>
      </div>
      <div class="muted">Status:
        <span id="statusText" style="font-weight:900; color:#ffd6d6">Stopped</span>
      </div>
    </div>

    <form id="controlForm" method="post" action="/start" enctype="multipart/form-data">
      <div class="row"><label>Instagram Username</label><input name="username" type="text" placeholder="username (optional if session.json exists)"/></div>
      <div class="row"><label>Password</label><input name="password" type="password" placeholder="password (only if fresh login)"/></div>
      <div class="row"><label>Upload session.json</label><input name="session_file" type="file" accept=".json" /></div>
      <div class="row"><label>Upload welcome_messages.txt (use === as separators)</label><input name="welcome_file" type="file" accept=".txt" /></div>
      <div class="row"><label>Or paste single welcome message (new lines => separate messages)</label><textarea name="single_message" rows="3"></textarea></div>
      <div class="row"><label>Welcome mode</label>
        <select name="welcome_mode">
          <option value="file">File (===)</option>
          <option value="single">Single (split by newline)</option>
          <option value="split_by_line">Split by line</option>
        </select>
      </div>
      <div class="row"><label>Group Chat IDs (comma separated)</label><input name="group_ids" type="text" placeholder="e.g. 24632887389663044,123..." /></div>
      <div class="row"><label>Delay between messages (sec)</label><input name="delay" value="2" class="small" /><label style="width:120px">Poll interval (sec)</label><input name="poll_interval" value="6" class="small" /></div>

      <div style="display:flex;gap:12px;margin-top:12px;">
        <button type="submit" class="btn-start">Start Bot</button>
        <button formaction="/stop" formmethod="post" class="btn-stop">Stop Bot</button>
        <a href="/download_sample" style="text-decoration:none"><button type="button" style="background:linear-gradient(90deg,#8be8a9,#7ab4ff); color:#001;">Download sample</button></a>
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

    <div class="footer">Tip: Keep this service private. Do not commit session.json to public repos.</div>
  </div>

<script>
  // periodically update logs and status
  async function refreshStatus(){
    try{
      const r = await fetch('/status');
      const j = await r.json();
      document.getElementById('logs').innerText = j.logs.join('\\n');
      document.getElementById('statusText').innerText = j.running ? 'Running' : 'Stopped';
    }catch(e){}
  }
  setInterval(refreshStatus, 3000);
  refreshStatus();
</script>
</body>
</html>
'''

@app.route("/")
def index():
    small_logs = bot_logs[-400:]
    welcomed = load_welcomed_cache()
    return render_template_string(PAGE_HTML, logs="\n".join(small_logs[::-1]) if small_logs else "No logs yet.", status=bot_status, welcomed_count=len(welcomed))

@app.route("/download_sample")
def download_sample():
    sample = ("Hey @{username} 👋 Welcome to the group! 🚀\n===\n🎉 @{username}, glad to have you here! 🥳\n===\nWelcome, @{username}!\n")
    path = os.path.join(UPLOAD_FOLDER, "sample_welcome.txt")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(sample)
        return send_file(path, as_attachment=True, download_name="welcome_messages_sample.txt")
    except Exception as e:
        append_log(f"Failed to create sample file: {e}")
        return jsonify({"ok": False, "message": "Failed to create sample."})

@app.route("/start", methods=["POST"])
def start_bot():
    global bot_thread, bot_stop_event
    if bot_status.get("running"):
        # already running
        return render_template_string(PAGE_HTML, logs="\n".join(bot_logs[-400:][::-1]), status=bot_status, welcomed_count=len(load_welcomed_cache()))

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
            dest = os.path.join(app.config["UPLOAD_FOLDER"], "uploaded_session.json")
            f.save(dest)
            session_file_path = dest
            append_log(f"Uploaded session file saved to {dest}")

    welcome_file_path = None
    if "welcome_file" in request.files:
        f = request.files["welcome_file"]
        if f and f.filename:
            dest = os.path.join(app.config["UPLOAD_FOLDER"], "uploaded_welcome.txt")
            f.save(dest)
            welcome_file_path = dest
            append_log(f"Uploaded welcome file saved to {dest}")

    if not welcome_file_path and os.path.exists(WELCOME_PATH):
        welcome_file_path = WELCOME_PATH

    cfg = {
        "username": username.strip() if username else None,
        "password": password.strip() if password else None,
        "session_file": session_file_path,
        "group_ids": group_ids,
        "welcome_mode": welcome_mode,
        "welcome_file": welcome_file_path,
        "single_message": single_message,
        "delay": float(delay),
        "poll_interval": float(poll_interval)
    }

    bot_stop_event = threading.Event()
    bot_task_id = f"TASK-{int(time.time())}"

    bot_thread = threading.Thread(target=instagram_bot_worker, args=(bot_task_id, cfg, bot_stop_event), daemon=True)
    bot_thread.start()
    append_log(f"Started bot task {bot_task_id}")
    return render_template_string(PAGE_HTML, logs="\n".join(bot_logs[-400:][::-1]), status=bot_status, welcomed_count=len(load_welcomed_cache()))

@app.route("/stop", methods=["POST"])
def stop_bot():
    global bot_stop_event
    if bot_stop_event:
        bot_stop_event.set()
        append_log("Stop signal sent to bot.")
    else:
        append_log("No active bot to stop.")
    return render_template_string(PAGE_HTML, logs="\n".join(bot_logs[-400:][::-1]), status=bot_status, welcomed_count=len(load_welcomed_cache()))

@app.route("/status")
def status_api():
    welcomed = load_welcomed_cache()
    return jsonify({
        "running": bot_status.get("running"),
        "task_id": bot_status.get("task_id"),
        "logs": bot_logs[-300:],
        "welcomed_count": len(welcomed)
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    append_log(f"Starting Flask on 0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
