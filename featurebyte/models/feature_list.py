"""
This module contains Feature list related models
"""
# pylint: disable=too-few-public-methods
from __future__ import annotations

from typing import Any, List, Optional

import functools
from collections import defaultdict

from bson.objectid import ObjectId
from pydantic import Field, StrictStr, root_validator, validator
from typeguard import typechecked

from featurebyte.enum import DBVarType, OrderedStrEnum
from featurebyte.models.base import (
    FeatureByteBaseDocumentModel,
    FeatureByteBaseModel,
    PydanticObjectId,
    UniqueConstraintResolutionSignature,
    UniqueValuesConstraint,
)
from featurebyte.models.feature import DefaultVersionMode, FeatureModel, FeatureReadiness

FeatureListVersionIdentifier = StrictStr


class FeatureListStatus(OrderedStrEnum):
    """FeatureList status"""

    DEPRECATED = "DEPRECATED"
    DRAFT = "DRAFT"
    PUBLIC_DRAFT = "PUBLIC_DRAFT"
    PUBLISHED = "PUBLISHED"


class FeatureTypeFeatureCount(FeatureByteBaseModel):
    """
    Feature count corresponding to the feature type within a feature list

    dtype: DBVarType
        Feature data type
    count: int
        Number of features with the specified data type
    """

    dtype: DBVarType
    count: int


class FeatureReadinessCount(FeatureByteBaseModel):
    """
    Feature count corresponding to the feature readiness within a feature list

    readiness: FeatureReadiness
        Feature readiness level
    count: int
        Number of features with the given readiness within a feature list
    """

    readiness: FeatureReadiness
    count: int


class FeatureReadinessTransition(FeatureByteBaseModel):
    """
    Feature readiness transition
    """

    from_readiness: FeatureReadiness
    to_readiness: FeatureReadiness


@functools.total_ordering
class FeatureReadinessDistribution(FeatureByteBaseModel):
    """
    Feature readiness distribution
    """

    __root__: List[FeatureReadinessCount]

    @property
    def total_count(self) -> int:
        """
        Total count of the distribution

        Returns
        -------
        int
        """
        return sum(readiness_count.count for readiness_count in self.__root__)

    @staticmethod
    def _to_count_per_readiness_map(
        feature_readiness_dist: FeatureReadinessDistribution,
    ) -> dict[FeatureReadiness, int]:
        output = {}
        for feature_readiness in FeatureReadiness:
            output[feature_readiness] = 0

        for feature_readiness_count in feature_readiness_dist.__root__:
            output[feature_readiness_count.readiness] += feature_readiness_count.count
        return output

    @classmethod
    def _transform_and_check(
        cls, this_dist: FeatureReadinessDistribution, other_dist: FeatureReadinessDistribution
    ) -> tuple[dict[FeatureReadiness, int], dict[FeatureReadiness, int]]:
        this_dist_map = cls._to_count_per_readiness_map(this_dist)
        other_dist_map = cls._to_count_per_readiness_map(other_dist)
        if sum(this_dist_map.values()) != sum(other_dist_map.values()):
            raise ValueError(
                "Invalid comparison between two feature readiness distributions with different sums."
            )
        return this_dist_map, other_dist_map

    @typechecked
    def __eq__(self, other: FeatureReadinessDistribution) -> bool:  # type: ignore[override]
        this_dist_map, other_dist_map = self._transform_and_check(self, other)
        for feature_readiness in FeatureReadiness:
            if this_dist_map[feature_readiness] != other_dist_map[feature_readiness]:
                return False
        return True

    @typechecked
    def __lt__(self, other: FeatureReadinessDistribution) -> bool:
        # check whether the two readiness distributions comparison is valid
        this_dist_map, other_dist_map = self._transform_and_check(self, other)

        # first check the production readiness fraction first
        this_prod_ready_frac = self.derive_production_ready_fraction()
        other_prod_ready_frac = other.derive_production_ready_fraction()
        if this_prod_ready_frac != other_prod_ready_frac:
            return this_prod_ready_frac < other_prod_ready_frac

        # feature readiness sorted from the worst readiness (deprecated) to the best readiness (production ready)
        # the one with the lower number of readiness should be preferred
        # this mean: dist_with_lower_bad_readiness > dist_with_higher_bad_readiness
        for feature_readiness in FeatureReadiness:
            compare_readiness = (
                this_dist_map[feature_readiness] == other_dist_map[feature_readiness]
            )
            if compare_readiness:
                continue
            return this_dist_map[feature_readiness] > other_dist_map[feature_readiness]
        return False

    def derive_production_ready_fraction(self) -> float:
        """
        Derive fraction of features whose readiness level is at production ready

        Returns
        -------
        Fraction of production ready features
        """
        production_ready_cnt = 0
        for readiness_count in self.__root__:
            if readiness_count.readiness == FeatureReadiness.PRODUCTION_READY:
                production_ready_cnt += readiness_count.count
        return production_ready_cnt / max(self.total_count, 1)

    def update_readiness(
        self, transition: FeatureReadinessTransition
    ) -> FeatureReadinessDistribution:
        """
        Construct a new readiness distribution based on current distribution & readiness transition

        Parameters
        ----------
        transition: FeatureReadinessTransition
            Feature readiness transition

        Returns
        -------
        FeatureReadinessDistribution

        Raises
        ------
        ValueError
            When the readiness transition is invalid
        """
        this_dist_map = self._to_count_per_readiness_map(self)
        if this_dist_map[transition.from_readiness] < 1:
            raise ValueError("Invalid feature readiness transition.")
        this_dist_map[transition.from_readiness] -= 1
        this_dist_map[transition.to_readiness] += 1
        readiness_dist = []
        for feature_readiness in FeatureReadiness:
            count = this_dist_map[feature_readiness]
            if count:
                readiness_dist.append(
                    FeatureReadinessCount(readiness=feature_readiness, count=count)
                )
        return FeatureReadinessDistribution(__root__=readiness_dist)

    def worst_case(self) -> FeatureReadinessDistribution:
        """
        Return the worst possible case for feature readiness distribution

        Returns
        -------
        FeatureReadinessDistribution
        """
        return FeatureReadinessDistribution(
            __root__=[
                FeatureReadinessCount(readiness=min(FeatureReadiness), count=self.total_count)
            ]
        )


