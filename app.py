import os
import threading
import time
import random
import json
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify
from instagrapi import Client

app = Flask(__name__)
BOT_THREAD = None
STOP_EVENT = threading.Event()
LOGS = []
SESSION_FILE = "session.json"
SESSION_TOKEN = None
STATS = {"total_welcomed": 0, "today_welcomed": 0, "last_reset": datetime.now().date()}
BOT_CONFIG = {"auto_replies": {}, "auto_reply_active": False, "target_spam": {}, "spam_active": {}, "media_library": {}}

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    lm = "[" + ts + "] " + msg
    LOGS.append(lm)
    print(lm)

MUSIC_EMOJIS = ["🎵", "🎶", "🎸", "🎹", "🎤", "🎧", "🎺", "🎷"]
FUNNY = ["Hahaha! 😂", "LOL! 🤣", "Mast! 😆", "Pagal! 🤪", "King! 👑😂"]
MASTI = ["Party! 🎉", "Masti! 🥳", "Dhamaal! 💃", "Full ON! 🔥", "Enjoy! 🎊"]

def login_with_token(cl, token):
    """Token se login karo"""
    try:
        cl.set_settings({"uuid": "9e3f5d8e-7b2a-4c5d-9f8e-2a3b4c5d6e7f"})  # Fixed UUID
        cl.login_by_sessionid(token)
        log("✅ Token login successful!")
        user_info = cl.user_info()
        log(f"Logged in as: @{user_info.username} (ID: {user_info.pk})")
        return True
    except Exception as e:
        log(f"❌ Token login failed: {str(e)}")
        return False

