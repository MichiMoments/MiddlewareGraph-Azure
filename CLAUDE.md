# teams_core

Framework-free Python package for Microsoft Teams integration via Microsoft Graph API.
Designed to be consumed by Django, Streamlit, or any other Python project.

> Referencia detallada de clases, métodos y firmas: ver [ARCHITECTURE.md](ARCHITECTURE.md) (local, no versionado).

## Architecture

```
teams_core/
  config.py              # TeamsConfig dataclass, loads .env via python-dotenv
  ports.py               # Protocol interfaces (TokenProvider, MessageSender, MessageReader, FileDownloader, FileUploader, EmailSender, EmailReader, MessageAnalyzer)
  auth/
    scopes.py            # Delegated Graph scopes (10 scopes, includes Files.Read.All, Mail.ReadWrite, Mail.Send)
    cache.py             # EncryptedTokenCache (Fernet-encrypted MSAL cache at rest)
    lock.py              # TokenLock: FileTokenLock (default, single-process) + RedisTokenLock (optional, multi-process)
    provider.py          # MsalTokenProvider (delegated auth, uses lock.create_lock for safe refresh)
  domain/
    models.py            # ConversationRef, Author, Mention, FileAttachment, DownloadedFile, BlobRef, OutboundMessage, InboundMessage, EmailAddress, EmailFileAttachment, OutboundEmail, InboundEmail, MailFolder
  adapters/
    fakes.py             # FakeSender, FakeReader, FakeFileDownloader, FakeFileUploader, FakeEmailSender, FakeEmailReader, make_message(), make_attachment(), make_blob_ref(), make_email(), make_email_address() for testing
    graph/
      client.py          # GraphClient (httpx, retry on 429/503/504, error translation, request_bytes for binary downloads)
      sender.py          # GraphMessageSender + mention_tag() helper
      reader.py          # GraphMessageReader (history + get_one, HTML stripping, attachment parsing)
      downloader.py      # GraphFileDownloader (download file attachments via /shares endpoint)
      subscriptions.py   # SubscriptionManager (create, renew, delete, list_active)
      mail_sender.py   # GraphEmailSender (send email, reply via /me/sendMail and /me/messages/{id}/reply)
      mail_reader.py   # GraphEmailReader (list_messages, get_message, list_folders via /me/messages)
    blob/
      storage.py         # BlobStorageUploader (Azure Blob Storage upload + URL retrieval via container SAS URL)
scripts/
  bootstrap_auth.py      # One-time interactive sign-in to seed the token cache
  test_read.py           # Smoke test: list chats and read recent messages
  test_send.py           # Smoke test: send a message to a Teams chat
  test_poll.py           # Polling test: detect new messages and auto-reply
  test_file.py           # Smoke test: find and download file attachments
  test_blob.py           # Smoke test: upload file to Azure Blob Storage and get URL
  test_mail_read.py    # Smoke test: list mail folders and read inbox
  test_mail_send.py    # Smoke test: send a test email
```

## Key design decisions

- **Delegated access model** (service account), not application-only. Graph has no app permission for normal message sending.
- **Token refresh locking is pluggable**: a local file lock is used by default (single-process deployments); setting `TEAMS_TOKEN_LOCK_URL` switches to a Redis-backed distributed lock for multi-process/multi-host deployments. See `teams_core/auth/lock.py`.
- **Auth flow**: Authorization code with confidential client. One interactive bootstrap, then silent refresh.
- **HTTP**: `msal` + `httpx` (sync). Avoids `msgraph-sdk` which is async-only.
- **Python 3.11+** required.
- **Graph v1.0 only** (`/beta` avoided in production).
- Nothing above the adapter layer imports `httpx`, `msal`, or knows about Graph. Ports are Protocol classes.

## Dependencies

- `msal` - Microsoft Authentication Library
- `httpx` - HTTP client
- `cryptography` - Fernet encryption for token cache
- `redis` (optional, `pip install teams-core[redis]`) - Distributed lock for token refresh in multi-process deployments; not needed for single-process deployments (file lock is used instead)
- `python-dotenv` - Loads `.env` automatically in `TeamsConfig.from_env()`
- `azure-storage-blob` - Azure Blob Storage SDK for file upload/download

## Environment variables

All required, loaded via `TeamsConfig.from_env()`:

