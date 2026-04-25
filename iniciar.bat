@echo off
echo.
echo  ========================================================
echo        L U C R O M A X I M O   L O G I S T I C S
echo  ========================================================
echo.
echo  [1/2] Ativando ambiente Python e iniciando servidor...

call "%~dp0venv\Scripts\activate.bat"
start "LucroMaximo Server" cmd /k "cd /d "%~dp0backend" && echo Servidor ativo em http://127.0.0.1:8000 && echo Pressione CTRL+C para encerrar. && uvicorn main:app --reload --host 127.0.0.1 --port 8000"

echo  [2/2] Aguardando servidor iniciar...
timeout /t 4 /nobreak >nul

echo  Abrindo navegador...
start http://127.0.0.1:8000/

echo.
echo  Tudo pronto! O sistema esta rodando.
echo  Feche a janela do servidor (cmd preta) para encerrar.
echo.
