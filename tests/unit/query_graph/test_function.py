"""
This module contains generic function related node classes
"""
import pytest
from bson import ObjectId

from featurebyte.enum import AggFunc, DBVarType, TableDataType
from featurebyte.query_graph.enum import NodeOutputType, NodeType
from featurebyte.query_graph.node.metadata.operation import (
    AggregationColumn,
    DerivedDataColumn,
    NodeOutputCategory,
    PostAggregationColumn,
    SourceDataColumn,
)
from featurebyte.query_graph.transform.operation_structure import OperationStructureExtractor
from featurebyte.query_graph.transform.sdk_code import SDKCodeExtractor


def test_generic_function__view_type(global_graph, input_node):
    """Test adding generic function node to query graph (View)"""
    proj_a = global_graph.add_operation(
        node_type=NodeType.PROJECT,
        node_params={"columns": ["a"]},
        node_output_type=NodeOutputType.SERIES,
        input_nodes=[input_node],
    )
    gfunc = global_graph.add_operation(
        node_type=NodeType.GENERIC_FUNCTION,
        node_params={
            "function_name": "my_func",
            "function_parameters": [
                {"column_name": "a", "dtype": "FLOAT", "input_form": "column"},
                {"value": 1, "dtype": "INT", "input_form": "value"},
                {"value": 2.0, "dtype": "FLOAT", "input_form": "value"},
                {"value": "hello", "dtype": "VARCHAR", "input_form": "value"},
                {"value": True, "dtype": "BOOL", "input_form": "value"},
            ],
            "output_dtype": DBVarType.FLOAT,
            "function_id": ObjectId("5f9b3b3b9c6d2b1a3f9b3b3b"),
        },
        node_output_type=NodeOutputType.SERIES,
        input_nodes=[proj_a],
    )

    # check node methods & attributes
    assert gfunc.max_input_count == 1
    assert gfunc.derive_var_type(inputs=[]) == DBVarType.FLOAT

    # check output operation structure
    op_struct = global_graph.extract_operation_structure(node=gfunc)
    assert op_struct.is_time_based is False
    assert op_struct.output_category == NodeOutputCategory.VIEW
    assert op_struct.output_type == NodeOutputType.SERIES
    assert op_struct.columns == [
        DerivedDataColumn(
            name=None,
            dtype=DBVarType.FLOAT,
            filter=False,
            node_names={"input_1", "project_1", "generic_function_1"},
            node_name="generic_function_1",
            transforms=["my_func"],
            columns=[
                SourceDataColumn(
                    name="a",
                    dtype=DBVarType.FLOAT,
                    filter=False,
                    node_names={"input_1", "project_1"},
                    node_name="input_1",
                    table_id=None,
                    table_type=TableDataType.EVENT_TABLE,
                )
            ],
        ),
    ]
    assert op_struct.aggregations == []

    # check the code generated by the generic function node
    state = SDKCodeExtractor(graph=global_graph).extract(node=gfunc)
    assert state.code_generator.statements[-1] == ("output", 'my_func(col, 1, 2.0, "hello", True)')


