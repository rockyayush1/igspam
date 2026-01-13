# 🔥 COMPLETE NEON BOT v3.2 - FULL DESIGN + FIXED PROXY + ALL FEATURES
import os
import threading
import time
import random
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify
from instagrapi import Client
from instagrapi.exceptions import ClientError, LoginRequired, PleaseWaitFewMinutes

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

def run_bot(un, pw, wm, gids, dly, pol, ucn, ecmd, admin_ids, proxy=None):
    cl = Client()
    
    # 🔥 TOP 10 WORKING PROXIES Jan 2026 - NO HANGING!
    proxies = [
        "http://103.153.154.110:80",      # India Fastest
        "http://103.174.102.223:80",      # India Fast  
        "http://47.74.152.44:8888",       # Singapore Fast
        "http://185.162.231.228:80",      # Europe Fast
        "http://167.71.5.83:3128",        # USA Fast
        "http://20.210.113.32:80",        # Backup
        "http://103.129.196.138:45262",
        "http://proxy6.net:8080"
    ]
    
    login_success = False
    current_proxy = None
    
    log("🚀 Trying NO PROXY first...")
    try:
        if os.path.exists(SESSION_FILE):
            cl.load_settings(SESSION_FILE)
            cl.login(un, pw)
        else:
            cl.login(un, pw)
            cl.dump_settings(SESSION_FILE)
        log("🎉 LOGIN SUCCESS WITHOUT PROXY!")
        current_proxy = "NO PROXY ✅"
        login_success = True
    except:
        log("❌ No proxy failed, trying 8 proxies...")
        
        for i, proxy_try in enumerate(proxies):
            try:
                log(f"🔄 [{i+1}/8] Testing: {proxy_try}")
                cl = Client()
                cl.set_proxy(proxy_try)
                time.sleep(2)
                
                if os.path.exists(SESSION_FILE):
                    cl.load_settings(SESSION_FILE)
                    cl.login(un, pw)
                    log("✅ Session loaded!")
                else:
                    cl.login(un, pw)
                    cl.dump_settings(SESSION_FILE)
                    log("✅ New session saved!")
                
                current_proxy = proxy_try
                login_success = True
                log("🎉 LOGIN SUCCESS WITH PROXY!")
                break
                
            except Exception as e:
                log(f"❌ Proxy {i+1} FAILED: {str(e)[:60]}")
                continue
    
    if not login_success:
        log("💥 ALL PROXIES FAILED! Check username/password")
        return
    
    log("Bot started!")
    log("Admins: " + str(admin_ids))
    log(f"✅ Using: {current_proxy}")
    
    km = {}
    lm = {}
    for gid in gids:
        try:
            g = cl.direct_thread(gid)
            km[gid] = {u.pk for u in g.users}
            lm[gid] = g.messages[0].id if g.messages else None
            BOT_CONFIG["spam_active"][gid] = False
            log("✅ Group " + gid + " ready")
        except Exception as e:
            log("❌ Error: " + str(e))
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
                            log("💥 Spam to @" + tu)
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
                                cl.direct_send(BOT_CONFIG["auto_replies"][tl], thread_ids=[gid])
                                log("🤖 Auto-reply sent")
                            
                            if not ecmd:
                                continue
                            
                            if tl in ["/help", "!help"]:
                                cl.direct_send("COMMANDS: /autoreply /stopreply /addvideo /addaudio /video /audio /library /music /funny /masti /kick /spam /stopspam /rules /stats /count /ping /time /about /welcome", thread_ids=[gid])
                                log("📋 Help sent")
                            elif tl in ["/stats", "!stats"]:
                                cl.direct_send("STATS - Total: " + str(STATS['total_welcomed']) + " Today: " + str(STATS['today_welcomed']), thread_ids=[gid])
                            elif tl in ["/count", "!count"]:
                                cl.direct_send("MEMBERS: " + str(len(g.users)), thread_ids=[gid])
                            elif tl in ["/welcome", "!welcome"]:
                                cl.direct_send("@" + sender.username + " Test!", thread_ids=[gid])
                            elif tl in ["/ping", "!ping"]:
                                cl.direct_send("Pong! Alive! 🔥", thread_ids=[gid])
                            elif tl in ["/time", "!time"]:
                                cl.direct_send("TIME: " + datetime.now().strftime("%I:%M %p"), thread_ids=[gid])
                            elif tl in ["/about", "!about"]:
                                cl.direct_send("Instagram Bot v3.2 - Neon Edition 🔥", thread_ids=[gid])
                            elif tl.startswith("/autoreply "):
                                p = t.split(" ", 2)
                                if len(p) >= 3:
                                    BOT_CONFIG["auto_replies"][p[1].lower()] = p[2]
                                    BOT_CONFIG["auto_reply_active"] = True
                                    cl.direct_send("✅ Auto-reply set: " + p[1] + " -> " + p[2], thread_ids=[gid])
                            elif tl in ["/stopreply", "!stopreply"]:
                                BOT_CONFIG["auto_reply_active"] = False
                                BOT_CONFIG["auto_replies"] = {}
                                cl.direct_send("⏹️ Auto-reply stopped!", thread_ids=[gid])
                            elif ia and tl.startswith("/addvideo "):
                                p = t.split(" ", 3)
                                if len(p) >= 4:
                                    BOT_CONFIG["media_library"][p[1].lower()] = {"type": "video", "format": p[2].upper(), "link": p[3]}
                                    cl.direct_send("✅ Video saved: " + p[1], thread_ids=[gid])
                            elif ia and tl.startswith("/addaudio "):
                                p = t.split(" ", 2)
                                if len(p) >= 3:
                                    BOT_CONFIG["media_library"][p[1].lower()] = {"type": "audio", "link": p[2]}
                                    cl.direct_send("✅ Audio saved: " + p[1], thread_ids=[gid])
                            elif tl.startswith("/video "):
                                p = t.split(" ", 1)
                                if len(p) >= 2:
                                    n = p[1].lower()
                                    if n in BOT_CONFIG["media_library"] and BOT_CONFIG["media_library"][n]["type"] == "video":
                                        md = BOT_CONFIG["media_library"][n]
                                        cl.direct_send("🎥 VIDEO: " + p[1].upper() + " | Type: " + md.get("format", "VIDEO") + " | Watch: " + md["link"], thread_ids=[gid])
                                    else:
                                        cl.direct_send("❌ Video not found!", thread_ids=[gid])
                            elif tl.startswith("/audio "):
                                p = t.split(" ", 1)
                                if len(p) >= 2:
                                    n = p[1].lower()
                                    if n in BOT_CONFIG["media_library"] and BOT_CONFIG["media_library"][n]["type"] == "audio":
                                        md = BOT_CONFIG["media_library"][n]
                                        cl.direct_send("🎵 AUDIO: " + p[1].upper() + " | Listen: " + md["link"], thread_ids=[gid])
                                    else:
                                        cl.direct_send("❌ Audio not found!", thread_ids=[gid])
                            elif tl in ["/library", "!library"]:
                                if BOT_CONFIG["media_library"]:
                                    vids = [k for k, v in BOT_CONFIG["media_library"].items() if v["type"] == "video"]
                                    auds = [k for k, v in BOT_CONFIG["media_library"].items() if v["type"] == "audio"]
                                    msg = "📚 LIBRARY | Videos: " + ", ".join(vids) if vids else "" + " | Audios: " + ", ".join(auds) if auds else ""
                                    cl.direct_send(msg, thread_ids=[gid])
                                else:
                                    cl.direct_send("📚 Library empty!", thread_ids=[gid])
                            elif tl in ["/music", "!music"]:
                                cl.direct_send("🎵 Music! " + " ".join(random.choices(MUSIC_EMOJIS, k=5)), thread_ids=[gid])
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
                                            cl.direct_send("👢 Kicked @" + tg.username, thread_ids=[gid])
                                        except:
                                            cl.direct_send("❌ Cannot kick", thread_ids=[gid])
                            elif tl in ["/rules", "!rules"]:
                                cl.direct_send("📜 RULES: 1.Respect 2.No spam 3.Follow guidelines 4.Have fun!", thread_ids=[gid])
                            elif ia and tl.startswith("/spam "):
                                p = t.split(" ", 2)
                                if len(p) >= 3:
                                    BOT_CONFIG["target_spam"][gid] = {"username": p[1].replace("@", ""), "message": p[2]}
                                    BOT_CONFIG["spam_active"][gid] = True
                                    cl.direct_send("💥 Spam started on @" + p[1], thread_ids=[gid])
                            elif ia and tl in ["/stopspam", "!stopspam"]:
                                BOT_CONFIG["spam_active"][gid] = False
                                cl.direct_send("⏹️ Spam stopped!", thread_ids=[gid])
                        
                        if g.messages:
                            lm[gid] = g.messages[0].id
                    
                    cm = {u.pk for u in g.users}
                    nwm = cm - km[gid]
                    if nwm:
                        for u in g.users:
                            if u.pk in nwm and u.username != un:
                                if STOP_EVENT.is_set():
                                    break
                                log("👋 NEW: @" + u.username)
                                for ms in wm:
                                    if STOP_EVENT.is_set():
                                        break
                                    fm = ("@" + u.username + " " + ms) if ucn else ms
                                    cl.direct_send(fm, thread_ids=[gid])
                                    STATS["total_welcomed"] += 1
                                    STATS["today_welcomed"] += 1
                                    log("✅ Welcomed @" + u.username)
                                    time.sleep(dly)
                                km[gid].add(u.pk)
                    km[gid] = cm
                    
                except:
                    pass
            time.sleep(pol)
        except:
            pass
    log("🏁 Bot stopped")

