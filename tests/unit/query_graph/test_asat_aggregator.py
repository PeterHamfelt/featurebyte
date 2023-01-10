"""
Unit tests for featurebyte.query_graph.sql.aggregator.asat.AsAtAggregator
"""
import textwrap

import pytest
from sqlglot.expressions import select

from featurebyte.enum import SourceType
from featurebyte.query_graph.node.generic import AggregateAsAtParameters
from featurebyte.query_graph.sql.aggregator.asat import AsAtAggregator
from featurebyte.query_graph.sql.specs import AggregateAsAtSpec


@pytest.fixture
def aggregate_as_at_node_parameters():
    return AggregateAsAtParameters(
        keys=["cust_id"],
        serving_names=["serving_cust_id"],
        parent="value",
        agg_func="sum",
        natural_key_column="scd_key",
        effective_timestamp_column="effective_ts",
        name="asat_feature",
    )


@pytest.fixture
def aggregate_as_at_node_parameters_with_end_timestamp(aggregate_as_at_node_parameters):
    params = aggregate_as_at_node_parameters.copy()
    params.end_timestamp_column = "end_ts"
    return params


@pytest.fixture
def scd_table_sql():
    return select("*").from_("SCD_TABLE")


@pytest.fixture
def aggregation_spec_without_end_timestamp(aggregate_as_at_node_parameters, scd_table_sql):
    return AggregateAsAtSpec(
        serving_names=["serving_cust_id"],
        serving_names_mapping=None,
        parameters=aggregate_as_at_node_parameters,
        source_expr=scd_table_sql,
    )


@pytest.fixture
def aggregation_spec_with_end_timestamp(
    aggregate_as_at_node_parameters_with_end_timestamp, scd_table_sql
):
    return AggregateAsAtSpec(
        serving_names=["serving_cust_id"],
        serving_names_mapping=None,
        parameters=aggregate_as_at_node_parameters_with_end_timestamp,
        source_expr=scd_table_sql,
    )


@pytest.fixture
def aggregation_specs_same_source_different_agg_funcs(
    aggregate_as_at_node_parameters_with_end_timestamp,
    scd_table_sql,
):
    params = aggregate_as_at_node_parameters_with_end_timestamp

    params_1 = params.copy()
    params_1.agg_func = "min"

    params_2 = params.copy()
    params_2.agg_func = "max"

    specs = []
    for params in [params_1, params_2]:
        specs.append(
            AggregateAsAtSpec(
                serving_names=["serving_cust_id"],
                serving_names_mapping=None,
                parameters=params,
                source_expr=scd_table_sql,
            )
        )

    return specs


@pytest.fixture
def aggregation_specs_same_source_different_keys(
    aggregate_as_at_node_parameters_with_end_timestamp,
    scd_table_sql,
):
    params = aggregate_as_at_node_parameters_with_end_timestamp

    params_1 = params.copy()
    params_1.__dict__.update({"keys": ["key_1"], "serving_names": ["serving_key_1"]})

    params_2 = params.copy()
    params_2.__dict__.update({"keys": ["key_2"], "serving_names": ["serving_key_2"]})

    specs = []
    for params in [params_1, params_2]:
        specs.append(
            AggregateAsAtSpec(
                serving_names=params.serving_names,
                serving_names_mapping=None,
                parameters=params,
                source_expr=scd_table_sql,
            )
        )

    return specs


