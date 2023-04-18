"""
HistoricalFeatureTable API routes
"""
from __future__ import annotations

from typing import Optional

from http import HTTPStatus

from fastapi import APIRouter, Request

from featurebyte.models.base import PydanticObjectId
from featurebyte.models.historical_feature_table import HistoricalFeatureTableModel
from featurebyte.models.persistent import AuditDocumentList
from featurebyte.routes.common.schema import (
    AuditLogSortByQuery,
    NameQuery,
    PageQuery,
    PageSizeQuery,
    SearchQuery,
    SortByQuery,
    SortDirQuery,
)
from featurebyte.schema.historical_feature_table import (
    HistoricalFeatureTableCreate,
    HistoricalFeatureTableList,
)
from featurebyte.schema.task import Task

router = APIRouter(prefix="/historical_feature_table")


@router.post("", response_model=Task, status_code=HTTPStatus.CREATED)
async def create_historical_feature_table(
    request: Request,
    data: HistoricalFeatureTableCreate,
) -> Task:
    """
    Create HistoricalFeatureTable by submitting a materialization task
    """
    controller = request.state.app_container.historical_feature_table_controller
    task_submit: Task = await controller.create_historical_feature_table(
        data=data,
    )
    return task_submit


@router.get("/{historical_feature_table_id}", response_model=HistoricalFeatureTableModel)
async def get_historical_feature_table(
    request: Request, historical_feature_table_id: PydanticObjectId
) -> HistoricalFeatureTableModel:
    """
    Get HistoricalFeatureTable
    """
    controller = request.state.app_container.historical_feature_table_controller
    historical_feature_table: HistoricalFeatureTableModel = await controller.get(
        document_id=historical_feature_table_id
    )
    return historical_feature_table


@router.get("", response_model=HistoricalFeatureTableList)
async def list_historical_feature_tables(
    request: Request,
    page: int = PageQuery,
    page_size: int = PageSizeQuery,
    sort_by: Optional[str] = SortByQuery,
    sort_dir: Optional[str] = SortDirQuery,
    search: Optional[str] = SearchQuery,
    name: Optional[str] = NameQuery,
) -> HistoricalFeatureTableList:
    """
    List HistoricalFeatureTables
    """
    controller = request.state.app_container.historical_feature_table_controller
    historical_feature_table_list: HistoricalFeatureTableList = await controller.list(
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
        search=search,
        name=name,
    )
    return historical_feature_table_list


@router.get("/audit/{historical_feature_table_id}", response_model=AuditDocumentList)
async def list_historical_feature_table_audit_logs(
    request: Request,
    historical_feature_table_id: PydanticObjectId,
    page: int = PageQuery,
    page_size: int = PageSizeQuery,
    sort_by: Optional[str] = AuditLogSortByQuery,
    sort_dir: Optional[str] = SortDirQuery,
    search: Optional[str] = SearchQuery,
) -> AuditDocumentList:
    """
    List HistoricalFeatureTable audit logs
    """
    controller = request.state.app_container.historical_feature_table_controller
    audit_doc_list: AuditDocumentList = await controller.list_audit(
        document_id=historical_feature_table_id,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
        search=search,
    )
    return audit_doc_list