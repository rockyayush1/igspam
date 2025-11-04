# app.py
# Insta Multi Welcome Bot — working backend + simple large-layout UI + multi welcome file support
# Usage:
#   pip install -r requirements.txt
#   python app.py
# Render: add Procfile -> web: python app.py

import os
import threading
import time
import json
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify, redirect, url_for, send_file
from werkzeug.utils import secure_filename
from instagrapi import Client

# ---------- config ----------
UPLOADS = "uploads"
os.makedirs(UPLOADS, exist_ok=True)

SESSION_FILE = os.path.join(UPLOADS, "session.json")
WELCOME_UPLOAD = os.path.join(UPLOADS, "uploaded_welcome.txt")
WELCOMED_CACHE = os.path.join(UPLOADS, "welcomed_cache.json")
LOG_FILE = os.path.join(UPLOADS, "bot_logs.txt")

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "replace-with-secure-key")
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024  # 12 MB

# ---------- runtime globals ----------
BOT_THREAD = None
BOT_THREAD_LOCK = threading.Lock()
BOT_STOP_EVENT = None
BOT_STATUS = {"running": False, "task_id": None, "started_at": None, "last_ping": None}
BOT_LOGS = []

# ---------- helpers ----------
def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def append_log(msg):
    line = f"[{now_str()}] {msg}"
    BOT_LOGS.append(line)
    if len(BOT_LOGS) > 4000:
        del BOT_LOGS[:1000]
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
        append_log(f"Could not load welcomed cache: {e}")
    return set()

def save_welcomed_cache(s):
    try:
        with open(WELCOMED_CACHE, "w", encoding="utf-8") as f:
            json.dump(list(s), f)
    except Exception as e:
        append_log(f"Could not save welcomed cache: {e}")

# ---------- bot worker (kept same working logic) ----------
def run_bot(task_id, cfg, stop_event):
    """
    cfg:
      username, password,
      session_file (optional path),
      group_ids (list),
      welcome_messages (list),
      delay (float), poll_interval (float)
    """
    append_log(f"Task {task_id}: starting")
    BOT_STATUS["running"] = True
    BOT_STATUS["task_id"] = task_id
    BOT_STATUS["started_at"] = now_str()

    cl = Client()

    # try load provided or existing session
    try:
        sess_path = cfg.get("session_file")
        if sess_path and os.path.exists(sess_path):
            try:
                # try load_settings then set_settings fallback
                try:
                    cl.load_settings(sess_path)
                    append_log("Loaded uploaded session via load_settings.")
                except Exception:
                    with open(sess_path, "r", encoding="utf-8") as f:
                        settings = json.load(f)
                    try:
                        cl.set_settings(settings)
                        append_log("Loaded uploaded session via set_settings.")
                    except Exception:
                        append_log("Loaded session file but client may still require login.")
            except Exception as e:
                append_log(f"Failed loading uploaded session: {e}")
        elif os.path.exists(SESSION_FILE):
            try:
                try:
                    cl.load_settings(SESSION_FILE)
                    append_log("Loaded local session via load_settings.")
                except Exception:
                    with open(SESSION_FILE, "r", encoding="utf-8") as f:
                        settings = json.load(f)
                    try:
                        cl.set_settings(settings)
                        append_log("Loaded local session via set_settings.")
                    except Exception:
                        append_log("Local session set but may require login.")
            except Exception as e:
                append_log(f"Local session load error: {e}")
        else:
            append_log("No session file found; will attempt fresh login.")
    except Exception as e:
        append_log(f"Session handling error: {e}")

    # ensure authenticated (try login if necessary)
    try:
        is_auth = False
        try:
            is_auth = getattr(cl, "authenticated", False)
        except Exception:
            is_auth = False

        if not is_auth:
            if cfg.get("username") and cfg.get("password"):
                append_log("Attempting fresh login with provided credentials...")
                cl.login(cfg["username"], cfg["password"])
                try:
                    cl.dump_settings(SESSION_FILE)
                    append_log(f"Saved new session to {SESSION_FILE}")
                except Exception as e:
                    append_log(f"Failed to save session: {e}")
            else:
                append_log("Not authenticated and no credentials provided. Stopping.")
                BOT_STATUS["running"] = False
                return
        else:
            append_log("Client authenticated (reused session).")
    except Exception as e:
        append_log(f"Login failed: {e}")
        BOT_STATUS["running"] = False
        return

    welcome_messages = cfg.get("welcome_messages", []) or []
    if not welcome_messages:
        append_log("No welcome messages provided - stopping.")
        BOT_STATUS["running"] = False
        return

    group_ids = cfg.get("group_ids", []) or []
    if isinstance(group_ids, str):
        group_ids = [g.strip() for g in group_ids.split(",") if g.strip()]

    if not group_ids:
        append_log("No group IDs provided - stopping.")
        BOT_STATUS["running"] = False
        return

    append_log(f"Monitoring groups: {group_ids}")
    welcomed = load_welcomed_cache()
    delay = float(cfg.get("delay", 2))
    poll_interval = float(cfg.get("poll_interval", 6))
    append_log(f"Delay {delay}s, Poll interval {poll_interval}s")

    try:
        while not stop_event.is_set():
            BOT_STATUS["last_ping"] = now_str()
            for thread_id in group_ids:
                if stop_event.is_set():
                    break
                try:
                    thread = cl.direct_thread(thread_id)
                    users = getattr(thread, "users", []) or []
                    for user in users:
                        if stop_event.is_set():
                            break
                        user_pk = getattr(user, "pk", None)
                        username = getattr(user, "username", None) or str(user_pk)
                        if cfg.get("username") and username == cfg.get("username"):
                            continue
                        key = f"{thread_id}::{username}"
                        if key not in welcomed:
                            append_log(f"New member @{username} in thread {thread_id}")
                            for m in welcome_messages:
                                if stop_event.is_set():
                                    break
                                text = m.replace("{username}", username)
                                try:
                                    cl.direct_send(text, thread_ids=[thread_id])
                                    append_log(f"Sent to @{username} in {thread_id}: {text[:80]}")
                                except Exception as e_send:
                                    append_log(f"Send error to @{username}: {e_send}")
                                    # fallback by user id
                                    try:
                                        if user_pk:
                                            cl.direct_send(text, user_ids=[user_pk])
                                            append_log(f"Fallback sent to @{username} by user id.")
                                    except Exception as e2:
                                        append_log(f"Fallback failed for @{username}: {e2}")
                                time.sleep(delay)
                            welcomed.add(key)
                            save_welcomed_cache(welcomed)
                except Exception as e_thread:
                    append_log(f"Error reading thread {thread_id}: {e_thread}")

            # responsive sleep
            slept = 0.0
            while slept < poll_interval:
                if stop_event.is_set():
                    break
                time.sleep(0.5)
                slept += 0.5
    except Exception as e:
        append_log(f"Worker exception: {e}")
    finally:
        BOT_STATUS["running"] = False
        BOT_STATUS["task_id"] = None
        append_log(f"Task {task_id} stopped.")

