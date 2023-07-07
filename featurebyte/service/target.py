"""
Target class
"""
from __future__ import annotations

from typing import Any, Optional

from bson import ObjectId

from featurebyte.common.model_util import parse_duration_string
from featurebyte.exception import DocumentCreationError, DocumentNotFoundError
from featurebyte.models.feature_namespace import DefaultVersionMode
from featurebyte.models.target import TargetModel
from featurebyte.models.target_namespace import TargetNamespaceModel
from featurebyte.persistent import Persistent
from featurebyte.schema.target import TargetCreate
from featurebyte.schema.target_namespace import TargetNamespaceCreate, TargetNamespaceServiceUpdate
from featurebyte.service.base_namespace_service import BaseNamespaceService
from featurebyte.service.namespace_handler import (
    NamespaceHandler,
    validate_version_and_namespace_consistency,
)
from featurebyte.service.target_namespace import TargetNamespaceService


class TargetService(BaseNamespaceService[TargetModel, TargetCreate]):
    """
    TargetService class
    """

    document_class = TargetModel

    def __init__(
        self,
        user: Any,
        persistent: Persistent,
        catalog_id: ObjectId,
        target_namespace_service: TargetNamespaceService,
        namespace_handler: NamespaceHandler,
    ):
        super().__init__(user=user, persistent=persistent, catalog_id=catalog_id)
        self.target_namespace_service = target_namespace_service
        self.namespace_handler = namespace_handler

    async def prepare_target_model(
        self, data: TargetCreate, sanitize_for_definition: bool
    ) -> TargetModel:
        """
        Prepare the target model by pruning the query graph

        Parameters
        ----------
        data: TargetCreate
            Target creation data
        sanitize_for_definition: bool
            Whether to sanitize the query graph for generating feature definition

        Returns
        -------
        FeatureModel
        """
        document = TargetModel(
            **{
                **data.dict(by_alias=True),
                "version": await self.get_document_version(data.name),
                "user_id": self.user.id,
                "catalog_id": self.catalog_id,
            }
        )

        # prepare the graph to store
        graph, node_name = await self.namespace_handler.prepare_graph_to_store(
            graph=document.graph,
            node=document.node,
            sanitize_for_definition=sanitize_for_definition,
        )

        # create a new target document (so that the derived attributes like table_ids is generated properly)
        return TargetModel(
            **{**document.dict(by_alias=True), "graph": graph, "node_name": node_name}
        )

    @staticmethod
    def derive_horizon(document: TargetModel, namespace: TargetNamespaceModel) -> Optional[str]:
        """
        Derive the horizon from the target and namespace

        Parameters
        ----------
        document: TargetModel
            Target document
        namespace: TargetNamespaceModel
            Target namespace document

        Returns
        -------
        Optional[str]

        Raises
        ------
        DocumentCreationError
            If the target horizon is greater than the namespace horizon
        """
        document_horizon = document.derive_horizon()
        if namespace.horizon is None:
            return document_horizon

        namespace_duration = parse_duration_string(namespace.horizon)
        if document_horizon:
            document_duration = parse_duration_string(document_horizon)
            if document_duration > namespace_duration:
                raise DocumentCreationError(
                    f"Target horizon {document_horizon} is greater than namespace horizon {namespace.horizon}"
                )
        return namespace.horizon

    async def create_document(self, data: TargetCreate) -> TargetModel:
        document = await self.prepare_target_model(data=data, sanitize_for_definition=False)
        async with self.persistent.start_transaction() as session:
            # check any conflict with existing documents
            await self._check_document_unique_constraints(document=document)

            # prepare target definition
            definition = await self.namespace_handler.prepare_definition(document=document)

            # insert the document
            insert_id = await session.insert_one(
                collection_name=self.collection_name,
                document={
                    **document.dict(by_alias=True),
                    "definition": definition,
                    "raw_graph": data.graph.dict(),
                },
                user_id=self.user.id,
            )
            assert insert_id == document.id

            try:
                target_namespace = await self.target_namespace_service.get_document(
                    document_id=document.target_namespace_id,
                )
                await validate_version_and_namespace_consistency(
                    base_model=document,
                    base_namespace_model=target_namespace,
                    attributes=["name"],
                )
                await self.target_namespace_service.update_document(
                    document_id=document.target_namespace_id,
                    data=TargetNamespaceServiceUpdate(
                        target_ids=self.include_object_id(target_namespace.target_ids, document.id),
                        horizon=self.derive_horizon(document=document, namespace=target_namespace),
                    ),
                    return_document=True,
                )
            except DocumentNotFoundError:
                entity_ids = document.entity_ids or []
                await self.target_namespace_service.create_document(
                    data=TargetNamespaceCreate(
                        _id=document.target_namespace_id,
                        name=document.name,
                        dtype=document.dtype,
                        target_ids=[insert_id],
                        default_target_id=insert_id,
                        default_version_mode=DefaultVersionMode.AUTO,
                        entity_ids=sorted(entity_ids),
                        horizon=document.derive_horizon(),
                    ),
                )
        return await self.get_document(document_id=insert_id)
