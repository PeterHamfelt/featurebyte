"""
Test SCD data API object
"""
from unittest.mock import patch

import pytest

from featurebyte.api.entity import Entity
from featurebyte.api.scd_data import SlowlyChangingData
from featurebyte.enum import TableDataType
from featurebyte.exception import DuplicatedRecordException, RecordRetrievalException
from featurebyte.models.feature_store import DataStatus
from tests.unit.api.base_data_test import BaseDataTestSuite, DataType


class TestEventDataTestSuite(BaseDataTestSuite):

    data_type = DataType.DIMENSION_DATA
    col = "col_int"
    expected_columns = {
        "col_char",
        "col_float",
        "col_boolean",
        "event_timestamp",
        "col_text",
        "created_at",
        "col_binary",
        "col_int",
        "cust_id",
    }


@pytest.fixture(name="scd_data_dict")
def scd_data_dict_fixture(snowflake_database_table):
    """SCDData in serialized dictionary format"""
    return {
        "type": TableDataType.SCD_DATA,
        "name": "sf_scd_data",
        "tabular_source": {
            "feature_store_id": snowflake_database_table.feature_store.id,
            "table_details": {
                "database_name": "sf_database",
                "schema_name": "sf_schema",
                "table_name": "sf_table",
            },
        },
        "columns_info": [
            {
                "entity_id": None,
                "name": "col_int",
                "dtype": "INT",
                "semantic_id": None,
                "critical_data_info": None,
            },
            {
                "entity_id": None,
                "name": "col_float",
                "dtype": "FLOAT",
                "semantic_id": None,
                "critical_data_info": None,
            },
            {
                "entity_id": None,
                "name": "col_char",
                "dtype": "CHAR",
                "semantic_id": None,
                "critical_data_info": None,
            },
            {
                "entity_id": None,
                "name": "col_text",
                "dtype": "VARCHAR",
                "semantic_id": None,
                "critical_data_info": None,
            },
            {
                "entity_id": None,
                "name": "col_binary",
                "dtype": "BINARY",
                "semantic_id": None,
                "critical_data_info": None,
            },
            {
                "entity_id": None,
                "name": "col_boolean",
                "dtype": "BOOL",
                "semantic_id": None,
                "critical_data_info": None,
            },
            {
                "entity_id": None,
                "name": "event_timestamp",
                "dtype": "TIMESTAMP_TZ",
                "semantic_id": None,
                "critical_data_info": None,
            },
            {
                "entity_id": None,
                "name": "created_at",
                "dtype": "TIMESTAMP_TZ",
                "semantic_id": None,
                "critical_data_info": None,
            },
            {
                "entity_id": None,
                "name": "cust_id",
                "dtype": "INT",
                "semantic_id": None,
                "critical_data_info": None,
            },
        ],
        "natural_key_column": "col_text",
        "surrogate_key_column": "col_int",
        "effective_timestamp_column": "event_timestamp",
        "end_timestamp_column": "event_timestamp",
        "current_flag": "col_char",
        "record_creation_date_column": "created_at",
        "created_at": None,
        "updated_at": None,
        "user_id": None,
        "status": DataStatus.DRAFT,
    }


def test_from_tabular_source(snowflake_database_table, scd_data_dict):
    """
    Test SCDData creation using tabular source
    """
    scd_data = SlowlyChangingData.from_tabular_source(
        tabular_source=snowflake_database_table,
        name="sf_scd_data",
        natural_key_column="col_text",
        surrogate_key_column="col_int",
        effective_timestamp_column="event_timestamp",
        end_timestamp_column="event_timestamp",
        current_flag_column="col_char",
        record_creation_date_column="created_at",
    )

    # check that node parameter is set properly
    node_params = scd_data.node.parameters
    assert node_params.id == scd_data.id
    assert node_params.type == TableDataType.SCD_DATA

    # check that dimension data columns for autocompletion
    assert set(scd_data.columns).issubset(dir(scd_data))
    assert scd_data._ipython_key_completions_() == set(scd_data.columns)

    output = scd_data.dict()
    scd_data_dict["id"] = scd_data.id
    scd_data_dict["graph"] = output["graph"]
    scd_data_dict["node_name"] = output["node_name"]
    scd_data_dict["current_flag_column"] = scd_data_dict.pop("current_flag")  # DEV-556
    assert output == scd_data_dict

    # user input validation
    with pytest.raises(TypeError) as exc:
        SlowlyChangingData.from_tabular_source(
            tabular_source=snowflake_database_table,
            name=123,
            natural_key_column="col_text",
            surrogate_key_column="col_int",
            effective_timestamp_column="event_timestamp",
            end_timestamp_column="event_timestamp",
            current_flag_column="col_char",
            record_creation_date_column=345,
        )
    assert 'type of argument "name" must be str; got int instead' in str(exc.value)


