"""
Perform database migration
"""
import asyncio

from featurebyte.app import User
from featurebyte.logger import logger
from featurebyte.migration.run import run_migration
from featurebyte.utils.credential import MongoBackedCredentialProvider
from featurebyte.utils.persistent import get_persistent

if __name__ == "__main__":
    logger.info("Running database migration")
    credential_provider = MongoBackedCredentialProvider(persistent=get_persistent())
    asyncio.run(
        run_migration(user=User(), persistent=get_persistent(), get_credential=credential_provider.get_credential)
    )

    logger.info("Database migration completed")