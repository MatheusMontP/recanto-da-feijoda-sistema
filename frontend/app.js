/**
 * Recanto da Feijoada — Roteirizador de Entregas
 * Frontend App (Vue 3 Composition API)
 */

const { createApp, ref, computed, watch, nextTick } = Vue;

// Robust icon refresh: calls createIcons multiple times with staggered delays
// to catch all DOM mutations from Vue's reactivity system
function refreshIcons() {
    const run = () => { if (window.lucide) window.lucide.createIcons(); };
    // Immediate (for static elements)
    run();
    // After Vue's nextTick
    nextTick(run);
    // After browser paint
    nextTick(() => { setTimeout(run, 50); });
    nextTick(() => { setTimeout(run, 150); });
}

// MutationObserver: watches for any new <i data-lucide> that Vue injects
// and automatically converts them to SVGs
document.addEventListener("DOMContentLoaded", () => {
    const obs = new MutationObserver(() => {
        const unprocessed = document.querySelectorAll("i[data-lucide]");
        if (unprocessed.length > 0 && window.lucide) {
            window.lucide.createIcons();
        }
    });
    obs.observe(document.body, { childList: true, subtree: true });
});

const App = {
    setup() {
        const newAddress = ref("");
        const newComplement = ref("");
        const newAmount = ref(1);
        const orders = ref([]);
        const isProcessing = ref(false);
        const errorMessage = ref("");
        const results = ref(null);
        const isOptimizedView = ref(true);
        const toastMessage = ref("");

        // ── Dark mode ──
        const isDark = ref(localStorage.getItem("recanto-dark") === "true");
        if (isDark.value) document.documentElement.classList.add("dark");

        function toggleDark() {
            isDark.value = !isDark.value;
            document.documentElement.classList.toggle("dark", isDark.value);
            localStorage.setItem("recanto-dark", isDark.value);
            refreshIcons();
        }

        // ── Edit mode ──
        const editingIndex = ref(-1);
        const editAddress = ref("");
        const editComplement = ref("");
        const editAmount = ref(1);

        function startEdit(index) {
            editingIndex.value = index;
            editAddress.value = orders.value[index].address;
            editComplement.value = orders.value[index].complement || "";
            editAmount.value = orders.value[index].amount;
            refreshIcons();
        }

        function cancelEdit() {
            editingIndex.value = -1;
            refreshIcons();
        }

        function saveEdit() {
            if (editingIndex.value < 0) return;
            if (!editAddress.value.trim() || editAmount.value < 1) return;
            orders.value[editingIndex.value].address = editAddress.value.trim();
            orders.value[editingIndex.value].complement = editComplement.value.trim();
            orders.value[editingIndex.value].amount = editAmount.value;
            editingIndex.value = -1;
            results.value = null; // Invalida resultados anteriores
            refreshIcons();
        }

        // ── Reorder ──
        function moveUp(index) {
            if (index <= 0) return;
            const tmp = orders.value[index];
            orders.value[index] = orders.value[index - 1];
            orders.value[index - 1] = tmp;
            // Force reactivity
            orders.value = [...orders.value];
            results.value = null;
            refreshIcons();
        }

        function moveDown(index) {
            if (index >= orders.value.length - 1) return;
            const tmp = orders.value[index];
            orders.value[index] = orders.value[index + 1];
            orders.value[index + 1] = tmp;
            orders.value = [...orders.value];
            results.value = null;
            refreshIcons();
        }

        // ── Computed ──
        const hasResults = computed(() => results.value !== null);
        const currentViewList = computed(() => {
            if (!hasResults.value) return [];
            return isOptimizedView.value ? results.value.optimized.route : results.value.original.route;
        });
        const currentDistance = computed(() => {
            if (!hasResults.value) return 0;
            return isOptimizedView.value ? results.value.optimized.distance_km : results.value.original.distance_km;
        });
        const geoErrors = computed(() => {
            if (!hasResults.value) return [];
            return results.value.errors || [];
        });

        watch([currentViewList, isOptimizedView, hasResults], () => refreshIcons());
        watch(orders, () => refreshIcons(), { deep: true });
        watch(editingIndex, () => refreshIcons());

        // ── Toast helper ──
        let toastTimer = null;
        function showToast(msg) {
            toastMessage.value = msg;
            clearTimeout(toastTimer);
            toastTimer = setTimeout(() => { toastMessage.value = ""; }, 2500);
            refreshIcons();
        }

        // ── Actions ──
        function decrementAmount() { if (newAmount.value > 1) newAmount.value--; }
        function incrementAmount() { newAmount.value++; }

        function addOrder() {
            if (!newAddress.value.trim() || newAmount.value < 1) return;
            if (orders.value.length >= 12) return;
            orders.value.push({ address: newAddress.value.trim(), complement: newComplement.value.trim(), amount: newAmount.value });
            newAddress.value = "";
            newComplement.value = "";
            newAmount.value = 1;
            errorMessage.value = "";
            refreshIcons();
        }

        function removeOrder(index) {
            orders.value.splice(index, 1);
            if (editingIndex.value === index) editingIndex.value = -1;
            results.value = null;
            refreshIcons();
        }

        function clearBlock() {
            orders.value = [];
            results.value = null;
            errorMessage.value = "";
            editingIndex.value = -1;
            refreshIcons();
        }

        async function processRoute() {
            if (orders.value.length === 0) return;
            isProcessing.value = true;
            results.value = null;
            errorMessage.value = "";
            editingIndex.value = -1;
            
            // Por usarmos o formato 2-em-1 (Backend + Frontend juntos), a URL base 
            // será totalmente relativa. O navegador chamará a API onde quer que o site esteja hospedado.
            const baseUrl = "";

            try {
                const res = await fetch(`${baseUrl}/api/optimize_route`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ orders: orders.value }),
                });
                if (!res.ok) {
                    const err = await res.json().catch(() => null);
                    throw new Error(err?.detail || `Erro HTTP ${res.status}`);
                }
                const data = await res.json();
                results.value = data;
                isOptimizedView.value = true;
                if (data.errors && data.errors.length > 0) {
                    showToast(`⚠️ ${data.errors.length} endereço(s) não localizado(s)`);
                }
            } catch (e) {
                errorMessage.value = e.message;
            } finally {
                isProcessing.value = false;
                refreshIcons();
            }
        }

        // ── Build route text ──
        function _buildRouteText() {
            if (!hasResults.value) return "";
            const mode = isOptimizedView.value ? "Rota Otimizada" : "Ordem de Inserção";
            const list = currentViewList.value;
            const dist = currentDistance.value;
            const total = results.value.summary.total_amount;

            let text = `🍲 RECANTO DA FEIJOADA — Roteiro de Entregas\n`;
            text += `📍 Modo: ${mode}\n`;
            text += `📏 Distância: ${dist} km | 🥘 Total: ${total} feijoadas\n`;
            text += `─────────────────────\n`;
            text += `🏠 ORIGEM: Farolândia, Aracaju\n\n`;

            list.forEach((n, i) => {
                const comp = n.complement ? ` (${n.complement})` : "";
                text += `${i + 1}. ${n.address}${comp} — ${n.amount}× feijoada\n`;
            });

            text += `\n─────────────────────\n`;
            text += `Gerado pelo Roteirizador · recantodafeijoada.netlify.app`;
            return text;
        }

        // ── Export Actions ──
        function exportWhatsApp() {
            const text = _buildRouteText();
            window.open(`https://wa.me/?text=${encodeURIComponent(text)}`, "_blank");
            showToast("Abrindo WhatsApp…");
        }

        function exportClipboard() {
            const text = _buildRouteText();
            navigator.clipboard.writeText(text).then(() => {
                showToast("Rota copiada!");
            }).catch(() => {
                const ta = document.createElement("textarea");
                ta.value = text;
                document.body.appendChild(ta);
                ta.select();
                document.execCommand("copy");
                document.body.removeChild(ta);
                showToast("Rota copiada!");
            });
        }

        function exportCSV() {
            if (!hasResults.value) return;
            const list = currentViewList.value;
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
            showToast("CSV baixado!");
        }

        function exportPrint() {
            if (!hasResults.value) return;
            const list = currentViewList.value;
            const optText = isOptimizedView.value ? "OTIMIZADA" : "ORIGINAL";
            const date = new Date().toLocaleDateString("pt-BR");
            
            let stopsHtml = ``;
            stopsHtml += `
                <div class="stop">
                    <b>[0] PONTO DE PARTIDA</b><br>
                    R. Brasílio Martinho Vale, 46<br>
                    Farolândia, Aracaju
                </div>
                <div class="divider">--------------------------------</div>
            `;
            
            list.forEach((n, i) => {
                stopsHtml += `
                <div class="stop">
                    <b>[${i+1}] ${n.amount}x FEIJ.</b><br>
                    ${n.address}
                    ${n.complement ? `<br><i>Comp: ${n.complement}</i>` : ""}
                </div>
                <div class="divider">--------------------------------</div>
                `;
            });

            const win = window.open("", "_blank");
            win.document.write(`
                <html><head><title>Cupom de Rota</title>
                <style>
                    @import url('https://fonts.googleapis.com/css2?family=Roboto+Mono:wght@400;700&display=swap');
                    * { box-sizing: border-box; }
                    body {
                        font-family: 'Roboto Mono', monospace; 
                        margin: 0 auto; 
                        padding: 10px;
                        color: #000;
                        background: #f1f1f1;
                    }
                    .paper {
                        background: #fff;
                        margin: 0 auto;
                        padding: 10px;
                        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                    }
                    /* Formatos */
                    .w80 { width: 80mm; font-size: 13px; }
                    .w58 { width: 58mm; font-size: 11px; }
                    
                    .header { text-align: center; margin-bottom: 10px; }
                    .header h1 { font-size: 1.2em; margin: 0; }
                    .header h2 { font-size: 1em; margin: 5px 0; font-weight: normal; }
                    .divider { text-align: center; overflow: hidden; white-space: nowrap; margin: 5px 0; }
                    .stop { margin-bottom: 5px; line-height: 1.3; }
                    .footer { text-align: center; margin-top: 10px; font-weight: bold; }
                    
                    /* Menu de Controles - Não aparece na impressão */
                    .controls {
                        display: flex; gap: 10px; justify-content: center; margin-bottom: 20px;
                        background: #333; padding: 15px; border-radius: 6px; color: #fff;
                        font-family: sans-serif;
                    }
                    .controls button {
                        padding: 8px 12px; font-weight: bold; cursor: pointer;
                        border: none; border-radius: 4px; background: #fff; color: #333;
                    }
                    .controls button.primary { background: #D4621A; color: white; }
                    
                    @media print {
                        body { background: transparent; padding: 0; }
                        .paper { box-shadow: none; margin: 0; padding: 0; }
                        .controls { display: none !important; }
                    }
                </style>
                <script>
                    function setWidth(c) {
                        document.getElementById('paper').className = 'paper ' + c;
                    }
                    function doPrint() { window.print(); }
                </script>
                </head><body>
                    
                <div class="controls no-print">
                    <span style="align-self:center">Formato Bobina:</span>
                    <button onclick="setWidth('w80')">80mm</button>
                    <button onclick="setWidth('w58')">58mm</button>
                    <button class="primary" onclick="doPrint()">🖨️ IMPRIMIR</button>
                </div>

                <div id="paper" class="paper w80">
                    <div class="header">
                        <h1>RECANTO DA FEIJOADA</h1>
                        <h2>ROTA ${optText}</h2>
                        <div>Data: ${date}</div>
                        <div>Distância: ${currentDistance.value} km</div>
                    </div>
                    
                    <div class="divider">================================</div>
                    ${stopsHtml}
                    <div class="footer">
                        TOTAL: ${results.value.summary.total_stops} paradas<br>
                        ENTREGAR: ${results.value.summary.total_amount} feijoadas<br><br>
                        --- BOM TRABALHO ---
                    </div>
                </div>
                
                <script>
                    // Aciona o diálogo de impressão assim que abrir (opcional)
                    setTimeout(() => window.print(), 500);
                </script>
                </body></html>
            `);
            win.document.close();
            showToast("Recibo gerado!");
        }

        function exportGoogleMaps() {
            if (!hasResults.value) return;
            const list = currentViewList.value;
            // Google Maps directions: origin / waypoint1 / waypoint2 / ... / destination
            const origin = "-10.97075,-37.06333"; // R. Brasílio Martinho Vale, 46 — Farolândia
            const stops = list.map(n => `${n.lat},${n.lon}`);
            const destination = stops.pop(); // Last stop is destination
            let url = `https://www.google.com/maps/dir/${origin}`;
            stops.forEach(s => { url += `/${s}`; });
            url += `/${destination}`;
            window.open(url, "_blank");
            showToast("Abrindo Google Maps…");
        }

        return {
            newAddress, newComplement, newAmount, orders, isProcessing, errorMessage, results,
            hasResults, isOptimizedView, currentViewList, currentDistance, toastMessage,
            geoErrors,
            isDark, toggleDark,
            editingIndex, editAddress, editComplement, editAmount, startEdit, cancelEdit, saveEdit,
            moveUp, moveDown,
            decrementAmount, incrementAmount, addOrder, removeOrder, clearBlock, processRoute,
            exportWhatsApp, exportClipboard, exportCSV, exportPrint, exportGoogleMaps,
        };
    },
    mounted() { refreshIcons(); },
};

createApp(App).mount("#app");
