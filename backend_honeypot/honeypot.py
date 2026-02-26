import socket
import paramiko
import threading
import sqlite3
import requests
from datetime import datetime
import os

HOST = '0.0.0.0'
PORT = 2222
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

# --- PARAMIKO SUNUCUSU ---
class KarguServer(paramiko.ServerInterface):
    def __init__(self, client_ip):
        self.event = threading.Event()
        self.client_ip = client_ip
        self.username = None
        self.password = None

    def get_allowed_auths(self, username):
        # İstemciye hangi giriş yöntemlerine izin verdiğimizi söyleyen KRİTİK fonksiyon
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

def handle_connection(client, addr):
    ip = addr[0]
    print(f"[!] Bağlantı isteği: {ip}")

    if is_ip_blocked(ip):
        print(f"[ENGEL] Yasaklı IP ({ip}) bağlantısı reddedildi!")
        client.close()
        return

    try:
        transport = paramiko.Transport(client)
        transport.add_server_key(HOST_KEY) # Bellekteki anahtarı kullan
        
        server = KarguServer(ip)
        
        try:
            transport.start_server(server=server)
        except paramiko.SSHException:
            print(f"[HATA] SSH Müzakeresi Başarısız ({ip})")
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

    except Exception as e:
        print(f"[HATA] Bağlantı sonlandı ({ip}): {e}")
    finally:
        try:
            client.close()
        except:
            pass

def start_honeypot():
    load_or_generate_key() # Program başlarken anahtarı 1 kez oluştur
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((HOST, PORT))
        sock.listen(100)
        print(f"[*] KarguCyber Honeypot {PORT} portunda aktif! (Kill Switch Aktif)")

        while True:
            # Hata yakalamayı döngü İÇİNE aldık, böylece bozuk bir paket sunucuyu kapatmaz
            try:
                client, addr = sock.accept()
                threading.Thread(target=handle_connection, args=(client, addr), daemon=True).start()
            except Exception as e:
                print(f"[UYARI] Socket accept hatası: {e}")
                
    except Exception as e:
        print(f"[KRİTİK HATA] Sunucu başlatılamadı: {e}")

if __name__ == "__main__":
    start_honeypot()