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
SESSION_FILE = "session.json"
STATS = {"total_welcomed": 0, "today_welcomed": 0, "last_reset": datetime.now().date()}
BOT_CONFIG = {"auto_replies": {}, "auto_reply_active": False, "target_spam": {}, "spam_active": {}, "media_library": {}}

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    lm = f"[{ts}] {msg}"
    LOGS.append(lm)
    print(lm)

MUSIC_EMOJIS = ["🎵", "🎶", "🎸", "🎹", "🎤", "🎧", "🎺", "🎷"]
FUNNY = ["Hahaha! 😂", "LOL! 🤣", "Mast! 😆", "Pagal! 🤪", "King! 👑😂"]
MASTI = ["Party! 🎉", "Masti! 🥳", "Dhamaal! 💃", "Full ON! 🔥", "Enjoy! 🎊"]

def run_bot(token, wm, gids, dly, pol, ucn, ecmd, admin_ids):
    cl = Client()
    try:
        cl.login_by_sessionid(token)
        cl.dump_settings(SESSION_FILE)
        log("✅ TOKEN LOGIN SUCCESS!")
    except Exception as e:
        log(f"💥 TOKEN LOGIN FAILED: {str(e)}")
        return
    
    log("🤖 Bot started!")
    log(f"Commands enabled: {ecmd}")
    
    km = {}
    lm = {}
    for gid in gids.split(","):
        gid = gid.strip()
        if gid:
            try:
                g = cl.direct_thread(gid)
                km[gid] = {u.pk for u in g.users}
                lm[gid] = g.messages[0].id if g.messages else None
                BOT_CONFIG["spam_active"][gid] = False
                log(f"✅ Group {gid[:8]}... ready")
            except Exception as e:
                log(f"⚠️ Group error: {str(e)}")
    
    global STATS
    if STATS["last_reset"] != datetime.now().date():
        STATS["today_welcomed"] = 0
        STATS["last_reset"] = datetime.now().date()
    
    while not STOP_EVENT.is_set():
        for gid_raw in gids.split(","):
            gid = gid_raw.strip()
            if STOP_EVENT.is_set() or not gid:
                continue
            try:
                g = cl.direct_thread(gid)
                
                # Spam check
                if BOT_CONFIG["spam_active"].get(gid, False):
                    tu = BOT_CONFIG["target_spam"].get(gid, {}).get("username")
                    sm = BOT_CONFIG["target_spam"].get(gid, {}).get("message")
                    if tu and sm:
                        cl.direct_send("@{} {}".format(tu, sm), thread_ids=[gid])
                        log("💥 Spam to @{}".format(tu))
                        time.sleep(2)
                
                # Message processing
                new_messages = []
                if lm.get(gid) and g.messages:
                    for m in g.messages:
                        if m.id == lm[gid]:
                            break
                        new_messages.append(m)
                
                for m in reversed(new_messages):
                    try:
                        if m.user_id == cl.user_id:
                            continue
                        sender = next((u for u in g.users if u.pk == m.user_id), None)
                        if not sender:
                            continue
                        su = sender.username.lower()
                        is_admin = su in [a.lower() for a in admin_ids.split(",") if a.strip()] if admin_ids else False
                        t = (m.text or "").strip()
                        tl = t.lower()
                        
                        log("📨 @{}: '{}'".format(sender.username, t[:30]))
                        
                        # Auto-reply
                        if BOT_CONFIG["auto_reply_active"] and tl in BOT_CONFIG["auto_replies"]:
                            cl.direct_send(BOT_CONFIG["auto_replies"][tl], thread_ids=[gid])
                            log("🤖 Auto-reply sent")
                            continue
                        
                        if not ecmd:
                            continue
                        
                        # 🔥 ALL COMMANDS - NO F-STRINGS!
                        if any(cmd in tl for cmd in ["/help", "!help", "/h", "!h"]):
                            help_msg = "🔥 NEON BOT v3.2 COMMANDS:
/help or /h - This help
/stats - Bot statistics
/count - Group members
/ping - Bot alive check
/time - Current time
/welcome - Test welcome
/music - 🎵 Music
/funny - 😂 Funny
/masti - 🎉 Party

