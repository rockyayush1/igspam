import os
import threading
import time
import random
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify
from instagrapi import Client

app = Flask(__name__)
BOT_THREAD = None
STOP_EVENT = threading.Event()
LOGS = []
SESSION_FILE = "token.txt"
STATS = {"total_welcomed": 0, "today_welcomed": 0}
BOT_CONFIG = {"auto_replies": {}, "auto_reply_active": False}

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    lm = f"[{ts}] {msg}"
    LOGS.append(lm)
    print(lm)

def load_token_session(token):
    cl = Client()
    try:
        cl.set_uuids({
            "phone_uuid": "12345678-1234-1234-1234-123456789abc",
            "device_uuid": "12345678-1234-1234-1234-123456789abc"
        })
        cl.login_by_sessionid(token)
        log("✅ Token login successful!")
        return cl
    except Exception as e:
        log(f"❌ Token failed: {str(e)[:50]}")
        return None

def run_bot(token, wm, gids, dly, pol, ucn, ecmd, admins):
    cl = load_token_session(token)
    if not cl:
        return
    
    log("🚀 Bot started!")
    km = {gid: set() for gid in gids}
    
    while not STOP_EVENT.is_set():
        for gid in gids:
            if STOP_EVENT.is_set(): break
            try:
                g = cl.direct_thread(gid)
                cm = {u.pk for u in g.users}
                new = cm - km[gid]
                
                for u in g.users:
                    if u.pk in new:
                        log(f"👋 NEW: @{u.username}")
                        for msg in wm:
                            fm = f"@{u.username} {msg}" if ucn else msg
                            cl.direct_send(fm, [gid])
                            STATS["total_welcomed"] += 1
                            time.sleep(dly)
                        km[gid] = cm
                        break
                        
            except:
                pass
        time.sleep(pol)
    log("🛑 Bot stopped!")

@app.route('/')
def index():
    token = ""
    if os.path.exists(SESSION_FILE):
        with open(SESSION_FILE) as f:
            token = f.read().strip()
    return f"""
<!DOCTYPE html>
<html>
<head><title>TOKEN BOT</title>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width">
<style>
body{{background:#000;color:#0ff;font-family:Arial;padding:20px}}
.c{{max-width:600px;margin:auto;background:rgba(0,0,20,0.9);padding:30px;border-radius:20px}}
h1{{text-align:center;color:#0ff;font-size:2em;margin-bottom:30px}}
input,textarea{{width:100%;padding:12px;margin:10px 0;border-radius:10px;background:#111;color:#fff;border:1px solid #0ff}}
button{{padding:15px 30px;background:#0ff;color:#000;border:none;border-radius:10px;cursor:pointer;font-weight:bold;margin:5px}}
button:hover{{background:#0cc;transform:scale(1.05)}}
.logs{{background:#111;padding:20px;border-radius:10px;height:300px;overflow:auto;font-family:monospace;font-size:12px;line-height:1.4}}
.note{{background:rgba(255,0,0,0.2);padding:15px;border-radius:10px;border-left:4px solid #f00;margin:20px 0}}
</style>
</head>
<body>
<div class="c">
<h1>🎟️ TOKEN BOT v6.0</h1>
<div class="note">Token paste करके SET TOKEN दबाओ। Username/password नही चाहिए!</div>

<div>
<textarea id="token" rows="3" placeholder="तुम्हारा token यहाँ paste करो...">{token}</textarea>
<button onclick="setToken()">💾 SET TOKEN</button>
<div id="status"></div>
</div>

<form id="form" style="display:none">
<h3>Bot Settings</h3>
<input name="group_ids" placeholder="Group IDs (comma separated)"><br>
<textarea name="welcome" rows="3" placeholder="Welcome messages">Welcome bro! 🎉
Glad you joined!</textarea><br>
<input name="admin_ids" placeholder="Admin usernames"><br>
<input type="number" name="delay" value="2" min="1"> Delay (sec)<br>
<input type="number" name="poll" value="5" min="2"> Poll (sec)<br>
<button onclick="startBot()">🚀 START BOT</button>
<button onclick="stopBot()">🛑 STOP BOT</button>
</form>

<div class="logs" id="logs">Bot ready...</div>
</div>

<script>
async function setToken() {{
    let token = document.getElementById('token').value.trim();
    if(!token) return alert('Token empty!');
    
    let form = new FormData();
    form.append('token', token);
    
    let r = await fetch('/set_token', {{method:'POST', body:form}});
    let res = await r.json();
    document.getElementById('status').innerHTML = res.message;
    if(res.success) {{
        document.getElementById('form').style.display = 'block';
    }}
}}

async function startBot() {{
    let form = new FormData(document.getElementById('form'));
    let r = await fetch('/start', {{method:'POST', body:form}});
    alert((await r.json()).message);
}}

async function stopBot() {{
    let r = await fetch('/stop', {{method:'POST'}});
    alert((await r.json()).message);
}}

setInterval(async()=>{
    let r = await fetch('/logs');
    let data = await r.json();
    document.getElementById('logs').innerHTML = data.logs.slice(-10).join('<br>');
}, 2000);
</script>
</body>
</html>
"""

@app.route('/set_token', methods=['POST'])
def set_token():
    token = request.form.get('token', '').strip()
    try:
        if token:
            with open(SESSION_FILE, 'w') as f:
                f.write(token)
            log("✅ Token saved!")
            return jsonify({"message": "✅ Token set!", "success": True})
        return jsonify({"message": "❌ Empty token!", "success": False})
    except Exception as e:
        log(f"❌ Set token error: {e}")
        return jsonify({"message": f"❌ Error: {str(e)}", "success": False})

@app.route('/start', methods=['POST'])
def start_bot():
    global BOT_THREAD, STOP_EVENT
    try:
        if BOT_THREAD and BOT_THREAD.is_alive():
            return jsonify({"message": "⚠️ Already running!"})
        
        token = ""
        if os.path.exists(SESSION_FILE):
            with open(SESSION_FILE) as f:
                token = f.read().strip()
        if not token:
            return jsonify({"message": "❌ No token!"})
        
        gids = [g.strip() for g in request.form.get('group_ids', '').split(',') if g.strip()]
        wl = [m.strip() for m in request.form.get('welcome', '').splitlines() if m.strip()]
        
        if not gids or not wl:
            return jsonify({"message": "❌ Groups & welcome messages required!"})
        
        STOP_EVENT.clear()
        BOT_THREAD = threading.Thread(
            target=run_bot,
            args=(token, wl, gids, 
                  int(request.form.get('delay', 2)),
                  int(request.form.get('poll', 5)),
                  True, True, []),
            daemon=True
        )
        BOT_THREAD.start()
        log("🚀 Bot started!")
        return jsonify({"message": "🚀 Bot started successfully!"})
    except Exception as e:
        log(f"❌ Start error: {e}")
        return jsonify({"message": f"❌ Error: {str(e)}"})

@app.route('/stop', methods=['POST'])
def stop_bot():
    global STOP_EVENT
    STOP_EVENT.set()
    log("🛑 Stop signal sent!")
    return jsonify({"message": "✅ Bot stopping..."})

@app.route('/logs')
def get_logs():
    return jsonify({"logs": LOGS[-20:]})

if __name__ == '__main__':
    print("🚀 TOKEN BOT v6.0 Starting...")
    print("http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=False)
