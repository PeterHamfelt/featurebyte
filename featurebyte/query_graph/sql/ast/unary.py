"""
Module for unary operations sql generation
"""
from __future__ import annotations

from typing import Literal, cast

from dataclasses import dataclass

from sqlglot import Expression, expressions, parse_one

from featurebyte.enum import DBVarType
from featurebyte.query_graph.enum import NodeType
from featurebyte.query_graph.sql.ast.base import ExpressionNode, SQLNodeContext
from featurebyte.query_graph.sql.ast.literal import make_literal_value
from featurebyte.query_graph.sql.ast.util import prepare_unary_input_nodes


@dataclass
class UnaryOp(ExpressionNode):
    """Typical unary operation node (can be handled identically given the correct sqlglot
    expression)
    """

    expr: ExpressionNode
    operation: type[expressions.Expression]

    node_type_to_expression_cls = {
        NodeType.SQRT: expressions.Sqrt,
        NodeType.ABS: expressions.Abs,
        NodeType.FLOOR: expressions.Floor,
        NodeType.CEIL: expressions.Ceil,
        NodeType.NOT: expressions.Not,
        NodeType.LENGTH: expressions.Length,
        NodeType.LOG: expressions.Ln,
        NodeType.EXP: expressions.Exp,
    }
    query_node_type = list(node_type_to_expression_cls.keys())

    @property
    def sql(self) -> Expression:
        return self.operation(this=self.expr.sql)

    @classmethod
    def build(cls, context: SQLNodeContext) -> UnaryOp:
        input_expr_node = cast(ExpressionNode, context.input_sql_nodes[0])
        table_node = input_expr_node.table_node
        expr_cls = cls.node_type_to_expression_cls[context.query_node.type]
        node = UnaryOp(
            context=context, table_node=table_node, expr=input_expr_node, operation=expr_cls
        )
        return node


@dataclass
class IsNullNode(ExpressionNode):
    """Node for IS_NULL operation"""

    expr: ExpressionNode
    query_node_type = NodeType.IS_NULL

    @property
    def sql(self) -> Expression:
        return expressions.Is(this=self.expr.sql, expression=expressions.Null())

    @classmethod
    def build(cls, context: SQLNodeContext) -> IsNullNode:
        table_node, expr_node, _ = prepare_unary_input_nodes(context)
        return IsNullNode(context=context, table_node=table_node, expr=expr_node)


@dataclass
class CastNode(ExpressionNode):
    """Node for casting operation"""

    expr: ExpressionNode
    new_type: Literal["int", "float", "str"]
    from_dtype: DBVarType
    query_node_type = NodeType.CAST

    @property
    def sql(self) -> Expression:
        if self.from_dtype == DBVarType.FLOAT and self.new_type == "int":
            # Casting to INTEGER performs rounding (could be up or down). Hence, apply FLOOR first
            # to mimic pandas astype(int)
            expr = expressions.Floor(this=self.expr.sql)
        elif self.from_dtype == DBVarType.BOOL and self.new_type == "float":
            # Casting to FLOAT from BOOL directly is not allowed
            expr = expressions.Cast(this=self.expr.sql, to=parse_one("LONG"))
        else:
            expr = self.expr.sql
        type_expr = {
            "int": parse_one("LONG"),
            "float": parse_one("FLOAT"),
            "str": parse_one("VARCHAR"),
        }[self.new_type]
        output_expr = expressions.Cast(this=expr, to=type_expr)
        return output_expr

    @classmethod
    def build(cls, context: SQLNodeContext) -> CastNode:
        table_node, input_expr_node, parameters = prepare_unary_input_nodes(context)
        sql_node = CastNode(
            context=context,
            table_node=table_node,
            expr=input_expr_node,
            new_type=parameters["type"],
            from_dtype=parameters["from_dtype"],
        )
        return sql_node


@dataclass
class LagNode(ExpressionNode):
    """Node for lag operation"""

    expr: ExpressionNode
    entity_columns: list[str]
    timestamp_column: str
    offset: int
    query_node_type = NodeType.LAG

    @property
    def sql(self) -> Expression:
        partition_by = [
            expressions.Column(this=expressions.Identifier(this=col, quoted=True))
            for col in self.entity_columns
        ]
        order = expressions.Order(
            expressions=[
                expressions.Ordered(
                    this=expressions.Identifier(this=self.timestamp_column, quoted=True)
                )
            ]
        )
        output_expr = expressions.Window(
            this=expressions.Anonymous(
                this="LAG", expressions=[self.expr.sql, make_literal_value(self.offset)]
            ),
            partition_by=partition_by,
            order=order,
        )
        return output_expr

    @classmethod
    def build(cls, context: SQLNodeContext) -> LagNode:
        table_node, input_expr_node, parameters = prepare_unary_input_nodes(context)
        sql_node = LagNode(
            context=context,
            table_node=table_node,
            expr=input_expr_node,
            entity_columns=parameters["entity_columns"],
            timestamp_column=parameters["timestamp_column"],
            offset=parameters["offset"],
        )
        return sql_node