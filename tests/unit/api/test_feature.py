"""
Unit test for Feature classes
"""
import textwrap
import time
from datetime import datetime
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from freezegun import freeze_time
from pandas.testing import assert_frame_equal

import featurebyte
from featurebyte import (
    DefaultVersionMode,
    MissingValueImputation,
    activate_and_get_catalog,
    get_version,
    list_unsaved_features,
)
from featurebyte.api.catalog import Catalog
from featurebyte.api.entity import Entity
from featurebyte.api.feature import Feature, FeatureNamespace
from featurebyte.api.feature_group import FeatureGroup
from featurebyte.api.feature_list import FeatureList
from featurebyte.api.table import Table
from featurebyte.enum import DBVarType
from featurebyte.exception import (
    ObjectHasBeenSavedError,
    RecordCreationException,
    RecordDeletionException,
    RecordRetrievalException,
    RecordUpdateException,
)
from featurebyte.models.feature_namespace import FeatureReadiness
from featurebyte.models.feature_store import TableStatus
from featurebyte.query_graph.graph import GlobalQueryGraph
from featurebyte.query_graph.model.feature_job_setting import (
    FeatureJobSetting,
    TableFeatureJobSetting,
)
from featurebyte.query_graph.model.graph import QueryGraphModel
from featurebyte.query_graph.node.cleaning_operation import (
    ColumnCleaningOperation,
    TableCleaningOperation,
)
from tests.unit.api.base_feature_or_target_test import FeatureOrTargetBaseTestSuite, TestItemType
from tests.util.helper import check_aggressively_pruned_graph, check_sdk_code_generation, get_node


@pytest.fixture(name="float_feature_dict")
def float_feature_dict_fixture(float_feature):
    """
    Serialize float feature in dictionary format
    """
    # before serialization, global query graph is used
    assert float_feature.saved is False
    assert isinstance(float_feature.graph, GlobalQueryGraph)
    feat_dict = float_feature.dict()

    # after serialization, pruned query graph is used
    assert set(node["name"] for node in feat_dict["graph"]["nodes"]) == {
        "input_1",
        "groupby_1",
        "project_1",
        "graph_1",
    }
    assert feat_dict["graph"]["edges"] == [
        {"source": "input_1", "target": "graph_1"},
        {"source": "graph_1", "target": "groupby_1"},
        {"source": "groupby_1", "target": "project_1"},
    ]
    yield feat_dict


def test_feature_group__getitem__list_of_str(feature_group):
    """
    Test retrieving single column
    """
    feature_group_subset = feature_group[["sum_2h", "sum_1d"]]
    assert isinstance(feature_group_subset, FeatureGroup)
    assert [feat.name for feat in feature_group_subset.feature_objects.values()] == [
        "sum_2h",
        "sum_1d",
    ]


def test_feature__binary_ops_return_feature_type(float_feature):
    """
    Test Feature return correct type after binary operation
    """
    output = float_feature + float_feature
    assert isinstance(output, Feature)


def test_feature__bool_series_key_scalar_value(float_feature, bool_feature):
    """
    Test Feature conditional assignment
    """
    float_feature[bool_feature] = 10
    assert float_feature.node.dict(exclude={"name": True}) == {
        "type": "alias",
        "parameters": {"name": "sum_1d"},
        "output_type": "series",
    }
    float_feature_dict = float_feature.dict()
    cond_node = get_node(float_feature_dict["graph"], "conditional_1")
    assert cond_node == {
        "name": "conditional_1",
        "type": "conditional",
        "parameters": {"value": 10},
        "output_type": "series",
    }
    assert float_feature_dict["graph"]["edges"] == [
        {"source": "input_1", "target": "graph_1"},
        {"source": "graph_1", "target": "groupby_1"},
        {"source": "groupby_1", "target": "project_1"},
        {"source": "project_1", "target": "gt_1"},
        {"source": "project_1", "target": "conditional_1"},
        {"source": "gt_1", "target": "conditional_1"},
        {"source": "conditional_1", "target": "alias_1"},
    ]


def test_feature__cond_assign_unnamed(float_feature, bool_feature):
    """
    Test Feature conditional assignment on unnamed Feature
    """
    temp_feature = float_feature + 123.0
    temp_feature[bool_feature] = 0.0
    temp_feature_dict = temp_feature.dict()
    cond_node = get_node(temp_feature_dict["graph"], node_name="conditional_1")
    assert cond_node == {
        "name": "conditional_1",
        "output_type": "series",
        "parameters": {"value": 0.0},
        "type": "conditional",
    }
    # No assignment occurred
    assert temp_feature_dict["graph"]["edges"] == [
        {"source": "input_1", "target": "graph_1"},
        {"source": "graph_1", "target": "groupby_1"},
        {"source": "groupby_1", "target": "project_1"},
        {"source": "project_1", "target": "add_1"},
        {"source": "project_1", "target": "gt_1"},
        {"source": "add_1", "target": "conditional_1"},
        {"source": "gt_1", "target": "conditional_1"},
    ]


def test_feature__preview_missing_point_in_time(float_feature):
    """
    Test feature preview validation missing point in time
    """
    invalid_params = pd.DataFrame([{"cust_id": "C1"}])
    with pytest.raises(RecordRetrievalException) as exc_info:
        float_feature.preview(invalid_params)
    assert "Point in time column not provided: POINT_IN_TIME" in str(exc_info.value)


def test_feature__preview_missing_entity_id(float_feature):
    """
    Test feature preview validation missing required entity
    """
    invalid_params = pd.DataFrame([{"POINT_IN_TIME": "2022-04-01"}])
    with pytest.raises(RecordRetrievalException) as exc_info:
        float_feature.preview(invalid_params)
    assert "Required entities are not provided in the request" in str(exc_info.value)


def test_feature_deserialization(
    float_feature, float_feature_dict, snowflake_feature_store, snowflake_event_view_with_entity
):
    """
    Test feature deserialization
    """
    global_graph = GlobalQueryGraph()
    float_feature_dict["_id"] = float_feature_dict.pop("id")
    float_feature_dict["feature_store"] = snowflake_feature_store
    deserialized_float_feature = Feature.parse_obj(float_feature_dict)
    assert deserialized_float_feature.saved is False
    assert deserialized_float_feature.id == float_feature.id
    assert deserialized_float_feature.name == float_feature.name
    assert deserialized_float_feature.dtype == float_feature.dtype
    assert deserialized_float_feature.tabular_source == float_feature.tabular_source
    assert deserialized_float_feature.graph == global_graph
    assert id(deserialized_float_feature.graph.nodes) == id(global_graph.nodes)

    # construct another identical float feature with an additional unused column,
    snowflake_event_view_with_entity["unused_feat"] = (
        10.0 * snowflake_event_view_with_entity["cust_id"]
    )
    grouped = snowflake_event_view_with_entity.groupby("cust_id")
    feature_group = grouped.aggregate_over(
        value_column="col_float",
        method="sum",
        windows=["30m", "2h", "1d"],
        feature_names=["sum_30m", "sum_2h", "sum_1d"],
        feature_job_setting=FeatureJobSetting(
            blind_spot="10m",
            frequency="30m",
            time_modulo_frequency="5m",
        ),
    )
    same_float_feature_dict = feature_group["sum_1d"].dict(exclude={"id": True})
    float_feature_dict.pop("_id")
    float_feature_dict.pop("feature_store")

    # as serialization only perform non-aggressive pruning (all travelled nodes are kept)
    # here we need to perform aggressive pruning & compare the final graph to make sure they are the same
    check_aggressively_pruned_graph(
        left_obj_dict=float_feature_dict, right_obj_dict=same_float_feature_dict
    )

    # check pruned graph and node_name are set properly
    pruned_graph, mapped_node = feature_group["sum_1d"].extract_pruned_graph_and_node()
    assert mapped_node.name != feature_group["sum_1d"].node_name


