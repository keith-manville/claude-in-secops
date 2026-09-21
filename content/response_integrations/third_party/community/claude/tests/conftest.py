from __future__ import annotations

import anthropic
import httpx2
import pytest
from integration_testing.common import use_live_api
from soar_sdk.SiemplifyBase import SiemplifyBase

from claude.core import auth
from claude.tests.core.product import ClaudeMockApi, FakeGoogleCredentials, SoarMockPlatform
from claude.tests.core.session import SoarMockSession

pytest_plugins = ("integration_testing.conftest",)


@pytest.fixture
def claude_api() -> ClaudeMockApi:
    """The mocked Claude API. Queue responses on it and inspect the recorded requests."""
    return ClaudeMockApi()


@pytest.fixture(autouse=True)
def claude_transport(monkeypatch: pytest.MonkeyPatch, claude_api: ClaudeMockApi) -> None:
    """Route the Anthropic SDK's HTTP client to the mocked Claude API."""
    if use_live_api():
        return

    def build_http_client(verify_ssl: bool) -> anthropic.DefaultHttpxClient:  # noqa: ARG001
        return anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(claude_api.handle))

    monkeypatch.setattr(auth, "build_http_client", build_http_client)


@pytest.fixture(autouse=True)
def vertex_credentials(monkeypatch: pytest.MonkeyPatch) -> FakeGoogleCredentials:
    """Replace Google service account credentials so Vertex tests never call the token endpoint."""
    credentials: FakeGoogleCredentials = FakeGoogleCredentials()
    if not use_live_api():
        monkeypatch.setattr(auth, "build_vertex_credentials", lambda _info: credentials)

    return credentials


@pytest.fixture
def soar_platform() -> SoarMockPlatform:
    """The mocked SOAR platform. Inspect it to see which insights, comments and entities were created."""
    return SoarMockPlatform()


@pytest.fixture(autouse=True)
def sdk_session(monkeypatch: pytest.MonkeyPatch, soar_platform: SoarMockPlatform) -> SoarMockSession:
    """Mock the SOAR SDK session and return it to inspect the request history."""
    session: SoarMockSession = SoarMockSession(soar_platform)
    if not use_live_api():
        monkeypatch.setattr(SiemplifyBase, "create_session", lambda *_: session)
        monkeypatch.setattr("requests.Session", lambda: session)

    return session
