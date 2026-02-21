from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import sqlite3
import json

# API Uygulamasını Başlatıyoruz
app = FastAPI(title="KarguCyber API", description="Honeypot Log ve Kontrol Servisi")

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

# [Adım 2 Görevi]: Veritabanındaki logları JSON formatında dışarı aktaran GET endpoint'i
@app.get("/api/logs")
def get_logs():
    logs = get_logs_from_db()
    return {"status": "success", "total_attacks": len(logs), "data": logs}

# [Adım 2 Görevi]: Backend'e "Şu IP'yi engelle" komutunu alacak endpoint (Kill Switch)
@app.post("/api/block")
def block_ip(ip: str):
    # İleride burada Honeypot'un o IP ile bağlantısını kesmesi için bir tetikleyici yazacağız
    return {"status": "success", "message": f"{ip} adresi kara listeye (Blacklist) alındı ve bağlantısı kesilecek!"}

# --- WEBSOCKET (CANLI YAYIN) ---

# Bağlı olan tüm WebSocket istemcilerini (örn: Mobil Uygulama) tutacağımız liste
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

# [Adım 2 Görevi]: Yeni log geldiğinde anında yayınlayacak WebSocket kanalı
@app.websocket("/ws/logs")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # İstemciden bir şey gelirse (şu an beklemiyoruz ama bağlantıyı açık tutmak için gerekli)
            data = await websocket.receive_text() 
    except WebSocketDisconnect:
        manager.disconnect(websocket)