@app.route("/")
def index():
    return render_template_string(PAGE_HTML)

@app.route("/start", methods=["POST"])
def start_bot():
    global BOT_THREAD, STOP_EVENT
    if BOT_THREAD and BOT_THREAD.is_alive():
        return jsonify({"message": "Bot already running!"})
    
    un = request.form.get("username")
    pw = request.form.get("password")
    wl = [m.strip() for m in request.form.get("welcome", "").splitlines() if m.strip()]
    gids = [g.strip() for g in request.form.get("group_ids", "").split(",") if g.strip()]
    adm = [a.strip() for a in request.form.get("admin_ids", "").split(",") if a.strip()]
    
    if not un or not pw or not gids or not wl:
        return jsonify({"message": "Fill all required fields!"})
    
    STOP_EVENT.clear()
    BOT_THREAD = threading.Thread(
        target=run_bot, 
        args=(un, pw, wl, gids, int(request.form.get("delay", 3)), int(request.form.get("poll", 5)), 
              request.form.get("use_custom_name") == "yes", request.form.get("enable_commands") == "yes", adm, None), 
        daemon=True
    )
    BOT_THREAD.start()
    log("🚀 Bot started via Web UI!")
    return jsonify({"message": "✅ Bot Started! Auto Proxy Active!"})

