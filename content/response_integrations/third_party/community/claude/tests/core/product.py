"""In-memory mocks of the Claude API and of the SOAR platform endpoints used by the actions."""

from __future__ import annotations

import contextlib
import dataclasses
import json
from collections import deque
from typing import TYPE_CHECKING, Any

import httpx2

from ..common import MOCK_MODEL_ID, MOCK_REQUEST_ID, MOCK_VERTEX_PROJECT, MOCK_VERTEX_REGION
from .mock_data import MOCK_ALERT, MOCK_CASE_METADATA

if TYPE_CHECKING:
    from collections.abc import Iterator

    from TIPCommon.types import JSON, SingleJson


@dataclasses.dataclass(slots=True)
class MockMessage:
    """Specification of the next /v1/messages response."""

    text: str = "OK"
    stop_reason: str = "end_turn"
    structured: JSON | None = None
    stop_details: SingleJson | None = None
    model: str | None = None


@dataclasses.dataclass(slots=True)
class MockApiError:
    status_code: int
    error_type: str
    message: str


@dataclasses.dataclass(slots=True)
class FakeGoogleCredentials:
    """Stand-in for google.auth credentials that never talks to the token endpoint."""

    token: str = "fake-vertex-access-token"
    expired: bool = False

    def refresh(self, _request: Any) -> None:  # noqa: ANN401
        self.expired = False


