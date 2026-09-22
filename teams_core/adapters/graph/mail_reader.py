"""Graph adapter for reading emails via /me/messages."""
import logging
from datetime import datetime
from typing import Sequence

from teams_core.adapters.graph.client import GraphClient
from teams_core.domain.models import EmailAddress, InboundEmail, MailFolder

log = logging.getLogger(__name__)


class GraphEmailReader:
    """Implements EmailReader. Reads as the signed-in service account."""

    def __init__(self, client: GraphClient) -> None:
        self._client = client

    def list_messages(
        self, *, folder_id: str | None = None, limit: int = 25
    ) -> Sequence[InboundEmail]:
        path = f"/me/mailFolders/{folder_id or 'Inbox'}/messages"
        params = {
            "$top": min(limit, 50),
            "$orderby": "receivedDateTime desc",
            "$select": (
                "id,subject,bodyPreview,body,from,toRecipients,"
                "ccRecipients,receivedDateTime,isRead,importance,"
                "hasAttachments,conversationId,internetMessageId"
            ),
        }
        items = self._client.paged(path, params=params)
        out: list[InboundEmail] = []
        for raw in items:
            out.append(self._to_domain(raw))
            if len(out) >= limit:
                break
        return out

    def get_message(self, message_id: str) -> InboundEmail:
        raw = self._client.request("GET", f"/me/messages/{message_id}")
        return self._to_domain(raw)

    def list_folders(self) -> Sequence[MailFolder]:
        items = self._client.paged("/me/mailFolders")
        return [
            MailFolder(
                id=f["id"],
                display_name=f.get("displayName", ""),
                total_count=f.get("totalItemCount", 0),
                unread_count=f.get("unreadItemCount", 0),
            )
            for f in items
        ]

    @staticmethod
    def _parse_address(raw: dict | None) -> EmailAddress:
        if not raw:
            return EmailAddress(address="unknown@unknown")
        ea = raw.get("emailAddress") or {}
        return EmailAddress(
            address=ea.get("address", "unknown@unknown"),
            name=ea.get("name"),
        )

    @staticmethod
    def _parse_recipients(raw_list: list[dict] | None) -> tuple[EmailAddress, ...]:
        if not raw_list:
            return ()
        return tuple(GraphEmailReader._parse_address(r) for r in raw_list)

    @staticmethod
    def _to_domain(raw: dict) -> InboundEmail:
        body = raw.get("body") or {}
        received = raw.get("receivedDateTime")
        received_at = (
            datetime.fromisoformat(received.replace("Z", "+00:00"))
            if received
            else None
        )

        return InboundEmail(
            message_id=raw["id"],
            subject=raw.get("subject", ""),
            body_html=body.get("content", ""),
            body_preview=raw.get("bodyPreview", ""),
            from_address=GraphEmailReader._parse_address(raw.get("from")),
            to_recipients=GraphEmailReader._parse_recipients(
                raw.get("toRecipients")
            ),
            cc_recipients=GraphEmailReader._parse_recipients(
                raw.get("ccRecipients")
            ),
            received_at=received_at,
            is_read=raw.get("isRead", False),
            importance=raw.get("importance", "normal"),
            has_attachments=raw.get("hasAttachments", False),
            conversation_id=raw.get("conversationId"),
            internet_message_id=raw.get("internetMessageId"),
        )
