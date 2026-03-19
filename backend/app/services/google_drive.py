"""Google Drive service: OAuth token exchange, file listing, download, and export."""

import base64
import hashlib
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode

import httpx
import structlog
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

from app.config import get_settings

logger = structlog.get_logger()
settings = get_settings()

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"

SCOPES = "openid email profile https://www.googleapis.com/auth/drive.file"

# Google Workspace MIME types that need export instead of download
EXPORT_MIME_TYPES = {
    "application/vnd.google-apps.document": "application/pdf",
    "application/vnd.google-apps.spreadsheet": "application/pdf",
    "application/vnd.google-apps.presentation": "application/pdf",
}


def _get_fernet() -> Fernet:
    """Derive a Fernet key from the app's SECRET_KEY."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"cognitionshift-google-oauth",
        iterations=100_000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(settings.secret_key.encode()))
    return Fernet(key)


def encrypt_token(token: str) -> str:
    """Encrypt a token string for storage."""
    return _get_fernet().encrypt(token.encode()).decode()


def decrypt_token(encrypted: str) -> str:
    """Decrypt a stored token string."""
    return _get_fernet().decrypt(encrypted.encode()).decode()


class GoogleDriveService:
    """Handles Google OAuth2 flows and Drive API interactions."""

    def __init__(self):
        self.client_id = settings.google_oauth_client_id
        self.client_secret = settings.google_oauth_client_secret
        self.redirect_uri = settings.google_oauth_redirect_uri

    def get_auth_url(self, state: str | None = None) -> str:
        """Build the Google OAuth2 authorization URL."""
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": SCOPES,
            "access_type": "offline",
            "prompt": "consent",
        }
        if state:
            params["state"] = state
        return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> dict:
        """Exchange authorization code for access and refresh tokens."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(GOOGLE_TOKEN_URL, data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": self.redirect_uri,
            })
            resp.raise_for_status()
            return resp.json()

    async def refresh_access_token(self, encrypted_refresh_token: str) -> dict:
        """Use a stored refresh token to get a new access token."""
        refresh_token = decrypt_token(encrypted_refresh_token)
        async with httpx.AsyncClient() as client:
            resp = await client.post(GOOGLE_TOKEN_URL, data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            })
            resp.raise_for_status()
            return resp.json()

    async def get_user_info(self, access_token: str) -> dict:
        """Fetch Google user profile (email, name, picture)."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(GOOGLE_USERINFO_URL, headers={
                "Authorization": f"Bearer {access_token}",
            })
            resp.raise_for_status()
            return resp.json()

    async def _get_valid_token(self, oauth_record) -> str:
        """Return a valid access token, refreshing if expired."""
        if oauth_record.token_expiry and oauth_record.token_expiry > datetime.now(timezone.utc):
            return decrypt_token(oauth_record.access_token)

        # Token expired, refresh it
        token_data = await self.refresh_access_token(oauth_record.refresh_token)
        new_access = token_data["access_token"]
        expires_in = token_data.get("expires_in", 3600)

        # Update stored tokens
        oauth_record.access_token = encrypt_token(new_access)
        oauth_record.token_expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        oauth_record.updated_at = datetime.now(timezone.utc)

        return new_access

    async def list_files(self, oauth_record, page_size: int = 50, page_token: str | None = None) -> dict:
        """List files the user has access to in Drive."""
        access_token = await self._get_valid_token(oauth_record)
        params = {
            "pageSize": page_size,
            "fields": "nextPageToken,files(id,name,mimeType,size,modifiedTime,iconLink,webViewLink)",
            "orderBy": "modifiedTime desc",
        }
        if page_token:
            params["pageToken"] = page_token

        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{DRIVE_API_BASE}/files", params=params, headers={
                "Authorization": f"Bearer {access_token}",
            })
            resp.raise_for_status()
            return resp.json()

    async def download_file(self, oauth_record, file_id: str) -> tuple[bytes, str, str]:
        """
        Download a file from Drive. Returns (data, filename, mime_type).
        Exports Google Workspace files as PDF.
        """
        access_token = await self._get_valid_token(oauth_record)
        headers = {"Authorization": f"Bearer {access_token}"}

        async with httpx.AsyncClient() as client:
            # Get file metadata first
            meta_resp = await client.get(
                f"{DRIVE_API_BASE}/files/{file_id}",
                params={"fields": "id,name,mimeType,size"},
                headers=headers,
            )
            meta_resp.raise_for_status()
            meta = meta_resp.json()

            mime_type = meta.get("mimeType", "application/octet-stream")
            filename = meta.get("name", "unnamed")

            # Google Workspace files need export
            if mime_type in EXPORT_MIME_TYPES:
                export_mime = EXPORT_MIME_TYPES[mime_type]
                resp = await client.get(
                    f"{DRIVE_API_BASE}/files/{file_id}/export",
                    params={"mimeType": export_mime},
                    headers=headers,
                )
                resp.raise_for_status()
                # Append .pdf extension if not already
                if not filename.lower().endswith(".pdf"):
                    filename = f"{filename}.pdf"
                return resp.content, filename, export_mime
            else:
                # Regular file download
                resp = await client.get(
                    f"{DRIVE_API_BASE}/files/{file_id}",
                    params={"alt": "media"},
                    headers=headers,
                )
                resp.raise_for_status()
                return resp.content, filename, mime_type

    async def revoke_token(self, encrypted_refresh_token: str) -> None:
        """Revoke the OAuth token with Google."""
        try:
            refresh_token = decrypt_token(encrypted_refresh_token)
            async with httpx.AsyncClient() as client:
                await client.post(GOOGLE_REVOKE_URL, params={"token": refresh_token})
        except Exception as e:
            logger.warning("google_token_revoke_failed", error=str(e))