@pytest.mark.usefixtures("saved_scd_data")
def test_from_tabular_source__duplicated_record(snowflake_database_table):
    """
    Test SCDData creation failure due to duplicated dimension data name
    """
    with pytest.raises(DuplicatedRecordException) as exc:
        SlowlyChangingData.from_tabular_source(
            tabular_source=snowflake_database_table,
            name="sf_scd_data",
            natural_key_column="col_text",
            surrogate_key_column="col_int",
            effective_timestamp_column="event_timestamp",
            end_timestamp_column="event_timestamp",
            current_flag_column="col_char",
            record_creation_date_column="created_at",
        )
    assert 'SlowlyChangingData (scd_data.name: "sf_scd_data") exists in saved record.' in str(
        exc.value
    )


def test_from_tabular_source__retrieval_exception(snowflake_database_table):
    """
    Test SCDData creation failure due to retrieval exception
    """
    with pytest.raises(RecordRetrievalException):
        with patch("featurebyte.api.base_data.Configurations"):
            SlowlyChangingData.from_tabular_source(
                tabular_source=snowflake_database_table,
                name="sf_scd_data",
                natural_key_column="col_text",
                surrogate_key_column="col_int",
                effective_timestamp_column="event_timestamp",
                end_timestamp_column="event_timestamp",
                current_flag_column="col_char",
                record_creation_date_column="created_at",
            )


def assert_info_helper(scd_data_info):
    """
    Helper function to assert info from SCD data.
    """
    assert scd_data_info["entities"] == []
    assert scd_data_info["name"] == "sf_scd_data"
    assert scd_data_info["status"] == "DRAFT"
    assert scd_data_info["natural_key_column"] == "col_text"
    assert scd_data_info["surrogate_key_column"] == "col_int"
    assert scd_data_info["effective_timestamp_column"] == "event_timestamp"
    assert scd_data_info["end_timestamp_column"] == "event_timestamp"
    assert scd_data_info["current_flag_column"] == "col_char"


def test_info(saved_scd_data):
    """
    Test info
    """
    info = saved_scd_data.info()
    assert_info_helper(info)

    # setting verbose = true is a no-op for now
    info = saved_scd_data.info(verbose=True)
    assert_info_helper(info)


def test_scd_data__entity_relation_auto_tagging(saved_scd_data):
    """Test scd data update: entity relation will be created automatically"""
    entity_a = Entity(name="a", serving_names=["a_id"])
    entity_a.save()

    entity_b = Entity(name="b", serving_names=["b_id"])
    entity_b.save()

    # add entities to scd data
    assert saved_scd_data.natural_key_column == "col_text"
    saved_scd_data.col_text.as_entity("a")
    saved_scd_data.cust_id.as_entity("b")

    updated_entity_a = Entity.get_by_id(id=entity_a.id)
    assert updated_entity_a.parents == [
        {"id": entity_b.id, "data_type": "scd_data", "data_id": saved_scd_data.id}
    ]
    updated_entity_b = Entity.get_by_id(id=entity_b.id)
    assert updated_entity_b.parents == []

    # remove primary id column's entity
    saved_scd_data.col_text.as_entity(None)
    updated_entity_a = Entity.get_by_id(id=entity_a.id)
    assert updated_entity_a.parents == []
