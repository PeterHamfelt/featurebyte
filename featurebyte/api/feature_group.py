"""
Feature group module.
"""

from __future__ import annotations

from typing import Any, List, Optional, OrderedDict, Sequence, Tuple, Union, cast

import collections
import time
from http import HTTPStatus

import pandas as pd
from pydantic import Field, parse_obj_as, root_validator
from typeguard import typechecked

from featurebyte.api.api_object import ConflictResolution
from featurebyte.api.entity import Entity
from featurebyte.api.feature import Feature
from featurebyte.common.doc_util import FBAutoDoc
from featurebyte.common.typing import Scalar
from featurebyte.common.utils import dataframe_from_json, enforce_observation_set_row_order
from featurebyte.config import Configurations
from featurebyte.core.mixin import ParentMixin
from featurebyte.core.series import Series
from featurebyte.exception import RecordRetrievalException
from featurebyte.logger import logger
from featurebyte.models.base import FeatureByteBaseModel
from featurebyte.models.feature import FeatureModel
from featurebyte.models.feature_list import FeatureCluster, FeatureListModel
from featurebyte.models.relationship_analysis import derive_primary_entity
from featurebyte.schema.feature_list import FeatureListPreview, FeatureListSQL


class BaseFeatureGroup(FeatureByteBaseModel):
    """
    BaseFeatureGroup class

    This class represents a collection of Feature's that users create.

    Parameters
    ----------
    items: Sequence[Union[Feature, BaseFeatureGroup]]
        List of feature like objects to be used to create the FeatureList
    feature_objects: OrderedDict[str, Feature]
        Dictionary of feature name to feature object
    """

    items: Sequence[Union[Feature, BaseFeatureGroup]] = Field(exclude=True)
    feature_objects: OrderedDict[str, Feature] = Field(
        exclude=True, default_factory=collections.OrderedDict
    )

    @property
    def _features(self) -> list[Feature]:
        """
        Retrieve list of features in the FeatureGroup object

        Returns
        -------
        List[Feature]


        Raises
        ------
        ValueError
            When the FeatureGroup object is empty
        """
        features: list[Feature] = list(self.feature_objects.values())
        if features:
            return features
        raise ValueError("There is no feature in the FeatureGroup object.")

    @property
    def feature_names(self) -> list[str]:
        """
        List of feature names in the FeatureGroup object.

        Returns
        -------
        list[str]
            List of feature names

        Examples
        --------
        >>> table = catalog.get_table("GROCERYINVOICE")
        >>> view = table.get_view()
        >>> feature_group = view.groupby("GroceryCustomerGuid").aggregate_over(
        ...     value_column=None,
        ...     method="count",
        ...     feature_names=["count_60days", "count_90days"],
        ...     windows=["60d", "90d"],
        ... )
        >>> feature_group.feature_names
        ['count_60days', 'count_90days']

        See Also
        --------
        - [FeatureGroup](/reference/featurebyte.api.feature_list.FeatureGroup/)
        - [FeatureList.feature_names](/reference/featurebyte.api.feature_list.FeatureList.feature_names/)
        """
        return list(self.feature_objects)

    @property
    def primary_entity(self) -> List[Entity]:
        """
        Returns the primary entity of the FeatureList object.

        Returns
        -------
        List[Entity]
            Primary entity
        """
        entity_ids = set()
        for feature in self._features:
            entity_ids.update(feature.entity_ids)
        primary_entity = derive_primary_entity(  # type: ignore
            [Entity.get_by_id(entity_id) for entity_id in entity_ids]
        )
        return primary_entity

    @root_validator
    @classmethod
    def _set_feature_objects(cls, values: dict[str, Any]) -> dict[str, Any]:
        feature_objects = collections.OrderedDict()
        feature_ids = set()
        items = values.get("items", [])
        for item in items:
            if isinstance(item, Feature):
                if item.name is None:
                    raise ValueError(f'Feature (feature.id: "{item.id}") name must not be None!')
                if item.name in feature_objects:
                    raise ValueError(f'Duplicated feature name (feature.name: "{item.name}")!')
                if item.id in feature_ids:
                    raise ValueError(f'Duplicated feature id (feature.id: "{item.id}")!')
                feature_objects[item.name] = item
                feature_ids.add(item.id)
            else:
                for name, feature in item.feature_objects.items():
                    if feature.name in feature_objects:
                        raise ValueError(
                            f'Duplicated feature name (feature.name: "{feature.name}")!'
                        )
                    if feature.id in feature_ids:
                        raise ValueError(f'Duplicated feature id (feature.id: "{feature.id}")!')
                    feature_objects[name] = feature
        values["feature_objects"] = feature_objects
        return values

    @typechecked
    def __init__(self, items: Sequence[Union[Feature, BaseFeatureGroup]], **kwargs: Any):
        super().__init__(items=items, **kwargs)
        # sanity check: make sure we don't make a copy on global query graph
        for item_origin, item in zip(items, self.items):
            if isinstance(item_origin, Feature) and isinstance(item, Feature):
                assert id(item_origin.graph.nodes) == id(item.graph.nodes)

    def _subset_single_column(self, column: str) -> Feature:
        return self.feature_objects[column]

    def _subset_list_of_columns(self, columns: list[str]) -> FeatureGroup:
        return FeatureGroup([self.feature_objects[elem] for elem in columns])

    @typechecked
    def __getitem__(self, item: Union[str, List[str]]) -> Union[Feature, FeatureGroup]:
        if isinstance(item, str):
            return self._subset_single_column(item)
        return self._subset_list_of_columns(item)

    @typechecked
    def drop(self, items: List[str]) -> FeatureGroup:
        """
        Drop feature(s) from the FeatureGroup/FeatureList

        Parameters
        ----------
        items: List[str]
            List of feature names to be dropped

        Returns
        -------
        FeatureGroup
            FeatureGroup object contains remaining feature(s)
        """
        selected_feat_names = [
            feat_name for feat_name in self.feature_objects if feat_name not in items
        ]
        return self._subset_list_of_columns(selected_feat_names)

    def _get_feature_clusters(self) -> List[FeatureCluster]:
        """
        Get groups of features in the feature lists that belong to the same feature store

        Returns
        -------
        List[FeatureCluster]
        """
        return FeatureListModel.derive_feature_clusters(cast(List[FeatureModel], self._features))

    @enforce_observation_set_row_order
    @typechecked
    def preview(
        self,
        observation_set: pd.DataFrame,
    ) -> Optional[pd.DataFrame]:
        """
        Materialize feature group using a small observation set of up to 50 rows.

        Unlike get_historical_features, this method does not store partial aggregations (tiles) to
        speed up future computation. Instead, it computes the features on the fly, and should be used
        only for small observation sets for debugging or prototyping unsaved features.

        Tiles are a method of storing partial aggregations in the feature store,
        which helps to minimize the resources required to fulfill historical, batch and online requests.

        Parameters
        ----------
        observation_set : pd.DataFrame
            Observation set DataFrame, which should contain the `POINT_IN_TIME` column,
            as well as columns with serving names for all entities used by features in the feature group.

        Returns
        -------
        pd.DataFrame
            Materialized feature values.
            The returned DataFrame will have the same number of rows, and include all columns from the observation set.

            **Note**: `POINT_IN_TIME` values will be converted to UTC time.

        Raises
        ------
        RecordRetrievalException
            Preview request failed

        Examples
        --------
        Create a feature group with two features.
        >>> features = fb.FeatureGroup([
        ...     catalog.get_feature("InvoiceCount_60days"),
        ...     catalog.get_feature("InvoiceAmountAvg_60days"),
        ... ])

        Prepare observation set with POINT_IN_TIME and serving names columns.
        >>> observation_set = pd.DataFrame({
        ...     "POINT_IN_TIME": ["2022-06-01 00:00:00", "2022-06-02 00:00:00"],
        ...     "GROCERYCUSTOMERGUID": [
        ...         "a2828c3b-036c-4e2e-9bd6-30c9ee9a20e3",
        ...         "ac479f28-e0ff-41a4-8e60-8678e670e80b",
        ...     ],
        ... })

        Preview the feature group with a small observation set.
        >>> features.preview(observation_set)
          POINT_IN_TIME                   GROCERYCUSTOMERGUID  InvoiceCount_60days  InvoiceAmountAvg_60days
        0    2022-06-01  a2828c3b-036c-4e2e-9bd6-30c9ee9a20e3                 10.0                    7.938
        1    2022-06-02  ac479f28-e0ff-41a4-8e60-8678e670e80b                  6.0                    9.870

        See Also
        --------
        - [Feature.preview](/reference/featurebyte.api.feature.Feature.preview/):
          Preview feature group.
        - [FeatureList.get_historical_features](/reference/featurebyte.api.feature_list.FeatureList.get_historical_features/):
          Get historical features from a feature list.
        """
        tic = time.time()

        payload = FeatureListPreview(
            feature_clusters=self._get_feature_clusters(),
            point_in_time_and_serving_name_list=observation_set.to_dict(orient="records"),
        )

        client = Configurations().get_client()
        response = client.post("/feature_list/preview", json=payload.json_dict())
        if response.status_code != HTTPStatus.OK:
            raise RecordRetrievalException(response)
        result = response.json()

        elapsed = time.time() - tic
        logger.debug(f"Preview took {elapsed:.2f}s")
        return dataframe_from_json(result)  # pylint: disable=no-member

    @property
    def sql(self) -> str:
        """
        Get FeatureGroup SQL.

        Returns
        -------
        str
            FeatureGroup SQL string.

        Raises
        ------
        RecordRetrievalException
            Failed to get feature list SQL.
        """
        payload = FeatureListSQL(
            feature_clusters=self._get_feature_clusters(),
        )

        client = Configurations().get_client()
        response = client.post("/feature_list/sql", json=payload.json_dict())
        if response.status_code != HTTPStatus.OK:
            raise RecordRetrievalException(response)

        return cast(
            str,
            response.json(),
        )