class FeatureListNamespaceModel(FeatureByteBaseDocumentModel):
    """
    Feature list set with the same feature list name

    id: PydanticObjectId
        Feature namespace id
    name: str
        Feature name
    feature_list_ids: List[PydanticObjectId]
        List of feature list ids
    feature_namespace_ids: List[PydanticObjectId]
        List of feature namespace ids
    dtype_distribution: List[FeatureTypeFeatureCount]
        Feature type distribution
    readiness_distribution: FeatureReadinessDistribution
        Feature readiness distribution of the default feature list
    default_feature_list_id: PydanticObjectId
        Default feature list id
    default_version_mode: DefaultVersionMode
        Default feature version mode
    status: FeatureListStatus
        Feature list status
    entity_ids: List[PydanticObjectId]
        Entity IDs used in the feature list
    event_data_ids: List[PydanticObjectId]
        EventData IDs used in the feature list
    """

    feature_list_ids: List[PydanticObjectId] = Field(allow_mutation=False)
    feature_namespace_ids: List[PydanticObjectId] = Field(allow_mutation=False)
    dtype_distribution: List[FeatureTypeFeatureCount] = Field(allow_mutation=False)
    readiness_distribution: FeatureReadinessDistribution = Field(allow_mutation=False)
    default_feature_list_id: PydanticObjectId = Field(allow_mutation=False)
    default_version_mode: DefaultVersionMode = Field(
        default=DefaultVersionMode.AUTO, allow_mutation=False
    )
    status: FeatureListStatus = Field(allow_mutation=False, default=FeatureListStatus.DRAFT)
    entity_ids: List[PydanticObjectId] = Field(allow_mutation=False)
    event_data_ids: List[PydanticObjectId] = Field(allow_mutation=False)

    @staticmethod
    def derive_feature_namespace_ids(features: List[FeatureModel]) -> List[PydanticObjectId]:
        """
        Derive feature namespace id from features

        Parameters
        ----------
        features: List[FeatureModel]
            List of features

        Returns
        -------
        List[PydanticObjectId]
        """
        return [feature.feature_namespace_id for feature in features]

    @staticmethod
    def derive_dtype_distribution(features: List[FeatureModel]) -> List[FeatureTypeFeatureCount]:
        """
        Derive feature data type distribution from features

        Parameters
        ----------
        features: List[FeatureModel]
            List of features

        Returns
        -------
        List[FeatureTypeFeatureCount]
        """
        dtype_count_map: dict[DBVarType, int] = defaultdict(int)
        for feature in features:
            dtype_count_map[feature.dtype] += 1
        return [
            FeatureTypeFeatureCount(dtype=dtype, count=count)
            for dtype, count in dtype_count_map.items()
        ]

    @staticmethod
    def derive_entity_ids(features: List[FeatureModel]) -> List[ObjectId]:
        """
        Derive entity ids from features

        Parameters
        ----------
        features: List[FeatureModel]
            List of features

        Returns
        -------
        List of entity ids
        """
        entity_ids = []
        for feature in features:
            entity_ids.extend(feature.entity_ids)
        return sorted(set(entity_ids))

    @staticmethod
    def derive_event_data_ids(features: List[FeatureModel]) -> List[ObjectId]:
        """
        Derive event data ids from features

        Parameters
        ----------
        features: List[FeatureModel]
            List of features

        Returns
        -------
        List of event data ids
        """
        event_data_ids = []
        for feature in features:
            event_data_ids.extend(feature.event_data_ids)
        return sorted(set(event_data_ids))

    @root_validator(pre=True)
    @classmethod
    def _derive_feature_related_attributes(cls, values: dict[str, Any]) -> dict[str, Any]:
        # "features" is not an attribute to the FeatureList model, when it appears in the input to
        # constructor, it is intended to be used to derive other feature-related attributes
        if "features" in values:
            features = values["features"]
            values["feature_namespace_ids"] = cls.derive_feature_namespace_ids(features)
            values["dtype_distribution"] = cls.derive_dtype_distribution(features)
            values["entity_ids"] = cls.derive_entity_ids(features)
            values["event_data_ids"] = cls.derive_event_data_ids(features)
        return values

    @validator("feature_list_ids", "feature_namespace_ids", "entity_ids", "event_data_ids")
    @classmethod
    def _validate_ids(cls, value: List[ObjectId]) -> List[ObjectId]:
        # make sure list of ids always sorted
        return sorted(value)

    class Settings:
        """
        MongoDB settings
        """

        collection_name: str = "feature_list_namespace"
        unique_constraints: List[UniqueValuesConstraint] = [
            UniqueValuesConstraint(
                fields=("_id",),
                conflict_fields_signature={"id": ["_id"]},
                resolution_signature=None,
            ),
            UniqueValuesConstraint(
                fields=("name",),
                conflict_fields_signature={"name": ["name"]},
                resolution_signature=UniqueConstraintResolutionSignature.RENAME,
            ),
        ]


