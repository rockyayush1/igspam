import os
import threading
import time
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string
from instagrapi import Client

app = Flask(__name__)
BOT_THREAD = None
STOP_EVENT = threading.Event()
LOGS = []
TOKEN_FILE = "token.txt"
ADMIN_IDS = set()
STATS = {"total": 0}

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    LOGS.append(f"[{ts}] {msg}")
    print(f"[{ts}] {msg}")

def safe_login(token):
    try:
        cl = Client()
        cl.login_by_sessionid(token)
        return cl
    except:
        return None

def run_bot(token, groups, welcomes, admins, delay, poll):
    cl = safe_login(token)
    if not cl: 
        log("❌ Token invalid")
        return
    
    log(f"🚀 Bot started! Groups: {len(groups)}")
    known = {g: set() for g in groups}
    
    while not STOP_EVENT.is_set():
        for gid in groups:
            try:
                thread = cl.direct_thread(gid)
                users = {u.pk for u in thread.users}
                new = users - known[gid]
                
                for u in thread.users:
                    if u.pk in new:
                        log(f"👋 New: @{u.username}")
                        for msg in welcomes:
                            cl.direct_send(f"@{u.username} {msg}", [gid])
                            STATS["total"] += 1
                            time.sleep(delay)
                        known[gid] = users
                        break
                        
            except Exception as e:
                log(f"⚠️ Group {gid}: {str(e)[:30]}")
        
        time.sleep(poll)
    
    log("🛑 Bot stopped")

@app.route('/')
def index():
    has_token = os.path.exists(TOKEN_FILE)
    return render_template_string(HTML, has_token=has_token)

@app.route('/set_token', methods=['POST'])
def set_token():
    try:
        token = request.form.get('token', '').strip()
        if token:
            with open(TOKEN_FILE, 'w') as f:
                f.write(token)
            log("✅ Token saved")
            return jsonify({"ok": True, "msg": "✅ Token set!"})
        return jsonify({"ok": False, "msg": "❌ Empty token"})
    except:
        return jsonify({"ok": False, "msg": "❌ Error"})

@app.route('/start', methods=['POST'])
def start():
    global BOT_THREAD, STOP_EVENT, ADMIN_IDS
    
    try:
        # Token
        if not os.path.exists(TOKEN_FILE):
            return jsonify({"ok": False, "msg": "❌ No token!"})
        with open(TOKEN_FILE) as f:
            token = f.read().strip()
        
        # Groups - SUPER SAFE parsing
        ginput = request.form.get('groups', '').strip().replace(" ", "")
        groups = []
        if ',' in ginput:
            for g in ginput.split(','):
                if g.isdigit() and len(g) > 10:
                    groups.append(g)
        elif ginput.isdigit() and len(ginput) > 10:
            groups.append(ginput)
        
        # Admins
        ainput = request.form.get('admins', '').strip().replace(" ", "")
        ADMIN_IDS = set()
        if ',' in ainput:
            for a in ainput.split(','):
                if a:
                    ADMIN_IDS.add(a.lower())
        elif ainput:
            ADMIN_IDS.add(ainput.lower())
        
        # Welcome
        winput = request.form.get('welcome', 'Welcome! 🎉').strip()
        welcomes = [w.strip() for w in winput.split('') if w.strip()]
        if not welcomes:
            welcomes = ['Welcome bro! 🎉']
        
        if not groups:
            return jsonify({"ok": False, "msg": "❌ Group ID required!"})
        if not ADMIN_IDS:
            return jsonify({"ok": False, "msg": "❌ Admin username required!"})
        
        if BOT_THREAD and BOT_THREAD.is_alive():
            return jsonify({"ok": False, "msg": "⚠️ Bot running!"})
        
        STOP_EVENT.clear()
        delay = int(request.form.get('delay', 2))
        poll = int(request.form.get('poll', 5))
        
        BOT_THREAD = threading.Thread(
            target=run_bot, 
            args=(token, groups, welcomes, list(ADMIN_IDS), delay, poll),
            daemon=True
        )
        BOT_THREAD.start()
        log(f"✅ Bot ON! Groups: {len(groups)} | Admins: {len(ADMIN_IDS)}")
        return jsonify({"ok": True, "msg": f"✅ Bot started! {len(groups)} groups"})
    except Exception as e:
        return jsonify({"ok": False, "msg": f"❌ {str(e)}"})

