"""Google Gmail & Calendar API service — handles OAuth flow and API calls."""
import httpx
import base64
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from urllib.parse import urlencode
from app.config import settings


# Google OAuth endpoints
AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1"
CALENDAR_BASE = "https://www.googleapis.com/calendar/v3"
USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

# Required scopes
SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.readonly",
]


def get_auth_url(state: str = "") -> str:
    """Build the Google OAuth authorization URL."""
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "scope": " ".join(SCOPES),
        "access_type": "offline",       # Get refresh token
        "prompt": "consent",            # Always show consent to get refresh token
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code_for_tokens(code: str) -> Dict[str, Any]:
    """Exchange authorization code for access + refresh tokens."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            TOKEN_URL,
            data={
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "code": code,
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )
        response.raise_for_status()
        data = response.json()
        return {
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token"),
            "token_type": data.get("token_type", "Bearer"),
            "scope": data.get("scope", ""),
            "expires_in": data.get("expires_in", 3600),
        }


async def refresh_access_token(refresh_token: str) -> Dict[str, Any]:
    """Use refresh token to get a new access token."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            TOKEN_URL,
            data={
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        response.raise_for_status()
        data = response.json()
        return {
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token", refresh_token),
            "expires_in": data.get("expires_in", 3600),
        }


class GmailClient:
    """Client for Google Gmail and Calendar API calls."""

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    async def get_me(self) -> Dict[str, Any]:
        """Get the authenticated user's profile."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(USERINFO_URL, headers=self.headers)
            resp.raise_for_status()
            return resp.json()

    async def get_emails(
        self,
        query: str = "",
        max_results: int = 20,
    ) -> List[Dict[str, Any]]:
        """Fetch emails from Gmail. Query uses Gmail search syntax (e.g., 'from:john newer_than:7d')."""
        params = {"maxResults": max_results}
        if query:
            params["q"] = query

        async with httpx.AsyncClient() as client:
            # Get message IDs
            resp = await client.get(
                f"{GMAIL_BASE}/users/me/messages",
                headers=self.headers,
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
            message_ids = [m["id"] for m in data.get("messages", [])]

            if not message_ids:
                return []

            # Fetch each message's details (batch would be better but this works for hackathon)
            emails = []
            for msg_id in message_ids[:max_results]:
                msg_resp = await client.get(
                    f"{GMAIL_BASE}/users/me/messages/{msg_id}",
                    headers=self.headers,
                    params={"format": "metadata", "metadataHeaders": ["Subject", "From", "To", "Date"]},
                )
                if msg_resp.status_code != 200:
                    continue
                msg = msg_resp.json()
                emails.append(self._parse_message(msg))

            return emails

    async def get_recent_emails(self, days: int = 7, max_results: int = 30) -> List[Dict[str, Any]]:
        """Get emails from the last N days."""
        return await self.get_emails(query=f"newer_than:{days}d", max_results=max_results)

    async def search_emails(self, query: str, max_results: int = 20) -> List[Dict[str, Any]]:
        """Search emails by keyword."""
        return await self.get_emails(query=query, max_results=max_results)

    async def get_email_body(self, message_id: str) -> str:
        """Get full email body text."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{GMAIL_BASE}/users/me/messages/{message_id}",
                headers=self.headers,
                params={"format": "full"},
            )
            resp.raise_for_status()
            msg = resp.json()
            return self._extract_body(msg.get("payload", {}))

    async def send_email(
        self,
        to: List[str],
        subject: str,
        body: str,
        cc: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Send an email via Gmail API."""
        # Build the raw email
        to_str = ", ".join(to)
        cc_str = ", ".join(cc) if cc else ""

        raw_email = f"To: {to_str}\r\n"
        if cc_str:
            raw_email += f"Cc: {cc_str}\r\n"
        raw_email += f"Subject: {subject}\r\n"
        raw_email += "Content-Type: text/html; charset=utf-8\r\n\r\n"
        raw_email += body

        encoded = base64.urlsafe_b64encode(raw_email.encode()).decode()

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{GMAIL_BASE}/users/me/messages/send",
                headers=self.headers,
                json={"raw": encoded},
            )
            resp.raise_for_status()
            return {"status": "sent", "id": resp.json().get("id")}

    async def get_calendar_events(self, days_ahead: int = 14, max_results: int = 20) -> List[Dict[str, Any]]:
        """Get upcoming calendar events."""
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        end = (datetime.utcnow() + timedelta(days=days_ahead)).strftime("%Y-%m-%dT%H:%M:%SZ")

        params = {
            "timeMin": now,
            "timeMax": end,
            "maxResults": max_results,
            "orderBy": "startTime",
            "singleEvents": "true",
        }

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{CALENDAR_BASE}/calendars/primary/events",
                headers=self.headers,
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
            return [
                {
                    "id": e.get("id"),
                    "subject": e.get("summary", "(No title)"),
                    "start": e.get("start", {}).get("dateTime", e.get("start", {}).get("date", "")),
                    "end": e.get("end", {}).get("dateTime", e.get("end", {}).get("date", "")),
                    "location": e.get("location", ""),
                    "is_online": bool(e.get("hangoutLink") or e.get("conferenceData")),
                    "attendees": [a.get("email", "") for a in e.get("attendees", [])],
                    "organizer": e.get("organizer", {}).get("email", ""),
                }
                for e in data.get("items", [])
            ]

    async def get_emails_for_contact(self, email_or_name: str, days: int = 30, max_results: int = 20) -> List[Dict[str, Any]]:
        """Get emails related to a specific contact (for deal monitoring)."""
        return await self.search_emails(query=f"{email_or_name} newer_than:{days}d", max_results=max_results)

    def _parse_message(self, msg: dict) -> dict:
        """Parse a Gmail message metadata response into a simplified dict."""
        headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
        labels = msg.get("labelIds", [])

        return {
            "id": msg["id"],
            "subject": headers.get("subject", "(No subject)"),
            "from": headers.get("from", ""),
            "from_name": headers.get("from", "").split("<")[0].strip().strip('"'),
            "to": headers.get("to", ""),
            "date": headers.get("date", ""),
            "preview": msg.get("snippet", ""),
            "received": headers.get("date", ""),
            "is_read": "UNREAD" not in labels,
            "importance": "high" if "IMPORTANT" in labels else "normal",
            "has_attachments": any(
                p.get("filename") for p in msg.get("payload", {}).get("parts", [])
            ) if "parts" in msg.get("payload", {}) else False,
        }

    def _extract_body(self, payload: dict) -> str:
        """Extract plain text body from Gmail payload."""
        if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")

        for part in payload.get("parts", []):
            result = self._extract_body(part)
            if result:
                return result
        return ""
