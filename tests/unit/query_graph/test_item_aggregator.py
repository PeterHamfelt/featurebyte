"""
Unit tests for featurebyte.query_graph.sql.aggregator.item.ItemAggregator
"""
import textwrap

import pytest
from sqlglot.expressions import select

from featurebyte.enum import SourceType
from featurebyte.query_graph.node.generic import ItemGroupbyParameters
from featurebyte.query_graph.sql.aggregator.item import ItemAggregator
from featurebyte.query_graph.sql.specs import ItemAggregationSpec


@pytest.fixture
def item_table_sql():
    return select("*").from_("ITEM_TABLE")


@pytest.fixture
def aggregation_spec_order_size(item_table_sql):
    params = ItemGroupbyParameters(
        keys=["order_id"],
        serving_names=["serving_order_id"],
        agg_func="count",
        name="order_size",
    )
    return ItemAggregationSpec(
        serving_names=["serving_order_id"],
        serving_names_mapping={"serving_order_id": "new_serving_order_id"},
        parameters=params,
        source_expr=item_table_sql,
    )


@pytest.fixture
def aggregation_spec_max_item_price(item_table_sql):
    params = ItemGroupbyParameters(
        keys=["order_id"],
        serving_names=["serving_order_id"],
        parent="price",
        agg_func="max",
        name="max_item_price",
    )
    return ItemAggregationSpec(
        serving_names=["serving_order_id"],
        serving_names_mapping={"serving_order_id": "new_serving_order_id"},
        parameters=params,
        source_expr=item_table_sql,
    )


@pytest.fixture
def aggregation_spec_with_category(item_table_sql):
    params = ItemGroupbyParameters(
        keys=["order_id"],
        serving_names=["serving_order_id"],
        value_by="item_type",
        parent="price",
        agg_func="max",
        name="max_item_price_by_type",
    )
    return ItemAggregationSpec(
        serving_names=["serving_order_id"],
        serving_names_mapping={"serving_order_id": "new_serving_order_id"},
        parameters=params,
        source_expr=item_table_sql,
    )


@pytest.fixture
def aggregation_specs(
    aggregation_spec_order_size,
    aggregation_spec_max_item_price,
    aggregation_spec_with_category,
):
    return [
        aggregation_spec_order_size,
        aggregation_spec_max_item_price,
        aggregation_spec_with_category,
    ]


def test_item_aggregation(aggregation_specs):
    """
    Test ItemAggregator
    """

    aggregator = ItemAggregator(source_type=SourceType.SNOWFLAKE)
    for spec in aggregation_specs:
        aggregator.update(spec)
    # updating same spec twice should not have issue
    for spec in aggregation_specs:
        aggregator.update(spec)

    result = aggregator.update_aggregation_table_expr(
        select("a").from_("REQUEST_TABLE"), "POINT_IN_TIME", ["a"], 0
    )

    expected = textwrap.dedent(
        """
        SELECT
          a,
          "T0"."count_None_96c6eef6e2c57bc9" AS "count_None_96c6eef6e2c57bc9",
          "T0"."max_price_96c6eef6e2c57bc9" AS "max_price_96c6eef6e2c57bc9",
          "T1"."max_price_fc08c26b73105fff" AS "max_price_fc08c26b73105fff"
        FROM REQUEST_TABLE
        LEFT JOIN (
          SELECT
            REQ."new_serving_order_id" AS "new_serving_order_id",
            COUNT(*) AS "count_None_96c6eef6e2c57bc9",
            MAX(ITEM."price") AS "max_price_96c6eef6e2c57bc9"
          FROM "REQUEST_TABLE_new_serving_order_id" AS REQ
          INNER JOIN (
            SELECT
              *
            FROM ITEM_TABLE
          ) AS ITEM
            ON REQ."new_serving_order_id" = ITEM."order_id"
          GROUP BY
            REQ."new_serving_order_id"
        ) AS T0
          ON REQ."new_serving_order_id" = T0."new_serving_order_id"
        LEFT JOIN (
          SELECT
            INNER_."new_serving_order_id",
            OBJECT_AGG(
              CASE
                WHEN INNER_."item_type" IS NULL
                THEN '__MISSING__'
                ELSE CAST(INNER_."item_type" AS VARCHAR)
              END,
              TO_VARIANT(INNER_."max_price_fc08c26b73105fff_inner")
            ) AS "max_price_fc08c26b73105fff"
          FROM (
            SELECT
              REQ."new_serving_order_id" AS "new_serving_order_id",
              ITEM."item_type" AS "item_type",
              MAX(ITEM."price") AS "max_price_fc08c26b73105fff_inner"
            FROM "REQUEST_TABLE_new_serving_order_id" AS REQ
            INNER JOIN (
              SELECT
                *
              FROM ITEM_TABLE
            ) AS ITEM
              ON REQ."new_serving_order_id" = ITEM."order_id"
            GROUP BY
              REQ."new_serving_order_id",
              ITEM."item_type"
          ) AS INNER_
          GROUP BY
            INNER_."new_serving_order_id"
        ) AS T1
          ON REQ."new_serving_order_id" = T1."new_serving_order_id"
        """
    ).strip()
    assert result.updated_table_expr.sql(pretty=True) == expected

    request_table_ctes = aggregator.get_common_table_expressions("REQUEST_TABLE")
    assert len(request_table_ctes) == 1
    expected = textwrap.dedent(
        """
        SELECT DISTINCT
          "new_serving_order_id"
        FROM REQUEST_TABLE
        """
    ).strip()
    assert request_table_ctes[0][0] == '"REQUEST_TABLE_new_serving_order_id"'
    assert request_table_ctes[0][1].sql(pretty=True) == expected