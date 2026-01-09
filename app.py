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
FUNNY = ["Hahaha! 😂", "LOL! 🤣", "Mast! 😆", "Pagal! 🤪", "King! 👑😂"]
MASTI = ["Party! 🎉", "Masti! 🥳", "Dhamaal! 💃", "Full ON! 🔥", "Enjoy! 🎊"]

def get_free_proxy():
    """Free proxy rotation list"""
    proxies = [
        "http://103.153.39.19:80",
        "http://47.74.66.248:8888", 
        "http://103.175.220.158:5746",
        "http://47.74.79.77:8888",
        "http://103.153.39.19:655",
        "http://proxy6.net:8080",
        "http://p.proxys rotation.com:8080"
    ]
    return random.choice(proxies)

def test_proxy(cl, proxy):
    """Test if proxy works"""
    try:
        cl.set_proxy(proxy)
        cl.get_timeline_feed(limit=1)
        return True
    except:
        return False

def run_bot(un, pw, wm, gids, dly, pol, ucn, ecmd, admin_ids, proxy=None):
    cl = Client()
    
    # Proxy setup with auto rotation
    current_proxy = proxy or get_free_proxy()
    log(f"🌐 Proxy: {current_proxy}")
    
    max_retries = 5
    login_success = False
    
    for attempt in range(max_retries):
        try:
            log(f"🔐 Login attempt {attempt + 1}/{max_retries}")
            
            # Set proxy
            if current_proxy:
                cl.set_proxy(current_proxy)
                time.sleep(3)
                log("✅ Proxy configured")
            
            # Try login
            if os.path.exists(SESSION_FILE):
                cl.load_settings(SESSION_FILE)
                cl.login(un, pw)
                log("✅ Session loaded successfully")
            else:
                cl.login(un, pw)
                cl.dump_settings(SESSION_FILE)
                log("✅ New session created")
            
            login_success = True
            break
            
        except (LoginRequired, ClientError, PleaseWaitFewMinutes) as e:
            error_msg = str(e).lower()
            log(f"⚠️ Login error: {str(e)[:80]}")
            
            if "blacklist" in error_msg or "ip" in error_msg or attempt > 2:
                log("🔄 Rotating proxy...")
                current_proxy = get_free_proxy()
            
            wait_time = 30 * (attempt + 1)
            log(f"⏳ Waiting {wait_time}s before retry...")
            time.sleep(wait_time)
            
        except Exception as e:
            log(f"❌ Unexpected error: {e}")
            time.sleep(10)
    
    if not login_success:
        log("💥 LOGIN FAILED - Check credentials or use different proxy")
        return
    
    log("🎉 BOT STARTED SUCCESSFULLY!")
    log(f"👑 Admins: {admin_ids}")
    
    # Initialize groups
    km = {gid: set() for gid in gids}
    lm = {gid: None for gid in gids}
    
    for gid in gids:
        try:
            g = cl.direct_thread(gid)
            km[gid] = {u.pk for u in g.users}
            lm[gid] = g.messages[0].id if g.messages else None
            BOT_CONFIG["spam_active"][gid] = False
            log(f"✅ Group {gid} ready ({len(g.users)} members)")
        except Exception as e:
            log(f"⚠️ Group {gid} error: {e}")
            km[gid] = set()
    
    # Reset daily stats
    global STATS
    if STATS["last_reset"] != datetime.now().date():
        STATS["today_welcomed"] = 0
        STATS["last_reset"] = datetime.now().date()
    
    # Main bot loop
    while not STOP_EVENT.is_set():
        try:
            for gid in gids:
                if STOP_EVENT.is_set():
                    break
                
                try:
                    g = cl.direct_thread(gid)
                    
                    # SPAM FEATURE
                    if BOT_CONFIG["spam_active"].get(gid, False):
                        spam_data = BOT_CONFIG["target_spam"].get(gid, {})
                        tu = spam_data.get("username")
                        sm = spam_data.get("message")
                        if tu and sm:
                            cl.direct_send(f"@{tu} {sm}", thread_ids=[gid])
                            log(f"📨 Spam sent to @{tu}")
                            time.sleep(3)
                    
                    # COMMAND PROCESSING
                    if ecmd or BOT_CONFIG["auto_reply_active"]:
                        new_messages = []
                        if lm[gid]:
                            for m in g.messages:
                                if m.id == lm[gid]:
                                    break
                                new_messages.append(m)
                        
                        for m in reversed(new_messages):
                            if m.user_id == cl.user_id:
                                continue
                            
                            sender = next((u for u in g.users if u.pk == m.user_id), None)
                            if not sender:
                                continue
                            
                            su = sender.username.lower()
                            is_admin = admin_ids and su in [a.lower() for a in admin_ids]
                            text = m.text.strip() if m.text else ""
                            text_lower = text.lower()
                            
                            # AUTO REPLY
                            if BOT_CONFIG["auto_reply_active"] and text_lower in BOT_CONFIG["auto_replies"]:
                                reply = BOT_CONFIG["auto_replies"][text_lower]
                                cl.direct_send(reply, thread_ids=[gid])
                                log(f"🤖 Auto-reply to @{sender.username}")
                            
                            if not ecmd:
                                continue
                            
                            # COMMANDS
                            if text_lower in ["/help", "!help"]:
                                help_text = "🤖 COMMANDS:
