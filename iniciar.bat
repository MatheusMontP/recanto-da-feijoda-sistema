@echo off
setlocal
echo.
echo  ========================================================
echo        R E C A N T O   D A   F E I J O A D A
echo  ========================================================
echo.
echo  [1/4] Preparando servidor local...

set "ROOT=%~dp0"
set "PYTHON=%ROOT%venv\Scripts\python.exe"
set "URL=http://127.0.0.1:8000/app/"

if not exist "%PYTHON%" (
    echo  ERRO: Python da venv nao encontrado em:
    echo  %PYTHON%
    echo.
    echo  Crie a venv ou ajuste o caminho antes de iniciar.
    pause
    exit /b 1
)

echo  [2/4] Liberando porta 8000, se ja estiver em uso...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ports = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue; if ($ports) { $ports | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue } }"

echo  [3/4] Iniciando API em http://127.0.0.1:8000 ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Add-Content -Encoding UTF8 -LiteralPath '%ROOT%uvicorn.out.log' -Value ''; Add-Content -Encoding UTF8 -LiteralPath '%ROOT%uvicorn.out.log' -Value ('===== Inicio ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + ' =====')" 2>nul
start "Recanto da Feijoada - Servidor" powershell -NoExit -ExecutionPolicy Bypass -Command "Set-Location -LiteralPath '%ROOT%'; $OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new(); $env:PYTHONIOENCODING = 'utf-8'; Write-Host ''; Write-Host 'Recanto da Feijoada - servidor local'; Write-Host 'URL: %URL%'; Write-Host 'Logs ao vivo nesta janela e em uvicorn.out.log'; Write-Host 'Para encerrar, pressione CTRL+C nesta janela.'; Write-Host ''; cmd /d /c '\"%PYTHON%\" -B -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 2>&1' | Tee-Object -FilePath '%ROOT%uvicorn.out.log' -Append"

echo  [4/4] Aguardando servidor responder...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ok = $false; for ($i = 0; $i -lt 20; $i++) { try { Invoke-WebRequest -Uri 'http://127.0.0.1:8000/' -UseBasicParsing -TimeoutSec 1 | Out-Null; $ok = $true; break } catch { Start-Sleep -Milliseconds 500 } }; if (-not $ok) { exit 1 }"
if errorlevel 1 (
    echo.
    echo  ERRO: O servidor nao respondeu em http://127.0.0.1:8000
    echo.
    echo  Ultimos logs:
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Content -LiteralPath '%ROOT%uvicorn.out.log' -Tail 80 -ErrorAction SilentlyContinue"
    echo.
    echo  Arquivo completo:
    echo  %ROOT%uvicorn.out.log
    echo.
    pause
    exit /b 1
)

echo  Abrindo navegador em %URL%
start "" "%URL%"

echo.
echo  Tudo pronto! O sistema esta rodando.
echo  Para encerrar, use CTRL+C na janela "Recanto da Feijoada - Servidor".
echo.
