"""
Integration tests for SCDView
"""
import json

import numpy as np
import pandas as pd
import pytest
from bson import ObjectId

from featurebyte import Entity, FeatureJobSetting, FeatureList
from featurebyte.schema.feature_list import OnlineFeaturesRequestPayload
from tests.util.helper import assert_preview_result_equal, make_online_request


def get_expected_scd_join_result(
    df_left,
    df_right,
    left_key,
    right_key,
    left_timestamp,
    right_timestamp,
):
    """
    Perform an SCD join using in memory DataFrames
    """
    df_left = df_left.copy()
    df_right = df_right.copy()
    df_left[left_timestamp] = pd.to_datetime(df_left[left_timestamp], utc=True).dt.tz_localize(None)
    df_right[right_timestamp] = pd.to_datetime(df_right[right_timestamp], utc=True).dt.tz_localize(
        None
    )
    df_left = df_left.set_index(left_timestamp).sort_index()
    df_right = df_right.set_index(right_timestamp).sort_index()
    df_result = pd.merge_asof(
        df_left,
        df_right,
        left_index=True,
        right_index=True,
        left_by=left_key,
        right_by=right_key,
        allow_exact_matches=True,
    )
    return df_result


@pytest.fixture
def expected_dataframe_scd_join(transaction_data_upper_case, scd_dataframe):
    """
    Fixture for expected result when joining the transaction table with scd table
    """
    df = get_expected_scd_join_result(
        df_left=transaction_data_upper_case.copy(),
        df_right=scd_dataframe,
        left_key="ÜSER ID",
        right_key="User ID",
        left_timestamp="ËVENT_TIMESTAMP",
        right_timestamp="Effective Timestamp",
    )
    df = df.reset_index()
    return df


@pytest.mark.parametrize("source_type", ["snowflake", "spark", "databricks"], indirect=True)
def test_scd_view_preview(scd_table):
    """
    Test preview of SCDView
    """
    view = scd_table.get_view()

    def _check_result_exclude_current_flag_column(df_result):
        assert scd_table.current_flag_column is not None
        assert scd_table.current_flag_column not in df_result.columns.tolist()

    _check_result_exclude_current_flag_column(view.preview())
    _check_result_exclude_current_flag_column(view.sample())
    _check_result_exclude_current_flag_column(view.describe())


@pytest.mark.parametrize("source_type", ["snowflake", "spark", "databricks"], indirect=True)
@pytest.mark.asyncio
async def test_scd_join_small(session, data_source, source_type):
    """
    Self-contained test case to test SCD with small datasets
    """
    df_events = pd.DataFrame(
        {
            "ts": pd.to_datetime(
                [
                    "2022-04-10 10:00:00",
                    "2022-04-15 10:00:00",
                    "2022-04-20 10:00:00",
                ]
            ),
            "cust_id": [1000, 1000, 1000],
            "event_id": [1, 2, 3],
        }
    )
    df_scd = pd.DataFrame(
        {
            "effective_ts": pd.to_datetime(["2022-04-12 10:00:00", "2022-04-20 10:00:00"]),
            "scd_cust_id": [1000, 1000],
            "scd_value": [1, 2],
        }
    )
    df_expected = pd.DataFrame(
        {
            "ts": pd.to_datetime(
                [
                    "2022-04-10 10:00:00",
                    "2022-04-15 10:00:00",
                    "2022-04-20 10:00:00",
                ]
            ),
            "cust_id": [1000, 1000, 1000],
            "event_id": [1, 2, 3],
            "scd_value_latest": [np.nan, 1, 2],
            "scd_value_latest_v2": [np.nan, 1, 2],
        }
    )
    table_prefix = "TEST_SCD_JOIN_SMALL"
    await session.register_table(f"{table_prefix}_EVENT", df_events, temporary=False)
    await session.register_table(f"{table_prefix}_SCD", df_scd, temporary=False)
    event_source_table = data_source.get_source_table(
        table_name=f"{table_prefix}_EVENT",
        database_name=session.database_name,
        schema_name=session.schema_name,
    )
    event_table = event_source_table.create_event_table(
        name=f"{source_type}_{table_prefix}_EVENT_DATA",
        event_id_column="event_id",
        event_timestamp_column="ts",
    )
    event_view = event_table.get_view()
    scd_source_table = data_source.get_source_table(
        table_name=f"{table_prefix}_SCD",
        database_name=session.database_name,
        schema_name=session.schema_name,
    )
    scd_table = scd_source_table.create_scd_table(
        name=f"{source_type}_{table_prefix}_SCD_DATA",
        natural_key_column="scd_cust_id",
        effective_timestamp_column="effective_ts",
    )
    scd_view = scd_table.get_view()
    event_view = event_view.join(scd_view, on="cust_id", rsuffix="_latest")
    event_view = event_view.join(scd_view, on="cust_id", rsuffix="_latest_v2")
    df_actual = event_view.preview()
    pd.testing.assert_frame_equal(df_actual, df_expected, check_dtype=False)


