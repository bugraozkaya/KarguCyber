from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
import json
from datetime import datetime
import threading

# YENİ: Firebase kütüphaneleri
import firebase_admin
from firebase_admin import credentials, messaging

# --- FİREBASE BAŞLATMA ---
try:
    # İndirdiğin gizli anahtar dosyasının adının tam olarak 'firebase-key.json' olduğundan emin ol
    cred = credentials.Certificate("firebase-key.json")
    firebase_admin.initialize_app(cred)
    print("🔥 Firebase Admin SDK Başarıyla Yüklendi! Bildirimler Aktif.")
except Exception as e:
    print(f"⚠️ Firebase başlatılamadı (firebase-key.json eksik veya hatalı olabilir): {e}")

# SENİN TELEFONUNUN EŞSİZ KİMLİĞİ (AZ ÖNCE ALDIĞIMIZ TOKEN)
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

# Gelen log verisinin yapısı
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
        # Bildirim başlığı ve içeriği
        title = f"🚨 TEHDİT: {log.threat_label}"
        body = f"IP: {log.ip_address}\nKomut: {log.command}"
        
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            token=FCM_DEVICE_TOKEN,
        )
        response = messaging.send(message)
        print(f"[🔔 BİLDİRİM GİTTİ] Hedef Cihaz: {response}")
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
        cursor.execute("INSERT OR IGNORE INTO blocked_ips (ip, banned_at) VALUES (?, ?)", 
                       (ip, datetime.now()))
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
    except Exception as e:
        return False

# --- REST API ENDPOINT'LERİ ---
@app.get("/")
def read_root():
    return {"message": "KarguCyber API Başarıyla Çalışıyor!"}

@app.get("/api/logs")
def get_logs():
    logs = get_logs_from_db()
    return {"status": "success", "total_attacks": len(logs), "data": logs}

@app.post("/api/block")
def block_ip(request: BlockRequest):
    add_ip_to_blacklist(request.ip)
    return {"status": "success", "message": f"{request.ip} adresi kara listeye alındı ve bağlantısı kesilecek!"}

@app.delete("/api/unblock/{ip}")
def unblock_ip(ip: str):
    success = remove_ip_from_blacklist(ip)
    if success:
        return {"status": "success", "message": f"{ip} adresi kara listeden çıkarıldı."}
    else:
        return {"status": "error", "message": "IP silinirken bir hata oluştu."}

# --- WEBSOCKET (CANLI YAYIN) ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

@app.websocket("/ws/logs")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text() 
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.post("/api/notify")
async def notify_new_log(log: LogNotify):
    # 1. Mobil uygulamaya canlı WebSocket verisi gönder
    await manager.broadcast(json.dumps(log.model_dump()))
    
    # 2. Arka planda Firebase Bildirimini Ateşle (API'yi yavaşlatmaması için Thread kullandık)
    threading.Thread(target=send_push_notification, args=(log,), daemon=True).start()
    
    return {"status": "success"}