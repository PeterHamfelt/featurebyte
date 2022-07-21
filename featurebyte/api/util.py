"""
This module contains utility function used in api directory
"""
from __future__ import annotations

from typing import Any, Type

from http import HTTPStatus

from requests.models import Response

from featurebyte.config import Configurations
from featurebyte.exception import RecordRetrievalException, ResponseException


def _get_response(
    response: Response, response_exception_class: Type[ResponseException], success_status_code: int
) -> dict[str, Any]:
    """
    Retrieve response data into a dictionary

    Parameters
    ----------
    response: Response
        API response
    response_exception_class: type
        ResponseException class for response failure
    success_status_code: int
        HTTP status code for success case

    Returns
    -------
    dict[str, Any]
        Response in dictionary format

    Raises
    ------
    response_exception_class
        When unexpected failure to create/retrieve/update resource
    """
    if response.status_code == success_status_code:
        response_dict: dict[str, Any] = response.json()
        return response_dict
    raise response_exception_class(response)


def get_entity(entity_name: str) -> dict[str, Any]:
    """
    Get entity dictionary given entity name

    Parameters
    ----------
    entity_name: str
        Entity name

    Returns
    -------
    dict[str, Any]
        Entity dictionary object if found

    Raises
    ------
    RecordRetrievalException
        When the given entity name is not found
    """
    client = Configurations().get_client()
    response = client.get(url="/entity", params={"name": entity_name})
    if response.status_code == HTTPStatus.OK:
        response_dict: dict[str, Any] = _get_response(
            response=response,
            response_exception_class=RecordRetrievalException,
            success_status_code=HTTPStatus.OK,
        )
        response_data = response_dict["data"]
        if len(response_data):
            first_item: dict[str, Any] = response_data[0]
            return first_item
    raise RecordRetrievalException(response, f'Entity name "{entity_name}" not found!')


def get_entity_by_id(entity_id: str) -> dict[str, Any]:
    """
    Get entity dictionary given entity ID

    Parameters
    ----------
    entity_id: str
        Entity ID

    Returns
    -------
    dict[str, Any]
        Entity dictionary object if found

    Raises
    ------
    RecordRetrievalException
        When the given entity ID is not found
    """
    client = Configurations().get_client()
    response = client.get(url=f"/entity/{entity_id}")
    if response.status_code == HTTPStatus.OK:
        response_dict: dict[str, Any] = _get_response(
            response=response,
            response_exception_class=RecordRetrievalException,
            success_status_code=HTTPStatus.OK,
        )
        return response_dict
    raise RecordRetrievalException(response, f'Entity id "{entity_id}" not found!')
