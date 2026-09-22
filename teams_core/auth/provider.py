import logging
from pathlib import Path

import msal

from teams_core.auth.cache import EncryptedTokenCache
from teams_core.auth.lock import create_lock
from teams_core.auth.scopes import SCOPES
from teams_core.config import TeamsConfig

log = logging.getLogger(__name__)


class ReauthRequired(RuntimeError):
    """No usable refresh token. A human must re-run bootstrap_auth."""


class MsalTokenProvider:
    def __init__(self, cfg: TeamsConfig) -> None:
        self._cfg = cfg
        self._cache = EncryptedTokenCache(cfg.token_cache_path, cfg.token_cache_key)
        lock_file = Path(cfg.token_cache_path).with_suffix(".lock")
        self._lock = create_lock(cfg.token_lock_url or None, lock_file)

    def get_token(self) -> str:
        with self._lock:
            token_cache = self._cache.load()
            app = msal.ConfidentialClientApplication(
                client_id=self._cfg.client_id,
                authority=self._cfg.authority,
                client_credential=self._cfg.client_secret,
                token_cache=token_cache,
            )

            accounts = app.get_accounts()
            if not accounts:
                raise ReauthRequired(
                    "Token cache empty -- run scripts/bootstrap_auth.py"
                )

            result = app.acquire_token_silent(SCOPES, account=accounts[0])
            self._cache.save(app.token_cache)

            if not result or "access_token" not in result:
                err = (result or {}).get("error_description", "unknown")
                log.error("Silent token acquisition failed: %s", err)
                raise ReauthRequired(f"Refresh failed: {err}")

            return result["access_token"]
