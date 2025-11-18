#!/usr/bin/env python3

import functools
import time
from typing import Union
import jq
import re
import operator
import backend.sandboxClient as sandboxClient

from backend.appConfig import logger


def debounce_check_active_tasks(debounce_seconds: int = 1):
    func_last_execution_time = {}
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            user_id = args[0]
            now = time.time()
            key = f"{user_id}_{func.__name__}"
            if key not in func_last_execution_time:
                func_last_execution_time[key] = now
                return func(*args, **kwargs)
            elif now >= func_last_execution_time[key] + debounce_seconds:
                func_last_execution_time[key] = now
                return func(*args, **kwargs)
            else:
                logger.debug(f">> Debounced for `{user_id}`")
                return None
        return wrapper
    return decorator


def eval_data_filtering(inject_evaluation: dict, data: dict, context: dict, debug: bool = False) -> Union[bool, tuple]:
    debug_steps = []
    eval_state = None
    for evaluation_params in inject_evaluation['parameters']:
        if eval_state is False:
            break
        debug_step = []
        for evaluation_path, evaluation_config in evaluation_params.items():
            if eval_state is False:
                break
            evaluation_path = apply_replacement_from_context(evaluation_path, context)
            data_to_validate = jq_extract(evaluation_path, data, evaluation_config.get('extract_type', 'first'))
            debug_step.append({'message': f'Testing `{evaluation_path}`', 'data': {}, 'style': 'primary'})
            cond_satisfied = False
            if data_to_validate is None:
                debug_step.append({'message': f'The provided path could not extract data', 'data': data, 'style': 'error'})
                eval_state = False
            else:
                cond_satisfied = condition_satisfied(evaluation_config, data_to_validate, context)
            if not cond_satisfied:
                debug_step.append({'message': f'Condition not satisfied', 'data': {}, 'style': 'fail'})
                debug_step.append({'message': f'The provided path extracted the following data to validate', 'data': data_to_validate, 'style': ''})
                eval_state = False
            else:
                eval_state = True
                debug_step.append({'message': f'Condition satisfied', 'data': {}, 'style': 'success'})
        debug_steps = debug_steps + [debug_step] if len(debug_step) > 0 else debug_steps
    return eval_state if not debug else (eval_state, debug_steps,)


# Replace the substring `{{variable}}` by context[variable] or the jq_path in the provided string
def apply_replacement_from_context(string: str, context: dict) -> str:
    string = str(string)

    # Non-greedy regex to match each placeholder separately
    replacement_regex = r"{{(.*?)}}"

    def replacer(match):
        key = match.group(1)
        value = context.get(key)
        if value is None:
            value = jq_extract(key, context) or ""
        return str(value)

    return re.sub(replacement_regex, replacer, string)


def jq_extract(path: str, data: dict, extract_type='first'):
    try:
        query = jq.compile(path).input_value(data)
        return query.first() if extract_type == 'first' else query.all()
    except StopIteration:
        return None
    except ValueError:
        return None


def eval_python(inject_evaluation: dict, data: dict, context: dict, debug: bool = False) -> Union[bool, tuple]:
    return sandboxClient.run(inject_evaluation, data, context, debug)


def condition_satisfied(evaluation_config: dict, data_to_validate: Union[dict, list, str], context: dict) -> bool:
    if type(data_to_validate) is bool:
        data_to_validate = "1" if data_to_validate else "0"
    if type(data_to_validate) is str:
        return eval_condition_str(evaluation_config, data_to_validate, context)
    elif type(data_to_validate) is list:
        return eval_condition_list(evaluation_config, data_to_validate, context)
    elif type(data_to_validate) is dict:
        # Not sure how we could have condition on this
        return eval_condition_dict(evaluation_config, data_to_validate, context)
    return False


def eval_condition_str(evaluation_config: dict, data_to_validate: str, context: dict) -> bool:
    comparison_type = evaluation_config['comparison']
    values = evaluation_config['values']
    if len(values) == 0:
        return False
    values = [apply_replacement_from_context(v, context) for v in values]

    if comparison_type == 'contains':
        values = [v.lower() for v in values]
        data_to_validate = data_to_validate.lower()
        data_to_validate_set = set(data_to_validate.split())
        values_set = set(values)
        intersection = data_to_validate_set & values_set
        return len(intersection) == len(values_set)
    elif comparison_type == 'equals':
        return data_to_validate == values[0]
    elif comparison_type == 'equals_any':
        return data_to_validate in values
    elif comparison_type == 'regex':
        return re.fullmatch(values[0], data_to_validate)
    elif comparison_type == 'count':
        return count_comparison(values, data_to_validate)
    return False


def eval_condition_list(evaluation_config: dict, data_to_validate: str, context: dict) -> bool:
    comparison_type = evaluation_config['comparison']
    values = evaluation_config['values']

    if len(values) == 0:
        return False
    values = [apply_replacement_from_context(v, context) for v in values]

    if comparison_type == 'contains' or comparison_type == 'equals':
        data_to_validate_set = set(data_to_validate)
        values_set = set(values)
        intersection = data_to_validate_set & values_set
        if comparison_type == 'contains':
            return len(intersection) == len(values_set)
        elif comparison_type == 'equals':
            return len(intersection) == len(values_set) and len(intersection) == len(data_to_validate_set)
    if comparison_type == 'equals-regex':
        regex = re.compile(values[0])
        for candidate in data_to_validate:
            if regex.match(candidate) is None:
                return False
            else:
                return True
        return False
    if comparison_type == 'contains-regex':
        regex = re.compile(values[0])
        for candidate in data_to_validate:
            if regex.match(candidate) is not None:
                return True
        return False
    elif comparison_type == 'count':
        return count_comparison(values, data_to_validate)
    return False

def count_comparison(values: str, data_to_validate: str) -> bool:
    comparators = {
        '<': operator.lt,
        '<=': operator.le,
        '>': operator.gt,
        '>=': operator.ge,
        '=': operator.eq,
    }
    value = values[0]
    if value.isdigit():
        value = int(value)
        return len(data_to_validate) == value
    elif value[:2] in comparators.keys():
        count = len(data_to_validate)
        value_operator = values[0][:2]
        value = int(value[2:])
        return comparators[value_operator](count, value)
    elif value[0] in comparators.keys():
        count = len(data_to_validate)
        value_operator = value[0]
        value = int(value[1:])
        return comparators[value_operator](count, value)


def eval_condition_dict(evaluation_config: dict, data_to_validate: str, context: dict) -> bool:
    comparison_type = evaluation_config['comparison']
    values = evaluation_config['values']
    comparators = {
        '<': operator.lt,
        '<=': operator.le,
        '>': operator.gt,
        '>=': operator.ge,
        '=': operator.eq,
    }

    if len(values) == 0:
        return False
    values = [apply_replacement_from_context(v, context) for v in values]

    comparison_type = evaluation_config['comparison']
    if comparison_type == 'contains':
        pass
    elif comparison_type == 'equals':
        pass
    elif comparison_type == 'count':
        return count_comparison(values, data_to_validate)
    return False
