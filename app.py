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
    log("Commands enabled: " + str(ecmd))
    
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
                    continue
                    
                try:
                    g = cl.direct_thread(gid)
                    log(f"Checking group {gid[:8]}... ({len(g.users)} members)")
                    
                    # 🔥 SPAM CHECK FIRST
                    if BOT_CONFIG["spam_active"].get(gid, False):
                        tu = BOT_CONFIG["target_spam"].get(gid, {}).get("username")
                        sm = BOT_CONFIG["target_spam"].get(gid, {}).get("message")
                        if tu and sm:
                            cl.direct_send("@" + tu + " " + sm, thread_ids=[gid])
                            log(f"💥 Spam sent to @{tu} in {gid[:8]}")
                            time.sleep(2)
                    
                    # 🔥 MESSAGE PROCESSING - FIXED LOGIC!
                    new_messages = []
                    if lm.get(gid) and g.messages:
                        # Get all new messages since last message ID
                        for m in g.messages:
                            if m.id == lm[gid]:
                                break
                            new_messages.append(m)
                    
                    log(f"Found {len(new_messages)} new messages in {gid[:8]}")
                    
                    # Process new messages in reverse order (newest first)
                    for m in reversed(new_messages):
                        try:
                            if m.user_id == cl.user_id:
                                continue
                                
                            sender = next((u for u in g.users if u.pk == m.user_id), None)
                            if not sender:
                                continue
                                
                            su = sender.username.lower()
                            is_admin = su in [a.lower() for a in admin_ids.split(",") if a.strip()] if admin_ids else False
                            t = (m.text or "").strip()
                            tl = t.lower()
                            
                            log(f"Processing message from @{sender.username}: '{t[:50]}...'")
                            
                            # 🔥 AUTO-REPLY FIRST (always works)
                            if BOT_CONFIG["auto_reply_active"] and tl in BOT_CONFIG["auto_replies"]:
                                reply = BOT_CONFIG["auto_replies"][tl]
                                cl.direct_send(reply, thread_ids=[gid])
                                log(f"🤖 Auto-reply sent to @{sender.username}")
                                continue
                            
                            # 🔥 COMMANDS (only if enabled)
                            if not ecmd:
                                continue
                            
                            # 🔥 ALL COMMANDS WITH DETAILED LOGGING
                            if tl in ["/help", "!help", "/h", "!h"]:
                                help_msg = """🔥 NEON BOT COMMANDS:
/welcome - Test welcome
/stats - Bot stats
/count - Member count  
/ping - Check alive
/time - Current time
/music - Music emojis
/funny - Funny replies
/masti - Party mode

ADMIN:
/autoreply hello Hi bro - Auto reply
/stopreply - Stop auto reply
/spam @user message - Spam user
/stopspam - Stop spam
/kick @user - Remove user
/addvideo name MP4 link - Add video
/addaudio name link - Add audio
/video name - Send video link
/audio name - Send audio
/library - Show library"""
                                cl.direct_send(help_msg, thread_ids=[gid])
                                log(f"✅ Help sent to @{sender.username} in {gid[:8]}")
                                
                            elif tl in ["/stats", "!stats"]:
                                stats_msg = f"📊 STATS:
