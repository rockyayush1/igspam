import os
import threading
import time
import random
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string
from instagrapi import Client

app = Flask(__name__)
BOT_THREAD = None
STOP_EVENT = threading.Event()
LOGS = []
TOKEN_FILE = "token.txt"
STATS = {"total_welcomed": 0, "today_welcomed": 0}
ADMIN_IDS = []  # Global admin list

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    lm = f"[{ts}] {msg}"
    LOGS.append(lm)
    print(lm)

def load_token_session(token):
    try:
        cl = Client()
        cl.set_uuids({
            "phone_uuid": "12345678-1234-1234-1234-123456789abc",
            "device_uuid": "12345678-1234-1234-1234-123456789abc"
        })
        cl.login_by_sessionid(token)
        log("✅ Token login successful!")
        return cl
    except Exception as e:
        log(f"❌ Token login failed: {str(e)[:50]}")
        return None

def is_admin(username):
    """Check if user is admin"""
    return username.lower() in [admin.lower() for admin in ADMIN_IDS]

def run_bot(token, welcome_msgs, group_ids, delay, poll_interval):
    global ADMIN_IDS
    cl = load_token_session(token)
    if not cl:
        log("❌ Cannot start - invalid token")
        return
    
    log("🚀 Bot started with admin protection!")
    log(f"👑 Admins: {ADMIN_IDS}")
    known_members = {gid: set() for gid in group_ids}
    last_msgs = {gid: None for gid in group_ids}
    
    while not STOP_EVENT.is_set():
        for gid in group_ids:
            if STOP_EVENT.is_set():
                break
            try:
                thread = cl.direct_thread(gid)
                current_members = {user.pk for user in thread.users}
                new_members = current_members - known_members[gid]
                
                # Welcome new members
                for user in thread.users:
                    if user.pk in new_members:
                        log(f"👋 New member: @{user.username}")
                        for msg in welcome_msgs:
                            full_msg = f"@{user.username} {msg}"
                            cl.direct_send(full_msg, thread_ids=[gid])
                            STATS["total_welcomed"] += 1
                            time.sleep(delay)
                        known_members[gid] = current_members
                        break
                
                # Check commands (only last 10 messages)
                if last_msgs[gid]:
                    messages = thread.messages[-10:]
                    for msg in reversed(messages):
                        if msg.id == last_msgs[gid]:
                            break
                        
                        if msg.user_id == cl.user_id:
                            continue
                            
                        sender = next((u for u in thread.users if u.pk == msg.user_id), None)
                        if not sender:
                            continue
                            
                        text = msg.text.strip().lower() if msg.text else ""
                        sender_name = sender.username.lower()
                        
                        # Admin only commands
                        if is_admin(sender_name):
                            if text in ["/stats", "!stats"]:
                                stats_msg = f"📊 Total: {STATS['total_welcomed']} | Today: {STATS['today_welcomed']}"
                                cl.direct_send(stats_msg, [gid])
                            elif text.startswith("/kick "):
                                target = text.split(" ", 1)[1].replace("@", "").strip()
                                target_user = next((u for u in thread.users if u.username.lower() == target.lower()), None)
                                if target_user:
                                    cl.direct_thread_remove_user(gid, target_user.pk)
                                    cl.direct_send(f"👢 @{target_user.username} kicked by admin!", [gid])
                            elif text.startswith("/spam "):
                                cl.direct_send("🔥 Spam mode ON (admin only)!", [gid])
                            elif text == "/help":
                                help_msg = """🔥 ADMIN COMMANDS:
/stats - Bot stats
/kick @username - Remove user  
/spam - Spam mode
/help - This help"""
                                cl.direct_send(help_msg, [gid])
                        
                        # Everyone commands
                        elif text in ["/ping", "/about"]:
                            cl.direct_send("🤖 Bot active! Commands only for admins 👑", [gid])
                
                last_msgs[gid] = thread.messages[0].id if thread.messages else None
                
            except Exception as e:
                log(f"⚠️ Group {gid} error: {str(e)[:30]}")
        
        if not STOP_EVENT.is_set():
            time.sleep(poll_interval)
    
    log("🛑 Bot stopped completely!")

@app.route('/')
def index():
    token_exists = os.path.exists(TOKEN_FILE)
    return render_template_string(HTML_TEMPLATE, token_exists=token_exists)

