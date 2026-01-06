import os
import threading
import time
import random
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify
from instagrapi import Client
import json

app = Flask(__name__)
BOT_THREAD = None
STOP_EVENT = threading.Event()
LOGS = []
SESSION_FILE = "session.json"
SESSION_TOKEN = ""
STATS = {"total_welcomed": 0, "today_welcomed": 0, "last_reset": datetime.now().date()}
BOT_CONFIG = {"commands_enabled": True}

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    lm = "[{}] {}".format(ts, msg)
    LOGS.append(lm)
    print(lm)

def load_session():
    try:
        if os.path.exists(SESSION_FILE):
            with open(SESSION_FILE, 'r') as f:
                data = json.load(f)
                log("Session loaded")
                return data
    except:
        if os.path.exists(SESSION_FILE):
            os.remove(SESSION_FILE)
    return None

def login_client():
    global SESSION_TOKEN
    cl = Client()
    
    session_data = load_session()
    if session_data:
        try:
            cl.load_settings(SESSION_FILE)
            cl.account_info()
            log("Session login OK!")
            return cl
        except:
            if os.path.exists(SESSION_FILE):
                os.remove(SESSION_FILE)
    
    if SESSION_TOKEN:
        try:
            cl.login_by_sessionid(SESSION_TOKEN)
            cl.dump_settings(SESSION_FILE)
            log("Token login OK!")
            return cl
        except Exception as e:
            log("Token fail: {}".format(str(e)[:50]))
    
    return None

def process_commands(cl, group, gid, message, sender_username):
    text = message.text.lower().strip() if message.text else ""
    
    if text in ["/help", ".help", "!help"]:
        help_msg = "/help - Commands
/stats - Stats
/count - Members
/ping - Alive
/time - Time
/music - Music
/funny - Funny
/masti - Party
/rules - Rules"
        cl.direct_send(help_msg, thread_ids=[gid])
        log("Help sent to {}".format(sender_username))
        
    elif text in ["/stats", ".stats"]:
        stats_msg = "STATS:
Total: {}
Today: {}".format(STATS['total_welcomed'], STATS['today_welcomed'])
        cl.direct_send(stats_msg, thread_ids=[gid])
        log("Stats sent to {}".format(sender_username))
        
    elif text in ["/count", ".count"]:
        count_msg = "MEMBERS: {}".format(len(group.users))
        cl.direct_send(count_msg, thread_ids=[gid])
        log("Count sent to {}".format(sender_username))
        
    elif text in ["/ping", ".ping"]:
        cl.direct_send("PONG! Bot alive", thread_ids=[gid])
        log("Ping from {}".format(sender_username))
        
    elif text in ["/time", ".time"]:
        now = datetime.now().strftime("%I:%M %p")
        time_msg = "TIME: {}".format(now)
        cl.direct_send(time_msg, thread_ids=[gid])
        log("Time sent to {}".format(sender_username))
        
    elif text in ["/music", ".music"]:
        music_emojis = ["🎵","🎶","🎸","🎹","🎤","🎧","🎺","🎷"]
        music_msg = "♪♫♪♫ " + " ".join(random.choices(music_emojis, k=5))
        cl.direct_send(music_msg, thread_ids=[gid])
        log("Music sent to {}".format(sender_username))
        
    elif text in ["/funny", ".funny"]:
        funny_msgs = ["Hahaha! 😂", "LOL! 🤣", "Mast! 😆", "Pagal! 🤪", "King! 👑😂"]
        cl.direct_send(random.choice(funny_msgs), thread_ids=[gid])
        log("Funny sent to {}".format(sender_username))
        
    elif text in ["/masti", ".masti"]:
        masti_msgs = ["Party! 🎉", "Masti! 🥳", "Dhamaal! 💃", "Fire! 🔥", "Enjoy! 🎊"]
        cl.direct_send(random.choice(masti_msgs), thread_ids=[gid])
        log("Masti sent to {}".format(sender_username))
        
    elif text in ["/rules", ".rules"]:
        rules_msg = "RULES: 1.No spam 2.Respect 3.Stay active 4.Have fun!"
        cl.direct_send(rules_msg, thread_ids=[gid])
        log("Rules sent to {}".format(sender_username))