def test_feature_to_json(float_feature):
    """
    Test feature to_json
    """
    # do not include any keys
    output_include = float_feature.json(include={})
    assert output_include == "{}"

    # exclude graph key
    output_exclude = float_feature.json(exclude={"graph": True})
    assert "graph" not in output_exclude

    # exclude_none
    output_exclude_none = float_feature.json(exclude_none=True)
    assert "is_default" not in output_exclude_none

    # check encoder
    float_feature.__dict__["created_at"] = datetime.now()
    output_encoder = float_feature.json(encoder=lambda v: "__default__")
    assert '"created_at": "__default__"' in output_encoder


@pytest.fixture(name="saved_feature")
def saved_feature_fixture(
    snowflake_event_table,
    float_feature,
):
    """
    Saved feature fixture
    """
    event_table_id_before = snowflake_event_table.id
    snowflake_event_table.update_default_feature_job_setting(
        feature_job_setting=FeatureJobSetting(
            blind_spot="10m", frequency="30m", time_modulo_frequency="5m"
        )
    )
    assert snowflake_event_table.id == event_table_id_before
    feature_id_before = float_feature.id
    assert float_feature.readiness is FeatureReadiness.DRAFT
    assert float_feature.saved is False

    # check the groupby node before feature is saved
    graph = QueryGraphModel(**float_feature.dict()["graph"])
    groupby_node = graph.nodes_map["groupby_1"]
    assert groupby_node.parameters.names == ["sum_30m", "sum_2h", "sum_1d"]
    assert groupby_node.parameters.windows == ["30m", "2h", "1d"]

    float_feature.save()
    assert float_feature.id == feature_id_before
    assert float_feature.readiness == FeatureReadiness.DRAFT
    assert float_feature.saved is True

    # check the groupby node after feature is saved (node parameters should get pruned)
    graph = QueryGraphModel(**float_feature.dict()["graph"])
    groupby_node = graph.nodes_map["groupby_1"]
    assert groupby_node.parameters.names == ["sum_1d"]
    assert groupby_node.parameters.windows == ["1d"]
    assert (
        groupby_node.parameters.tile_id
        == "TILE_F1800_M300_B600_B5CAF33CCFEDA76C257EC2CB7F66C4AD22009B0F"
    )
    assert groupby_node.parameters.aggregation_id == "sum_aed233b0e8a6e1c1e0d5427b126b03c949609481"

    assert float_feature.name == "sum_1d"
    return float_feature


def test_list(saved_feature):
    """
    Test list features
    """
    # test list features
    saved_feature_namespace = FeatureNamespace.get(saved_feature.name)
    feature_list = Feature.list(include_id=True)
    assert_frame_equal(
        feature_list,
        pd.DataFrame(
            {
                "id": [saved_feature.id],
                "name": [saved_feature_namespace.name],
                "dtype": [saved_feature.dtype],
                "readiness": [saved_feature_namespace.readiness],
                "online_enabled": [saved_feature.online_enabled],
                "tables": [["sf_event_table"]],
                "primary_tables": [["sf_event_table"]],
                "entities": [["customer"]],
                "primary_entities": [["customer"]],
                "created_at": [saved_feature_namespace.created_at],
            }
        ),
    )


def test_info(saved_feature):
    """
    Test info
    """
    info_dict = saved_feature.info()
    data_feature_job_setting = {
        "table_name": "sf_event_table",
        "feature_job_setting": {
            "blind_spot": "600s",
            "frequency": "1800s",
            "time_modulo_frequency": "300s",
        },
    }
    expected_info = {
        "name": "sum_1d",
        "dtype": "FLOAT",
        "entities": [{"name": "customer", "serving_names": ["cust_id"], "catalog_name": "catalog"}],
        "primary_entity": [
            {"name": "customer", "serving_names": ["cust_id"], "catalog_name": "catalog"}
        ],
        "tables": [{"name": "sf_event_table", "status": "PUBLIC_DRAFT", "catalog_name": "catalog"}],
        "table_feature_job_setting": {
            "this": [data_feature_job_setting],
            "default": [data_feature_job_setting],
        },
        "table_cleaning_operation": {"this": [], "default": []},
        "default_version_mode": "AUTO",
        "default_feature_id": str(saved_feature.id),
        "readiness": {"this": "DRAFT", "default": "DRAFT"},
        "catalog_name": "catalog",
        "namespace_description": None,
        "description": None,
    }
    assert info_dict.items() > expected_info.items(), info_dict
    assert "created_at" in info_dict, info_dict
    assert "version" in info_dict, info_dict
    assert set(info_dict["version"]) == {"this", "default"}, info_dict["version"]
    assert info_dict["versions_info"] is None, info_dict["versions_info"]

    verbose_info_dict = saved_feature.info(verbose=True)
    assert verbose_info_dict.items() > expected_info.items(), verbose_info_dict
    assert "created_at" in verbose_info_dict, verbose_info_dict
    assert "version" in verbose_info_dict, verbose_info_dict
    assert set(verbose_info_dict["version"]) == {"this", "default"}, verbose_info_dict["version"]

    assert "versions_info" in verbose_info_dict, verbose_info_dict
    assert len(verbose_info_dict["versions_info"]) == 1, verbose_info_dict
    assert set(verbose_info_dict["versions_info"][0]) == {
        "version",
        "readiness",
        "created_at",
    }, verbose_info_dict


def test_feature_save__exception_due_to_feature_saved_before(float_feature, saved_feature):
    """
    Test feature save failure due to event table not saved
    """
    _ = saved_feature
    assert saved_feature.saved is True
    with pytest.raises(ObjectHasBeenSavedError) as exc:
        float_feature.save()
    expected_msg = f'Feature (id: "{float_feature.id}") has been saved before.'
    assert expected_msg in str(exc.value)

    # check that saving a saved feature twice won't throw ObjectHasBeenSavedError
    feature_id = saved_feature.id
    saved_feature.save(conflict_resolution="retrieve")
    assert saved_feature.id == feature_id


def test_feature_name__set_name_when_unnamed(float_feature):
    """
    Test setting name for unnamed features creates alias node
    """
    new_feature = float_feature + 1234

    assert new_feature.name is None
    assert new_feature.node.dict(exclude={"name": True}) == {
        "type": "add",
        "parameters": {"value": 1234, "right_op": False},
        "output_type": "series",
    }
    old_node_name = new_feature.node.name

    new_feature.name = "my_feature_1234"
    assert new_feature.node.dict(exclude={"name": True}) == {
        "type": "alias",
        "parameters": {"name": "my_feature_1234"},
        "output_type": "series",
    }
    assert new_feature.graph.backward_edges_map[new_feature.node.name] == [old_node_name]


def test_feature_name__set_name_invalid_from_project(float_feature):
    """
    Test changing name for already named feature is not allowed
    """
    with pytest.raises(ValueError) as exc_info:
        float_feature.name = "my_new_feature"
    assert str(exc_info.value) == 'Feature "sum_1d" cannot be renamed to "my_new_feature"'


