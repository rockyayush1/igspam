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
    lm = "[" + ts + "] " + msg
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
        log("💥 TOKEN LOGIN FAILED: " + str(e))
        return
    
    log("🤖 Bot started!")
    log("Admins: " + str(admin_ids))
    
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
                log("✅ Group " + gid[:8] + "... ready")
            except Exception as e:
                log("⚠️ Group error: " + str(e))
                km[gid] = set()
                lm[gid] = None
    
    global STATS
    if STATS["last_reset"] != datetime.now().date():
        STATS["today_welcomed"] = 0
        STATS["last_reset"] = datetime.now().date()
    
    while not STOP_EVENT.is_set():
        try:
            for gid_raw in gids.split(","):
                gid = gid_raw.strip()
                if STOP_EVENT.is_set() or not gid:
                    break
                try:
                    g = cl.direct_thread(gid)
                    
                    if BOT_CONFIG["spam_active"].get(gid, False):
                        tu = BOT_CONFIG["target_spam"].get(gid, {}).get("username")
                        sm = BOT_CONFIG["target_spam"].get(gid, {}).get("message")
                        if tu and sm:
                            cl.direct_send("@" + tu + " " + sm, thread_ids=[gid])
                            log("Spam to @" + tu)
                            time.sleep(2)
                    
                    if ecmd or BOT_CONFIG["auto_reply_active"]:
                        nm = []
                        if lm.get(gid):
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
                                cl.direct_send(BOT_CONFIG["auto_replies"][tl], thread_ids=[gid])
                                log("Auto-reply sent")
                            
                            if not ecmd:
                                continue
                                
                            if tl in ["/help", "!help"]:
                                cl.direct_send("COMMANDS: /autoreply /stopreply /addvideo /addaudio /video /audio /library /music /funny /masti /kick /spam /stopspam /rules /stats /count /ping /time /about /welcome", thread_ids=[gid])
                                log("Help sent")
                            elif tl in ["/stats", "!stats"]:
                                cl.direct_send("STATS - Total: " + str(STATS['total_welcomed']) + " Today: " + str(STATS['today_welcomed']), thread_ids=[gid])
                            elif tl in ["/count", "!count"]:
                                cl.direct_send("MEMBERS: " + str(len(g.users)), thread_ids=[gid])
                            elif tl in ["/welcome", "!welcome"]:
                                cl.direct_send("@" + sender.username + " Test!", thread_ids=[gid])
                            elif tl in ["/ping", "!ping"]:
                                cl.direct_send("Pong! Alive!", thread_ids=[gid])
                            elif tl in ["/time", "!time"]:
                                cl.direct_send("TIME: " + datetime.now().strftime("%I:%M %p"), thread_ids=[gid])
                            elif tl in ["/about", "!about"]:
                                cl.direct_send("Instagram Bot v3.0 - Full Featured", thread_ids=[gid])
                            elif tl.startswith("/autoreply "):
                                p = t.split(" ", 2)
                                if len(p) >= 3:
                                    BOT_CONFIG["auto_replies"][p[1].lower()] = p[2]
                                    BOT_CONFIG["auto_reply_active"] = True
                                    cl.direct_send("Auto-reply set: " + p[1] + " -> " + p[2], thread_ids=[gid])
                            elif tl in ["/stopreply", "!stopreply"]:
                                BOT_CONFIG["auto_reply_active"] = False
                                BOT_CONFIG["auto_replies"] = {}
                                cl.direct_send("Auto-reply stopped!", thread_ids=[gid])
                            elif ia and tl.startswith("/addvideo "):
                                p = t.split(" ", 3)
                                if len(p) >= 4:
                                    BOT_CONFIG["media_library"][p[1].lower()] = {"type": "video", "format": p[2].upper(), "link": p[3]}
                                    cl.direct_send("Video saved: " + p[1], thread_ids=[gid])
                            elif ia and tl.startswith("/addaudio "):
                                p = t.split(" ", 2)
                                if len(p) >= 3:
                                    BOT_CONFIG["media_library"][p[1].lower()] = {"type": "audio", "link": p[2]}
                                    cl.direct_send("Audio saved: " + p[1], thread_ids=[gid])
                            elif tl.startswith("/video "):
                                p = t.split(" ", 1)
                                if len(p) >= 2:
                                    n = p[1].lower()
                                    if n in BOT_CONFIG["media_library"] and BOT_CONFIG["media_library"][n]["type"] == "video":
                                        md = BOT_CONFIG["media_library"][n]
                                        cl.direct_send("VIDEO: " + p[1].upper() + " | Type: " + md.get("format", "VIDEO") + " | Watch: " + md["link"], thread_ids=[gid])
                                    else:
                                        cl.direct_send("Video not found!", thread_ids=[gid])
                            elif tl.startswith("/audio "):
                                p = t.split(" ", 1)
                                if len(p) >= 2:
                                    n = p[1].lower()
                                    if n in BOT_CONFIG["media_library"] and BOT_CONFIG["media_library"][n]["type"] == "audio":
                                        md = BOT_CONFIG["media_library"][n]
                                        cl.direct_send("AUDIO: " + p[1].upper() + " | Listen: " + md["link"], thread_ids=[gid])
                                    else:
                                        cl.direct_send("Audio not found!", thread_ids=[gid])
                            elif tl in ["/library", "!library"]:
                                if BOT_CONFIG["media_library"]:
                                    vids = [k for k, v in BOT_CONFIG["media_library"].items() if v["type"] == "video"]
                                    auds = [k for k, v in BOT_CONFIG["media_library"].items() if v["type"] == "audio"]
                                    msg = "LIBRARY | Videos: " + ", ".join(vids) if vids else "" + " | Audios: " + ", ".join(auds) if auds else ""
                                    cl.direct_send(msg, thread_ids=[gid])
                                else:
                                    cl.direct_send("Library empty!", thread_ids=[gid])
                            elif tl in ["/music", "!music"]:
                                cl.direct_send("Music! " + " ".join(random.choices(MUSIC_EMOJIS, k=5)), thread_ids=[gid])
                            elif tl in ["/funny", "!funny"]:
                                cl.direct_send(random.choice(FUNNY), thread_ids=[gid])
                            elif tl in ["/masti", "!masti"]:
                                cl.direct_send(random.choice(MASTI), thread_ids=[gid])
                            elif ia and tl.startswith("/kick "):
                                p = t.split(" ", 1)
                                if len(p) >= 2:
                                    ku = p[1].replace("@", "")
                                    tg = next((u for u in g.users if u.username.lower() == ku.lower()), None)
                                    if tg:
                                        try:
                                            cl.direct_thread_remove_user(gid, tg.pk)
                                            cl.direct_send("Kicked @" + tg.username, thread_ids=[gid])
                                        except:
                                            cl.direct_send("Cannot kick", thread_ids=[gid])
                            elif tl in ["/rules", "!rules"]:
                                cl.direct_send("RULES: 1.Respect 2.No spam 3.Follow guidelines 4.Have fun!", thread_ids=[gid])
                            elif ia and tl.startswith("/spam "):
                                p = t.split(" ", 2)
                                if len(p) >= 3:
                                    BOT_CONFIG["target_spam"][gid] = {"username": p[1].replace("@", ""), "message": p[2]}
                                    BOT_CONFIG["spam_active"][gid] = True
                                    cl.direct_send("Spam started", thread_ids=[gid])
                            elif ia and tl in ["/stopspam", "!stopspam"]:
                                BOT_CONFIG["spam_active"][gid] = False
                                cl.direct_send("Spam stopped!", thread_ids=[gid])
                        
                        if g.messages:
                            lm[gid] = g.messages[0].id
                    
                    cm = {u.pk for u in g.users}
                    nwm = cm - km[gid]
                    if nwm:
                        for u in g.users:
                            if u.pk in nwm and u.username != cl.user_id:
                                if STOP_EVENT.is_set():
                                    break
                                log("NEW: @" + u.username)
                                for ms in wm:
                                    if STOP_EVENT.is_set():
                                        break
                                    fm = ("@" + u.username + " " + ms) if ucn else ms
                                    cl.direct_send(fm, thread_ids=[gid])
                                    STATS["total_welcomed"] += 1
                                    STATS["today_welcomed"] += 1
                                    log("Welcomed @" + u.username)
                                    time.sleep(dly)
                                km[gid] = cm
                                break
                    km[gid] = cm
                except:
                    pass
            time.sleep(pol)
        except:
            pass
    log("🛑 Bot stopped")

