from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel # [ADIM 2] İçin eklendi
import sqlite3
import json

# API Uygulamasını Başlatıyoruz
app = FastAPI(title="KarguCyber API", description="Honeypot Log ve Kontrol Servisi")

# CORS ayarlarını ekliyoruz (Web sitesinin API'den veri çekebilmesi için)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Şimdilik her yerden erişime açık (İleride kısıtlanabilir)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# [ADIM 2] Gelen log verisinin yapısı
class LogNotify(BaseModel):
    ip_address: str
    username: str
    password: str
    command: str
    timestamp: str

# --- VERİTABANI İŞLEMLERİ ---
def get_logs_from_db():
    try:
        conn = sqlite3.connect('kargucyber.db')
        conn.row_factory = sqlite3.Row  # Verileri JSON (dictionary) formatında almak için
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM attack_logs ORDER BY timestamp DESC")
        logs = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return logs
    except Exception as e:
        return {"error": str(e)}

# --- REST API ENDPOINT'LERİ ---

@app.get("/")
def read_root():
    return {"message": "KarguCyber API Başarıyla Çalışıyor!"}

# Veritabanındaki logları JSON formatında dışarı aktaran GET endpoint'i
@app.get("/api/logs")
def get_logs():
    logs = get_logs_from_db()
    return {"status": "success", "total_attacks": len(logs), "data": logs}

# Backend'e "Şu IP'yi engelle" komutunu alacak endpoint (Kill Switch)
@app.post("/api/block")
def block_ip(ip: str):
    return {"status": "success", "message": f"{ip} adresi kara listeye (Blacklist) alındı ve bağlantısı kesilecek!"}

# --- WEBSOCKET (CANLI YAYIN) VE BİLDİRİM ALTYAPISI ---

# Bağlı olan tüm WebSocket istemcilerini tutacağımız liste
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

# Yeni log geldiğinde anında yayınlayacak WebSocket kanalı
@app.websocket("/ws/logs")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text() 
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# [ADIM 2] Honeypot'un API'ye "yeni log var" diyeceği endpoint
@app.post("/api/notify")
async def notify_new_log(log: LogNotify):
    # Gelen veriyi JSON'a çevirip WebSocket'teki herkese (Web Paneline) fırlat
    await manager.broadcast(json.dumps(log.model_dump()))
    return {"status": "success"}