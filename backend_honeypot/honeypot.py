import socket
import paramiko
import threading
import sqlite3
import requests
import time
from datetime import datetime
import os

HOST = '0.0.0.0'
SSH_PORT = 2222
HTTP_PORT = 8080  # Web bal küpü
DB_NAME = 'kargucyber.db'
HOST_KEY = None

# ==========================================
# YENİ: TEHDİT ANALİZ MOTORU (DATA LABELING)
# ==========================================
def analyze_threat(port, command):
    command = command.lower()
    
    # WEB Saldırıları Analizi
    if port == 8080:
        if "wp-admin" in command or "wp-login" in command:
            return "WEB_WP_BRUTEFORCE"
        elif ".env" in command or "config" in command:
            return "WEB_ENV_EXPLOIT"
        elif "select" in command or "union" in command:
            return "WEB_SQL_INJECTION"
        else:
            return "WEB_SCANNER_GENERIC"
            
    # SSH Saldırıları Analizi
    elif port == 2222:
        if not command:
            return "SSH_AUTH_ATTEMPT"
        elif command in ["ls", "pwd", "whoami", "id", "uname -a"]:
            return "SSH_RECONNAISSANCE" # Sistemi tanıma/keşif
        elif "wget" in command or "curl" in command:
            return "SSH_MALWARE_DOWNLOAD" # Virüs/Zararlı indirme
        elif "rm -rf" in command or "drop" in command:
            return "SSH_DESTRUCTIVE_ACTION" # Sisteme zarar verme
        elif "chmod +x" in command or "./" in command:
            return "SSH_PAYLOAD_EXECUTION" # Zararlı çalıştırma
        else:
            return "SSH_GENERIC_EXPLOIT"
            
    return "UNKNOWN_THREAT"

