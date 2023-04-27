"""
ObservationTable API routes
"""
from __future__ import annotations

from typing import Optional, cast

from http import HTTPStatus

from fastapi import APIRouter, Request

from featurebyte.models.base import PydanticObjectId
from featurebyte.models.observation_table import ObservationTableModel
from featurebyte.models.persistent import AuditDocumentList
from featurebyte.routes.common.schema import (
    AuditLogSortByQuery,
    NameQuery,
    PageQuery,
    PageSizeQuery,
    SearchQuery,
    SortByQuery,
    SortDirQuery,
    VerboseQuery,
)
from featurebyte.schema.observation_table import (
    ObservationTableCreate,
    ObservationTableInfo,
    ObservationTableList,
)
from featurebyte.schema.task import Task

router = APIRouter(prefix="/observation_table")


@router.post("", response_model=Task, status_code=HTTPStatus.CREATED)
async def create_observation_table(
    request: Request,
    data: ObservationTableCreate,
) -> Task:
    """
    Create ObservationTable by submitting a materialization task
    """
    controller = request.state.app_container.observation_table_controller
    task_submit: Task = await controller.create_observation_table(
        data=data,
    )
    return task_submit


@router.get("/{observation_table_id}", response_model=ObservationTableModel)
async def get_observation_table(
    request: Request, observation_table_id: PydanticObjectId
) -> ObservationTableModel:
    """
    Get ObservationTable
    """
    controller = request.state.app_container.observation_table_controller
    observation_table: ObservationTableModel = await controller.get(
        document_id=observation_table_id
    )
    return observation_table


@router.get("", response_model=ObservationTableList)
async def list_observation_tables(
    request: Request,
    page: int = PageQuery,
    page_size: int = PageSizeQuery,
    sort_by: Optional[str] = SortByQuery,
    sort_dir: Optional[str] = SortDirQuery,
    search: Optional[str] = SearchQuery,
    name: Optional[str] = NameQuery,
) -> ObservationTableList:
    """
    List ObservationTables
    """
    controller = request.state.app_container.observation_table_controller
    observation_table_list: ObservationTableList = await controller.list(
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
        search=search,
        name=name,
    )
    return observation_table_list


@router.get("/audit/{observation_table_id}", response_model=AuditDocumentList)
async def list_observation_table_audit_logs(
    request: Request,
    observation_table_id: PydanticObjectId,
    page: int = PageQuery,
    page_size: int = PageSizeQuery,
    sort_by: Optional[str] = AuditLogSortByQuery,
    sort_dir: Optional[str] = SortDirQuery,
    search: Optional[str] = SearchQuery,
) -> AuditDocumentList:
    """
    List ObservationTable audit logs
    """
    controller = request.state.app_container.observation_table_controller
    audit_doc_list: AuditDocumentList = await controller.list_audit(
        document_id=observation_table_id,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
        search=search,
    )
    return audit_doc_list


@router.get("/{observation_table_id}/info", response_model=ObservationTableInfo)
async def get_observation_table_info(
    request: Request, observation_table_id: PydanticObjectId, verbose: bool = VerboseQuery
) -> ObservationTableInfo:
    """
    Get ObservationTable info
    """
    controller = request.state.app_container.observation_table_controller
    info = await controller.get_info(document_id=observation_table_id, verbose=verbose)
    return cast(ObservationTableInfo, info)
