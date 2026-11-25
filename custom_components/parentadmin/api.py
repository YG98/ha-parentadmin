"""Minimal client for the ParentAdmin parent portal (no official API)."""
from __future__ import annotations

import asyncio
from datetime import date

import aiohttp

from .const import BASE_URL, DIARY_PATH, LOGGER, LOGIN_PATH
from .parser import is_login_page

_TIMEOUT = aiohttp.ClientTimeout(total=30)


class ParentAdminError(Exception):
    """Base error."""


class ParentAdminAuthError(ParentAdminError):
    """Credentials rejected."""


class ParentAdminConnectionError(ParentAdminError):
    """Network / server problem."""


class ParentAdminClient:
    """Logs in with the web form and reads pages using the PHP session cookie."""

    def __init__(self, session: aiohttp.ClientSession, email: str, password: str) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._login_lock = asyncio.Lock()

    async def async_login(self) -> None:
        """Log in and verify the session works. Raises on failure."""
        await self._post_login()
        status, html = await self._get(DIARY_PATH, None)
        if status != 200 or is_login_page(html):
            raise ParentAdminAuthError("Login was not accepted")

    async def async_get_page(self, path: str, params: dict | None = None) -> str:
        """Return a portal page, logging in again if the session expired."""
        for attempt in range(2):
            status, html = await self._get(path, params)
            if status == 200 and not is_login_page(html):
                return html
            if attempt == 0:
                LOGGER.debug("Session not valid for %s (HTTP %s), logging in again", path, status)
                await self._relogin()
        raise ParentAdminAuthError("Still logged out after logging in again")

    async def async_get_diary_html(self, day: date) -> str:
        """Return the diary HTML for a day."""
        return await self.async_get_page(DIARY_PATH, {"date": day.isoformat()})

    async def async_get_photo(self, url: str) -> tuple[bytes, str]:
        """Download a diary photo. Returns (bytes, content type)."""
        for attempt in range(2):
            try:
                async with self._session.get(url, timeout=_TIMEOUT) as resp:
                    resp.raise_for_status()
                    content_type = resp.headers.get("Content-Type", "").split(";")[0]
                    body = await resp.read()
            except (aiohttp.ClientError, TimeoutError) as err:
                raise ParentAdminConnectionError(f"Photo download failed: {err}") from err
            # Without a valid session the server returns a placeholder PNG
            # with HTTP 200 instead of the real JPEG.
            placeholder = content_type == "image/png" and url.lower().endswith((".jpg", ".jpeg"))
            if not placeholder:
                return body, content_type or "image/jpeg"
            if attempt == 0:
                await self._relogin()
        raise ParentAdminAuthError("Got placeholder image after logging in again")

    async def _relogin(self) -> None:
        # Both coordinators can notice an expired session at once; log in one at a time.
        async with self._login_lock:
            await self._post_login()

    async def _post_login(self) -> None:
        data = {"uemail": self._email, "pwd": self._password, "Submit": ""}
        try:
            async with self._session.post(
                BASE_URL + LOGIN_PATH, data=data, allow_redirects=False, timeout=_TIMEOUT
            ) as resp:
                await resp.read()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise ParentAdminConnectionError(f"Login request failed: {err}") from err

    async def _get(self, path: str, params: dict | None) -> tuple[int, str]:
        try:
            async with self._session.get(
                BASE_URL + path, params=params, allow_redirects=False, timeout=_TIMEOUT
            ) as resp:
                if resp.status >= 500:
                    raise ParentAdminConnectionError(f"Server error HTTP {resp.status}")
                return resp.status, await resp.text()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise ParentAdminConnectionError(f"Request for {path} failed: {err}") from err
