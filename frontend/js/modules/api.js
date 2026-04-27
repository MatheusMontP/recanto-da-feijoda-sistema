/**
 * API Module - Backend communication
 */

export async function processRoute(orders, returnToOrigin) {
    const baseUrl = "";
    const res = await fetch(`${baseUrl}/api/optimize_route`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
            orders: orders,
            optimize_for: "distance",
            return_to_origin: returnToOrigin
        }),
    });
    
    if (!res.ok) {
        const err = await res.json().catch(() => null);
        throw new Error(err?.detail || `Erro HTTP ${res.status}`);
    }
    
    return await res.json();
}

/**
 * Versão em stream da otimização para obter progresso em tempo real
 */
export async function processRouteStream(orders, returnToOrigin, onProgress) {
    const baseUrl = "";
    const response = await fetch(`${baseUrl}/api/optimize_route_stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
            orders: orders,
            optimize_for: "distance",
            return_to_origin: returnToOrigin
        }),
    });

    if (!response.ok) {
        const err = await response.json().catch(() => null);
        throw new Error(err?.detail || `Erro HTTP ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop(); // Mantém o resto incompleto no buffer

        for (const line of lines) {
            if (!line.trim()) continue;
            try {
                const data = JSON.parse(line);
                if (data.step === "done") {
                    return data.data;
                }
                onProgress(data);
            } catch (e) {
                console.error("Erro ao processar linha do stream:", e);
            }
        }
    }
}

export async function syncGoogleDistance(origin, stops, returnToOrigin) {
    const baseUrl = "";
    const res = await fetch(`${baseUrl}/api/sync_google_distance`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
            origin,
            stops,
            return_to_origin: returnToOrigin
        }),
    });
    
    if (!res.ok) {
        const err = await res.json().catch(() => null);
        throw new Error(err?.detail || `Erro HTTP ${res.status}`);
    }
    
    return await res.json();
}
