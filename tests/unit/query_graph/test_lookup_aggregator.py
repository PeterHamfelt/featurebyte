"""
Unit tests for featurebyte.query_graph.sql.aggregator.lookup.LookupAggregator
"""
from __future__ import annotations

import textwrap
from dataclasses import asdict

import pytest

from featurebyte.enum import SourceType
from featurebyte.query_graph.node.generic import SCDLookupParameters
from featurebyte.query_graph.sql.aggregator.lookup import LookupAggregator
from featurebyte.query_graph.sql.specs import LookupSpec


@pytest.fixture
def dimension_lookup_specs(global_graph, lookup_node):
    """
    Fixture for a list of LookupSpec derived from lookup_node
    """
    return LookupSpec.from_lookup_query_node(
        lookup_node,
        graph=global_graph,
        source_type=SourceType.SNOWFLAKE,
    )


@pytest.fixture
def scd_lookup_specs_with_current_flag(global_graph, scd_lookup_node):
    """
    Fixture for a list of LookupSpec derived from SCD lookup
    """
    return LookupSpec.from_lookup_query_node(
        scd_lookup_node,
        graph=global_graph,
        source_type=SourceType.SNOWFLAKE,
    )


@pytest.fixture
def scd_lookup_specs_without_current_flag(global_graph, scd_lookup_without_current_flag_node):
    """
    Fixture for a list of LookupSpec derived from SCD lookup without current flag column
    """
    return LookupSpec.from_lookup_query_node(
        scd_lookup_without_current_flag_node,
        graph=global_graph,
        source_type=SourceType.SNOWFLAKE,
    )


@pytest.fixture
def scd_lookup_specs_with_offset(global_graph, scd_offset_lookup_node):
    """
    Fixture for a list of LookupSpec derived from SCD lookup with offset
    """
    return LookupSpec.from_lookup_query_node(
        scd_offset_lookup_node,
        graph=global_graph,
        source_type=SourceType.SNOWFLAKE,
    )


@pytest.fixture
def offline_lookup_aggregator():
    """
    Fixture for a LookupAggregator for serving offline features
    """
    return LookupAggregator(source_type=SourceType.SNOWFLAKE, is_online_serving=False)


@pytest.fixture
def online_lookup_aggregator():
    """
    Fixture for a LookupAggregator for serving online features
    """
    return LookupAggregator(source_type=SourceType.SNOWFLAKE, is_online_serving=True)


def update_aggregator(aggregator, specs):
    """
    Helper function to update Aggregator using a list of specs
    """
    for spec in specs:
        aggregator.update(spec)


def test_lookup_aggregator__offline_dimension_only(
    offline_lookup_aggregator, dimension_lookup_specs
):
    """
    Test lookup aggregator with only dimension lookup
    """
    aggregator = offline_lookup_aggregator
    update_aggregator(aggregator, dimension_lookup_specs)

    direct_lookup_specs = list(aggregator.iterate_grouped_lookup_specs(is_scd=False))
    assert len(direct_lookup_specs) == 1
    specs = [asdict(spec) for spec in direct_lookup_specs[0]]
    for spec in specs:
        spec.pop("source_expr")
    assert specs == [
        {
            "serving_names": ["CUSTOMER_ID"],
            "serving_names_mapping": None,
            "input_column_name": "cust_value_1",
            "feature_name": "CUSTOMER ATTRIBUTE 1",
            "entity_column": "cust_id",
            "scd_parameters": None,
        },
        {
            "serving_names": ["CUSTOMER_ID"],
            "serving_names_mapping": None,
            "input_column_name": "cust_value_2",
            "feature_name": "CUSTOMER ATTRIBUTE 2",
            "entity_column": "cust_id",
            "scd_parameters": None,
        },
    ]

    scd_lookup_specs = list(aggregator.iterate_grouped_lookup_specs(is_scd=True))
    assert len(scd_lookup_specs) == 0


def test_lookup_aggregator__offline_scd_only(
    offline_lookup_aggregator, scd_lookup_specs_with_current_flag
):
    """
    Test lookup aggregator with only scd lookups
    """
    aggregator = offline_lookup_aggregator
    update_aggregator(aggregator, scd_lookup_specs_with_current_flag)

    direct_lookup_specs = list(aggregator.iterate_grouped_lookup_specs(is_scd=False))
    assert len(direct_lookup_specs) == 0

    scd_lookup_specs = list(aggregator.iterate_grouped_lookup_specs(is_scd=True))
    assert len(scd_lookup_specs) == 1
    specs = [asdict(spec) for spec in scd_lookup_specs[0]]
    for spec in specs:
        spec.pop("source_expr")
    assert specs == [
        {
            "serving_names": ["CUSTOMER_ID"],
            "serving_names_mapping": None,
            "input_column_name": "membership_status",
            "feature_name": "Current Membership Status",
            "entity_column": "cust_id",
            "scd_parameters": SCDLookupParameters(
                effective_timestamp_column="event_timestamp",
                current_flag_column="is_record_current",
                end_timestamp_column=None,
                offset=None,
            ),
        }
    ]


