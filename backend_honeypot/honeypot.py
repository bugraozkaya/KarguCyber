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
HTTP_PORT = 8080  # Web bal küpü için yeni portumuz
DB_NAME = 'kargucyber.db'
HOST_KEY = None

# --- VERİTABANI KURULUMU ---
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

# --- RSA ANAHTARI YÜKLEME / OLUŞTURMA ---
def load_or_generate_key():
    global HOST_KEY
    key_path = 'server.key'
    if os.path.exists(key_path):
        print(f"[*] Sunucu anahtarı yükleniyor: {key_path}")
        HOST_KEY = paramiko.RSAKey(filename=key_path)
    else:
        print("[*] server.key bulunamadı, yeni bir RSA anahtarı oluşturuluyor...")
        print("    (Bu işlem birkaç saniye sürebilir, lütfen bekleyin)")
        HOST_KEY = paramiko.RSAKey.generate(2048)
        HOST_KEY.write_private_key_file(key_path)
        print("[+] server.key başarıyla oluşturuldu ve kaydedildi.")

def is_ip_blocked(ip):
    try:
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM blocked_ips WHERE ip = ?", (ip,))
            return cursor.fetchone() is not None
    except sqlite3.Error:
        return False

def log_attack(ip, username, password, command):
    timestamp = datetime.now()
    try:
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO attack_logs (ip_address, username, password, command, timestamp) VALUES (?, ?, ?, ?, ?)",
                           (ip, username, password, command, timestamp))
            conn.commit()
    except sqlite3.Error as e:
        print(f"[DB HATA] Log yazılamadı: {e}")

    print(f"[LOG] {ip} - {username}:{password} - Komut: {command}")

    log_data = {
        "ip_address": ip,
        "username": username,
        "password": password,
        "command": command,
        "timestamp": str(timestamp).split('.')[0]
    }
    
    try:
        requests.post("http://127.0.0.1:8000/api/notify", json=log_data, timeout=1)
    except requests.RequestException:
        pass

# ==========================================
# 1. BÖLÜM: SSH HONEYPOT MODÜLÜ (PORT 2222)
# ==========================================
class KarguServer(paramiko.ServerInterface):
    def __init__(self, client_ip):
        self.event = threading.Event()
        self.client_ip = client_ip
        self.username = None
        self.password = None

    def get_allowed_auths(self, username):
        return "password"

    def check_channel_request(self, kind, chanid):
        if kind == 'session':
            return paramiko.OPEN_SUCCEEDED
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_auth_password(self, username, password):
        self.username = username
        self.password = password
        return paramiko.AUTH_SUCCESSFUL

    def check_channel_pty_request(self, channel, term, width, height, pixelwidth, pixelheight, modes):
        return True

    def check_channel_shell_request(self, channel):
        self.event.set()
        return True

def handle_ssh_connection(client, addr):
    ip = addr[0]
    print(f"[!] Yeni SSH Bağlantısı: {ip}")

    if is_ip_blocked(ip):
        print(f"[ENGEL] Yasaklı IP ({ip}) bağlantısı reddedildi!")
        client.close()
        return

    try:
        transport = paramiko.Transport(client)
        transport.add_server_key(HOST_KEY) 
        
        server = KarguServer(ip)
        
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

        channel.send("Welcome to Ubuntu 22.04 LTS (GNU/Linux 5.15.0-76-generic x86_64)\r\n$ ")

        while True:
            if is_ip_blocked(ip):
                channel.send("\r\n*** BAĞLANTINIZ YÖNETİCİ TARAFINDAN KESİLDİ ***\r\n")
                print(f"[KILL] {ip} adresi içerideyken atıldı!")
                break

            command = ""
            while not command.endswith("\r"):
                try:
                    channel.settimeout(1.0)
                    recv_data = channel.recv(1024)
                    
                    if not recv_data:
                        break
                        
                    recv = recv_data.decode('utf-8', errors='ignore')
                    command += recv
                    channel.send(recv) 
                except socket.timeout:
                    if is_ip_blocked(ip):
                        break
                    continue
                except Exception:
                    break
            
            if not command or is_ip_blocked(ip):
                if is_ip_blocked(ip):
                     channel.send("\r\n*** BAĞLANTINIZ KESİLDİ ***\r\n")
                break

            command = command.strip()
            if not command:
                channel.send("\r\n$ ")
                continue

            log_attack(ip, server.username, server.password, command)

            if command == "ls":
                channel.send("\r\nDesktop  Documents  Downloads  passwords.txt  scripts\r\n$ ")
            elif command == "whoami":
                channel.send(f"\r\n{server.username}\r\n$ ")
            elif command == "pwd":
                channel.send(f"\r\n/home/{server.username}\r\n$ ")
            elif command in ["exit", "quit", "logout"]:
                channel.send("\r\nLogout\r\n")
                break
            else:
                channel.send(f"\r\n{command}: command not found\r\n$ ")

    except Exception:
        pass
    finally:
        try:
            client.close()
        except:
            pass

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
            except Exception as e:
                pass
    except Exception as e:
        print(f"[KRİTİK HATA] SSH Sunucu başlatılamadı: {e}")

# ==========================================
# 2. BÖLÜM: WEB (HTTP) HONEYPOT MODÜLÜ (PORT 8080)
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
            # Gelen HTTP isteğinin ilk satırını al (Örn: GET /wp-admin HTTP/1.1)
            first_line = request.split('\n')[0].strip()
            
            # Eğer istek boş değilse logla
            if first_line:
                print(f"[!] Yeni WEB Saldırısı: {ip} -> {first_line}")
                
                # Mobil ve Web panel için özel formatlanmış log
                log_attack(ip, "[WEB_HTTP]", "PORT_8080", first_line)

            # Hacker'ı oylamak için sahte bir Apache Sunucu yanıtı dönüyoruz
            fake_response = (
                "HTTP/1.1 200 OK\r\n"
                "Server: Apache/2.4.41 (Ubuntu)\r\n"
                "Content-Type: text/html; charset=UTF-8\r\n\r\n"
                "<html><head><title>Admin Panel</title></head>"
                "<body><h1>403 Forbidden - Bu Olay KarguCyber Tarafından Kaydedildi!</h1></body></html>\r\n"
            )
            client_socket.sendall(fake_response.encode('utf-8'))
            
    except Exception:
        pass
    finally:
        client_socket.close()

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
            except Exception:
                pass
    except Exception as e:
        print(f"[KRİTİK HATA] Web Sunucu başlatılamadı: {e}")

# ==========================================
# ANA ÇALIŞTIRICI (MULTI-THREADING)
# ==========================================
if __name__ == "__main__":
    load_or_generate_key() 
    
    print("\n" + "="*50)
    print("🚀 KARGUCYBER MULTI-HONEYPOT BAŞLATILIYOR 🚀")
    print("="*50 + "\n")

    # İki ayrı asenkron thread oluşturuyoruz
    ssh_thread = threading.Thread(target=start_ssh_honeypot, daemon=True)
    web_thread = threading.Thread(target=start_http_honeypot, daemon=True)

    # İkisini aynı anda başlat
    ssh_thread.start()
    web_thread.start()

    # Ana programın kapanmaması için bekletiyoruz
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[!] KarguCyber Sistemleri Kapatılıyor...")