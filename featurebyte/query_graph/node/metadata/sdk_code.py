"""
This module contains models used for sdk code extractor.
"""
from __future__ import annotations

from typing import Any, DefaultDict, Dict, List, Optional, Sequence, Set, Tuple, Union

import json
import os
from collections import defaultdict
from enum import Enum

from bson import ObjectId
from jinja2 import Template
from pydantic import BaseModel, Field

from featurebyte.common.typing import Scalar
from featurebyte.common.utils import get_version
from featurebyte.models.base import PydanticObjectId
from featurebyte.query_graph.enum import NodeOutputType
from featurebyte.query_graph.node.metadata.operation import NodeOutputCategory


class ValueStr(str):
    """
    ValueStr class is used to represent value in python code, for example: 1, 'a', 1.23, ['a']
    """

    @classmethod
    def create(cls, value: Union[ObjectId, Scalar, Sequence[Scalar]]) -> ValueStr:
        """
        Create expression from a given value

        Parameters
        ----------
        value: Union[ObjectId, Scalar, Sequence[Scalar]]
            Input value

        Returns
        -------
        ExpressionStr
        """
        if isinstance(value, str):
            return ValueStr(json.dumps(value))
        if isinstance(value, ObjectId):
            return ValueStr(f'"{value}"')
        return ValueStr(value)

    def as_input(self) -> str:
        """
        Used as an input in an expression

        Returns
        -------
        str
        """
        return str(self)


class VariableNameStr(str):
    """
    VariableNameStr class is used to represent variable name string in the code. It also includes
    indexed variable, for example: `event_data`, `event_data['timestamp']`.
    """

    def as_input(self) -> str:
        """
        Used as an input in an expression

        Returns
        -------
        str
        """
        return str(self)


class ExpressionStr(str):
    """
    ExpressionStr class is used to represent a combination of operations, variables, or values that will
    produce a result when evaluated, for example: `event_data['quantity'] * event_data['price_per_unit']`.
    """

    def as_input(self) -> str:
        """
        Used as an input in an expression

        Returns
        -------
        str
        """
        return f"({self})"


class StatementStr(str):
    """
    StatementStr class is used to represent an instruction that performs specific task, for example:
    `event_data['rate'] = 1.34`, `col = event_view["amount"]`.
    """


class ObjectClass(BaseModel):
    """
    ObjectClass is used as a mock class object which are used to
    - capture the method/function input parameters
    - import objects
    """

    module_path: str
    class_name: str
    positional_args: List[Any]
    keyword_args: Dict[str, Any]
    method_name: Optional[str] = Field(default=None)

    def __str__(self) -> str:
        params: List[Union[VariableNameStr, ExpressionStr, ValueStr, str]] = []
        for elem in self.positional_args:
            if not isinstance(elem, VariableNameStr) and not isinstance(elem, ExpressionStr):
                params.append(ValueStr.create(elem))
            else:
                params.append(elem)

        for key, value in self.keyword_args.items():
            if not isinstance(value, VariableNameStr) and not isinstance(value, ExpressionStr):
                params.append(f"{key}={ValueStr.create(value)}")
            else:
                params.append(f"{key}={value}")

        if self.method_name:
            return f"{self.class_name}.{self.method_name}({', '.join(params)})"
        return f"{self.class_name}({', '.join(params)})"

    def __repr__(self) -> str:
        return str(self)

    @classmethod
    def _extract_import_helper(cls, obj: Any) -> Set[Tuple[str, str]]:
        output = set()
        if isinstance(obj, ObjectClass):
            output.update(cls._extract_import(obj))
        if isinstance(obj, list):
            for elem in obj:
                output.update(cls._extract_import_helper(elem))
        if isinstance(obj, dict):
            for value in obj.values():
                output.update(cls._extract_import_helper(value))
        return output

    @classmethod
    def _extract_import(cls, obj: ObjectClass) -> Set[Tuple[str, str]]:
        output = {(obj.module_path, obj.class_name)}
        for pos_arg in obj.positional_args:
            output.update(cls._extract_import_helper(pos_arg))
        for val_arg in obj.keyword_args.values():
            output.update(cls._extract_import_helper(val_arg))
        return output

    def extract_import(self) -> Set[Tuple[str, str]]:
        """
        Extract set of required (module_path, class_name) tuple for this object

        Returns
        -------
        Set[Tuple[str, str]]
        """
        return self._extract_import(self)


class ClassEnum(Enum):
    """
    ClassEnum is used to store the python package import tagging for specific classes or objects
    """

    # non-featurebyte related
    OBJECT_ID = ("bson", "ObjectId")

    # feature store
    FEATURE_STORE = ("featurebyte", "FeatureStore")

    # database details
    SNOWFLAKE_DETAILS = ("featurebyte", "SnowflakeDetails")
    DATABRICK_DETAILS = ("featurebyte", "DatabricksDetails")
    SPARK_DETAILS = ("featurebyte", "SparkDetails")
    SQLITE_DETAILS = ("featurebyte.query_graph.node.schema", "SQLiteDetails")
    TESTDB_DETAILS = ("featurebyte.query_graph.node.schema", "TestDatabaseDetails")

    # table details & tabular source
    TABLE_DETAILS = ("featurebyte.query_graph.node.schema", "TableDetails")
    TABULAR_SOURCE = ("featurebyte.query_graph.model.common_table", "TabularSource")

    # column
    COLUMN_INFO = ("featurebyte.query_graph.model.column_info", "ColumnInfo")

    # data
    DATABASE_TABLE = ("featurebyte.api.database_table", "DatabaseTable")
    EVENT_DATA = ("featurebyte", "EventData")
    ITEM_DATA = ("featurebyte", "ItemData")
    DIMENSION_DATA = ("featurebyte", "DimensionData")
    SCD_DATA = ("featurebyte", "SlowlyChangingData")

    # view
    EVENT_VIEW = ("featurebyte", "EventView")
    ITEM_VIEW = ("featurebyte", "ItemView")
    DIMENSION_VIEW = ("featurebyte", "DimensionView")
    SCD_VIEW = ("featurebyte", "SlowlyChangingView")

    def __call__(
        self, *args: Any, _method_name: Optional[str] = None, **kwargs: Any
    ) -> ObjectClass:
        module_path, class_name = self.value
        return ObjectClass(
            module_path=module_path,
            class_name=class_name,
            method_name=_method_name,
            positional_args=args,
            keyword_args=kwargs,
        )


