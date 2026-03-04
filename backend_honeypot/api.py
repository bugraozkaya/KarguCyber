from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
import json
from datetime import datetime
import threading
import os # YENİ EKLENDİ: Karantina klasörünü okumak için

# YENİ: Firebase kütüphaneleri
import firebase_admin
from firebase_admin import credentials, messaging

# --- FİREBASE BAŞLATMA ---
try:
    cred = credentials.Certificate("firebase-key.json")
    firebase_admin.initialize_app(cred)
    print("🔥 Firebase Admin SDK Başarıyla Yüklendi! Bildirimler Aktif.")
except Exception as e:
    print(f"⚠️ Firebase başlatılamadı: {e}")

FCM_DEVICE_TOKEN = "fqlFlaYHSb-o-nv7SS3Xjg:APA91bH9CEhsCShxe34SzkLtfATKwOuvOhkBGfYVHiQPNGJ3VdVJ032mFKjpqaUjuQD822owpQeKDZYXaOfmyc9yEDbUQsFD6nhFu9KnCGE_o3kjLtHKZVM"

# API Uygulamasını Başlatıyoruz
app = FastAPI(title="KarguCyber API", description="Honeypot Log ve Kontrol Servisi")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class LogNotify(BaseModel):
    ip_address: str
    username: str
    password: str
    command: str
    timestamp: str
    threat_label: str = "UNKNOWN_THREAT"

class BlockRequest(BaseModel):
    ip: str

# --- BİLDİRİM GÖNDERME FONKSİYONU ---
def send_push_notification(log: LogNotify):
    try:
        title = f"🚨 TEHDİT: {log.threat_label}"
        body = f"IP: {log.ip_address}\nKomut: {log.command}"
        message = messaging.Message(notification=messaging.Notification(title=title, body=body), token=FCM_DEVICE_TOKEN)
        response = messaging.send(message)
    except Exception as e:
        print(f"[🔔 BİLDİRİM HATASI] {e}")

# --- VERİTABANI İŞLEMLERİ ---
def get_logs_from_db():
    try:
        conn = sqlite3.connect('kargucyber.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM attack_logs ORDER BY timestamp DESC")
        logs = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return logs
    except Exception as e:
        return {"error": str(e)}

def add_ip_to_blacklist(ip):
    try:
        conn = sqlite3.connect('kargucyber.db')
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO blocked_ips (ip, banned_at) VALUES (?, ?)", (ip, datetime.now()))
        conn.commit()
        conn.close()
        return True
    except:
        return False

def remove_ip_from_blacklist(ip):
    try:
        conn = sqlite3.connect('kargucyber.db')
        cursor = conn.cursor()
        cursor.execute("DELETE FROM blocked_ips WHERE ip = ?", (ip,))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False

# --- REST API ENDPOINT'LERİ ---
@app.get("/")
def read_root(): return {"message": "KarguCyber API Aktif!"}

@app.get("/api/logs")
def get_logs():
    logs = get_logs_from_db()
    return {"status": "success", "total_attacks": len(logs), "data": logs}

# --- YENİ EKLENEN: KARANTİNA LİSTESİNİ GETİREN ENDPOINT ---
@app.get("/api/quarantine")
def get_quarantine_files():
    quarantine_dir = "quarantine"
    # Klasör yoksa boş liste dön
    if not os.path.exists(quarantine_dir):
        return {"status": "success", "total": 0, "data": []}
    
    files_data = []
    # Klasördeki tüm dosyaları tara
    for filename in os.listdir(quarantine_dir):
        if filename.endswith(".vir"):
            filepath = os.path.join(quarantine_dir, filename)
            size_kb = os.path.getsize(filepath) / 1024 # Boyutu KB cinsine çevir
            
            # malware_127.0.0.1_20260304_123456.vir formatından IP'yi ayıkla
            parts = filename.split('_')
            ip = parts[1] if len(parts) > 1 else "Bilinmiyor"
            
            files_data.append({
                "filename": filename,
                "ip_source": ip,
                "size": f"{size_kb:.1f} KB"
            })
    
    files_data.reverse() # En son indirilen virüs en üstte görünsün
    return {"status": "success", "total": len(files_data), "data": files_data}

@app.post("/api/block")
def block_ip(request: BlockRequest):
    add_ip_to_blacklist(request.ip)
    return {"status": "success"}

@app.delete("/api/unblock/{ip}")
def unblock_ip(ip: str):
    success = remove_ip_from_blacklist(ip)
    return {"status": "success"} if success else {"status": "error"}

# --- WEBSOCKET ---
class ConnectionManager:
    def __init__(self): self.active_connections: list[WebSocket] = []
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections: self.active_connections.remove(websocket)
    async def broadcast(self, message: str):
        for connection in self.active_connections: await connection.send_text(message)

manager = ConnectionManager()

@app.websocket("/ws/logs")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True: await websocket.receive_text() 
    except WebSocketDisconnect: manager.disconnect(websocket)

@app.post("/api/notify")
async def notify_new_log(log: LogNotify):
    await manager.broadcast(json.dumps(log.model_dump()))
    threading.Thread(target=send_push_notification, args=(log,), daemon=True).start()
    return {"status": "success"}