"""
Common test fixtures used across api test directories
"""
import textwrap
from datetime import datetime

import pandas as pd
import pytest
from bson.objectid import ObjectId
from pandas.testing import assert_frame_equal

from featurebyte import EventView
from featurebyte.api.change_view import ChangeView
from featurebyte.api.dimension_view import DimensionView
from featurebyte.api.event_data import EventData
from featurebyte.api.item_data import ItemData
from featurebyte.api.item_view import ItemView
from featurebyte.api.scd_view import SlowlyChangingView
from featurebyte.models.event_data import FeatureJobSetting
from featurebyte.models.feature_store import DataStatus


@pytest.fixture()
def expected_snowflake_table_preview_query() -> str:
    """
    Expected preview_sql output
    """
    return textwrap.dedent(
        """
        SELECT
          "col_int" AS "col_int",
          "col_float" AS "col_float",
          "col_char" AS "col_char",
          "col_text" AS "col_text",
          "col_binary" AS "col_binary",
          "col_boolean" AS "col_boolean",
          CAST("event_timestamp" AS VARCHAR) AS "event_timestamp",
          CAST("created_at" AS VARCHAR) AS "created_at",
          "cust_id" AS "cust_id"
        FROM "sf_database"."sf_schema"."sf_table"
        LIMIT 10
        """
    ).strip()


@pytest.fixture()
def expected_item_data_table_preview_query() -> str:
    """
    Expected preview_sql output
    """
    return textwrap.dedent(
        """
        SELECT
          "event_id_col" AS "event_id_col",
          "item_id_col" AS "item_id_col",
          "item_type" AS "item_type",
          "item_amount" AS "item_amount",
          CAST("created_at" AS VARCHAR) AS "created_at",
          CAST("event_timestamp" AS VARCHAR) AS "event_timestamp"
        FROM "sf_database"."sf_schema"."items_table"
        LIMIT 10
        """
    ).strip()


@pytest.fixture(name="snowflake_database_table")
def snowflake_database_table_fixture(
    snowflake_connector, snowflake_execute_query, snowflake_feature_store
):
    """
    DatabaseTable object fixture (using config object)
    """
    _ = snowflake_connector, snowflake_execute_query
    yield snowflake_feature_store.get_table(
        database_name="sf_database",
        schema_name="sf_schema",
        table_name="sf_table",
    )


@pytest.fixture(name="snowflake_event_data")
def snowflake_event_data_fixture(
    snowflake_database_table, mock_get_persistent, snowflake_event_data_id
):
    """
    Snowflake EventData object fixture (using config object)
    """
    _ = mock_get_persistent
    yield EventData.from_tabular_source(
        tabular_source=snowflake_database_table,
        name="sf_event_data",
        event_id_column="col_int",
        event_timestamp_column="event_timestamp",
        record_creation_date_column="created_at",
        _id=snowflake_event_data_id,
    )


@pytest.fixture(name="saved_event_data")
def saved_event_data_fixture(snowflake_feature_store, snowflake_event_data):
    """
    Saved event data fixture
    """
    snowflake_feature_store.save()
    previous_id = snowflake_event_data.id
    assert snowflake_event_data.saved is False
    snowflake_event_data.save()
    assert snowflake_event_data.saved is True
    assert snowflake_event_data.id == previous_id
    assert snowflake_event_data.status == DataStatus.DRAFT
    assert isinstance(snowflake_event_data.created_at, datetime)
    assert isinstance(snowflake_event_data.tabular_source.feature_store_id, ObjectId)

    # test list event data
    event_data_list = EventData.list()
    assert_frame_equal(
        event_data_list,
        pd.DataFrame(
            {
                "name": [snowflake_event_data.name],
                "type": [snowflake_event_data.type],
                "status": [snowflake_event_data.status],
                "entities": [[]],
                "created_at": [snowflake_event_data.created_at],
            }
        ),
    )
    yield snowflake_event_data


@pytest.fixture(name="saved_dimension_data")
def saved_dimension_data_fixture(snowflake_feature_store, snowflake_dimension_data):
    """
    Saved dimension data fixture
    """
    snowflake_feature_store.save()
    previous_id = snowflake_dimension_data.id
    assert snowflake_dimension_data.saved is False
    snowflake_dimension_data.save()
    assert snowflake_dimension_data.saved is True
    assert snowflake_dimension_data.id == previous_id
    assert snowflake_dimension_data.status == DataStatus.DRAFT
    assert isinstance(snowflake_dimension_data.created_at, datetime)
    assert isinstance(snowflake_dimension_data.tabular_source.feature_store_id, ObjectId)

    yield snowflake_dimension_data


