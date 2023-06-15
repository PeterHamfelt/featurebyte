"""
Test target module
"""
from typing import List

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from featurebyte.api.entity import Entity
from featurebyte.api.target import Target


@pytest.fixture(name="test_entity")
def get_test_entity_fixture():
    """
    Create an entity for testing
    """
    return Entity(name="test_entity", serving_names=["test_serving_name"])


@pytest.fixture(name="get_test_target")
def get_test_target_fixture():
    """
    Create a target for testing
    """

    def get_target(entity_names: List[str]):
        return Target.create(
            name="test_target",
            entities=entity_names,
            horizon="3d",
            blind_spot="1d",
        )

    return get_target


def test_create_target_from_constructor(test_entity, get_test_target):
    test_entity.save()
    target = get_test_target(["test_entity"])

    # List target
    target_list = Target.list()
    assert target_list.shape[0] == 1
    expected_target_list = pd.DataFrame(
        {
            "id": [target.id],
            "name": [target.name],
            "entities": [["test_entity"]],
        }
    )
    assert_frame_equal(target_list, expected_target_list)

    # Get target
    retrieved_target = Target.get(target.name)
    assert retrieved_target.name == target.name
    actual_entity_names = [entity.name for entity in retrieved_target.entities]
    assert actual_entity_names == ["test_entity"]
    assert retrieved_target.horizon == target.horizon
    assert retrieved_target.blind_spot == target.blind_spot


def test_target_info(test_entity, get_test_target):
    test_entity.save()
    target = get_test_target([test_entity.name])

    retrieved_target = Target.get(target.name)
    target_info = retrieved_target.info()
    assert target_info["id"] == str(target.id)