def test_generic_function__feature_type(global_graph, query_graph_with_groupby_and_feature_nodes):
    """Test adding generic function node to query graph (Feature)"""
    graph, feature_proj, _ = query_graph_with_groupby_and_feature_nodes
    gfunc = graph.add_operation(
        node_type=NodeType.GENERIC_FUNCTION,
        node_params={
            "function_name": "my_func",
            "function_parameters": [
                {"value": 1, "dtype": "INT", "input_form": "value"},
                {"column_name": "a", "dtype": "FLOAT", "input_form": "column"},
            ],
            "output_dtype": DBVarType.FLOAT,
            "function_id": ObjectId("5f9b3b3b9c6d2b1a3f9b3b3b"),
        },
        node_output_type=NodeOutputType.SERIES,
        input_nodes=[feature_proj],
    )

    # check node methods & attributes
    assert gfunc.max_input_count == 1
    assert gfunc.derive_var_type(inputs=[]) == DBVarType.FLOAT

    # check output operation structure
    op_struct = graph.extract_operation_structure(node=gfunc)
    assert op_struct.is_time_based is True
    assert op_struct.output_category == NodeOutputCategory.FEATURE
    assert op_struct.output_type == NodeOutputType.SERIES
    assert op_struct.columns == [
        SourceDataColumn(
            name="a",
            dtype=DBVarType.FLOAT,
            filter=False,
            node_names={"input_1"},
            node_name="input_1",
            table_id=None,
            table_type=TableDataType.EVENT_TABLE,
        ),
    ]
    assert op_struct.aggregations == [
        PostAggregationColumn(
            name=None,
            dtype=DBVarType.FLOAT,
            filter=False,
            node_names={"input_1", "groupby_1", "project_3", "generic_function_1"},
            node_name="generic_function_1",
            transforms=["my_func"],
            columns=[
                AggregationColumn(
                    name="a_2h_average",
                    dtype=DBVarType.FLOAT,
                    filter=False,
                    node_names={"input_1", "groupby_1", "project_3"},
                    node_name="groupby_1",
                    method=AggFunc.AVG,
                    keys=["cust_id"],
                    window="2h",
                    category=None,
                    aggregation_type="groupby",
                    column=SourceDataColumn(
                        name="a",
                        dtype=DBVarType.FLOAT,
                        filter=False,
                        node_names={"input_1"},
                        node_name="input_1",
                        table_id=None,
                        table_type=TableDataType.EVENT_TABLE,
                    ),
                )
            ],
        )
    ]

    # check the code generated by the generic function node
    state = SDKCodeExtractor(graph=global_graph).extract(node=gfunc)
    assert state.code_generator.statements[-1] == ("output", "my_func(1, feat)")


def test_generic_function__invalid_inputs(global_graph, query_graph_with_groupby_and_feature_nodes):
    """Test adding generic function node to query graph with non-homogenous inputs"""
    graph, feature_proj, _ = query_graph_with_groupby_and_feature_nodes
    gfunc_node_params = {
        "function_name": "my_func",
        "function_parameters": [
            {"value": 1, "dtype": "INT", "input_form": "value"},
            {"column_name": "a", "dtype": "FLOAT", "input_form": "column"},
        ],
        "output_dtype": DBVarType.FLOAT,
        "function_id": ObjectId("5f9a3b3b9b3f4a1b9f6b1b1b"),
    }

    # check generic function node with feature and view inputs (non-homogenous)
    view_proj = graph.get_node_by_name("project_1")
    gfunc_1 = graph.add_operation(
        node_type=NodeType.GENERIC_FUNCTION,
        node_params=gfunc_node_params,
        node_output_type=NodeOutputType.SERIES,
        input_nodes=[feature_proj, view_proj],
    )
    with pytest.raises(ValueError, match="Input category type is not homogeneous"):
        OperationStructureExtractor(graph=global_graph).extract(node=gfunc_1)

    # check generic function node with non series input
    view = graph.get_node_by_name("input_1")
    gfunc_2 = graph.add_operation(
        node_type=NodeType.GENERIC_FUNCTION,
        node_params=gfunc_node_params,
        node_output_type=NodeOutputType.SERIES,
        input_nodes=[view_proj, view],
    )
    with pytest.raises(ValueError, match="Input type is not series"):
        OperationStructureExtractor(graph=global_graph).extract(node=gfunc_2)

    # check generic function node with non-aligned row index lineage
    filter_node = graph.add_operation(
        node_type=NodeType.FILTER,
        node_params={},
        node_output_type=NodeOutputType.FRAME,
        input_nodes=[view, view_proj],
    )
    proj_filter = graph.add_operation(
        node_type=NodeType.PROJECT,
        node_params={"columns": ["a"]},
        node_output_type=NodeOutputType.SERIES,
        input_nodes=[filter_node],
    )
    gfunc_3 = graph.add_operation(
        node_type=NodeType.GENERIC_FUNCTION,
        node_params=gfunc_node_params,
        node_output_type=NodeOutputType.SERIES,
        input_nodes=[view_proj, proj_filter],
    )
    with pytest.raises(ValueError, match="Input row index is not matched"):
        OperationStructureExtractor(graph=global_graph).extract(node=gfunc_3)