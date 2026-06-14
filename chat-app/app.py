import eventlet
eventlet.monkey_patch()
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, join_room, emit
from flask_sqlalchemy import SQLAlchemy
import os
import json
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'anas_chat_437_ultra'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['STICKERS_FOLDER'] = 'static/stickers' # مجلد حزم الملصقات المحلية الجديد
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///anas_chat_v14.db'

ADMIN_PASSWORD = "anas_admin_2026"

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# التأكد من وجود المجلدات المطلوبة
if not os.path.exists(app.config['UPLOAD_FOLDER']): 
    os.makedirs(app.config['UPLOAD_FOLDER'])
if not os.path.exists(app.config['STICKERS_FOLDER']): 
    os.makedirs(app.config['STICKERS_FOLDER'])

class SiteSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    global_password = db.Column(db.String(100), default="anas2026")

class Room(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(50))

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room = db.Column(db.String(50))
    username = db.Column(db.String(50))
    content = db.Column(db.String(2000))
    reply_to = db.Column(db.String(1000))
    file = db.Column(db.String(200))
    file_type = db.Column(db.String(20))
    time = db.Column(db.String(20))
    reactions = db.Column(db.String(2000), default="{}")

class BannedDevice(db.Model): 
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(150), unique=True)

class BannedIP(db.Model): 
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(100), unique=True)

class VisitorLog(db.Model): 
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    ip_address = db.Column(db.String(100))
    device_id = db.Column(db.String(150))
    room_name = db.Column(db.String(50))
    last_visit = db.Column(db.String(50))

with app.app_context(): 
    db.create_all()
    if not SiteSetting.query.first():
        db.session.add(SiteSetting(global_password="anas2026"))
        db.session.commit()

active_sessions = {}

def get_ip(): 
    return request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0]

@app.before_request
def check_global_ip_ban():
    if BannedIP.query.filter_by(ip_address=get_ip()).first():
        return "<h1>أنت محظور نهائياً من دخول Anas Chat 437.</h1>", 403

@app.route('/admin_gate')
def admin_gate():
    p = request.args.get('pass')
    if p == ADMIN_PASSWORD:
        online = [v for v in active_sessions.values()]
        banned_devs = BannedDevice.query.all()
        banned_ips = BannedIP.query.all()
        history = VisitorLog.query.order_by(VisitorLog.id.desc()).all()
        rooms = Room.query.all()
        config = SiteSetting.query.first()
        global_pass = config.global_password if config else "anas2026"
        return render_template('admin.html', online=online, banned_devs=banned_devs, banned_ips=banned_ips, history=history, rooms=rooms, global_pass=global_pass)
    return "خطأ في كلمة السر", 401

@app.route('/api/check_global_pass', methods=['POST'])
def check_global_pass():
    data = request.json
    config = SiteSetting.query.first()
    current_pass = config.global_password if config else "anas2026"
    if data.get('password') == current_pass:
        return jsonify({"status": "success"})
    return jsonify({"status": "wrong"}), 401

@app.route('/api/admin/update_global_pass', methods=['POST'])
def admin_update_global_pass():
    data = request.json
    if data.get('pass') == ADMIN_PASSWORD:
        new_pass = data.get('new_global_pass').strip()
        if not new_pass: return jsonify({"status": "error", "msg": "كلمة السر فارغة"}), 400
        config = SiteSetting.query.first()
        if not config:
            config = SiteSetting(global_password=new_pass)
            db.session.add(config)
        else:
            config.global_password = new_pass
        db.session.commit()
        return jsonify({"status": "success"})
    return jsonify({"status": "unauthorized"}), 401

@app.route('/api/admin/delete_room', methods=['POST'])
def admin_delete_room():
    data = request.json
    if data.get('pass') == ADMIN_PASSWORD:
        room_id = data.get('room_id')
        room = Room.query.get(room_id)
        if room:
            Message.query.filter_by(room=room.name).delete()
            db.session.delete(room)
            db.session.commit()
            return jsonify({"status": "success"})
    return jsonify({"status": "unauthorized"}), 401

@app.route('/api/admin/delete_log', methods=['POST'])
def admin_delete_log():
    data = request.json
    if data.get('pass') == ADMIN_PASSWORD:
        log_id = data.get('log_id')
        if log_id == "all":
            VisitorLog.query.delete()
        else:
            log = VisitorLog.query.get(log_id)
            if log: db.session.delete(log)
        db.session.commit()
        return jsonify({"status": "success"})
    return jsonify({"status": "unauthorized"}), 401

@app.route('/api/ban', methods=['POST'])
def api_ban():
    data = request.json
    if data.get('pass') == ADMIN_PASSWORD:
        dev_id = data.get('device_id')
        ip = data.get('ip')
        if dev_id and not BannedDevice.query.filter_by(device_id=dev_id).first():
            db.session.add(BannedDevice(device_id=dev_id))
        if ip and not BannedIP.query.filter_by(ip_address=ip).first():
            db.session.add(BannedIP(ip_address=ip))
        db.session.commit()
        for sid, session in list(active_sessions.items()):
            if (dev_id and session['device_id'] == dev_id) or (ip and session['ip'] == ip):
                socketio.emit('kick_banned', {}, to=sid)
        return jsonify({"status": "success"})
    return jsonify({"status": "unauthorized"}), 401

