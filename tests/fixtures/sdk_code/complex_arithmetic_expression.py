# Generated by SDK version: 0.1.0
from bson import ObjectId
from featurebyte import EventData
from featurebyte import EventView

event_data = EventData.get_by_id(ObjectId("{data_id}"))
event_view = EventView.from_event_data(
    event_data=event_data,
    view_mode="manual",
    drop_column_names=["created_at"],
    column_cleaning_operations=[],
)
col = event_view["col_float"]
col_1 = event_view["col_int"]
col_2 = ((1 - col_1) * (col - 1)) / (col_1 + col)
col_3 = (col_2 + (1 / (col_1 - col))) + (col_1 % 10)
output = (col_3 - (col.pow(2))) + col_1
