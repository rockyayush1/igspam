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
BOT_CONFIG = {
    "auto_replies": {}, 
    "auto_reply_active": False, 
    "target_spam": {}, 
    "spam_active": {},
    "media_library": {}
}

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    lm = "[" + ts + "] " + msg
    LOGS.append(lm)
    print(lm)

MUSIC_EMOJIS = ["🎵", "🎶", "🎸", "🎹", "🎤", "🎧", "🎺", "🎷"]
FUNNY = ["Hahaha! 😂", "LOL! Bahut funny! 🤣", "Mast joke tha! 😆", "Dimag ka dahi! 🤪", "Comedy king! 👑😂"]
MASTI = ["Party karte hain! 🎉", "Masti time! 🥳", "Dhamaal! 💃", "Full mode ON! 🔥", "Enjoy karo! 🎊"]

def run_bot(un, pw, wm, gids, dly, pol, ucn, ecmd, admin_ids):
    cl = Client()
    try:
        if os.path.exists(SESSION_FILE):
            cl.load_settings(SESSION_FILE)
            cl.login(un, pw)
            log("Session loaded")
        else:
            cl.login(un, pw)
            cl.dump_settings(SESSION_FILE)
            log("Session saved")
    except Exception as e:
        log("Login failed: " + str(e))
        return
    log("Bot started - All features active!")
    log("Admin IDs: " + str(admin_ids))
    km = {}
    lm = {}
    for gid in gids:
        try:
            g = cl.direct_thread(gid)
            km[gid] = {u.pk for u in g.users}
            lm[gid] = g.messages[0].id if g.messages else None
            BOT_CONFIG["spam_active"][gid] = False
            log("Group " + gid + " ready with " + str(len(km[gid])) + " members")
        except Exception as e:
            log("Error: " + str(e))
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
                    if BOT_CONFIG["spam_active"].get(gid, False):
                        tu = BOT_CONFIG["target_spam"].get(gid, {}).get("username")
                        sm = BOT_CONFIG["target_spam"].get(gid, {}).get("message")
                        if tu and sm:
                            cl.direct_send("@" + tu + " " + sm, thread_ids=[gid])
                            log("Spam sent to @" + tu)
                            time.sleep(2)
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
                            if BOT_CONFIG["auto_reply_active"] and tl in BOT_CONFIG["auto_replies"]:
                                rp = BOT_CONFIG["auto_replies"][tl]
                                cl.direct_send(rp, thread_ids=[gid])
                                log("Auto-reply: " + tl + " -> " + rp)
                            if not ecmd:
                                continue
                            if tl in ["/help", "!help"]:
                                h = "ALL COMMANDS:

AUTO-REPLY:
/autoreply TRIGGER RESPONSE
/stopreply

MEDIA:
/addvideo NAME TYPE LINK
/addaudio NAME LINK
/video NAME
/audio NAME
/library

FUN:
/funny
/masti
/music

ADMIN:
/kick @user
/spam @user MSG
/stopspam
/rules