@pytest.fixture(name="saved_scd_data")
def saved_scd_data_fixture(snowflake_feature_store, snowflake_scd_data):
    """
    Saved SCD data fixture
    """
    snowflake_feature_store.save()
    previous_id = snowflake_scd_data.id
    assert snowflake_scd_data.saved is False
    snowflake_scd_data.save()
    assert snowflake_scd_data.saved is True
    assert snowflake_scd_data.id == previous_id
    assert snowflake_scd_data.status == DataStatus.DRAFT
    assert isinstance(snowflake_scd_data.created_at, datetime)
    assert isinstance(snowflake_scd_data.tabular_source.feature_store_id, ObjectId)

    yield snowflake_scd_data


@pytest.fixture(name="snowflake_item_data")
def snowflake_item_data_fixture(
    snowflake_database_table_item_data,
    mock_get_persistent,
    snowflake_item_data_id,
    saved_event_data,
    cust_id_entity,
    arbitrary_default_feature_job_setting,
):
    """
    Snowflake ItemData object fixture (using config object)
    """
    _ = mock_get_persistent
    saved_event_data.update_default_feature_job_setting(arbitrary_default_feature_job_setting)
    saved_event_data["cust_id"].as_entity(cust_id_entity.name)
    item_data = ItemData.from_tabular_source(
        tabular_source=snowflake_database_table_item_data,
        name="sf_item_data",
        event_id_column="event_id_col",
        item_id_column="item_id_col",
        event_data_name=saved_event_data.name,
        _id=snowflake_item_data_id,
    )
    yield item_data


@pytest.fixture(name="saved_item_data")
def saved_item_data_fixture(snowflake_feature_store, snowflake_item_data):
    """
    Saved ItemData fixture
    """
    previous_id = snowflake_item_data.id
    assert snowflake_item_data.saved is False
    snowflake_item_data.save()
    assert snowflake_item_data.saved is True
    assert snowflake_item_data.id == previous_id
    assert snowflake_item_data.status == DataStatus.DRAFT
    assert isinstance(snowflake_item_data.created_at, datetime)
    assert isinstance(snowflake_item_data.tabular_source.feature_store_id, ObjectId)

    yield snowflake_item_data


@pytest.fixture(name="snowflake_item_view")
def snowflake_item_view_fixture(snowflake_item_data):
    """
    ItemView fixture
    """
    item_view = ItemView.from_item_data(snowflake_item_data, event_suffix="_event_table")
    yield item_view


@pytest.fixture(name="snowflake_dimension_view")
def snowflake_dimension_view_fixture(snowflake_dimension_data):
    """
    DimensionView fixture
    """
    dimension_view = DimensionView.from_dimension_data(snowflake_dimension_data)
    yield dimension_view


@pytest.fixture(name="snowflake_scd_view")
def snowflake_slowly_changing_view_fixture(snowflake_scd_data):
    """
    SlowlyChangingView fixture
    """
    scd_view = SlowlyChangingView.from_slowly_changing_data(snowflake_scd_data)
    yield scd_view


@pytest.fixture(name="snowflake_change_view")
def snowflake_change_view(snowflake_scd_data):
    """
    ChangeView fixture
    """
    change_view = ChangeView.from_slowly_changing_data(snowflake_scd_data, "col_int")
    yield change_view


@pytest.fixture(name="snowflake_event_view")
def snowflake_event_view_fixture(
    snowflake_event_data, config, arbitrary_default_feature_job_setting
):
    """
    EventData object fixture
    """
    _ = config
    snowflake_event_data.update_default_feature_job_setting(
        feature_job_setting=arbitrary_default_feature_job_setting
    )
    event_view = EventView.from_event_data(event_data=snowflake_event_data)
    yield event_view


@pytest.fixture(name="feature_job_logs", scope="session")
def feature_job_logs_fixture():
    """
    Feature job log records
    """
    job_logs = pd.read_csv("tests/fixtures/feature_job_status/job_logs.csv")
    job_logs["CREATED_AT"] = pd.to_datetime(job_logs["CREATED_AT"])
    return job_logs
