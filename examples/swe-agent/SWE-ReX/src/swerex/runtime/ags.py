"""Tencent AGS (Agent Sandbox) Runtime for SWE-ReX.

This runtime connects to Tencent Cloud AGS sandbox instances and uses
X-Access-Token header for authentication instead of X-API-Key.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel
from typing_extensions import Self

from swerex.runtime.remote import RemoteRuntime
from swerex.utils.log import get_logger

if TYPE_CHECKING:
    from swerex.deployment.ags import TencentAGSDeployment

__all__ = ["AGSRuntime"]


class AGSRuntime(RemoteRuntime):
    """Runtime for Tencent AGS (Agent Sandbox).

    This runtime extends RemoteRuntime and uses X-Access-Token header
    instead of X-API-Key for authentication, as required by AGS.

    It also supports automatic token refresh via a token_refresher callback.
    """

    def __init__(
        self,
        *,
        logger: logging.Logger | None = None,
        token_refresher: "TencentAGSDeployment | None" = None,
        **kwargs: Any,
    ):
        """Initialize AGS Runtime.

        Args:
            logger: Logger instance
            token_refresher: Optional deployment instance that can refresh tokens
            **kwargs: Arguments passed to RemoteRuntime (see AGSRuntimeConfig)
        """
        from swerex.runtime.config import AGSRuntimeConfig

        self._config = AGSRuntimeConfig(**kwargs)
        self._token_refresher = token_refresher
        self.logger = logger or get_logger("rex-runtime")
        # Don't add http:// prefix since AGS uses https:// URLs
        if not self._config.host.startswith("http"):
            self.logger.warning("Host %s does not start with http, adding https://", self._config.host)
            self._config.host = f"https://{self._config.host}"

    @classmethod
    def from_config(cls, config: Any) -> Self:
        return cls(**config.model_dump())

    @property
    def _headers(self) -> dict[str, str]:
        """Request headers with both AGS and SWE-ReX server authentication."""
        headers = {}
        # AGS gateway authentication
        if self._config.ags_token:
            headers["X-Access-Token"] = self._config.ags_token
        # SWE-ReX server authentication
        if self._config.auth_token:
            headers["X-API-Key"] = self._config.auth_token
        return headers

    async def _ensure_valid_token(self) -> None:
        """Ensure the AGS token is valid, refresh if needed."""
        if self._token_refresher is not None:
            new_token = await self._token_refresher._ensure_valid_token()
            self._config.ags_token = new_token

    async def _request(self, endpoint: str, payload: BaseModel | None, output_class: Any, num_retries: int = 0):
        """Make a request with automatic token refresh."""
        # Ensure token is valid before making request
        await self._ensure_valid_token()
        return await super()._request(endpoint, payload, output_class, num_retries)
