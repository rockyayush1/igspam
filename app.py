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
        cl.direct_send("/help-Commands/stats-Members/ping-Alive/time-Music/funny-Party/rules", thread_ids=[gid])
        log("Help sent to {}".format(sender_username))
        
    elif text in ["/stats", ".stats"]:
        cl.direct_send("STATS:Total:{} Today:{}".format(STATS['total_welcomed'], STATS['today_welcomed']), thread_ids=[gid])
        log("Stats sent to {}".format(sender_username))
        
    elif text in ["/count", ".count"]:
        cl.direct_send("MEMBERS:{}".format(len(group.users)), thread_ids=[gid])
        log("Count sent to {}".format(sender_username))
        
    elif text in ["/ping", ".ping"]:
        cl.direct_send("PONG!Bot alive", thread_ids=[gid])
        log("Ping from {}".format(sender_username))
        
    elif text in ["/time", ".time"]:
        now = datetime.now().strftime("%I:%M %p")
        cl.direct_send("TIME:{}".format(now), thread_ids=[gid])
        log("Time sent to {}".format(sender_username))
        
    elif text in ["/music", ".music"]:
        music_emojis = ["🎵","🎶","🎸","🎹"]
        music_msg = "".join(random.choices(music_emojis, k=4))
        cl.direct_send(music_msg, thread_ids=[gid])
        log("Music sent to {}".format(sender_username))
        
    elif text in ["/funny", ".funny"]:
        funny_msgs = ["Hahaha!😂","LOL!🤣","Mast!😆"]
        cl.direct_send(random.choice(funny_msgs), thread_ids=[gid])
        log("Funny sent to {}".format(sender_username))
        
    elif text in ["/masti", ".masti"]:
        masti_msgs = ["Party!🎉","Masti!🥳","Fire!🔥"]
        cl.direct_send(random.choice(masti_msgs), thread_ids=[gid])
        log("Masti sent to {}".format(sender_username))
        
    elif text in ["/rules", ".rules"]:
        cl.direct_send("RULES:1.No spam 2.Respect 3.Active 4.Fun!", thread_ids=[gid])
        log("Rules sent to {}".format(sender_username))

