"""
This module contains EventData related models
"""
from typing import Any, Dict, List, Optional, Union

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, root_validator

from featurebyte.common.feature_job_setting_validation import validate_job_setting_parameters
from featurebyte.enum import SourceType


class SnowflakeDetails(BaseModel):
    """Model for Snowflake data source information"""

    account: str
    warehouse: str
    database: str
    sf_schema: str  # schema shadows a BaseModel attribute


class SQLiteDetails(BaseModel):
    """Model for SQLite data source information"""

    filename: str


class DatabaseSource(BaseModel):
    """Model for a database source"""

    type: SourceType
    details: Union[SnowflakeDetails, SQLiteDetails]


class FeatureJobSetting(BaseModel):
    """Model for Feature Job Setting"""

    blind_spot: str
    frequency: str
    time_modulo_frequency: str

    # pylint: disable=no-self-argument
    @root_validator(pre=True)
    def validate_setting_parameters(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        """Validate feature job setting parameters

        Parameters
        ----------
        values : dict
            Parameter values

        Returns
        -------
        dict
        """
        _ = cls
        validate_job_setting_parameters(
            frequency=values["frequency"],
            time_modulo_frequency=values["time_modulo_frequency"],
            blind_spot=values["blind_spot"],
        )
        return values


class FeatureJobSettingHistoryEntry(BaseModel):
    """Model for an entry in setting history"""

    creation_date: datetime
    setting: FeatureJobSetting


class EventDataStatus(str, Enum):
    """EventData status"""

    PUBLISHED = "PUBLISHED"
    DRAFT = "DRAFT"
    DEPRECATED = "DEPRECATED"


class EventDataModel(BaseModel):
    """
    Model for EventData entity

    Parameters
    ----------
    name : str
        Name of the EventData
    table_name : str
        Database table name
    source : DatabaseSource
        Data warehouse connection information
    default_feature_job_setting : FeatureJobSetting
        Default feature job setting
    created_at : datetime
        Date when the EventData was first saved or published
    history : list[FeatureJobSettingHistoryEntry]
        History of feature job settings
    status : EventDataStatus
        Status of the EventData
    """

    name: str
    table_name: str
    source: DatabaseSource
    event_timestamp_column: str
    record_creation_date_column: Optional[str]
    default_feature_job_setting: Optional[FeatureJobSetting]
    created_at: datetime
    history: List[FeatureJobSettingHistoryEntry]
    status: EventDataStatus