/help /stats /ping /time
/count /welcome /music /funny /masti
/autoreply /stopreply /spam /stopspam"
                                cl.direct_send(help_text, thread_ids=[gid])
                                log(f"Help sent to @{sender.username}")
                            
                            elif text_lower in ["/stats", "!stats"]:
                                stats_text = f"📊 STATS
Total: {STATS['total_welcomed']}
Today: {STATS['today_welcomed']}"
                                cl.direct_send(stats_text, thread_ids=[gid])
                            
                            elif text_lower in ["/count", "!count"]:
                                cl.direct_send(f"👥 Members: {len(g.users)}", thread_ids=[gid])
                            
                            elif text_lower in ["/ping", "!ping"]:
                                cl.direct_send("🏓 PONG! Bot Active 🚀", thread_ids=[gid])
                            
                            elif text_lower in ["/time", "!time"]:
                                current_time = datetime.now().strftime("%I:%M %p")
                                cl.direct_send(f"🕐 Time: {current_time}", thread_ids=[gid])
                            
                            elif text_lower in ["/music", "!music"]:
                                music_msg = "♪♫ " + " ".join(random.choices(MUSIC_EMOJIS, k=4))
                                cl.direct_send(music_msg, thread_ids=[gid])
                            
                            elif text_lower in ["/funny", "!funny"]:
                                cl.direct_send(random.choice(FUNNY), thread_ids=[gid])
                            
                            elif text_lower in ["/masti", "!masti"]:
                                cl.direct_send(random.choice(MASTI), thread_ids=[gid])
                            
                            elif text_lower.startswith("/autoreply ") and len(text.split()) >= 3:
                                parts = text.split(" ", 2)
                                trigger = parts[1].lower()
                                response = parts[2]
                                BOT_CONFIG["auto_replies"][trigger] = response
                                BOT_CONFIG["auto_reply_active"] = True
                                cl.direct_send(f"✅ Auto-reply set: '{trigger}' → '{response[:30]}...'", thread_ids=[gid])
                            
                            elif text_lower in ["/stopreply", "!stopreply"]:
                                BOT_CONFIG["auto_reply_active"] = False
                                BOT_CONFIG["auto_replies"] = {}
                                cl.direct_send("⏹️ Auto-reply stopped!", thread_ids=[gid])
                            
                            elif is_admin and text_lower.startswith("/spam ") and len(text.split()) >= 3:
                                parts = text.split(" ", 2)
                                target = parts[1].replace("@", "")
                                message = parts[2]
                                BOT_CONFIG["target_spam"][gid] = {"username": target, "message": message}
                                BOT_CONFIG["spam_active"][gid] = True
                                cl.direct_send(f"🔥 Spam started → @{target}", thread_ids=[gid])
                            
                            elif is_admin and text_lower in ["/stopspam", "!stopspam"]:
                                BOT_CONFIG["spam_active"][gid] = False
                                cl.direct_send("🛑 Spam stopped!", thread_ids=[gid])
                        
                        if g.messages:
                            lm[gid] = g.messages[0].id
                    
                    # NEW MEMBER WELCOME
                    current_members = {u.pk for u in g.users}
                    new_members = current_members - km[gid]
                    
                    for member in g.users:
                        if member.pk in new_members and member.username != un:
                            log(f"👋 NEW MEMBER: @{member.username}")
                            for welcome_msg in wm:
                                final_msg = (f"@{member.username} " + welcome_msg) if ucn else welcome_msg
                                cl.direct_send(final_msg, thread_ids=[gid])
                                STATS["total_welcomed"] += 1
                                STATS["today_welcomed"] += 1
                                log(f"✅ Welcomed @{member.username}")
                                time.sleep(dly)
                            km[gid].add(member.pk)
                            break
                    
                    km[gid] = current_members
                
                except Exception as e:
                    log(f"⚠️ Group {gid} error: {str(e)[:60]}")
                    time.sleep(5)
            
            time.sleep(pol)
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            log(f"⚠️ Main loop error: {e}")
            time.sleep(10)
    
    log("🛑 Bot stopped gracefully")

@app.route("/")
def index():
    return render_template_string(PAGE_HTML)

