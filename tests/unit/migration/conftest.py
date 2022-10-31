"""
This module contains common fixtures used in tests/unit/migration directory
"""
from contextlib import asynccontextmanager
from unittest.mock import Mock, patch

import pytest
import pytest_asyncio
from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient

from featurebyte.persistent.mongo import MongoDB


@pytest.fixture(scope="session")
def user():
    """Mock user"""
    user = Mock()
    user.id = ObjectId()
    return user


@pytest_asyncio.fixture(name="persistent")
async def persistent_fixture():
    """Persistent fixture"""
    with patch("motor.motor_asyncio.AsyncIOMotorClient.__new__") as mock_new:
        mongo_client = AsyncMongoMockClient()
        mock_new.return_value = mongo_client
        persistent = MongoDB(uri="mongodb://server.example.com:27017", database="test")

        @asynccontextmanager
        async def start_transaction():
            yield persistent

        with patch.object(persistent, "start_transaction", start_transaction):
            yield persistent