ADMIN ONLY:
/autoreply hello Hi - Auto reply setup
/stopreply - Stop auto reply
/spam @user msg - Spam target
/stopspam - Stop spam
/kick @user - Remove user"
                            cl.direct_send(help_msg, thread_ids=[gid])
                            log("✅ HELP sent to @{}".format(sender.username))
                            
                        elif tl in ["/stats", "!stats"]:
                            stats_msg = "📊 STATS:
Total: {}
Today: {}".format(STATS['total_welcomed'], STATS['today_welcomed'])
                            cl.direct_send(stats_msg, thread_ids=[gid])
                            log("📊 Stats sent")
                            
                        elif tl in ["/count", "!count"]:
                            count_msg = "👥 MEMBERS: {}".format(len(g.users))
                            cl.direct_send(count_msg, thread_ids=[gid])
                            log("👥 Count: {}".format(len(g.users)))
                            
                        elif tl in ["/ping", "!ping"]:
                            cl.direct_send("🏓 PONG! Bot 100% Alive 🔥", thread_ids=[gid])
                            log("🏓 Ping OK")
                            
                        elif tl in ["/time", "!time"]:
                            time_msg = "🕐 {}".format(datetime.now().strftime('%H:%M:%S'))
                            cl.direct_send(time_msg, thread_ids=[gid])
                            log("🕐 Time sent")
                            
                        elif tl.startswith("/autoreply "):
                            parts = t.split(" ", 2)
                            if len(parts) >= 3:
                                BOT_CONFIG["auto_replies"][parts[1].lower()] = parts[2]
                                BOT_CONFIG["auto_reply_active"] = True
                                reply_msg = "✅ Auto-reply: '{}' → '{}'".format(parts[1], parts[2][:20])
                                cl.direct_send(reply_msg, thread_ids=[gid])
                            else:
                                cl.direct_send("❌ /autoreply trigger reply", thread_ids=[gid])
                                
                        elif tl in ["/stopreply", "!stopreply"]:
                            BOT_CONFIG["auto_reply_active"] = False
                            BOT_CONFIG["auto_replies"] = {}
                            cl.direct_send("🛑 Auto-reply OFF", thread_ids=[gid])
                            log("Auto-reply stopped")
                            
                        elif is_admin and tl.startswith("/spam "):
                            parts = t.split(" ", 2)
                            if len(parts) >= 3:
                                BOT_CONFIG["target_spam"][gid] = {"username": parts[1].replace("@", ""), "message": parts[2]}
                                BOT_CONFIG["spam_active"][gid] = True
                                cl.direct_send("💥 Spam ON", thread_ids=[gid])
                                
                        elif is_admin and tl == "/stopspam":
                            BOT_CONFIG["spam_active"][gid] = False
                            cl.direct_send("🛑 Spam OFF", thread_ids=[gid])
                            
                    except Exception as e:
                        log("❌ Command error: {}".format(str(e)))
                
                if g.messages:
                    lm[gid] = g.messages[0].id
                
                # New members
                cm = {u.pk for u in g.users}
                new_members = cm - km.get(gid, set())
                if new_members:
                    for u in g.users:
                        if u.pk in new_members:
                            log("👤 NEW: @{}".format(u.username))
                            for msg in wm:
                                welcome_msg = ("@{} ".format(u.username) + msg) if ucn else msg
                                cl.direct_send(welcome_msg, thread_ids=[gid])
                                STATS["total_welcomed"] += 1
                                STATS["today_welcomed"] += 1
                                time.sleep(dly)
                            km[gid] = cm
                            break
                km[gid] = cm
                
            except Exception as e:
                log("❌ Group error: {}".format(str(e)))
        
        time.sleep(pol)
    log("🛑 Bot stopped")

@app.route("/")
def index():
    return render_template_string(PAGE_HTML)

