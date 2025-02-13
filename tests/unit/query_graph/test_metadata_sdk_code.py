"""
Unit tests for featurebyte.query_graph.node.metadata.sdk_code
"""
import importlib

import pytest
from bson import ObjectId

from featurebyte import get_version
from featurebyte.query_graph.enum import NodeOutputType
from featurebyte.query_graph.node.metadata.operation import NodeOutputCategory
from featurebyte.query_graph.node.metadata.sdk_code import (
    ClassEnum,
    CodeGenerator,
    ExpressionStr,
    ValueStr,
    VariableNameGenerator,
    VariableNameStr,
)


@pytest.mark.parametrize(
    "value, expected, expected_as_input",
    [
        (123, "123", "123"),
        ("abc", '"abc"', '"abc"'),
        ("'abc'", "\"'abc'\"", "\"'abc'\""),
        ([123, "abc"], "[123, 'abc']", "[123, 'abc']"),
    ],
)
def test_value_string(value, expected, expected_as_input):
    """Test ValueStr class"""
    obj = ValueStr.create(value)
    assert str(obj) == expected
    assert obj.as_input() == expected_as_input
    assert eval(obj) == value


@pytest.mark.parametrize(
    "obj, expected",
    [
        (VariableNameStr("event_table"), "event_table"),
        (ExpressionStr("1 + 1"), "(1 + 1)"),
    ],
)
def test_variable_name_expression(obj, expected):
    """Test VariableNameStr and ExpressionStr"""
    assert obj.as_input() == expected


def test_class_enum__module_import():
    """Test enum in ClassEnum can be imported properly"""
    for tag in ClassEnum:
        package_path, name = tag.value
        package = importlib.import_module(package_path)
        assert name in dir(package)


def test_class_enum_and_object_class():
    """Test ClassEnum & ObjectClass interaction"""
    object_id = ObjectId("63eaeafcbe3a62da29705ad1")
    event_table = ClassEnum.EVENT_TABLE(ClassEnum.OBJECT_ID(object_id), name="event_table")
    assert (
        str(event_table)
        == repr(event_table)
        == 'EventTable(ObjectId("63eaeafcbe3a62da29705ad1"), name="event_table")'
    )
    assert event_table.extract_import() == {ClassEnum.EVENT_TABLE.value, ClassEnum.OBJECT_ID.value}

    # check ObjectClass object inside containers (list & dict)
    event_table = ClassEnum.EVENT_TABLE(
        id=ClassEnum.OBJECT_ID(object_id),
        list_value=[ClassEnum.COLUMN_INFO(name="column")],
        dict_value={
            "key": ClassEnum.TABULAR_SOURCE("some_value"),
            "list_value": [ClassEnum.COLUMN_INFO(name="other_column")],
        },
    )
    expected_str = (
        'EventTable(id=ObjectId("63eaeafcbe3a62da29705ad1"), list_value=[ColumnInfo(name="column")], '
        "dict_value={'key': TabularSource(\"some_value\"), 'list_value': [ColumnInfo(name=\"other_column\")]})"
    )
    assert str(event_table) == repr(event_table) == expected_str
    assert event_table.extract_import() == {
        ClassEnum.EVENT_TABLE.value,
        ClassEnum.OBJECT_ID.value,
        ClassEnum.COLUMN_INFO.value,
        ClassEnum.TABULAR_SOURCE.value,
    }

    # check _method_name
    event_table = ClassEnum.EVENT_TABLE(ClassEnum.OBJECT_ID("1234"), _method_name="get_by_id")
    assert str(event_table) == repr(event_table) == 'EventTable.get_by_id(ObjectId("1234"))'
    assert event_table.extract_import() == {ClassEnum.EVENT_TABLE.value, ClassEnum.OBJECT_ID.value}


def test_variable_name_generator():
    """Test VariableNameGenerator"""
    var_gen = VariableNameGenerator()
    input_params_expected_pairs = [
        ((NodeOutputType.SERIES, NodeOutputCategory.VIEW), "col"),
        ((NodeOutputType.FRAME, NodeOutputCategory.VIEW), "view"),
        ((NodeOutputType.SERIES, NodeOutputCategory.FEATURE), "feat"),
        ((NodeOutputType.FRAME, NodeOutputCategory.FEATURE), "grouped"),
        ((NodeOutputType.SERIES, NodeOutputCategory.VIEW), "col_1"),
        ((NodeOutputType.FRAME, NodeOutputCategory.VIEW), "view_1"),
        ((NodeOutputType.SERIES, NodeOutputCategory.FEATURE), "feat_1"),
        ((NodeOutputType.FRAME, NodeOutputCategory.FEATURE), "grouped_1"),
    ]
    for (output_type, output_cat), expected in input_params_expected_pairs:
        var_name = var_gen.generate_variable_name(
            node_output_type=output_type,
            node_output_category=output_cat,
            node_name=None,
        )
        assert var_name == expected

    assert var_gen.convert_to_variable_name("event_table", node_name=None) == "event_table"
    assert var_gen.convert_to_variable_name("event_view", node_name=None) == "event_view"
    assert var_gen.convert_to_variable_name("event_view", node_name=None) == "event_view_1"
    assert var_gen.convert_to_variable_name("feat", node_name=None) == "feat_2"


def test_code_generator():
    """Test CodeGenerator"""
    code_gen = CodeGenerator()
    assert code_gen.generate() == "# Generated by SDK version: {version}\n\n\n".format(
        version=get_version()
    )

    code_gen.add_statements(
        statements=[(VariableNameStr("event_table"), ClassEnum.EVENT_TABLE(name="event_table"))],
    )
    assert code_gen.generate(remove_unused_variables=False) == (
        "# Generated by SDK version: {version}\n"
        "from featurebyte import EventTable\n\n"
        'event_table = EventTable(name="event_table")'
    ).format(version=get_version())

    code_gen.add_statements(
        statements=[
            (VariableNameStr("event_table_1"), ClassEnum.EVENT_TABLE(name="another_event_table"))
        ],
    )
    assert code_gen.generate(remove_unused_variables=False) == (
        "# Generated by SDK version: {version}\n"
        "from featurebyte import EventTable\n\n"
        'event_table = EventTable(name="event_table")\n'
        'event_table_1 = EventTable(name="another_event_table")'
    ).format(version=get_version())
