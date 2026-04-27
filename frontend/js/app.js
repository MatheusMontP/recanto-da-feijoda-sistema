/**
 * Recanto da Feijoada — Roteirizador de Entregas
 * Main App Entrypoint (ES Modules)
 */

import { processRouteStream as apiProcessRoute, syncGoogleDistance as apiSyncGoogleDistance } from './modules/api.js';
import { refreshIcons, initIconObserver } from './modules/utils.js';
import { generatePrintReceipt } from './modules/printer.js';
import * as exporter from './modules/export.js';

const { createApp, ref, computed, watch, nextTick } = Vue;

// Initialize global observers
initIconObserver();

const App = {
    setup() {
        const newAddress = ref("");
        const newComplement = ref("");
        const newAmount = ref(1);
        const activeBlockIndex = ref(0);
        const blocks = ref([
            { orders: [], results: null, isProcessing: false, isSyncing: false, errorMessage: "", isOptimizedView: true, manualDistance: null, progressPercentage: 0, progressStatus: "", progressMessage: "" },
            { orders: [], results: null, isProcessing: false, isSyncing: false, errorMessage: "", isOptimizedView: true, manualDistance: null, progressPercentage: 0, progressStatus: "", progressMessage: "" },
            { orders: [], results: null, isProcessing: false, isSyncing: false, errorMessage: "", isOptimizedView: true, manualDistance: null, progressPercentage: 0, progressStatus: "", progressMessage: "" }
        ]);
        const returnToOrigin = ref(true);
        const toastMessage = ref("");

        // ── Persistence ──
        function saveState() {
            localStorage.setItem("recanto-logistics-state", JSON.stringify({
                blocks: blocks.value,
                returnToOrigin: returnToOrigin.value,
                activeBlockIndex: activeBlockIndex.value
            }));
        }

        function loadState() {
            const saved = localStorage.getItem("recanto-logistics-state");
            if (saved) {
                try {
                    const data = JSON.parse(saved);
                    blocks.value = data.blocks.map(b => ({ 
                        ...b, 
                        isProcessing: false, 
                        errorMessage: "",
                        progressPercentage: 0,
                        progressStatus: "",
                        progressMessage: ""
                    }));
                    returnToOrigin.value = data.returnToOrigin;
                    activeBlockIndex.value = data.activeBlockIndex || 0;
                } catch (e) {
                    console.error("Erro ao carregar estado salvo", e);
                }
            }
        }

        watch([blocks, returnToOrigin, activeBlockIndex], saveState, { deep: true });

        // ── Active Block Proxies ──
        const orders = computed({
            get: () => blocks.value[activeBlockIndex.value].orders,
            set: (val) => { blocks.value[activeBlockIndex.value].orders = val; }
        });
        const results = computed({
            get: () => blocks.value[activeBlockIndex.value].results,
            set: (val) => { blocks.value[activeBlockIndex.value].results = val; }
        });
        const isProcessing = computed({
            get: () => blocks.value[activeBlockIndex.value].isProcessing,
            set: (val) => { blocks.value[activeBlockIndex.value].isProcessing = val; }
        });
        const errorMessage = computed({
            get: () => blocks.value[activeBlockIndex.value].errorMessage,
            set: (val) => { blocks.value[activeBlockIndex.value].errorMessage = val; }
        });
        const isOptimizedView = computed({
            get: () => blocks.value[activeBlockIndex.value].isOptimizedView,
            set: (val) => { blocks.value[activeBlockIndex.value].isOptimizedView = val; }
        });
        const isSyncing = computed({
            get: () => blocks.value[activeBlockIndex.value].isSyncing,
            set: (val) => { blocks.value[activeBlockIndex.value].isSyncing = val; }
        });
        const manualDistance = computed({
            get: () => blocks.value[activeBlockIndex.value].manualDistance,
            set: (val) => { blocks.value[activeBlockIndex.value].manualDistance = val; }
        });
        const progressPercentage = computed({
            get: () => blocks.value[activeBlockIndex.value].progressPercentage,
            set: (val) => { blocks.value[activeBlockIndex.value].progressPercentage = val; }
        });
        const progressStatus = computed({
            get: () => blocks.value[activeBlockIndex.value].progressStatus,
            set: (val) => { blocks.value[activeBlockIndex.value].progressStatus = val; }
        });
        const progressMessage = computed({
            get: () => blocks.value[activeBlockIndex.value].progressMessage,
            set: (val) => { blocks.value[activeBlockIndex.value].progressMessage = val; }
        });

        function toggleManualDistance() {
            if (manualDistance.value === null) {
                manualDistance.value = currentDistance.value;
            } else {
                manualDistance.value = null;
            }
        }

        // ── Dark mode ──
        const isDark = ref(localStorage.getItem("recanto-dark") === "true");
        if (isDark.value) document.documentElement.classList.add("dark");

        function toggleDark() {
            isDark.value = !isDark.value;
            document.documentElement.classList.toggle("dark", isDark.value);
            localStorage.setItem("recanto-dark", isDark.value);
            refreshIcons(nextTick);
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
            refreshIcons(nextTick);
        }

        function cancelEdit() {
            editingIndex.value = -1;
            refreshIcons(nextTick);
        }

        function saveEdit() {
            if (editingIndex.value < 0) return;
            if (!editAddress.value.trim() || editAmount.value < 1) return;
            orders.value[editingIndex.value].address = editAddress.value.trim();
            orders.value[editingIndex.value].complement = editComplement.value.trim();
            orders.value[editingIndex.value].amount = editAmount.value;
            editingIndex.value = -1;
            results.value = null;
            refreshIcons(nextTick);
        }

        // ── List Helpers ──
        function moveUp(index) {
            if (index <= 0) return;
            const tmp = orders.value[index];
            orders.value[index] = orders.value[index - 1];
            orders.value[index - 1] = tmp;
            orders.value = [...orders.value];
            results.value = null;
            refreshIcons(nextTick);
        }

        function moveDown(index) {
            if (index >= orders.value.length - 1) return;
            const tmp = orders.value[index];
            orders.value[index] = orders.value[index + 1];
            orders.value[index + 1] = tmp;
            orders.value = [...orders.value];
            results.value = null;
            refreshIcons(nextTick);
        }

        // ── Route Logic ──
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

        watch([currentViewList, isOptimizedView, hasResults], () => refreshIcons(nextTick));
        watch(orders, () => refreshIcons(nextTick), { deep: true });

        // ── Actions ──
        function showToast(msg) {
            toastMessage.value = msg;
            setTimeout(() => { toastMessage.value = ""; }, 2500);
            refreshIcons(nextTick);
        }

        const toggleManualDistance = () => {
            if (manualDistance.value === null) {
                manualDistance.value = currentDistance.value;
            } else {
                manualDistance.value = null;
            }
        };

        function addOrder() {
            if (!newAddress.value.trim() || newAmount.value < 1) return;
            if (orders.value.length >= 15) return;
            orders.value.push({ address: newAddress.value.trim(), complement: newComplement.value.trim(), amount: newAmount.value });
            newAddress.value = ""; newComplement.value = ""; newAmount.value = 1;
            errorMessage.value = "";
            refreshIcons(nextTick);
        }

        async function processRoute() {
            if (orders.value.length === 0) return;
            isProcessing.value = true;
            results.value = null;
            errorMessage.value = "";
            editingIndex.value = -1;
            
            // Inicializa progresso
            progressPercentage.value = 0;
            progressStatus.value = "Iniciando...";
            progressMessage.value = "Preparando pedidos para otimização.";
            
            try {
                const data = await apiProcessRoute(orders.value, returnToOrigin.value, (progress) => {
                    // Callback de progresso
                    if (progress.step === "consolidating") {
                        progressPercentage.value = 5;
                        progressStatus.value = "Consolidando";
                        progressMessage.value = progress.message;
                    } else if (progress.step === "geocoding") {
                        const base = 5;
                        const range = 80;
                        const p = Math.floor(base + (progress.current / progress.total) * range);
                        progressPercentage.value = p;
                        progressStatus.value = `Geocodificando (${progress.current}/${progress.total})`;
                        progressMessage.value = `Localizando: ${progress.address}`;
                    } else if (progress.step === "optimizing") {
                        progressPercentage.value = 90;
                        progressStatus.value = "Otimizando";
                        progressMessage.value = progress.message;
                    }
                });

                progressPercentage.value = 100;
                progressStatus.value = "Concluído!";
                
                results.value = data;
                isOptimizedView.value = true;
                
                if (data.errors && data.errors.length > 0) {
                    showToast(`⚠️ ${data.errors.length} endereço(s) não localizado(s)`);
                }
            } catch (e) {
                errorMessage.value = e.message;
            } finally {
                isProcessing.value = false;
                refreshIcons(nextTick);
            }
        }

        // ── Export Wrappers ──
        function exportWhatsApp() {
            const dist = manualDistance.value || currentDistance.value;
            const text = exporter.buildRouteText(results.value, activeBlockIndex.value, isOptimizedView.value, returnToOrigin.value, currentViewList.value, dist);
            exporter.exportWhatsApp(text);
            showToast("Abrindo WhatsApp…");
        }

        function exportClipboard() {
            const dist = manualDistance.value || currentDistance.value;
            const text = exporter.buildRouteText(results.value, activeBlockIndex.value, isOptimizedView.value, returnToOrigin.value, currentViewList.value, dist);
            exporter.exportClipboard(text).then(() => showToast("Rota copiada!"));
        }

        function exportCSV() {
            exporter.exportCSV(currentViewList.value);
            showToast("CSV baixado!");
        }

        function exportPrint() {
            const dist = manualDistance.value || currentDistance.value;
            generatePrintReceipt(results.value, activeBlockIndex.value, isOptimizedView.value, dist);
            showToast("Recibo gerado!");
        }

        function exportGoogleMaps() {
            exporter.exportGoogleMaps(currentViewList.value, returnToOrigin.value);
            showToast("Abrindo Google Maps…");
        }
        loadState();

        return {
            newAddress, newComplement, newAmount, orders, isProcessing, errorMessage, results,
            hasResults, isOptimizedView, manualDistance, currentViewList, currentDistance, toastMessage,
            geoErrors, activeBlockIndex, blocks, returnToOrigin, isDark, toggleDark,
            editingIndex, editAddress, editComplement, editAmount, startEdit, cancelEdit, saveEdit,
            moveUp, moveDown, addOrder, processRoute, toggleManualDistance, isSyncing,
            exportWhatsApp, exportClipboard, exportCSV, exportPrint, exportGoogleMaps,
            decrementAmount: () => { if (newAmount.value > 1) newAmount.value--; },
            incrementAmount: () => { newAmount.value++; },
            removeOrder: (idx) => { orders.value.splice(idx, 1); results.value = null; refreshIcons(nextTick); },
            clearBlock: () => { orders.value = []; results.value = null; refreshIcons(nextTick); },
            progressPercentage, progressStatus, progressMessage
        };
    },
    mounted() {
        this.$nextTick(() => {
            refreshIcons(this.$nextTick);
        });
    }
};

createApp(App).mount("#app");