INFO:
/stats
/count
/ping
/time
/about
/welcome"
                                cl.direct_send(h, thread_ids=[gid])
                                log("Help sent")
                            elif tl in ["/stats", "!stats"]:
                                cl.direct_send("STATS - Total: " + str(STATS['total_welcomed']) + " | Today: " + str(STATS['today_welcomed']), thread_ids=[gid])
                                log("Stats sent")
                            elif tl in ["/count", "!count"]:
                                cl.direct_send("MEMBERS - Total: " + str(len(g.users)) + " members", thread_ids=[gid])
                                log("Count sent")
                            elif tl in ["/welcome", "!welcome"]:
                                cl.direct_send("@" + sender.username + " Test welcome!", thread_ids=[gid])
                                log("Test welcome")
                            elif tl in ["/ping", "!ping"]:
                                cl.direct_send("Pong! Bot is alive!", thread_ids=[gid])
                                log("Ping sent")
                            elif tl in ["/time", "!time"]:
                                ct = datetime.now().strftime("%I:%M %p, %d %b %Y")
                                cl.direct_send("TIME: " + ct, thread_ids=[gid])
                                log("Time sent")
                            elif tl in ["/about", "!about"]:
                                cl.direct_send("Instagram Bot v3.0 - Full Featured Auto-Welcome Bot with Media Library", thread_ids=[gid])
                                log("About sent")
                            elif tl.startswith("/autoreply ") or tl.startswith("!autoreply "):
                                p = t.split(" ", 2)
                                if len(p) >= 3:
                                    tr = p[1].lower()
                                    rs = p[2]
                                    BOT_CONFIG["auto_replies"][tr] = rs
                                    BOT_CONFIG["auto_reply_active"] = True
                                    cl.direct_send("Auto-reply set! " + tr + " -> " + rs, thread_ids=[gid])
                                    log("Auto-reply: " + tr)
                                else:
                                    cl.direct_send("Usage: /autoreply TRIGGER RESPONSE", thread_ids=[gid])
                            elif tl in ["/stopreply", "!stopreply"]:
                                BOT_CONFIG["auto_reply_active"] = False
                                BOT_CONFIG["auto_replies"] = {}
                                cl.direct_send("Auto-reply stopped!", thread_ids=[gid])
                                log("Auto-reply stopped")
                            elif ia and (tl.startswith("/addvideo ") or tl.startswith("!addvideo ")):
                                p = t.split(" ", 3)
                                if len(p) >= 4:
                                    n = p[1].lower()
                                    tp = p[2].upper()
                                    lk = p[3]
                                    BOT_CONFIG["media_library"][n] = {"type": "video", "format": tp, "link": lk}
                                    cl.direct_send("Video saved!
Name: " + n + "
Type: " + tp, thread_ids=[gid])
                                    log("Video: " + n)
                                else:
                                    cl.direct_send("Usage: /addvideo NAME TYPE LINK", thread_ids=[gid])
                            elif ia and (tl.startswith("/addaudio ") or tl.startswith("!addaudio ")):
                                p = t.split(" ", 2)
                                if len(p) >= 3:
                                    n = p[1].lower()
                                    lk = p[2]
                                    BOT_CONFIG["media_library"][n] = {"type": "audio", "link": lk}
                                    cl.direct_send("Audio saved!
Name: " + n, thread_ids=[gid])
                                    log("Audio: " + n)
                                else:
                                    cl.direct_send("Usage: /addaudio NAME LINK", thread_ids=[gid])
                            elif tl.startswith("/video ") or tl.startswith("!video "):
                                p = t.split(" ", 1)
                                if len(p) >= 2:
                                    n = p[1].lower()
                                    if n in BOT_CONFIG["media_library"] and BOT_CONFIG["media_library"][n]["type"] == "video":
                                        md = BOT_CONFIG["media_library"][n]
                                        msg = "🎬 VIDEO: " + p[1].upper() + "
━━━━━━━━━━━━━━━
📺 Type: " + md.get("format", "VIDEO") + "
🔗 Watch:
" + md["link"] + "
━━━━━━━━━━━━━━━"
                                        cl.direct_send(msg, thread_ids=[gid])
                                        log("Video sent: " + n)
                                    else:
                                        cl.direct_send("Video not found! Use /library", thread_ids=[gid])
                            elif tl.startswith("/audio ") or tl.startswith("!audio "):
                                p = t.split(" ", 1)
                                if len(p) >= 2:
                                    n = p[1].lower()
                                    if n in BOT_CONFIG["media_library"] and BOT_CONFIG["media_library"][n]["type"] == "audio":
                                        md = BOT_CONFIG["media_library"][n]
                                        msg = "🎵 AUDIO: " + p[1].upper() + "
━━━━━━━━━━━━━━━
🎧 Listen:
" + md["link"] + "
━━━━━━━━━━━━━━━"
                                        cl.direct_send(msg, thread_ids=[gid])
                                        log("Audio sent: " + n)
                                    else:
                                        cl.direct_send("Audio not found! Use /library", thread_ids=[gid])
                            elif tl in ["/library", "!library"]:
                                if BOT_CONFIG["media_library"]:
                                    vids = [k for k, v in BOT_CONFIG["media_library"].items() if v["type"] == "video"]
                                    auds = [k for k, v in BOT_CONFIG["media_library"].items() if v["type"] == "audio"]
                                    msg = "MEDIA LIBRARY

"
                                    if vids:
                                        msg += "VIDEOS:
" + "
".join(["- " + v for v in vids]) + "

"
                                    if auds:
                                        msg += "AUDIOS:
" + "
".join(["- " + a for a in auds])
                                    cl.direct_send(msg, thread_ids=[gid])
                                else:
                                    cl.direct_send("Library empty!", thread_ids=[gid])
                            elif tl in ["/music", "!music"]:
                                em = " ".join(random.choices(MUSIC_EMOJIS, k=5))
                                cl.direct_send("Playing music! " + em, thread_ids=[gid])
                                log("Music emojis")
                            elif tl in ["/funny", "!funny"]:
                                cl.direct_send(random.choice(FUNNY), thread_ids=[gid])
                                log("Funny sent")
                            elif tl in ["/masti", "!masti"]:
                                cl.direct_send(random.choice(MASTI), thread_ids=[gid])
                                log("Masti sent")
                            elif ia and (tl.startswith("/kick ") or tl.startswith("!kick ")):
                                p = t.split(" ", 1)
                                if len(p) >= 2:
                                    ku = p[1].replace("@", "")
                                    tg = next((u for u in g.users if u.username.lower() == ku.lower()), None)
                                    if tg:
                                        try:
                                            cl.direct_thread_remove_user(gid, tg.pk)
                                            cl.direct_send("Kicked @" + tg.username, thread_ids=[gid])
                                            log("Kicked: @" + tg.username)
                                        except:
                                            cl.direct_send("Cannot kick", thread_ids=[gid])
                            elif tl in ["/rules", "!rules"]:
                                ru = "GROUP RULES:
1. Be respectful
2. No spam
3. Follow guidelines
4. Have fun!"
                                cl.direct_send(ru, thread_ids=[gid])
                                log("Rules sent")
                            elif ia and (tl.startswith("/spam ") or tl.startswith("!spam ")):
                                p = t.split(" ", 2)
                                if len(p) >= 3:
                                    tu = p[1].replace("@", "")
                                    sm = p[2]
                                    BOT_CONFIG["target_spam"][gid] = {"username": tu, "message": sm}
                                    BOT_CONFIG["spam_active"][gid] = True
                                    cl.direct_send("Spam started to @" + tu, thread_ids=[gid])
                                    log("Spam: @" + tu)
                            elif ia and (tl in ["/stopspam", "!stopspam"]):
                                BOT_CONFIG["spam_active"][gid] = False
                                cl.direct_send("Spam stopped!", thread_ids=[gid])
                                log("Spam stopped")
                        if g.messages:
                            lm[gid] = g.messages[0].id
                    cm = {u.pk for u in g.users}
                    nwm = cm - km[gid]
                    if nwm:
                        for u in g.users:
                            if u.pk in nwm and u.username != un:
                                if STOP_EVENT.is_set():
                                    break
                                log("NEW MEMBER: @" + u.username)
                                for ms in wm:
                                    if STOP_EVENT.is_set():
                                        break
                                    fm = ("@" + u.username + " " + ms) if ucn else ms
                                    cl.direct_send(fm, thread_ids=[gid])
                                    STATS["total_welcomed"] += 1
                                    STATS["today_welcomed"] += 1
                                    log("Welcomed @" + u.username)
                                    for _ in range(dly):
                                        if STOP_EVENT.is_set():
                                            break
                                        time.sleep(1)
                                    if STOP_EVENT.is_set():
                                        break
                                km[gid].add(u.pk)
                    km[gid] = cm
                except Exception as e:
                    log("Error: " + str(e))
            if STOP_EVENT.is_set():
                break
            for _ in range(pol):
                if STOP_EVENT.is_set():
                    break
                time.sleep(1)
        except Exception as e:
            log("Loop error: " + str(e))
    log("Bot stopped")

@app.route("/")
def index():
    return render_template_string(PAGE_HTML)

@app.route("/start", methods=["POST"])
def start_bot():
    global BOT_THREAD, STOP_EVENT
    if BOT_THREAD and BOT_THREAD.is_alive():
        return jsonify({"message": "Already running"})
    un = request.form.get("username")
    pw = request.form.get("password")
    wl = [m.strip() for m in request.form.get("welcome", "").splitlines() if m.strip()]
    gids = [g.strip() for g in request.form.get("group_ids", "").split(",") if g.strip()]
    adm = [a.strip() for a in request.form.get("admin_ids", "").split(",") if a.strip()]
    if not un or not pw or not gids or not wl:
        return jsonify({"message": "Fill all fields"})
    STOP_EVENT.clear()
    BOT_THREAD = threading.Thread(target=run_bot, args=(un, pw, wl, gids, int(request.form.get("delay", 3)), int(request.form.get("poll", 5)), request.form.get("use_custom_name") == "yes", request.form.get("enable_commands") == "yes", adm), daemon=True)
    BOT_THREAD.start()
    log("Bot started by user")
    return jsonify({"message": "Bot started!"})

@app.route("/stop", methods=["POST"])
def stop_bot():
    global BOT_THREAD
    STOP_EVENT.set()
    log("Stopping...")
    if BOT_THREAD:
        BOT_THREAD.join(timeout=5)
    log("Stopped")
    return jsonify({"message": "Bot stopped!"})

@app.route("/logs")
def get_logs():
    return jsonify({"logs": LOGS[-200:]})

@app.route("/stats")
def get_stats():
    return jsonify(STATS)

PAGE_HTML = """<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>🌟 NEON BOT CONTROL</title><style>@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&display=swap');*{margin:0;padding:0;box-sizing:border-box}body{font-family:'Orbitron',sans-serif;min-height:100vh;background:#000;background-image:radial-gradient(circle at 20% 50%,rgba(120,0,255,.3) 0%,transparent 50%),radial-gradient(circle at 80% 80%,rgba(255,0,150,.3) 0%,transparent 50%),radial-gradient(circle at 40% 20%,rgba(0,255,255,.3) 0%,transparent 50%);background-size:200% 200%;animation:gradientShift 15s ease infinite;color:#fff;padding:20px;overflow-x:hidden}@keyframes gradientShift{0%,100%{background-position:0% 50%}50%{background-position:100% 50%}}@keyframes neonPulse{0%,100%{text-shadow:0 0 10px #0ff,0 0 20px #0ff,0 0 30px #0ff,0 0 40px #0ff}50%{text-shadow:0 0 5px #0ff,0 0 10px #0ff,0 0 15px #0ff,0 0 20px #0ff}}@keyframes float{0%,100%{transform:translateY(0)}50%{transform:translateY(-10px)}}@keyframes glow{0%,100%{box-shadow:0 0 5px #0ff,0 0 10px #0ff,0 0 15px #0ff,0 0 20px #0ff,inset 0 0 10px rgba(0,255,255,.2)}50%{box-shadow:0 0 10px #0ff,0 0 20px #0ff,0 0 30px #0ff,0 0 40px #0ff,inset 0 0 15px rgba(0,255,255,.3)}}.container{max-width:1100px;margin:0 auto;background:rgba(10,10,30,.85);border-radius:30px;padding:40px;box-shadow:0 0 50px rgba(0,255,255,.4),0 0 100px rgba(255,0,255,.3);border:2px solid rgba(0,255,255,.5);backdrop-filter:blur(10px);animation:float 6s ease-in-out infinite}h1{text-align:center;font-size:48px;font-weight:900;margin-bottom:30px;background:linear-gradient(90deg,#0ff,#f0f,#0ff);-webkit-background-clip:text;-webkit-text-fill-color:transparent;animation:neonPulse 2s ease-in-out infinite;letter-spacing:3px;text-transform:uppercase}.feature-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px;margin-bottom:30px}.feature-box{background:linear-gradient(135deg,rgba(0,255,255,.1),rgba(255,0,255,.1));border:2px solid rgba(0,255,255,.4);border-radius:20px;padding:20px;animation:glow 3s ease-in-out infinite;transition:all .3s}.feature-box:hover{transform:translateY(-5px) scale(1.02);border-color:#0ff}.feature-title{color:#0ff;font-size:18px;font-weight:700;margin-bottom:15px;text-transform:uppercase;letter-spacing:2px}.feature-list{color:#fff;font-size:13px;line-height:1.8;list-style:none}.feature-list li:before{content:"▸ ";color:#f0f}label{display:block;margin:15px 0 8px;color:#0ff;font-weight:700;font-size:14px;text-transform:uppercase;letter-spacing:1px}.sub{font-size:11px;color:#aaa;margin-top:5px;font-weight:400;letter-spacing:0}input,textarea,select{width:100%;padding:14px;border:2px solid rgba(0,255,255,.4);border-radius:15px;background:rgba(0,20,40,.6);color:#fff;font-size:14px;font-family:'Orbitron',sans-serif;transition:all .3s;backdrop-filter:blur(5px)}input:focus,textarea:focus,select:focus{outline:0;border-color:#0ff;box-shadow:0 0 15px rgba(0,255,255,.5);background:rgba(0,30,60,.7)}textarea{min-height:90px;resize:vertical}::placeholder{color:rgba(255,255,255,.4)}.button-container{display:flex;justify-content:center;gap:20px;margin-top:30px;flex-wrap:wrap}button{padding:16px 40px;font-size:18px;font-weight:700;border:none;border-radius:50px;cursor:pointer;font-family:'Orbitron',sans-serif;text-transform:uppercase;letter-spacing:2px;transition:all .3s;position:relative;overflow:hidden}.btn-start{background:linear-gradient(135deg,#0ff,#0af);color:#000;box-shadow:0 0 20px rgba(0,255,255,.5)}.btn-start:hover{transform:scale(1.05);box-shadow:0 0 30px rgba(0,255,255,.8)}.btn-stop{background:linear-gradient(135deg,#f0f,#f06);color:#fff;box-shadow:0 0 20px rgba(255,0,255,.5)}.btn-stop:hover{transform:scale(1.05);box-shadow:0 0 30px rgba(255,0,255,.8)}button:active{transform:scale(.98)}.logs-section{margin-top:40px}.logs-title{text-align:center;color:#0ff;font-size:24px;margin-bottom:20px;text-transform:uppercase;letter-spacing:3px}.logs-box{background:rgba(0,0,0,.7);border:2px solid rgba(0,255,255,.4);border-radius:20px;padding:20px;height:280px;overflow-y:auto;font-family:'Courier New',monospace;font-size:13px;line-height:1.8;box-shadow:inset 0 0 20px rgba(0,255,255,.2);backdrop-filter:blur(5px)}.logs-box::-webkit-scrollbar{width:10px}.logs-box::-webkit-scrollbar-track{background:rgba(0,0,0,.5);border-radius:10px}.logs-box::-webkit-scrollbar-thumb{background:linear-gradient(180deg,#0ff,#f0f);border-radius:10px}.log-entry{color:#0ff;margin-bottom:5px;animation:fadeIn .5s}@keyframes fadeIn{from{opacity:0;transform:translateX(-10px)}to{opacity:1;transform:translateX(0)}}@media(max-width:768px){.container{padding:25px}h1{font-size:32px}.feature-grid{grid-template-columns:1fr}.button-container{flex-direction:column}button{width:100%}}</style></head><body><div class="container"><h1>🌟 NEON BOT CONTROL 🌟</h1><div class="feature-grid"><div class="feature-box"><div class="feature-title">⚡ AUTO FEATURES</div><ul class="feature-list"><li>24x7 Auto-Welcome New Members</li><li>Auto-Reply System (Always Active)</li><li>Real-time Member Detection</li><li>Smart Statistics Tracking</li></ul></div><div class="feature-box"><div class="feature-title">🎬 MEDIA LIBRARY</div><ul class="feature-list"><li>YouTube Video Management</li><li>Audio File Library</li><li>Quick Media Access Commands</li><li>Admin-Controlled Setup</li></ul></div><div class="feature-box"><div class="feature-title">🎮 FUN & ADMIN</div><ul class="feature-list"><li>Funny & Masti Messages</li><li>Music Emoji Player</li><li>Member Kick Control</li><li>Target Spam System</li><li>Group Rules Display</li></ul></div></div><form id="botForm"><label>🤖 Bot Username</label><input name="username" placeholder="Enter Instagram username"><label>🔐 Bot Password</label><input type="password" name="password" placeholder="Enter password"><label>👑 Admin Usernames<div class="sub">Comma separated: admin1,admin2,admin3</div></label><input name="admin_ids" placeholder="admin1,admin2"><label>💬 Welcome Messages<div class="sub">One message per line - sent to all new members</div></label><textarea name="welcome" placeholder="Welcome to our awesome group!
We're glad you joined us!
Feel free to introduce yourself!"></textarea><label>📝 Mention Username in Welcome?</label><select name="use_custom_name"><option value="yes">✅ Yes - Add @username</option><option value="no">❌ No - Plain message</option></select><label>⚙️ Enable Bot Commands?</label><select name="enable_commands"><option value="yes">✅ Yes - All commands active</option><option value="no">❌ No - Only auto-welcome</option></select><label>👥 Group Chat IDs<div class="sub">Comma separated: 123456789,987654321</div></label><input name="group_ids" placeholder="123456789,987654321"><label>⏱️ Delay Between Messages (seconds)</label><input type="number" name="delay" value="3" min="1" max="10"><label>🔄 Check Interval (seconds)<div class="sub">How often to check for new members</div></label><input type="number" name="poll" value="5" min="3" max="30"><div class="button-container"><button type="button" class="btn-start" onclick="startBot()">▶️ START BOT</button><button type="button" class="btn-stop" onclick="stopBot()">⏹️ STOP BOT</button></div></form><div class="logs-section"><div class="logs-title">📋 LIVE ACTIVITY LOGS</div><div class="logs-box" id="logsContainer">🔌 Waiting for bot to start...</div></div></div><script>async function startBot(){const form=document.getElementById('botForm');const data=new FormData(form);try{const response=await fetch('/start',{method:'POST',body:data});const result=await response.json();alert('✅ '+result.message)}catch(error){alert('❌ Error: '+error.message)}}async function stopBot(){try{const response=await fetch('/stop',{method:'POST'});const result=await response.json();alert('🛑 '+result.message)}catch(error){alert('❌ Error: '+error.message)}}async function updateLogs(){try{const response=await fetch('/logs');const data=await response.json();const logsBox=document.getElementById('logsContainer');if(data.logs&&data.logs.length>0){logsBox.innerHTML=data.logs.map(log=>'<div class="log-entry">'+log+'</div>').join('');logsBox.scrollTop=logsBox.scrollHeight}else{logsBox.innerHTML='🔌 No activity yet. Start the bot to see logs...'}}catch(error){console.error('Log update error:',error)}}setInterval(updateLogs,2000);updateLogs()</script></body></html>"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
