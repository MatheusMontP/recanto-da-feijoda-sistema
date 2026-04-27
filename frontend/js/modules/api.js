/**
 * API Module - Backend communication
 */

export class ApiError extends Error {
    constructor(message, { status = 0, code = "API_ERROR", details = [], retryAfter = null } = {}) {
        super(message);
        this.name = "ApiError";
        this.status = status;
        this.code = code;
        this.details = details;
        this.retryAfter = retryAfter;
    }
}

async function parseApiError(response) {
    const payload = await response.json().catch(() => null);
    const error = payload?.error;
    const retryAfter = Number(response.headers.get("Retry-After")) || findRetryAfter(error?.details);

    if (error?.code === "RATE_LIMIT_EXCEEDED") {
        const waitText = retryAfter ? ` Aguarde ${retryAfter}s e tente novamente.` : "";
        return new ApiError(`${error.message}${waitText}`, {
            status: response.status,
            code: error.code,
            details: error.details || [],
            retryAfter,
        });
    }

    return new ApiError(error?.message || payload?.detail || `Erro HTTP ${response.status}`, {
        status: response.status,
        code: error?.code || "HTTP_ERROR",
        details: error?.details || [],
        retryAfter,
    });
}

function findRetryAfter(details = []) {
    const retryDetail = details.find((item) => item && typeof item === "object" && "retry_after" in item);
    return retryDetail ? Number(retryDetail.retry_after) : null;
}

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
        throw await parseApiError(res);
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
        throw await parseApiError(response);
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
        throw await parseApiError(res);
    }
    
    return await res.json();
}