@pytest.mark.parametrize("source_type", ["snowflake"], indirect=True)
@pytest.mark.asyncio
async def test_feature_derived_from_multiple_scd_joins(session, data_source, source_type):
    """
    Test case to test feature derived from multiple SCD joins
    """
    df_events = pd.DataFrame(
        {
            "ts": pd.to_datetime(
                [
                    "2022-04-10 10:00:00",
                    "2022-04-15 10:00:00",
                    "2022-04-20 10:00:00",
                ]
            ),
            "event_id": [1, 2, 3],
            "event_type": ["A", "B", "A"],
            "account_id": [1000, 1000, 1000],
        }
    )
    df_scd = pd.DataFrame(
        {
            "effective_ts": pd.to_datetime(["2022-04-12 10:00:00", "2022-04-20 10:00:00"]),
            "account_id": [1000, 1000],
            "customer_id": ["c1", "c1"],
        }
    )
    df_scd_2 = pd.DataFrame(
        {
            "effective_ts": pd.to_datetime(["2022-04-12 10:00:00", "2022-04-20 10:00:00"]),
            "customer_id": ["c1", "c1"],
            "state_code": ["CA", "MA"],
        }
    )
    table_prefix = str(ObjectId())
    await session.register_table(f"{table_prefix}_EVENT", df_events, temporary=False)
    await session.register_table(f"{table_prefix}_SCD", df_scd, temporary=False)
    await session.register_table(f"{table_prefix}_SCD_2", df_scd_2, temporary=False)
    event_source_table = data_source.get_source_table(
        table_name=f"{table_prefix}_EVENT",
        database_name=session.database_name,
        schema_name=session.schema_name,
    )
    event_table = event_source_table.create_event_table(
        name=f"{source_type}_{table_prefix}_EVENT_DATA",
        event_id_column="event_id",
        event_timestamp_column="ts",
    )
    event_view = event_table.get_view()
    scd_source_table = data_source.get_source_table(
        table_name=f"{table_prefix}_SCD",
        database_name=session.database_name,
        schema_name=session.schema_name,
    )
    scd_table = scd_source_table.create_scd_table(
        name=f"{source_type}_{table_prefix}_SCD_DATA",
        natural_key_column="account_id",
        effective_timestamp_column="effective_ts",
    )
    scd_source_table_2 = data_source.get_source_table(
        table_name=f"{table_prefix}_SCD_2",
        database_name=session.database_name,
        schema_name=session.schema_name,
    )
    scd_table_2 = scd_source_table_2.create_scd_table(
        name=f"{source_type}_{table_prefix}_SCD_DATA_2",
        natural_key_column="customer_id",
        effective_timestamp_column="effective_ts",
    )

    state_entity = Entity.create(f"{table_prefix}_state", ["state_code"])
    scd_table_2["state_code"].as_entity(state_entity.name)

    customer_entity = Entity.create(f"{table_prefix}_customer", ["customer_id"])
    scd_table["customer_id"].as_entity(customer_entity.name)
    scd_table_2["customer_id"].as_entity(customer_entity.name)

    scd_view = scd_table.get_view()
    scd_view_2 = scd_table_2.get_view()
    event_view = event_view.join(scd_view[["account_id", "customer_id"]], on="account_id")
    event_view = event_view.join(scd_view_2[["customer_id", "state_code"]], on="customer_id")
    features = event_view.groupby("state_code", category="event_type").aggregate_over(
        None,
        "count",
        windows=["30d"],
        feature_names=["state_code_counts_30d"],
        feature_job_setting=FeatureJobSetting(
            frequency="24h", time_modulo_frequency="1h", blind_spot="2h"
        ),
    )
    df_observations = pd.DataFrame(
        {"POINT_IN_TIME": ["2022-04-25 10:00:00"], "customer_id": ["c1"]}
    )
    df = features.preview(df_observations)
    expected = df_observations.copy()
    expected["POINT_IN_TIME"] = pd.to_datetime(expected["POINT_IN_TIME"])
    expected["state_code_counts_30d"] = '{\n  "A": 1\n}'
    pd.testing.assert_frame_equal(df, expected)


