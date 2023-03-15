# Generated by SDK version: 0.1.0
from bson import ObjectId
from featurebyte import ColumnCleaningOperation
from featurebyte import ItemData
from featurebyte import MissingValueImputation

item_data = ItemData.get_by_id(ObjectId("{data_id}"))
item_view = item_data.get_view(
    event_suffix="_event_table",
    view_mode="manual",
    drop_column_names=[],
    column_cleaning_operations=[
        ColumnCleaningOperation(
            column_name="event_id_col",
            cleaning_operations=[MissingValueImputation(imputed_value=-999)],
        )
    ],
    event_drop_column_names=["created_at"],
    event_column_cleaning_operations=[
        ColumnCleaningOperation(
            column_name="col_int", cleaning_operations=[MissingValueImputation(imputed_value=-99)]
        )
    ],
    event_join_column_names=["event_timestamp", "cust_id"],
)
feat = item_view.groupby(by_keys=["event_id_col"], category=None).aggregate(
    value_column=None, method="count", feature_name="order_size", skip_fill_na=True
)
feat[feat.isnull()] = 0
feat.name = "order_size"
feat_1 = feat + 123
feat_1.name = "feat"
output = feat_1
