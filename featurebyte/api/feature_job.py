"""
FeatureJobMixin class
"""
from typing import Any, Dict, List, Tuple

import base64
import datetime
import textwrap
from abc import abstractmethod
from http import HTTPStatus
from io import BytesIO

import humanize
import numpy as np
import pandas as pd
from typeguard import typechecked

from featurebyte.api.api_object import ApiObject
from featurebyte.common.date_util import get_next_job_datetime
from featurebyte.common.utils import dataframe_from_json
from featurebyte.config import Configurations
from featurebyte.exception import RecordRetrievalException
from featurebyte.logger import logger
from featurebyte.models.base import FeatureByteBaseModel, PydanticObjectId
from featurebyte.models.tile import TileSpec


class FeatureJobStatusResult(FeatureByteBaseModel):
    """
    FeatureJobStatusResult class
    """

    request_date: datetime.datetime
    job_history_window: int
    job_duration_tolerance: int
    feature_tile_table: pd.DataFrame
    feature_job_summary: pd.DataFrame
    job_session_logs: pd.DataFrame

    class Config:
        """
        Config for pydantic model
        """

        arbitrary_types_allowed: bool = True

    @property
    def request_parameters(self) -> Dict[str, Any]:
        """
        Parameters used to make the status request

        Returns
        -------
        Dict[str, Any]
        """
        return {
            "request_date": self.request_date.isoformat(),
            "job_history_window": self.job_history_window,
            "job_duration_tolerance": self.job_duration_tolerance,
        }

    def __str__(self) -> str:
        return "\n\n".join(
            [
                str(pd.DataFrame.from_dict([self.request_parameters])),
                str(self.feature_tile_table),
                str(self.feature_job_summary),
            ]
        )

    def __repr__(self) -> str:
        return str(self)

    def _repr_html_(self) -> str:
        try:
            # pylint: disable=import-outside-toplevel
            from matplotlib import pyplot as plt

            # plot job time distribution
            fig = plt.figure(figsize=(15, 3))
            plt.hist(self.job_session_logs.COMPLETED, bins=self.job_history_window, rwidth=0.7)
            plt.title("Job distribution over time")
            plt.axvline(x=self.request_date, color="red")
            buffer = BytesIO()
            fig.savefig(buffer, format="png", metadata={"Software": None})
            image_1 = base64.b64encode(buffer.getvalue()).decode("utf-8")
            plt.close()

            # plot job duration distributions
            late_pct = self.job_session_logs["IS_LATE"].sum() / self.job_session_logs.shape[0] * 100
            fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(20, 5))
            ax1.set_title(f"Job duration ({late_pct:.2f}% exceeds threshold)")
            ax1.set_xlabel("Duration in seconds")
            ax1.set_ylabel("Job count")
            ax1.hist(self.job_session_logs.TOTAL_DURATION, rwidth=0.7)
            ax1.axvline(x=self.job_duration_tolerance, color="red")

            ax2.set_title("Queue duration")
            ax2.set_xlabel("Queue duration in seconds")
            ax2.set_ylabel("Job count")
            ax2.hist(self.job_session_logs.QUEUE_DURATION, rwidth=0.7)

            ax3.set_title("Compute duration")
            ax3.set_xlabel("Compute duration in seconds")
            ax3.set_ylabel("Job count")
            ax3.hist(self.job_session_logs.COMPUTE_DURATION, rwidth=0.7)
            buffer = BytesIO()
            fig.savefig(buffer, format="png", metadata={"Software": None})
            image_2 = base64.b64encode(buffer.getvalue()).decode("utf-8")
            fig.savefig(buffer, format="png", metadata={"Software": None})
            plt.close()
        except ModuleNotFoundError:
            logger.warning("matplotlib not installed, skipping job status plots.")

        return textwrap.dedent(
            f"""
        <div>
            <h1>Job statistics (last {self.job_history_window} hours)</h1>
            {pd.DataFrame.from_dict([self.request_parameters]).to_html()}
            {self.feature_tile_table.to_html()}
            {self.feature_job_summary.to_html()}
            <img src="data:image/png;base64,{image_1}">
            <img src="data:image/png;base64,{image_2}">
        </div>
        """
        ).strip()


