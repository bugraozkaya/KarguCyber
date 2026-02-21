import socket
import paramiko
import threading
import sqlite3
import requests  # [ADIM 3] API'ye haber uçurmak için eklendi
from datetime import datetime

HOST = '0.0.0.0'
PORT = 2222 # 2222 portunu dinleyen sunucu

# --- VERİTABANI KURULUMU VE LOGLAMA ---
def setup_db():
    conn = sqlite3.connect('kargucyber.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attack_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip_address TEXT,
            username TEXT,
            password TEXT,
            command TEXT,
            timestamp DATETIME
        )
    ''')
    conn.commit()
    return conn

db_conn = setup_db()

def log_attack(ip, username, password, command):
    timestamp = datetime.now()
    
    # 1. Veritabanına kaydet
    cursor = db_conn.cursor()
    cursor.execute("INSERT INTO attack_logs (ip_address, username, password, command, timestamp) VALUES (?, ?, ?, ?, ?)",
                   (ip, username, password, command, timestamp))
    db_conn.commit()
    print(f"[LOG] {ip} - {username}:{password} - Komut: {command}")

    # 2. [ADIM 3] Canlı yayın için API'ye haber ver
    log_data = {
        "ip_address": ip,
        "username": username,
        "password": password,
        "command": command,
        "timestamp": str(timestamp).split('.')[0] # Milisaniyeleri kırpıyoruz
    }
    try:
        # Timeout'u kısa tutuyoruz (1 saniye), eğer API kapalıysa Honeypot kilitlenip donmasın
        requests.post("http://127.0.0.1:8000/api/notify", json=log_data, timeout=1)
    except Exception as e:
        # API kapalıysa hata verme, sessizce geç
        pass

# --- PARAMIKO SAHTE SSH SUNUCUSU ---
class KarguServer(paramiko.ServerInterface):
    def __init__(self, client_ip):
        self.event = threading.Event()
        self.client_ip = client_ip
        self.username = None
        self.password = None

    def check_channel_request(self, kind, chanid):
        if kind == 'session':
            return paramiko.OPEN_SUCCEEDED
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_auth_password(self, username, password):
        # Her şifreyi doğru kabul edip saldırganı içeri alıyoruz
        self.username = username
        self.password = password
        return paramiko.AUTH_SUCCESSFUL

    def check_channel_pty_request(self, channel, term, width, height, pixelwidth, pixelheight, modes):
        return True

    def check_channel_shell_request(self, channel):
        self.event.set()
        return True

def handle_connection(client, addr):
    print(f"[!] Yeni sızma girişimi tespit edildi: {addr[0]}")
    try:
        transport = paramiko.Transport(client)
        transport.add_server_key(paramiko.RSAKey(filename='server.key'))
        server = KarguServer(addr[0])
        
        try:
            transport.start_server(server=server)
        except paramiko.SSHException:
            return

        channel = transport.accept(20)
        if channel is None:
            return

        server.event.wait(10)
        if not server.event.is_set():
            return

        # Sahte Linux Karşılama Mesajı
        channel.send("Welcome to Ubuntu 22.04 LTS (GNU/Linux 5.15.0-76-generic x86_64)\r\n$ ")

        while True:
            command = ""
            while not command.endswith("\r"):
                recv = channel.recv(1024).decode('utf-8')
                if not recv:
                    break
                command += recv
                channel.send(recv) # Karakterleri terminale geri yansıt

            command = command.strip()
            if not command:
                channel.send("\r\n$ ")
                continue

            # Komutu veritabanına kaydet ve API'ye uçur
            log_attack(addr[0], server.username, server.password, command)

            # Sahte komut cevapları
            if command == "ls":
                channel.send("\r\nDesktop  Documents  Downloads  passwords.txt  scripts\r\n$ ")
            elif command == "whoami":
                channel.send(f"\r\n{server.username}\r\n$ ")
            elif command == "pwd":
                channel.send(f"\r\n/home/{server.username}\r\n$ ")
            elif command == "exit":
                channel.send("\r\nLogout\r\n")
                break
            else:
                channel.send(f"\r\n{command}: command not found\r\n$ ")

    except Exception as e:
        print(f"Bağlantı koptu: {e}")
    finally:
        client.close()

def start_honeypot():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((HOST, PORT))
        sock.listen(100)
        print(f"[*] KarguCyber Honeypot {PORT} portunda aktif! Saldırganlar bekleniyor...")

        while True:
            client, addr = sock.accept()
            threading.Thread(target=handle_connection, args=(client, addr)).start()
    except Exception as e:
        print(f"Sunucu başlatılamadı: {e}")

if __name__ == "__main__":
    start_honeypot()