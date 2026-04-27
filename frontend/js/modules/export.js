/**
 * Export Module - WhatsApp, Clipboard, Maps, CSV
 */

export function buildRouteText(results, blockIndex, isOptimized, returnToOrigin, currentViewList, currentDistance) {
    if (!results) return "";
    const mode = isOptimized ? "Rota Otimizada" : "Ordem de Inserção";
    const total = results.summary.total_amount;

    let text = `🍲 RECANTO DA FEIJOADA — Roteiro de Entregas\n`;
    text += `📦 BLOCO ${blockIndex + 1} — ENTREGADOR ${blockIndex + 1}\n`;
    text += `📍 Modo: ${mode}\n`;
    text += `↩️ Retorno ao Restaurante: ${returnToOrigin ? 'Sim' : 'Não'}\n`;
    text += `🥘 Total: ${total} feijoadas\n`;
    text += `─────────────────────\n`;
    text += `🏠 ORIGEM: Farolândia, Aracaju\n\n`;

    currentViewList.forEach((n, i) => {
        const comp = n.complement ? ` (${n.complement})` : "";
        const manualNote = n.not_found ? " ⚠️ [LOCALIZAR MANUALMENTE]" : "";
        text += `${i + 1}. ${n.address}${comp}${manualNote} — ${n.amount}× feijoada\n`;
    });

    text += `\n─────────────────────\n`;
    text += `Gerado pelo Roteirizador · recantodafeijoada.netlify.app`;
    return text;
}

export function exportWhatsApp(text) {
    window.open(`https://wa.me/?text=${encodeURIComponent(text)}`, "_blank");
}

export function exportClipboard(text) {
    return navigator.clipboard.writeText(text).catch(() => {
        const ta = document.createElement("textarea");
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
    });
}

export function exportCSV(list) {
    let csv = "Parada,Endereço,Complemento,Feijoadas,Latitude,Longitude\n";
    csv += `0,"Recanto da Feijoada — R. Brasílio Martinho Vale, 46, Farolândia, Aracaju","",—,-10.97075,-37.06333\n`;
    list.forEach((n, i) => {
        const comp = n.complement ? n.complement.replace(/"/g, '""') : "";
        csv += `${i + 1},"${n.address.replace(/"/g, '""')}","${comp}",${n.amount},${n.lat},${n.lon}\n`;
    });
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `rota_recanto_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
}

export function exportGoogleMaps(list, returnToOrigin) {
    const origin = encodeURIComponent("R. Brasílio Martinho Vale, 46, Farolândia, Aracaju - SE");
    const stops = list.map(n => {
        let addr = n.address;
        
        // 1. Limpeza de caracteres que quebram a URL do Maps
        addr = addr.replace(/\//g, ' '); 
        
        // 2. Expansão de abreviações para ajudar o Google
        addr = addr.replace(/\bR\.\s+/gi, 'Rua ');
        addr = addr.replace(/\bAv\.\s+/gi, 'Avenida ');
        
        // 3. Garante contexto de Aracaju
        if (!addr.toLowerCase().includes("aracaju")) {
            addr += ", Aracaju - SE";
        }
        
        return encodeURIComponent(addr);
    });
    
    let url = `https://www.google.com/maps/dir/${origin}`;
    if (stops.length > 0) {
        const destination = stops.pop();
        stops.forEach(s => { url += `/${s}`; });
        url += `/${destination}`;
        if (returnToOrigin) url += `/${origin}`;
    }
    window.open(url, "_blank");
}
