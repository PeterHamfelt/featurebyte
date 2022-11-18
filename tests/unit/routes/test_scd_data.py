"""
Tests for SCDData routes
"""
from unittest import mock

import pytest
import pytest_asyncio
from bson import ObjectId

from featurebyte.models.scd_data import SCDDataModel
from featurebyte.schema.scd_data import SCDDataCreate
from featurebyte.service.semantic import SemanticService
from tests.unit.routes.base import BaseDataApiTestSuite


class TestSCDDataApi(BaseDataApiTestSuite):
    """
    TestSCDDataApi class
    """

    class_name = "SCDData"
    base_route = "/scd_data"
    data_create_schema_class = SCDDataCreate
    payload = BaseDataApiTestSuite.load_payload("tests/fixtures/request_payloads/scd_data.json")
    document_name = "sf_scd_data"
    create_conflict_payload_expected_detail_pairs = [
        (
            payload,
            f'{class_name} (id: "{payload["_id"]}") already exists. '
            f'Get the existing object by `{class_name}.get(name="{document_name}")`.',
        ),
        (
            {**payload, "_id": str(ObjectId())},
            f'SCDData (name: "{document_name}") already exists. '
            f'Get the existing object by `SCDData.get(name="{document_name}")`.',
        ),
        (
            {**payload, "_id": str(ObjectId()), "name": "other_name"},
            f"SCDData (tabular_source: \"{{'feature_store_id': "
            f'ObjectId(\'{payload["tabular_source"]["feature_store_id"]}\'), \'table_details\': '
            "{'database_name': 'sf_database', 'schema_name': 'sf_schema', 'table_name': 'sf_scd_table'}}\") "
            f'already exists. Get the existing object by `SCDData.get(name="{document_name}")`.',
        ),
    ]
    create_unprocessable_payload_expected_detail_pairs = [
        (
            {**payload, "tabular_source": ("Some other source", "other table")},
            [
                {
                    "ctx": {"object_type": "TabularSource"},
                    "loc": ["body", "tabular_source"],
                    "msg": "value is not a valid TabularSource type",
                    "type": "type_error.featurebytetype",
                }
            ],
        )
    ]
    update_unprocessable_payload_expected_detail_pairs = []

    @pytest_asyncio.fixture(name="scd_data_semantic_ids")
    async def scd_data_semantic_ids_fixture(self, user_id, persistent):
        """SCD ID semantic IDs fixture"""
        user = mock.Mock()
        user.id = user_id
        semantic_service = SemanticService(user=user, persistent=persistent)
        natural_data = await semantic_service.get_or_create_document("natural_id")
        surrogate_data = await semantic_service.get_or_create_document("surrogate_id")
        return natural_data.id, surrogate_data.id

    @pytest.fixture(name="data_model_dict")
    def data_model_dict_fixture(self, tabular_source, columns_info, user_id, scd_data_semantic_ids):
        """Fixture for a SCD Data dict"""
        natural_id, surrogate_id = scd_data_semantic_ids
        cols_info = []
        for col_info in columns_info:
            col = col_info.copy()
            if col["name"] == "natural_id":
                col["semantic_id"] = natural_id
            elif col["name"] == "surrogate_id":
                col["semantic_id"] = surrogate_id
            cols_info.append(col)

        scd_data_dict = {
            "name": "订单表",
            "tabular_source": tabular_source,
            "columns_info": cols_info,
            "record_creation_date_column": "created_at",
            "status": "PUBLISHED",
            "user_id": str(user_id),
            "natural_key_column": "natural_id",
            "surrogate_key_column": "surrogate_id",
            "effective_timestamp_column": "effective_at",
            "end_timestamp_column": "end_at",
            "current_flag": "current_value",
        }
        output = SCDDataModel(**scd_data_dict).json_dict()
        assert output.pop("created_at") is None
        assert output.pop("updated_at") is None
        return output

    @pytest.fixture(name="data_update_dict")
    def data_update_dict_fixture(self):
        """
        SCD data update dict object
        """
        return {
            "record_creation_date_column": "created_at",
            "natural_key_column": "natural_id",
            "surrogate_key_column": "surrogate_id",
            "effective_timestamp_column": "effective_at",
            "end_timestamp_column": "end_at",
            "current_flag": "current_value",
        }