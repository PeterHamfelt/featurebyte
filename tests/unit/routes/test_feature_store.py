"""
Test for FeatureStore route
"""
from http import HTTPStatus
from unittest.mock import Mock

import pandas as pd
import pytest
from bson.objectid import ObjectId
from pandas.testing import assert_frame_equal

from featurebyte.exception import CredentialsError
from featurebyte.schema.feature_store import FeatureStoreSample
from tests.unit.routes.base import BaseApiTestSuite


class TestFeatureStoreApi(BaseApiTestSuite):
    """
    TestFeatureStoreApi
    """

    class_name = "FeatureStore"
    base_route = "/feature_store"
    payload = BaseApiTestSuite.load_payload("tests/fixtures/request_payloads/feature_store.json")
    create_conflict_payload_expected_detail_pairs = [
        (
            payload,
            f'FeatureStore (id: "{payload["_id"]}") already exists. '
            f'Get the existing object by `FeatureStore.get(name="sf_featurestore")`.',
        ),
        (
            {**payload, "_id": str(ObjectId())},
            'FeatureStore (name: "sf_featurestore") already exists. '
            'Get the existing object by `FeatureStore.get(name="sf_featurestore")`.',
        ),
    ]
    create_unprocessable_payload_expected_detail_pairs = [
        (
            {key: val for key, val in payload.items() if key != "name"},
            [
                {
                    "loc": ["body", "name"],
                    "msg": "field required",
                    "type": "value_error.missing",
                }
            ],
        )
    ]

    def multiple_success_payload_generator(self, api_client):
        """Create multiple payload for setting up create_multiple_success_responses fixture"""
        _ = api_client
        for i in range(3):
            payload = self.payload.copy()
            payload["_id"] = str(ObjectId())
            payload["name"] = f'{self.payload["name"]}_{i}'
            payload["details"] = {
                key: f"{value}_{i}" for key, value in self.payload["details"].items()
            }
            yield payload

    @pytest.mark.asyncio
    async def test_get_info_200(self, test_api_client_persistent, create_success_response):
        """Test retrieve info"""
        test_api_client, _ = test_api_client_persistent
        create_response_dict = create_success_response.json()
        doc_id = create_response_dict["_id"]
        response = test_api_client.get(f"{self.base_route}/{doc_id}/info")
        assert response.status_code == HTTPStatus.OK, response.text
        response_dict = response.json()
        assert (
            response_dict.items()
            > {
                "name": "sf_featurestore",
                "updated_at": None,
                "source": "snowflake",
                "database_details": {
                    "account": "sf_account",
                    "database": "sf_database",
                    "sf_schema": "sf_schema",
                    "warehouse": "sf_warehouse",
                },
            }.items()
        )
        assert "created_at" in response_dict

    def test_list_databases__200(
        self, test_api_client_persistent, create_success_response, mock_get_session
    ):
        """
        Test list databases
        """
        test_api_client, _ = test_api_client_persistent
        assert create_success_response.status_code == HTTPStatus.CREATED
        feature_store = create_success_response.json()

        databases = ["a", "b", "c"]
        mock_get_session.return_value.list_databases.return_value = databases
        response = test_api_client.post(f"{self.base_route}/database", json=feature_store)
        assert response.status_code == HTTPStatus.OK
        assert response.json() == databases

    def test_list_databases__401(
        self,
        test_api_client_persistent,
        create_success_response,
        snowflake_connector,
        mock_get_session,
    ):
        """
        Test list databases with invalid credentials
        """
        test_api_client, _ = test_api_client_persistent
        assert create_success_response.status_code == HTTPStatus.CREATED
        feature_store = create_success_response.json()

        credentials_error = CredentialsError("Invalid credentials provided.")
        snowflake_connector.side_effect = CredentialsError
        mock_get_session.return_value.list_databases.side_effect = credentials_error
        response = test_api_client.post(f"{self.base_route}/database", json=feature_store)
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert response.json() == {"detail": str(credentials_error)}

    def test_list_schemas__422(self, test_api_client_persistent, create_success_response):
        """
        Test list schemas
        """
        test_api_client, _ = test_api_client_persistent
        assert create_success_response.status_code == HTTPStatus.CREATED
        feature_store = create_success_response.json()

        response = test_api_client.post(f"{self.base_route}/schema", json=feature_store)
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert response.json() == {
            "detail": [
                {
                    "loc": ["query", "database_name"],
                    "msg": "field required",
                    "type": "value_error.missing",
                }
            ],
        }

    def test_list_schemas__200(
        self, test_api_client_persistent, create_success_response, mock_get_session
    ):
        """
        Test list schemas
        """
        test_api_client, _ = test_api_client_persistent
        assert create_success_response.status_code == HTTPStatus.CREATED
        feature_store = create_success_response.json()

        schemas = ["a", "b", "c"]
        mock_get_session.return_value.list_schemas.return_value = schemas
        response = test_api_client.post(
            f"{self.base_route}/schema?database_name=x", json=feature_store
        )
        assert response.status_code == HTTPStatus.OK
        assert response.json() == schemas

    def test_list_tables_422(self, test_api_client_persistent, create_success_response):
        """
        Test list tables
        """
        test_api_client, _ = test_api_client_persistent
        assert create_success_response.status_code == HTTPStatus.CREATED
        feature_store = create_success_response.json()

        response = test_api_client.post(f"{self.base_route}/table", json=feature_store)
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert response.json() == {
            "detail": [
                {
                    "loc": ["query", "database_name"],
                    "msg": "field required",
                    "type": "value_error.missing",
                },
                {
                    "loc": ["query", "schema_name"],
                    "msg": "field required",
                    "type": "value_error.missing",
                },
            ],
        }

    def test_list_tables__200(
        self, test_api_client_persistent, create_success_response, mock_get_session
    ):
        """
        Test list tables
        """
        test_api_client, _ = test_api_client_persistent
        assert create_success_response.status_code == HTTPStatus.CREATED
        feature_store = create_success_response.json()

        tables = ["a", "b", "c"]
        mock_get_session.return_value.list_tables.return_value = tables
        response = test_api_client.post(
            f"{self.base_route}/table?database_name=x&schema_name=y", json=feature_store
        )
        assert response.status_code == HTTPStatus.OK
        assert response.json() == tables

    def test_list_columns_422(self, test_api_client_persistent, create_success_response):
        """
        Test list columns
        """
        test_api_client, _ = test_api_client_persistent
        assert create_success_response.status_code == HTTPStatus.CREATED
        feature_store = create_success_response.json()

        response = test_api_client.post(f"{self.base_route}/column", json=feature_store)
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert response.json() == {
            "detail": [
                {
                    "loc": ["query", "database_name"],
                    "msg": "field required",
                    "type": "value_error.missing",
                },
                {
                    "loc": ["query", "schema_name"],
                    "msg": "field required",
                    "type": "value_error.missing",
                },
                {
                    "loc": ["query", "table_name"],
                    "msg": "field required",
                    "type": "value_error.missing",
                },
            ],
        }

    def test_list_columns__200(
        self, test_api_client_persistent, create_success_response, mock_get_session
    ):
        """
        Test list columns
        """
        test_api_client, _ = test_api_client_persistent
        assert create_success_response.status_code == HTTPStatus.CREATED
        feature_store = create_success_response.json()

        columns = {"a": "TIMESTAMP", "b": "INT", "c": "BOOL"}
        mock_get_session.return_value.list_table_schema.return_value = columns
        response = test_api_client.post(
            f"{self.base_route}/column?database_name=x&schema_name=y&table_name=z",
            json=feature_store,
        )
        assert response.status_code == HTTPStatus.OK
        assert response.json() == [
            {"name": "a", "dtype": "TIMESTAMP"},
            {"name": "b", "dtype": "INT"},
            {"name": "c", "dtype": "BOOL"},
        ]

    @pytest.fixture(name="data_sample_payload")
    def data_sample_payload_fixture(
        self, test_api_client_persistent, create_success_response, snowflake_feature_store
    ):
        """Payload for data sample"""
        _ = create_success_response
        test_api_client, _ = test_api_client_persistent
        payload = self.load_payload("tests/fixtures/request_payloads/event_data.json")
        response = test_api_client.post("/event_data", json=payload)
        assert response.status_code == HTTPStatus.CREATED, response.json()

        data_response_dict = response.json()
        return FeatureStoreSample(
            feature_store_name=snowflake_feature_store.name,
            graph={
                "edges": [],
                "nodes": [
                    {
                        "name": "input_1",
                        "output_type": "frame",
                        "parameters": {
                            "type": data_response_dict["type"],
                            "id": "6332fdb21e8f0eeccc414512",
                            "columns": [
                                "col_int",
                                "col_float",
                                "col_char",
                                "col_text",
                                "col_binary",
                                "col_boolean",
                                "event_timestamp",
                                "created_at",
                                "cust_id",
                            ],
                            "table_details": {
                                "database_name": "sf_database",
                                "schema_name": "sf_schema",
                                "table_name": "sf_table",
                            },
                            "feature_store_details": snowflake_feature_store.json_dict(),
                        },
                        "type": "input",
                    },
                ],
            },
            node_name="input_1",
            from_timestamp="2012-11-24T11:00:00",
            to_timestamp="2019-11-24T11:00:00",
            timestamp_column="event_timestamp",
        ).json_dict()

    def test_sample_200(self, test_api_client_persistent, data_sample_payload, mock_get_session):
        """Test data preview (success)"""
        test_api_client, _ = test_api_client_persistent

        expected_df = pd.DataFrame({"a": [0, 1, 2]})
        mock_session = mock_get_session.return_value
        mock_session.execute_query.return_value = expected_df
        mock_session.generate_session_unique_id = Mock(return_value="1")
        response = test_api_client.post("/feature_store/sample", json=data_sample_payload)
        assert response.status_code == HTTPStatus.OK
        assert_frame_equal(pd.read_json(response.json(), orient="table"), expected_df)
        assert mock_session.execute_query.call_args[0][0].endswith(
            "WHERE\n  event_timestamp >= CAST('2012-11-24T11:00:00' AS TIMESTAMP)\n  "
            "AND event_timestamp < CAST('2019-11-24T11:00:00' AS TIMESTAMP)\n"
            "ORDER BY\n  RANDOM(1234)\nLIMIT 10"
        )

    def test_sample_422__no_timestamp_column(self, test_api_client_persistent, data_sample_payload):
        """Test data preview no timestamp column"""
        test_api_client, _ = test_api_client_persistent
        response = test_api_client.post(
            "/feature_store/sample",
            json={
                **data_sample_payload,
                "from_timestamp": "2012-11-24T11:00:00",
                "to_timestamp": None,
                "timestamp_column": None,
            },
        )
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert response.json() == {
            "detail": [
                {
                    "loc": ["body", "__root__"],
                    "msg": "timestamp_column must be specified.",
                    "type": "value_error",
                }
            ]
        }

    def test_sample_422__invalid_timestamp_range(
        self, test_api_client_persistent, data_sample_payload
    ):
        """Test data preview no timestamp column"""
        test_api_client, _ = test_api_client_persistent
        response = test_api_client.post(
            "/feature_store/sample",
            json={
                **data_sample_payload,
                "from_timestamp": "2012-11-24T11:00:00",
                "to_timestamp": "2012-11-20T11:00:00",
            },
        )
        assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert response.json() == {
            "detail": [
                {
                    "loc": ["body", "__root__"],
                    "msg": "from_timestamp must be smaller than to_timestamp.",
                    "type": "assertion_error",
                }
            ]
        }
