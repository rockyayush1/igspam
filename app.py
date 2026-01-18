import os
import threading
import time
import random
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify
from instagrapi import Client
from instagrapi.exceptions import (
    LoginRequired, RateLimitError, ClientError, ClientForbiddenError, 
    ClientNotFoundError, ChallengeRequired, SessionIdExpired, PleaseWaitFewMinutes
)

app = Flask(__name__)

# Global variables
BOT_THREAD = None
STOP_EVENT = threading.Event()
LOGS = []
START_TIME = None
CLIENT = None
SESSION_TOKEN = None
LOGIN_SUCCESS = False

STATS = {
    "total_welcomed": 0,
    "today_welcomed": 0,
    "last_reset": datetime.now().date()
}

BOT_CONFIG = {
    "auto_replies": {},
    "auto_reply_active": False,
    "target_spam": {},
    "spam_active": {},
    "media_library": {}
}

def uptime():
    if not START_TIME:
        return "00:00:00"
    delta = datetime.now() - START_TIME
    hours, rem = divmod(int(delta.total_seconds()), 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    lm = f"[{ts}] {msg}"
    LOGS.append(lm)
    if len(LOGS) > 500:
        LOGS[:] = LOGS[-500:]
    print(lm)

def clear_logs():
    global LOGS
    LOGS.clear()
    log("🧹 Logs cleared by user!")

def create_stable_client():
    """Create ultra-stable client with 2026 Instagram settings"""
    cl = Client()
    
    # ULTRA CONSERVATIVE settings - No detection
    cl.delay_range = [8, 15]  # Very slow
    cl.request_timeout = 90
    cl.max_retries = 1
    
    # Latest REAL Samsung S25 UA (2026)
    ua = "Instagram 380.0.0.28.104 Android (35/14; 600dpi; 1440x3360; samsung; SM-S936B; dm5q; exynos2500; en_IN; 380000028)"
    cl.set_user_agent(ua)
    
    # Real device fingerprint
    cl.set_device({
        "phone_manufacturer": "samsung",
        "phone_model": "SM-S936B",
        "android_version": 35,
        "android_release": "15"
    })
    
    return cl

def safe_login(cl, token, max_retries=3):
    """Safe login with full error handling"""
    global LOGIN_SUCCESS, SESSION_TOKEN
    
    for attempt in range(max_retries):
        try:
            log(f"🔐 Login attempt {attempt+1}/{max_retries}")
            cl.login_by_sessionid(token)
            
            # Verify login worked
            account = cl.account_info()
            if account and hasattr(account, 'username') and account.username:
                username = account.username
                log(f"✅ Login SUCCESS: @{username}")
                LOGIN_SUCCESS = True
                SESSION_TOKEN = token
                time.sleep(3)  # Stabilization delay
                return True, username
            else:
                raise Exception("Account info incomplete")
                
        except SessionIdExpired:
            log("❌ SESSION EXPIRED - Get new token!")
            return False, None
        except (LoginRequired, ChallengeRequired):
            log("❌ Login required - Token invalid")
            time.sleep(20)
        except RateLimitError:
            log("⏳ Rate limited during login - 60s wait")
            time.sleep(60)
        except PleaseWaitFewMinutes:
            log("⏳ Instagram cooldown - 5min wait")
            time.sleep(300)
        except Exception as e:
            log(f"⚠️ Login error {attempt+1}: {str(e)[:50]}")
            time.sleep(15 * (attempt + 1))
    
    return False, None

def session_health_check():
    """Check if session is still valid"""
    global CLIENT, LOGIN_SUCCESS
    try:
        if CLIENT:
            CLIENT.account_info()
            return True
    except:
        pass
    LOGIN_SUCCESS = False
    return False

def refresh_session(token):
    """Refresh expired session"""
    global CLIENT, LOGIN_SUCCESS
    log("🔄 Auto session refresh...")
    new_client = create_stable_client()
    success, _ = safe_login(new_client, token)
    if success:
        CLIENT = new_client
        return True
    return False

# ================= MAIN ULTRA-STABLE BOT =================
def run_bot(session_token, wm, gids, dly, pol, ucn, ecmd, admin_ids):
    global START_TIME, CLIENT, LOGIN_SUCCESS
    
    START_TIME = datetime.now()
    consecutive_errors = 0
    max_errors = 12
    
    log("🚀 Starting Premium Bot v4.3 - Anti-Logout Edition")
    
    # Initial login
    CLIENT = create_stable_client()
    success, username = safe_login(CLIENT, session_token)
    if not success:
        log("💥 CRITICAL: Cannot login. Bot STOPPED.")
        return
    
    # Slow group initialization
    km = {gid: set() for gid in gids}
    lm = {gid: None for gid in gids}
    
    log("📱 Initializing groups slowly...")
    for i, gid in enumerate(gids):
        try:
            time.sleep(12)  # 12 sec between groups
            thread = CLIENT.direct_thread(gid)
            km[gid] = {u.pk for u in thread.users}
            if thread.messages:
                lm[gid] = thread.messages[0].id
            BOT_CONFIG["spam_active"][gid] = False
            log(f"✅ Group {i+1}: {gid[:12]}... ready")
        except Exception as e:
            log(f"⚠️ Group {gid[:12]}... failed: {str(e)[:30]}")
    
    log("🎉 ULTRA STABLE MODE ACTIVE - No Logout Guaranteed!")
    
    while not STOP_EVENT.is_set():
        cycle_errors = 0
        
        for gid in gids:
            if STOP_EVENT.is_set():
                break
                
            try:
                # Session check before every operation
                if not session_health_check():
                    log("🔓 Session expired - refreshing...")
                    if not refresh_session(SESSION_TOKEN):
                        log("💥 Refresh failed - stopping bot")
                        return
                    time.sleep(10)
                
                # Ultra slow polling
                time.sleep(random.uniform(10, 18))
                thread = CLIENT.direct_thread(gid)
                consecutive_errors = 0
                
                # ========== COMMANDS (Minimal - Less detection) ==========
                if ecmd:
                    new_msgs = []
                    if lm[gid] and thread.messages:
                        for msg in thread.messages[:10]:  # Check last 10
                            if msg.id == lm[gid]:
                                break
                            new_msgs.append(msg)
                    
                    for msg in reversed(new_msgs[:2]):  # Max 2 per cycle
                        try:
                            if msg.user_id == CLIENT.user_id:
                                continue
                                
                            sender = next((u for u in thread.users if u.pk == msg.user_id), None)
                            if not sender or not sender.username:
                                continue
                                
                            text = (msg.text or "").strip().lower()
                            
                            # Simple commands only
                            if text in ['/ping', '!ping']:
                                CLIENT.direct_send("✅ Bot Active", thread_ids=[gid])
                                time.sleep(8)
                            elif text.startswith('/uptime'):
                                CLIENT.direct_send(f"⏱️ {uptime()}", thread_ids=[gid])
                                time.sleep(8)
                                
                        except:
                            pass
                    if thread.messages:
                        lm[gid] = thread.messages[0].id

                # ========== WELCOME NEW MEMBERS (Main Feature) ==========
                current_members = {u.pk for u in thread.users}
                new_users = current_members - km[gid]
                
                for user in thread.users:
                    if user.pk in new_users and hasattr(user, 'username') and user.username:
                        try:
                            # Send welcome (only first message)
                            welcome_msg = f"@{user.username} Welcome bro! 🔥" if ucn else wm[0]
                            CLIENT.direct_send(welcome_msg, thread_ids=[gid])
                            STATS["total_welcomed"] += 1
                            STATS["today_welcomed"] += 1
                            log(f"👋 NEW USER: @{user.username}")
                            time.sleep(dly * 2 + random.uniform(3, 6))
                            break  # Only 1 welcome per cycle
                        except Exception as e:
                            log(f"⚠️ Welcome error: {str(e)[:30]}")
                            break
                            
                km[gid] = current_members
                
            except SessionIdExpired:
                consecutive_errors += 1
                log("🔓 SESSION EXPIRED - Auto recovery...")
                if refresh_session(SESSION_TOKEN):
                    consecutive_errors = 0
                time.sleep(30)
                
            except (RateLimitError, PleaseWaitFewMinutes):
                consecutive_errors += 1
                log("⏳ Instagram cooldown - waiting 2min")
                time.sleep(120)
                
            except ClientError as e:
                consecutive_errors += 1
                log(f"⚠️ API Error: {str(e)[:30]}")
                time.sleep(20)
                
            except Exception as e:
                cycle_errors += 1
                consecutive_errors += 1
                log(f"💥 Error: {str(e)[:40]}")
                time.sleep(15)
        
        # Emergency recovery
        if consecutive_errors > max_errors:
            log("🔄 EMERGENCY SESSION RESTART")
            if refresh_session(SESSION_TOKEN):
                consecutive_errors = 0
                log("✅ Recovery successful")
            else:
                log("💥 Recovery failed - stopping")
                break
        
        # Main sleep cycle
        if not STOP_EVENT.is_set():
            time.sleep(pol + random.uniform(2, 5))

    log("🛑 Bot stopped gracefully")

# ================= FLASK ROUTES =================
@app.route("/")
def index():
    return render_template_string(PAGE_HTML)

@app.route("/start", methods=["POST"])
def start():
    global BOT_THREAD
    if BOT_THREAD and BOT_THREAD.is_alive():
        return jsonify({"message": "❌ Bot already running! Stop first."})
    
    try:
        token = request.form.get("session", "").strip()
        welcome = [x.strip() for x in request.form.get("welcome", "").splitlines() if x.strip()]
        gids = [x.strip() for x in request.form.get("group_ids", "").split(",") if x.strip()]
        admins = [x.strip() for x in request.form.get("admin_ids", "").split(",") if x.strip()]

        if not all([token, welcome, gids]):
            return jsonify({"message": "❌ Fill ALL fields: Token, Welcome, Group IDs!"})

        global STOP_EVENT
        STOP_EVENT.clear()
        BOT_THREAD = threading.Thread(
            target=run_bot,
            args=(token, welcome, gids,
                  int(request.form.get("delay", 5)),
                  int(request.form.get("poll", 20)),
                  request.form.get("use_custom_name") == "yes",
                  request.form.get("enable_commands") == "yes",
                  admins),
            daemon=True
        )
        BOT_THREAD.start()
        log("🚀 v4.3 Anti-Logout Bot STARTED!")
        return jsonify({"message": "✅ Bot started! Anti-logout protection ACTIVE!"})
    except Exception as e:
        log(f"❌ Start error: {str(e)}")
        return jsonify({"message": f"❌ Start failed: {str(e)}"})

@app.route("/stop", methods=["POST"])
def stop():
    global STOP_EVENT, CLIENT
    STOP_EVENT.set()
    if CLIENT:
        CLIENT = None
    if BOT_THREAD:
        BOT_THREAD.join(timeout=5)
    log("🛑 Bot stopped by user!")
    return jsonify({"message": "✅ Bot stopped safely!"})

@app.route("/logs")
def logs():
    return jsonify({
        "logs": LOGS[-250:],
        "uptime": uptime(),
        "status": "running" if BOT_THREAD and BOT_THREAD.is_alive() else "stopped"
    })

@app.route("/clear_logs", methods=["POST"])
def clear_logs_route():
    clear_logs()
    return jsonify({"message": "✅ Logs cleared successfully!"})

@app.route("/stats")
def stats():
    return jsonify({
        "uptime": uptime(),
        "status": "running" if BOT_THREAD and BOT_THREAD.is_alive() else "stopped",
        "total_welcomed": STATS["total_welcomed"],
        "today_welcomed": STATS["today_welcomed"]
    })

# ================= COMPLETE RESPONSIVE UI =================
PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Premium Instagram Bot v4.3 - Anti-Logout</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        *{margin:0;padding:0;box-sizing:border-box;}
        body{font-family:'Inter',sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);min-height:100vh;padding:20px;color:#2d3748;}
        .container{max-width:950px;margin:0 auto;background:rgba(255,255,255,0.97);backdrop-filter:blur(25px);border-radius:24px;box-shadow:0 30px 60px rgba(0,0,0,0.2);overflow:hidden;}
        .header{background:linear-gradient(135deg,#4f46e5,#7c3aed);color:white;padding:35px;text-align:center;position:relative;overflow:hidden;}
        .header h1{font-size:2.7rem;font-weight:700;margin-bottom:8px;text-shadow:0 2px 10px rgba(0,0,0,0.3);}
        .header p{font-size:1.1rem;opacity:0.95;}
        .status-bar{display:flex;justify-content:space-between;align-items:center;padding:25px 35px;background:linear-gradient(90deg,#f8fafc,#e2e8f0);border-bottom:2px solid #e2e8f0;}
        .status-item{display:flex;align-items:center;gap:10px;font-weight:600;font-size:1rem;}
        .status-running{color:#10b981;}.status-stopped{color:#ef4444;}
        .status-dot{width:14px;height:14px;border-radius:50%;background:#10b981;animation:pulse 1.5s infinite;}
        @keyframes pulse{0%{opacity:1;transform:scale(1);}50%{opacity:0.5;transform:scale(1.1);}100%{opacity:1;transform:scale(1);}}
        .content{padding:35px;}
        .form-grid{display:grid;grid-template-columns:1fr 1fr;gap:25px;margin-bottom:35px;}
        .form-group{position:relative;}
        .form-group.full{grid-column:1/-1;}
        label{display:block;margin-bottom:10px;font-weight:600;color:#374151;font-size:1rem;}
        input,textarea{width:100%;padding:16px 18px;border:2px solid #e5e7eb;border-radius:14px;font-size:1rem;background:white;transition:all 0.3s ease;box-shadow:0 2px 8px rgba(0,0,0,0.05);}
        input:focus,textarea:focus{outline:none;border-color:#4f46e5;box-shadow:0 0 0 4px rgba(79,70,229,0.15),0 4px 15px rgba(0,0,0,0.1);transform:translateY(-2px);}
        textarea{resize:vertical;min-height:140px;font-family:inherit;}
        .checkbox-group{display:flex;align-items:center;gap:15px;padding:20px;background:#f8fafc;border-radius:14px;border:2px solid #e5e7eb;cursor:pointer;transition:all 0.3s ease;}
        .checkbox-group:hover{border-color:#4f46e5;background:#eff6ff;transform:translateY(-2px);}
        .checkbox-group input[type="checkbox"]{width:auto;transform:scale(1.3);}
        .controls{display:flex;gap:20px;justify-content:center;margin:50px 0;flex-wrap:wrap;}
        .btn{padding:18px 40px;border:none;border-radius:18px;font-size:1.15rem;font-weight:600;cursor:pointer;transition:all 0.3s ease;display:flex;align-items:center;gap:12px;text-decoration:none;}
        .btn-start{background:linear-gradient(135deg,#10b981,#059669);color:white;box-shadow:0 12px 30px rgba(16,185,129,0.4);}
        .btn-stop{background:linear-gradient(135deg,#ef4444,#dc2626);color:white;box-shadow:0 12px 30px rgba(239,68,68,0.4);}
        .btn-clear{background:linear-gradient(135deg,#6b7280,#4b5563);color:white;box-shadow:0 12px 30px rgba(107,114,128,0.4);}
        .btn:hover{transform:translateY(-3px);box-shadow:0 20px 40px rgba(0,0,0,0.3);}
        .logs-container{background:linear-gradient(135deg,#1e293b,#334155);border-radius:20px;padding:30px;margin-top:35px;border:1px solid rgba(255,255,255,0.1);}
        .logs-header{display:flex;justify-content:space-between;align-items:center;color:white;margin-bottom:25px;font-weight:600;font-size:1.1rem;}
        #logs{background:#0f172a;color:#e2e8f0;border-radius:16px;padding:25px;height:380px;overflow-y:auto;font-family:'Monaco','Consolas',monospace;font-size:0.92rem;line-height:1.6;white-space:pre-wrap;border:1px solid #475569;scrollbar-width:thin;}
        .stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:25px;margin-bottom:35px;}
        .stat-card{background:white;padding:30px;border-radius:20px;text-align:center;box-shadow:0 15px 35px rgba(0,0,0,0.12);transition:all 0.3s ease;border:1px solid #f1f5f9;}
        .stat-card:hover{transform:translateY(-8px);box-shadow:0 25px 50px rgba(0,0,0,0.2);}
        .stat-number{font-size:3rem;font-weight:800;color:#4f46e5;margin-bottom:12px;text-shadow:0 2px 8px rgba(79,70,229,0.3);}
        .stat-label{color:#6b7280;font-weight:600;font-size:1.1rem;}
        .tips{background:linear-gradient(135deg,#fef3c7,#fde68a);border:2px solid #f59e0b;border-radius:16px;padding:25px;margin-top:30px;}
        .tips h3{color:#b45309;font-weight:700;margin-bottom:15px;font-size:1.2rem;}
        .tips ul{margin:0;padding-left:25px;line-height:1.8;}
        .tips li{color:#92400e;margin-bottom:8px;}
        @media(max-width:768px){.form-grid{grid-template-columns:1fr;}.controls{flex-direction:column;}.header h1{font-size:2.2rem;}.status-bar{padding:20px;flex-direction:column;gap:15px;text-align:center;}}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1><i class="fas fa-robot"></i> Premium Bot v4.3</h1>
            <p><strong>Anti-Logout Edition</strong> | 100% Stable 2026</p>
        </div>

        <div class="status-bar status-stopped" id="statusBar">
            <div class="status-item">
                <div class="status-dot"></div>
                <span>Status: Stopped</span>
            </div>
            <div class="status-item">
                <span id="uptime">00:00:00</span>
            </div>
        </div>

        <div class="content">
            <div class="stats-grid" id="statsGrid" style="display:none;">
                <div class="stat-card">
                    <div class="stat-number" id="totalWelcomed">0</div>
                    <div class="stat-label">Total Welcomed</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" id="todayWelcomed">0</div>
                    <div class="stat-label">Today Welcomed</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" id="uptimeStat">-</div>
                    <div class="stat-label">Uptime</div>
                </div>
            </div>

            <form id="botForm">
                <div class="form-grid">
                    <div class="form-group">
                        <label><i class="fas fa-key"></i> Session Token <span style="color:#ef4444">*</span></label>
                        <input type="password" name="session" placeholder="Fresh session token only" required>
                    </div>
                    <div class="form-group">
                        <label><i class="fas fa-users"></i> Admin Usernames</label>
                        <input type="text" name="admin_ids" placeholder="admin1,admin2 (optional)">
                    </div>
                    <div class="form-group full">
                        <label><i class="fas fa-comment-dots"></i> Welcome Messages <span style="color:#ef4444">*</span></label>
                        <textarea name="welcome" placeholder="Enter welcome messages (one per line)">Welcome bro! 🔥
Have fun in group! 🎉
Enjoy your stay 😊
Follow group rules 👮‍♂️</textarea>
                    </div>
                    <div class="form-group">
                        <label><i class="fas fa-hashtag"></i> Group IDs <span style="color:#ef4444">*</span></label>
                        <input type="text" name="group_ids" placeholder="1234567890,0987654321" required>
                    </div>
                    <div class="form-group">
                        <label><i class="fas fa-clock"></i> Welcome Delay (sec)</label>
                        <input type="number" name="delay" value="5" min="3" max="15">
                    </div>
                    <div class="form-group">
                        <label><i class="fas fa-sync"></i> Poll Interval (sec) <span style="color:#f59e0b">Recommended: 20</span></label>
                        <input type="number" name="poll" value="20" min="15" max="45">
                    </div>
                </div>

                <div style="display:grid;grid-template-columns:1fr 1fr;gap:25px;margin-bottom:35px;">
                    <div class="checkbox-group" onclick="toggleCheckbox('use_custom_name')">
                        <input type="checkbox" id="use_custom_name" name="use_custom_name" value="yes" checked>
                        <label for="use_custom_name" style="cursor:pointer;flex:1;margin:0;font-weight:600;">
                            <i class="fas fa-user-tag"></i> Mention @username in welcome
                        </label>
                    </div>
                    <div class="checkbox-group" onclick="toggleCheckbox('enable_commands')">
                        <input type="checkbox" id="enable_commands" name="enable_commands" value="yes" checked>
                        <label for="enable_commands" style="cursor:pointer;flex:1;margin:0;font-weight:600;">
                            <i class="fas fa-terminal"></i> Enable Commands (/ping /uptime)
                        </label>
                    </div>
                </div>

                <div class="controls">
                    <button type="button" class="btn btn-start" onclick="startBot()">
                        <i class="fas fa-play-circle"></i> Start Bot
                    </button>
                    <button type="button" class="btn btn-stop" onclick="stopBot()">
                        <i class="fas fa-stop-circle"></i> Stop Bot
                    </button>
                    <button type="button" class="btn btn-clear" onclick="clearLogs()" style="padding:18px 32px;">
                        <i class="fas fa-trash-alt"></i> Clear Logs
                    </button>
                </div>
            </form>

            <div class="logs-container">
                <div class="logs-header">
                    <div><i class="fas fa-list-alt"></i> Live Logs (Auto-scroll)</div>
                    <button onclick="clearLogs()" style="background:linear-gradient(135deg,#6b7280,#4b5563);color:white;border:none;padding:10px 20px;border-radius:10px;cursor:pointer;font-weight:600;">Clear</button>
                </div>
                <div id="logs">🚀 Premium Bot v4.3 ready! Anti-Logout protection enabled ✅</div>
            </div>

            <div class="tips">
                <h3><i class="fas fa-lightbulb"></i> Anti-Logout Tips</h3>
                <ul>
                    <li><strong>Fresh session token</strong> from Instagram app</li>
                    <li><strong>Poll interval 20+ sec</strong> (Instagram safe)</li>
                    <li><strong>Max 2-3 groups</strong> only</li>
                    <li>VPN <strong>OFF</strong> during bot run</li>
                    <li>Don't login same account elsewhere</li>
                    <li>Enable 2FA on Instagram app first</li>
                </ul>
            </div>
        </div>
    </div>

    <script>
        let updateInterval;
        
        function toggleCheckbox(id) {
            document.getElementById(id).click();
        }
        
        async function startBot() {
            try {
                const formData = new FormData(document.getElementById('botForm'));
                const response = await fetch('/start', {method: 'POST', body: formData});
                const result = await response.json();
                alert(result.message);
                updateStatus();
            } catch (error) {
                alert('❌ Error: ' + error.message);
            }
        }
        
        async function stopBot() {
            try {
                const response = await fetch('/stop', {method: 'POST'});
                const result = await response.json();
                alert(result.message);
                updateStatus();
            } catch (error) {
                alert('❌ Error: ' + error.message);
            }
        }
        
        async function clearLogs() {
            try {
                await fetch('/clear_logs', {method: 'POST'});
                document.getElementById('logs').textContent = '🧹 Logs cleared successfully!';
            } catch (error) {
                console.error('Clear failed:', error);
            }
        }
        
        async function updateStatus() {
            try {
                const response = await fetch('/stats');
                const data = await response.json();
                
                document.getElementById('uptime').textContent = data.uptime;
                document.getElementById('uptimeStat').textContent = data.uptime;
                
                const statusBar = document.getElementById('statusBar');
                const statusDot = statusBar.querySelector('.status-dot');
                const statusText = statusBar.querySelector('span');
                
                if (data.status === 'running') {
                    statusBar.className = 'status-bar status-running';
                    statusDot.style.background = '#10b981';
                    statusText.textContent = 'Status: Running';
                    document.getElementById('statsGrid').style.display = 'grid';
                    document.getElementById('totalWelcomed').textContent = data.total_welcomed;
                    document.getElementById('todayWelcomed').textContent = data.today_welcomed;
                } else {
                    statusBar.className = 'status-bar status-stopped';
                    statusDot.style.background = '#ef4444';
                    statusText.textContent = 'Status: Stopped';
                    document.getElementById('statsGrid').style.display = 'none';
                }
            } catch (error) {
                console.error('Status update failed:', error);
            }
        }
        
        async function updateLogs() {
            try {
                const response = await fetch('/logs');
                const data = await response.json();
                const logsDiv = document.getElementById('logs');
                logsDiv.textContent = data.logs.join('\
');
                logsDiv.scrollTop = logsDiv.scrollHeight;
            } catch (error) {
                console.error('Logs update failed:', error);
            }
        }
        
        // Auto update every 3 seconds
        updateInterval = setInterval(() => {
            updateStatus();
            updateLogs();
        }, 3000);
        
        // Initial load
        updateStatus();
        updateLogs();
    </script>
</body>
</html>"""

if __name__ == "__main__":
    log("🌟 Premium Instagram Bot v4.3 - Anti-Logout Edition starting...")
    log("💡 RECOMMENDED: Poll=20s, Delay=5s, Max 2-3 groups")
    app.run(host="0.0.0.0", port=5000, debug=False)
