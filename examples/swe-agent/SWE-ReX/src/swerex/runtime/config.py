from typing import Literal

from pydantic import BaseModel, ConfigDict

from swerex.runtime.abstract import AbstractRuntime


class LocalRuntimeConfig(BaseModel):
    """Configuration for a local runtime."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["local"] = "local"
    """Discriminator for (de)serialization/CLI. Do not change."""

    def get_runtime(self) -> AbstractRuntime:
        from swerex.runtime.local import LocalRuntime

        return LocalRuntime.from_config(self)


class RemoteRuntimeConfig(BaseModel):
    auth_token: str
    """The token to use for authentication."""
    host: str = "http://127.0.0.1"
    """The host to connect to."""
    port: int | None = None
    """The port to connect to."""
    timeout: float = 0.15
    """The timeout for the runtime."""

    type: Literal["remote"] = "remote"
    """Discriminator for (de)serialization/CLI. Do not change."""

    model_config = ConfigDict(extra="forbid")

    def get_runtime(self) -> AbstractRuntime:
        from swerex.runtime.remote import RemoteRuntime

        return RemoteRuntime.from_config(self)


class DummyRuntimeConfig(BaseModel):
    """Configuration for a dummy runtime."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["dummy"] = "dummy"
    """Discriminator for (de)serialization/CLI. Do not change."""

    def get_runtime(self) -> AbstractRuntime:
        from swerex.runtime.dummy import DummyRuntime

        return DummyRuntime.from_config(self)


class AGSRuntimeConfig(BaseModel):
    """Configuration for Tencent AGS (Agent Sandbox) runtime."""

    auth_token: str = ""
    """The token for SWE-ReX server authentication (X-API-Key)."""
    ags_token: str = ""
    """The access token for AGS gateway authentication (X-Access-Token)."""
    host: str = "https://127.0.0.1"
    """The host URL to connect to (e.g., https://8080-instance-id.ap-guangzhou.tencentags.com)."""
    port: int | None = None
    """The port to connect to. Usually None since port is embedded in AGS URLs."""
    timeout: float = 60.0
    """The timeout for runtime requests."""

    type: Literal["ags"] = "ags"
    """Discriminator for (de)serialization/CLI. Do not change."""

    model_config = ConfigDict(extra="forbid")

    def get_runtime(self) -> AbstractRuntime:
        from swerex.runtime.ags import AGSRuntime

        return AGSRuntime.from_config(self)


RuntimeConfig = LocalRuntimeConfig | RemoteRuntimeConfig | DummyRuntimeConfig | AGSRuntimeConfig


def get_runtime(config: RuntimeConfig) -> AbstractRuntime:
    return config.get_runtime()
