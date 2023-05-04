# Generated by SDK version: {sdk_version}
from bson import ObjectId
from featurebyte import EventTable
from featurebyte import FeatureJobSetting
from featurebyte import ItemTable

item_table = ItemTable.get_by_id(ObjectId("{item_table_id}"))
item_view = item_table.get_view(
    event_suffix="_event_view",
    view_mode="manual",
    drop_column_names=[],
    column_cleaning_operations=[],
    event_drop_column_names=["created_at"],
    event_column_cleaning_operations=[],
    event_join_column_names=["event_timestamp", "cust_id"],
)
event_table = EventTable.get_by_id(ObjectId("{table_id}"))
event_view = event_table.get_view(
    view_mode="manual",
    drop_column_names=["created_at"],
    column_cleaning_operations=[],
)
joined_view = item_view.join_event_table_attributes(
    columns=["col_float"], event_suffix=None
)
col = joined_view.groupby(by_keys=["event_id_col"], category=None).aggregate(
    value_column="col_float",
    method="sum",
    feature_name="non_time_sum_feature",
    skip_fill_na=True,
)
joined_view_1 = event_view.add_feature(
    new_column_name="non_time_sum_feature", feature=col, entity_column="cust_id"
)
grouped = joined_view_1.groupby(
    by_keys=["cust_id"], category="col_int"
).aggregate_over(
    value_column=None,
    method="count",
    windows=["24h"],
    feature_names=["count_a_24h_per_col_int"],
    feature_job_setting=FeatureJobSetting(
        blind_spot="90s", frequency="360s", time_modulo_frequency="180s"
    ),
    skip_fill_na=True,
)
feat = grouped["count_a_24h_per_col_int"]
feat_1 = (feat.cd.entropy()) * (feat.cd.most_frequent()).str.len()
grouped_1 = joined_view_1.groupby(
    by_keys=["cust_id"], category=None
).aggregate_over(
    value_column="non_time_sum_feature",
    method="sum",
    windows=["24h"],
    feature_names=["sum_a_24h"],
    feature_job_setting=FeatureJobSetting(
        blind_spot="90s", frequency="360s", time_modulo_frequency="180s"
    ),
    skip_fill_na=True,
)
feat_2 = grouped_1["sum_a_24h"]
feat_3 = feat.cd.unique_count(include_missing=False)
feat_4 = feat.cd.unique_count(include_missing=True)
output = (feat_2 + feat_1) - (feat_3 / feat_4)