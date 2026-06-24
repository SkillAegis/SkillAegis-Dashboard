#!/usr/bin/env python3

import json
import re
from typing import Union

from backend.appConfig import logger
from backend.utils import apply_replacement_from_context
import backend.db as db
import backend.misp_api as misp_api

from backend.target_tools.misp.inject_eval import eval_data_filtering, eval_query_mirror, eval_query_search, eval_python


def is_valid_evaluation_context(user_id: int, inject_evaluation: dict, data: dict, context: dict) -> bool:
    if 'evaluation_context' not in inject_evaluation or len(inject_evaluation['evaluation_context']) == 0:
        return True
    if 'request_is_rest' in inject_evaluation['evaluation_context']:
        if 'request_is_rest' in context:
            if inject_evaluation['evaluation_context']['request_is_rest'] == context['request_is_rest']:
                return True
            else:
                logger.debug('Request type does not match state of `request_is_rest`')
                return False
        else:
            logger.debug('Unknown request type')
            return False
    return True


async def inject_checker_router(user_id: int, inject_evaluation: dict, data: dict, context: dict) -> bool:
    if not is_valid_evaluation_context(user_id, inject_evaluation, data, context):
        return False

    if 'evaluation_strategy' not in inject_evaluation:
        logger.warning('Evaluation strategy not specified in inject')
        return False

    data_to_validate = await get_data_to_validate(user_id, inject_evaluation, data, context)
    if data_to_validate is None:
        logger.debug('Could not fetch data to validate')
        return False

    if inject_evaluation['evaluation_strategy'] == 'data_filtering':
        return eval_data_filtering(user_id, inject_evaluation, data_to_validate, context)
    elif inject_evaluation['evaluation_strategy'] == 'query_mirror':
        expected_data = data_to_validate['expected_data']
        data_to_validate = data_to_validate['data_to_validate']
        return eval_query_mirror(user_id, expected_data, data_to_validate, context)
    elif inject_evaluation['evaluation_strategy'] == 'query_search':
        return eval_query_search(user_id, inject_evaluation, data_to_validate, context)
    elif inject_evaluation['evaluation_strategy'] == 'python':
        return eval_python(user_id, inject_evaluation, data_to_validate, context)
    return False


async def get_data_to_validate(user_id: int, inject_evaluation: dict, data: dict, context: dict = {}) -> Union[dict, list, str, None]:
    data_to_validate = None
    if inject_evaluation['evaluation_strategy'] == 'data_filtering':
        event_id = parse_event_id_from_log(data)
        data_to_validate = await fetch_data_for_data_filtering(event_id=event_id)
    elif inject_evaluation['evaluation_strategy'] == 'query_mirror':
        perfomed_query = parse_performed_query_from_log(data)
        data_to_validate = await fetch_data_for_query_mirror(user_id, inject_evaluation, perfomed_query)
    elif inject_evaluation['evaluation_strategy'] == 'query_search':
        data_to_validate = await fetch_data_for_query_search(user_id, inject_evaluation, context)
    elif inject_evaluation['evaluation_strategy'] == 'python':
        data_to_validate = await fetch_data_for_query_search(user_id, inject_evaluation, context)
    return data_to_validate


def parse_event_id_from_log(data: dict) -> Union[int, None]:
    event_id_from_change_field_regex = r".*event_id \(.*\) => \((\d+)\).*"
    event_id_from_title_field_regex = r".*from Event \((\d+)\).*"
    if 'Log' in data:
        log = data['Log']
        if 'model' in log and 'model_id' in log and log['model'] == 'Event':
            return int(log['model_id'])
        if 'change' in log:
            event_id_search = re.search(event_id_from_change_field_regex, log['change'], re.IGNORECASE)
            if event_id_search is not None:
                event_id = event_id_search.group(1)
                return event_id
        if 'title' in log:
            event_id_search = re.search(event_id_from_title_field_regex, log['title'], re.IGNORECASE)
            if event_id_search is not None:
                event_id = event_id_search.group(1)
                return event_id
    elif 'AuditLog' in data:
        log = data['AuditLog']
        if 'model' in log and 'model_id' in log and log['model'] == 'Event':
            return int(log['model_id'])
        if 'change' in log:
            if 'event_id' in log and log['event_id'] is not None:
                return int(log['event_id'])
    return None