@app.route('/set_token', methods=['POST'])
def set_token():
    try:
        token = request.form.get('token', '').strip()
        if not token:
            return jsonify({'success': False, 'message': '❌ Token cannot be empty!'})
        
        with open(TOKEN_FILE, 'w') as f:
            f.write(token)
        log("💾 Token saved successfully!")
        return jsonify({'success': True, 'message': '✅ Token set successfully!'})
    except Exception as e:
        log(f"❌ Token save error: {e}")
        return jsonify({'success': False, 'message': f'❌ Error: {str(e)}'})

@app.route('/start', methods=['POST'])
def start_bot():
    global BOT_THREAD, STOP_EVENT, ADMIN_IDS
    
    try:
        if not os.path.exists(TOKEN_FILE):
            return jsonify({'success': False, 'message': '❌ No token found! Set token first.'})
        
        with open(TOKEN_FILE, 'r') as f:
            token = f.read().strip()
        
        # Get admin IDs from form
        admin_input = request.form.get('admin_ids', '').strip()
        global ADMIN_IDS
        ADMIN_IDS = [admin.strip() for admin in admin_input.split(',') if admin.strip()]
        
        group_ids = [g.strip() for g in request.form.get('group_ids', '').split(',') if g.strip()]
        welcome_msgs = [m.strip() for m in request.form.get('welcome', '').split('
') if m.strip()]
        
        if not group_ids:
            return jsonify({'success': False, 'message': '❌ Enter Group IDs'})
        if not welcome_msgs:
            return jsonify({'success': False, 'message': '❌ Enter welcome messages'})
        if not ADMIN_IDS:
            return jsonify({'success': False, 'message': '❌ Enter Admin IDs 👑'})
        
        if BOT_THREAD and BOT_THREAD.is_alive():
            return jsonify({'success': False, 'message': '⚠️ Bot already running!'})
        
        STOP_EVENT.clear()
        delay = int(request.form.get('delay', 2))
        poll = int(request.form.get('poll', 5))
        
        BOT_THREAD = threading.Thread(
            target=run_bot,
            args=(token, welcome_msgs, group_ids, delay, poll),
            daemon=True
        )
        BOT_THREAD.start()
        log(f"🚀 Bot started! Admins: {ADMIN_IDS}")
        return jsonify({'success': True, 'message': f'🚀 Bot started! Admins: {", ".join(ADMIN_IDS)}'})
    
    except Exception as e:
        log(f"❌ Start bot error: {e}")
        return jsonify({'success': False, 'message': f'❌ Error: {str(e)}'})

@app.route('/stop', methods=['POST'])
def stop_bot():
    global STOP_EVENT
    STOP_EVENT.set()
    log("🛑 Stop signal sent!")
    return jsonify({'success': True, 'message': '✅ Bot stopping...'})

@app.route('/logs')
def get_logs():
    return jsonify({'logs': LOGS[-15:]})

# Updated HTML with Admin ID field
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Instagram Admin Bot</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            background: linear-gradient(135deg, #0c0c1a 0%, #1a0033 100%); 
            color: #00ffff; 
            font-family: 'Segoe UI', Arial, sans-serif; 
            min-height: 100vh; 
            padding: 20px;
        }
        .container { max-width: 700px; margin: 0 auto; background: rgba(0,0,30,0.95); padding: 30px; border-radius: 20px; border: 2px solid rgba(0,255,255,0.3); }
        h1 { text-align: center; font-size: 2.5em; background: linear-gradient(45deg, #00ffff, #ff00ff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 30px; }
        .admin-section { background: rgba(255,215,0,0.1); padding: 20px; border-radius: 15px; border: 2px solid rgba(255,215,0,0.4); margin-bottom: 20px; }
        .token-section { background: rgba(0,255,0,0.1); padding: 20px; border-radius: 15px; border: 2px solid rgba(0,255,0,0.3); margin-bottom: 20px; }
        input, textarea, select { width: 100%; padding: 15px; margin: 10px 0; border-radius: 10px; background: rgba(0,0,50,0.8); color: #00ffff; border: 2px solid rgba(0,255,255,0.4); font-size: 14px; }
        input:focus, textarea:focus { outline: none; border-color: #00ffff; box-shadow: 0 0 15px rgba(0,255,255,0.3); }
        button { padding: 15px 30px; background: linear-gradient(45deg, #00ffff, #00bfff); color: #000; border: none; border-radius: 10px; cursor: pointer; font-weight: bold; font-size: 16px; margin: 10px 5px; transition: all 0.3s; }
        button:hover { transform: translateY(-2px); box-shadow: 0 10px 25px rgba(0,255,255,0.4); }
        .stop-btn { background: linear-gradient(45deg, #ff4444, #cc0000); }
        .logs { background: rgba(0,0,0,0.7); border: 2px solid rgba(0,255,255,0.3); border-radius: 10px; padding: 20px; height: 300px; overflow-y: auto; font-family: monospace; font-size: 13px; line-height: 1.5; margin-top: 20px; }
        .status { padding: 10px; border-radius: 8px; margin: 10px 0; text-align: center; font-weight: bold; }
        .success { background: rgba(0,255,0,0.2); color: #00ff00; border: 1px solid #00ff00; }
        .error { background: rgba(255,0,0,0.2); color: #ff4444; border: 1px solid #ff4444; }
        @media (max-width: 768px) { .container { padding: 20px; } h1 { font-size: 2em; } }
    </style>
</head>
<body>
    <div class="container">
        <h1>👑 Instagram Admin Bot</h1>
        
        <div class="token-section">
            <h3>🔑 Token Setup</h3>
            <textarea id="tokenInput" rows="4" placeholder="Instagram session token paste करें..."></textarea>
            <button onclick="setToken()">💾 Set Token</button>
            <div id="tokenStatus" class="status"></div>
        </div>

        <form id="botForm" style="display: {{ 'block' if token_exists else 'none' }};">
            <h3>🤖 Bot Settings</h3>
            
            <div class="admin-section">
                <h4>👑 Admin IDs (अलग-अलग comma से)</h4>
                <input type="text" id="adminIds" placeholder="admin1, admin2, yourusername">
            </div>
            
            <input type="text" id="groupIds" placeholder="Group IDs: 123456789,987654321">
            <textarea id="welcomeMsg" rows="3" placeholder="Welcome messages">नया भाई आ गया! 🎉
ग्रुप में स्वागत! 🔥</textarea>
            
            <div style="display: flex; gap: 10px;">
                <input type="number" id="delay" value="2" min="1" max="10" style="flex: 1;"> Delay
                <input type="number" id="poll" value="5" min="2" max="30" style="flex: 1;"> Poll
            </div>
            
            <div style="display: flex; gap: 10px;">
                <button onclick="startBot()" style="flex: 1;">🚀 Start Bot</button>
                <button class="stop-btn" onclick="stopBot()" style="flex: 1;">🛑 Stop Bot</button>
            </div>
        </form>

        <div class="logs" id="logsBox">Admin IDs डालो - सिर्फ admins commands चला सकेंगे!</div>
    </div>

    <script>
        async function setToken() {
            const token = document.getElementById('tokenInput').value.trim();
            if (!token) return showStatus('Token empty!', 'error');
            
            const formData = new FormData();
            formData.append('token', token);
            
            try {
                const response = await fetch('/set_token', { method: 'POST', body: formData });
                const result = await response.json();
                showStatus(result.message, result.success ? 'success' : 'error');
                if (result.success) document.getElementById('botForm').style.display = 'block';
            } catch (e) { showStatus('Network error!', 'error'); }
        }
        
        async function startBot() {
            const formData = new FormData();
            formData.append('admin_ids', document.getElementById('adminIds').value);
            formData.append('group_ids', document.getElementById('groupIds').value);
            formData.append('welcome', document.getElementById('welcomeMsg').value);
            formData.append('delay', document.getElementById('delay').value);
            formData.append('poll', document.getElementById('poll').value);
            
            try {
                const response = await fetch('/start', { method: 'POST', body: formData });
                const result = await response.json();
                alert(result.message);
            } catch (e) { alert('Error: ' + e.message); }
        }
        
        async function stopBot() {
            try {
                const response = await fetch('/stop', { method: 'POST' });
                const result = await response.json();
                alert(result.message);
            } catch (e) { alert('Error: ' + e.message); }
        }
        
        function showStatus(msg, type) {
            document.getElementById('tokenStatus').textContent = msg;
            document.getElementById('tokenStatus').className = 'status ' + type;
        }
        
        setInterval(async () => {
            try {
                const r = await fetch('/logs');
                const data = await r.json();
                document.getElementById('logsBox').innerHTML = data.logs.map(l => `<div>${l}</div>`).join('');
                document.getElementById('logsBox').scrollTop = document.getElementById('logsBox').scrollHeight;
            } catch (e) {}
        }, 2000);
    </script>
</body>
</html>
'''

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    log("🚀 Admin Bot starting on port " + str(port))
    app.run(host='0.0.0.0', port=port, debug=False)