@app.route("/")
def index():
    return render_template_string(PAGE_HTML)

@app.route("/start", methods=["POST"])
def start_bot():
    global BOT_THREAD, STOP_EVENT
    if BOT_THREAD and BOT_THREAD.is_alive():
        return jsonify({"message": "Already running!"})
    
    token = request.form.get("token", "")
    wl = [m.strip() for m in request.form.get("welcome", "").splitlines() if m.strip()]
    gids = [g.strip() for g in request.form.get("group_ids", "").split(",") if g.strip()]
    adm = [a.strip() for a in request.form.get("admin_ids", "").split(",") if a.strip()]
    
    if not token or not gids or not wl:
        return jsonify({"message": "Token, Groups & Welcome required!"})
    
    STOP_EVENT.clear()
    BOT_THREAD = threading.Thread(target=run_bot, args=(token, wl, ",".join(gids), int(request.form.get("delay", 3)), int(request.form.get("poll", 5)), request.form.get("use_custom_name") == "yes", request.form.get("enable_commands") == "yes", ",".join(adm)), daemon=True)
    BOT_THREAD.start()
    return jsonify({"message": "Started with TOKEN!"})

@app.route("/stop", methods=["POST"])
def stop_bot():
    STOP_EVENT.set()
    return jsonify({"message": "Stopped!"})