def test_feature_name__set_name_invalid_from_alias(float_feature):
    """
    Test changing name for already named feature is not allowed
    """
    new_feature = float_feature + 1234
    new_feature.name = "my_feature_1234"
    with pytest.raises(ValueError) as exc_info:
        new_feature.name = "my_feature_1234_v2"
    assert str(exc_info.value) == (
        'Feature "my_feature_1234" cannot be renamed to "my_feature_1234_v2"'
    )


def test_feature_name__set_name_invalid_none(float_feature):
    """
    Test setting name as None is not allowed
    """
    new_feature = float_feature + 1234
    with pytest.raises(ValueError) as exc_info:
        new_feature.name = None
    assert str(exc_info.value) == "None is not a valid feature name"


def test_get_feature(saved_feature):
    """
    Test get feature using feature name
    """
    feature = Feature.get(name=saved_feature.name)
    assert feature.saved is True
    assert feature.dict() == saved_feature.dict()
    get_by_id_feat = Feature.get_by_id(feature.id)
    assert get_by_id_feat.dict() == feature.dict()
    assert get_by_id_feat.saved is True

    # ensure Proxy object works in binary operations
    _ = get_by_id_feat == feature

    # check audit history
    audit_history = saved_feature.audit()
    assert (audit_history["action_type"] == "INSERT").all()
    assert (audit_history["name"] == 'insert: "sum_1d"').all()
    assert audit_history["old_value"].isnull().all()
    assert set(audit_history["field_name"]) == {
        "tabular_source.table_details.table_name",
        "updated_at",
        "tabular_source.feature_store_id",
        "table_ids",
        "primary_table_ids",
        "user_id",
        "tabular_source.table_details.database_name",
        "feature_namespace_id",
        "online_enabled",
        "created_at",
        "entity_ids",
        "version.name",
        "feature_list_ids",
        "raw_graph.nodes",
        "raw_graph.edges",
        "node_name",
        "version.suffix",
        "deployed_feature_list_ids",
        "tabular_source.table_details.schema_name",
        "name",
        "readiness",
        "graph.edges",
        "graph.nodes",
        "dtype",
        "catalog_id",
        "definition",
        "user_defined_function_ids",
        "block_modification_by",
        "aggregation_ids",
        "aggregation_result_names",
        "description",
    }

    with pytest.raises(RecordRetrievalException) as exc:
        Feature.get(name="random_name")

    expected_msg = 'FeatureNamespace (name: "random_name") not found. Please save the FeatureNamespace object first.'
    assert expected_msg in str(exc.value)


def test_unary_op_inherits_event_table_id(float_feature):
    """
    Test unary operation inherits table_ids
    """
    new_feature = float_feature.isnull()
    assert new_feature.table_ids == float_feature.table_ids


def test_feature__default_version_info_retrieval(
    saved_feature, snowflake_event_table, mock_api_object_cache
):
    """
    Test get feature using feature name
    """
    _ = mock_api_object_cache
    feature = Feature.get(name=saved_feature.name)
    assert feature.is_default is True
    assert feature.default_version_mode == DefaultVersionMode.AUTO
    assert feature.default_readiness == FeatureReadiness.DRAFT
    assert feature.saved is True

    new_feature = feature.create_new_version(
        table_feature_job_settings=[
            TableFeatureJobSetting(
                table_name=snowflake_event_table.name,
                feature_job_setting=FeatureJobSetting(
                    blind_spot="45m", frequency="30m", time_modulo_frequency="15m"
                ),
            )
        ],
    )
    assert new_feature.is_default is True
    assert new_feature.default_version_mode == DefaultVersionMode.AUTO
    assert new_feature.default_readiness == FeatureReadiness.DRAFT

    # check that feature becomes non-default
    assert feature.is_default is False


def test_feature_derived_from_saved_feature_not_saved(saved_feature):
    """
    Test feature derived from saved feature is consider not saved
    """
    derived_feat = saved_feature + 1
    assert derived_feat.saved is False


def test_create_new_version(saved_feature, snowflake_event_table):
    """Test creation a new version"""
    new_version = saved_feature.create_new_version(
        table_feature_job_settings=[
            TableFeatureJobSetting(
                table_name=snowflake_event_table.name,
                feature_job_setting=FeatureJobSetting(
                    blind_spot="45m", frequency="30m", time_modulo_frequency="15m"
                ),
            )
        ],
        table_cleaning_operations=None,
    )

    assert new_version.id != saved_feature.id
    assert new_version.saved is True

    saved_feature_version = saved_feature.version
    assert new_version.version == f"{saved_feature_version}_1"

    new_version_dict = new_version.dict()
    assert new_version_dict["graph"]["nodes"][1]["type"] == "graph"
    groupby_node = new_version_dict["graph"]["nodes"][2]
    groupby_node_params = groupby_node["parameters"]
    assert groupby_node["type"] == "groupby"
    assert groupby_node_params["blind_spot"] == 45 * 60
    assert groupby_node_params["frequency"] == 30 * 60
    assert groupby_node_params["time_modulo_frequency"] == 15 * 60

    # before deletion
    _ = Feature.get_by_id(new_version.id)

    # check feature deletion
    new_version.delete()
    assert new_version.saved is False

    # check that feature is no longer retrievable
    with pytest.raises(RecordRetrievalException) as exc_info:
        Feature.get_by_id(new_version.id)
    expected_msg = (
        f'Feature (id: "{new_version.id}") not found. Please save the Feature object first.'
    )
    assert expected_msg in str(exc_info.value)


def test_delete_feature(saved_feature):
    """Test deletion of feature"""
    assert saved_feature.readiness == FeatureReadiness.DRAFT
    saved_feature.delete()
    assert saved_feature.saved is False

    with pytest.raises(RecordRetrievalException) as exc_info:
        Feature.get_by_id(saved_feature.id)

    expected_msg = (
        f'Feature (id: "{saved_feature.id}") not found. Please save the Feature object first.'
    )
    assert expected_msg in str(exc_info.value)


def test_create_new_version__with_data_cleaning_operations(
    saved_feature, snowflake_event_table, update_fixtures
):
    """Test creation of new version with table cleaning operations"""
    # check sdk code generation of source feature
    check_sdk_code_generation(saved_feature, to_use_saved_data=True)

    # create a new feature version
    new_version = saved_feature.create_new_version(
        table_feature_job_settings=[
            TableFeatureJobSetting(
                table_name=snowflake_event_table.name,
                feature_job_setting=FeatureJobSetting(
                    blind_spot="45m", frequency="30m", time_modulo_frequency="15m"
                ),
            )
        ],
        table_cleaning_operations=[
            TableCleaningOperation(
                table_name="sf_event_table",
                column_cleaning_operations=[
                    # column to be aggregated on
                    ColumnCleaningOperation(
                        column_name="col_float",
                        cleaning_operations=[MissingValueImputation(imputed_value=0.0)],
                    ),
                    # group by column
                    ColumnCleaningOperation(
                        column_name="cust_id",
                        cleaning_operations=[MissingValueImputation(imputed_value=-999)],
                    ),
                    # unused column
                    ColumnCleaningOperation(
                        column_name="col_int",
                        cleaning_operations=[MissingValueImputation(imputed_value=0)],
                    ),
                ],
            )
        ],
    )

    # check sdk code generation for newly created feature
    check_sdk_code_generation(
        new_version,
        to_use_saved_data=True,
        fixture_path="tests/fixtures/sdk_code/feature_time_based_with_data_cleaning_operations.py",
        update_fixtures=update_fixtures,
        table_id=saved_feature.table_ids[0],
    )

    # create another new feature version without table cleaning operations
    version_without_clean_ops = new_version.create_new_version(
        table_cleaning_operations=[
            TableCleaningOperation(table_name="sf_event_table", column_cleaning_operations=[])
        ]
    )
    check_sdk_code_generation(version_without_clean_ops, to_use_saved_data=True)


