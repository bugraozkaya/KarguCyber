import socket
import paramiko
import threading
import sqlite3
import requests
from datetime import datetime
import time

HOST = '0.0.0.0'
PORT = 2222

# --- VERİTABANI VE KARA LİSTE KONTROLÜ ---
def setup_db():
    conn = sqlite3.connect('kargucyber.db', check_same_thread=False)
    cursor = conn.cursor()
    # Log tablosu
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
    # [YENİ] Kara Liste Tablosu (Engellenenler buraya yazılır)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS blocked_ips (
            ip TEXT PRIMARY KEY,
            banned_at DATETIME
        )
    ''')
    conn.commit()
    return conn

db_conn = setup_db()

# Bir IP'nin yasaklı olup olmadığını kontrol eden fonksiyon
def is_ip_blocked(ip):
    try:
        # Thread güvenliği için her sorguda yeni bağlantı açıyoruz
        temp_conn = sqlite3.connect('kargucyber.db')
        cursor = temp_conn.cursor()
        cursor.execute("SELECT 1 FROM blocked_ips WHERE ip = ?", (ip,))
        result = cursor.fetchone()
        temp_conn.close()
        return result is not None
    except:
        return False

def log_attack(ip, username, password, command):
    timestamp = datetime.now()
    cursor = db_conn.cursor()
    cursor.execute("INSERT INTO attack_logs (ip_address, username, password, command, timestamp) VALUES (?, ?, ?, ?, ?)",
                   (ip, username, password, command, timestamp))
    db_conn.commit()
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
    except:
        pass

# --- PARAMIKO SUNUCUSU ---
class KarguServer(paramiko.ServerInterface):
    def __init__(self, client_ip):
        self.event = threading.Event()
        self.client_ip = client_ip

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

    # [KILL SWITCH 1] Bağlanırken kontrol et: IP yasaklı mı?
    if is_ip_blocked(ip):
        print(f"[ENGEL] Yasaklı IP ({ip}) engellendi!")
        client.close()
        return

    try:
        transport = paramiko.Transport(client)
        transport.add_server_key(paramiko.RSAKey(filename='server.key'))
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
            # [KILL SWITCH 2] Döngü içinde kontrol: Saldırgan hala içerideyken engellendiyse at!
            if is_ip_blocked(ip):
                channel.send("\r\n*** BAĞLANTINIZ YÖNETİCİ TARAFINDAN KESİLDİ ***\r\n")
                print(f"[KILL] {ip} adresi içerideyken atıldı!")
                break

            command = ""
            while not command.endswith("\r"):
                # Soketten veri okurken zaman aşımı ekleyip sürekli IP kontrolü yapıyoruz
                try:
                    channel.settimeout(1.0) # 1 saniye bekle
                    recv = channel.recv(1024).decode('utf-8')
                    command += recv
                    channel.send(recv)
                except socket.timeout:
                    # Veri gelmediyse döngüye dön ve IP yasaklı mı diye tekrar kontrol et
                    if is_ip_blocked(ip):
                        break
                    continue
                except:
                    break
            
            # Eğer timeout döngüsünden break ile çıktıysa ve yasaklıysa ana döngüyü de kır
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
            elif command == "exit":
                channel.send("\r\nLogout\r\n")
                break
            else:
                channel.send(f"\r\n{command}: command not found\r\n$ ")

    except Exception as e:
        pass # Hataları görmezden gel
    finally:
        client.close()

def start_honeypot():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((HOST, PORT))
        sock.listen(100)
        print(f"[*] KarguCyber Honeypot {PORT} portunda aktif! (Kill Switch Aktif)")

        while True:
            client, addr = sock.accept()
            threading.Thread(target=handle_connection, args=(client, addr)).start()
    except Exception as e:
        print(f"Sunucu başlatılamadı: {e}")

if __name__ == "__main__":
    start_honeypot()