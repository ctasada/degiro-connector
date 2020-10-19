import json
import logging
import requests
import time
import urllib3

from quotecast.constants import Endpoint, Headers
from quotecast.pb.quotecast_pb2 import (
    Action,
    Metadata,
    RawResponse,
    SubscriptionRequest
)
from typing import List


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# pylint: disable=no-member

def build_session(headers:dict=None) -> requests.Session:
    """ Setup a requests.Session object.

    Arguments:
    headers {dict} -- Headers to used for the Session.

    Returns:
    {requests.Session} -- Session object with the right headers.
    """

    session = requests.Session()

    if isinstance(headers, dict) :
        session.headers.update(headers)
    else:
        session.headers.update(Headers.get_headers())

    return session

def build_logger():
    return logging.getLogger(__name__)

def get_session_id(
        user_token:int,
        session:requests.Session=None,
        logger:logging.Logger=None
    )->str:
    """ Retrieve "session_id".
    This "session_id" is used by most Degiro's trading endpoint.

    Returns:
        str -- Session id
    """

    if logger is None:
        logger = build_logger()
    if session is None:
        session = build_session()
    
    url = Endpoint.URL
    url = f'{url}/request_session'
    version = Endpoint.VERSION
    
    parameters = {'version': version, 'userToken': user_token}
    data = '{"referrer":"https://trader.degiro.nl"}'

    request = requests.Request(
        method='POST',
        url=url,
        data=data,
        params=parameters
    )
    prepped = session.prepare_request(request)

    try:
        response = session.send(prepped, verify=False)
        response_dict = response.json()
    except Exception as e:
        logger.fatal(e)
        return False
    
    logger.info('get_session_id:response_dict: %s', response_dict)

    if 'sessionId' in response_dict:
        return response_dict['sessionId']
    else:
        return None

def fetch_data(
        session_id:str,
        session:requests.Session=None,
        logger:logging.Logger=None
    )->RawResponse:
    """
    Fetch data from the feed.

    Parameters :
    session_id {str} -- API's session id.

    Returns :
    dict
        response : JSON encoded string fetched from this endpoint.
        response_datetime : Datetime at which we received the response.
        request_duration : Duration of the request.
    """

    if logger is None:
        logger = build_logger()
    if session is None:
        session = build_session()
    
    url = Endpoint.URL
    url = f'{url}/{session_id}'

    request = requests.Request(method='GET', url=url)
    prepped = session.prepare_request(request)

    start = time.time()
    response = session.send(prepped, verify=False)
    # We could also use : response.elapsed.total_seconds()
    request_duration = time.time() - start 

    if response.text == '[{"m":"sr"}]' :
        raise BrokenPipeError('A new "session_id" is required.')

    # There are no "date" header returned
    # We use the date generated by "requests" library
    response_datetime = time.strftime(
        '%Y-%m-%d %H:%M:%S',
        time.localtime(response.cookies._now)
    )

    metadata = Metadata(
        response_datetime=response_datetime,
        request_duration=request_duration
    )
    raw_response = RawResponse(
        response_json=response.text,
        metadata=metadata
    )

    logger.debug(
        'fetch_data:raw_response.response_json: %s',
        raw_response.response_json
    )
    logger.debug(
        'fetch_data:raw_response.response_datetime: %s',
        metadata.response_datetime
    )
    logger.debug(
        'fetch_data:raw_response.request_duration: %s',
        metadata.request_duration
    )

    return raw_response

def subscribe(
        subscription_request:SubscriptionRequest,
        session_id:str,
        session:requests.Session=None,
        logger:logging.Logger=None
    )->bool:
    """ Subscribe/unsubscribe to a feed from Degiro's QuoteCast API.
    Parameters :
    session_id {str} -- API's session id.

    Returns :
    {bool} -- Whether or not the subscription succeeded.
    """

    if logger is None:
        logger = build_logger()
    if session is None:
        session = build_session()
    
    url = Endpoint.URL
    url = f'{url}/{session_id}'

    if subscription_request.action == Action.SUBSCRIBE:
        action = 'req'
    elif subscription_request.action == Action.UNSUBSCRIBE:
        action = 'rel'
    else:
        raise AttributeError('Unknown "Request.action".')
    
    data = list()
    for label in subscription_request.label_list:
        data.append(f'{action}({subscription_request.product_id}.{label})')
    data = '{"controlData":"' + ';'.join(data) + ';"}'

    request = requests.Request(method='POST', url=url, data=data)
    prepped = session.prepare_request(request)

    logger.info('subscribe:payload: %s', data)
    
    try:
        response = session.send(prepped, verify=False)
    except Exception as e:
        logger.fatal(e)
        return False

    logger.debug(
        'subscribe:response.text: %s',
        response.text
    )
    logger.debug(
        'subscribe:response.status_code: %s',
        response.status_code
    )

    return response.status_code == 200