class FeatureGroup(BaseFeatureGroup, ParentMixin):
    """
    FeatureGroup represents a collection of Feature's.

    These Features are typically not production ready, and are mostly used as an in-memory representation while
    users are still building up their features in the SDK. Note that while this object has a `save` function, it is
    actually the individual features within this feature group that get persisted. Similarly, the object that
    gets constructed on the read path does not become a FeatureGroup. The persisted version that users interact with
    is called a FeatureList.

    Note that the following operations result in a new FeatureGroup object as the output could contain more than
    one Feature object:

    - [GroupBy.aggregate_over](/reference/featurebyte.api.groupby.GroupBy.aggregate_over/)
    - [View.as_features](/reference/featurebyte.api.view.View.as_features/)
    """

    # documentation metadata
    __fbautodoc__ = FBAutoDoc(proxy_class="featurebyte.FeatureGroup")

    @typechecked
    def __getitem__(self, item: Union[str, List[str]]) -> Union[Feature, FeatureGroup]:
        # Note: Feature can only modify FeatureGroup parent but not FeatureList parent.
        output = super().__getitem__(item)
        if isinstance(output, Feature):
            output.set_parent(self)
        return output

    @typechecked
    def __setitem__(
        self, key: Union[str, Tuple[Feature, str]], value: Union[Feature, Union[Scalar, Series]]
    ) -> None:
        if isinstance(key, tuple):
            if len(key) != 2:
                raise ValueError(f"{len(key)} elements found, when we only expect 2.")
            mask = key[0]
            if not isinstance(mask, Feature):
                raise ValueError("The mask provided should be a Feature.")
            column: str = key[1]
            feature = self[column]
            assert isinstance(feature, Series)
            feature[mask] = value
            return

        # Note: since parse_obj_as() makes a copy, the changes below don't apply to the original
        # Feature object
        value = parse_obj_as(Feature, value)
        # Name setting performs validation to ensure the specified name is valid
        value.name = key
        self.feature_objects[key] = value
        # sanity check: make sure we don't copy global query graph
        assert id(self.feature_objects[key].graph.nodes) == id(value.graph.nodes)

    @typechecked
    def save(self, conflict_resolution: ConflictResolution = "raise") -> None:
        """
        Save features within a FeatureGroup object to the persistent. Conflict could be triggered when the feature
        being saved has violated uniqueness check at the persistent (for example, same ID has been used by another
        record stored at the persistent).

        Parameters
        ----------
        conflict_resolution: ConflictResolution
            "raise" raises error when then counters conflict error (default)
            "retrieve" handle conflict error by retrieving the object with the same name
        """
        for feature_name in self.feature_names:
            self[feature_name].save(conflict_resolution=conflict_resolution)