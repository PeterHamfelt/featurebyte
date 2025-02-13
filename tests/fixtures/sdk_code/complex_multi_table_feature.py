# Generated by SDK version: {sdk_version}
from bson import ObjectId
from featurebyte import ColumnCleaningOperation
from featurebyte import EventTable
from featurebyte import FeatureJobSetting
from featurebyte import ItemTable
from featurebyte import MissingValueImputation

item_table = ItemTable.get_by_id(ObjectId("{item_table_id}"))
item_view = item_table.get_view(
    event_suffix="_event_table",
    view_mode="manual",
    drop_column_names=[],
    column_cleaning_operations=[
        ColumnCleaningOperation(
            column_name="event_id_col",
            cleaning_operations=[MissingValueImputation(imputed_value=0.0)],
        ),
        ColumnCleaningOperation(
            column_name="item_amount",
            cleaning_operations=[MissingValueImputation(imputed_value=0.0)],
        ),
    ],
    event_drop_column_names=["created_at"],
    event_column_cleaning_operations=[
        ColumnCleaningOperation(
            column_name="col_int",
            cleaning_operations=[MissingValueImputation(imputed_value=0.0)],
        ),
        ColumnCleaningOperation(
            column_name="col_float",
            cleaning_operations=[MissingValueImputation(imputed_value=0.0)],
        ),
        ColumnCleaningOperation(
            column_name="cust_id",
            cleaning_operations=[MissingValueImputation(imputed_value=0.0)],
        ),
    ],
    event_join_column_names=["event_timestamp", "cust_id"],
)
event_table = EventTable.get_by_id(ObjectId("{table_id}"))
event_view = event_table.get_view(
    view_mode="manual",
    drop_column_names=["created_at"],
    column_cleaning_operations=[
        ColumnCleaningOperation(
            column_name="col_int",
            cleaning_operations=[MissingValueImputation(imputed_value=0.0)],
        ),
        ColumnCleaningOperation(
            column_name="col_float",
            cleaning_operations=[MissingValueImputation(imputed_value=0.0)],
        ),
        ColumnCleaningOperation(
            column_name="cust_id",
            cleaning_operations=[MissingValueImputation(imputed_value=0.0)],
        ),
    ],
)
joined_view = item_view.join_event_table_attributes(
    columns=["col_float", "col_char", "col_boolean"],
    event_suffix="_event_table",
)
col = joined_view["item_amount"]
col_1 = joined_view["col_float_event_table"]
view = joined_view.copy()
view["percent"] = col / col_1
col_2 = view.groupby(by_keys=["event_id_col"], category=None).aggregate(
    value_column="percent",
    method="max",
    feature_name="max_percent",
    skip_fill_na=True,
)
joined_view_1 = event_view.add_feature(
    new_column_name="max_percent", feature=col_2, entity_column="cust_id"
)
grouped = joined_view_1.groupby(
    by_keys=["cust_id"], category=None
).aggregate_over(
    value_column="max_percent",
    method="max",
    windows=["30d"],
    feature_names=["max_percent_over_30d"],
    feature_job_setting=FeatureJobSetting(
        blind_spot="90s", frequency="360s", time_modulo_frequency="180s"
    ),
    skip_fill_na=True,
)
feat = grouped["max_percent_over_30d"]
output = feat