@app.route('/stop', methods=['POST'])
def stop():
    STOP_EVENT.set()
    log("🛑 Stopping...")
    return jsonify({"ok": True, "msg": "✅ Stopping..."})

@app.route('/logs')
def logs():
    return jsonify({"logs": LOGS[-20:]})

HTML = '''
<!DOCTYPE html>
<html>
<head>
<title>IG Bot</title>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width">
<style>
* {margin:0;padding:0;box-sizing:border-box}
body {background:#000;color:#0ff;font-family:Arial;padding:20px}
.box {max-width:500px;margin:auto;background:rgba(0,0,30,0.9);padding:25px;border-radius:15px}
h1 {text-align:center;font-size:2em;margin-bottom:20px;color:#f0f}
input,textarea {width:100%;padding:12px;margin:8px 0;border-radius:8px;background:#111;color:#fff;border:1px solid #0ff;box-sizing:border-box}
button {width:100%;padding:15px;margin:10px 0;background:#0ff;color:#000;border:none;border-radius:10px;font-weight:bold;cursor:pointer}
.stop {background:#f44}
.logs {background:#111;padding:15px;border-radius:10px;height:250px;overflow:auto;font-family:mono;font-size:12px;line-height:1.4;margin-top:15px}
.status {padding:10px;border-radius:5px;margin:10px 0;text-align:center}
.ok {background:rgba(0,255,0,0.2);color:#0f0}
.error {background:rgba(255,0,0,0.2);color:#f44}
</style>
</head>
<body>
<div class="box">
<h1>🤖 IG Token Bot</h1>

<textarea id="token" rows="3" placeholder="Token paste..."></textarea>
<button onclick="setToken()">💾 Set Token</button>
<div id="status"></div>

<div id="form" style="display:{{'block' if has_token else 'none'}}">
<input id="admins" placeholder="Admin username: tumhara_username">
<input id="groups" placeholder="Group ID: 2032530394271295">
<textarea id="welcome" rows="2">नया भाई! 🎉</textarea>
<input id="delay" type="number" value="2" style="width:48%;margin-right:4%">Delay
<input id="poll" type="number" value="5" style="width:48%">Poll
<button onclick="startB()">🚀 START</button>
<button class="stop" onclick="stopB()">🛑 STOP</button>
</div>

<div class="logs" id="logbox">Ready...</div>
</div>

<script>
async function setToken(){
    let t = document.getElementById('token').value.trim();
    if(!t) return status('Token empty!','error');
    let fd = new FormData(); fd.append('token',t);
    let r = await fetch('/set_token',{method:'POST',body:fd});
    let res = await r.json();
    status(res.msg, res.ok?'ok':'error');
    if(res.ok) document.getElementById('form').style.display='block';
}

async function startB(){
    let fd = new FormData();
    fd.append('admins',document.getElementById('admins').value);
    fd.append('groups',document.getElementById('groups').value);
    fd.append('welcome',document.getElementById('welcome').value);
    fd.append('delay',document.getElementById('delay').value);
    fd.append('poll',document.getElementById('poll').value);
    let r = await fetch('/start',{method:'POST',body:fd});
    let res = await r.json();
    alert(res.msg);
}

async function stopB(){
    let r = await fetch('/stop',{method:'POST'});
    let res = await r.json();
    alert(res.msg);
}

function status(msg,t){ 
    let s = document.getElementById('status');
    s.textContent = msg; 
    s.className = 'status '+t; 
}

setInterval(async()=>{
    try{
        let r = await fetch('/logs');
        let d = await r.json();
        document.getElementById('logbox').innerHTML = d.logs.map(l=>'<div>'+l+'</div>').join('');
    }catch(e){}
},2000);
</script>
</body>
</html>
'''

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    log("🚀 Bot ready on port "+str(port))
    app.run(host='0.0.0.0', port=port, debug=False)
