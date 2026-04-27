@echo off
setlocal
echo.
echo  ========================================================
echo        R E C A N T O   D A   F E I J O A D A
echo  ========================================================
echo.
echo  [1/2] Ativando ambiente Python e iniciando servidor...

set "ROOT=%~dp0"
set "PYTHON=%ROOT%venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo  ERRO: Python da venv nao encontrado em:
    echo  %PYTHON%
    echo.
    echo  Crie a venv ou ajuste o caminho antes de iniciar.
    pause
    exit /b 1
)

start "Recanto da Feijoada Server" powershell -NoExit -ExecutionPolicy Bypass -Command "Set-Location -LiteralPath '%ROOT%'; Write-Host 'Servidor ativo em http://127.0.0.1:8000'; Write-Host 'Pressione CTRL+C para encerrar.'; & '%PYTHON%' -B -m uvicorn backend.main:app --host 127.0.0.1 --port 8000"

echo  [2/2] Aguardando servidor iniciar...
timeout /t 4 /nobreak >nul

echo  Abrindo navegador...
start http://127.0.0.1:8000/

echo.
echo  Tudo pronto! O sistema esta rodando.
echo  Feche a janela do servidor (cmd preta) para encerrar.
echo.
