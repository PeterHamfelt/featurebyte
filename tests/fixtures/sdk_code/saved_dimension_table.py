# Generated by SDK version: 0.1.0
from bson import ObjectId
from featurebyte import DimensionTable

dimension_table = DimensionTable.get_by_id(ObjectId("{data_id}"))
output = dimension_table