def test_create_new_version__error(float_feature):
    """Test creation a new version (exception)"""
    with pytest.raises(RecordCreationException) as exc:
        float_feature.create_new_version(
            table_feature_job_settings=[
                TableFeatureJobSetting(
                    table_name="sf_event_table",
                    feature_job_setting=FeatureJobSetting(
                        blind_spot="45m", frequency="30m", time_modulo_frequency="15m"
                    ),
                )
            ],
            table_cleaning_operations=None,
        )

    expected_msg = (
        f'Feature (id: "{float_feature.id}") not found. Please save the Feature object first.'
    )
    assert expected_msg in str(exc.value)


def test_feature__as_default_version(saved_feature):
    """Test feature as_default_version method"""
    new_version = saved_feature.create_new_version(
        table_feature_job_settings=[
            TableFeatureJobSetting(
                table_name="sf_event_table",
                feature_job_setting=FeatureJobSetting(
                    blind_spot="15m", frequency="30m", time_modulo_frequency="15m"
                ),
            )
        ],
        table_cleaning_operations=None,
    )
    assert new_version.is_default is True
    assert new_version.default_version_mode == "AUTO"

    # check setting default version fails when default version mode is not MANUAL
    with pytest.raises(RecordUpdateException) as exc:
        saved_feature.as_default_version()
    expected = "Cannot set default feature ID when default version mode is not MANUAL."
    assert expected in str(exc.value)

    # check get by name use the default version
    assert Feature.get(name=saved_feature.name) == new_version

    # check setting default version manually
    assert new_version.is_default is True
    assert saved_feature.is_default is False
    saved_feature.update_default_version_mode(DefaultVersionMode.MANUAL)
    saved_feature.as_default_version()
    assert new_version.is_default is False
    assert saved_feature.is_default is True

    # check get by name use the default version
    assert Feature.get(name=saved_feature.name) == saved_feature

    # check get by name and version
    assert Feature.get(name=saved_feature.name, version=new_version.version) == new_version

    # check logic to prevent setting lower readiness version as default
    saved_feature.update_readiness(FeatureReadiness.PUBLIC_DRAFT)
    with pytest.raises(RecordUpdateException) as exc:
        new_version.as_default_version()

    error_msg = (
        f"Cannot set default feature ID to {new_version.id} "
        f"because its readiness level (DRAFT) is lower than the readiness level of "
        f"version {saved_feature.version} (PUBLIC_DRAFT)."
    )
    assert error_msg in str(exc.value)
    assert new_version.is_default is False
    assert saved_feature.is_default is True

    new_version.update_readiness(FeatureReadiness.PUBLIC_DRAFT)
    new_version.as_default_version()
    assert new_version.is_default is True
    assert saved_feature.is_default is False


def test_composite_features(snowflake_event_table_with_entity, cust_id_entity):
    """Test composite features' property"""
    entity = Entity(name="binary", serving_names=["col_binary"])
    entity.save()

    # make col_binary as an entity column
    snowflake_event_table_with_entity.col_binary.as_entity("binary")

    event_view = snowflake_event_table_with_entity.get_view()
    feature_job_setting = FeatureJobSetting(
        blind_spot="10m",
        frequency="30m",
        time_modulo_frequency="5m",
    )
    feature_group_by_cust_id_30m = event_view.groupby("cust_id").aggregate_over(
        value_column="col_float",
        method="sum",
        windows=["30m"],
        feature_job_setting=feature_job_setting,
        feature_names=["sum_30m_by_cust_id_30m"],
    )
    feature_group_by_cust_id_1h = event_view.groupby("cust_id").aggregate_over(
        value_column="col_float",
        method="sum",
        windows=["1h"],
        feature_job_setting=feature_job_setting,
        feature_names=["sum_30m_by_cust_id_1h"],
    )
    feature_group_by_binary = event_view.groupby("col_binary").aggregate_over(
        value_column="col_float",
        method="sum",
        windows=["30m"],
        feature_job_setting=feature_job_setting,
        feature_names=["sum_30m_by_binary"],
    )
    composite_feature = (
        feature_group_by_cust_id_30m["sum_30m_by_cust_id_30m"]
        + feature_group_by_cust_id_1h["sum_30m_by_cust_id_1h"]
        + feature_group_by_binary["sum_30m_by_binary"]
    )

    assert composite_feature.primary_entity == [
        Entity.get_by_id(cust_id_entity.id),
        Entity.get_by_id(entity.id),
    ]
    assert composite_feature.entity_ids == sorted([cust_id_entity.id, entity.id])
    assert composite_feature.graph.get_entity_columns(node_name=composite_feature.node_name) == [
        "col_binary",
        "cust_id",
    ]


def test_update_readiness_and_default_version_mode(saved_feature):
    """Test update feature readiness"""
    assert saved_feature.readiness == FeatureReadiness.DRAFT
    saved_feature.update_readiness("PRODUCTION_READY")
    assert saved_feature.readiness == FeatureReadiness.PRODUCTION_READY
    saved_feature.update_readiness(FeatureReadiness.PUBLIC_DRAFT)
    assert saved_feature.readiness == FeatureReadiness.PUBLIC_DRAFT

    # check update on the same readiness
    saved_feature.update_readiness(FeatureReadiness.PUBLIC_DRAFT)
    assert saved_feature.readiness == FeatureReadiness.PUBLIC_DRAFT

    # check default version mode
    assert saved_feature.default_version_mode == DefaultVersionMode.AUTO
    saved_feature.update_default_version_mode("MANUAL")
    assert saved_feature.default_version_mode == DefaultVersionMode.MANUAL

    # test update on wrong readiness input
    with pytest.raises(ValueError) as exc:
        saved_feature.update_readiness("random")
    assert "'random' is not a valid FeatureReadiness" in str(exc.value)


def test_update_readiness__fail_guardrail_checks(saved_feature):
    """Test update feature readiness fail guardrail checks"""
    assert saved_feature.readiness == FeatureReadiness.DRAFT
    saved_feature.update_readiness(FeatureReadiness.PRODUCTION_READY)

    # create a new feature and try to update it production ready
    new_feature = saved_feature.create_new_version(
        table_feature_job_settings=[
            TableFeatureJobSetting(
                table_name="sf_event_table",
                feature_job_setting=FeatureJobSetting(
                    blind_spot="45m", frequency="30m", time_modulo_frequency="15m"
                ),
            )
        ],
    )

    # update saved_feature to PRODUCTION_READY should fail guardrail checks
    # test fail guardrail check due to existing feature version that is production ready
    with pytest.raises(RecordUpdateException) as exc:
        new_feature.update_readiness(FeatureReadiness.PRODUCTION_READY)

    expected_msg = (
        "Found another feature version that is already PRODUCTION_READY. "
        f'Please deprecate the feature "sum_1d" with ID {saved_feature.id} first before promoting the promoted '
        "version as there can only be one feature version that is production ready at any point in time. "
        f"We are unable to promote the feature with ID {new_feature.id} right now."
    )
    assert expected_msg in str(exc.value)

    # test fail guardrail check due to using deprecated table
    saved_feature.update_readiness(FeatureReadiness.PUBLIC_DRAFT)

    table = Table.get_by_id(saved_feature.table_ids[0])
    table.update_status(TableStatus.DEPRECATED)

    with pytest.raises(RecordUpdateException) as exc:
        new_feature.update_readiness(FeatureReadiness.PRODUCTION_READY)

    expected_msg = (
        'Found a deprecated table "sf_event_table" that is used by the feature "sum_1d". '
        "We are unable to promote the feature to PRODUCTION_READY right now."
    )
    assert expected_msg in str(exc.value)


