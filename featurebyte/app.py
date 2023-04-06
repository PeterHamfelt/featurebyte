"""
FastAPI Application
"""
from typing import Callable

import aioredis
import uvicorn
from bson import ObjectId
from fastapi import Depends, FastAPI, Request
from starlette.websockets import WebSocket

import featurebyte.routes.catalog.api as catalog_api
import featurebyte.routes.context.api as context_api
import featurebyte.routes.dimension_table.api as dimension_table_api
import featurebyte.routes.entity.api as entity_api
import featurebyte.routes.event_table.api as event_table_api
import featurebyte.routes.feature.api as feature_api
import featurebyte.routes.feature_job_setting_analysis.api as feature_job_setting_analysis_api
import featurebyte.routes.feature_list.api as feature_list_api
import featurebyte.routes.feature_list_namespace.api as feature_list_namespace_api
import featurebyte.routes.feature_namespace.api as feature_namespace_api
import featurebyte.routes.feature_store.api as feature_store_api
import featurebyte.routes.item_table.api as item_table_api
import featurebyte.routes.observation_table.api as observation_table_api
import featurebyte.routes.periodic_tasks.api as periodic_tasks_api
import featurebyte.routes.relationship_info.api as relationship_info_api
import featurebyte.routes.scd_table.api as scd_table_api
import featurebyte.routes.semantic.api as semantic_api
import featurebyte.routes.table.api as table_api
import featurebyte.routes.task.api as task_api
import featurebyte.routes.temp_data.api as temp_data_api
from featurebyte import Configurations
from featurebyte.common.utils import get_version
from featurebyte.logger import logger
from featurebyte.middleware import ExceptionMiddleware, TelemetryMiddleware
from featurebyte.models.base import DEFAULT_CATALOG_ID, User
from featurebyte.routes.app_container import AppContainer
from featurebyte.schema import APIServiceStatus
from featurebyte.schema.task import TaskId
from featurebyte.service.task_manager import TaskManager
from featurebyte.utils.credential import ConfigCredentialProvider
from featurebyte.utils.messaging import REDIS_URI
from featurebyte.utils.persistent import get_persistent
from featurebyte.utils.storage import get_storage, get_temp_storage


def _get_api_deps() -> Callable[[Request], None]:
    """
    Get API dependency injection function

    Returns
    -------
    Callable[Request]
        Dependency injection function
    """

    def _dep_injection_func(request: Request) -> None:
        """
        Inject dependencies into the requests

        Parameters
        ----------
        request: Request
            Request object to be updated
        """

        request.state.persistent = get_persistent()
        request.state.user = User()
        request.state.get_credential = ConfigCredentialProvider().get_credential
        request.state.get_storage = get_storage
        request.state.get_temp_storage = get_temp_storage
        catalog_id = ObjectId(request.query_params.get("catalog_id", DEFAULT_CATALOG_ID))
        request.state.app_container = AppContainer.get_instance(
            user=request.state.user,
            persistent=request.state.persistent,
            temp_storage=get_temp_storage(),
            task_manager=TaskManager(
                user=request.state.user,
                persistent=request.state.persistent,
                catalog_id=catalog_id,
            ),
            storage=get_storage(),
            container_id=catalog_id,
        )

    return _dep_injection_func


def get_app() -> FastAPI:
    """
    Get FastAPI object

    Returns
    -------
    FastAPI
        FastAPI object
    """
    _app = FastAPI()

    # add routers into the app
    resource_apis = [
        context_api,
        dimension_table_api,
        event_table_api,
        item_table_api,
        entity_api,
        feature_api,
        feature_job_setting_analysis_api,
        feature_list_api,
        feature_list_namespace_api,
        feature_namespace_api,
        feature_store_api,
        relationship_info_api,
        scd_table_api,
        semantic_api,
        table_api,
        task_api,
        temp_data_api,
        catalog_api,
        periodic_tasks_api,
        observation_table_api,
    ]
    dependencies = _get_api_deps()
    for resource_api in resource_apis:
        _app.include_router(
            resource_api.router,
            dependencies=[Depends(dependencies)],
            tags=[resource_api.router.prefix[1:]],
        )

    @_app.get("/status", description="Get API status.", response_model=APIServiceStatus)
    async def get_status() -> APIServiceStatus:
        """
        Service alive health check.

        Returns
        -------
        APIServiceStatus
            APIServiceStatus object.
        """
        return APIServiceStatus(sdk_version=get_version())

    @_app.websocket("/ws/{task_id}")
    async def websocket_endpoint(
        websocket: WebSocket,
        task_id: TaskId,
    ) -> None:
        """
        Websocket for getting task progress updates.

        Parameters
        ----------
        websocket: WebSocket
            Websocket object.
        task_id: TaskId
            Task ID.
        """
        await websocket.accept()
        user = User()
        channel = f"task_{user.id}_{task_id}_progress"

        logger.debug("Listening to channel", extra={"channel": channel})
        redis = await aioredis.from_url(REDIS_URI)
        sub = redis.pubsub()
        await sub.subscribe(channel)

        # listen for messages
        async for message in sub.listen():
            if message and isinstance(message, dict):
                data = message.get("data")
                if isinstance(data, bytes):
                    await websocket.send_bytes(data)

        # clean up
        logger.debug("Unsubscribing from channel", extra={"channel": channel})
        await sub.unsubscribe(channel)
        await sub.close()
        redis.close()

    config = Configurations()
    # Add telemetry middleware if enabled
    if config.logging.telemetry:
        _app.add_middleware(
            TelemetryMiddleware,
            endpoint=config.logging.telemetry_url,
            user_id=config.logging.telemetry_id,
            user_ip=config.logging.telemetry_ip,
        )

    # Add exception middleware
    _app.add_middleware(ExceptionMiddleware)

    return _app


app = get_app()


if __name__ == "__main__":
    # for debugging the api service
    uvicorn.run(app, host="127.0.0.1", port=8000)
