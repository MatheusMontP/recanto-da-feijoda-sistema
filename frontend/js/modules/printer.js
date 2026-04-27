/**
 * Printer Module - Thermal receipt generation
 */

export function generatePrintReceipt(data, blockIndex, isOptimized, currentDistance) {
    const list = isOptimized ? data.optimized.route : data.original.route;
    const optText = isOptimized ? "OTIMIZADA" : "ORIGINAL";
    const date = new Date().toLocaleDateString("pt-BR");
    
    let stopsHtml = `
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
            ${n.not_found ? '<br><b style="color:#000">[!] LOCALIZAR MANUALMENTE</b>' : ""}
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
                margin: 0 auto; padding: 10px; color: #000; background: #f1f1f1;
            }
            .paper {
                background: #fff; margin: 0 auto; padding: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
            .w80 { width: 80mm; font-size: 13px; }
            .w58 { width: 58mm; font-size: 11px; }
            .header { text-align: center; margin-bottom: 10px; }
            .header h1 { font-size: 1.2em; margin: 0; }
            .header h2 { font-size: 1em; margin: 5px 0; font-weight: normal; }
            .divider { text-align: center; overflow: hidden; white-space: nowrap; margin: 5px 0; }
            .stop { margin-bottom: 5px; line-height: 1.3; }
            .footer { text-align: center; margin-top: 10px; font-weight: bold; }
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
            function setWidth(c) { document.getElementById('paper').className = 'paper ' + c; }
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
            </div>
            <div class="divider">================================</div>
            ${stopsHtml}
            <div class="footer">
                TOTAL: ${data.summary.total_stops} paradas<br>
                ENTREGAR: ${data.summary.total_amount} feijoadas<br><br>
                --- BOM TRABALHO ---
            </div>
        </div>
        <script>setTimeout(() => window.print(), 500);</script>
        </body></html>
    `);
    win.document.close();
}