def test_asat_aggregate_scd_table_without_end_timestamp(aggregation_spec_without_end_timestamp):
    """
    Test AsAtAggregator on SCD table without end timestamp
    """
    aggregator = AsAtAggregator(source_type=SourceType.SNOWFLAKE)
    aggregator.update(aggregation_spec_without_end_timestamp)

    result = aggregator.update_aggregation_table_expr(
        select("a", "b", "c").from_("REQUEST_TABLE"), "POINT_INT_TIME", ["a", "b", "c"], 0
    )

    expected = textwrap.dedent(
        """
        SELECT
          a,
          b,
          c,
          "T0"."sum_value_cffc07d0b60086cc" AS "sum_value_cffc07d0b60086cc"
        FROM REQUEST_TABLE
        LEFT JOIN (
          SELECT
            REQ."POINT_IN_TIME",
            REQ."serving_cust_id",
            SUM(SCD."value") AS "sum_value_cffc07d0b60086cc"
          FROM "REQUEST_TABLE_POINT_IN_TIME_serving_cust_id" AS REQ
          INNER JOIN (
            SELECT
              *,
              LEAD("effective_ts") OVER (PARTITION BY "scd_key" ORDER BY "effective_ts" NULLS LAST) AS "__FB_END_TS"
            FROM (
              SELECT
                *
              FROM SCD_TABLE
            )
          ) AS SCD
            ON REQ."serving_cust_id" = SCD."cust_id"
            AND (
              SCD."effective_ts" <= REQ."POINT_IN_TIME"
              AND (
                SCD."__FB_END_TS" > REQ."POINT_IN_TIME" OR SCD."__FB_END_TS" IS NULL
              )
            )
          GROUP BY
            REQ."POINT_IN_TIME",
            REQ."serving_cust_id"
        ) AS T0
          ON REQ."POINT_IN_TIME" = T0."POINT_IN_TIME"
          AND REQ."serving_cust_id" = T0."serving_cust_id"
        """
    ).strip()
    assert result.updated_table_expr.sql(pretty=True) == expected

    request_table_ctes = aggregator.get_common_table_expressions("REQUEST_TABLE")
    assert len(request_table_ctes) == 1
    expected = textwrap.dedent(
        """
        SELECT DISTINCT
          "POINT_IN_TIME",
          "serving_cust_id"
        FROM REQUEST_TABLE
        """
    ).strip()
    assert request_table_ctes[0][0] == '"REQUEST_TABLE_POINT_IN_TIME_serving_cust_id"'
    assert request_table_ctes[0][1].sql(pretty=True) == expected


def test_asat_aggregate_scd_table_with_end_timestamp(aggregation_spec_with_end_timestamp):
    """
    Test AsAtAggregator on SCD table with end timestamp (query is simpler because no need to compute
    the end timestamp for the SCD table)
    """
    aggregator = AsAtAggregator(source_type=SourceType.SNOWFLAKE)
    aggregator.update(aggregation_spec_with_end_timestamp)

    result = aggregator.update_aggregation_table_expr(
        select("a", "b", "c").from_("REQUEST_TABLE"), "POINT_INT_TIME", ["a", "b", "c"], 0
    )

    expected = textwrap.dedent(
        """
        SELECT
          a,
          b,
          c,
          "T0"."sum_value_d9f27f309eb1beea" AS "sum_value_d9f27f309eb1beea"
        FROM REQUEST_TABLE
        LEFT JOIN (
          SELECT
            REQ."POINT_IN_TIME",
            REQ."serving_cust_id",
            SUM(SCD."value") AS "sum_value_d9f27f309eb1beea"
          FROM "REQUEST_TABLE_POINT_IN_TIME_serving_cust_id" AS REQ
          INNER JOIN (
            SELECT
              *
            FROM SCD_TABLE
          ) AS SCD
            ON REQ."serving_cust_id" = SCD."cust_id"
            AND (
              SCD."effective_ts" <= REQ."POINT_IN_TIME"
              AND (
                SCD."end_ts" > REQ."POINT_IN_TIME" OR SCD."end_ts" IS NULL
              )
            )
          GROUP BY
            REQ."POINT_IN_TIME",
            REQ."serving_cust_id"
        ) AS T0
          ON REQ."POINT_IN_TIME" = T0."POINT_IN_TIME"
          AND REQ."serving_cust_id" = T0."serving_cust_id"
        """
    ).strip()
    assert result.updated_table_expr.sql(pretty=True) == expected