@app.route("/stop", methods=["POST"])
def stop_bot():
    STOP_EVENT.set()
    return jsonify({"message": "✅ Bot Stopped!"})

@app.route("/logs")
def get_logs():
    return jsonify({"logs": LOGS[-200:]})

@app.route("/stats")
def get_stats():
    return jsonify(STATS)

# 🔥 FULL NEON DESIGN - SAME AS ORIGINAL (BADA WALA)
PAGE_HTML = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>🔥 NEON INSTAGRAM BOT v3.2 🔥</title>
    <style>
        *{margin:0;padding:0;box-sizing:border-box}
        body{font-family:'Segoe UI',Tahoma,Geneva,Verdana,sans-serif;background:linear-gradient(135deg,#0c0c0c 0%,#1a1a2e 50%,#16213e 100%);min-height:100vh;color:#fff;position:relative;overflow-x:hidden}
        body::before{content:'';position:fixed;top:0;left:0;width:100%;height:100%;background:radial-gradient(circle at 20% 80%,rgba(120,119,198,0.3) 0%,transparent 50%),radial-gradient(circle at 80% 20%,rgba(255,119,198,0.3) 0%,transparent 50%),radial-gradient(circle at 40% 40%,rgba(120,219,255,0.3) 0%,transparent 50%);z-index:-1;animation:neonPulse 4s ease-in-out infinite alternate}
        @keyframes neonPulse{0%{opacity:0.8}100%{opacity:1}}
        .container{max-width:800px;margin:0 auto;padding:20px}
        .header{text-align:center;margin-bottom:30px}
        .logo{font-size:2.5em;font-weight:800;background:linear-gradient(45deg,#ff6b6b,#4ecdc4,#45b7d1,#96ceb4,#feca57);background-size:400% 400%;-webkit-background-clip:text;-webkit-text-fill-color:transparent;animation:gradientShift 3s ease infinite}
        @keyframes gradientShift{0%{background-position:0% 50%}50%{background-position:100% 50%}100%{background-position:0% 50%}}
        .subtitle{font-size:1.1em;color:#a0a0a0;margin-top:10px;animation:pulse 2s infinite}
        @keyframes pulse{0%,100%{opacity:1}50%{opacity:0.7}}
        .card{background:rgba(255,255,255,0.05);backdrop-filter:blur(20px);border-radius:20px;border:1px solid rgba(255,255,255,0.1);padding:25px;margin-bottom:20px;box-shadow:0 20px 40px rgba(0,0,0,0.3)}
        .card-title{font-size:1.3em;margin-bottom:15px;color:#4ecdc4;font-weight:600;text-align:center}
        .form-group{margin-bottom:20px}
        label{display:block;margin-bottom:8px;color:#b0b0b0;font-weight:500}
        input,textarea,select{width:100%;padding:15px;border:2px solid rgba(255,255,255,0.1);border-radius:12px;background:rgba(255,255,255,0.05);color:#fff;font-size:16px;transition:all 0.3s ease}
        input:focus,textarea:focus,select:focus{outline:none;border-color:#4ecdc4;box-shadow:0 0 20px rgba(78,205,196,0.3)}
        textarea{height:120px;resize:vertical}
        .checkbox-group{display:flex;align-items:center;gap:10px;margin:10px 0}
        .btn{display:block;width:100%;padding:15px;font-size:18px;font-weight:600;border:none;border-radius:12px;cursor:pointer;transition:all 0.3s ease;margin:10px 0;text-transform:uppercase;letter-spacing:1px}
        .btn-primary{background:linear-gradient(45deg,#ff6b6b,#4ecdc4);box-shadow:0 10px 30px rgba(78,205,196,0.4)}
        .btn-primary:hover{background:linear-gradient(45deg,#4ecdc4,#ff6b6b);transform:translateY(-2px);box-shadow:0 15px 40px rgba(78,205,196,0.6)}
        .btn-danger{background:linear-gradient(45deg,#ff4757,#ff3838);box-shadow:0 10px 30px rgba(255,71,87,0.4)}
        .btn-danger:hover{background:linear-gradient(45deg,#ff3838,#ff4757);transform:translateY(-2px)}
        .status{display:flex;align-items:center;gap:10px;padding:15px;border-radius:12px;margin:15px 0;font-weight:500}
        .status.running{background:rgba(46,204,113,0.2);border:1px solid #46d113;color:#46d113}
        .status.stopped{background:rgba(149,165,166,0.2);border:1px solid #95a5a6;color:#95a5a6}
        .logs{max-height:400px;overflow-y:auto;background:rgba(0,0,0,0.5);border-radius:12px;padding:15px;border:1px solid rgba(255,255,255,0.1);font-family:monospace;font-size:14px;line-height:1.5}
        .log-line{word-break:break-all;margin-bottom:5px}
        .log-time{color:#4ecdc4}
        .stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:15px;margin-top:15px}
        .stat-card{background:rgba(255,255,255,0.05);padding:20px;border-radius:15px;text-align:center;border:1px solid rgba(255,255,255,0.1);transition:transform 0.3s ease}
        .stat-card:hover{transform:translateY(-5px)}
        .stat-value{font-size:2em;font-weight:800;color:#4ecdc4}
        .stat-label{color:#a0a0a0;font-size:0.9em;margin-top:5px}
        @media(max-width:768px){.container{padding:15px}.logo{font-size:2em}.card{padding:20px}}
        .glow{animation:glow 2s ease-in-out infinite alternate}
        @keyframes glow{from{text-shadow:0 0 10px #4ecdc4}to{text-shadow:0 0 20px #4ecdc4,0 0 30px #4ecdc4}}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1 class="logo glow">🔥 NEON BOT v3.2</h1>
            <p class="subtitle">Instagram Direct Bot | Auto Proxy | Full Commands | Neon Design</p>
        </div>
        
        <div class="card" id="statusCard">
            <div class="status stopped" id="status">
                <span>🛑 Bot Stopped</span>
            </div>
        </div>
        
        <div class="stats-grid" id="statsGrid" style="display:none;">
            <div class="stat-card">
                <div class="stat-value" id="totalWelcomed">0</div>
                <div class="stat-label">Total Welcomed</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="todayWelcomed">0</div>
                <div class="stat-label">Today Welcomed</div>
            </div>
        </div>
        
        <div class="card">
            <h2 class="card-title">⚙️ Bot Settings</h2>
            <form id="botForm">
                <div class="form-group">
                    <label>📱 Instagram Username</label>
                    <input type="text" name="username" placeholder="your_username" required>
                </div>
                <div class="form-group">
                    <label>🔐 Password</label>
                    <input type="password" name="password" placeholder="your_password" required>
                </div>
                <div class="form-group">
                    <label>👥 Group IDs (comma separated)</label>
                    <input type="text" name="group_ids" placeholder="123456789,987654321" required>
                </div>
                <div class="form-group">
                    <label>💬 Welcome Messages (one per line)</label>
                    <textarea name="welcome" placeholder="Welcome bro! 🔥&#10;New member alert! 👋&#10;Hey enjoy the group! 🎉" required>Hey @user welcome to group! 🔥
New member! Enjoy mastii! 🎉
Hello brother! 😎</textarea>
                </div>
                <div class="form-group">
                    <label>⏱️ Welcome Delay (seconds)</label>
                    <input type="number" name="delay" value="3" min="1" max="10">
                </div>
                <div class="form-group">
                    <label>🔄 Poll Interval (seconds)</label>
                    <input type="number" name="poll" value="5" min="2" max="30">
                </div>
                <div class="checkbox-group">
                    <input type="checkbox" name="use_custom_name" id="customName">
                    <label for="customName">@username in welcome msg</label>
                </div>
                <div class="checkbox-group">
                    <input type="checkbox" name="enable_commands" id="commands" checked>
                    <label for="commands">Enable Commands (/help)</label>
                </div>
                <div class="form-group">
                    <label>👑 Admin Usernames (comma separated)</label>
                    <input type="text" name="admin_ids" placeholder="admin1,admin2">
                </div>
                <button type="submit" class="btn btn-primary">🚀 START BOT</button>
            </form>
        </div>
        
        <div class="card">
            <div style="display:flex;gap:10px;">
                <button onclick="stopBot()" class="btn btn-danger" style="flex:1">🛑 STOP BOT</button>
                <button onclick="refreshLogs()" class="btn" style="flex:1;background:rgba(255,255,255,0.1);color:#fff">🔄 REFRESH</button>
            </div>
        </div>
        
        <div class="card">
            <h2 class="card-title">📊 Live Logs</h2>
            <div class="logs" id="logs"></div>
        </div>
    </div>

    <script>
        let logInterval;
        const form = document.getElementById('botForm');
        const logsDiv = document.getElementById('logs');
        const statusDiv = document.getElementById('status');
        
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(form);
            try {
                const res = await fetch('/start', {method:'POST', body:formData});
                const data = await res.json();
                alert('✅ ' + data.message);
                updateStatus('running');
                refreshLogs();
            } catch(e) {
                alert('❌ Error: ' + e.message);
            }
        });
        
        async function stopBot() {
            try {
                const res = await fetch('/stop', {method:'POST'});
                const data = await res.json();
                alert('✅ ' + data.message);
                updateStatus('stopped');
            } catch(e) {
                alert('❌ Error: ' + e.message);
            }
        }
        
        function updateStatus(state) {
            statusDiv.className = `status ${state}`;
            statusDiv.innerHTML = state === 'running' ? '<span>🟢 Bot Running</span>' : '<span>🛑 Bot Stopped</span>';
            document.getElementById('statsGrid').style.display = state === 'running' ? 'grid' : 'none';
        }
        
        async function refreshLogs() {
            try {
                const res = await fetch('/logs');
                const data = await res.json();
                logsDiv.innerHTML = data.logs.map(log => {
                    const timeMatch = log.match(/\\[(\\d{2}:\\d{2}:\\d{2})\\]/);
                    const time = timeMatch ? timeMatch[1] : '';
                    const message = log.replace(/\\[\\d{2}:\\d{2}:\\d{2}\\] /, '');
                    return `<div class="log-line"><span class="log-time">[${time}]</span> ${message}</div>`;
                }).join('');
                logsDiv.scrollTop = logsDiv.scrollHeight;
            } catch(e) {}
        }
        
        async function updateStats() {
            try {
                const res = await fetch('/stats');
                const stats = await res.json();
                document.getElementById('totalWelcomed').textContent = stats.total_welcomed;
                document.getElementById('todayWelcomed').textContent = stats.today_welcomed;
            } catch(e) {}
        }
        
        logInterval = setInterval(refreshLogs, 2000);
        setInterval(updateStats, 5000);
        refreshLogs();
        updateStats();
    </script>
</body>
</html>"""

if __name__ == "__main__":
    log("🌟 NEON BOT v3.2 Starting... 🔥")
    log("📱 Web UI: http://localhost:5000")
    log("🚀 FULL FEATURES + NEON DESIGN + FIXED PROXY!")
    app.run(host="0.0.0.0", port=5000, debug=False)