class FeatureListModel(FeatureByteBaseDocumentModel):
    """
    Model for feature list entity

    id: PydanticObjectId
        FeatureList id of the object
    name: str
        Name of the feature list
    feature_ids: List[PydanticObjectId]
        List of feature IDs
    readiness_distribution: List[Dict[str, Any]]
        Feature readiness distribution of this feature list
    version: FeatureListVersionIdentifier
        Feature list version
    feature_list_namespace_id: PydanticObjectId
        Feature list namespace id of the object
    created_at: Optional[datetime]
        Datetime when the FeatureList was first saved or published
    """

    feature_ids: List[PydanticObjectId] = Field(default_factory=list)
    readiness_distribution: FeatureReadinessDistribution = Field(
        allow_mutation=False, default_factory=list
    )
    version: Optional[FeatureListVersionIdentifier] = Field(allow_mutation=False)
    feature_list_namespace_id: PydanticObjectId = Field(
        allow_mutation=False, default_factory=ObjectId
    )

    @staticmethod
    def derive_readiness_distribution(features: List[FeatureModel]) -> FeatureReadinessDistribution:
        """
        Derive feature readiness distribution from features

        Parameters
        ----------
        features: List[FeatureModel]
            List of features

        Returns
        -------
        FeatureReadinessDistribution
        """
        readiness_count_map: dict[FeatureReadiness, int] = defaultdict(int)
        for feature in features:
            readiness_count_map[feature.readiness] += 1
        return FeatureReadinessDistribution(
            __root__=[
                FeatureReadinessCount(readiness=readiness, count=count)
                for readiness, count in readiness_count_map.items()
            ]
        )

    @root_validator(pre=True)
    @classmethod
    def _derive_feature_related_attributes(cls, values: dict[str, Any]) -> dict[str, Any]:
        # "features" is not an attribute to the FeatureList model, when it appears in the input to
        # constructor, it is intended to be used to derive other feature-related attributes
        if "features" in values:
            values["readiness_distribution"] = cls.derive_readiness_distribution(values["features"])
        return values

    @validator("feature_ids")
    @classmethod
    def _validate_ids(cls, value: List[ObjectId]) -> List[ObjectId]:
        # make sure list of ids always sorted
        return sorted(value)

    @validator("readiness_distribution")
    @classmethod
    def _validate_readiness_distribution(cls, value: Any, values: dict[str, Any]) -> Any:
        total_count = sum(read_count.count for read_count in value.__root__)
        if total_count != len(values["feature_ids"]):
            raise ValueError(
                "readiness_distribution total count is different from total feature ids."
            )
        return value

    class Settings:
        """
        MongoDB settings
        """

        collection_name: str = "feature_list"
        unique_constraints: List[UniqueValuesConstraint] = [
            UniqueValuesConstraint(
                fields=("_id",),
                conflict_fields_signature={"id": ["_id"]},
                resolution_signature=UniqueConstraintResolutionSignature.GET_NAME,
            ),
            UniqueValuesConstraint(
                fields=("name", "version"),
                conflict_fields_signature={"name": ["name"], "version": ["version"]},
                resolution_signature=UniqueConstraintResolutionSignature.GET_BY_ID,
            ),
            UniqueValuesConstraint(
                fields=("feature_ids",),
                conflict_fields_signature={"feature_ids": ["feature_ids"]},
                resolution_signature=UniqueConstraintResolutionSignature.GET_NAME,
            ),
        ]