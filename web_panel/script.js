const API_BASE = "http://127.0.0.1:8000";

// Logları çeken ana fonksiyon
async function fetchLogs() {
    try {
        const response = await fetch(`${API_BASE}/api/logs`);
        const result = await response.json();

        const tableBody = document.getElementById('log-table-body');
        tableBody.innerHTML = ''; 

        if (result.data.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="6" class="p-4 text-center text-gray-500">Henüz saldırı kaydı bulunmuyor.</td></tr>';
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
            tableBody.innerHTML = '<tr><td colspan="6" class="p-4 text-center text-red-500">API bağlantı hatası! Sunucunun çalıştığından emin olun.</td></tr>';
        }
    }
}

// --- YENİ EKLENEN: Karantina Kasası Fonksiyonları ---
async function toggleQuarantineVault() {
    const vault = document.getElementById('quarantine-vault');
    if (vault.classList.contains('hidden')) {
        vault.classList.remove('hidden');
        await fetchQuarantineFiles(); // Açılınca verileri çek
    } else {
        vault.classList.add('hidden');
    }
}

async function fetchQuarantineFiles() {
    const tableBody = document.getElementById('quarantine-table-body');
    tableBody.innerHTML = '<tr><td colspan="3" class="pt-4 text-center text-gray-500">Kasa taranıyor...</td></tr>';
    
    try {
        const response = await fetch(`${API_BASE}/api/quarantine`);
        const result = await response.json();

        tableBody.innerHTML = ''; 

        if (result.data.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="3" class="pt-4 text-center text-green-500 font-bold">Kasa Temiz. Zararlı yazılım bulunamadı.</td></tr>';
            return;
        }

        result.data.forEach(file => {
            tableBody.innerHTML += `
                <tr class="hover:bg-gray-900 transition">
                    <td class="py-3 border-b border-gray-800 text-red-400 font-bold">${file.filename}</td>
                    <td class="py-3 border-b border-gray-800 text-gray-300">${file.ip_source}</td>
                    <td class="py-3 border-b border-gray-800 text-right text-yellow-500">${file.size}</td>
                </tr>
            `;
        });
    } catch (error) {
        tableBody.innerHTML = '<tr><td colspan="3" class="pt-4 text-center text-red-500">Veri çekilemedi. API kapalı olabilir.</td></tr>';
    }
}


function getThreatBadge(label) {
    if (!label) return `<span class="bg-gray-600 text-gray-200 px-2 py-1 rounded text-xs font-bold">BİLİNMEYEN</span>`;

    let colorClass = "bg-gray-600 text-gray-200"; 
    let displayName = label;

    if (label.includes("WEB_")) {
        if (label === "WEB_WP_BRUTEFORCE") { colorClass = "bg-fuchsia-900 text-fuchsia-300"; displayName = "WP KABA KUVVET"; }
        else if (label === "WEB_ENV_EXPLOIT") { colorClass = "bg-red-900 text-red-300"; displayName = "ENV SIZINTISI"; }
        else if (label === "WEB_SQL_INJECTION") { colorClass = "bg-orange-900 text-orange-300"; displayName = "SQL INJECTION"; }
        else { colorClass = "bg-purple-900 text-purple-300"; displayName = "WEB TARAMASI"; }
    } 
    else if (label.includes("SSH_")) {
        if (label === "SSH_MALWARE_DOWNLOAD") { colorClass = "bg-red-600 text-white animate-pulse shadow-lg shadow-red-500/50"; displayName = "ZARARLI YAZILIM"; }
        else if (label === "SSH_DESTRUCTIVE_ACTION") { colorClass = "bg-red-800 text-red-200"; displayName = "SİSTEM İMHASI"; }
        else if (label === "SSH_PAYLOAD_EXECUTION") { colorClass = "bg-orange-600 text-white"; displayName = "VİRÜS ÇALIŞTIRMA"; }
        else if (label === "SSH_RECONNAISSANCE") { colorClass = "bg-blue-900 text-blue-300"; displayName = "SİSTEM KEŞFİ"; }
        else if (label === "SSH_AUTH_ATTEMPT") { colorClass = "bg-gray-700 text-gray-300"; displayName = "ŞİFRE DENEMESİ"; }
        else { colorClass = "bg-yellow-900 text-yellow-300"; displayName = "SSH EXPLOIT"; }
    }

    return `<span class="${colorClass} px-2 py-1 rounded text-xs font-bold tracking-wide">${displayName}</span>`;
}

function createRow(log) {
    return `
        <tr class="hover:bg-gray-700 transition duration-150">
            <td class="p-4 border-b border-gray-700 text-sm">${log.timestamp.split('.')[0]}</td>
            <td class="p-4 border-b border-gray-700 font-bold text-red-400">${log.ip_address}</td>
            <td class="p-4 border-b border-gray-700 text-gray-400">${log.username} : <span class="text-gray-500">${log.password}</span></td>
            <td class="p-4 border-b border-gray-700">${getThreatBadge(log.threat_label)}</td>
            <td class="p-4 border-b border-gray-700 text-yellow-300 font-bold">> ${log.command}</td>
            <td class="p-4 border-b border-gray-700 text-center space-x-2">
                <button onclick="blockIp('${log.ip_address}')" class="bg-red-600 hover:bg-red-700 text-white px-3 py-1 rounded text-xs font-bold transition">Engelle</button>
                <button onclick="unblockIp('${log.ip_address}')" class="bg-emerald-600 hover:bg-emerald-700 text-white px-3 py-1 rounded text-xs font-bold transition">Yasağı Kaldır</button>
            </td>
        </tr>
    `;
}

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
        fetchLogs(); 
    } catch (error) { alert("Bağlantı hatası!"); }
}

async function unblockIp(ip) {
    if(!confirm(ip + " adresinin yasağını kaldırmak istiyor musunuz?")) return;
    try {
        const response = await fetch(`${API_BASE}/api/unblock/${ip}`, { method: 'DELETE' });
        const result = await response.json();
        if (result.status === 'success') {
            alert("✅ YASAK KALDIRILDI: " + ip);
            fetchLogs(); 
        } else {
            alert("Hata: " + result.message);
        }
    } catch (error) { alert("Bağlantı hatası!"); }
}

fetchLogs();

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
        console.log("WebSocket Verisi: ", event.data); 
    }
};