@app.route('/api/unban', methods=['POST'])
def api_unban():
    data = request.json
    if data.get('pass') == ADMIN_PASSWORD:
        dev_id = data.get('device_id')
        ip = data.get('ip')
        if dev_id:
            ban_entry = BannedDevice.query.filter_by(device_id=dev_id).first()
            if ban_entry: db.session.delete(ban_entry)
        if ip:
            ban_entry = BannedIP.query.filter_by(ip_address=ip).first()
            if ban_entry: db.session.delete(ban_entry)
        db.session.commit()
        return jsonify({"status": "success"})
    return jsonify({"status": "unauthorized"}), 401

@app.route('/')
def home(): 
    return render_template('index.html')

# مسار جديد لجلب الملصقات المحلية تلقائياً
@app.route('/api/get_stickers')
def get_stickers():
    if os.path.exists(app.config['STICKERS_FOLDER']):
        stickers = [f for f in os.listdir(app.config['STICKERS_FOLDER']) if f.lower().endswith(('.png', '.gif', '.webp', '.jpg', '.jpeg'))]
        return jsonify(stickers)
    return jsonify([])

@app.route('/create_room', methods=['POST'])
def create_room():
    data = request.json
    if Room.query.filter_by(name=data['name']).first(): 
        return jsonify({"msg": "اسم الغرفة موجود مسبقاً!"})
    db.session.add(Room(name=data['name'], password=data['password']))
    db.session.commit()
    return jsonify({"msg": "تم الإنشاء بنجاح ✅"})

@app.route('/upload_chunk', methods=['POST'])
def upload_chunk():
    file = request.files['chunk']
    fname = request.form['filename']
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], fname)
    with open(filepath, "ab") as f: 
        f.write(file.read())
    return jsonify({"status": "success"})

@socketio.on('join')
def on_join(data):
    dev_id = data.get('device_id')
    ip = get_ip()
    if BannedDevice.query.filter_by(device_id=dev_id).first() or BannedIP.query.filter_by(ip_address=ip).first():
        emit('join_status', 'banned')
        return

    r = Room.query.filter_by(name=data['room'], password=data['password']).first()
    if r:
        join_room(data['room'])
        active_sessions[request.sid] = {'user': data['username'], 'room': data['room'], 'ip': ip, 'device_id': dev_id}
        
        log = VisitorLog.query.filter_by(device_id=dev_id, room_name=data['room']).first()
        if not log:
            db.session.add(VisitorLog(username=data['username'], ip_address=ip, device_id=dev_id, room_name=data['room'], last_visit=datetime.now().strftime("%Y-%m-%d %H:%M")))
        else:
            log.username = data['username']
            log.ip_address = ip
            log.last_visit = datetime.now().strftime("%Y-%m-%d %H:%M")
        db.session.commit()

        emit('join_status', 'success')
        users = [s['user'] for s in active_sessions.values() if s['room'] == data['room']]
        emit('update_users', users, to=data['room'])
        
        for m in Message.query.filter_by(room=data['room']).all():
            emit('message', {"id": m.id, "username": m.username, "msg": m.content, "reply_to": m.reply_to, "file": m.file, "file_type": m.file_type, "time": m.time, "reactions": m.reactions})
    else: 
        emit('join_status', 'error')

@socketio.on('disconnect')
def on_disconnect():
    s = active_sessions.pop(request.sid, None)
    if s:
        room = s['room']
        users = [ss['user'] for ss in active_sessions.values() if ss['room'] == room]
        emit('update_users', users, to=room)

@socketio.on('message')
def handle_msg(data):
    session_data = active_sessions.get(request.sid)
    if not session_data or BannedDevice.query.filter_by(device_id=session_data['device_id']).first() or BannedIP.query.filter_by(ip_address=session_data['ip']).first():
        return

    ts = datetime.now().strftime("%I:%M %p")
    ft = None
    if data.get('file_type') == 'sticker':
        ft = 'sticker'
    elif data.get('file'):
        ext = data['file'].split('.')[-1].lower()
        if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp']: ft = 'image'
        elif ext in ['mp4', 'webm', 'ogg']: ft = 'video'
        elif ext in ['mp3', 'wav', 'weba']: ft = 'audio'
        else: ft = 'file'

    new_m = Message(room=data['room'], username=data['username'], content=data.get('msg'), reply_to=data.get('reply_to'), file=data.get('file'), file_type=ft, time=ts, reactions="{}")
    db.session.add(new_m)
    db.session.commit()
    
    emit('message', {"id": new_m.id, "username": data['username'], "msg": data.get('msg'), "reply_to": data.get('reply_to'), "file": data.get('file'), "file_type": ft, "time": ts, "reactions": "{}"}, to=data['room'])

@socketio.on('delete_message')
def delete_msg(data):
    m = Message.query.get(data['id'])
    session_data = active_sessions.get(request.sid)
    if m and session_data and m.username == session_data['user']:
        room = m.room
        db.session.delete(m)
        db.session.commit()
        emit('message_deleted', {'id': data['id']}, to=room)

@socketio.on('send_reaction')
def handle_reaction(data):
    session_data = active_sessions.get(request.sid)
    if not session_data: return

    msg_id = data.get('msg_id')
    emoji = data.get('emoji')
    username = session_data['user']

    m = Message.query.get(msg_id)
    if m:
        try:
            rx = json.loads(m.reactions or "{}")
        except:
            rx = {}
        
        if emoji not in rx:
            rx[emoji] = []
            
        if username in rx[emoji]:
            rx[emoji].remove(username)
            if not rx[emoji]:
                del rx[emoji]
        else:
            rx[emoji].append(username)
            
        m.reactions = json.dumps(rx)
        db.session.commit()
        emit('update_reaction', {'msg_id': msg_id, 'reactions': rx}, to=m.room)

if __name__ == '__main__': 
    socketio.run(app, host='0.0.0.0', port=10000)