def run_bot():
    global STATS
    cl = login_client()
    if not cl:
        log("Login failed!")
        return

    welcome_raw = BOT_CONFIG.get('welcome', 'Welcome!')
    welcome_messages = [m.strip() for m in welcome_raw.split("
") if m.strip()]
    group_ids = [g.strip() for g in BOT_CONFIG.get('group_ids', '').split(',') if g.strip()]
    
    log("Bot started! Commands: ON")
    known_members = {}
    last_message_ids = {}
    
    for gid in group_ids:
        try:
            group = cl.direct_thread(gid)
            known_members[gid] = {user.pk for user in group.users}
            last_message_ids[gid] = group.messages[0].id if group.messages else None
            log("Group {} ready".format(gid[:15]))
        except Exception as e:
            log("Group {} failed: {}".format(gid[:15], str(e)[:30]))
            known_members[gid] = set()
            last_message_ids[gid] = None

    if STATS["last_reset"] != datetime.now().date():
        STATS["today_welcomed"] = 0
        STATS["last_reset"] = datetime.now().date()

    while not STOP_EVENT.is_set():
        try:
            for gid in group_ids:
                if STOP_EVENT.is_set():
                    break
                try:
                    group = cl.direct_thread(gid)
                    current_members = {user.pk for user in group.users}
                    
                    # Check commands in new messages
                    if BOT_CONFIG.get("commands_enabled", True) and group.messages:
                        last_id = last_message_ids.get(gid)
                        new_messages = []
                        
                        for msg in group.messages:
                            if last_id and msg.id == last_id:
                                break
                            new_messages.append(msg)
                        
                        for message in reversed(new_messages):
                            if message.user_id == cl.user_id:
                                continue
                            sender = next((u for u in group.users if u.pk == message.user_id), None)
                            if sender and sender.username:
                                process_commands(cl, group, gid, message, sender.username)
                        
                        last_message_ids[gid] = group.messages[0].id if group.messages else None
                    
                    # Welcome new members
                    new_members = current_members - known_members[gid]
                    if new_members:
                        for user in group.users:
                            if user.pk in new_members and user.username:
                                log("NEW: @{}".format(user.username))
                                for msg in welcome_messages:
                                    if STOP_EVENT.is_set():
                                        break
                                    final_msg = "@{} {}".format(user.username, msg) if BOT_CONFIG.get('mention', 'yes') == 'yes' else msg
                                    cl.direct_send(final_msg, thread_ids=[gid])
                                    STATS["total_welcomed"] += 1
                                    STATS["today_welcomed"] += 1
                                    log("Welcomed @{}".format(user.username))
                                    time.sleep(int(BOT_CONFIG.get('delay', 3)))
                                known_members[gid].add(user.pk)
                    
                    known_members[gid] = current_members
                except Exception as e:
                    log("Group error: {}".format(str(e)[:50]))
            
            time.sleep(int(BOT_CONFIG.get('poll', 10)))
        except Exception as e:
            log("Main loop error: {}".format(str(e)[:50]))
            time.sleep(10)

    log("Bot stopped!")

@app.route("/")
def index():
    return '''<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>COMMAND BOT v6</title>
<style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:Arial,sans-serif;background:#000;color:#fff;padding:20px;min-height:100vh;}
.card{max-width:500px;margin:0 auto;background:rgba(10,10,30,0.95);border-radius:20px;padding:30px;border:2px solid #00ff88;box-shadow:0 0 40px rgba(0,255,136,0.4);}
h1{text-align:center;color:#00ff88;font-size:2.5em;margin-bottom:25px;text-shadow:0 0 20px #00ff88;}
.input-group{margin-bottom:20px;}label{display:block;margin-bottom:8px;color:#00eaff;font-weight:bold;}
input,textarea,select{width:100%;padding:15px;border:2px solid #00eaff;border-radius:10px;background:rgba(0,0,0,0.6);color:#fff;font-size:16px;}
input:focus,textarea:focus,select:focus{outline:none;border-color:#00ff88;box-shadow:0 0 20px rgba(0,255,136,0.4);}
textarea{min-height:100px;}.btn{width:100%;padding:18px;font-size:18px;font-weight:bold;border:none;border-radius:12px;cursor:pointer;margin:10px 0;transition:all .3s;}
.btn-token{background:linear-gradient(45deg,#00ff88,#00cc66);color:#000;box-shadow:0 5px 20px rgba(0,255,136,0.4);}
.btn-start{background:linear-gradient(45deg,#00eaff,#0072ff);color:#fff;box-shadow:0 5px 20px rgba(0,198,255,0.4);}
.btn-stop{background:linear-gradient(45deg,#ff4757,#ff3838);color:#fff;box-shadow:0 5px 20px rgba(255,71,87,0.4);}
.btn:hover{transform:translateY(-3px);box-shadow:0 10px 30px;}
.logs{background:rgba(0,0,0,0.8);border:2px solid #00eaff;border-radius:15px;padding:20px;height:280px;overflow-y:auto;font-family:monospace;font-size:14px;line-height:1.6;color:#00ff88;margin-top:20px;}
.logs::-webkit-scrollbar{width:6px;}.logs::-webkit-scrollbar-thumb{background:#00ff88;border-radius:3px;}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:15px;margin:20px 0;}
.stat-card{background:rgba(0,255,136,0.15);border:2px solid #00ff88;border-radius:10px;padding:15px;text-align:center;}
.commands{background:rgba(255,71,87,0.1);border:2px solid #ff4757;border-radius:10px;padding:15px;margin-top:15px;}
.status{padding:15px;border-radius:10px;margin:20px 0;text-align:center;font-weight:bold;display:none;}
.success{background:rgba(0,255,136,0.2);border:2px solid #00ff88;color:#00ff88;}
.error{background:rgba(255,71,87,0.2);border:2px solid #ff4757;color:#ff4757;}
@media(max-width:600px){.card{padding:20px;}}</style></head><body>
<div class="card">
<h1>🚀 COMMAND BOT v6</h1>
<div id="status" class="status"></div>

<div class="input-group"><label>🔑 Token *</label><input type="text" id="token" placeholder="56748960230%3AF8ELTyGZTkSadW...">
<button class="btn btn-token" onclick="setToken()">✅ SET TOKEN</button></div>

<div class="input-group"><label>💬 Welcome</label><textarea id="welcome">Welcome brother!
Glad you joined!
Stay active 24x7!</textarea></div>

<div class="input-group"><label>👥 Groups *</label><input type="text" id="group_ids" placeholder="24632887389663044,12345678901234567"></div>

<div class="input-group"><label>⏱️ Delay</label><input type="number" id="delay" value="3" min="1" max="10"></div>
<div class="input-group"><label>🔄 Poll</label><input type="number" id="poll" value="10" min="5" max="30"></div>

<button class="btn btn-start" onclick="startBot()" id="startBtn" style="display:none;">▶️ START BOT</button>
<button class="btn btn-stop" onclick="stopBot()" id="stopBtn" style="display:none;">🛑 STOP BOT</button>

<div class="stats" id="stats" style="display:none;">
<div class="stat-card"><strong>Total</strong><div id="total">0</div></div>
<div class="stat-card"><strong>Today</strong><div id="today">0</div></div>
</div>

<div class="commands">
<strong>🔥 COMMANDS WORKING:</strong><br>
/help /stats /count /ping /time /music /funny /masti /rules
</div>

<div class="logs" id="logs">Bot ready! Set token to start...</div>
</div>

<script>
function showStatus(msg, type="success") {
    const s = document.getElementById("status");
    s.textContent = msg;
    s.className = "status " + type;
    s.style.display = "block";
    setTimeout(()=>s.style.display="none", 4000);
}

async function setToken() {
    const form = new FormData();
    form.append("token", document.getElementById("token").value);
    form.append("welcome", document.getElementById("welcome").value);
    form.append("group_ids", document.getElementById("group_ids").value);
    form.append("delay", document.getElementById("delay").value);
    form.append("poll", document.getElementById("poll").value);
    
    const res = await fetch("/set_token", {method:"POST", body:form});
    const data = await res.json();
    if(data.status === "success") {
        showStatus("Token set! Click START");
        document.getElementById("startBtn").style.display = "block";
    } else showStatus("Error!", "error");
}

async function startBot() {
    const res = await fetch("/start", {method:"POST"});
    const data = await res.json();
    if(data.status === "started") {
        showStatus("Bot + Commands started!");
        document.getElementById("startBtn").style.display = "none";
        document.getElementById("stopBtn").style.display = "block";
        document.getElementById("stats").style.display = "grid";
    }
}

async function stopBot() {
    await fetch("/stop", {method:"POST"});
    showStatus("Bot stopped!");
    document.getElementById("stopBtn").style.display = "none";
    document.getElementById("startBtn").style.display = "block";
}

setInterval(async()=>{
    try {
        const res = await fetch("/logs");
        const data = await res.json();
        document.getElementById("logs").innerHTML = data.logs.slice(-12).map(l=>"<div>"+l+"</div>").join("");
        document.getElementById("logs").scrollTop = 9999;
        document.getElementById("total").textContent = data.stats.total_welcomed || 0;
        document.getElementById("today").textContent = data.stats.today_welcomed || 0;
    } catch(e) {}
}, 2000);
</script></body></html>'''

@app.route("/set_token", methods=["POST"])
def set_token():
    global SESSION_TOKEN, BOT_CONFIG
    token = request.form.get("token", "").strip()
    if token:
        SESSION_TOKEN = token
        BOT_CONFIG.update({
            "token": token,
            "welcome": request.form.get("welcome", ""),
            "group_ids": request.form.get("group_ids", ""),
            "delay": request.form.get("delay", "3"),
            "poll": request.form.get("poll", "10"),
            "mention": "yes",
            "commands_enabled": True
        })
        log("Token + Config saved!")
        return jsonify({"status": "success"})
    return jsonify({"status": "error"})

@app.route("/start", methods=["POST"])
def start_bot():
    global BOT_THREAD, STOP_EVENT
    if BOT_THREAD and BOT_THREAD.is_alive():
        return jsonify({"status": "running"})
    
    if not SESSION_TOKEN or not BOT_CONFIG.get('group_ids'):
        return jsonify({"status": "error"})
    
    STOP_EVENT.clear()
    BOT_THREAD = threading.Thread(target=run_bot, daemon=True)
    BOT_THREAD.start()
    log("Bot started with COMMANDS!")
    return jsonify({"status": "started"})

@app.route("/stop", methods=["POST"])
def stop_bot():
    STOP_EVENT.set()
    log("Stop signal sent!")
    return jsonify({"status": "stopping"})

@app.route("/logs")
def get_logs():
    return jsonify({"logs": LOGS[-30:], "stats": STATS})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("Instagram Command Bot v6 - FIXED!")
    app.run(host="0.0.0.0", port=port, debug=False)
