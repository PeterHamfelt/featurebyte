"""
DatabricksSession class
"""
from __future__ import annotations

from typing import Any, OrderedDict

import collections

import pandas as pd

try:
    from databricks import sql as databricks_sql

    HAS_DATABRICKS_SQL_CONNECTOR = True
except ImportError:
    HAS_DATABRICKS_SQL_CONNECTOR = False

from pydantic import Field

from featurebyte.enum import DBVarType, SourceType
from featurebyte.query_graph.sql.dataframe import construct_dataframe_sql_expr
from featurebyte.session.base import BaseSchemaInitializer, BaseSession


class DatabricksSession(BaseSession):
    """
    Databricks session class
    """

    server_hostname: str
    http_path: str
    access_token: str
    featurebyte_catalog: str
    featurebyte_schema: str
    source_type: SourceType = Field(SourceType.DATABRICKS, const=True)

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)

        if not HAS_DATABRICKS_SQL_CONNECTOR:
            raise RuntimeError("databricks-sql-connector is not available")

        self._connection = databricks_sql.connect(
            server_hostname=data["server_hostname"],
            http_path=data["http_path"],
            access_token=data["access_token"],
            catalog=self.featurebyte_catalog,
            schema=self.featurebyte_schema,
        )

    async def initialize(self) -> None:
        await DatabricksSchemaInitializer(self).initialize()

    @property
    def schema_name(self) -> str:
        return self.featurebyte_schema

    @property
    def database_name(self) -> str:
        return self.featurebyte_catalog

    async def list_databases(self) -> list[str]:
        cursor = self._connection.cursor().catalogs()
        df_result = super().fetch_query_result_impl(cursor)
        out = []
        if df_result is not None:
            out.extend(df_result["TABLE_CAT"])
        return out

    async def list_schemas(self, database_name: str | None = None) -> list[str]:
        cursor = self._connection.cursor().schemas(catalog_name=database_name)
        df_result = self.fetch_query_result_impl(cursor)
        out = []
        if df_result is not None:
            out.extend(df_result["TABLE_SCHEM"])
        return out

    async def list_tables(
        self, database_name: str | None = None, schema_name: str | None = None
    ) -> list[str]:
        cursor = self._connection.cursor().tables(
            catalog_name=database_name, schema_name=schema_name
        )
        df_result = super().fetch_query_result_impl(cursor)
        out = []
        if df_result is not None:
            out.extend(df_result["TABLE_NAME"])
        return out

    async def list_table_schema(
        self,
        table_name: str | None,
        database_name: str | None = None,
        schema_name: str | None = None,
    ) -> OrderedDict[str, DBVarType]:
        cursor = self._connection.cursor().columns(
            table_name=table_name,
            catalog_name=database_name,
            schema_name=schema_name,
        )
        df_result = super().fetch_query_result_impl(cursor)
        column_name_type_map = collections.OrderedDict()
        if df_result is not None:
            for _, (column_name, databricks_type_name) in df_result[
                ["COLUMN_NAME", "TYPE_NAME"]
            ].iterrows():
                column_name_type_map[column_name] = self._convert_to_internal_variable_type(
                    databricks_type_name
                )
        return column_name_type_map

    @staticmethod
    def _convert_to_internal_variable_type(databricks_type: str) -> DBVarType:
        if databricks_type.endswith("INT"):
            # BIGINT, INT, SMALLINT, TINYINT
            return DBVarType.INT
        mapping = {
            "BINARY": DBVarType.BINARY,
            "BOOLEAN": DBVarType.BOOL,
            "DATE": DBVarType.DATE,
            "DECIMAL": DBVarType.FLOAT,
            "DOUBLE": DBVarType.FLOAT,
            "FLOAT": DBVarType.FLOAT,
            "INTERVAL": DBVarType.TIMEDELTA,
            "VOID": DBVarType.VOID,
            "TIMESTAMP": DBVarType.TIMESTAMP,
            "ARRAY": DBVarType.ARRAY,
            "MAP": DBVarType.MAP,
            "STRUCT": DBVarType.STRUCT,
            "STRING": DBVarType.VARCHAR,
        }
        return mapping[databricks_type]

    def fetch_query_result_impl(self, cursor: Any) -> pd.DataFrame | None:
        arrow_table = cursor.fetchall_arrow()
        return arrow_table.to_pandas()

    async def register_temp_table(self, table_name: str, dataframe: pd.DataFrame) -> None:
        date_cols = dataframe.select_dtypes(include=["datetime64"]).columns.tolist()
        table_expr = construct_dataframe_sql_expr(dataframe, date_cols).sql(
            pretty=True, dialect="spark"
        )
        query = f"CREATE OR REPLACE TEMPORARY VIEW {table_name} AS {table_expr}"
        await self.execute_query(query)


class DatabricksSchemaInitializer(BaseSchemaInitializer):
    """Databricks schema initializer class"""

    @property
    def sql_directory_name(self) -> str:
        return "databricks"

    async def create_schema(self) -> None:
        create_schema_query = f"CREATE SCHEMA {self.session.schema_name}"
        await self.session.execute_query(create_schema_query)

    async def list_functions(self) -> list[str]:
        def _function_name_to_identifier(function_name: str) -> str:
            # function names returned from SHOW FUNCTIONS are three part fully qualified, but
            # identifiers are based on function names only
            return function_name.rsplit(".", 1)[1]

        df_result = await self.session.execute_query(
            f"SHOW USER FUNCTIONS IN {self.session.schema_name}"
        )
        out = []
        if df_result is not None:
            out.extend(df_result["function"].apply(_function_name_to_identifier))
        return out

    async def list_procedures(self) -> list[str]:
        return []