# --- VERİTABANI KURULUMU (threat_label eklendi) ---
def setup_db():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS attack_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip_address TEXT,
                username TEXT,
                password TEXT,
                command TEXT,
                threat_label TEXT,
                timestamp DATETIME
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS blocked_ips (
                ip TEXT PRIMARY KEY,
                banned_at DATETIME
            )
        ''')
        conn.commit()

setup_db()

# --- RSA ANAHTARI YÜKLEME ---
def load_or_generate_key():
    global HOST_KEY
    key_path = 'server.key'
    if os.path.exists(key_path):
        HOST_KEY = paramiko.RSAKey(filename=key_path)
    else:
        print("[*] Yeni RSA anahtarı oluşturuluyor...")
        HOST_KEY = paramiko.RSAKey.generate(2048)
        HOST_KEY.write_private_key_file(key_path)

def is_ip_blocked(ip):
    try:
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM blocked_ips WHERE ip = ?", (ip,))
            return cursor.fetchone() is not None
    except sqlite3.Error:
        return False

# --- LOGLAMA FONKSİYONU (threat_label eklendi) ---
def log_attack(ip, username, password, command, port):
    timestamp = datetime.now()
    
    # 1. Saldırıyı Analiz Et ve Etiketle
    threat_label = analyze_threat(port, command)
    
    # 2. Veritabanına Kaydet
    try:
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO attack_logs (ip_address, username, password, command, threat_label, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                           (ip, username, password, command, threat_label, timestamp))
            conn.commit()
    except sqlite3.Error as e:
        print(f"[DB HATA] Log yazılamadı: {e}")

    print(f"[LOG] {ip} | Tür: {threat_label} | Komut: {command}")

    # 3. API'ye Gönder
    log_data = {
        "ip_address": ip,
        "username": username,
        "password": password,
        "command": command,
        "threat_label": threat_label,
        "timestamp": str(timestamp).split('.')[0]
    }
    
    try:
        requests.post("http://127.0.0.1:8000/api/notify", json=log_data, timeout=1)
    except requests.RequestException:
        pass

# ==========================================
# 1. BÖLÜM: SSH HONEYPOT MODÜLÜ
# ==========================================
class KarguServer(paramiko.ServerInterface):
    def __init__(self, client_ip):
        self.event = threading.Event()
        self.client_ip = client_ip
        self.username = None
        self.password = None

    def get_allowed_auths(self, username): return "password"
    def check_channel_request(self, kind, chanid):
        if kind == 'session': return paramiko.OPEN_SUCCEEDED
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED
    def check_auth_password(self, username, password):
        self.username = username
        self.password = password
        return paramiko.AUTH_SUCCESSFUL
    def check_channel_pty_request(self, channel, term, width, height, pixelwidth, pixelheight, modes): return True
    def check_channel_shell_request(self, channel):
        self.event.set()
        return True

def handle_ssh_connection(client, addr):
    ip = addr[0]
    if is_ip_blocked(ip):
        client.close()
        return

    try:
        transport = paramiko.Transport(client)
        transport.add_server_key(HOST_KEY) 
        server = KarguServer(ip)
        
        try: transport.start_server(server=server)
        except paramiko.SSHException: return

        channel = transport.accept(20)
        if channel is None: return

        server.event.wait(10)
        if not server.event.is_set(): return

        channel.send("Welcome to Ubuntu 22.04 LTS (GNU/Linux 5.15.0-76-generic x86_64)\r\n$ ")

        while True:
            if is_ip_blocked(ip):
                channel.send("\r\n*** BAĞLANTINIZ KESİLDİ ***\r\n")
                break

            command = ""
            while not command.endswith("\r"):
                try:
                    channel.settimeout(1.0)
                    recv_data = channel.recv(1024)
                    if not recv_data: break
                    recv = recv_data.decode('utf-8', errors='ignore')
                    command += recv
                    channel.send(recv) 
                except socket.timeout:
                    if is_ip_blocked(ip): break
                    continue
                except Exception: break
            
            if not command or is_ip_blocked(ip): break

            command = command.strip()
            if not command:
                channel.send("\r\n$ ")
                continue

            # PORT 2222 OLARAK API'YE GÖNDERİYORUZ
            log_attack(ip, server.username, server.password, command, 2222)

            if command == "ls": channel.send("\r\nDesktop  Documents  Downloads  passwords.txt  scripts\r\n$ ")
            elif command == "whoami": channel.send(f"\r\n{server.username}\r\n$ ")
            elif command == "pwd": channel.send(f"\r\n/home/{server.username}\r\n$ ")
            elif command in ["exit", "quit", "logout"]:
                channel.send("\r\nLogout\r\n")
                break
            else: channel.send(f"\r\n{command}: command not found\r\n$ ")

    except Exception: pass
    finally:
        try: client.close()
        except: pass

def start_ssh_honeypot():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((HOST, SSH_PORT))
        sock.listen(100)
        print(f"[*] KarguCyber SSH Honeypot {SSH_PORT} portunda aktif! 🛡️")
        while True:
            try:
                client, addr = sock.accept()
                threading.Thread(target=handle_ssh_connection, args=(client, addr), daemon=True).start()
            except Exception: pass
    except Exception as e: print(f"[KRİTİK HATA] {e}")

# ==========================================
# 2. BÖLÜM: WEB (HTTP) HONEYPOT MODÜLÜ
# ==========================================
def handle_http_connection(client_socket, addr):
    ip = addr[0]
    if is_ip_blocked(ip):
        client_socket.close()
        return

    try:
        client_socket.settimeout(3.0)
        request = client_socket.recv(1024).decode('utf-8', errors='ignore')
        if request:
            first_line = request.split('\n')[0].strip()
            if first_line:
                # PORT 8080 OLARAK API'YE GÖNDERİYORUZ
                log_attack(ip, "[WEB_HTTP]", "PORT_8080", first_line, 8080)

            fake_response = (
                "HTTP/1.1 200 OK\r\n"
                "Server: Apache/2.4.41 (Ubuntu)\r\n"
                "Content-Type: text/html; charset=UTF-8\r\n\r\n"
                "<html><head><title>Admin Panel</title></head>"
                "<body><h1>403 Forbidden - Bu Olay KarguCyber Tarafından Kaydedildi!</h1></body></html>\r\n"
            )
            client_socket.sendall(fake_response.encode('utf-8'))
    except Exception: pass
    finally: client_socket.close()

def start_http_honeypot():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((HOST, HTTP_PORT))
        sock.listen(100)
        print(f"[*] KarguCyber WEB Honeypot {HTTP_PORT} portunda aktif! 🌐")
        while True:
            try:
                client, addr = sock.accept()
                threading.Thread(target=handle_http_connection, args=(client, addr), daemon=True).start()
            except Exception: pass
    except Exception as e: print(f"[KRİTİK HATA] {e}")

if __name__ == "__main__":
    load_or_generate_key() 
    print("\n" + "="*50)
    print("🚀 KARGUCYBER MULTI-HONEYPOT BAŞLATILIYOR 🚀")
    print("="*50 + "\n")

    threading.Thread(target=start_ssh_honeypot, daemon=True).start()
    threading.Thread(target=start_http_honeypot, daemon=True).start()

    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        print("\n[!] KarguCyber Sistemleri Kapatılıyor...")