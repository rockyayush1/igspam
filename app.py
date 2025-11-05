#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
app.py - ULTRA SPEED Instagram Group Name Changer (Flask UI)
Use responsibly. This script attempts to log in and call Instagram mobile endpoints.
"""

import os
import time
import random
import threading
import requests
from collections import deque
from flask import Flask, render_template_string, request, jsonify, redirect, url_for
from rich.console import Console
from rich.text import Text

console = Console()
app = Flask(__name__)

# Shared state
worker_thread = None
worker_stop_event = threading.Event()
worker_lock = threading.Lock()
logs = deque(maxlen=2000)
state = {"running": False, "current_account": None, "error_count": 0, "accounts": []}

# ---------- Helpers ----------
def add_log(s: str):
    ts = time.strftime("%H:%M:%S")
    entry = f"[{ts}] {s}"
    with worker_lock:
        logs.append(entry)
    console.print(Text(entry))

def smart_sleep_ms(ms):
    try:
        ms = float(ms)
    except:
        ms = 500.0
    if ms <= 1:
        time.sleep(0.001)
    else:
        time.sleep(ms / 1000.0)

def get_random_headers():
    user_agents = [
        "Instagram 155.0.0.37.107 Android",
        "Instagram 156.0.0.41.119 Android",
        "Instagram 157.0.0.32.118 Android",
        "Instagram 158.0.0.34.123 Android",
        "Instagram 159.0.0.12.116 Android",
    ]
    return {
        "User-Agent": random.choice(user_agents),
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-IG-App-ID": "936619743392459"
    }

# ---------- Instagram actions (best-effort) ----------
def insta_login(username, password):
    """
    Try to login and return a requests.Session or None.
    This is best-effort; Instagram changes often.
    """
    try:
        session = requests.Session()
        headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 10)",
            "X-IG-App-ID": "936619743392459",
        }
        session.headers.update(headers)
        login_url = "https://www.instagram.com/accounts/login/ajax/"

        # GET to gather cookies & csrftoken
        r = session.get("https://www.instagram.com/accounts/login/", timeout=10)
        csrf = r.cookies.get("csrftoken", "")
        session.headers.update({"X-CSRFToken": csrf})

        payload = {"username": username, "enc_password": f"#PWD_INSTAGRAM_BROWSER:0:{int(time.time())}:{password}"}
        res = session.post(login_url, data=payload, allow_redirects=True, timeout=10)

        # Heuristics for successful login
        text = res.text or ""
        if res.status_code == 200 and ('"authenticated":true' in text or '"authenticated": true' in text):
            return session
        # some accounts may get redirect/other response - try to accept common success markers
        if res.status_code == 200 and ("userId" in text or "status" in text):
            return session

        add_log(f"❌ Login failed for {username} (status {res.status_code})")
        return None
    except Exception as e:
        add_log(f"❌ Login error for {username}: {e}")
        return None

def change_group_name_safe(thread_id, new_name, session):
    """
    Attempt to change group title via i.instagram API (mobile).
    Returns (ok: bool, message: str)
    """
    url = f"https://i.instagram.com/api/v1/direct_v2/threads/{thread_id}/update_title/"
    headers = get_random_headers()
    data = {"title": new_name}
    try:
        r = session.post(url, headers=headers, data=data, timeout=12)
        if r.status_code == 200:
            return True, "OK"
        return False, f"HTTP {r.status_code}"
    except Exception as e:
        return False, str(e)

# ---------- Worker ----------
def worker_run(accounts_list, thread_ids, names_list, delay_ms, err_threshold):
    """
    accounts_list: list of "username:password"
    thread_ids: list of thread ids
    names_list: list of names
    delay_ms: milliseconds pause between each group name change
    err_threshold: consecutive errors before switching account
    """
    add_log("🚀 Worker started")
    state["running"] = True
    state["current_account"] = None
    state["error_count"] = 0

    sessions_cache = [None] * len(accounts_list)
    account_index = 0
    name_index = 0

    try:
        while not worker_stop_event.is_set():
            # Ensure we have a session for current account
            if sessions_cache[account_index] is None:
                username, password = accounts_list[account_index].split(":", 1)
                add_log(f"🔑 Trying login: {username}")
                sess = insta_login(username, password)
                sessions_cache[account_index] = sess
                if sess:
                    add_log(f"✅ Logged in as {username}")
                    state["current_account"] = username
                    state["error_count"] = 0
                else:
                    add_log(f"⚠ Login failed for {username}, switching to next account")
                    account_index = (account_index + 1) % len(accounts_list)
                    continue

            session = sessions_cache[account_index]
            # pick next name
            name = names_list[name_index % len(names_list)].strip()
            name_index += 1
            suffix = random.choice(["🔥", "⚡", "💀", "✨", "🚀"])
            unique_name = f"{name}_{random.randint(1000,9999)}{suffix}"

            # apply to each thread id
            for tid in thread_ids:
                if worker_stop_event.is_set():
                    break
                tid = tid.strip()
                if not tid:
                    continue
                ok, resp = change_group_name_safe(tid, unique_name, session)
                if ok:
                    add_log(f"✅ [{tid}] -> {unique_name} (acc {account_index+1})")
                    state["error_count"] = 0
                else:
                    add_log(f"❌ [{tid}] -> {unique_name} | {resp}")
                    state["error_count"] += 1
                    if state["error_count"] >= err_threshold:
                        add_log("⚠️ Too many errors for this account, switching to next")
                        sessions_cache[account_index] = None
                        account_index = (account_index + 1) % len(accounts_list)
                        state["error_count"] = 0
                        break

                smart_sleep_ms(delay_ms)

            # continue infinite loop (names rotate)
            continue

    except Exception as e:
        add_log(f"❌ Worker exception: {e}")
    finally:
        state["running"] = False
        state["current_account"] = None
        add_log("🛑 Worker stopped")

# ---------- HTML (with animated background) ----------
INDEX_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>ULTRA SPEED Instagram Bot</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;500;700&display=swap');
    :root{--bg:#07121a;--accent:#7ee8fa}
    body{margin:0; font-family:Inter,system-ui,Arial; background:linear-gradient(135deg,#020617,#07121a); color:#e6f1ff; display:flex; align-items:center; justify-content:center; min-height:100vh;}
    .bg { position:fixed; inset:0; z-index:0; background:
      radial-gradient(circle at 10% 20%, rgba(126,232,250,0.05), transparent 8%),
      radial-gradient(circle at 80% 80%, rgba(255,107,203,0.04), transparent 8%),
      linear-gradient(90deg, rgba(3,10,18,0.9), rgba(2,6,12,0.95));
      filter: blur(18px) saturate(120%); animation:bgmove 12s linear infinite; }
    @keyframes bgmove {0%{transform:translateY(0)}50%{transform:translateY(-18px)}100%{transform:translateY(0)}}
    .card{position:relative; z-index:2; width:95%; max-width:1100px; border-radius:12px; padding:20px; background:rgba(2,8,14,0.6); border:1px solid rgba(126,232,250,0.04)}
    h1{margin:0; color:var(--accent)}
    label{display:block; margin-top:10px; color:#9bdcff; font-size:13px}
    input, textarea{width:100%; padding:10px; margin-top:6px; border-radius:8px; background:#031018; border:1px solid rgba(125,170,200,0.04); color:#e6f1ff}
    .row{display:flex; gap:12px; margin-top:10px}
    .col{flex:1}
    .controls{display:flex; gap:10px; align-items:center; margin-top:12px}
    button{padding:10px 14px; border-radius:10px; border:none; cursor:pointer; font-weight:700}
    .btn-start{background:linear-gradient(90deg,#00d4ff,#7ee8fa); color:#021018}
    .btn-stop{background:linear-gradient(90deg,#ff6b6b,#ff9aa2); color:#fff}
    pre#logs{background:transparent; color:#bfe9ff; padding:12px; border-radius:8px; max-height:360px; overflow:auto; font-family:monospace}
    .status{background:#02131a; padding:10px; border-radius:8px; border:1px solid rgba(255,255,255,0.02)}
    @media(max-width:800px){.row{flex-direction:column}}
    footer{margin-top:10px; color:#6fa8c8; text-align:center; font-size:13px}
  </style>
</head>
<body>
  <div class="bg" aria-hidden="true"></div>
  <div class="card">
    <h1>🚀 ULTRA SPEED Instagram Bot</h1>
    <p style="color:#9bb7d6; margin:6px 0 12px 0">Multiple accounts, auto-switch, infinite loop, millisecond delay. Use responsibly.</p>

    <form id="frm" onsubmit="startBot(event)">
      <label>Accounts (comma separated, username:password)</label>
      <input id="accounts" name="accounts" placeholder="nfyter:x-223344, nfyte_r:g-223344" required>

      <div class="row">
        <div class="col">
          <label>Group Thread IDs (comma separated)</label>
          <input id="threads" name="threads" placeholder="1372945174421748, 1234567890" required>
        </div>
        <div class="col">
          <label>Group Names (comma separated)</label>
          <input id="names" name="names" placeholder="Hacker, UltraSpeed, Matrix" required>
        </div>
      </div>

      <div class="row">
        <div class="col">
          <label>Delay (milliseconds)</label>
          <input id="delay_ms" name="delay_ms" placeholder="500" value="500" required>
        </div>
        <div class="col">
          <label>Error threshold (consecutive errors before switch)</label>
          <input id="err_th" name="err_th" placeholder="3" value="3" required>
        </div>
      </div>

      <div class="controls">
        <button id="btnStart" class="btn-start" type="submit">Start</button>
        <button id="btnStop" class="btn-stop" type="button" onclick="stopBot()">Stop</button>
        <div style="flex:1"></div>
        <div class="status">
          <div>Status: <strong id="status">Stopped</strong></div>
          <div>Current Account: <span id="current_account">-</span></div>
          <div>Errors: <span id="error_count">0</span></div>
        </div>
      </div>
    </form>

    <hr style="border-color:#122233; margin:14px 0;">

    <div>
      <h4 style="margin:6px 0">Live Logs</h4>
      <pre id="logs">No logs yet.</pre>
    </div>

    <footer>Made for testing — do not run at scale. Stop to halt the worker.</footer>
  </div>

<script>
function updateStatus(){
  fetch('/status').then(r=>r.json()).then(j=>{
    document.getElementById('status').innerText = j.running ? "Running" : "Stopped";
    document.getElementById('current_account').innerText = j.current_account || "-";
    document.getElementById('error_count').innerText = j.error_count || 0;
    document.getElementById('btnStart').disabled = j.running;
    document.getElementById('btnStop').disabled = !j.running;
  });
  fetch('/logs').then(r=>r.json()).then(j=>{
    const logs = j.logs.join('\\n');
    const pre = document.getElementById('logs');
    pre.innerText = logs || "No logs yet.";
    pre.scrollTop = pre.scrollHeight;
  });
}
setInterval(updateStatus, 1000);
updateStatus();

function startBot(e){
  e.preventDefault();
  const form = document.getElementById('frm');
  const formData = new FormData(form);
  fetch('/start', {method:'POST', body: formData}).then(resp=>{
    if(resp.redirected){
      window.location = resp.url;
    } else {
      updateStatus();
    }
  });
}

function stopBot(){
  fetch('/stop', {method:'POST'}).then(()=>updateStatus());
}
</script>
</body>
</html>
"""