def run_bot():
    global STATS
    cl = login_client()
    if not cl:
        log("Login failed!")
        return

    welcome_raw = BOT_CONFIG.get('welcome', 'Welcome!')
    welcome_messages = welcome_raw.replace("
", "
").split("
")
    final_welcome = []
    i = 0
    while i < len(welcome_messages):
        msg = welcome_messages[i].strip()
        if len(msg) > 0:
            final_welcome.append(msg)
        i = i + 1
    
    group_ids = []
    group_raw = BOT_CONFIG.get('group_ids', '')
    if len(group_raw) > 0:
        parts = group_raw.split(",")
        i = 0
        while i < len(parts):
            gid = parts[i].strip()
            if len(gid) > 0:
                group_ids.append(gid)
            i = i + 1
    
    log("Bot started! Commands:ON")
    known_members = {}
    last_message_ids = {}
    
    i = 0
    while i < len(group_ids):
        gid = group_ids[i]
        try:
            group = cl.direct_thread(gid)
            known_members[gid] = set()
            j = 0
            while j < len(group.users):
                known_members[gid].add(group.users[j].pk)
                j = j + 1
            if len(group.messages) > 0:
                last_message_ids[gid] = group.messages[0].id
            log("Group {} ready".format(gid[:15]))
        except Exception as e:
            log("Group {} failed: {}".format(gid[:15], str(e)[:30]))
            known_members[gid] = set()
        i = i + 1

    if STATS["last_reset"] != datetime.now().date():
        STATS["today_welcomed"] = 0
        STATS["last_reset"] = datetime.now().date()

    while not STOP_EVENT.is_set():
        try:
            i = 0
            while i < len(group_ids):
                gid = group_ids[i]
                if STOP_EVENT.is_set():
                    break
                try:
                    group = cl.direct_thread(gid)
                    current_members = set()
                    j = 0
                    while j < len(group.users):
                        current_members.add(group.users[j].pk)
                        j = j + 1
                    
                    if BOT_CONFIG.get("commands_enabled", True) and len(group.messages) > 0:
                        last_id = last_message_ids.get(gid)
                        new_messages = []
                        
                        k = 0
                        while k < len(group.messages):
                            msg = group.messages[k]
                            if last_id and msg.id == last_id:
                                break
                            new_messages.append(msg)
                            k = k + 1
                        
                        m = len(new_messages) - 1
                        while m >= 0:
                            message = new_messages[m]
                            if message.user_id == cl.user_id:
                                m = m - 1
                                continue
                            sender = None
                            j = 0
                            while j < len(group.users):
                                if group.users[j].pk == message.user_id:
                                    sender = group.users[j]
                                    break
                                j = j + 1
                            if sender and sender.username:
                                process_commands(cl, group, gid, message, sender.username)
                            m = m - 1
                        
                        if len(group.messages) > 0:
                            last_message_ids[gid] = group.messages[0].id
                    
                    new_members = current_members - known_members.get(gid, set())
                    if len(new_members) > 0:
                        j = 0
                        while j < len(group.users):
                            user = group.users[j]
                            if user.pk in new_members and user.username:
                                log("NEW:@{}".format(user.username))
                                n = 0
                                while n < len(final_welcome):
                                    if STOP_EVENT.is_set():
                                        break
                                    msg = final_welcome[n]
                                    final_msg = "@{} {}".format(user.username, msg) if BOT_CONFIG.get('mention', 'yes') == 'yes' else msg
                                    cl.direct_send(final_msg, thread_ids=[gid])
                                    STATS["total_welcomed"] = STATS["total_welcomed"] + 1
                                    STATS["today_welcomed"] = STATS["today_welcomed"] + 1
                                    log("Welcomed @{}".format(user.username))
                                    time.sleep(int(BOT_CONFIG.get('delay', 3)))
                                    n = n + 1
                                known_members[gid].add(user.pk)
                            j = j + 1
                    
                    known_members[gid] = current_members
                except Exception as e:
                    log("Group error: {}".format(str(e)[:50]))
                i = i + 1
            
            time.sleep(int(BOT_CONFIG.get('poll', 10)))
        except Exception as e:
            log("Main loop error: {}".format(str(e)[:50]))
            time.sleep(10)

    log("Bot stopped!")

@app.route("/")
def index():
    return '''<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>BOT v9</title>
<style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:Arial,sans-serif;background:#000;color:#fff;padding:20px;min-height:100vh;}
.card{max-width:500px;margin:0 auto;background:rgba(10,10,30,0.95);border-radius:20px;padding:30px;border:2px solid #00ff88;box-shadow:0 0 40px rgba(0,255,136,0.4);}
h1{text-align:center;color:#00ff88;font-size:2.5em;margin-bottom:25px;text-shadow:0 0 20px #00ff88;}
.input-group{margin-bottom:20px;}label{display:block;margin-bottom:8px;color:#00eaff;font-weight:bold;}
input,textarea,select{width:100%;padding:15px;border:2px solid #00eaff;border-radius:10px;background:rgba(0,0,0,0.6);color:#fff;font-size:16px;}
input:focus,textarea:focus,select:focus{outline:none;border-color:#00ff88;box-shadow:0 0 20px rgba(0,255,136,0.4);}
textarea{min-height:100px;}.btn{width:100%;padding:18px;font-size:18px;font-weight:bold;border:none;border-radius:12px;cursor:pointer;margin:10px 0;transition:all .3s;}
.btn-token{background:#00ff88;color:#000;box-shadow:0 5px 20px rgba(0,255,136,0.4);}
.btn-start{background:#00eaff;color:#fff;box-shadow:0 5px 20px rgba(0,198,255,0.4);}
.btn-stop{background:#ff4757;color:#fff;box-shadow:0 5px 20px rgba(255,71,87,0.4);}
.btn:hover{transform:translateY(-3px);box-shadow:0 10px 30px;}
.logs{background:rgba(0,0,0,0.8);border:2px solid #00eaff;border-radius:15px;padding:20px;height:280px;overflow-y:auto;font-family:monospace;font-size:14px;line-height:1.6;color:#00ff88;margin-top:20px;}
.logs::-webkit-scrollbar{width:6px;}.logs::-webkit-scrollbar-thumb{background:#00ff88;border-radius:3px;}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:15px;margin:20px 0;}
.stat-card{background:rgba(0,255,136,0.15);border:2px solid #00ff88;border-radius:10px;padding:15px;text-align:center;}
.status{padding:15px;border-radius:10px;margin:20px 0;text-align:center;font-weight:bold;display:none;}
.success{background:rgba(0,255,136,0.2);border:2px solid #00ff88;color:#00ff88;}
.error{background:rgba(255,71,87,0.2);border:2px solid #ff4757;color:#ff4757;}</style></head><body>
<div class="card">
<h1>🤖 BOT v9</h1>
<div id="status" class="status"></div>
<div class="input-group"><label>Token</label><input id="token" placeholder="56748960230%3AF8ELTyGZTkSadW..."><button class="btn btn-token" onclick="setToken()">SET TOKEN</button></div>
<div class="input-group"><label>Welcome</label><textarea id="welcome">Welcome brother!&#10;Glad you joined!&#10;Stay active!</textarea></div>
<div class="input-group"><label>Groups</label><input id="group_ids" placeholder="24632887389663044,12345678901234567"></div>
<div class="input-group"><label>Delay</label><input type="number" id="delay" value="3" min="1" max="10"></div>
<div class="input-group"><label>Poll</label><input type="number" id="poll" value="10" min="5" max="30"></div>
<button class="btn btn-start" onclick="startBot()" id="startBtn" style="display:none;">START BOT</button>
<button class="btn btn-stop" onclick="stopBot()" id="stopBtn" style="display:none;">STOP BOT</button>
<div class="stats" id="stats" style="display:none;"><div class="stat-card"><strong>Total</strong><div id="total">0</div></div><div class="stat-card"><strong>Today</strong><div id="today">0</div></div></div>
<div class="logs" id="logs">Bot ready...</div>
</div>
<script>
function showStatus(msg,type="success"){const s=document.getElementById("status");s.textContent=msg;s.className="status "+type;s.style.display="block";setTimeout(()=>s.style.display="none",4000);}
async function setToken(){const form=new FormData();form.append("token",document.getElementById("token").value);form.append("welcome",document.getElementById("welcome").value);form.append("group_ids",document.getElementById("group_ids").value);form.append("delay",document.getElementById("delay").value);form.append("poll",document.getElementById("poll").value);const res=await fetch("/set_token",{method:"POST",body:form});const data=await res.json();if(data.status==="success"){showStatus("Token set!");document.getElementById("startBtn").style.display="block";}else showStatus("Error!","error");}
async function startBot(){const res=await fetch("/start",{method:"POST"});const data=await res.json();if(data.status==="started"){showStatus("Bot started!");document.getElementById("startBtn").style.display="none";document.getElementById("stopBtn").style.display="block";document.getElementById("stats").style.display="grid";}}
async function stopBot(){await fetch("/stop",{method:"POST"});showStatus("Bot stopped!");document.getElementById("stopBtn").style.display="none";document.getElementById("startBtn").style.display="block";}
setInterval(async()=>{try{const res=await fetch("/logs");const data=await res.json();document.getElementById("logs").innerHTML=data.logs.slice(-12).map(l=>"<div>"+l+"</div>").join("");document.getElementById("logs").scrollTop=9999;document.getElementById("total").textContent=data.stats.total_welcomed||0;document.getElementById("today").textContent=data.stats.today_welcomed||0;}catch(e){}},2000);
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
        log("Token saved!")
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
    log("Bot started!")
    return jsonify({"status": "started"})

@app.route("/stop", methods=["POST"])
def stop_bot():
    STOP_EVENT.set()
    log("Stop signal!")
    return jsonify({"status": "stopping"})

@app.route("/logs")
def get_logs():
    return jsonify({"logs": LOGS[-30:], "stats": STATS})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("Instagram Bot v9 - ULTRA SAFE!")
    app.run(host="0.0.0.0", port=port, debug=False)