@app.route("/start", methods=["POST"])
def start_bot():
    global BOT_THREAD, STOP_EVENT
    if BOT_THREAD and BOT_THREAD.is_alive():
        return jsonify({"message": "Already running!"})
    
    data = request.form
    token = data.get("token", "")
    wl = [m.strip() for m in data.get("welcome", "").splitlines() if m.strip()]
    gids = ",".join([g.strip() for g in data.get("group_ids", "").split(",") if g.strip()])
    adm = data.get("admin_ids", "")
    
    if not all([token, gids, wl]):
        return jsonify({"message": "❌ Token, Groups & Welcome required!"})
    
    STOP_EVENT.clear()
    BOT_THREAD = threading.Thread(
        target=run_bot, 
        args=(token, wl, gids, int(data.get("delay", 3)), int(data.get("poll", 5)), 
              data.get("use_custom_name") == "yes", data.get("enable_commands") == "yes", adm),
        daemon=True
    )
    BOT_THREAD.start()
    log("🚀 Bot STARTED!")
    return jsonify({"message": "✅ Bot Started! Check logs..."})

@app.route("/stop", methods=["POST"])
def stop_bot():
    global BOT_THREAD
    STOP_EVENT.set()
    if BOT_THREAD:
        BOT_THREAD.join(timeout=2)
    log("🛑 Bot STOPPED!")
    return jsonify({"message": "🛑 Bot Stopped!"})

@app.route("/logs")
def get_logs():
    return jsonify({"logs": LOGS[-100:]})