@app.route("/logs")
def get_logs():
    return jsonify({"logs": LOGS[-200:]})

# 🔥 COMPLETE NEON HTML (FULL WORKING!)
PAGE_HTML = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>🚀 NEON BOT v3.0</title>
    <style>
        *{margin:0;padding:0;box-sizing:border-box}
        body{font-family:'Segoe UI',Tahoma,Geneva,Verdana,sans-serif;background:linear-gradient(135deg,#0c0c0c 0%,#1a1a2e 50%,#16213e 100%);min-height:100vh;color:#fff;position:relative;overflow-x:hidden;padding:20px}
        body::before{content:'';position:fixed;top:0;left:0;width:100%;height:100%;background:radial-gradient(circle at 20% 80%,rgba(120,119,198,0.3) 0%,transparent 50%),radial-gradient(circle at 80% 20%,rgba(255,119,198,0.3) 0%,transparent 50%),radial-gradient(circle at 40% 40%,rgba(120,219,255,0.3) 0%,transparent 50%);z-index:-1;animation:neonPulse 4s ease-in-out infinite alternate}
        @keyframes neonPulse{0%{opacity:0.8}100%{opacity:1}}
        .container{max-width:800px;margin:0 auto;background:rgba(0,0,0,0.85);border:2px solid #00ffff;border-radius:20px;padding:30px;box-shadow:0 20px 60px rgba(0,255,255,0.3);backdrop-filter:blur(10px)}
        h1{text-align:center;font-size:2.5em;margin-bottom:10px;background:linear-gradient(45deg,#00ffff,#ff00ff,#ffff00,#00ff00);background-size:400% 400%;-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;animation:gradientShift 3s ease infinite}
        @keyframes gradientShift{0%{background-position:0% 50%}50%{background-position:100% 50%}100%{background-position:0% 50%}}
        .status{display:flex;align-items:center;gap:15px;padding:20px;background:rgba(0,255,255,0.1);border-radius:15px;margin:20px 0;border-left:4px solid #00ffff}
        .status.online{color:#00ff88}.status.offline{color:#ff4444}
        .btn{display:block;width:100%;padding:15px;margin:10px 0;font-size:1.1em;font-weight:bold;border:none;border-radius:12px;cursor:pointer;transition:all 0.3s ease;text-transform:uppercase;letter-spacing:1px}
        .btn-primary{background:linear-gradient(45deg,#00ffff,#0099ff);color:#000;box-shadow:0 5px 20px rgba(0,255,255,0.4)}
        .btn-success{background:linear-gradient(45deg,#00ff88,#00cc66);color:#000;box-shadow:0 5px 20px rgba(0,255,136,0.4)}
        .btn-danger{background:linear-gradient(45deg,#ff4444,#cc0000);color:#fff;box-shadow:0 5px 20px rgba(255,68,68,0.4)}
        .btn:hover{transform:translateY(-3px);box-shadow:0 10px 30px rgba(0,255,255,0.6)}
        .form-group{margin:20px 0}
        .form-group label{display:block;margin-bottom:8px;font-weight:bold;color:#00ffff}
        .form-control{width:100%;padding:15px;border:2px solid rgba(0,255,255,0.3);border-radius:10px;background:rgba(255,255,255,0.05);color:#fff;font-size:1em;transition:border-color 0.3s ease}
        .form-control:focus{outline:none;border-color:#00ffff;box-shadow:0 0 20px rgba(0,255,255,0.5)}
        .form-control::placeholder{color:rgba(255,255,255,0.5)}
        textarea.form-control{height:120px;resize:vertical}
        .checkbox-group{display:flex;align-items:center;gap:10px;margin:10px 0}
        .checkbox-group input{width:auto}
        .logs{background:rgba(0,0,0,0.5);border:1px solid #00ffff;border-radius:10px;height:300px;overflow-y:auto;padding:15px;font-family:monospace;font-size:0.9em}
        .log-entry{margin:5px 0;padding:8px;border-radius:5px;background:rgba(0,255,255,0.05)}
        .log-success{color:#00ff88}.log-error{color:#ff4444}.log-info{color:#00ffff}
        #logs-container{max-height:400px;overflow-y:auto}
        @media (max-width:600px){.container{padding:20px}h1{font-size:2em}}
    </style>
</head>
<body>
    <div class="container">
        <h1>🚀 NEON BOT v3.0</h1>
        <div class="status" id="status">
            <div id="status-icon" style="width:20px;height:20px;border-radius:50%;background:#ff4444"></div>
            <span id="status-text">🛑 Bot Offline</span>
        </div>
        
        <form id="bot-form">
            <div class="form-group">
                <label>🔑 Session Token <span style="color:#ffaa00;font-size:0.9em">(Instagram Session ID)</span></label>
                <input type="text" class="form-control" name="token" placeholder="AABCxyz123..." required>
            </div>
            
            <div class="form-group">
                <label>📝 Welcome Messages <span style="color:#ffaa00;font-size:0.9em">(Multiple lines = random)</span></label>
                <textarea class="form-control" name="welcome" placeholder="Welcome bro! 🔥&#10;New member detected! 👋&#10;Namaste ji! 🙏" required></textarea>
            </div>
            
            <div class="form-group">
                <label>👥 Group IDs <span style="color:#ffaa00;font-size:0.9em">(Comma separated)</span></label>
                <input type="text" class="form-control" name="group_ids" placeholder="1234567890,0987654321" required>
            </div>
            
            <div class="form-group">
                <label>👑 Admin Usernames <span style="color:#ffaa00;font-size:0.9em">(Comma separated, optional)</span></label>
                <input type="text" class="form-control" name="admin_ids" placeholder="username1,username2">
            </div>
            
            <div class="form-group">
                <label>⏱️ Delay (seconds) <span style="color:#ffaa00;font-size:0.9em">(Between welcomes)</span></label>
                <input type="number" class="form-control" name="delay" value="3" min="1" max="10">
            </div>
            
            <div class="form-group">
                <label>🔄 Poll Interval (seconds)</label>
                <input type="number" class="form-control" name="poll" value="5" min="1" max="30">
            </div>
            
            <div class="checkbox-group">
                <input type="checkbox" id="use_custom_name" name="use_custom_name">
                <label for="use_custom_name" style="font-weight:normal;margin:0">✅ Mention @username in welcomes</label>
            </div>
            
            <div class="checkbox-group">
                <input type="checkbox" id="enable_commands" name="enable_commands" checked>
                <label for="enable_commands" style="font-weight:normal;margin:0">⚙️ Enable Commands (/help, /stats etc)</label>
  
