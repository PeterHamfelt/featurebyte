"""
BaseDataController for API routes
"""
from __future__ import annotations

from typing import Any, Type, TypeVar, cast

from abc import abstractmethod

from bson.objectid import ObjectId

from featurebyte.models.dimension_table import DimensionTableModel
from featurebyte.models.event_table import EventTableModel
from featurebyte.models.item_table import ItemTableModel
from featurebyte.models.scd_table import SCDTableModel
from featurebyte.query_graph.model.column_info import ColumnInfo
from featurebyte.routes.common.base import BaseDocumentController, PaginatedDocument
from featurebyte.schema.table import TableServiceUpdate, TableUpdate
from featurebyte.service.dimension_table import DimensionTableService
from featurebyte.service.event_table import EventTableService
from featurebyte.service.info import InfoService
from featurebyte.service.item_table import ItemTableService
from featurebyte.service.scd_table import SCDTableService
from featurebyte.service.semantic import SemanticService
from featurebyte.service.table_update import TableDocumentService, TableUpdateService

TableDocumentT = TypeVar(
    "TableDocumentT", EventTableModel, ItemTableModel, DimensionTableModel, SCDTableModel
)
TableDocumentServiceT = TypeVar(
    "TableDocumentServiceT",
    EventTableService,
    ItemTableService,
    DimensionTableService,
    SCDTableService,
)


class BaseTableDocumentController(
    BaseDocumentController[TableDocumentT, TableDocumentServiceT, PaginatedDocument]
):
    """
    BaseTableDocumentController for API routes
    """

    document_update_schema_class: Type[TableServiceUpdate]

    def __init__(
        self,
        service: TableDocumentService,
        table_update_service: TableUpdateService,
        semantic_service: SemanticService,
        info_service: InfoService,
    ):
        super().__init__(service)  # type: ignore[arg-type]
        self.table_update_service = table_update_service
        self.semantic_service = semantic_service
        self.info_service = info_service

    @abstractmethod
    async def _get_column_semantic_map(self, document: TableDocumentT) -> dict[str, Any]:
        """
        Construct column name to semantic mapping

        Parameters
        ----------
        document: TableDocumentT
            Newly created document

        Returns
        -------
        dict[str, Any]
        """

    async def _add_semantic_tags(self, document: TableDocumentT) -> TableDocumentT:
        """
        Add semantic tags to newly created document

        Parameters
        ----------
        document: TableDocumentT
            Newly created document

        Returns
        -------
        TableDocumentT
        """
        column_semantic_map = await self._get_column_semantic_map(document=document)
        columns_info = []
        for col_info in document.columns_info:
            semantic = column_semantic_map.get(col_info.name)
            if semantic:
                columns_info.append(ColumnInfo(**{**col_info.dict(), "semantic_id": semantic.id}))
            else:
                columns_info.append(col_info)

        output = await self.service.update_document(
            document_id=document.id,
            data=self.document_update_schema_class(columns_info=columns_info),  # type: ignore
            return_document=True,
        )
        return cast(TableDocumentT, output)

    async def create_table(self, data: TableDocumentT) -> TableDocumentT:
        """
        Create Table record at persistent

        Parameters
        ----------
        data: TableDocumentT
            EventTable/ItemTable/SCDTable/DimensionTable creation payload

        Returns
        -------
        TableDocumentT
            Newly created data object
        """
        document = await self.service.create_document(data)  # type: ignore[arg-type]
        return await self._add_semantic_tags(document=document)  # type: ignore

    async def update_table(self, document_id: ObjectId, data: TableUpdate) -> TableDocumentT:
        """
        Update Table (for example, to update scheduled task) at persistent (GitDB or MongoDB)

        Parameters
        ----------
        document_id: ObjectId
            Table document ID
        data: TableUpdate
            Table update payload

        Returns
        -------
        TableDocumentT
            Data object with updated attribute(s)
        """
        if data.columns_info:
            await self.table_update_service.update_columns_info(
                service=self.service,
                document_id=document_id,
                data=self.document_update_schema_class(**data.dict()),  # type: ignore
            )

        if data.status:
            await self.table_update_service.update_data_status(
                service=self.service,
                document_id=document_id,
                data=self.document_update_schema_class(**data.dict()),  # type: ignore
            )

        # update other parameters
        update_dict = data.dict(exclude={"status": True, "columns_info": True}, exclude_none=True)
        if update_dict:
            await self.service.update_document(
                document_id=document_id,
                data=self.document_update_schema_class(**update_dict),  # type: ignore[arg-type]
                return_document=False,
            )

        return await self.get(document_id=document_id)