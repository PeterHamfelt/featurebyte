"""
TargetNamespace API routes
"""
from __future__ import annotations

from typing import Optional, cast

from fastapi import APIRouter, Request

from featurebyte.models.base import PydanticObjectId
from featurebyte.models.persistent import AuditDocumentList
from featurebyte.models.target_namespace import TargetNamespaceModel
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
from featurebyte.schema.target_namespace import (
    TargetNamespaceInfo,
    TargetNamespaceList,
    TargetNamespaceUpdate,
)

router = APIRouter(prefix="/target_namespace")


@router.get("/{target_namespace_id}", response_model=TargetNamespaceModel)
async def get_target_namespace(
    request: Request, target_namespace_id: PydanticObjectId
) -> TargetNamespaceModel:
    """
    Retrieve Target Namespace
    """
    controller = request.state.app_container.target_namespace_controller
    target_namespace: TargetNamespaceModel = await controller.get(
        document_id=target_namespace_id,
        exception_detail=(
            f'TargetNamespace (id: "{target_namespace_id}") not found. Please save the TargetNamespace object first.'
        ),
    )
    return target_namespace


@router.patch("/{target_namespace_id}", response_model=TargetNamespaceModel)
async def update_target_namespace(
    request: Request, target_namespace_id: PydanticObjectId, data: TargetNamespaceUpdate
) -> TargetNamespaceModel:
    """
    Update TargetNamespace
    """
    controller = request.state.app_container.target_namespace_controller
    target_namespace: TargetNamespaceModel = (
        await controller.target_namespace_service.update_document(target_namespace_id, data)
    )
    return target_namespace


@router.get("", response_model=TargetNamespaceList)
async def list_target_namespaces(
    request: Request,
    page: int = PageQuery,
    page_size: int = PageSizeQuery,
    sort_by: Optional[str] = SortByQuery,
    sort_dir: Optional[str] = SortDirQuery,
    search: Optional[str] = SearchQuery,
    name: Optional[str] = NameQuery,
) -> TargetNamespaceList:
    """
    List TargetNamespace
    """
    controller = request.state.app_container.target_namespace_controller
    target_namespace_list: TargetNamespaceList = await controller.list(
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
        search=search,
        name=name,
    )
    return target_namespace_list


@router.get("/audit/{target_namespace_id}", response_model=AuditDocumentList)
async def list_target_namespace_audit_logs(
    request: Request,
    target_namespace_id: PydanticObjectId,
    page: int = PageQuery,
    page_size: int = PageSizeQuery,
    sort_by: Optional[str] = AuditLogSortByQuery,
    sort_dir: Optional[str] = SortDirQuery,
    search: Optional[str] = SearchQuery,
) -> AuditDocumentList:
    """
    List Target Namespace audit logs
    """
    controller = request.state.app_container.target_namespace_controller
    audit_doc_list: AuditDocumentList = await controller.list_audit(
        document_id=target_namespace_id,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
        search=search,
    )
    return audit_doc_list


@router.get("/{target_namespace_id}/info", response_model=TargetNamespaceInfo)
async def get_target_namespace_info(
    request: Request,
    target_namespace_id: PydanticObjectId,
    verbose: bool = VerboseQuery,
) -> TargetNamespaceInfo:
    """
    Retrieve TargetNamespace info
    """
    controller = request.state.app_container.target_namespace_controller
    info = await controller.get_info(
        document_id=target_namespace_id,
        verbose=verbose,
    )
    return cast(TargetNamespaceInfo, info)