def run_bot(token, wm, gids, dly, pol, ucn, ecmd, admin_ids):
    global SESSION_TOKEN
    SESSION_TOKEN = token
    cl = Client()
    
    # Token login
    if not login_with_token(cl, token):
        return
    
    # Session save karo future ke liye
    try:
        cl.dump_settings(SESSION_FILE)
        log("Session file saved")
    except:
        pass
    
    log("🚀 Bot started successfully!")
    log(f"👑 Admins: {admin_ids}")
    
    km = {}
    lm = {}
    for gid in gids:
        try:
            g = cl.direct_thread(gid)
            km[gid] = {u.pk for u in g.users}
            lm[gid] = g.messages[0].id if g.messages else None
            BOT_CONFIG["spam_active"][gid] = False
            log(f"✅ Group {gid} ready")
        except Exception as e:
            log(f"❌ Group {gid} error: {str(e)}")
            km[gid] = set()
            lm[gid] = None
    
    global STATS
    if STATS["last_reset"] != datetime.now().date():
        STATS["today_welcomed"] = 0
        STATS["last_reset"] = datetime.now().date()
    
    while not STOP_EVENT.is_set():
        try:
            for gid in gids:
                if STOP_EVENT.is_set():
                    break
                try:
                    g = cl.direct_thread(gid)
                    
                    # Spam logic
                    if BOT_CONFIG["spam_active"].get(gid, False):
                        tu = BOT_CONFIG["target_spam"].get(gid, {}).get("username")
                        sm = BOT_CONFIG["target_spam"].get(gid, {}).get("message")
                        if tu and sm:
                            cl.direct_send("@" + tu + " " + sm, thread_ids=[gid])
                            log(f"📨 Spam to @{tu}")
                            time.sleep(2)
                    
                    # Commands + Auto-reply
                    if ecmd or BOT_CONFIG["auto_reply_active"]:
                        nm = []
                        if lm[gid]:
                            for m in g.messages:
                                if m.id == lm[gid]:
                                    break
                                nm.append(m)
                        for m in reversed(nm):
                            if m.user_id == cl.user_id:
                                continue
                            sender = next((u for u in g.users if u.pk == m.user_id), None)
                            if not sender:
                                continue
                            su = sender.username.lower()
                            ia = su in [a.lower() for a in admin_ids] if admin_ids else True
                            t = m.text.strip() if m.text else ""
                            tl = t.lower()
                            
                            # Auto-reply
                            if BOT_CONFIG["auto_reply_active"] and tl in BOT_CONFIG["auto_replies"]:
                                cl.direct_send(BOT_CONFIG["auto_replies"][tl], thread_ids=[gid])
                                log("🤖 Auto-reply sent")
                            
                            if not ecmd:
                                continue
                            
                            # Commands (same as original)
                            if tl in ["/help", "!help"]:
                                cl.direct_send("COMMANDS: /autoreply /stopreply /addvideo /addaudio /video /audio /library /music /funny /masti /kick /spam /stopspam /rules /stats /count /ping /time /about /welcome", thread_ids=[gid])
                                log("📋 Help sent")
                            elif tl in ["/stats", "!stats"]:
                                cl.direct_send(f"📊 STATS - Total: {STATS['total_welcomed']} Today: {STATS['today_welcomed']}", thread_ids=[gid])
                            elif tl in ["/count", "!count"]:
                                cl.direct_send(f"👥 MEMBERS: {len(g.users)}", thread_ids=[gid])
                            elif tl in ["/ping", "!ping"]:
                                cl.direct_send("🏓 Pong! Bot Alive! 🚀", thread_ids=[gid])
                            elif tl in ["/time", "!time"]:
                                cl.direct_send(f"🕐 TIME: {datetime.now().strftime('%I:%M %p')}", thread_ids=[gid])
                            elif tl.startswith("/autoreply "):
                                p = t.split(" ", 2)
                                if len(p) >= 3:
                                    BOT_CONFIG["auto_replies"][p[1].lower()] = p[2]
                                    BOT_CONFIG["auto_reply_active"] = True
                                    cl.direct_send(f"✅ Auto-reply set: {p[1]} -> {p[2][:50]}...", thread_ids=[gid])
                            elif tl in ["/stopreply", "!stopreply"]:
                                BOT_CONFIG["auto_reply_active"] = False
                                BOT_CONFIG["auto_replies"] = {}
                                cl.direct_send("⏹️ Auto-reply stopped!", thread_ids=[gid])
                            elif ia and tl.startswith("/spam "):
                                p = t.split(" ", 2)
                                if len(p) >= 3:
                                    BOT_CONFIG["target_spam"][gid] = {"username": p[1].replace("@", ""), "message": p[2]}
                                    BOT_CONFIG["spam_active"][gid] = True
                                    cl.direct_send("🔥 Spam started!", thread_ids=[gid])
                            elif ia and tl in ["/stopspam", "!stopspam"]:
                                BOT_CONFIG["spam_active"][gid] = False
                                cl.direct_send("⏹️ Spam stopped!", thread_ids=[gid])
                        
                        if g.messages:
                            lm[gid] = g.messages[0].id
                    
                    # Welcome new members
                    cm = {u.pk for u in g.users}
                    nwm = cm - km[gid]
                    if nwm:
                        for u in g.users:
                            if u.pk in nwm and u.username:
                                if STOP_EVENT.is_set():
                                    break
                                log(f"👋 NEW: @{u.username}")
                                for ms in wm:
                                    if STOP_EVENT.is_set():
                                        break
                                    fm = (f"@{u.username} " + ms) if ucn else ms
                                    cl.direct_send(fm, thread_ids=[gid])
                                    STATS["total_welcomed"] += 1
                                    STATS["today_welcomed"] += 1
                                    log(f"✅ Welcomed @{u.username}")
                                    time.sleep(dly)
                                km[gid].add(u.pk)
                    km[gid] = cm
                    
                except Exception as e:
                    log(f"⚠️ Group {gid} error: {str(e)}")
            time.sleep(pol)
        except Exception as e:
            log(f"❌ Main loop error: {str(e)}")
            time.sleep(10)
    log("🛑 Bot stopped")

@app.route("/")
def index():
    return render_template_string(PAGE_HTML)

@app.route("/set_token", methods=["POST"])
def set_token():
    global SESSION_TOKEN
    token = request.form.get("session_token", "").strip()
    if token:
        SESSION_TOKEN = token
        log(f"🔑 Token set: {token[:30]}...")
        return jsonify({"message": "✅ Token set successfully! Fill groups & start bot."})
    return jsonify({"message": "❌ Invalid token!"})

@app.route("/start", methods=["POST"])
def start_bot():
    global BOT_THREAD, STOP_EVENT
    if not SESSION_TOKEN:
        return jsonify({"message": "❌ First SET TOKEN!"})
    
    if BOT_THREAD and BOT_THREAD.is_alive():
        return jsonify({"message": "🤖 Already running!"})
    
    wl = [m.strip() for m in request.form.get("welcome", "").splitlines() if m.strip()]
    gids = [g.strip() for g in request.form.get("group_ids", "").split(",") if g.strip()]
    adm = [a.strip() for a in request.form.get("admin_ids", "").split(",") if a.strip()]
    
    if not gids or not wl:
        return jsonify({"message": "❌ Fill Groups & Welcome messages!"})
    
    STOP_EVENT.clear()
    BOT_THREAD = threading.Thread(target=run_bot, args=(SESSION_TOKEN, wl, gids, int(request.form.get("delay", 3)), int(request.form.get("poll", 5)), request.form.get("use_custom_name") == "yes", request.form.get("enable_commands") == "yes", adm), daemon=True)
    BOT_THREAD.start()
    return jsonify({"message": "🚀 Bot started! Check logs..."})

