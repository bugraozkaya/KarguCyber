const API_BASE = "http://127.0.0.1:8000";

// Logları çeken ana fonksiyon
async function fetchLogs() {
    try {
        const response = await fetch(`${API_BASE}/api/logs`);
        const result = await response.json();

        const tableBody = document.getElementById('log-table-body');
        tableBody.innerHTML = ''; 

        if (result.data.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="5" class="p-4 text-center text-gray-500">Henüz saldırı kaydı bulunmuyor.</td></tr>';
            return;
        }

        result.data.forEach(log => {
            const row = createRow(log);
            tableBody.innerHTML += row;
        });

    } catch (error) {
        console.error("Veri çekme hatası:", error);
        const tableBody = document.getElementById('log-table-body');
        if(tableBody) {
            tableBody.innerHTML = '<tr><td colspan="5" class="p-4 text-center text-red-500">API bağlantı hatası! Sunucunun çalıştığından emin olun.</td></tr>';
        }
    }
}

// Tablo satırı oluşturucu (HTML şablonu)
function createRow(log) {
    return `
        <tr class="hover:bg-gray-700 transition duration-150">
            <td class="p-4 border-b border-gray-700 text-sm">${log.timestamp.split('.')[0]}</td>
            <td class="p-4 border-b border-gray-700 font-bold text-red-400">${log.ip_address}</td>
            <td class="p-4 border-b border-gray-700 text-gray-400">${log.username} : <span class="text-gray-500">${log.password}</span></td>
            <td class="p-4 border-b border-gray-700 text-yellow-300 font-bold">> ${log.command}</td>
            <td class="p-4 border-b border-gray-700 text-center space-x-2">
                <button onclick="blockIp('${log.ip_address}')" class="bg-red-600 hover:bg-red-700 text-white px-3 py-1 rounded text-xs font-bold transition">
                    Engelle
                </button>
                <button onclick="unblockIp('${log.ip_address}')" class="bg-emerald-600 hover:bg-emerald-700 text-white px-3 py-1 rounded text-xs font-bold transition">
                    Yasağı Kaldır
                </button>
            </td>
        </tr>
    `;
}

// IP Engelleme (POST)
async function blockIp(ip) {
    if(!confirm(ip + " adresini engellemek istiyor musunuz?")) return;
    try {
        const response = await fetch(`${API_BASE}/api/block`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ip: ip })
        });
        const result = await response.json();
        alert(result.status === 'success' ? "🛑 Engellendi: " + ip : "Hata: " + result.message);
        fetchLogs(); // Durumu güncelle
    } catch (error) { 
        alert("Bağlantı hatası!"); 
    }
}

// IP Yasağını Kaldırma (DELETE)
async function unblockIp(ip) {
    if(!confirm(ip + " adresinin yasağını kaldırmak istiyor musunuz?")) return;
    try {
        const response = await fetch(`${API_BASE}/api/unblock/${ip}`, {
            method: 'DELETE'
        });
        const result = await response.json();
        if (result.status === 'success') {
            alert("✅ YASAK KALDIRILDI: " + ip);
            fetchLogs(); // Tabloyu tazele
        } else {
            alert("Hata: " + result.message);
        }
    } catch (error) { 
        alert("Bağlantı hatası!"); 
    }
}

// Sayfa yüklendiğinde ilk verileri çek
fetchLogs();

// WebSocket Canlı Takip Kurulumu
const ws = new WebSocket("ws://127.0.0.1:8000/ws/logs");

ws.onmessage = function(event) {
    try {
        const log = JSON.parse(event.data);
        const tableBody = document.getElementById('log-table-body');
        
        if (tableBody && tableBody.innerHTML.includes('Henüz saldırı kaydı bulunmuyor')) {
            tableBody.innerHTML = '';
        }
        
        const tr = document.createElement('tr');
        tr.className = "bg-gray-700 transition duration-1000";
        tr.innerHTML = createRow(log);
        
        if(tableBody) {
            tableBody.insertAdjacentElement('afterbegin', tr);
            setTimeout(() => { 
                tr.classList.remove('bg-gray-700'); 
                tr.classList.add('hover:bg-gray-700'); 
            }, 100);
        }
    } catch (e) { 
        console.log("WebSocket Verisi (JSON değil): ", event.data); 
    }
};