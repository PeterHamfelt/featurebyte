"""
BatchFeatureTable class
"""
from __future__ import annotations

from featurebyte.api.api_object import ApiObject, ForeignKeyMapping
from featurebyte.api.batch_request_table import BatchRequestTable
from featurebyte.api.feature_store import FeatureStore
from featurebyte.models.batch_feature_table import BatchFeatureTableModel


class BatchFeatureTable(BatchFeatureTableModel, ApiObject):
    """
    BatchFeatureTable class
    """

    _route = "/batch_feature_table"
    _list_schema = BatchFeatureTableModel
    _get_schema = BatchFeatureTableModel
    _list_fields = [
        "name",
        "feature_store_name",
        "batch_request_table_name",
        "created_at",
    ]
    _list_foreign_keys = [
        ForeignKeyMapping("feature_store_id", FeatureStore, "feature_store_name"),
        ForeignKeyMapping("batch_request_table_id", BatchRequestTable, "batch_request_table_name"),
    ]
