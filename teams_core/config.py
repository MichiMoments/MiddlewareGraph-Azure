from dataclasses import dataclass
import os

from dotenv import load_dotenv


@dataclass(frozen=True)
class TeamsConfig:
    tenant_id: str
    client_id: str
    client_secret: str
    redirect_uri: str
    token_cache_path: str
    token_cache_key: str
    notification_url: str
    lifecycle_url: str
    client_state: str
    storage_account_connection_string: str
    token_lock_url: str = ""
    graph_base: str = "https://graph.microsoft.com/v1.0"

    @property
    def authority(self) -> str:
        return f"https://login.microsoftonline.com/{self.tenant_id}"

    @classmethod
    def from_env(cls) -> "TeamsConfig":
        load_dotenv()

        def req(key: str) -> str:
            val = os.environ.get(key)
            if not val:
                raise RuntimeError(f"Missing required env var: {key}")
            return val

        return cls(
            tenant_id=req("TEAMS_TENANT_ID"),
            client_id=req("TEAMS_CLIENT_ID"),
            client_secret=req("TEAMS_CLIENT_SECRET"),
            redirect_uri=req("TEAMS_REDIRECT_URI"),
            token_cache_path=req("TEAMS_TOKEN_CACHE_PATH"),
            token_cache_key=req("TEAMS_TOKEN_CACHE_KEY"),
            token_lock_url=os.environ.get("TEAMS_TOKEN_LOCK_URL", ""),
            notification_url=req("TEAMS_NOTIFICATION_URL"),
            lifecycle_url=req("TEAMS_LIFECYCLE_URL"),
            client_state=req("TEAMS_CLIENT_STATE"),
            storage_account_connection_string=req('STORAGE_ACCOUNT_CONNECTION_STRING'),
        )