def test_update_readiness_and_default_version_mode__unsaved_feature(float_feature):
    """Test update feature readiness on unsaved feature"""
    _ = float_feature
    with pytest.raises(RecordUpdateException) as exc:
        float_feature.update_readiness(FeatureReadiness.PRODUCTION_READY)
    expected = (
        f'Feature (id: "{float_feature.id}") not found. Please save the Feature object first.'
    )
    assert expected in str(exc.value)

    with pytest.raises(RecordRetrievalException) as exc:
        float_feature.update_default_version_mode(DefaultVersionMode.MANUAL)
    assert expected in str(exc.value)


def test_get_sql(float_feature):
    """Test get sql for feature"""
    assert float_feature.sql.endswith(
        'SELECT\n  "_fb_internal_window_w86400_sum_aed233b0e8a6e1c1e0d5427b126b03c949609481" AS "sum_1d"\n'
        "FROM _FB_AGGREGATED AS AGG"
    )


def test_list_filter(saved_feature):
    """Test filters in list"""
    # test filter by table and entity
    feature_list = Feature.list(primary_table="sf_event_table")
    assert feature_list.shape[0] == 1

    feature_list = Feature.list(primary_table="other_data", include_id=True)
    assert feature_list.shape[0] == 0

    feature_list = Feature.list(primary_entity="customer")
    assert feature_list.shape[0] == 1

    feature_list = Feature.list(primary_entity="other_entity")
    assert feature_list.shape[0] == 0

    feature_list = Feature.list(primary_table="sf_event_table", primary_entity="customer")
    assert feature_list.shape[0] == 1

    feature_list = Feature.list(primary_table=["sf_event_table"], primary_entity=["customer"])
    assert feature_list.shape[0] == 1

    feature_list = Feature.list(primary_table="sf_event_table", primary_entity="other_entity")
    assert feature_list.shape[0] == 0

    feature_list = Feature.list(primary_table=["sf_event_table"], primary_entity=["other_entity"])
    assert feature_list.shape[0] == 0

    feature_list = Feature.list(primary_table="other_data", primary_entity="customer")
    assert feature_list.shape[0] == 0


def test_is_time_based(saved_feature, non_time_based_feature):
    """
    Test is_time_based
    """
    # window aggregation feature is time based
    assert saved_feature.is_time_based is True

    # item aggregation feature is not time based
    assert non_time_based_feature.is_time_based is False


def test_list_versions(saved_feature):
    """
    Test list_versions
    """
    # save a few more features
    feature_group = FeatureGroup(items=[])
    feature_group[f"new_feat1"] = saved_feature + 1
    feature_group[f"new_feat2"] = saved_feature + 2
    feature_group.save()

    # check feature class list_version & feature object list_versions
    assert_frame_equal(
        Feature.list_versions(),
        pd.DataFrame(
            {
                "id": [
                    feature_group["new_feat2"].id,
                    feature_group["new_feat1"].id,
                    saved_feature.id,
                ],
                "name": ["new_feat2", "new_feat1", saved_feature.name],
                "version": [saved_feature.version] * 3,
                "dtype": [saved_feature.dtype] * 3,
                "readiness": [saved_feature.readiness] * 3,
                "online_enabled": [saved_feature.online_enabled] * 3,
                "tables": [["sf_event_table"]] * 3,
                "primary_tables": [["sf_event_table"]] * 3,
                "entities": [["customer"]] * 3,
                "primary_entities": [["customer"]] * 3,
                "created_at": [
                    feature_group[
                        "new_feat2"
                    ].cached_model.created_at,  # DEV-1820: created_at is not synced
                    feature_group[
                        "new_feat1"
                    ].cached_model.created_at,  # DEV-1820: created_at is not synced
                    saved_feature.created_at,
                ],
                "is_default": [True] * 3,
            }
        ),
    )
    assert_frame_equal(
        saved_feature.list_versions(),
        pd.DataFrame(
            {
                "id": [saved_feature.id],
                "name": [saved_feature.name],
                "version": [saved_feature.version],
                "dtype": [saved_feature.dtype],
                "readiness": [saved_feature.readiness],
                "online_enabled": [saved_feature.online_enabled],
                "tables": [["sf_event_table"]],
                "primary_tables": [["sf_event_table"]],
                "entities": [["customer"]],
                "primary_entities": [["customer"]],
                "created_at": [saved_feature.created_at],
                "is_default": [True],
            }
        ),
    )

    # check documentation of the list_versions
    assert Feature.list_versions.__doc__ == Feature._list_versions.__doc__
    assert (
        saved_feature.list_versions.__doc__ == saved_feature._list_versions_with_same_name.__doc__
    )


@freeze_time("2023-01-20 03:20:00")
def test_get_feature_jobs_status(saved_feature, feature_job_logs, update_fixtures):
    """
    Test get_feature_jobs_status
    """
    if update_fixtures:
        # update job_logs.csv fixture
        log_fixture_path = "tests/fixtures/feature_job_status/job_logs.csv"
        feature_job_logs = pd.read_csv(log_fixture_path)
        feature_job_logs["CREATED_AT"] = pd.to_datetime(feature_job_logs["CREATED_AT"])

        # extract tile ID and aggregation ID from the feature
        groupby_node = saved_feature.extract_pruned_graph_and_node()[0].get_node_by_name(
            "groupby_1"
        )
        tile_id = groupby_node.parameters.tile_id
        feature_job_logs["AGGREGATION_ID"] = groupby_node.parameters.aggregation_id
        feature_job_logs["SESSION_ID"] = feature_job_logs["SESSION_ID"].apply(
            lambda x: f"{tile_id}|{x.split('|')[1]}"
        )
        feature_job_logs.to_csv(log_fixture_path, index=False)

    with patch(
        "featurebyte.service.tile_job_log.TileJobLogService.get_logs_dataframe"
    ) as mock_get_jobs_dataframe:
        mock_get_jobs_dataframe.return_value = feature_job_logs
        job_status_result = saved_feature.get_feature_jobs_status(
            job_history_window=24, job_duration_tolerance=1700
        )

    fixture_path = "tests/fixtures/feature_job_status/expected_session_logs.parquet"
    if update_fixtures:
        job_status_result.job_session_logs.to_parquet(fixture_path)
        raise ValueError("Fixtures updated. Please run test again without --update-fixtures flag")
    else:
        expected_session_logs = pd.read_parquet(fixture_path)
        assert_frame_equal(job_status_result.job_session_logs, expected_session_logs)