# ---------- Frontend: simple font, large layout, multi welcome file support ----------
PAGE_HTML = r"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>INSTA MULTI WELCOME BOT</title>
  <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;600&display=swap" rel="stylesheet">
  <style>
    :root{
      --bg1:#0b1630; --bg2:#07102a; --accent:#00c2b3; --accent2:#6b5bff;
    }
    *{box-sizing:border-box}
    body{
      margin:0; min-height:100vh; font-family:'Poppins',sans-serif;
      background: linear-gradient(180deg,var(--bg1),var(--bg2));
      color:#eafcff; display:flex; align-items:center; justify-content:center; padding:30px;
    }
    .wrap{ width:100%; max-width:1300px; display:flex; gap:22px; align-items:flex-start; }
    .card{ background: rgba(255,255,255,0.02); padding:28px; border-radius:14px; border:1px solid rgba(255,255,255,0.03); box-shadow:0 12px 40px rgba(0,0,0,0.6); }
    .left{ flex:0 0 760px; } .right{ flex:1; min-width:380px; }
    h1{ margin:0 0 8px 0; font-size:34px; color:var(--accent); }
    .subtitle{ color:#9fd8e8; margin-bottom:18px; font-size:15px; }
    label{ display:block; color:#bfeffc; font-size:15px; margin-bottom:8px; font-weight:600; }
    input[type=text], input[type=password], textarea, select {
      width:100%; padding:14px 12px; border-radius:10px; border:1px solid rgba(255,255,255,0.04);
      background: rgba(0,0,0,0.48); color:#eafcff; font-size:16px; margin-bottom:14px;
    }
    textarea{ min-height:180px; resize:vertical; font-size:15px; }
    .row{ display:flex; gap:12px; align-items:center; margin-bottom:12px; }
    .small{ width:180px; }
    .controls{ display:flex; gap:12px; margin-top:10px; }
    .btn{ padding:12px 18px; border-radius:10px; border:none; cursor:pointer; font-weight:700;
      background: linear-gradient(90deg,var(--accent),var(--accent2)); color:#001; }
    .btn.stop{ background: linear-gradient(90deg,#ff6b6b,#ffd18f); color:#111; }
    .note{ color:#bfeffc; font-size:14px; margin-top:6px; }
    .logs{ max-height:680px; overflow:auto; padding:16px; border-radius:10px; background: rgba(0,0,0,0.45);
      border:1px solid rgba(255,255,255,0.02); font-family:monospace; font-size:13px; color:#dff8ff; }
    .info{ font-size:14px; color:#9fd8e8; margin-bottom:6px; }
    .footer{ margin-top:12px; font-size:13px; color:#bfeffc; text-align:center; }
    @media (max-width:1100px){
      .wrap{ flex-direction:column; align-items:center; }
      .left{ width:100%; } .right{ width:100%; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card left">
      <h1>INSTA MULTI WELCOME BOT</h1>
      <div class="subtitle">Simple font • Large layout • Multiple welcome messages supported</div>

      <form id="controlForm" method="post" action="/start" enctype="multipart/form-data">
        <label>Instagram Username</label>
        <input type="text" name="username" placeholder="username (optional if session.json exists)" />

        <label>Password</label>
        <input type="password" name="password" placeholder="password (only for fresh login)" />

        <label>Upload session.json (optional)</label>
        <input type="file" name="session_file" accept=".json" />

        <label>Upload welcome_messages.txt (optional)<br><small>Use <code>===</code> to separate messages or use separate lines</small></label>
        <input type="file" name="welcome_file" accept=".txt" />

        <label>Or paste messages below (each line = separate message)</label>
        <textarea name="single_message" placeholder="Welcome @{username}!"></textarea>

        <label>Welcome mode</label>
        <select name="welcome_mode">
          <option value="file">File (=== separators)</option>
          <option value="single">Textarea (each line)</option>
          <option value="split_by_line">Split by line (file)</option>
        </select>

        <label>Group Chat IDs (comma separated)</label>
        <input type="text" name="group_ids" placeholder="24632887389663044,123..." />

        <div class="row">
          <div style="flex:1">
            <label>Delay between messages (sec)</label>
            <input class="small" name="delay" value="2" />
          </div>
          <div style="flex:1">
            <label>Poll interval (sec)</label>
            <input class="small" name="poll_interval" value="6" />
          </div>
        </div>

        <div class="controls">
          <button type="submit" class="btn">Start Bot</button>
          <button formaction="/stop" formmethod="post" class="btn stop">Stop Bot</button>
          <a href="/download_sample" style="text-decoration:none"><button type="button" class="btn" style="background:linear-gradient(90deg,#8be8a9,#7ab4ff);">Download Sample</button></a>
        </div>
        <div class="note">Use <code>{username}</code> placeholder in messages to insert username.</div>
      </form>
    </div>

    <div class="card right">
      <div class="info">Status: <strong id="statusText">Stopped</strong></div>
      <div class="logs" id="logs">{{ logs }}</div>

      <div style="margin-top:12px">
        <div class="info"><b>Task:</b> <span id="taskId">{{ status.task_id or '—' }}</span></div>
        <div class="info"><b>Started:</b> <span id="startedAt">{{ status.started_at or '—' }}</span></div>
        <div class="info"><b>Last ping:</b> <span id="lastPing">{{ status.last_ping or '—' }}</span></div>
        <div class="info"><b>Welcomed cache:</b> <span id="welcomedCount">{{ welcomed_count }}</span></div>
      </div>
    </div>
  </div>

  <div class="footer">Keep session private. Do not commit <code>/uploads/session.json</code> to public repos.</div>

<script>
  async function refreshStatus(){
    try{
      const r = await fetch('/status');
      const j = await r.json();
      document.getElementById('logs').innerText = j.logs.join('\\n');
      document.getElementById('statusText').innerText = j.running ? 'Running' : 'Stopped';
      document.getElementById('taskId').innerText = j.task_id || '—';
      document.getElementById('startedAt').innerText = j.started_at || '—';
      document.getElementById('lastPing').innerText = j.last_ping || '—';
      document.getElementById('welcomedCount').innerText = j.welcomed_count || 0;
    }catch(e){
      // ignore
    }
  }
  setInterval(refreshStatus, 3000);
  refreshStatus();
</script>
</body>
</html>
"""

# ---------- Flask routes ----------
@app.route("/")
def index():
    recent = BOT_LOGS[-800:]
    rendered_logs = "\n".join(recent[::-1]) if recent else "No logs yet."
    welcomed = load_welcomed_cache()
    return render_template_string(PAGE_HTML, logs=rendered_logs, status=BOT_STATUS, welcomed_count=len(welcomed))

@app.route("/download_sample")
def download_sample():
    sample = "Welcome @{username} 👋\n===\nHello @{username}, glad to have you here!\n===\nEnjoy the group @{username}!"
    path = os.path.join(UPLOADS, "welcome_sample.txt")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(sample)
        return send_file(path, as_attachment=True, download_name="welcome_messages_sample.txt")
    except Exception as e:
        append_log(f"Failed to create sample: {e}")
        return jsonify({"ok": False, "message": "Could not create sample."})

@app.route("/start", methods=["POST"])
def start():
    global BOT_THREAD, BOT_STOP_EVENT

    if BOT_STATUS.get("running"):
        return redirect(url_for("index"))

    username = (request.form.get("username") or "").strip()
    password = (request.form.get("password") or "").strip()
    welcome_mode = request.form.get("welcome_mode") or "file"
    group_ids = (request.form.get("group_ids") or "").strip()
    delay = request.form.get("delay") or "2"
    poll_interval = request.form.get("poll_interval") or "6"

    # session upload
    session_file_path = None
    if "session_file" in request.files:
        f = request.files["session_file"]
        if f and f.filename:
            dest = os.path.join(UPLOADS, secure_filename(f.filename))
            f.save(dest)
            session_file_path = dest
            append_log(f"Uploaded session saved to {dest}")

    # welcome file upload
    welcome_file_path = None
    if "welcome_file" in request.files:
        f = request.files["welcome_file"]
        if f and f.filename:
            dest = os.path.join(UPLOADS, "uploaded_welcome.txt")
            f.save(dest)
            welcome_file_path = dest
            append_log(f"Uploaded welcome saved to {dest}")

    if not welcome_file_path and os.path.exists(WELCOME_UPLOAD):
        welcome_file_path = WELCOME_UPLOAD

    # load messages (priority: uploaded file > textarea)
    welcome_messages = []
    if welcome_file_path and os.path.exists(welcome_file_path):
        try:
            with open(welcome_file_path, "r", encoding="utf-8") as f:
                content = f.read()
            if "===" in content:
                welcome_messages = [m.strip() for m in content.split("===") if m.strip()]
            else:
                welcome_messages = [m.strip() for m in content.splitlines() if m.strip()]
            append_log(f"Loaded {len(welcome_messages)} messages from file.")
        except Exception as e:
            append_log(f"Failed reading welcome file: {e}")
    else:
        single = request.form.get("single_message") or ""
        welcome_messages = [m.strip() for m in single.splitlines() if m.strip()]
        append_log(f"Loaded {len(welcome_messages)} messages from textarea.")

    group_list = [g.strip() for g in group_ids.split(",") if g.strip()]

    if not username or not password:
        append_log("Start failed: missing username/password")
        return redirect(url_for("index"))
    if not welcome_messages:
        append_log("Start failed: no welcome messages")
        return redirect(url_for("index"))
    if not group_list:
        append_log("Start failed: no group IDs")
        return redirect(url_for("index"))

    try:
        cfg = {
            "username": username,
            "password": password,
            "session_file": session_file_path,
            "group_ids": group_list,
            "welcome_messages": welcome_messages,
            "delay": float(delay),
            "poll_interval": float(poll_interval)
        }
    except Exception:
        cfg = {
            "username": username, "password": password, "session_file": session_file_path,
            "group_ids": group_list, "welcome_messages": welcome_messages,
            "delay": 2.0, "poll_interval": 6.0
        }

    BOT_STOP_EVENT = threading.Event()
    task_id = f"TASK-{int(time.time())}"
    with BOT_THREAD_LOCK:
        BOT_THREAD = threading.Thread(target=run_bot, args=(task_id, cfg, BOT_STOP_EVENT), daemon=True)
        BOT_THREAD.start()
    append_log(f"Started bot task {task_id}")
    return redirect(url_for("index"))

@app.route("/stop", methods=["POST"])
def stop():
    global BOT_STOP_EVENT
    if BOT_STOP_EVENT:
        BOT_STOP_EVENT.set()
        append_log("Stop request
