"""
ContextService class
"""
from __future__ import annotations

from typing import Optional

from bson import ObjectId

from featurebyte.exception import DocumentUpdateError
from featurebyte.models.context import ContextModel
from featurebyte.query_graph.enum import NodeOutputType
from featurebyte.query_graph.node.metadata.operation import NodeOutputCategory, OperationStructure
from featurebyte.schema.context import ContextCreate, ContextUpdate
from featurebyte.service.base_document import BaseDocumentService
from featurebyte.service.entity import EntityService
from featurebyte.service.tabular_data import DataService


class ContextService(BaseDocumentService[ContextModel, ContextCreate, ContextUpdate]):
    """
    ContextService class
    """

    document_class = ContextModel

    @property
    def entity_service(self) -> EntityService:
        """
        Entity service instance

        Returns
        -------
        EntityService
        """
        return EntityService(user=self.user, persistent=self.persistent)

    async def create_document(self, data: ContextCreate) -> ContextModel:
        entities = await self.entity_service.list_documents(
            page=1, page_size=0, query_filter={"_id": {"$in": data.entity_ids}}
        )
        found_entity_ids = set(doc["_id"] for doc in entities["data"])
        not_found_entity_ids = set(data.entity_ids).difference(found_entity_ids)
        if not_found_entity_ids:
            # trigger entity not found error
            await self.entity_service.get_document(document_id=list(not_found_entity_ids)[0])
        return await super().create_document(data=data)

    async def _validate_view(
        self, operation_structure: OperationStructure, context: ContextModel
    ) -> None:
        """
        Validate context view operation structure, check that
        - whether all tabular data used in the view can be retrieved from persistent
        - whether the view output contains required entity column(s)

        Parameters
        ----------
        operation_structure: OperationStructure
            Context view's operation structure to be validated
        context: ContextModel
            Context stored at the persistent

        Raises
        ------
        DocumentUpdateError
            When the context view is not a proper context view (frame, view and has all required entities)
        """
        data_service = DataService(user=self.user, persistent=self.persistent)

        # check that it is a proper view
        if operation_structure.output_type != NodeOutputType.FRAME:
            raise DocumentUpdateError("Context view must but a table but not a single column.")
        if operation_structure.output_category != NodeOutputCategory.VIEW:
            raise DocumentUpdateError("Context view must be a view but not a feature.")

        # check that tabular data document can be retrieved from the persistent
        tabular_data_map = {}
        tabular_data_ids = list(
            set(col.tabular_data_id for col in operation_structure.source_columns)
        )
        for tabular_data_id in tabular_data_ids:
            if tabular_data_id is None:
                raise DocumentUpdateError("Data record has not been stored at the persistent.")
            tabular_data_map[tabular_data_id] = await data_service.get_document(
                document_id=tabular_data_id
            )

        # check that entities can be found on the view
        # TODO: add entity id to operation structure column (DEV-957)
        found_entity_ids = set()
        for source_col in operation_structure.source_columns:
            assert source_col.tabular_data_id is not None
            tabular_data = tabular_data_map[source_col.tabular_data_id]
            column_info = next(
                (
                    col_info
                    for col_info in tabular_data.columns_info
                    if col_info.name == source_col.name
                ),
                None,
            )
            if column_info is None:
                raise DocumentUpdateError(
                    f'Column "{source_col.name}" not found in table "{tabular_data.name}".'
                )
            if column_info.entity_id:
                found_entity_ids.add(column_info.entity_id)

        missing_entity_ids = list(set(context.entity_ids).difference(found_entity_ids))
        if missing_entity_ids:
            missing_entities = await self.entity_service.list_documents(
                query_filter={"_id": {"$in": missing_entity_ids}}
            )
            missing_entity_names = [entity["name"] for entity in missing_entities["data"]]
            raise DocumentUpdateError(
                f"Entities {missing_entity_names} not found in the context view."
            )

    async def update_document(
        self,
        document_id: ObjectId,
        data: ContextUpdate,
        exclude_none: bool = True,
        document: Optional[ContextModel] = None,
        return_document: bool = True,
    ) -> Optional[ContextModel]:
        document = await self.get_document(document_id=document_id)
        if data.graph and data.node_name:
            node = data.graph.get_node_by_name(data.node_name)
            operation_structure = data.graph.extract_operation_structure(node=node)
            await self._validate_view(operation_structure=operation_structure, context=document)

        document = await super().update_document(
            document_id=document_id,
            document=document,
            data=data,
            exclude_none=exclude_none,
            return_document=return_document,
        )
        return document