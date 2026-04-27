/**
 * Utils Module - Formatting and Icons
 */

export function refreshIcons(nextTick) {
    const run = () => { if (window.lucide) window.lucide.createIcons(); };
    run();
    if (nextTick) {
        nextTick(run);
        nextTick(() => { setTimeout(run, 50); });
        nextTick(() => { setTimeout(run, 150); });
    }
}

export function initIconObserver() {
    document.addEventListener("DOMContentLoaded", () => {
        const obs = new MutationObserver(() => {
            const unprocessed = document.querySelectorAll("i[data-lucide]");
            if (unprocessed.length > 0 && window.lucide) {
                window.lucide.createIcons();
            }
        });
        obs.observe(document.body, { childList: true, subtree: true });
    });
}

export function formatDate(date = new Date()) {
    return date.toLocaleDateString("pt-BR");
}
