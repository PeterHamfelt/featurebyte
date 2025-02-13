"""
Test relationship_info controller
"""
import json
import os

import pytest
import pytest_asyncio
from bson import ObjectId

from featurebyte import Entity
from featurebyte.exception import DocumentNotFoundError
from featurebyte.models.base import PydanticObjectId
from featurebyte.models.relationship import RelationshipType
from featurebyte.schema.event_table import EventTableCreate
from featurebyte.schema.relationship_info import RelationshipInfoCreate


@pytest.fixture(name="relationship_info_controller")
def relationship_info_controller_fixture(app_container):
    """
    relationship_info_controller fixture
    """
    return app_container.relationship_info_controller


@pytest.fixture(name="relationship_info_create")
def relationship_info_create_fixture():
    """
    relationship_info_create fixture
    """
    entity_id = PydanticObjectId(ObjectId())
    related_entity_id = PydanticObjectId(ObjectId())
    relation_table_id = PydanticObjectId(ObjectId())
    return RelationshipInfoCreate(
        name="random",
        relationship_type=RelationshipType.CHILD_PARENT,
        entity_id=entity_id,
        related_entity_id=related_entity_id,
        relation_table_id=relation_table_id,
        enabled=False,
        updated_by=PydanticObjectId(ObjectId()),
    )


@pytest.mark.asyncio
async def test_validate_relationship_info_create__entity_id_error_thrown(
    relationship_info_controller, relationship_info_create
):
    """
    Test validate_relationship_info_create
    """
    with pytest.raises(ValueError) as exc:
        await relationship_info_controller._validate_relationship_info_create(
            relationship_info_create
        )
    assert "entity IDs not found" in str(exc)


@pytest.fixture(name="entities")
def entities_fixture(relationship_info_create):
    """
    Create entities
    """
    entity_1 = Entity(
        name="entity_1", serving_names=["entity_1"], _id=relationship_info_create.entity_id
    )
    entity_1.save()
    entity_2 = Entity(
        name="entity_2", serving_names=["entity_2"], _id=relationship_info_create.related_entity_id
    )
    entity_2.save()


@pytest.mark.asyncio
async def test_validate_relationship_info_create__table_id_error_thrown(
    relationship_info_controller, relationship_info_create, entities
):
    """
    Test validate_relationship_info_create
    """
    _ = entities

    # Try to create relationship info again - expect a different error from missing table source
    with pytest.raises(DocumentNotFoundError) as exc:
        await relationship_info_controller._validate_relationship_info_create(
            relationship_info_create
        )
    assert "Please save the Table object first" in str(exc)


@pytest_asyncio.fixture(name="event_table")
async def event_table_fixture(app_container, snowflake_feature_store):
    """
    Create event_table fixture
    """
    fixture_path = os.path.join("tests/fixtures/request_payloads/event_table.json")
    with open(fixture_path, encoding="utf") as fhandle:
        payload = json.loads(fhandle.read())
        payload["tabular_source"]["table_details"]["table_name"] = "sf_event_table"
        payload["tabular_source"]["feature_store_id"] = snowflake_feature_store.id
        event_table = await app_container.event_table_service.create_document(
            data=EventTableCreate(**payload)
        )
        yield event_table


@pytest.mark.asyncio
async def test_validate_relationship_info_create__no_error_thrown(
    relationship_info_controller, relationship_info_create, entities, event_table
):
    """
    Test validate_relationship_info_create
    """
    _ = entities

    # Try to create relationship info again - expect no error
    create_dict = relationship_info_create.dict()
    create_dict["relation_table_id"] = event_table.id  # update table source ID to a valid table ID
    relationship_info_create = RelationshipInfoCreate(**create_dict)
    await relationship_info_controller._validate_relationship_info_create(relationship_info_create)
