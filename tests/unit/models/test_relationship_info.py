"""
Test relationship info
"""
import pytest
from bson import ObjectId

from featurebyte.models.base import PydanticObjectId
from featurebyte.models.relationship import RelationshipInfo, RelationshipType


def test_duplicate_primary_and_related_ids_throws_error():
    """
    Test duplicate primary and related ids throws error
    """
    id_1 = PydanticObjectId(ObjectId())
    with pytest.raises(ValueError) as exc:
        RelationshipInfo(
            relationship_type=RelationshipType.CHILD_PARENT,
            primary_entity_id=id_1,
            related_entity_id=id_1,
            primary_data_source_id=PydanticObjectId(ObjectId()),
            is_enabled=False,
            updated_by=PydanticObjectId(ObjectId()),
        )
    assert "Primary and Related entity id cannot be the same" in str(exc.value)