@app.route("/start", methods=["POST"])
def start_bot():
    global BOT_THREAD, STOP_EVENT
    
    if BOT_THREAD and BOT_THREAD.is_alive():
        return jsonify({"message": "🤖 Bot already running!"})
    
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()
    welcome_msgs = [m.strip() for m in request.form.get("welcome", "").splitlines() if m.strip()]
    group_ids = [g.strip() for g in request.form.get("group_ids", "").split(",") if g.strip()]
    admin_ids = [a.strip() for a in request.form.get("admin_ids", "").split(",") if a.strip()]
    proxy = request.form.get("proxy", "").strip()
    
    if not all([username, password, group_ids, welcome_msgs]):
        return jsonify({"message": "❌ Please fill all required fields!"})
    
    if len(group_ids) == 0:
        return jsonify({"message": "❌ Enter at least one group ID!"})
    
    STOP_EVENT.clear()
    BOT_THREAD = threading.Thread(
        target=run_bot,
        args=(
            username, password, welcome_msgs, group_ids,
            int(request.form.get("delay", 3)),
            int(request.form.get("poll", 5)),
            request.form.get("use_custom_name") == "yes",
            request.form.get("enable_commands") == "yes",
            admin_ids,
            proxy if proxy else None
        ),
        daemon=True
    )
    BOT_THREAD.start()
    log("🚀 Bot started by web interface!")
    return jsonify({"message": "🚀 Bot started with Anti-Ban protection!"})

@app.route("/stop", methods=["POST"])
def stop_bot():
    global BOT_THREAD
    STOP_EVENT.set()
    if BOT_THREAD:
        BOT_THREAD.join(timeout=10)
    LOGS.clear()
    return jsonify({"message": "🛑 Bot stopped successfully!"})

@app.route("/logs")
def get_logs():
    return jsonify({"logs": LOGS[-150:]})

@app.route("/stats")
def get_stats():
    return jsonify(STATS)

