"""
Pytest configuration file for doctest
"""
import pandas
import pytest

import featurebyte


@pytest.fixture(autouse=True)
def add_imports(doctest_namespace):
    """
    Add default imports to doctest namespace
    """
    doctest_namespace["fb"] = featurebyte
    doctest_namespace["pd"] = pandas

    # get entity id
    grocery_customer_entity = featurebyte.Entity.get("grocerycustomer")
    doctest_namespace["grocery_customer_entity_id"] = grocery_customer_entity.id

    # get feature id
    feature = featurebyte.Feature.get("InvoiceCount_60days")
    doctest_namespace["invoice_count_60_days_feature_id"] = feature.id


@pytest.fixture(autouse=True)
def activate_playground_catalog():
    """
    Activate the playground catalog automatically
    """
    featurebyte.Catalog.activate("grocery")
