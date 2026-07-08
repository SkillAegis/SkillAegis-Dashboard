#!/usr/bin/env python3
import json
from typing import Union
import jq

from backend.utils import apply_replacement_from_context, eval_data_filtering, eval_python
from backend.appConfig import logger
import backend.db as db
from backend.target_tools.misp.exercise import fetch_data_for_query_search


async def inject_checker_router(user_id: int, inject_evaluation: dict, data: dict, context: dict, debug: bool = False) -> Union[bool, tuple]:
    # When debug=True, return (success, debug_steps) so the caller can capture the
    # trace. This path previously computed the data_filtering/python trace and threw
    # it away (`outcome, d = …`) — now it is surfaced (PRD-inject-eval-provenance).
    if inject_evaluation['evaluation_strategy'] == 'data_filtering':
        return eval_data_filtering(inject_evaluation, data, context, debug)
    elif inject_evaluation["evaluation_strategy"] == "misp_query_search":
        context['webhook_data'] = data
        inject_evaluation = doReplacementOnQueryContext(inject_evaluation, context)
        data_to_validate = await fetch_data_for_query_search(user_id, inject_evaluation)
        if data_to_validate is None:
            logger.debug('Could not fetch data to validate')
            return (False, []) if debug else False
        return eval_data_filtering(inject_evaluation, data_to_validate, context, debug)
    elif inject_evaluation["evaluation_strategy"] == "python":
        data_to_validate = data
        return eval_python(inject_evaluation, data_to_validate, context, debug)
    return (False, []) if debug else False


def doReplacementOnQueryContext(inject_evaluation, context):
    query_context_str = json.dumps(inject_evaluation["evaluation_context"]["query_context"])
    interpolated_query_context = json.loads(apply_replacement_from_context(query_context_str, context))
    inject_evaluation["evaluation_context"]["query_context"] = interpolated_query_context
    return inject_evaluation
