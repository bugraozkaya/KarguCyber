from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
import json
from datetime import datetime

# API Uygulamasını Başlatıyoruz
app = FastAPI(title="KarguCyber API", description="Honeypot Log ve Kontrol Servisi")

# CORS ayarlarını ekliyoruz
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

# IP Engelleme isteği için veri modeli
class BlockRequest(BaseModel):
    ip: str

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

# IP'yi kara listeye ekleyen fonksiyon
def add_ip_to_blacklist(ip):
    try:
        conn = sqlite3.connect('kargucyber.db')
        cursor = conn.cursor()
        # Eğer IP zaten varsa hata vermez (IGNORE), yoksa ekler
        cursor.execute("INSERT OR IGNORE INTO blocked_ips (ip, banned_at) VALUES (?, ?)", 
                       (ip, datetime.now()))
        conn.commit()
        conn.close()
        return True
    except:
        return False

# --- REST API ENDPOINT'LERİ ---

@app.get("/")
def read_root():
    return {"message": "KarguCyber API Başarıyla Çalışıyor!"}

# Logları getiren endpoint
@app.get("/api/logs")
def get_logs():
    logs = get_logs_from_db()
    return {"status": "success", "total_attacks": len(logs), "data": logs}

# Backend'e "Şu IP'yi engelle" komutunu alıp veritabanına yazan endpoint
@app.post("/api/block")
def block_ip(request: BlockRequest):
    add_ip_to_blacklist(request.ip)
    # Engellendiğine dair bilgi mesajı dön
    return {"status": "success", "message": f"{request.ip} adresi kara listeye alındı ve bağlantısı kesilecek!"}

# --- VERİTABANINDAN IP SİLME FONKSİYONU ---
def remove_ip_from_blacklist(ip):
    try:
        conn = sqlite3.connect('kargucyber.db')
        cursor = conn.cursor()
        cursor.execute("DELETE FROM blocked_ips WHERE ip = ?", (ip,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Hata: {e}")
        return False

# --- YASAĞI KALDIRMA ENDPOINT'İ ---
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
            # İstemciden gelen mesajları dinle (şu an için sadece bağlantıyı açık tutuyor)
            data = await websocket.receive_text() 
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.post("/api/notify")
async def notify_new_log(log: LogNotify):
    # Honeypot'tan gelen veriyi JSON'a çevir ve WebSocket tünelinden Flutter'a fırlat
    await manager.broadcast(json.dumps(log.model_dump()))
    return {"status": "success"}