def get_model_action(data: dict):
    if 'Log' in data or 'AuditLog' in data:
        data = data['Log'] if 'Log' in data else data['AuditLog']
        if 'model' in data and 'action' in data:
            return (data['model'], data['action'],)
    return (None, None,)


def is_accepted_query(data: dict) -> bool:
    model, action = get_model_action(data)
    if model in ['Event', 'Attribute', 'Object', 'Tag', ]:
        if action in ['add', 'edit', 'delete', 'publish', 'tag', ]:
            if 'Log' in data:
                if data['Log']['change'].startswith('Validation errors:'):
                    return False
            return True

    if data.get('user_agent', None) == 'SkillAegis':
        return None
    url = data.get('url', None)
    if url is not None:
        return url in [
            '/attributes/restSearch',
            '/events/restSearch',
            '/events/view',
            '/events/index',
            '/users/view/me',
        ]
    return False


def parse_performed_query_from_log(data: dict) -> Union[dict, None]:
    performed_query = {
        'request_method': '',
        'url': '',
        'payload': {},
    }
    if 'request' in data:
        request = data['request']
        performed_query['request_method'] = data.get('request_method', None)
        performed_query['url'] = data.get('url', None)
        if request.startswith('application/json\n\n'):
            query_raw = request.replace('application/json\n\n', '')
            try:
                payload = json.loads(query_raw)
                performed_query['payload'] = payload
            except:
                pass
        if performed_query['request_method'] is not None and performed_query['url'] is not None:
            return performed_query 
    else: # No data POSTed
        performed_query['request_method'] = data.get('request_method', None)
        performed_query['url'] = data.get('url', None)
        return performed_query
    return None


async def fetch_data_for_data_filtering(event_id=None) -> Union[None, dict]:
    data = None
    if event_id is not None:
        data = await misp_api.getEvent(event_id)
    return data


async def get_api_key_or_gen_new_one(user_id: int) -> str:
    authkey = db.USER_ID_TO_AUTHKEY_MAPPING.get(user_id, None)
    if authkey is None:
        logger.info(f'User[{user_id}] Authkey unknown. Creating a new one')
        authkey = await misp_api.genAPIKey(user_id)
        if authkey is not None:
            db.USER_ID_TO_AUTHKEY_MAPPING[user_id] = authkey
    return authkey


async def fetch_data_for_query_mirror(user_id: int, inject_evaluation: dict, perfomed_query: dict) -> Union[None, dict]:
    data = None
    authkey = await get_api_key_or_gen_new_one(user_id)
    if perfomed_query is not None:
        if 'evaluation_context' not in inject_evaluation and 'query_context' not in inject_evaluation['evaluation_context']:
            return None
        query_context = inject_evaluation['evaluation_context']['query_context']
        expected_method = query_context['request_method']
        expected_url = query_context['url']
        expected_payload = inject_evaluation['parameters'][0] if len(inject_evaluation['parameters']) > 0 else {}
        expected_data  = await misp_api.doRestQuery(authkey, expected_method, expected_url, expected_payload)
        data_to_validate  = await misp_api.doRestQuery(authkey, perfomed_query['request_method'], perfomed_query['url'], perfomed_query['payload'])
        data = {
            'expected_data' : expected_data,
            'data_to_validate' : data_to_validate,
        }
    return data


async def fetch_data_for_query_search(user_id: int, inject_evaluation: dict, context: dict = {}) -> Union[None, dict]:
    authkey = await get_api_key_or_gen_new_one(user_id)
    if 'evaluation_context' not in inject_evaluation and 'query_context' not in inject_evaluation['evaluation_context']:
        return None
    query_context = inject_evaluation['evaluation_context'].get('query_context', None)
    if query_context is None:
        logger.warning('Could not fetch data for query search. No query context provided.')
        return None
    try:
        replaced_context = apply_replacement_from_context(
            json.dumps(query_context),
            context
        )
        query_context = json.loads(replaced_context)
    except:
        pass
    search_method = query_context['request_method']
    search_url = query_context['url']
    search_payload = query_context.get('payload', {})
    search_data  = await misp_api.doRestQuery(authkey, search_method, search_url, search_payload)
    return search_data