@freeze_time("2023-01-20 03:20:00")
def test_get_feature_jobs_status_incomplete_logs(saved_feature, feature_job_logs):
    """
    Test get_feature_jobs_status incomplete logs found
    """
    with patch(
        "featurebyte.service.tile_job_log.TileJobLogService.get_logs_dataframe"
    ) as mock_get_jobs_dataframe:
        mock_get_jobs_dataframe.return_value = feature_job_logs[:1]
        job_status_result = saved_feature.get_feature_jobs_status(job_history_window=24)
    assert job_status_result.job_session_logs.shape == (1, 12)
    expected_feature_job_summary = pd.DataFrame(
        {
            "aggregation_hash": {0: "aed233b0"},
            "frequency(min)": {0: 30},
            "completed_jobs": {0: 0},
            "max_duration(s)": {0: np.nan},
            "95 percentile": {0: np.nan},
            "frac_late": {0: np.nan},
            "exceed_period": {0: 0},
            "failed_jobs": {0: 0},
            "incomplete_jobs": {0: 48},
            "time_since_last": {0: "NaT"},
        }
    )
    assert_frame_equal(
        job_status_result.feature_job_summary, expected_feature_job_summary, check_dtype=False
    )


@freeze_time("2023-01-20 03:20:00")
def test_get_feature_jobs_status_empty_logs(saved_feature, feature_job_logs):
    """
    Test get_feature_jobs_status incomplete logs found
    """
    with patch(
        "featurebyte.service.tile_job_log.TileJobLogService.get_logs_dataframe"
    ) as mock_get_jobs_dataframe:
        mock_get_jobs_dataframe.return_value = feature_job_logs[:0]
        job_status_result = saved_feature.get_feature_jobs_status(job_history_window=24)
    assert job_status_result.job_session_logs.shape == (0, 12)
    expected_feature_job_summary = pd.DataFrame(
        {
            "aggregation_hash": {0: "aed233b0"},
            "frequency(min)": {0: 30},
            "completed_jobs": {0: 0},
            "max_duration(s)": {0: np.nan},
            "95 percentile": {0: np.nan},
            "frac_late": {0: np.nan},
            "exceed_period": {0: 0},
            "failed_jobs": {0: 0},
            "incomplete_jobs": {0: 48},
            "time_since_last": {0: "NaT"},
        }
    )
    assert_frame_equal(
        job_status_result.feature_job_summary, expected_feature_job_summary, check_dtype=False
    )


def test_get_feature_jobs_status_feature_without_tile(
    saved_scd_table, cust_id_entity, feature_job_logs
):
    """
    Test get_feature_jobs_status for feature without tile
    """
    saved_scd_table["col_text"].as_entity(cust_id_entity.name)
    scd_view = saved_scd_table.get_view()
    feature = scd_view["effective_timestamp"].as_feature("Latest Record Change Date")
    feature.save()

    with patch(
        "featurebyte.session.snowflake.SnowflakeSession.execute_query"
    ) as mock_execute_query:
        mock_execute_query.return_value = feature_job_logs[:0]
        job_status_result = feature.get_feature_jobs_status()

    assert job_status_result.feature_tile_table.shape == (0, 2)
    assert job_status_result.feature_job_summary.shape == (0, 10)
    assert job_status_result.job_session_logs.shape == (0, 12)


def test_feature_synchronization(saved_feature):
    """Test feature synchronization"""
    # construct a cloned feature (feature with the same feature ID)
    cloned_feat = Feature.get_by_id(id=saved_feature.id)

    # update the original feature's version mode (stored at feature namespace record)
    target_mode = DefaultVersionMode.MANUAL
    assert saved_feature.default_version_mode != target_mode
    saved_feature.update_default_version_mode(target_mode)
    assert saved_feature.default_version_mode == target_mode

    # check the clone's version mode also get updated
    assert cloned_feat.default_version_mode == target_mode

    # update original feature's readiness (stored at feature record)
    target_readiness = FeatureReadiness.PUBLIC_DRAFT
    assert saved_feature.readiness != target_readiness
    saved_feature.update_readiness(target_readiness)
    assert saved_feature.readiness == target_readiness

    # check the clone's readiness value
    assert cloned_feat.readiness == target_readiness


def test_feature_deletion_failure(saved_feature):
    """Test feature deletion failure"""
    feature_list = FeatureList([saved_feature], name="test_feature_list")
    feature_list.save()
    with pytest.raises(RecordDeletionException) as exc_info:
        saved_feature.delete()

    version = feature_list.version
    expected_msg = (
        "Feature is still in use by feature list(s). Please remove the following feature list(s) first:\n"
        f"[{{'id': '{feature_list.id}',\n  'name': 'test_feature_list',\n  'version': '{version}'}}]"
    )
    assert expected_msg == exc_info.value.response.json()["detail"]


def test_feature_properties_from_cached_model__before_save(float_feature):
    """Test (unsaved) feature properties from cached model"""
    # check properties derived from feature model directly
    assert float_feature.saved is False
    assert float_feature.readiness == FeatureReadiness.DRAFT
    assert float_feature.online_enabled is False
    assert float_feature.deployed_feature_list_ids == []

    # check properties use feature namespace model info
    props = ["is_default", "default_version_mode", "default_readiness"]
    for prop in props:
        with pytest.raises(RecordRetrievalException):
            _ = getattr(float_feature, prop)


def test_feature_properties_from_cached_model__after_save(saved_feature):
    """Test (saved) feature properties from cached model"""
    # check properties derived from feature model directly
    assert saved_feature.saved is True
    assert saved_feature.readiness == FeatureReadiness.DRAFT
    assert saved_feature.online_enabled is False
    assert saved_feature.deployed_feature_list_ids == []

    # check properties use feature namespace model info
    assert saved_feature.is_default is True
    assert saved_feature.default_version_mode == DefaultVersionMode.AUTO
    assert saved_feature.default_readiness == FeatureReadiness.DRAFT


@pytest.fixture(name="feature_with_clean_column_names")
def feature_with_clean_column_names_fixture(saved_event_table, cust_id_entity):
    """Feature with clean column names"""
    col_names = ["col_int", "col_float", "cust_id"]
    for col_name in col_names:
        col = saved_event_table[col_name]
        col.update_critical_data_info(
            cleaning_operations=[MissingValueImputation(imputed_value=-1)]
        )

    saved_event_table.cust_id.as_entity(cust_id_entity.name)
    event_view = saved_event_table.get_view()
    feature = event_view.groupby("cust_id").aggregate_over(
        value_column="col_float",
        method="sum",
        windows=["30m"],
        feature_names=["sum_30m"],
        feature_job_setting=FeatureJobSetting(
            blind_spot="10m",
            frequency="30m",
            time_modulo_frequency="5m",
        ),
    )["sum_30m"]
    return feature, col_names


def test_feature_graph_prune_unused_cleaning_operations(feature_with_clean_column_names):
    """Test feature graph pruning unused cleaning operations"""
    feature, col_names = feature_with_clean_column_names

    # check feature graph before saving
    graph = QueryGraphModel(**feature._get_create_payload()["graph"])
    event_view_graph_node_metadata = graph.get_node_by_name("graph_1").parameters.metadata
    assert event_view_graph_node_metadata.column_cleaning_operations == [
        {"column_name": col_name, "cleaning_operations": [{"type": "missing", "imputed_value": -1}]}
        for col_name in col_names
    ]

    # check feature graph after saving
    feature.save()
    graph = QueryGraphModel(**feature.dict()["graph"])

    # check event view graph node metadata
    event_view_graph_node = graph.get_node_by_name("graph_1")
    assert event_view_graph_node.parameters.type == "event_view"
    event_view_graph_node_metadata = event_view_graph_node.parameters.metadata
    assert event_view_graph_node_metadata.column_cleaning_operations == [
        {"column_name": col_name, "cleaning_operations": [{"type": "missing", "imputed_value": -1}]}
        for col_name in ["col_float", "cust_id"]
    ]

    # check cleaning graph node (should contain only those columns that are used in the feature)
    cleaning_graph_node = event_view_graph_node.parameters.graph.get_node_by_name("graph_1")
    assert cleaning_graph_node.parameters.type == "cleaning"
    nested_graph = cleaning_graph_node.parameters.graph
    for assign_node in nested_graph.iterate_nodes(
        target_node=cleaning_graph_node.output_node,
        node_type="assign",
    ):
        assert assign_node.parameters.name in {"col_float", "cust_id"}


