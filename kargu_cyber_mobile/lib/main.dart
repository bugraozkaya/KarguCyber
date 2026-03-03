import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';
import 'dart:async';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:vibration/vibration.dart';

void main() {
  runApp(const KarguCyberApp());
}

class KarguCyberApp extends StatelessWidget {
  const KarguCyberApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'KarguCyber',
      theme: ThemeData.dark().copyWith(
        scaffoldBackgroundColor: const Color(0xFF111827),
        primaryColor: const Color(0xFFEF4444),
        appBarTheme: const AppBarTheme(
          backgroundColor: Color(0xFF1F2937),
          centerTitle: true,
        ),
      ),
      home: const DashboardScreen(),
    );
  }
}

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  String statusText = "Sistem Beklemede...";
  Color statusColor = Colors.orange;
  List<dynamic> logs = [];

  final String baseUrl = "http://10.0.2.2:8000";
  final String wsUrl = "ws://10.0.2.2:8000/ws/logs";
  WebSocketChannel? channel;
  bool isReconnecting = false;

  @override
  void initState() {
    super.initState();
    fetchLogs();
    connectWebSocket();
  }

  void connectWebSocket() {
    try {
      channel = WebSocketChannel.connect(Uri.parse(wsUrl));

      channel!.stream.listen(
            (message) async {
          try {
            final newLog = json.decode(message);

            bool? hasVibrator = await Vibration.hasVibrator();
            if (hasVibrator == true) {
              Vibration.vibrate(duration: 500);
            }

            setState(() {
              logs.insert(0, newLog);
              statusText = "⚠️ CANLI TEHDİT TESPİT EDİLDİ!";
              statusColor = Colors.redAccent;
            });

            Future.delayed(const Duration(seconds: 3), () {
              if (mounted) {
                setState(() {
                  statusText = "🛡️ SİSTEM AKTİF - İZLENİYOR";
                  statusColor = Colors.greenAccent;
                });
              }
            });
          } catch (e) {
            debugPrint("Gelen JSON parse edilemedi: $e");
          }
        },
        onError: (error) {
          handleDisconnect();
        },
        onDone: () {
          handleDisconnect();
        },
      );
    } catch (e) {
      handleDisconnect();
    }
  }

  void handleDisconnect() {
    if (isReconnecting) return;
    isReconnecting = true;

    if (mounted) {
      setState(() {
        statusText = "❌ BAĞLANTI KOPUK (Yeniden deneniyor...)";
        statusColor = Colors.red;
      });
    }

    Future.delayed(const Duration(seconds: 5), () {
      isReconnecting = false;
      if (mounted) connectWebSocket();
    });
  }

  Future<void> fetchLogs() async {
    try {
      final response = await http.get(Uri.parse("$baseUrl/api/logs")).timeout(const Duration(seconds: 5));
      if (response.statusCode == 200) {
        final Map<String, dynamic> responseData = json.decode(response.body);
        setState(() {
          logs = responseData['data'] ?? [];
          statusText = logs.isEmpty ? "🟢 SİSTEM AKTİF - SALDIRI YOK" : "🛡️ SİSTEM GÜNCEL";
          statusColor = logs.isEmpty ? Colors.greenAccent : Colors.blueAccent;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          statusText = "❌ SUNUCUYA ERİŞİLEMİYOR";
          statusColor = Colors.red;
        });
      }
    }
  }

  Future<void> blockIP(String ip) async {
    try {
      final response = await http.post(
        Uri.parse("$baseUrl/api/block"),
        headers: {"Content-Type": "application/json"},
        body: json.encode({"ip": ip}),
      );
      if (response.statusCode == 200) {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("🛡️ $ip kara listeye alındı!"), backgroundColor: Colors.red),
        );
      }
    } catch (e) {
      debugPrint("Bloklama Hatası: $e");
    }
  }

  Future<void> unblockIP(String ip) async {
    try {
      final response = await http.delete(Uri.parse("$baseUrl/api/unblock/$ip"));
      if (response.statusCode == 200) {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("✅ $ip yasağı kaldırıldı!"), backgroundColor: Colors.green),
        );
        fetchLogs();
      }
    } catch (e) {
      debugPrint("Unblock Hatası: $e");
    }
  }

  @override
  void dispose() {
    channel?.sink.close();
    super.dispose();
  }

  // --- YENİ EKLENEN: Tehdit Sınıfına Göre Renkli Etiket (Badge) Oluşturucu ---
  Widget buildThreatBadge(String? label) {
    String text = "BİLİNMEYEN";
    Color bgColor = Colors.grey.shade800;
    Color textColor = Colors.grey.shade300;

    if (label != null) {
      if (label.contains("WEB_")) {
        if (label == "WEB_WP_BRUTEFORCE") { text = "WP KABA KUVVET"; bgColor = Colors.purple.shade900; textColor = Colors.purple.shade200; }
        else if (label == "WEB_ENV_EXPLOIT") { text = "ENV SIZINTISI"; bgColor = Colors.red.shade900; textColor = Colors.red.shade200; }
        else if (label == "WEB_SQL_INJECTION") { text = "SQL INJECTION"; bgColor = Colors.orange.shade900; textColor = Colors.orange.shade200; }
        else { text = "WEB TARAMASI"; bgColor = Colors.deepPurple.shade900; textColor = Colors.deepPurple.shade200; }
      }
      else if (label.contains("SSH_")) {
        if (label == "SSH_MALWARE_DOWNLOAD") { text = "ZARARLI YAZILIM"; bgColor = Colors.redAccent.shade700; textColor = Colors.white; }
        else if (label == "SSH_DESTRUCTIVE_ACTION") { text = "SİSTEM İMHASI"; bgColor = Colors.red.shade900; textColor = Colors.red.shade100; }
        else if (label == "SSH_PAYLOAD_EXECUTION") { text = "VİRÜS ÇALIŞTIRMA"; bgColor = Colors.orange.shade800; textColor = Colors.white; }
        else if (label == "SSH_RECONNAISSANCE") { text = "SİSTEM KEŞFİ"; bgColor = Colors.blue.shade900; textColor = Colors.blue.shade200; }
        else if (label == "SSH_AUTH_ATTEMPT") { text = "ŞİFRE DENEMESİ"; bgColor = Colors.grey.shade700; textColor = Colors.grey.shade300; }
        else { text = "SSH EXPLOIT"; bgColor = Colors.yellow.shade900; textColor = Colors.yellow.shade200; }
      }
    }

    return Container(
      margin: const EdgeInsets.only(bottom: 5),
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: BorderRadius.circular(5),
      ),
      child: Text(
        text,
        style: TextStyle(color: textColor, fontSize: 10, fontWeight: FontWeight.bold, letterSpacing: 0.5),
      ),
    );
  }

  // --- ARAYÜZ (UI) ---
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.shield, color: Colors.redAccent),
            SizedBox(width: 10),
            Text("KARGU CYBER", style: TextStyle(fontWeight: FontWeight.bold, letterSpacing: 1.2)),
          ],
        ),
      ),
      body: Padding(
        padding: const EdgeInsets.all(20.0),
        child: Column(
          children: [
            // Durum Paneli
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: const Color(0xFF1F2937),
                borderRadius: BorderRadius.circular(15),
                border: Border.all(color: statusColor.withOpacity(0.5)),
                boxShadow: [BoxShadow(color: statusColor.withOpacity(0.2), blurRadius: 10)],
              ),
              child: Text(
                statusText,
                style: TextStyle(color: statusColor, fontSize: 16, fontWeight: FontWeight.bold),
                textAlign: TextAlign.center,
              ),
            ),
            const SizedBox(height: 20),

            // Log Listesi
            Expanded(
              child: Container(
                width: double.infinity,
                decoration: BoxDecoration(
                  color: Colors.black26,
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: Colors.white10),
                ),
                child: logs.isEmpty
                    ? const Center(child: Text("Saldırı kaydı bulunamadı.", style: TextStyle(color: Colors.white38)))
                    : ListView.builder(
                  itemCount: logs.length,
                  itemBuilder: (context, index) {
                    final log = logs[index];
                    final ip = log['ip_address'] ?? 'Bilinmeyen IP';
                    final threatLabel = log['threat_label']; // Yeni veri çekildi

                    return Card(
                      color: const Color(0xFF1F2937),
                      margin: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                      child: Padding(
                        padding: const EdgeInsets.symmetric(vertical: 8.0),
                        child: ListTile(
                          leading: const Icon(Icons.security, color: Colors.redAccent, size: 30),
                          title: Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Text(ip, style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.white, fontSize: 15)),
                            ],
                          ),
                          // GÜNCELLENEN KISIM: Rozet (Badge) + Komut + Tarih alt alta dizildi
                          subtitle: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const SizedBox(height: 5),
                              buildThreatBadge(threatLabel), // Renkli Etiket Burada
                              Text(
                                "> ${log['command'] ?? 'N/A'}",
                                style: const TextStyle(color: Colors.yellowAccent, fontFamily: 'monospace', fontSize: 13),
                              ),
                              const SizedBox(height: 3),
                              Text(
                                "${log['timestamp']}",
                                style: const TextStyle(color: Colors.white54, fontSize: 11),
                              ),
                            ],
                          ),
                          trailing: Wrap(
                            spacing: -10, // Butonları biraz daha yakınlaştırdık
                            children: [
                              IconButton(
                                icon: const Icon(Icons.block, color: Colors.redAccent),
                                onPressed: () => blockIP(ip),
                                tooltip: "Engelle",
                              ),
                              IconButton(
                                icon: const Icon(Icons.delete_outline, color: Colors.orangeAccent),
                                onPressed: () => unblockIP(ip),
                                tooltip: "Yasağı Kaldır",
                              ),
                            ],
                          ),
                        ),
                      ),
                    );
                  },
                ),
              ),
            ),
            const SizedBox(height: 20),

            // Manuel Yenileme Butonu
            SizedBox(
              width: double.infinity,
              height: 50,
              child: ElevatedButton.icon(
                onPressed: fetchLogs,
                icon: const Icon(Icons.radar),
                label: const Text("SİSTEMİ KONTROL ET", style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF2563EB),
                  foregroundColor: Colors.white,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}