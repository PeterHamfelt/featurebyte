"""
Unit test for DatabricksSession
"""
from unittest import mock

import pandas as pd
import pytest

from featurebyte.enum import DBVarType
from featurebyte.session.databricks import DatabricksSession


@pytest.fixture
def databricks_session_dict():
    """
    DatabricksSession parameters
    """
    return {
        "server_hostname": "some-databricks-hostname",
        "http_path": "some-databricks-http-endpoint",
        "access_token": "some-databricks-access-token",
        "featurebyte_catalog": "hive_metastore",
        "featurebyte_schema": "featurebyte",
    }


class MockDatabricksConnection:
    """
    Mocked Databricks connection
    """

    def __init__(self, *args, **kwargs):
        self.description = None
        self.result_rows = None

    def cursor(self):
        return self

    def catalogs(self):
        self.description = [["TABLE_CAT"]]
        self.result_rows = [["hive_metastore"], ["samples"]]
        return self

    def schemas(self, *args, **kwargs):
        self.description = [["TABLE_SCHEM"], ["TABLE_CATALOG"]]
        self.result_rows = [
            ["default", "hive_metastore"],
            ["demo", "hive_metastore"],
        ]
        return self

    def tables(self, *args, **kwargs):
        self.description = [["TABLE_CAT"], ["TABLE_SCHEM"], ["TABLE_NAME"]]
        self.result_rows = [
            ["hive_metastore", "default", "transactions"],
            ["hive_metastore", "default", "calls"],
        ]
        return self

    def columns(self, *args, **kwargs):
        self.description = [["COLUMN_NAME"], ["TYPE_NAME"]]
        self.result_rows = [
            ["col_binary", "BINARY"],
            ["col_bool", "BOOLEAN"],
            ["col_date", "DATE"],
            ["col_decimal", "DECIMAL"],
            ["col_double", "DOUBLE"],
            ["col_float", "FLOAT"],
            ["col_int", "INT"],
            ["col_interval", "INTERVAL"],
            ["col_void", "VOID"],
            ["col_timestamp", "TIMESTAMP"],
            ["col_array", "ARRAY"],
            ["col_map", "MAP"],
            ["col_struct", "STRUCT"],
            ["col_string", "STRING"],
        ]
        return self

    def fetchall(self):
        return self.result_rows[:]

    def fetchall_arrow(self):
        columns = [cols[0] for cols in self.description]
        data = []
        for row in self.result_rows:
            data.append({k: v for (k, v) in zip(columns, row)})
        df = pd.DataFrame(data)
        mock_arrow_table = mock.Mock()
        mock_arrow_table.to_pandas.return_value = df
        return mock_arrow_table

    def execute(self, *args, **kwargs):
        self.description = [["a"], ["b"], ["c"]]
        self.result_rows = [
            [1, 2, 3],
            [100, 200, 300],
        ]
        return self

    def close(self):
        pass


@pytest.fixture
def databricks_connection():
    """
    Mock databricks connector in featurebyte.session.databricks module
    """
    with mock.patch("featurebyte.session.databricks.databricks_sql") as mock_connector:
        mock_connector.connect.return_value = MockDatabricksConnection()
        yield mock_connector


@pytest.mark.usefixtures("databricks_connection")
@pytest.mark.asyncio
async def test_databricks_session(databricks_session_dict):
    """
    Test DatabricksSession
    """
    session = DatabricksSession(**databricks_session_dict)
    assert session.server_hostname == "some-databricks-hostname"
    assert session.http_path == "some-databricks-http-endpoint"
    assert session.access_token == "some-databricks-access-token"
    assert await session.list_databases() == ["hive_metastore", "samples"]
    assert await session.list_schemas(database_name="hive_metastore") == ["default", "demo"]
    assert await session.list_tables(database_name="hive_metastore", schema_name="default") == [
        "transactions",
        "calls",
    ]
    assert await session.list_table_schema(
        database_name="hive_metastore", schema_name="default", table_name="transactions"
    ) == {
        "col_binary": DBVarType.BINARY,
        "col_bool": DBVarType.BOOL,
        "col_date": DBVarType.DATE,
        "col_decimal": DBVarType.FLOAT,
        "col_double": DBVarType.FLOAT,
        "col_float": DBVarType.FLOAT,
        "col_int": DBVarType.INT,
        "col_interval": DBVarType.TIMEDELTA,
        "col_void": DBVarType.VOID,
        "col_timestamp": DBVarType.TIMESTAMP,
        "col_array": DBVarType.ARRAY,
        "col_map": DBVarType.MAP,
        "col_struct": DBVarType.STRUCT,
        "col_string": DBVarType.VARCHAR,
    }
    df_result = await session.execute_async_query("SELECT * FROM table")
    df_expected = pd.DataFrame({"a": [1, 100], "b": [2, 200], "c": [3, 300]})
    pd.testing.assert_frame_equal(df_result, df_expected)


def test_databricks_sql_connector_not_available(databricks_session_dict):
    """
    Simulate missing databricks-sql-connector dependency
    """
    with mock.patch("featurebyte.session.databricks.HAS_DATABRICKS_SQL_CONNECTOR", False):
        with pytest.raises(RuntimeError) as exc:
            _ = DatabricksSession(**databricks_session_dict)
        assert str(exc.value) == "databricks-sql-connector is not available"