def test_feature_definition(feature_with_clean_column_names):
    """Test feature definition"""
    feature, _ = feature_with_clean_column_names

    # before save, the redundant cleaning operation should be included
    redundant_clean_op = 'column_name="col_int",'
    assert redundant_clean_op in feature.definition

    # after save, the redundant cleaning operation should be removed
    header = f"# Generated by SDK version: {get_version()}\n"
    expected = (
        header
        + textwrap.dedent(
            f"""
    from bson import ObjectId
    from featurebyte import ColumnCleaningOperation
    from featurebyte import EventTable
    from featurebyte import FeatureJobSetting
    from featurebyte import MissingValueImputation


    # event_table name: "sf_event_table"
    event_table = EventTable.get_by_id(ObjectId("6337f9651050ee7d5980660d"))
    event_view = event_table.get_view(
        view_mode="manual",
        drop_column_names=["created_at"],
        column_cleaning_operations=[
            ColumnCleaningOperation(
                column_name="col_float",
                cleaning_operations=[MissingValueImputation(imputed_value=-1)],
            ),
            ColumnCleaningOperation(
                column_name="cust_id",
                cleaning_operations=[MissingValueImputation(imputed_value=-1)],
            ),
        ],
    )
    grouped = event_view.groupby(by_keys=["cust_id"], category=None).aggregate_over(
        value_column="col_float",
        method="sum",
        windows=["30m"],
        feature_names=["sum_30m"],
        feature_job_setting=FeatureJobSetting(
            blind_spot="600s", frequency="1800s", time_modulo_frequency="300s"
        ),
        skip_fill_na=True,
    )
    feat = grouped["sum_30m"]
    output = feat
    output.save(_id=ObjectId("{feature.id}"))
    """
        ).strip()
    )
    feature.save()
    assert feature.definition.strip() == expected
    assert redundant_clean_op not in expected


@pytest.mark.parametrize("main_data_from_event_table", [True, False])
def test_feature_create_new_version__multiple_event_table(
    saved_event_table,
    snowflake_database_table_scd_table,
    cust_id_entity,
    main_data_from_event_table,
):
    """Test create new version with multiple feature job settings"""
    another_event_table = snowflake_database_table_scd_table.create_event_table(
        name="another_event_table",
        event_id_column="col_int",
        event_timestamp_column="effective_timestamp",
        record_creation_timestamp_column="end_timestamp",
    )

    # label entity column
    saved_event_table.cust_id.as_entity(cust_id_entity.name)
    another_event_table.col_text.as_entity(cust_id_entity.name)

    event_view = saved_event_table.get_view()
    another_event_view = another_event_table.get_view()
    if main_data_from_event_table:
        event_view.join(
            another_event_view,
            on="col_int",
            how="left",
            rsuffix="_another",
        )
        event_view_used = event_view
        entity_col_name = "cust_id"
        main_data_name, non_main_data_name = saved_event_table.name, another_event_table.name
    else:
        another_event_view.join(
            event_view,
            on="col_int",
            how="left",
            rsuffix="_another",
        )
        event_view_used = another_event_view
        entity_col_name = "col_text"
        main_data_name, non_main_data_name = another_event_table.name, saved_event_table.name

    feature = event_view_used.groupby(entity_col_name).aggregate_over(
        method="count",
        windows=["30m"],
        feature_names=["count_30m"],
        feature_job_setting=FeatureJobSetting(
            blind_spot="10m",
            frequency="30m",
            time_modulo_frequency="5m",
        ),
    )["count_30m"]
    feature.save()

    # create new version with different feature job setting on another event table dataset
    feature_job_setting = FeatureJobSetting(
        blind_spot="20m", frequency="30m", time_modulo_frequency="5m"
    )
    with pytest.raises(RecordCreationException) as exc:
        feature.create_new_version(
            table_feature_job_settings=[
                TableFeatureJobSetting(
                    table_name=non_main_data_name,
                    feature_job_setting=feature_job_setting,
                ),
            ],
        )

    # error expected as the group by is on event table dataset, but not on another event table dataset
    expected_error = (
        "Feature job setting does not result a new feature version. "
        "This is because the new feature version is the same as the source feature."
    )
    assert expected_error in str(exc.value)

    # create new version on event table & check group by params
    new_version = feature.create_new_version(
        table_feature_job_settings=[
            TableFeatureJobSetting(
                table_name=main_data_name, feature_job_setting=feature_job_setting
            ),
        ]
    )
    pruned_graph, _ = new_version.extract_pruned_graph_and_node()
    expected_job_settings = feature_job_setting.to_seconds()
    group_by_params = pruned_graph.get_node_by_name("groupby_1").parameters
    assert group_by_params.blind_spot == expected_job_settings["blind_spot"]
    assert group_by_params.frequency == expected_job_settings["frequency"]
    assert group_by_params.time_modulo_frequency == expected_job_settings["time_modulo_frequency"]


def test_primary_entity__unsaved_feature(float_feature, cust_id_entity):
    """
    Test primary_entity property for an unsaved feature
    """
    assert float_feature.primary_entity == [Entity.get_by_id(cust_id_entity.id)]


def test_primary_entity__saved_feature(saved_feature, cust_id_entity):
    """
    Test primary_entity property for a saved feature
    """
    assert saved_feature.primary_entity == [Entity.get_by_id(cust_id_entity.id)]


def test_primary_entity__feature_group(feature_group, cust_id_entity):
    """
    Test primary_entity property for a feature group
    """
    assert feature_group.primary_entity == [Entity.get_by_id(cust_id_entity.id)]