@dataclasses.dataclass(slots=True)
class ClaudeMockApi:
    """A mock of the Anthropic API and of Claude on Vertex AI served through an httpx2 MockTransport.

    Anthropic API routes: GET /v1/models/{id}, POST /v1/messages.
    Vertex AI routes: POST /v1/projects/{p}/locations/{r}/publishers/anthropic/models/{model}:rawPredict
    and the count-tokens variant.
    """

    model_id: str = MOCK_MODEL_ID
    vertex_project: str = MOCK_VERTEX_PROJECT
    vertex_region: str = MOCK_VERTEX_REGION
    requests: list[SingleJson] = dataclasses.field(default_factory=list)
    model_requests: list[str] = dataclasses.field(default_factory=list)
    count_token_requests: list[SingleJson] = dataclasses.field(default_factory=list)
    request_headers: list[dict[str, str]] = dataclasses.field(default_factory=list)
    request_paths: list[str] = dataclasses.field(default_factory=list)
    _responses: deque[MockMessage] = dataclasses.field(default_factory=deque)
    _errors: deque[MockApiError] = dataclasses.field(default_factory=deque)
    _fail_all: MockApiError | None = None

    # ---------------- Test setup helpers ---------------- #

    def queue_text(self, text: str, stop_reason: str = "end_turn") -> None:
        self._responses.append(MockMessage(text=text, stop_reason=stop_reason))

    def queue_structured(self, structured: JSON, stop_reason: str = "end_turn") -> None:
        self._responses.append(MockMessage(structured=structured, stop_reason=stop_reason))

    def queue_refusal(self, category: str = "cyber", explanation: str = "Request declined.") -> None:
        self._responses.append(
            MockMessage(
                text="",
                stop_reason="refusal",
                stop_details={"type": "refusal", "category": category, "explanation": explanation},
            )
        )

    def fail_next(self, status_code: int = 401, error_type: str = "authentication_error", message: str = "") -> None:
        self._errors.append(MockApiError(status_code, error_type, message or f"mock {error_type}"))

    @contextlib.contextmanager
    def fail_requests(self, status_code: int = 401, error_type: str = "authentication_error") -> Iterator[None]:
        """Fail every request made inside the context."""
        self._fail_all = MockApiError(status_code, error_type, f"mock {error_type}")
        try:
            yield
        finally:
            self._fail_all = None

    @property
    def last_request(self) -> SingleJson:
        return self.requests[-1]

    # ---------------- Transport handler ---------------- #

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        """Route an httpx2 request to the mock endpoint."""
        error: MockApiError | None = self._fail_all or (self._errors.popleft() if self._errors else None)
        if error is not None:
            return httpx2.Response(
                error.status_code,
                json={"type": "error", "error": {"type": error.error_type, "message": error.message}},
                headers={"request-id": MOCK_REQUEST_ID},
                request=request,
            )

        path: str = request.url.path
        self.request_paths.append(path)
        self.request_headers.append(dict(request.headers))
        if request.method == "GET" and path.startswith("/v1/models/"):
            return self._handle_get_model(request, path.rsplit("/", maxsplit=1)[-1])

        if request.method == "POST" and path == "/v1/messages":
            return self._handle_create_message(request)

        vertex_prefix: str = (
            f"/v1/projects/{self.vertex_project}/locations/{self.vertex_region}/publishers/anthropic/models/"
        )
        if request.method == "POST" and path.startswith(vertex_prefix):
            model_and_action: str = path[len(vertex_prefix) :]
            model, _, action = model_and_action.partition(":")
            if model == "count-tokens" and action == "rawPredict":
                return self._handle_count_tokens(request)
            if action == "rawPredict":
                if model != self.model_id:
                    return httpx2.Response(
                        404,
                        json={
                            "error": {
                                "code": 404,
                                "message": f"Publisher Model `{model}` not found",
                                "status": "NOT_FOUND",
                            }
                        },
                        request=request,
                    )
                return self._handle_create_message(request, model=model)

        return httpx2.Response(
            404,
            json={"type": "error", "error": {"type": "not_found_error", "message": f"No route for {path}"}},
            request=request,
        )

    def _handle_get_model(self, request: httpx2.Request, model_id: str) -> httpx2.Response:
        self.model_requests.append(model_id)
        if model_id != self.model_id:
            return httpx2.Response(
                404,
                json={"type": "error", "error": {"type": "not_found_error", "message": f"model: {model_id}"}},
                headers={"request-id": MOCK_REQUEST_ID},
                request=request,
            )

        return httpx2.Response(
            200,
            json={
                "id": model_id,
                "display_name": "Claude Opus 5",
                "type": "model",
                "created_at": "2026-04-01T00:00:00Z",
            },
            headers={"request-id": MOCK_REQUEST_ID},
            request=request,
        )

    def _handle_count_tokens(self, request: httpx2.Request) -> httpx2.Response:
        body: SingleJson = json.loads(request.read())
        self.count_token_requests.append(body)
        return httpx2.Response(200, json={"input_tokens": 7}, headers={"request-id": MOCK_REQUEST_ID}, request=request)

    def _handle_create_message(self, request: httpx2.Request, model: str | None = None) -> httpx2.Response:
        body: SingleJson = json.loads(request.read())
        self.requests.append(body)
        spec: MockMessage = self._responses.popleft() if self._responses else MockMessage()
        text: str = json.dumps(spec.structured) if spec.structured is not None else spec.text
        payload: dict[str, Any] = {
            "id": f"msg_{len(self.requests):03d}",
            "type": "message",
            "role": "assistant",
            "model": spec.model or model or body["model"],
            "content": [{"type": "text", "text": text}] if text else [],
            "stop_reason": spec.stop_reason,
            "stop_sequence": None,
            "usage": {
                "input_tokens": 120,
                "output_tokens": 45,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            },
        }
        if spec.stop_details is not None:
            payload["stop_details"] = spec.stop_details

        return httpx2.Response(200, json=payload, headers={"request-id": MOCK_REQUEST_ID}, request=request)


@dataclasses.dataclass(slots=True)
class SoarMockPlatform:
    """Records the calls the actions make to the SOAR platform."""

    alert: SingleJson | None = dataclasses.field(default_factory=lambda: dict(MOCK_ALERT))
    case_metadata: SingleJson = dataclasses.field(default_factory=lambda: dict(MOCK_CASE_METADATA))
    insights: list[SingleJson] = dataclasses.field(default_factory=list)
    comments: list[SingleJson] = dataclasses.field(default_factory=list)
    entity_updates: list[SingleJson] = dataclasses.field(default_factory=list)
    created_entities: list[SingleJson] = dataclasses.field(default_factory=list)