# 🔥 CLEAN HTML - SINGLE QUOTES
PAGE_HTML = '''<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>🚀 NEON BOT v3.2</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:Segoe UI,Tahoma,Geneva,Verdana,sans-serif;background:linear-gradient(135deg,#0c0c0c 0%,#1a1a2e 50%,#16213e 100%);min-height:100vh;color:#fff;padding:15px}
.container{max-width:700px;margin:0 auto;background:rgba(0,0,0,0.9);border:2px solid #00ffff;border-radius:15px;padding:25px;box-shadow:0 15px 40px rgba(0,255,255,0.3)}
h1{text-align:center;font-size:2.2em;margin-bottom:20px;background:linear-gradient(45deg,#00ffff,#ff00ff,#ffff00);background-size:300% 300%;-webkit-background-clip:text;-webkit-text-fill-color:transparent;animation:gradient 2s ease infinite}
@keyframes gradient{0%{background-position:0% 50%}50%{background-position:100% 50%}100%{background-position:0% 50%}}
.status{display:flex;align-items:center;gap:12px;padding:15px;background:rgba(0,255,255,0.1);border-radius:10px;margin:20px 0;border-left:4px solid #00ffff;font-weight:bold}
.status.online{color:#00ff88}.status.offline{color:#ff5555}
.btn{display:block;width:100%;padding:15px;margin:10px 0;font-size:1.1em;font-weight:bold;border:none;border-radius:10px;cursor:pointer;transition:all 0.3s;text-transform:uppercase;letter-spacing:1px}
.btn-primary{background:linear-gradient(45deg,#00ffff,#0099ff);color:#000;box-shadow:0 5px 15px rgba(0,255,255,0.4)}
.btn-success{background:linear-gradient(45deg,#00ff88,#00cc66);color:#000;box-shadow:0 5px 15px rgba(0,255,136,0.4)}
.btn-danger{background:linear-gradient(45deg,#ff5555,#cc3333);color:#fff;box-shadow:0 5px 15px rgba(255,85,85,0.4)}
.btn:hover{transform:translateY(-2px);box-shadow:0 8px 25px rgba(0,255,255,0.5)}
.form-group{margin:20px 0}
label{display:block;margin-bottom:8px;font-weight:bold;color:#00ffff;font-size:1em}
input,textarea{width:100%;padding:12px;border:2px solid rgba(0,255,255,0.3);border-radius:8px;background:rgba(255,255,255,0.05);color:#fff;font-size:1em}
input:focus,textarea:focus{outline:none;border-color:#00ffff;box-shadow:0 0 15px rgba(0,255,255,0.4)}
textarea{height:100px;resize:vertical}
.checkbox-group{display:flex;align-items:center;gap:10px;margin:15px 0}
.checkbox-group input{width:auto;transform:scale(1.2)}
.logs{background:rgba(0,0,0,0.7);border:1px solid #00ffff;border-radius:10px;height:280px;overflow-y:auto;padding:15px;font-family:monospace;font-size:0.85em;line-height:1.4}
.log-entry{margin:4px 0;padding:8px;border-radius:6px;background:rgba(0,255,255,0.05);word-break:break-word}
.log-success{color:#00ff88}.log-error{color:#ff5555}.log-info{color:#00ffff}
#logs{max-height:350px;overflow-y:auto}
@media(max-width:600px){.container{padding:20px}h1{font-size:1.8em}}
</style>
</head>
<body>
<div class="container">
<h1>🚀 NEON BOT v3.2</h1>
<div class="status offline" id="status">
<span id="status-icon">🛑</span>
<span id="status-text">Bot Offline</span>
</div>

<form id="botForm">
<div class="form-group">
<label>🔑 Session Token</label>
<input type="text" name="token" placeholder="AABCxyz123... (Instagram sessionid)" required>
</div>
<div class="form-group">
<label>📝 Welcome Messages</label>
<textarea name="welcome" placeholder="Welcome bro! 🔥&#10;Namaste ji 🙏&#10;New member! 👋">Welcome bro! 🔥
Namaste ji 🙏</textarea>
</div>
<div class="form-group">
<label>👥 Group IDs</label>
<input type="text" name="group_ids" placeholder="1234567890,0987654321" required>
</div>
<div class="form-group">
<label>⏱️ Delay (sec)</label>
<input type="number" name="delay" value="3" min="1" max="10">
</div>
<div class="form-group">
<label>🔄 Poll (sec)</label>
<input type="number" name="poll" value="5" min="2" max="30">
</div>
<div class="checkbox-group">
<input type="checkbox" id="customName" name="use_custom_name">
<label for="customName">✅ @username in welcome</label>
</div>
<div class="checkbox-group">
<input type="checkbox" id="commands" name="enable_commands" checked>
<label for="commands">⚙️ Enable Commands (/help /stats)</label>
</div>
<button type="submit" class="btn btn-success" id="startBtn">🚀 START BOT</button>
<button type="button" class="btn btn-danger" id="stopBtn" style="display:none">🛑 STOP BOT</button>
</form>

<div style="margin-top:25px">
<h3 style="color:#00ffff;margin-bottom:12px">📊 LIVE LOGS</h3>
<div id="logs" class="logs"></div>
</div>
</div>

<script>
const form=document.getElementById("botForm"),startBtn=document.getElementById("startBtn"),stopBtn=document.getElementById("stopBtn"),status=document.getElementById("status"),logs=document.getElementById("logs");
let interval;
function updateStatus(running){status.className=running?"status online":"status offline";status.querySelector("#status-icon").textContent=running?"✅":"🛑";status.querySelector("#status-text").textContent=running?"Bot Online":"Bot Offline";startBtn.style.display=running?"none":"block";stopBtn.style.display=running?"block":"none";}
function addLog(msg){const div=document.createElement("div");div.className="log-entry log-info";if(msg.includes("✅")||msg.includes("SUCCESS"))div.className+=" log-success";else if(msg.includes("❌")||msg.includes("FAILED")||msg.includes("ERROR"))div.className+=" log-error";div.textContent=msg;logs.appendChild(div);logs.scrollTop=logs.scrollHeight;}
form.onsubmit=async e=>{e.preventDefault();const fd=new FormData(form);try{const r=await fetch("/start",{method:"POST",body:fd}),d=await r.json();addLog(d.message);updateStatus(true);clearInterval(interval);interval=setInterval(updateLogs,2000);}catch(e){addLog("❌ "+e.message);}};
stopBtn.onclick=async()=>{try{const r=await fetch("/stop",{method:"POST"}),d=await r.json();addLog(d.message);updateStatus(false);clearInterval(interval);}catch(e){addLog("❌ "+e.message);}};
async function updateLogs(){try{const r=await fetch("/logs"),d=await r.json();d.logs.slice(-10).forEach(addLog);}catch(e){}}
setInterval(updateLogs,3000);updateLogs();
</script>
</body>
</html>'''

if __name__ == "__main__":
    log("🌟 NEON BOT v3.2 READY!")
    port = int(os.environ.get("PORT", 5000))
    log("📱 Open: http://localhost:{}".format(port))
    app.run(host="0.0.0.0", port=port, debug=False)
