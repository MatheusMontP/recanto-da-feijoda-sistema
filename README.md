# Recanto da Feijoada - Roteirizador

Sistema local de roteirizacao de entregas com FastAPI, Vue 3 via CDN, cache SQLite, Nominatim e OSRM.

## Rodar Localmente

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

Tambem existe o atalho:

```powershell
.\iniciar.bat
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

## API

Principais endpoints:

| Metodo | Caminho | Descricao |
|---|---|---|
| `POST` | `/api/optimize_route` | Otimiza uma lista de entregas e retorna JSON completo. |
| `POST` | `/api/optimize_route_stream` | Otimiza com progresso em NDJSON. Usado pelo frontend. |
| `POST` | `/api/sync_google_distance` | Consulta distancia no Google Maps quando disponivel. |

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