# ---------- Flask endpoints ----------
@app.route("/", methods=["GET"])
def index():
    return render_template_string(INDEX_HTML)

@app.route("/start", methods=["POST"])
def start():
    global worker_thread, worker_stop_event, logs, state

    if state.get("running"):
        return redirect(url_for("index"))

    accounts_raw = request.form.get("accounts", "").strip()
    threads_raw = request.form.get("threads", "").strip()
    names_raw = request.form.get("names", "").strip()
    delay_raw = request.form.get("delay_ms", "500").strip()
    err_th_raw = request.form.get("err_th", "3").strip()

    if not accounts_raw or not threads_raw or not names_raw:
        return "Missing fields", 400

    accounts_list = [a.strip() for a in accounts_raw.split(",") if ":" in a]
    thread_ids = [t.strip() for t in threads_raw.split(",") if t.strip()]
    names_list = [n.strip() for n in names_raw.split(",") if n.strip()]

    try:
        delay_ms = float(delay_raw)
        if delay_ms < 0: delay_ms = 500.0
    except:
        delay_ms = 500.0

    try:
        err_threshold = int(err_th_raw)
    except:
        err_threshold = 3

    state["accounts"] = accounts_list

    # clear logs
    with worker_lock:
        logs.clear()

    # reset stop event and start worker
    worker_stop_event.clear()
    worker_thread = threading.Thread(target=worker_run, args=(accounts_list, thread_ids, names_list, delay_ms, err_threshold), daemon=True)
    worker_thread.start()

    time.sleep(0.12)
    return redirect(url_for("index"))

@app.route("/stop", methods=["POST"])
def stop():
    global worker_stop_event
    worker_stop_event.set()
    return ("", 204)

@app.route("/logs", methods=["GET"])
def get_logs():
    with worker_lock:
        data = list(logs)
    return jsonify({"logs": data})

@app.route("/status", methods=["GET"])
def get_status():
    return jsonify({
        "running": state.get("running", False),
        "current_account": state.get("current_account", None),
        "error_count": state.get("error_count", 0)
    })

# ---------- Run ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    host = "0.0.0.0"
    print(f"Starting Flask app on {host}:{port} ...")
    app.run(host=host, port=port, debug=False)
