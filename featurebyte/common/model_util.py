"""
This module contains the implementation of feature job setting validation
"""
from __future__ import annotations

from typing import Any, Tuple

from datetime import datetime

import pandas as pd
from typeguard import typechecked


def parse_duration_string(duration_string: str, minimum_seconds: int = 0) -> int:
    """Check whether the string is a valid duration

    Parameters
    ----------
    duration_string : str
        String to validate
    minimum_seconds : int
        Validate that the duration has at least this number of seconds

    Returns
    -------
    int
        Number of seconds converted from the duration string

    Raises
    ------
    ValueError
        If the specified duration is invalid
    """
    duration = pd.Timedelta(duration_string)
    duration_total_seconds = int(duration.total_seconds())
    if duration_total_seconds < minimum_seconds:
        raise ValueError(f"Duration specified is too small: {duration_string}")
    return duration_total_seconds


@typechecked
def validate_job_setting_parameters(
    frequency: str, time_modulo_frequency: str, blind_spot: str
) -> Tuple[int, int, int]:
    """Validate that job setting parameters are correct

    Parameters
    ----------
    frequency: str
        frequency of the feature job
    time_modulo_frequency: str
        offset of when the feature job will be run, should be smaller than frequency
    blind_spot: str
        historical gap introduced to the aggregation

    Returns
    -------
    tuple
        Result of the parsed duration strings

    Raises
    ------
    ValueError
        If the specified job setting parameters are invalid
    """
    frequency_seconds = parse_duration_string(frequency, minimum_seconds=60)
    time_modulo_frequency_seconds = parse_duration_string(time_modulo_frequency)
    blind_spot_seconds = parse_duration_string(blind_spot)

    if time_modulo_frequency_seconds >= frequency_seconds:
        raise ValueError(
            f"Time modulo frequency ({time_modulo_frequency}) should be smaller than frequency"
            f" ({frequency})"
        )
    return frequency_seconds, time_modulo_frequency_seconds, blind_spot_seconds


def get_version() -> str:
    """
    Construct version name given feature or featurelist name

    Returns
    -------
    str
        Version name
    """
    creation_date = datetime.today().strftime("%y%m%d")
    return f"V{creation_date}"


def convert_version_string_to_dict(version: str) -> dict[str, Any]:
    """
    Convert version string to dictionary format

    Parameters
    ----------
    version: str
        Version string value

    Returns
    -------
    dict[str, Any]
    """
    name = version
    suffix = None
    if "_" in version:
        name, suffix_str = version.rsplit("_", 1)
        suffix = int(suffix_str) if suffix_str else None
    return {"name": name, "suffix": suffix}