class FeatureJobMixin(ApiObject):
    """
    FeatureJobMixin implement feature job management functionality
    """

    id: PydanticObjectId

    @abstractmethod
    def _get_feature_tiles_specs(self) -> List[Tuple[str, List[TileSpec]]]:
        """
        Get dictionary of feature and tile specs

        Returns
        -------
        List[Tuple[str, List[TileSpec]]]
        """

    @staticmethod
    def _compute_feature_jobs_summary(
        logs: pd.DataFrame,
        feature_tile_specs: pd.DataFrame,
        job_history_window: int,
        job_duration_tolerance: int,
    ) -> FeatureJobStatusResult:
        """
        Display summary statistics and charts on feature jobs

        Parameters
        ----------
        logs: pd.DataFrame
            Log records
        feature_tile_specs: pd.DataFrame,
            Feature and tile specs table
        job_history_window: int
            History window in hours
        job_duration_tolerance: int
            Threshold for job delays in seconds

        Returns
        -------
        FeatureJobStatusResult
        """
        utc_now = datetime.datetime.utcnow()

        # identify jobs with duration that exceeds job period
        logs = logs.merge(
            feature_tile_specs[["tile_id", "frequency_minute"]].drop_duplicates(),
            on="tile_id",
            how="left",
        )
        logs["PERIOD"] = logs["frequency_minute"] * 60
        logs["EXCEED_PERIOD"] = logs["TOTAL_DURATION"] > logs["PERIOD"]

        # feature tile table
        feature_tile_table = (
            feature_tile_specs[["feature_name", "tile_hash"]]
            .sort_values("feature_name")
            .reset_index(drop=True)
        )

        # summarize by tiles
        stats = (
            logs.groupby("tile_id", group_keys=True)
            .agg(
                completed_jobs=("COMPLETED", "count"),
                max_duration=("TOTAL_DURATION", "max"),
                percentile_95=("TOTAL_DURATION", lambda x: x.quantile(0.95)),
                frac_late=("IS_LATE", "sum"),
                last_completed=("COMPLETED", "max"),
                exceed_period=("EXCEED_PERIOD", "sum"),
            )
            .reset_index()
        )
        feature_stats = (
            feature_tile_specs[
                [
                    "tile_hash",
                    "frequency_minute",
                    "time_modulo_frequency_second",
                    "tile_id",
                ]
            ]
            .drop_duplicates("tile_id")
            .merge(stats, on="tile_id", how="left")
        )

        # compute expected number of jobs
        feature_stats["expected_jobs"] = 0
        last_job_times = feature_stats.apply(
            lambda row: get_next_job_datetime(
                utc_now, row.frequency_minute, row.time_modulo_frequency_second
            ),
            axis=1,
        ) - pd.to_timedelta(feature_stats.frequency_minute, unit="minute")
        window_start = utc_now - datetime.timedelta(hours=job_history_window)
        last_job_expected_to_complete_in_window = (
            (utc_now - last_job_times).dt.total_seconds() > job_duration_tolerance
        ) & (last_job_times > window_start)
        feature_stats.loc[last_job_expected_to_complete_in_window, "expected_jobs"] = 1

        window_size = np.maximum((last_job_times - window_start).dt.total_seconds(), 0)
        feature_stats["expected_jobs"] += np.floor(
            window_size / feature_stats["frequency_minute"] / 60
        ).astype(int)

        # default values for tiles without job records
        mask = feature_stats["last_completed"].isnull()
        if mask.any():
            feature_stats.loc[mask, "completed_jobs"] = 0
            feature_stats.loc[mask, "exceed_period"] = 0
            feature_stats["completed_jobs"] = feature_stats["completed_jobs"].astype(int)
            feature_stats["exceed_period"] = feature_stats["exceed_period"].astype(int)
            feature_stats.loc[mask, "last_completed"] = pd.NaT

        feature_stats["frac_late"] = feature_stats["frac_late"] / feature_stats["completed_jobs"]
        feature_stats.loc[feature_stats["completed_jobs"] == 0, "frac_late"] = np.nan
        feature_stats["failed_jobs"] = (
            # missing / incomplete + job duration exceed period
            feature_stats["expected_jobs"]
            - feature_stats["completed_jobs"]
            + feature_stats["exceed_period"]
        )
        feature_stats.loc[feature_stats["last_completed"].isnull(), "last_completed"] = pd.NaT
        feature_stats["time_since_last"] = (utc_now - feature_stats["last_completed"]).apply(
            humanize.naturaldelta
        )
        feature_stats = feature_stats.drop(
            ["tile_id", "time_modulo_frequency_second", "expected_jobs", "last_completed"],
            axis=1,
        ).rename(
            {
                "frequency_minute": "frequency(min)",
                "max_duration": "max_duration(s)",
                "percentile_95": "95 percentile",
            },
            axis=1,
        )

        return FeatureJobStatusResult(
            request_date=utc_now,
            job_history_window=job_history_window,
            job_duration_tolerance=job_duration_tolerance,
            feature_tile_table=feature_tile_table,
            feature_job_summary=feature_stats,
            job_session_logs=logs.drop(["SESSION_ID", "tile_id", "frequency_minute"], axis=1)
            .sort_values("STARTED", ascending=False)
            .reset_index(drop=True),
        )

    @typechecked
    def get_feature_jobs_status(
        self,
        job_history_window: int = 1,
        job_duration_tolerance: int = 60,
    ) -> FeatureJobStatusResult:
        """
        Get FeatureList feature jobs status

        Parameters
        ----------
        job_history_window: int
            History window in hours
        job_duration_tolerance: int
            Maximum duration before job is considered later

        Returns
        -------
        FeatureJobStatusResult

        Raises
        ------
        RecordRetrievalException
            Preview request failed
        """
        client = Configurations().get_client()
        response = client.get(
            url=f"{self._route}/{self.id}/feature_job_logs?hour_limit={job_history_window}"
        )
        if response.status_code != HTTPStatus.OK:
            raise RecordRetrievalException(response)
        result = response.json()
        logs = dataframe_from_json(result)

        # Compute short tile hash
        log_columns = logs.columns.to_list()  # pylint: disable=no-member
        logs["TILE_HASH"] = logs["tile_id"].apply(lambda x: x.split("_")[-1][:8])
        logs = logs[["TILE_HASH"] + log_columns]
        logs["IS_LATE"] = logs["TOTAL_DURATION"] > job_duration_tolerance

        # get feature tilespecs information
        feature_tile_specs = self._get_feature_tiles_specs()
        tile_specs = []
        for (feature_name, tile_spec_list) in feature_tile_specs:
            data = []
            for tile_spec in tile_spec_list:
                tile_hash = tile_spec.tile_id.split("_")[-1][:8]
                data.append(
                    dict(**tile_spec.dict(), tile_hash=tile_hash, feature_name=feature_name)
                )
            tile_specs.append(pd.DataFrame.from_dict(data))
        feature_tile_specs_df = pd.concat(tile_specs)

        return self._compute_feature_jobs_summary(
            logs=logs,
            feature_tile_specs=feature_tile_specs_df,
            job_history_window=job_history_window,
            job_duration_tolerance=job_duration_tolerance,
        )