def test_same_source_different_agg_funcs(aggregation_specs_same_source_different_agg_funcs):
    """
    Test that asat_aggregation using the same source and join keys but different agg_func can be
    aggregated in the same groubpy statement
    """
    aggregator = AsAtAggregator(source_type=SourceType.SNOWFLAKE)
    for spec in aggregation_specs_same_source_different_agg_funcs:
        aggregator.update(spec)

    assert len(aggregator.grouped_specs) == 1

    result = aggregator.update_aggregation_table_expr(
        select("a", "b", "c").from_("REQUEST_TABLE"), "POINT_INT_TIME", ["a", "b", "c"], 0
    )
    expected = textwrap.dedent(
        """
        SELECT
          a,
          b,
          c,
          "T0"."min_value_d9f27f309eb1beea" AS "min_value_d9f27f309eb1beea",
          "T0"."max_value_d9f27f309eb1beea" AS "max_value_d9f27f309eb1beea"
        FROM REQUEST_TABLE
        LEFT JOIN (
          SELECT
            REQ."POINT_IN_TIME",
            REQ."serving_cust_id",
            MIN(SCD."value") AS "min_value_d9f27f309eb1beea",
            MAX(SCD."value") AS "max_value_d9f27f309eb1beea"
          FROM "REQUEST_TABLE_POINT_IN_TIME_serving_cust_id" AS REQ
          INNER JOIN (
            SELECT
              *
            FROM SCD_TABLE
          ) AS SCD
            ON REQ."serving_cust_id" = SCD."cust_id"
            AND (
              SCD."effective_ts" <= REQ."POINT_IN_TIME"
              AND (
                SCD."end_ts" > REQ."POINT_IN_TIME" OR SCD."end_ts" IS NULL
              )
            )
          GROUP BY
            REQ."POINT_IN_TIME",
            REQ."serving_cust_id"
        ) AS T0
          ON REQ."POINT_IN_TIME" = T0."POINT_IN_TIME"
          AND REQ."serving_cust_id" = T0."serving_cust_id"
        """
    ).strip()
    assert result.updated_table_expr.sql(pretty=True) == expected


def test_same_source_different_keys(aggregation_specs_same_source_different_keys):
    """
    Test that asat_aggregation using the same source and join keys but different keys will have to
    be aggregated using multiple groupby operations
    """
    aggregator = AsAtAggregator(source_type=SourceType.SNOWFLAKE)
    for spec in aggregation_specs_same_source_different_keys:
        aggregator.update(spec)

    assert len(aggregator.grouped_specs) == 2

    result = aggregator.update_aggregation_table_expr(
        select("a", "b", "c").from_("REQUEST_TABLE"), "POINT_INT_TIME", ["a", "b", "c"], 0
    )
    expected = textwrap.dedent(
        """
        SELECT
          a,
          b,
          c,
          "T0"."sum_value_e6b2e16bbba4cafd" AS "sum_value_e6b2e16bbba4cafd",
          "T1"."sum_value_d56300cbaf25cc59" AS "sum_value_d56300cbaf25cc59"
        FROM REQUEST_TABLE
        LEFT JOIN (
          SELECT
            REQ."POINT_IN_TIME",
            REQ."serving_key_1",
            SUM(SCD."value") AS "sum_value_e6b2e16bbba4cafd"
          FROM "REQUEST_TABLE_POINT_IN_TIME_serving_key_1" AS REQ
          INNER JOIN (
            SELECT
              *
            FROM SCD_TABLE
          ) AS SCD
            ON REQ."serving_key_1" = SCD."key_1"
            AND (
              SCD."effective_ts" <= REQ."POINT_IN_TIME"
              AND (
                SCD."end_ts" > REQ."POINT_IN_TIME" OR SCD."end_ts" IS NULL
              )
            )
          GROUP BY
            REQ."POINT_IN_TIME",
            REQ."serving_key_1"
        ) AS T0
          ON REQ."POINT_IN_TIME" = T0."POINT_IN_TIME" AND REQ."serving_key_1" = T0."serving_key_1"
        LEFT JOIN (
          SELECT
            REQ."POINT_IN_TIME",
            REQ."serving_key_2",
            SUM(SCD."value") AS "sum_value_d56300cbaf25cc59"
          FROM "REQUEST_TABLE_POINT_IN_TIME_serving_key_2" AS REQ
          INNER JOIN (
            SELECT
              *
            FROM SCD_TABLE
          ) AS SCD
            ON REQ."serving_key_2" = SCD."key_2"
            AND (
              SCD."effective_ts" <= REQ."POINT_IN_TIME"
              AND (
                SCD."end_ts" > REQ."POINT_IN_TIME" OR SCD."end_ts" IS NULL
              )
            )
          GROUP BY
            REQ."POINT_IN_TIME",
            REQ."serving_key_2"
        ) AS T1
          ON REQ."POINT_IN_TIME" = T1."POINT_IN_TIME" AND REQ."serving_key_2" = T1."serving_key_2"
        """
    ).strip()
    assert result.updated_table_expr.sql(pretty=True) == expected