| Variable | Purpose |
|---|---|
| `TEAMS_TENANT_ID` | Entra tenant |
| `TEAMS_CLIENT_ID` | App registration client ID |
| `TEAMS_CLIENT_SECRET` | App registration secret (or use cert) |
| `TEAMS_REDIRECT_URI` | OAuth callback (e.g. `http://localhost:8400/callback`) |
| `TEAMS_TOKEN_CACHE_PATH` | File path for encrypted token cache |
| `TEAMS_TOKEN_CACHE_KEY` | Fernet key (32 url-safe base64 bytes) |
| `TEAMS_TOKEN_LOCK_URL` | (optional) Redis URL for refresh lock; if unset, a local file lock is used instead (single-process only) |
| `TEAMS_NOTIFICATION_URL` | Public HTTPS URL for Graph change notifications |
| `TEAMS_LIFECYCLE_URL` | Public HTTPS URL for Graph lifecycle events |
| `TEAMS_CLIENT_STATE` | Random secret echoed by Graph to verify notifications |
| `STORAGE_ACCOUNT_CONNECTION_STRING` | Azure Blob Storage container SAS URL (for file uploads) |

## Flujo de ejecución (setup completo)

El sistema requiere que los pasos se ejecuten en este orden. Cada paso depende del anterior.

```
1. Instalar dependencias
   pip install -e ".[dev]"

2. Configurar variables de entorno
   Copiar .env.example a .env y completar todos los valores.
   Ver tabla "Environment variables" arriba.

3. (Opcional) Levantar Redis, solo si hay múltiples procesos/hosts
   docker run -d -p 6379:6379 redis
   El provider usa un lock para evitar que múltiples procesos
   invaliden el refresh token al renovar simultáneamente. Por
   defecto usa un lock de archivo local (sin dependencias externas),
   suficiente para despliegues de un solo proceso. Si se define
   `TEAMS_TOKEN_LOCK_URL`, usa un lock distribuido en Redis en su
   lugar (necesario si hay más de un proceso u host compartiendo
   el mismo token cache). Instalar el extra con
   `pip install -e ".[redis]"` en ese caso.

4. Bootstrap de autenticación (una sola vez, interactivo)
   python -m scripts.bootstrap_auth
   python -m scripts.bootstrap_auth --no-browser   # solo imprime la URL, no abre el navegador
   Abre el navegador para que el service account inicie sesión.
   Genera el archivo token_cache.enc cifrado con Fernet.
   Debe repetirse si el refresh token expira (~90 días de
   inactividad, verificar por tenant).

5. El sistema está listo para operar
   A partir de aquí, MsalTokenProvider renueva el access token
   silenciosamente usando el cache cifrado + el lock (archivo local
   o Redis, según `TEAMS_TOKEN_LOCK_URL`).
   GraphClient, GraphMessageSender y GraphMessageReader pueden
   instanciarse y usarse.
```


## Common commands

```bash
# Install in dev mode
pip install -e ".[dev]"

# (Optional) install Redis extra + start Redis, only for multi-process deployments
pip install -e ".[redis]"
docker run -d -p 6379:6379 redis

# Bootstrap auth (run once, interactively, as the service account)
python -m scripts.bootstrap_auth                  # opens browser automatically
python -m scripts.bootstrap_auth --no-browser     # prints URL only, no browser

# Run tests
pytest

# Lint
ruff check teams_core/ tests/

# Type check
mypy teams_core/

# Smoke test: list chats and read messages (requires token cache)
python -m scripts.test_read

# Smoke test: send a message (requires token cache)
python -m scripts.test_send

# Polling test: auto-reply to new messages (requires token cache)
python -m scripts.test_poll

# File test: find and download attachments (requires token cache + Files.Read.All scope)
python -m scripts.test_file

# Blob test: upload file to Azure Blob Storage (requires STORAGE_ACCOUNT_CONNECTION_STRING)
python -m scripts.test_blob

# Mail test: list folders and read inbox (requires token cache + Mail.ReadWrite)
python -m scripts.test_mail_read

# Mail test: send a test email (requires token cache + Mail.Send)
python -m scripts.test_mail_send
```

## Important constraints

- The service account must be a **member** of every target chat/team. No app permission bypasses this.
- `<at id="N">` tags in body_html must match the `mentions` array `id` values exactly.
- Stick to safe HTML tags: `<b>`, `<i>`, `<a>`, `<br>`, `<ul>`, `<code>`, `<blockquote>`.
- Change notifications are not guaranteed delivery; always have a backfill path via `history()`.
- Org limit: 10,000 total Teams change-notification subscriptions.
- Token refresh uses a lock (file-based by default, Redis for multi-process). Multiple processes refreshing without locking can invalidate each other's tokens permanently.
- `ReauthRequired` should trigger an alert; refresh tokens can silently expire.

## Items to verify per tenant

- Maximum `chatMessage` subscription lifetime (read from API response)
- Tenant refresh-token inactivity window (platform default ~90 days, can be overridden)
- Which non-`.All` scopes require admin consent under your user-consent policy
- Maximum client-secret lifetime
