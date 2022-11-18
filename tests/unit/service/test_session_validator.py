"""
Test session validator class
"""
from unittest.mock import AsyncMock, patch

import pytest

from featurebyte import FeatureStore, SnowflakeDetails, SourceType
from featurebyte.app import User
from featurebyte.exception import FeatureStoreSchemaCollisionError, NoFeatureStorePresentError
from featurebyte.models.base import PydanticObjectId
from featurebyte.service.session_validator import SessionValidatorService, ValidateStatus


@pytest.fixture(name="session_validator_service")
def get_session_validator_service_fixture(persistent):
    """
    Fixture to get a session validator service
    """
    user = User()
    return SessionValidatorService(user=user, persistent=persistent)


@pytest.fixture(name="test_snowflake_details")
def get_test_snowflake_details():
    """
    Get test snowflake details
    """
    return SnowflakeDetails(
        account="sf_details_account",
        warehouse="sf_details_warehouse",
        database="sf_details_database",
        sf_schema="sf_details_schema",
    )


@pytest.mark.asyncio
async def test_get_feature_store_id_from_details(session_validator_service, test_snowflake_details):
    """
    Test getting feature store ID from details
    """
    feature_store_id = await session_validator_service.get_feature_store_id_from_details(
        test_snowflake_details
    )
    assert feature_store_id is None

    # Write details to persistent layer
    feature_store = FeatureStore.create(
        name="test_feature_name", source_type=SourceType.SNOWFLAKE, details=test_snowflake_details
    )
    assert isinstance(feature_store, FeatureStore)

    # Check that we can retrieve the feature store ID
    feature_store_id = await session_validator_service.get_feature_store_id_from_details(
        test_snowflake_details
    )
    assert feature_store_id is not None
    assert feature_store_id == feature_store.id


@pytest.fixture(name="mock_session")
def get_mock_session():
    """
    Mock out session
    """
    with patch("featurebyte.session.base.BaseSession") as mock_session:
        yield mock_session


@pytest.mark.asyncio
async def test_validate_existing_session(session_validator_service, mock_session):
    """
    Test validate existing function
    """
    mock_session.get_working_schema_metadata = AsyncMock()
    mock_session.get_working_schema_metadata.return_value = {
        "feature_store_id": "",
    }
    validate_status = await session_validator_service.validate_existing_session(mock_session, None)
    assert validate_status == ValidateStatus.NOT_IN_DWH

    object_id = PydanticObjectId("631b00277280fc9aa9522789")
    mock_session.get_working_schema_metadata.return_value = {
        "feature_store_id": object_id,
    }
    validate_status = await session_validator_service.validate_existing_session(
        mock_session, object_id
    )
    assert validate_status == ValidateStatus.FEATURE_STORE_ID_MATCHES

    mock_session.get_working_schema_metadata.return_value = {
        "feature_store_id": PydanticObjectId("631b00277280fc9aa9522788"),
    }
    with pytest.raises(FeatureStoreSchemaCollisionError):
        _ = await session_validator_service.validate_existing_session(mock_session, object_id)


@pytest.fixture(name="noop_session_validator", autouse=True)
def get_noop_session_validator_fixture():
    """
    Override the default noop_session_validator to not patch with an empty validation since we want to actually
    test the behaviour of the validator here.
    """
    return


@pytest.mark.asyncio
async def test_validate_feature_store_exists(session_validator_service, test_snowflake_details):
    """
    Test validate_feature_store_exists function
    """
    with pytest.raises(NoFeatureStorePresentError):
        await session_validator_service.validate_feature_store_exists(test_snowflake_details)

    # Write details to persistent layer
    feature_store = FeatureStore.create(
        name="test_feature_name", source_type=SourceType.SNOWFLAKE, details=test_snowflake_details
    )
    assert isinstance(feature_store, FeatureStore)

    # Calling validate now shouldn't throw an error
    await session_validator_service.validate_feature_store_exists(test_snowflake_details)