def test_list_unsaved_features(
    snowflake_database_table,
    feature_group_feature_job_setting,
    float_feature,
    count_per_category_feature_group,
    sum_per_category_feature,
    count_per_category_feature,
    snowflake_feature_store,
):
    """
    Test list_unsaved_features method
    """
    try:
        # create feature in new catalog
        Catalog.create(name="test_catalog", feature_store_name=snowflake_feature_store.name)
        event_table = snowflake_database_table.create_event_table(
            name="sf_event_table",
            event_id_column="col_int",
            event_timestamp_column="event_timestamp",
            record_creation_timestamp_column="created_at",
        )
        Entity.create(name="cust_id_entity", serving_names=["cust_id"])
        event_table.cust_id.as_entity("cust_id_entity")
        bool_feature = (
            event_table.get_view()
            .groupby("cust_id")
            .aggregate_over(
                value_column="col_float",
                method="sum",
                windows=["1d"],
                feature_job_setting=feature_group_feature_job_setting,
                feature_names=["sum_1d"],
            )["sum_1d"]
            > 100.0
        )
        activate_and_get_catalog("catalog")

        # create unsaved features
        unsaved_feature = float_feature
        feature_group = FeatureGroup(
            [float_feature, sum_per_category_feature],
        )
        feature_list_1 = FeatureList(
            [count_per_category_feature_group, sum_per_category_feature], name="FL1"
        )
        feature_list_2 = FeatureList(
            [float_feature, sum_per_category_feature, count_per_category_feature], name="FL2"
        )

        # test list unsaved features
        unsaved_feature_df = list_unsaved_features().sort_values(["name", "variable_name"])
        expected_df = pd.DataFrame(
            {
                "variable_name": [
                    "count_per_category_feature",
                    'count_per_category_feature_group["counts_1d"]',
                    'feature_list_1["counts_1d"]',
                    'feature_list_2["counts_1d"]',
                    'count_per_category_feature_group["counts_2h"]',
                    'feature_list_1["counts_2h"]',
                    'count_per_category_feature_group["counts_30m"]',
                    'feature_list_1["counts_30m"]',
                    'feature_group["sum_1d"]',
                    'feature_list_2["sum_1d"]',
                    "float_feature",
                    "unsaved_feature",
                    'feature_group["sum_30m"]',
                    'feature_list_1["sum_30m"]',
                    'feature_list_2["sum_30m"]',
                    "sum_per_category_feature",
                    "bool_feature",
                ],
                "name": [
                    "counts_1d",
                    "counts_1d",
                    "counts_1d",
                    "counts_1d",
                    "counts_2h",
                    "counts_2h",
                    "counts_30m",
                    "counts_30m",
                    "sum_1d",
                    "sum_1d",
                    "sum_1d",
                    "sum_1d",
                    "sum_30m",
                    "sum_30m",
                    "sum_30m",
                    "sum_30m",
                    None,
                ],
                "catalog": [
                    "catalog",
                    "catalog",
                    "catalog",
                    "catalog",
                    "catalog",
                    "catalog",
                    "catalog",
                    "catalog",
                    "catalog",
                    "catalog",
                    "catalog",
                    "catalog",
                    "catalog",
                    "catalog",
                    "catalog",
                    "catalog",
                    "test_catalog",
                ],
                "active_catalog": [
                    True,
                    True,
                    True,
                    True,
                    True,
                    True,
                    True,
                    True,
                    True,
                    True,
                    True,
                    True,
                    True,
                    True,
                    True,
                    True,
                    False,
                ],
            }
        )
        assert unsaved_feature_df.columns.tolist() == [
            "object_id",
            "variable_name",
            "name",
            "catalog",
            "active_catalog",
        ]
        pd.testing.assert_frame_equal(
            unsaved_feature_df[["variable_name", "name", "catalog", "active_catalog"]].reset_index(
                drop=True
            ),
            expected_df,
        )

        # save some features
        feature_list_1.save()
        float_feature.save()
        unsaved_feature_df = list_unsaved_features().sort_values(["name", "variable_name"])
        expected_df = pd.DataFrame(
            [
                {
                    "variable_name": "bool_feature",
                    "name": None,
                    "catalog": "test_catalog",
                    "active_catalog": False,
                }
            ]
        )
        pd.testing.assert_frame_equal(
            unsaved_feature_df[["variable_name", "name", "catalog", "active_catalog"]].reset_index(
                drop=True
            ),
            expected_df,
        )

        # save remaining
        activate_and_get_catalog("test_catalog")
        bool_feature.name = "bool"
        bool_feature.save()
        unsaved_feature_df = list_unsaved_features().sort_values(["name", "variable_name"])
        pd.testing.assert_frame_equal(
            unsaved_feature_df,
            pd.DataFrame(
                columns=["object_id", "variable_name", "name", "catalog", "active_catalog"]
            ),
        )
    finally:
        activate_and_get_catalog("catalog")


def test_unsaved_feature_repr(
    float_feature,
):
    expected_value = f"Feature[FLOAT](name=sum_1d, node_name={float_feature.node_name})"
    assert repr(float_feature) == expected_value

    # html representation for unsaved object should be the same as repr
    assert float_feature._repr_html_() == expected_value


def test_feature_dtype(
    float_feature,
    bool_feature,
    non_time_based_feature,
    sum_per_category_feature,
):
    """Test feature dtype before and after save"""
    bool_feature.name = "bool_feat"

    # test feature dtype before save
    assert float_feature.dtype == DBVarType.FLOAT
    assert bool_feature.dtype == DBVarType.BOOL
    assert non_time_based_feature.dtype == DBVarType.FLOAT
    assert sum_per_category_feature.dtype == DBVarType.OBJECT

    float_feature.save()
    bool_feature.save()
    non_time_based_feature.save()
    sum_per_category_feature.save()

    # test feature dtype after save
    assert float_feature.dtype == DBVarType.FLOAT
    assert bool_feature.dtype == DBVarType.BOOL
    assert non_time_based_feature.dtype == DBVarType.FLOAT
    assert sum_per_category_feature.dtype == DBVarType.OBJECT


@pytest.mark.flaky(reruns=3)
@pytest.mark.asyncio
async def test_feature_loading_time(mock_api_object_cache, saved_feature, persistent):
    """Test feature loading time (to detect changes in performance)"""
    # mock api object cache to disable caching
    _ = mock_api_object_cache
    sample_size = 10
    feature_loading_limit = 200

    # get elapsed time with persistent
    start = time.time()
    for _ in range(sample_size):
        _ = await persistent.find_one(
            collection_name="feature", query_filter={"_id": saved_feature.id}
        )
    persistent_elapsed_time = time.time() - start

    # get end-to-end elapsed time
    start = time.time()
    for _ in range(sample_size):
        _ = Feature.get_by_id(saved_feature.id)
    elapsed_time = time.time() - start

    # compute persistent elapsed time to elapsed time ratio
    ratio = elapsed_time / persistent_elapsed_time
    assert ratio < feature_loading_limit, ratio


class TestFeatureTestSuite(FeatureOrTargetBaseTestSuite):
    """Test suite for feature"""

    item_type = TestItemType.FEATURE
    expected_item_definition = (
        f"""
    # Generated by SDK version: {featurebyte.get_version()}"""
        + """
    from bson import ObjectId
    from featurebyte import EventTable
    from featurebyte import FeatureJobSetting

    event_table = EventTable.get_by_id(ObjectId("{table_id}"))
    event_view = event_table.get_view(
        view_mode="manual",
        drop_column_names=["created_at"],
        column_cleaning_operations=[],
    )
    grouped = event_view.groupby(by_keys=["cust_id"], category=None).aggregate_over(
        value_column="col_float",
        method="sum",
        windows=["1d"],
        feature_names=["sum_1d"],
        feature_job_setting=FeatureJobSetting(
            blind_spot="600s", frequency="1800s", time_modulo_frequency="300s"
        ),
        skip_fill_na=True,
    )
    feat = grouped["sum_1d"]
    output = feat
    """
    )
    expected_saved_item_definition = (
        f"""
    # Generated by SDK version: {featurebyte.get_version()}"""
        + """
    from bson import ObjectId
    from featurebyte import EventTable
    from featurebyte import FeatureJobSetting


    # event_table name: "sf_event_table"
    event_table = EventTable.get_by_id(ObjectId("{table_id}"))
    event_view = event_table.get_view(
        view_mode="manual",
        drop_column_names=["created_at"],
        column_cleaning_operations=[],
    )
    grouped = event_view.groupby(by_keys=["cust_id"], category=None).aggregate_over(
        value_column="col_float",
        method="sum",
        windows=["1d"],
        feature_names=["sum_1d"],
        feature_job_setting=FeatureJobSetting(
            blind_spot="600s", frequency="1800s", time_modulo_frequency="300s"
        ),
        skip_fill_na=True,
    )
    feat = grouped["sum_1d"]
    output = feat
    output.save(_id=ObjectId("{item_id}"))
    """
    )
