# Generated by SDK version: 0.1.0
from bson import ObjectId
from featurebyte import SlowlyChangingData

scd_data = SlowlyChangingData.get_by_id(ObjectId("{data_id}"))
output = scd_data