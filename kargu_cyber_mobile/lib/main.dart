import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:web_socket_channel/io.dart';
import 'package:vibration/vibration.dart'; // [YENİ] Titreşim paketi

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
  late WebSocketChannel channel;

  @override
  void initState() {
    super.initState();
    fetchLogs();
    connectWebSocket();
  }

  // CANLI BAĞLANTI VE TİTREŞİM FONKSİYONU
  void connectWebSocket() {
    channel = IOWebSocketChannel.connect(Uri.parse(wsUrl));

    channel.stream.listen((message) {
      final newLog = json.decode(message);

      // [YENİ] SALDIRI ANINDA TİTREŞİM TETİKLE
      Vibration.hasVibrator().then((hasVibrator) {
        if (hasVibrator == true) {
          Vibration.vibrate(duration: 500, amplitude: 128); // 0.5 saniye titre
        }
      });

      setState(() {
        logs.insert(0, newLog);
        statusText = "⚠️ CANLI TEHDİT TESPİT EDİLDİ!";
        statusColor = Colors.redAccent;
      });
    }, onError: (error) {
      debugPrint("WS Hatası: $error");
      setState(() {
        statusText = "❌ CANLI BAĞLANTISI KOPUK";
        statusColor = Colors.red;
      });
    }, onDone: () {
      debugPrint("WS Bağlantısı Kapandı");
    });
  }

  // LOGLARI ÇEKME
  Future<void> fetchLogs() async {
    try {
      final response = await http.get(Uri.parse("$baseUrl/api/logs"));
      if (response.statusCode == 200) {
        final Map<String, dynamic> responseData = json.decode(response.body);
        setState(() {
          logs = responseData['data'] ?? [];
          statusText = logs.isEmpty ? "🟢 SİSTEM AKTİF - SALDIRI YOK" : "🛡️ SİSTEM GÜNCEL";
          statusColor = logs.isEmpty ? Colors.greenAccent : Colors.blueAccent;
        });
      }
    } catch (e) {
      setState(() {
        statusText = "❌ SUNUCU BAĞLANTISI KOPUK";
        statusColor = Colors.red;
      });
    }
  }

  // KULLANICIYI ENGELLEME
  Future<void> blockIP(String ip) async {
    try {
      final response = await http.post(
        Uri.parse("$baseUrl/api/block"),
        headers: {"Content-Type": "application/json"},
        body: json.encode({"ip": ip}),
      );
      if (response.statusCode == 200) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("$ip kara listeye alındı!"), backgroundColor: Colors.red),
        );
      }
    } catch (e) {
      debugPrint("Bloklama Hatası: $e");
    }
  }

  // YASAĞI KALDIRMA
  Future<void> unblockIP(String ip) async {
    try {
      final response = await http.delete(Uri.parse("$baseUrl/api/unblock/$ip"));
      if (response.statusCode == 200) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("$ip yasağı kaldırıldı!"), backgroundColor: Colors.green),
        );
        fetchLogs();
      }
    } catch (e) {
      debugPrint("Unblock Hatası: $e");
    }
  }

  @override
  void dispose() {
    channel.sink.close();
    super.dispose();
  }

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
                style: TextStyle(color: statusColor, fontSize: 18, fontWeight: FontWeight.bold),
                textAlign: TextAlign.center,
              ),
            ),
            const SizedBox(height: 30),
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
                    return Card(
                      color: const Color(0xFF1F2937),
                      margin: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                      child: ListTile(
                        leading: const Icon(Icons.security, color: Colors.redAccent),
                        title: Text(ip, style: const TextStyle(fontWeight: FontWeight.bold)),
                        subtitle: Text("Komut: ${log['command'] ?? 'N/A'}\n${log['timestamp']}"),
                        isThreeLine: true,
                        trailing: Wrap(
                          spacing: 8,
                          children: [
                            IconButton(
                              icon: const Icon(Icons.block, color: Colors.red),
                              onPressed: () => blockIP(ip),
                              tooltip: "Engelle",
                            ),
                            IconButton(
                              icon: const Icon(Icons.delete_forever, color: Colors.orangeAccent),
                              onPressed: () => unblockIP(ip),
                              tooltip: "Yasağı Kaldır",
                            ),
                          ],
                        ),
                      ),
                    );
                  },
                ),
              ),
            ),
            const SizedBox(height: 20),
            SizedBox(
              width: double.infinity,
              height: 50,
              child: ElevatedButton.icon(
                onPressed: fetchLogs,
                icon: const Icon(Icons.radar),
                label: const Text("TÜMÜNÜ YENİLE", style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
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