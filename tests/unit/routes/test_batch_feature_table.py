"""
Tests for BatchFeatureTable routes
"""
from http import HTTPStatus
from unittest.mock import patch

import pytest
from bson.objectid import ObjectId

from featurebyte.models.base import DEFAULT_CATALOG_ID
from tests.unit.routes.base import BaseAsyncApiTestSuite


class TestBatchFeatureTableApi(BaseAsyncApiTestSuite):
    """
    Tests for BatchFeatureTable route
    """

    class_name = "BatchFeatureTable"
    base_route = "/batch_feature_table"
    payload = BaseAsyncApiTestSuite.load_payload(
        "tests/fixtures/request_payloads/batch_feature_table.json"
    )
    random_id = str(ObjectId())

    create_conflict_payload_expected_detail_pairs = [
        (
            payload,
            f'BatchFeatureTable (id: "{payload["_id"]}") already exists. '
            f'Get the existing object by `BatchFeatureTable.get(name="{payload["name"]}")`.',
        ),
        (
            {**payload, "_id": str(ObjectId())},
            f'BatchFeatureTable (name: "{payload["name"]}") already exists. '
            f'Get the existing object by `BatchFeatureTable.get(name="{payload["name"]}")`.',
        ),
    ]
    create_unprocessable_payload_expected_detail_pairs = [
        (
            {
                **payload,
                "_id": str(ObjectId()),
                "name": "random_name",
                "batch_request_table_id": random_id,
            },
            f'BatchRequestTable (id: "{random_id}") not found. Please save the BatchRequestTable object first.',
        ),
        (
            {**payload, "_id": str(ObjectId()), "name": "random_name", "deployment_id": random_id},
            f'Deployment (id: "{random_id}") not found. Please save the Deployment object first.',
        ),
    ]

    @pytest.fixture(autouse=True)
    def mock_online_enable_service_update_data_warehouse(self):
        """Mock _update_data_warehouse method in OnlineEnableService to make it a no-op"""
        with patch("featurebyte.service.deploy.OnlineEnableService.update_data_warehouse"):
            yield

    def setup_creation_route(self, api_client, catalog_id=DEFAULT_CATALOG_ID):
        """
        Setup for post route
        """
        api_object_filename_pairs = [
            ("feature_store", "feature_store"),
            ("entity", "entity"),
            ("context", "context"),
            ("batch_request_table", "batch_request_table"),
            ("event_table", "event_table"),
            ("feature", "feature_sum_30m"),
            ("feature_list", "feature_list_single"),
            ("deployment", "deployment"),
        ]
        for api_object, filename in api_object_filename_pairs:
            payload = self.load_payload(f"tests/fixtures/request_payloads/{filename}.json")
            response = api_client.post(
                f"/{api_object}",
                headers={"active-catalog-id": str(catalog_id)},
                json=payload,
            )
            if api_object == "feature":
                self.make_feature_production_ready(api_client, response.json()["_id"], catalog_id)

            if api_object in {"batch_request_table", "deployment"}:
                response = self.wait_for_results(api_client, response)
                assert response.json()["status"] == "SUCCESS"
            else:
                assert response.status_code == HTTPStatus.CREATED

    def multiple_success_payload_generator(self, api_client):
        """Create multiple payload for setting up create_multiple_success_responses fixture"""
        _ = api_client
        for i in range(3):
            payload = self.payload.copy()
            payload["_id"] = str(ObjectId())
            payload["name"] = f'{self.payload["name"]}_{i}'
            yield payload