@pytest.mark.parametrize("source_type", ["snowflake", "spark", "databricks"], indirect=True)
def test_event_view_join_scd_view__preview_view(
    event_table, scd_table, expected_dataframe_scd_join
):
    """
    Test joining an EventView with and SCDView
    """
    event_view = event_table.get_view()
    scd_view = scd_table.get_view()
    event_view = event_view.join(scd_view, on="ÜSER ID")
    df = event_view.preview(1000)
    df_expected = expected_dataframe_scd_join

    # Check correctness of joined view
    df["ËVENT_TIMESTAMP"] = pd.to_datetime(df["ËVENT_TIMESTAMP"], utc=True).dt.tz_localize(None)
    df_compare = df[["ËVENT_TIMESTAMP", "ÜSER ID", "User Status"]].merge(
        df_expected[["ËVENT_TIMESTAMP", "ÜSER ID", "User Status"]],
        on=["ËVENT_TIMESTAMP", "ÜSER ID"],
        suffixes=("_actual", "_expected"),
    )
    pd.testing.assert_series_equal(
        df_compare["User Status_actual"],
        df_compare["User Status_expected"],
        check_names=False,
    )


@pytest.mark.parametrize("source_type", ["snowflake", "spark", "databricks"], indirect=True)
def test_event_view_join_scd_view__preview_feature(event_table, scd_table):
    """
    Test joining an EventView with and SCDView
    """
    event_view = event_table.get_view()
    scd_table = scd_table.get_view()
    event_view = event_view.join(scd_table, on="ÜSER ID")

    # Create a feature and preview it
    feature = event_view.groupby("ÜSER ID", category="User Status").aggregate_over(
        method="count",
        windows=["7d"],
        feature_names=["count_7d"],
    )["count_7d"]

    df = feature.preview(pd.DataFrame([{"POINT_IN_TIME": "2001-11-15 10:00:00", "üser id": 1}]))
    expected = {
        "POINT_IN_TIME": pd.Timestamp("2001-11-15 10:00:00"),
        "üser id": 1,
        "count_7d": '{\n  "STÀTUS_CODE_34": 3,\n  "STÀTUS_CODE_39": 15\n}',
    }
    assert_preview_result_equal(df, expected, dict_like_columns=["count_7d"])


@pytest.mark.parametrize("source_type", ["snowflake", "spark", "databricks"], indirect=True)
def test_scd_lookup_feature(config, event_table, dimension_table, scd_table, scd_dataframe):
    """
    Test creating lookup feature from a SCDView
    """
    # SCD lookup feature
    scd_view = scd_table.get_view()
    scd_lookup_feature = scd_view["User Status"].as_feature("Current User Status")

    # Dimension lookup feature
    dimension_view = dimension_table.get_view()
    dimension_lookup_feature = dimension_view["item_name"].as_feature("Item Name Feature")

    # Window feature that depends on an SCD join
    event_view = event_table.get_view()
    event_view = event_view.join(scd_view, on="ÜSER ID")
    window_feature = event_view.groupby("ÜSER ID", "User Status").aggregate_over(
        method="count",
        windows=["7d"],
        feature_names=["count_7d"],
    )["count_7d"]

    # Preview a feature list with above features
    feature_list = FeatureList(
        [window_feature, scd_lookup_feature, dimension_lookup_feature],
        "feature_list__test_scd_lookup_feature",
    )
    point_in_time = "2001-11-15 10:00:00"
    item_id = "item_42"
    user_id = 1
    preview_params = {
        "POINT_IN_TIME": point_in_time,
        "üser id": user_id,
        "item_id": item_id,
    }
    preview_output = feature_list.preview(pd.DataFrame([preview_params])).iloc[0].to_dict()
    assert set(preview_output.keys()) == {
        "POINT_IN_TIME",
        "üser id",
        "item_id",
        "count_7d",
        "Current User Status",
        "Item Name Feature",
    }

    # Compare with expected result
    mask = (scd_dataframe["Effective Timestamp"] <= point_in_time) & (
        scd_dataframe["User ID"] == user_id
    )
    expected_row = scd_dataframe[mask].sort_values("Effective Timestamp").iloc[-1]
    assert preview_output["Current User Status"] == expected_row["User Status"]
    assert preview_output["Item Name Feature"] == "name_42"
    assert json.loads(preview_output["count_7d"]) == json.loads(
        '{\n  "STÀTUS_CODE_34": 3,\n  "STÀTUS_CODE_39": 15\n}'
    )

    # Check online serving.
    feature_list.save()
    deployment = None
    try:
        deployment = feature_list.deploy(make_production_ready=True)
        deployment.enable()
        params = preview_params.copy()
        params.pop("POINT_IN_TIME")
        online_result = make_online_request(config.get_client(), deployment, [params])
        assert online_result.json()["features"] == [
            {
                "üser id": 1,
                "item_id": "item_42",
                "Current User Status": "STÀTUS_CODE_39",
                "Item Name Feature": "name_42",
                "count_7d": None,
            }
        ]
    finally:
        if deployment:
            deployment.disable()


