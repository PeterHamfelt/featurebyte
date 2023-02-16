"""
SQL generation for looking up parent entities
"""
from __future__ import annotations

from sqlglot import expressions
from sqlglot.expressions import Select, select

from featurebyte.enum import SpecialColumnName, TableDataType
from featurebyte.models.parent_serving import JoinStep
from featurebyte.query_graph.graph import QueryGraph
from featurebyte.query_graph.node.generic import EventLookupParameters, SCDLookupParameters
from featurebyte.query_graph.node.schema import FeatureStoreDetails
from featurebyte.query_graph.sql.aggregator.lookup import LookupAggregator
from featurebyte.query_graph.sql.builder import SQLOperationGraph
from featurebyte.query_graph.sql.common import SQLType, get_qualified_column_identifier
from featurebyte.query_graph.sql.specs import LookupSpec


def construct_request_table_with_parent_entities(
    request_table_name: str,
    request_table_columns: list[str],
    join_steps: list[JoinStep],
    feature_store_details: FeatureStoreDetails,
) -> Select:
    """
    Construct a query to join parent entities into the request table

    Parameters
    ----------
    request_table_name: str
        Request table name
    request_table_columns: list[str]
        Column names in the request table
    join_steps: list[JoinStep]
        The list of join steps to be applied. Each step joins a parent entity into the request
        table. Subsequent joins can use the newly joined columns as the join key.
    feature_store_details: FeatureStoreDetails
        Information about the feature store

    Returns
    -------
    Select
    """
    table_expr = select(
        *[get_qualified_column_identifier(col, "REQ") for col in request_table_columns]
    ).from_(expressions.alias_(request_table_name, "REQ"))

    current_columns = request_table_columns[:]
    for join_step in join_steps:
        table_expr = _apply_join_step(
            table_expr=table_expr,
            join_step=join_step,
            feature_store_details=feature_store_details,
            current_columns=current_columns,
        )
        current_columns.append(join_step.parent_serving_name)

    return table_expr


def _apply_join_step(
    table_expr: Select,
    join_step: JoinStep,
    feature_store_details: FeatureStoreDetails,
    current_columns: list[str],
) -> Select:

    # Use a LookupAggregator to join in the parent entity since the all the different types of
    # lookup logic dependent on the data type still apply (SCD lookup, time based event data lookup,
    # etc)
    aggregator = LookupAggregator(source_type=feature_store_details.type)
    spec = _get_lookup_spec_from_join_step(
        join_step=join_step,
        feature_store_details=feature_store_details,
    )
    aggregator.update(spec)
    aggregation_result = aggregator.update_aggregation_table_expr(
        table_expr=table_expr,
        point_in_time_column=SpecialColumnName.POINT_IN_TIME,
        current_columns=current_columns,
        current_query_index=0,
    )

    return aggregation_result.updated_table_expr


def _get_lookup_spec_from_join_step(
    join_step: JoinStep,
    feature_store_details: FeatureStoreDetails,
) -> LookupSpec:

    # Set up data specific parameters
    if join_step.data.type == TableDataType.SCD_DATA:
        scd_parameters = SCDLookupParameters(**join_step.data.dict())
    else:
        scd_parameters = None

    if join_step.data.type == TableDataType.EVENT_DATA:
        event_parameters = EventLookupParameters(**join_step.data.dict())
    else:
        event_parameters = None

    # Get the sql expression for the data
    graph = QueryGraph()
    input_node = graph.add_node(
        node=join_step.data.construct_input_node(feature_store_details=feature_store_details),
        input_nodes=[],
    )
    sql_operation_graph = SQLOperationGraph(
        query_graph=graph, sql_type=SQLType.AGGREGATION, source_type=feature_store_details.type
    )
    sql_input_node = sql_operation_graph.build(input_node)
    source_expr = sql_input_node.sql

    return LookupSpec(
        input_column_name=join_step.parent_key,
        feature_name=join_step.parent_serving_name,
        entity_column=join_step.child_key,
        serving_names=[join_step.child_serving_name],
        source_expr=source_expr,
        scd_parameters=scd_parameters,
        event_parameters=event_parameters,
        serving_names_mapping=None,
        entity_ids=[],  # entity_ids doesn't matter in this case, passing empty list for convenience
        is_parent_lookup=True,
    )