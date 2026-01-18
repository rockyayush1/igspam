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

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    lm = f"[{ts}] {msg}"
    LOGS.append(lm)
    print(lm)

MUSIC_EMOJIS = ["ðŸŽµ","ðŸŽ¶","ðŸŽ¸","ðŸŽ¹","ðŸŽ¤","ðŸŽ§"]
FUNNY = ["Hahaha ðŸ¤£","LOL ðŸ¤£","Mast ðŸ˜†","Pagal ðŸ¤ª","King ðŸ‘‘ðŸ˜‚"]
MASTI = ["Party ðŸŽ‰","Masti ðŸ¥³","Dhamaal ðŸ’ƒ","Full ON ðŸ”¥","Enjoy ðŸŽŠ"]

# ================= BOT =================
def run_bot(session_token, wm, gids, dly, pol, ucn, ecmd, admin_ids):
    cl = Client()
    try:
        cl.login_by_sessionid(session_token)
        me = cl.account_info().username
        log(f"Session login success: @{me}")
    except Exception as e:
        log("Session login failed: " + str(e))
        return

    km = {}
    lm = {}

    for gid in gids:
        try:
            g = cl.direct_thread(gid)
            km[gid] = {u.pk for u in g.users}
            lm[gid] = g.messages[0].id if g.messages else None
            BOT_CONFIG["spam_active"][gid] = False
            log("Group ready: " + gid)
        except:
            km[gid] = set()
            lm[gid] = None

    while not STOP_EVENT.is_set():
        for gid in gids:
            if STOP_EVENT.is_set():
                break
            try:
                g = cl.direct_thread(gid)

                # -------- SPAM --------
                if BOT_CONFIG["spam_active"].get(gid):
                    t = BOT_CONFIG["target_spam"].get(gid)
                    if t:
                        cl.direct_send(
                            "@" + t["username"] + " " + t["message"],
                            thread_ids=[gid]
                        )
                        log("Spam sent")
                        time.sleep(2)

                # -------- COMMANDS --------
                if ecmd or BOT_CONFIG["auto_reply_active"]:
                    new_msgs = []
                    if lm[gid]:
                        for m in g.messages:
                            if m.id == lm[gid]:
                                break
                            new_msgs.append(m)

                    for m in reversed(new_msgs):
                        if m.user_id == cl.user_id:
                            continue

                        sender = next((u for u in g.users if u.pk == m.user_id), None)
                        if not sender:
                            continue

                        su = sender.username.lower()
                        ia = su in [a.lower() for a in admin_ids] if admin_ids else True
                        t = (m.text or "").strip()
                        tl = t.lower()

                        if BOT_CONFIG["auto_reply_active"] and tl in BOT_CONFIG["auto_replies"]:
                            cl.direct_send(BOT_CONFIG["auto_replies"][tl], thread_ids=[gid])

                        if not ecmd:
                            continue

                        if tl in ["/help","!help"]:
                            cl.direct_send(
                                "COMMANDS:\n"
                                "/help /ping /time /about\n"
                                "/stats /count /welcome\n"
                                "/autoreply key msg\n/stopreply\n"
                                "/music /funny /masti\n"
                                "/spam @user msg\n/stopspam",
                                thread_ids=[gid]
                            )

                        elif tl in ["/ping","!ping"]:
                            cl.direct_send("Pong! âœ…", thread_ids=[gid])

                        elif tl in ["/time","!time"]:
                            cl.direct_send(datetime.now().strftime("%I:%M %p"), thread_ids=[gid])

                        elif tl in ["/about","!about"]:
                            cl.direct_send("Instagram Neon Bot v3.0 (SESSION)", thread_ids=[gid])

                        elif tl.startswith("/autoreply "):
                            p = t.split(" ",2)
                            if len(p)==3:
                                BOT_CONFIG["auto_replies"][p[1].lower()] = p[2]
                                BOT_CONFIG["auto_reply_active"] = True

                        elif tl in ["/stopreply","!stopreply"]:
                            BOT_CONFIG["auto_reply_active"] = False
                            BOT_CONFIG["auto_replies"] = {}

                        elif tl in ["/music","!music"]:
                            cl.direct_send(" ".join(random.choices(MUSIC_EMOJIS,k=5)), thread_ids=[gid])

                        elif tl in ["/funny","!funny"]:
                            cl.direct_send(random.choice(FUNNY), thread_ids=[gid])

                        elif tl in ["/masti","!masti"]:
                            cl.direct_send(random.choice(MASTI), thread_ids=[gid])

                        elif ia and tl.startswith("/spam "):
                            p = t.split(" ",2)
                            if len(p)==3:
                                BOT_CONFIG["target_spam"][gid] = {
                                    "username": p[1].replace("@",""),
                                    "message": p[2]
                                }
                                BOT_CONFIG["spam_active"][gid] = True

                        elif ia and tl in ["/stopspam","!stopspam"]:
                            BOT_CONFIG["spam_active"][gid] = False

                    if g.messages:
                        lm[gid] = g.messages[0].id

                # -------- WELCOME --------
                cm = {u.pk for u in g.users}
                new_users = cm - km[gid]

                for u in g.users:
                    if u.pk in new_users:
                        for msg in wm:
                            final = f"@{u.username} {msg}" if ucn else msg
                            cl.direct_send(final, thread_ids=[gid])
                            STATS["total_welcomed"] += 1
                            STATS["today_welcomed"] += 1
                            time.sleep(dly)

                km[gid] = cm

            except:
                pass

        time.sleep(pol)

    log("BOT STOPPED")

