# Generated by SDK version: {sdk_version}
from bson import ObjectId
from featurebyte import EventTable
from featurebyte import FeatureStore
from featurebyte import SnowflakeDetails
from featurebyte.query_graph.model.column_info import ColumnInfo
from featurebyte.query_graph.model.common_table import TabularSource
from featurebyte.query_graph.node.schema import TableDetails

event_table = EventTable(
    name="event_table",
    feature_store=FeatureStore(
        name="sf_featurestore",
        type="snowflake",
        details=SnowflakeDetails(
            account="sf_account",
            warehouse="sf_warehouse",
            database="sf_database",
            sf_schema="sf_schema",
        ),
    ),
    tabular_source=TabularSource(
        feature_store_id=ObjectId("{feature_store_id}"),
        table_details=TableDetails(
            database_name="sf_database",
            schema_name="sf_schema",
            table_name="sf_table",
        ),
    ),
    columns_info=[
        ColumnInfo(name="col_int", dtype="INT"),
        ColumnInfo(name="col_float", dtype="FLOAT"),
        ColumnInfo(name="col_char", dtype="CHAR"),
        ColumnInfo(name="col_text", dtype="VARCHAR"),
        ColumnInfo(name="col_binary", dtype="BINARY"),
        ColumnInfo(name="col_boolean", dtype="BOOL"),
        ColumnInfo(name="event_timestamp", dtype="TIMESTAMP_TZ"),
        ColumnInfo(name="created_at", dtype="TIMESTAMP_TZ"),
        ColumnInfo(name="cust_id", dtype="INT"),
    ],
    record_creation_timestamp_column=None,
    event_id_column="col_int",
    event_timestamp_column="event_timestamp",
    _id=ObjectId("{table_id}"),
)
output = event_table