@app.route("/stop", methods=["POST"])
def stop_bot():
    STOP_EVENT.set()
    return jsonify({"message": "⏹️ Bot stopped!"})

@app.route("/logs")
def get_logs():
    return jsonify({"logs": LOGS[-200:], "token_set": bool(SESSION_TOKEN)})

# Updated HTML with Token field
PAGE_HTML = '''<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>NEON BOT v4</title><style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:Arial,sans-serif;min-height:100vh;background:#000;position:relative;color:#fff;padding:15px}body::before{content:'';position:fixed;top:0;left:0;width:100%;height:100%;background:linear-gradient(45deg,#000,#0f0f3a,#1a0033);animation:gradient 15s ease infinite}body::after{content:'';position:fixed;top:0;left:0;width:100%;height:100%;background:radial-gradient(circle at 20% 50%,rgba(0,255,255,.1),transparent 60%),radial-gradient(circle at 80% 80%,rgba(255,0,255,.1),transparent 60%);z-index:-1}@keyframes gradient{0%,100%{background-position:0% 50%}50%{background-position:100% 50%}}.c{max-width:700px;margin:0 auto;background:rgba(10,10,30,.9);border-radius:20px;padding:25px;border:2px solid rgba(0,255,255,.5);box-shadow:0 0 30px rgba(0,255,255,.3)}h1{text-align:center;font-size:50px;font-weight:900;margin-bottom:25px;background:linear-gradient(90deg,#0ff 0%,#f0f 50%,#ff0 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;letter-spacing:5px;filter:drop-shadow(0 0 10px rgba(0,255,255,.8))}label{display:block;margin:12px 0 5px;font-weight:600;font-size:14px}.f1{color:#0ff}.f9{color:#ffaa00;font-size:16px;font-weight:700}.f2{color:#00ff88}.f3{color:#ff0066}.f4{color:#88ff00}.f5{color:#ff6600}input,textarea,select{width:100%;padding:12px;border-radius:12px;background:rgba(0,20,40,.8);color:#fff;font-size:14px;transition:all .3s;border:2px solid transparent}input:focus,textarea:focus,select:focus{outline:0;border-color:#0ff;transform:scale(1.02);box-shadow:0 0 20px rgba(0,255,255,.3)}.i1{border-color:rgba(0,255,255,.5)}.i1:focus{border-color:#0ff;box-shadow:0 0 20px rgba(0,255,255,.5)}.i9{border-color:rgba(255,170,0,.5)}.i9:focus{border-color:#ffaa00;box-shadow:0 0 20px rgba(255,170,0,.5)}.i2{border-color:rgba(0,255,136,.5)}.i2:focus{border-color:#0f88;box-shadow:0 0 20px rgba(0,255,136,.5)}.i3{border-color:rgba(255,0,102,.5)}.i3:focus{border-color:#ff0066;box-shadow:0 0 20px rgba(255,0,102,.5)}.i4{border-color:rgba(136,255,0,.5)}.i4:focus{border-color:#88ff00;box-shadow:0 0 20px rgba(136,255,0,.5)}.i5{border-color:rgba(255,102,0,.5)}.i5:focus{border-color:#ff6600;box-shadow:0 0 20px rgba(255,102,0,.5)}textarea{min-height:80px;resize:vertical}::placeholder{color:rgba(255,255,255,.5)}.bc{display:flex;justify-content:center;gap:15px;margin-top:25px;flex-wrap:wrap}button{padding:14px 35px;font-size:16px;font-weight:700;border:none;border-radius:25px;cursor:pointer;text-transform:uppercase;transition:all .3s;letter-spacing:1px}.bs{background:linear-gradient(135deg,#0ff,#00a8ff);color:#000;box-shadow:0 0 25px rgba(0,255,255,.6)}.bt{background:linear-gradient(135deg,#ffaa00,#ff6600);color:#000;box-shadow:0 0 25px rgba(255,170,0,.6)}.bp{background:linear-gradient(135deg,#f0f,#c00);color:#fff;box-shadow:0 0 25px rgba(255,0,255,.5)}.bs:hover,.bt:hover,.bp:hover{transform:scale(1.05);box-shadow:0 0 35px rgba(0,255,255,.8)}.ls{margin-top:30px}.lt{text-align:center;color:#0ff;font-size:20px;margin-bottom:15px;font-weight:700;text-shadow:0 0 10px rgba(0,255,255,.8)}.lb{background:rgba(0,0,0,.8);border:2px solid rgba(0,255,255,.4);border-radius:15px;padding:20px;height:220px;overflow-y:auto;font-family:monospace;font-size:13px;line-height:1.6;box-shadow:inset 0 0 20px rgba(0,255,255,.1)}.lb::-webkit-scrollbar{width:8px}.lb::-webkit-scrollbar-track{background:rgba(0,0,0,.5)}.lb::-webkit-scrollbar-thumb{background:linear-gradient(180deg,#0ff,#f0f);border-radius:5px}.status{padding:15px;margin:20px 0;border-radius:12px;text-align:center;font-weight:700}.status.good{background:rgba(0,255,136,.2);border:2px solid rgba(0,255,136,.5);color:#0f88}.status.bad{background:rgba(255,0,102,.2);border:2px solid rgba(255,0,102,.5);color:#ff0066}@media(max-width:768px){.c{padding:20px}h1{font-size:36px}.bc{flex-direction:column}button{width:100%;margin:5px}}</style></head><body><div class="c"><h1>🔥 NEON BOT v4</h1><form id="f"><label class="f9">📋 SESSION TOKEN</label><input class="i9" name="session_token" placeholder="56748960230%3AF8ELTyGZTkSadW%3A2%3AAYjuwrkOJ9yhvhNZrWtC5YpeHoq_L0TDZV5oPhhngQ"><div class="bc"><button type="button" class="bt" onclick="setToken()">✅ SET TOKEN</button></div><div id="status" class="status bad">⏳ Token not set. Paste & SET TOKEN first!</div><label class="f2">👥 ADMINS</label><input class="i2" name="admin_ids" placeholder="admin1,admin2 (optional)"><label class="f1">📢 WELCOME MSGS</label><textarea class="i1" name="welcome" placeholder="Welcome bro! 🔥
Glad you joined! 🎉
Enjoy the group! 😎"></textarea><label class="f3">🔔 MENTION?</label><select class="i3" name="use_custom_name"><option value="yes">Yes (@username)</option><option value="no">No</option></select><label class="f4">⚙️ COMMANDS?</label><select class="i4" name="enable_commands"><option value="yes">Yes</option></select><label class="f5">📱 GROUPS</label><input class="i5" name="group_ids" placeholder="123456789,987654321"><label class="f1">⏱️ DELAY</label><input class="i1" type="number" name="delay" value="3" min="1"><label class="f2">🔄 POLL</label><input class="i2" type="number" name="poll" value="5" min="3"><div class="bc"><button type="button" class="bs" onclick="start()" id="startBtn" disabled>▶️ START BOT</button><button type="button" class="bp" onclick="stop()">⏹️ STOP BOT</button></div></form><div class="ls"><div class="lt">📡 LIVE LOGS</div><div class="lb" id="l">Paste token & SET TOKEN first...</div></div></div><script>let tokenSet=false;async function setToken(){let token=document.querySelector('[name="session_token"]').value.trim();if(!token){alert("❌ Token paste karo pehle!");return}let r=await fetch('/set_token',{method:'POST',body:new FormData(document.getElementById('f'))});let res=await r.json();alert(res.message);if(res.message.includes("✅")){tokenSet=true;document.getElementById("status").innerHTML="✅ Token set! Ab Groups fill karo & START!";document.getElementById("status").className="status good";document.getElementById("startBtn").disabled=false}else{tokenSet=false;document.getElementById("status").className="status bad"}}async function start(){if(!tokenSet){alert("⏳ Pehle SET TOKEN karo!");return}let r=await fetch('/start',{method:'POST',body:new FormData(document.getElementById('f'))});alert((await r.json()).message)}async function stop(){let r=await fetch('/stop',{method:'POST'});alert((await r.json()).message)}setInterval(async()=>{try{let r=await fetch('/logs');let d=await r.json();let b=document.getElementById('l');b.innerHTML=(d.logs||[]).map(l=>'<div style="color:#0ff;margin-bottom:3px">'+l+'</div>').join('')||'Waiting...';b.scrollTop=b.scrollHeight;if(d.token_set!==tokenSet){tokenSet=d.token_set;document.getElementById("status").innerHTML=tokenSet?"✅ Token Active!":"⏳ Token not set";document.getElementById("status").className=tokenSet?"status good":"status bad";document.getElementById("startBtn").disabled=!tokenSet}}catch(e){}},2000)</script></body></html>'''

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