@pytest.mark.parametrize("source_type", ["snowflake", "spark", "databricks"], indirect=True)
def test_scd_lookup_feature_with_offset(config, scd_table, scd_dataframe):
    """
    Test creating lookup feature from a SCDView with offset
    """
    # SCD lookup feature
    offset = "90d"
    scd_view = scd_table.get_view()
    scd_lookup_feature = scd_view["User Status"].as_feature(
        "Current User Status Offset 90d", offset=offset
    )

    # Preview
    point_in_time = "2001-11-15 10:00:00"
    user_id = 1
    preview_params = {
        "POINT_IN_TIME": point_in_time,
        "üser id": user_id,
    }
    preview_output = scd_lookup_feature.preview(pd.DataFrame([preview_params])).iloc[0].to_dict()

    # Compare with expected result
    mask = (
        pd.to_datetime(scd_dataframe["Effective Timestamp"], utc=True).dt.tz_localize(None)
        <= (pd.to_datetime(point_in_time) - pd.Timedelta(offset))
    ) & (scd_dataframe["User ID"] == user_id)
    expected_row = scd_dataframe[mask].sort_values("Effective Timestamp").iloc[-1]
    assert preview_output["Current User Status Offset 90d"] == expected_row["User Status"]

    # Check online serving
    feature_list = FeatureList(
        [scd_lookup_feature], "feature_list__test_scd_lookup_feature_with_offset"
    )
    feature_list.save()
    deployment = None
    try:
        deployment = feature_list.deploy(make_production_ready=True)
        deployment.enable()
        params = preview_params.copy()
        params.pop("POINT_IN_TIME")
        online_result = make_online_request(config.get_client(), deployment, [params])
        assert online_result.json()["features"] == [
            {"üser id": 1, "Current User Status Offset 90d": "STÀTUS_CODE_39"}
        ]
    finally:
        deployment.disable()


@pytest.mark.parametrize("source_type", ["snowflake", "spark", "databricks"], indirect=True)
def test_aggregate_asat(scd_table, scd_dataframe, source_type):
    """
    Test aggregate_asat aggregation on SCDView
    """
    scd_view = scd_table.get_view()
    feature = scd_view.groupby("User Status").aggregate_asat(
        method="count", feature_name="Current Number of Users With This Status"
    )

    # check preview but provides children id
    df = FeatureList([feature], name="mylist").preview(
        pd.DataFrame(
            [
                {
                    "POINT_IN_TIME": "2001-10-25 10:00:00",
                    "üser id": 1,
                }
            ]
        )
    )
    # databricks return POINT_IN_TIME with "Etc/UTC" timezone
    if source_type == "databricks":
        df["POINT_IN_TIME"] = pd.to_datetime(df["POINT_IN_TIME"]).dt.tz_localize(None)
    expected = {
        "POINT_IN_TIME": pd.Timestamp("2001-10-25 10:00:00"),
        "üser id": 1,
        "Current Number of Users With This Status": 1,
    }
    assert df.iloc[0].to_dict() == expected

    # check preview
    df = feature.preview(
        pd.DataFrame(
            [
                {
                    "POINT_IN_TIME": "2001-10-25 10:00:00",
                    "user_status": "STÀTUS_CODE_42",
                }
            ]
        )
    )
    # databricks return POINT_IN_TIME with "Etc/UTC" timezone
    if source_type == "databricks":
        df["POINT_IN_TIME"] = pd.to_datetime(df["POINT_IN_TIME"]).dt.tz_localize(None)
    expected = {
        "POINT_IN_TIME": pd.Timestamp("2001-10-25 10:00:00"),
        "user_status": "STÀTUS_CODE_42",
        "Current Number of Users With This Status": 1,
    }
    assert df.iloc[0].to_dict() == expected

    # check historical features
    feature_list = FeatureList([feature], "feature_list")
    observations_set = pd.DataFrame(
        {
            "POINT_IN_TIME": pd.date_range("2001-01-10 10:00:00", periods=10, freq="1d"),
            "user_status": ["STÀTUS_CODE_47"] * 10,
        }
    )
    expected = observations_set.copy()
    expected["Current Number of Users With This Status"] = [0, 1, 2, 2, 1, 1, 0, 0, 0, 0]
    df = feature_list.compute_historical_features(observations_set)
    # databricks return POINT_IN_TIME with "Etc/UTC" timezone
    if source_type == "databricks":
        df["POINT_IN_TIME"] = pd.to_datetime(df["POINT_IN_TIME"]).dt.tz_localize(None)
    pd.testing.assert_frame_equal(df, expected, check_dtype=False)