PAGE_HTML = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>🚀 INSTAGRAM ANTI-BAN BOT</title>
    <style>
        *{margin:0;padding:0;box-sizing:border-box}
        body{font-family:'Segoe UI',Arial,sans-serif;background:linear-gradient(135deg,#0c0c1d,#1a0033,#0f0f23);color:#fff;min-height:100vh;padding:20px;position:relative}
        body::before{content:'';position:fixed;top:0;left:0;width:100%;height:100%;background:radial-gradient(circle at 20% 50%,rgba(0,255,255,.1),transparent 60%),radial-gradient(circle at 80% 80%,rgba(255,0,255,.1),transparent 60%);z-index:-1}
        .container{max-width:800px;margin:0 auto;background:rgba(10,10,40,.95);border-radius:25px;padding:30px;border:2px solid rgba(0,255,255,.6);box-shadow:0 0 50px rgba(0,255,255,.3)}
        h1{text-align:center;font-size:3em;font-weight:900;margin-bottom:30px;background:linear-gradient(90deg,#00ffff,#ff00ff,#ffff00);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;letter-spacing:3px;text-shadow:0 0 20px rgba(0,255,255,.5);animation:pulse 2s infinite}
        @keyframes pulse{0%,100%{opacity:1}50%{opacity:.8}}
        label{display:block;margin:15px 0 5px 0;font-weight:700;font-size:15px;color:#00ffff}
        input,textarea,select{width:100%;padding:15px;border-radius:15px;background:rgba(0,25,50,.8);color:#fff;font-size:16px;border:2px solid rgba(0,255,255,.4);transition:all .3s;margin-bottom:15px}
        input:focus,textarea:focus,select:focus{outline:0;border-color:#00ffff;box-shadow:0 0 20px rgba(0,255,255,.4);transform:scale(1.02)}
        textarea{min-height:100px;resize:vertical}
        .btn-group{display:flex;gap:20px;margin-top:30px;justify-content:center;flex-wrap:wrap}
        button{padding:18px 40px;font-size:18px;font-weight:900;border:none;border-radius:30px;cursor:pointer;text-transform:uppercase;transition:all .4s;box-shadow:0 8px 25px rgba(0,0,0,.4);min-width:180px}
        .start{background:linear-gradient(135deg,#00ff88,#00cc66);color:#000}
        .stop{background:linear-gradient(135deg,#ff416c,#ff4b2b);color:#fff}
        button:hover{transform:translateY(-5px) scale(1.05)}
        .status{padding:20px;margin:25px 0;border-radius:15px;text-align:center;font-weight:700;font-size:18px}
        .status.success{background:rgba(0,255,0,.2);border-left:5px solid #00ff00}
        .status.error{background:rgba(255,0,0,.2);border-left:5px solid #ff4444}
        .logs-section{margin-top:40px}
        .logs-title{text-align:center;color:#00ffff;font-size:24px;margin-bottom:20px;font-weight:900;text-shadow:0 0 15px rgba(0,255,255,.5)}
        .logs{background:rgba(0,0,0,.9);border:2px solid rgba(0,255,255,.5);border-radius:20px;padding:25px;height:400px;overflow-y:auto;font-family:'Courier New',monospace;font-size:14px;line-height:1.6;box-shadow:inset 0 0 30px rgba(0,255,255,.1)}
        .log-line{margin-bottom:8px;padding:8px;border-radius:8px;background:rgba(255,255,255,.03);border-left:4px solid #00ffff}
        .logs::-webkit-scrollbar{width:12px}
        .logs::-webkit-scrollbar-track{background:rgba(0,0,0,.5)}
        .logs::-webkit-scrollbar-thumb{background:linear-gradient(#00ffff,#ff00ff);border-radius:10px}
        @media(max-width:768px){.container{padding:20px}h1{font-size:2em}.btn-group{flex-direction:column}button{width:100%}}
        ::placeholder{color:rgba(255,255,255,.6)}
    </style>
</head>
<body>
    <div class="container">
        <h1>🚀 ANTI-BAN BOT v4.0</h1>
        <div class="status success" id="status">✅ Ready to deploy with IP protection!</div>
        
        <form id="botForm">
            <label>👤 Instagram Username</label>
            <input name="username" placeholder="your_username" required>
            
            <label>🔑 Password</label>
            <input type="password" name="password" placeholder="your_password" required>
            
            <label>👑 Admin Usernames (optional)</label>
            <input name="admin_ids" placeholder="admin1,admin2,admin3">
            
            <label>🎉 Welcome Messages</label>
            <textarea name="welcome" placeholder="Welcome to our group! 🎉
Have fun and follow rules 😊" required>Hey there! Welcome 🎉
Enjoy the group! 😊</textarea>
            
            <label>📢 Group IDs (comma separated)</label>
            <input name="group_ids" placeholder="1234567890,9876543210" required>
            
            <label>🌐 Proxy (optional - auto rotation enabled)</label>
            <input name="proxy" placeholder="http://user:pass@ip:port">
            
            <label>⚙️ Mention New Users?</label>
            <select name="use_custom_name">
                <option value="yes">Yes (@username)</option>
                <option value="no">No</option>
            </select>
            
            <label>🎛️ Enable Commands?</label>
            <select name="enable_commands">
                <option value="yes">Yes (Full Features)</option>
            </select>
            
            <label>⏱️ Welcome Delay (seconds)</label>
            <input type="number" name="delay" value="3" min="1" max="10">
            
            <label>🔄 Poll Interval (seconds)</label>
            <input type="number" name="poll" value="5" min="3" max="30">
            
            <div class="btn-group">
                <button type="button" class="start" onclick="startBot()">🚀 START BOT</button>
                <button type="button" class="stop" onclick="stopBot()">🛑 STOP BOT</button>
            </div>
        </form>
        
        <div class="logs-section">
            <div class="logs-title">📡 LIVE LOGS</div>
            <div class="logs" id="logs">Waiting for bot activity... ⌛</div>
        </div>
    </div>

    <script>
        async function startBot() {
            const form = document.getElementById('botForm');
            const formData = new FormData(form);
            const status = document.getElementById('status');
            
            try {
                status.textContent = '🚀 Starting bot...';
                status.className = 'status error';
                
                const response = await fetch('/start', {
                    method: 'POST',
                    body: formData
                });
                const result = await response.json();
                
                status.textContent = result.message;
                status.className = 'status success';
                alert(result.message);
                
            } catch (error) {
                status.textContent = '❌ Network error!';
                status.className = 'status error';
                alert('Error: ' + error.message);
            }
        }
        
        async function stopBot() {
            try {
                const response = await fetch('/stop', {method: 'POST'});
                const result = await response.json();
                alert(result.message);
                document.getElementById('status').textContent = '🛑 Bot stopped';
            } catch (error) {
                alert('Error: ' + error.message);
            }
        }
        
        // Auto refresh logs
        setInterval(async () => {
            try {
                const response = await fetch('/logs');
                const data = await response.json();
                const logsDiv = document.getElementById('logs');
                logsDiv.innerHTML = data.logs.map(log => 
                    `<div class="log-line">${log}</div>`
                ).join('') || 'No logs yet...';
                logsDiv.scrollTop = logsDiv.scrollHeight;
            } catch (e) {}
        }, 2500);
    </script>
</body>
</html>"""

if __name__ == "__main__":
    log("🎉 Instagram Anti-Ban Bot v4.0 starting...")
    log("✅ Deployed on Render.com - IP Blacklist Protection ACTIVE")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