# ================= FLASK =================
@app.route("/")
def index():
    return render_template_string(PAGE_HTML)

@app.route("/start", methods=["POST"])
def start():
    global BOT_THREAD
    if BOT_THREAD and BOT_THREAD.is_alive():
        return jsonify({"message":"Already running"})

    token = request.form.get("session")
    welcome = [x.strip() for x in request.form.get("welcome","").splitlines() if x.strip()]
    gids = [x.strip() for x in request.form.get("group_ids","").split(",") if x.strip()]
    admins = [x.strip() for x in request.form.get("admin_ids","").split(",") if x.strip()]

    if not token or not welcome or not gids:
        return jsonify({"message":"Fill all fields"})

    STOP_EVENT.clear()
    BOT_THREAD = threading.Thread(
        target=run_bot,
        args=(
            token,
            welcome,
            gids,
            int(request.form.get("delay",3)),
            int(request.form.get("poll",5)),
            request.form.get("use_custom_name")=="yes",
            request.form.get("enable_commands")=="yes",
            admins
        ),
        daemon=True
    )
    BOT_THREAD.start()
    return jsonify({"message":"Started!"})

@app.route("/stop", methods=["POST"])
def stop():
    STOP_EVENT.set()
    return jsonify({"message":"Stopped!"})

@app.route("/logs")
def logs():
    return jsonify({"logs": LOGS[-200:]})

# ================= ORIGINAL NEON UI =================
PAGE_HTML = """<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>NEON BOT</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:Arial,sans-serif;min-height:100vh;background:#000;color:#fff;padding:15px}
body::before{content:'';position:fixed;inset:0;background:url('https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=1920&q=80') center/cover;opacity:.4;z-index:-2}
body::after{content:'';position:fixed;inset:0;background:radial-gradient(circle at 20% 50%,rgba(0,200,255,.2),transparent 60%),radial-gradient(circle at 80% 80%,rgba(255,0,150,.2),transparent 60%);z-index:-1}
.c{max-width:700px;margin:auto;background:rgba(10,10,30,.6);border-radius:20px;padding:25px;border:2px solid rgba(0,255,255,.5);box-shadow:0 0 30px rgba(0,255,255,.4)}
h1{text-align:center;font-size:50px;font-weight:900;margin-bottom:25px;background:linear-gradient(90deg,#0ff,#f0f,#ff0);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
label{display:block;margin-top:12px;font-size:13px;font-weight:600}
input,textarea,select{width:100%;padding:10px;border-radius:10px;background:rgba(0,20,40,.6);color:#fff;border:2px solid rgba(0,255,255,.4)}
.bc{display:flex;gap:15px;justify-content:center;margin-top:25px}
button{padding:12px 35px;border:none;border-radius:25px;font-size:16px;font-weight:700;cursor:pointer}
.bs{background:linear-gradient(135deg,#0ff,#00a8cc);color:#000}
.bp{background:linear-gradient(135deg,#f0f,#c00);color:#fff}
.lb{background:#000;border:2px solid #0ff;border-radius:15px;padding:15px;height:200px;overflow:auto;font-family:monospace;margin-top:20px}
</style></head>
<body>
<div class="c">
<h1>NEON BOT</h1>
<form id="f">
<label>SESSION TOKEN</label><input name="session">
<label>ADMINS</label><input name="admin_ids">
<label>WELCOME</label><textarea name="welcome"></textarea>
<label>MENTION?</label><select name="use_custom_name"><option value="yes">Yes</option></select>
<label>COMMANDS?</label><select name="enable_commands"><option value="yes">Yes</option></select>
<label>GROUP IDS</label><input name="group_ids">
<label>DELAY</label><input name="delay" value="3">
<label>POLL</label><input name="poll" value="5">
<div class="bc">
<button type="button" class="bs" onclick="start()">START</button>
<button type="button" class="bp" onclick="stop()">STOP</button>
</div>
</form>
<div class="lb" id="l">Waiting...</div>
</div>
<script>
async function start(){
 let r=await fetch('/start',{method:'POST',body:new FormData(f)});
 alert((await r.json()).message)
}
async function stop(){
 let r=await fetch('/stop',{method:'POST'});
 alert((await r.json()).message)
}
setInterval(async()=>{
 let r=await fetch('/logs');
 let d=await r.json();
 l.innerText=d.logs.join("\\n");
},2000)
</script>
</body></html>"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