VarNameExpressionStr = Union[VariableNameStr, ExpressionStr]
RightHandSide = Union[ValueStr, VariableNameStr, ExpressionStr, ObjectClass]
StatementT = Union[StatementStr, Tuple[VariableNameStr, RightHandSide]]


class CodeGenerationConfig(BaseModel):
    """
    CodeGenerationConfig is used to control the code generating style like whether to introduce a new variable to
    store some intermediate results.

    feature_store_name: str
        Feature store name used to construct unsaved data object
    final_output_name: str
        Variable name which contains final output
    to_use_saved_data: str
        When enabled, load the data object from the persistent, otherwise construct the data from
        feature store explicitly
    max_expression_length: int
        Maximum expression length used to decide whether to assign the expression into a variable
        to reduce overall statement's line width.
    """

    # values not controlled by the query graph (can be configured outside graph)
    feature_store_id: PydanticObjectId = Field(default_factory=ObjectId)
    feature_store_name: str = Field(default="feature_store")
    final_output_name: str = Field(default="output")

    # other configurations
    to_use_saved_data: bool = Field(default=False)
    max_expression_length: int = Field(default=60)


class VariableNameGenerator(BaseModel):
    """
    VariableNameGenerator class is used to generate the variable name given the characteristics of the
    value to be stored.
    """

    var_name_counter: DefaultDict[str, int] = Field(default_factory=lambda: defaultdict(int))

    def generate_variable_name(
        self,
        node_output_type: NodeOutputType,
        node_output_category: NodeOutputCategory,
    ) -> VariableNameStr:
        """
        Generate a valid variable name (no name collision) based on node output type (series or frame) &
        category (view or feature) characteristic.

        Parameters
        ----------
        node_output_type: NodeOutputType
            Node output type (series or frame)
        node_output_category: NodeOutputCategory
            Node output category (view or feature)

        Returns
        -------
        VariableNameStr
        """
        if node_output_category == NodeOutputCategory.VIEW:
            if node_output_type == NodeOutputType.FRAME:
                pre_variable_name = "view"
            else:
                pre_variable_name = "col"
        else:
            if node_output_type == NodeOutputType.FRAME:
                pre_variable_name = "grouped"
            else:
                pre_variable_name = "feat"

        return self.convert_to_variable_name(variable_name_prefix=pre_variable_name)

    def convert_to_variable_name(self, variable_name_prefix: str) -> VariableNameStr:
        """
        Convert an input variable name into a valid variable name (no name collision).

        Parameters
        ----------
        variable_name_prefix: str
            Variable name before name collision check

        Returns
        -------
        VariableNameStr
        """
        count = self.var_name_counter[variable_name_prefix]
        self.var_name_counter[variable_name_prefix] += 1
        if count:
            return VariableNameStr(f"{variable_name_prefix}_{count}")
        return VariableNameStr(variable_name_prefix)


class CodeGenerator(BaseModel):
    """
    SDKCodeGenerator class is used to generate the SDK codes from a list of import tags and statements.

    A statement could be one
    of the following two forms:

        a) Statement: Statement("event_view['ratio'] = 1.34")
        b) Tuple[VariableName, Expression]: (VariableName("col"), Expression("event_view['amount']"))
    """

    statements: List[StatementT] = Field(default_factory=list)

    @staticmethod
    def _get_template() -> Template:
        template_path = os.path.join(os.path.dirname(__file__), "templates/sdk_code.tpl")
        with open(template_path, mode="r", encoding="utf-8") as file_handle:
            return Template(file_handle.read())

    def add_statements(self, statements: List[StatementT]) -> None:
        """
        Add statement to the list of statements

        Parameters
        ----------
        statements: List[Union[Statement, Tuple[VariableNameStr, ExpressionStr]]]
            Statements to be inserted
        """
        self.statements.extend(statements)

    def generate(self, to_format: bool = False) -> str:
        """
        Generate code as string using list of stored statements

        Parameters
        ----------
        to_format: bool
            Whether to format the final code

        Returns
        -------
        str
        """
        # process statements & extract required imports
        statement_lines = []
        import_pairs = set()
        for statement in self.statements:
            if isinstance(statement, tuple):
                var_name, right_hand_side = statement
                if isinstance(right_hand_side, ObjectClass):
                    import_pairs.update(right_hand_side.extract_import())
                statement_lines.append(f"{var_name} = {right_hand_side}")
            else:
                statement_lines.append(statement)
        statements = "\n".join(statement_lines)

        # process imports and generate import statements
        import_statements = []
        for module_path, name in sorted(import_pairs):
            import_statements.append(f"from {module_path} import {name}")
        imports = "\n".join(import_statements)

        # prepare final SDK code
        code = self._get_template().render(
            header_comment=f"# Generated by SDK version: {get_version()}",
            imports=imports,
            statements=statements,
        )
        if to_format:
            from black import FileMode, format_str  # pylint: disable=import-outside-toplevel

            return format_str(code, mode=FileMode())
        return code