def test_lookup_aggregator__online_with_current_flag(
    online_lookup_aggregator,
    scd_lookup_specs_with_current_flag,
):
    """
    Test lookup aggregator with only scd lookups
    """
    aggregator = online_lookup_aggregator
    update_aggregator(aggregator, scd_lookup_specs_with_current_flag)

    # With current flag column, scd lookup is simplified as direct lookup
    direct_lookup_specs = list(aggregator.iterate_grouped_lookup_specs(is_scd=False))
    assert len(direct_lookup_specs) == 1
    specs = [asdict(spec) for spec in direct_lookup_specs[0]]
    for spec in specs:
        spec.pop("source_expr")
    assert specs == [
        {
            "serving_names": ["CUSTOMER_ID"],
            "serving_names_mapping": None,
            "input_column_name": "membership_status",
            "feature_name": "Current Membership Status",
            "entity_column": "cust_id",
            "scd_parameters": SCDLookupParameters(
                effective_timestamp_column="event_timestamp",
                current_flag_column="is_record_current",
                end_timestamp_column=None,
                offset=None,
            ),
        }
    ]

    direct_lookups = aggregator.get_direct_lookups()
    assert len(direct_lookups) == 1
    assert direct_lookups[0].column_names == ["membership_status_a18d6f89f8538bdb"]
    assert direct_lookups[0].join_keys == ["CUSTOMER_ID"]
    expected_sql = textwrap.dedent(
        """
        SELECT
          "cust_id" AS "CUSTOMER_ID",
          "membership_status" AS "membership_status_a18d6f89f8538bdb"
        FROM (
          SELECT
            "effective_ts" AS "effective_ts",
            "cust_id" AS "cust_id",
            "membership_status" AS "membership_status"
          FROM "db"."public"."customer_profile_table"
          WHERE
            "is_record_current" = TRUE
        )
        """
    ).strip()
    assert direct_lookups[0].expr.sql(pretty=True) == expected_sql

    scd_lookup_specs = list(aggregator.iterate_grouped_lookup_specs(is_scd=True))
    assert len(scd_lookup_specs) == 0


def test_lookup_aggregator__online_without_current_flag(
    online_lookup_aggregator,
    scd_lookup_specs_without_current_flag,
):
    """
    Test lookup aggregator with only scd lookups without a current flag column
    """
    aggregator = online_lookup_aggregator
    update_aggregator(aggregator, scd_lookup_specs_without_current_flag)

    direct_lookup_specs = list(aggregator.iterate_grouped_lookup_specs(is_scd=False))
    assert len(direct_lookup_specs) == 0

    # If no current flag, SCD join has to be performed even during online serving
    scd_lookup_specs = list(aggregator.iterate_grouped_lookup_specs(is_scd=True))
    assert len(scd_lookup_specs) == 1
    specs = [asdict(spec) for spec in scd_lookup_specs[0]]
    for spec in specs:
        spec.pop("source_expr")
    assert specs == [
        {
            "serving_names": ["CUSTOMER_ID"],
            "serving_names_mapping": None,
            "input_column_name": "membership_status",
            "feature_name": "Current Membership Status",
            "entity_column": "cust_id",
            "scd_parameters": SCDLookupParameters(
                effective_timestamp_column="event_timestamp",
                current_flag_column=None,
                end_timestamp_column=None,
                offset=None,
            ),
        }
    ]


def test_lookup_aggregator__online_with_offset(
    online_lookup_aggregator,
    scd_lookup_specs_with_offset,
):
    """
    Test lookup aggregator with only scd lookups with offset
    """
    aggregator = online_lookup_aggregator
    update_aggregator(aggregator, scd_lookup_specs_with_offset)

    direct_lookup_specs = list(aggregator.iterate_grouped_lookup_specs(is_scd=False))
    assert len(direct_lookup_specs) == 0

    # If offset is specified, current flag column cannot be used to simplify online serving
    scd_lookup_specs = list(aggregator.iterate_grouped_lookup_specs(is_scd=True))
    assert len(scd_lookup_specs) == 1
    specs = [asdict(spec) for spec in scd_lookup_specs[0]]
    for spec in specs:
        spec.pop("source_expr")
    assert specs == [
        {
            "serving_names": ["CUSTOMER_ID"],
            "serving_names_mapping": None,
            "input_column_name": "membership_status",
            "feature_name": "Current Membership Status",
            "entity_column": "cust_id",
            "scd_parameters": SCDLookupParameters(
                effective_timestamp_column="event_timestamp",
                current_flag_column="is_record_current",
                end_timestamp_column=None,
                offset="14d",
            ),
        }
    ]