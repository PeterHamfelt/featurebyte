"""
Test MongoDB persistent backend
"""
from typing import Any, Dict, List, Tuple

import mongomock
import pymongo
import pytest
from bson import ObjectId

from featurebyte.persistent.mongo import MongoDB


@pytest.fixture(name="mongo_persistent")
def mongo_persistent_fixture() -> Tuple[MongoDB, pymongo.MongoClient]:
    """
    Patched MongoDB fixture for testing

    Returns
    -------
    Tuple[MongoDB, pymongo.MongoClient]
        Patched MongoDB object and MongoClient
    """
    with mongomock.patch(servers=(("server.example.com", 27017),)):
        persistent = MongoDB(uri="mongodb://server.example.com:27017", database="test")
        mongo_client = pymongo.MongoClient("mongodb://server.example.com:27017")
        return persistent, mongo_client


@pytest.fixture(name="test_document")
def test_document_fixture() -> Dict[str, Any]:
    """
    Test document to be used for testing

    Returns
    -------
    Dict[str, Any]
        Document for testing
    """
    return {
        "id": ObjectId(),
        "name": "Generic Document",
        "value": [
            {
                "key1": "value1",
                "key2": "value2",
            }
        ],
    }


@pytest.fixture(name="test_documents")
def test_documents_fixture(test_document) -> List[Dict[str, Any]]:
    """
    Test documents to be used for testing

    Returns
    -------
    List[Dict[str, Any]]
        Document for testing
    """
    return [{**test_document, **{"id": ObjectId()}} for _ in range(3)]


def test_insert_one(mongo_persistent, test_document):
    """
    Test inserting one document
    """
    persistent, client = mongo_persistent
    persistent.insert_one(collection_name="data", document=test_document)
    # check document is inserted
    results = list(client["test"]["data"].find({}))
    assert results[0] == test_document


def test_insert_many(mongo_persistent, test_documents):
    """
    Test inserting many documents
    """
    persistent, client = mongo_persistent
    persistent.insert_many(collection_name="data", documents=test_documents)
    # check documents are inserted
    assert list(client["test"]["data"].find({})) == test_documents


def test_find_one(mongo_persistent, test_documents):
    """
    Test finding one document
    """
    persistent, client = mongo_persistent
    client["test"]["data"].insert_many(test_documents)
    doc = persistent.find_one(collection_name="data", filter_query={})
    assert doc == test_documents[0]


def test_find_many(mongo_persistent, test_documents):
    """
    Test finding many documents
    """
    persistent, client = mongo_persistent
    client["test"]["data"].insert_many(test_documents)
    docs, total = persistent.find(collection_name="data", filter_query={})
    assert list(docs) == test_documents
    assert total == 3

    # test pagination
    docs, total = persistent.find(collection_name="data", filter_query={}, page_size=2, page=1)
    assert list(docs) == test_documents[:2]
    assert total == 3
    docs, total = persistent.find(collection_name="data", filter_query={}, page_size=2, page=2)
    assert list(docs) == test_documents[2:]
    assert total == 3
    docs, total = persistent.find(collection_name="data", filter_query={}, page_size=0, page=2)
    assert list(docs) == test_documents
    assert total == 3

    # test sort
    docs, total = persistent.find(
        collection_name="data", filter_query={}, sort_by="id", sort_dir="desc"
    )
    assert list(docs) == test_documents[-1::-1]
    assert total == 3


def test_update_one(mongo_persistent, test_document, test_documents):
    """
    Test updating one document
    """
    persistent, client = mongo_persistent
    test_documents = [{**test_document, **{"id": ObjectId()}} for _ in range(3)]
    client["test"]["data"].insert_many(test_documents)
    result = persistent.update_one(
        collection_name="data", filter_query={}, update={"$set": {"value": 1}}
    )

    assert result == 1
    results = list(client["test"]["data"].find({}))

    # only first document should be updated
    assert results[0]["value"] == 1
    assert results[1]["value"] == test_document["value"]
    assert results[2]["value"] == test_document["value"]


def test_update_many(mongo_persistent, test_documents):
    """
    Test updating one document
    """
    persistent, client = mongo_persistent
    client["test"]["data"].insert_many(test_documents)
    result = persistent.update_many(
        collection_name="data", filter_query={}, update={"$set": {"value": 1}}
    )
    # expect all documents to be updated
    assert result == 3
    results = client["test"]["data"].find({})
    for result in results:
        assert result["value"] == 1


def test_delete_one(mongo_persistent, test_documents):
    """
    Test deleting one document
    """
    persistent, client = mongo_persistent
    client["test"]["data"].insert_many(test_documents)
    result = persistent.delete_one(collection_name="data", filter_query={})
    # expect only one document to be deleted
    assert result == 1
    results = list(client["test"]["data"].find({}))
    assert len(results) == 2


def test_delete_many(mongo_persistent, test_documents):
    """
    Test deleting many documents
    """
    persistent, client = mongo_persistent
    client["test"]["data"].insert_many(test_documents)
    result = persistent.delete_many(collection_name="data", filter_query={})
    # expect all documents to be deleted
    assert result == 3
    results = list(client["test"]["data"].find({}))
    assert len(results) == 0