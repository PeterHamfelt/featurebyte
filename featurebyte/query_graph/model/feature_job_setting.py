"""
Feature Job Setting Model
"""
from typing import Any, Dict

from pydantic import root_validator

from featurebyte.common.doc_util import FBAutoDoc
from featurebyte.common.model_util import parse_duration_string, validate_job_setting_parameters
from featurebyte.models.base import FeatureByteBaseModel


class FeatureJobSetting(FeatureByteBaseModel):
    """
    FeatureJobSetting class is used to declare the Feature Job Setting.

    The setting comprises three parameters:

    - The frequency parameter specifies how often the batch process should run.
    - The time_modulo_frequency parameter defines the timing from the end of the frequency time period to when the
      feature job commences. For example, a feature job with the following settings (frequency 60m,
      time_modulo_frequency: 130s) will start 2 min and 10 seconds after the beginning of each hour:
      00:02:10, 01:02:10, 02:02:10, …, 15:02:10, …, 23:02:10.
    - The blind_spot parameter sets the time gap between feature computation and the latest event timestamp to be
    processed.

    Note that these parameters are the same duration type strings that pandas accepts in pd.Timedelta().

    Examples
    --------
    Configure a feature job to run daily at 12am

    >>> feature_job_setting = FeatureJobSetting( # doctest: +SKIP
    ...   blind_spot="0"
    ...   frequency="24h"
    ...   time_modulo_frequency="0"
    ... )

    Configure a feature job to run daily at 8am

    >>> feature_job_setting = FeatureJobSetting( # doctest: +SKIP
    ...   blind_spot="0"
    ...   frequency="24h"
    ...   time_modulo_frequency="8h"
    ... )
    """

    __fbautodoc__ = FBAutoDoc(proxy_class="featurebyte.FeatureJobSetting")

    blind_spot: str
    frequency: str
    time_modulo_frequency: str

    @root_validator(pre=True)
    @classmethod
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

    @property
    def frequency_seconds(self) -> int:
        """
        Get frequency in seconds

        Returns
        -------
        int
            frequency in seconds
        """
        return parse_duration_string(self.frequency, minimum_seconds=60)

    @property
    def time_modulo_frequency_seconds(self) -> int:
        """
        Get time modulo frequency in seconds

        Returns
        -------
        int
            time modulo frequency in seconds
        """
        return parse_duration_string(self.time_modulo_frequency)

    @property
    def blind_spot_seconds(self) -> int:
        """
        Get blind spot in seconds

        Returns
        -------
        int
            blind spot in seconds
        """
        return parse_duration_string(self.blind_spot)

    def to_seconds(self) -> Dict[str, Any]:
        """Convert job settings format using seconds as time unit

        Returns
        -------
        Dict[str, Any]
        """
        return {
            "frequency": self.frequency_seconds,
            "time_modulo_frequency": self.time_modulo_frequency_seconds,
            "blind_spot": self.blind_spot_seconds,
        }

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, FeatureJobSetting):
            return NotImplemented
        return self.to_seconds() == other.to_seconds()


class TableFeatureJobSetting(FeatureByteBaseModel):
    """
    The TableFeatureJobSetting object serves as a link between a table and a specific feature job setting configuration.
    It is utilized when creating a new version of a feature that requires different configurations for feature job
    settings. The table_feature_job_settings parameter takes a list of these configurations. For each configuration,
    the TableFeatureJobSetting object establishes the relationship between the table involved and the corresponding
    feature job setting.
    """

    __fbautodoc__ = FBAutoDoc(proxy_class="featurebyte.TableFeatureJobSetting")

    table_name: str
    feature_job_setting: FeatureJobSetting
