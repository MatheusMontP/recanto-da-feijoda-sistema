# Recanto da Feijoada - Roteirizador

Sistema local de roteirizacao de entregas com FastAPI, Vue 3 via CDN, cache SQLite, Nominatim e OSRM.

## Rodar Localmente

Use o atalho padrao:

```powershell
.\iniciar.bat
```

Ele libera a porta `8000`, inicia o servidor e abre a aplicacao em:

```text
http://127.0.0.1:8000/app/
```

Se o servidor nao subir, veja os logs:

```text
uvicorn.out.log
```

Comando manual equivalente:

```powershell
.\venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Aplicacao:

```text
http://127.0.0.1:8000/app/
```

Documentacao interativa da API:

```text
http://127.0.0.1:8000/docs
```

## Testes

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

Os testes em `tests/` evitam chamadas reais para Nominatim, OSRM e Google Maps. Os arquivos `test_geo.py`, `test_scraper.py` e `test_api_async.py` sao scripts manuais de diagnostico e podem depender de rede ou servidor rodando.

## Configuracao

Variaveis de ambiente suportadas:

| Nome | Padrao | Uso |
|---|---|---|
| `APP_ENV` | `development` | Use `production` para restringir CORS por padrao. |
| `CORS_ORIGINS` | `*` em dev | Lista separada por virgula, exemplo `https://seudominio.com,http://localhost:8000`. |
| `RATE_LIMIT_REQUESTS` | `30` | Maximo de requisicoes por IP + endpoint. |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Janela do rate limit em segundos. |
| `ADMIN_TOKEN` | vazio | Token obrigatorio para endpoints administrativos em producao. |
| `CLEAR_CACHE_ON_STARTUP` | `false` | Use `true` temporariamente para limpar o cache quando o app iniciar. |

## API

Principais endpoints:

| Metodo | Caminho | Descricao |
|---|---|---|
| `POST` | `/api/optimize_route` | Otimiza uma lista de entregas e retorna JSON completo. |
| `POST` | `/api/optimize_route_stream` | Otimiza com progresso em NDJSON. Usado pelo frontend. |
| `POST` | `/api/sync_google_distance` | Consulta distancia no Google Maps quando disponivel. |
| `POST` | `/api/admin/cache/clear` | Limpa o cache SQLite e o cache em memoria. Requer header `X-Admin-Token`. |

## Limpar cache em producao no Render

Opcao sem Shell:

1. No Render, abra o servico da API e adicione `CLEAR_CACHE_ON_STARTUP=true`.
2. Faca deploy ou restart do servico.
3. Depois que ficar Live, remova a variavel ou altere para `false`.
4. Faca deploy ou restart de novo para voltar ao comportamento normal.

Opcao via endpoint:

1. No Render, abra o servico da API e adicione a variavel de ambiente `ADMIN_TOKEN` com um valor secreto.
2. Faca deploy da versao com este endpoint.
3. Chame uma vez:

```powershell
Invoke-RestMethod -Method Post `
  -Uri "https://SEU-SERVICO.onrender.com/api/admin/cache/clear" `
  -Headers @{ "X-Admin-Token" = "SEU_TOKEN" }
```

Resposta esperada:

```json
{"status":"ok","deleted_rows":0,"memory_entries":0}
```

Formato padrao de erro:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Revise os dados enviados e tente novamente.",
    "details": []
  }
}
```

Quando o rate limit e atingido, a API retorna `429` e o header `Retry-After`.
