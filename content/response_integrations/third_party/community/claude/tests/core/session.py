from __future__ import annotations

from typing import TYPE_CHECKING

from integration_testing import router
from integration_testing.common import get_request_payload
from integration_testing.request import MockRequest
from integration_testing.requests.response import MockResponse
from integration_testing.requests.session import MockSession

from .product import SoarMockPlatform

if TYPE_CHECKING:
    from collections.abc import Iterable

    from integration_testing.requests.session import Response, RouteFunction


class SoarMockSession(MockSession[MockRequest, MockResponse, SoarMockPlatform]):
    """Mock of the SOAR SDK HTTP session used for case wall, insight and entity operations."""

    def get_routed_functions(self) -> Iterable[RouteFunction[Response]]:
        return [
            self.get_case_metadata,
            self.get_alert_full_details,
            self.create_case_insight,
            self.add_comment,
            self.update_entities,
            self.create_entity,
        ]

    @router.get(r"/api/external/v1/sdk/CaseMetadata/[0-9]+")
    def get_case_metadata(self, _: MockRequest) -> MockResponse:
        return MockResponse(content=self._product.case_metadata, status_code=200)

    @router.post(r"/api/external/v1/sdk/AlertFullDetails")
    def get_alert_full_details(self, _: MockRequest) -> MockResponse:
        if self._product.alert is None:
            return MockResponse(content="Alert not found", status_code=404)

        return MockResponse(content=self._product.alert, status_code=200)

    @router.post(r"/api/external/v1/sdk/CreateCaseInsight")
    def create_case_insight(self, request: MockRequest) -> MockResponse:
        self._product.insights.append(get_request_payload(request))
        return MockResponse(content=True, status_code=200)

    @router.post(r"/api/external/v1/cases/comments")
    def add_comment(self, request: MockRequest) -> MockResponse:
        self._product.comments.append(get_request_payload(request))
        return MockResponse(content={}, status_code=200)

    @router.post(r"/api/external/v1/sdk/UpdateEntities")
    def update_entities(self, request: MockRequest) -> MockResponse:
        self._product.entity_updates.append(get_request_payload(request))
        return MockResponse(content={}, status_code=200)

    @router.post(r"/api/external/v1/sdk/CreateEntity")
    def create_entity(self, request: MockRequest) -> MockResponse:
        self._product.created_entities.append(get_request_payload(request))
        return MockResponse(content={}, status_code=200)