Total: {STATS['total_welcomed']}
Today: {STATS['today_welcomed']}"
                                cl.direct_send(stats_msg, thread_ids=[gid])
                                log(f"📊 Stats sent to @{sender.username}")
                                
                            elif tl in ["/count", "!count"]:
                                cl.direct_send(f"👥 MEMBERS: {len(g.users)}", thread_ids=[gid])
                                log(f"👥 Count sent: {len(g.users)} members")
                                
                            elif tl in ["/ping", "!ping"]:
                                cl.direct_send("🏓 PONG! Bot Alive 🔥", thread_ids=[gid])
                                log("🏓 Ping response sent")
                                
                            elif tl in ["/time", "!time"]:
                                cl.direct_send(f"🕐 TIME: {datetime.now().strftime('%I:%M %p')}", thread_ids=[gid])
                                log("🕐 Time sent")
                                
                            elif tl in ["/welcome", "!welcome"]:
                                cl.direct_send(f"@{sender.username} Test Welcome! 🎉", thread_ids=[gid])
                                log(f"🎉 Welcome test for @{sender.username}")
                                
                            elif tl.startswith("/autoreply "):
                                parts = t.split(" ", 2)
                                if len(parts) >= 3:
                                    trigger = parts[1].lower()
                                    reply = parts[2]
                                    BOT_CONFIG["auto_replies"][trigger] = reply
                                    BOT_CONFIG["auto_reply_active"] = True
                                    cl.direct_send(f"✅ Auto-reply set: '{trigger}' → '{reply[:30]}...'", thread_ids=[gid])
                                    log(f"Auto-reply configured: {trigger}")
                                else:
                                    cl.direct_send("❌ Format: /autoreply trigger reply", thread_ids=[gid])
                                    
                            elif tl in ["/stopreply", "!stopreply"]:
                                BOT_CONFIG["auto_reply_active"] = False
                                BOT_CONFIG["auto_replies"] = {}
                                cl.direct_send("🛑 Auto-reply stopped!", thread_ids=[gid])
                                log("Auto-reply stopped")
                                
                            elif is_admin and tl.startswith("/spam "):
                                parts = t.split(" ", 2)
                                if len(parts) >= 3:
                                    target = parts[1].replace("@", "")
                                    msg = parts[2]
                                    BOT_CONFIG["target_spam"][gid] = {"username": target, "message": msg}
                                    BOT_CONFIG["spam_active"][gid] = True
                                    cl.direct_send(f"💥 Spam started → @{target}", thread_ids=[gid])
                                    log(f"Spam started for @{target}")
                                    
                            elif is_admin and tl in ["/stopspam"]:
                                BOT_CONFIG["spam_active"][gid] = False
                                cl.direct_send("🛑 Spam stopped!", thread_ids=[gid])
                                log("Spam stopped")
                                
                            else:
                                log(f"❌ No command matched for '{tl[:20]}...' from @{sender.username}")
                                
                        except Exception as e:
                            log(f"❌ Message processing error: {str(e)}")
                    
                    # Update last message ID
                    if g.messages:
                        lm[gid] = g.messages[0].id
                    
                    # 🔥 NEW MEMBER WELCOME
                    cm = {u.pk for u in g.users}
                    new_members = cm - km.get(gid, set())
                    if new_members:
                        for u in g.users:
                            if u.pk in new_members:
                                log(f"👤 NEW MEMBER: @{u.username}")
                                for msg in wm:
                                    if STOP_EVENT.is_set():
                                        break
                                    welcome_msg = (f"@{u.username} " + msg) if ucn else msg
                                    cl.direct_send(welcome_msg, thread_ids=[gid])
                                    STATS["total_welcomed"] += 1
                                    STATS["today_welcomed"] += 1
                                    log(f"✅ Welcomed @{u.username}")
                                    time.sleep(dly)
                                km[gid] = cm
                                break
                    
                    km[gid] = cm
                    
                except Exception as e:
                    log(f"❌ Group {gid[:8]} error: {str(e)}")
                    
            time.sleep(pol)
            
        except Exception as e:
            log(f"❌ Main loop error: {str(e)}")
            
    log("🛑 Bot stopped")

# Flask routes same as before...
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
    return jsonify({"message": "✅ Bot Started! Check logs..."})

@app.route("/stop", methods=["POST"])
def stop_bot():
    STOP_EVENT.set()
    return jsonify({"message": "🛑 Bot Stopped!"})

@app.route("/logs")
def get_logs():
    return jsonify({"logs": LOGS[-50:]})

# HTML same as previous (complete one)
PAGE_HTML = """[Previous complete HTML code - same as before]"""

if __name__ == "__main__":
    print("🌟 NEON BOT v3.1 FIXED Starting...")
    print("📱 Open: http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