@pytest.mark.parametrize("source_type", ["snowflake", "spark", "databricks"], indirect=True)
def test_aggregate_asat__no_entity(scd_table, scd_dataframe, config, source_type):
    """
    Test aggregate_asat aggregation on SCDView without entity
    """
    scd_view = scd_table.get_view()
    feature = scd_view.groupby([]).aggregate_asat(
        method="count", feature_name="Current Number of Users"
    )

    # check preview
    df = feature.preview(
        pd.DataFrame(
            [
                {
                    "POINT_IN_TIME": "2001-10-25 10:00:00",
                }
            ]
        )
    )
    # databricks return POINT_IN_TIME with "Etc/UTC" timezone
    if source_type == "databricks":
        df["POINT_IN_TIME"] = pd.to_datetime(df["POINT_IN_TIME"]).dt.tz_localize(None)
    expected = {
        "POINT_IN_TIME": pd.Timestamp("2001-10-25 10:00:00"),
        "Current Number of Users": 9,
    }
    assert df.iloc[0].to_dict() == expected

    # check historical features
    feature_list = FeatureList([feature], "feature_list")
    observations_set = pd.DataFrame(
        {
            "POINT_IN_TIME": pd.date_range("2001-01-10 10:00:00", periods=10, freq="1d"),
        }
    )
    expected = observations_set.copy()
    expected["Current Number of Users"] = [8, 8, 9, 9, 9, 9, 9, 9, 9, 9]
    df = feature_list.compute_historical_features(observations_set)
    df = df.sort_values("POINT_IN_TIME").reset_index(drop=True)
    # databricks return POINT_IN_TIME with "Etc/UTC" timezone
    if source_type == "databricks":
        df["POINT_IN_TIME"] = pd.to_datetime(df["POINT_IN_TIME"]).dt.tz_localize(None)
    pd.testing.assert_frame_equal(df, expected, check_dtype=False)

    # check online serving
    feature_list.save()
    deployment = feature_list.deploy(make_production_ready=True)
    deployment.enable()

    data = OnlineFeaturesRequestPayload(entity_serving_names=[{"row_number": 1}])
    res = config.get_client().post(
        f"/deployment/{deployment.id}/online_features",
        json=data.json_dict(),
    )
    assert res.status_code == 200
    assert res.json() == {"features": [{"row_number": 1, "Current Number of Users": 9}]}


@pytest.mark.parametrize("source_type", ["snowflake", "spark", "databricks"], indirect=True)
def test_columns_joined_from_scd_view_as_groupby_keys(event_table, scd_table, source_type):
    """
    Test aggregate_over using a key column joined from another view
    """
    event_view = event_table.get_view()
    scd_view = scd_table.get_view()

    event_view = event_view.join(scd_view, on="ÜSER ID")

    feature = event_view.groupby("User Status").aggregate_over(
        method="count",
        windows=["30d"],
        feature_names=["count_30d"],
    )["count_30d"]
    feature_list = FeatureList([feature], "feature_list")

    # check preview
    preview_param = {
        "POINT_IN_TIME": "2002-01-01 10:00:00",
        "user_status": "STÀTUS_CODE_47",
    }

    df = feature_list.preview(pd.DataFrame([preview_param]))
    # databricks return POINT_IN_TIME with "Etc/UTC" timezone
    if source_type == "databricks":
        df["POINT_IN_TIME"] = pd.to_datetime(df["POINT_IN_TIME"]).dt.tz_localize(None)
    expected = {
        "POINT_IN_TIME": pd.Timestamp("2002-01-01 10:00:00"),
        "user_status": "STÀTUS_CODE_47",
        "count_30d": 7,
    }
    assert df.iloc[0].to_dict() == expected

    # check historical features
    observations_set = pd.DataFrame([preview_param])
    df = feature_list.compute_historical_features(observations_set)
    df = df.sort_values("POINT_IN_TIME").reset_index(drop=True)
    # databricks return POINT_IN_TIME with "Etc/UTC" timezone
    if source_type == "databricks":
        df["POINT_IN_TIME"] = pd.to_datetime(df["POINT_IN_TIME"]).dt.tz_localize(None)
    assert df.iloc[0].to_dict() == expected
