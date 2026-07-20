#!/urs/bin/env python3


from typing import Union
from backend.utils import (
    eval_data_filtering as eval_data_filtering_util,
    eval_python as eval_python_util,
    jq_extract,
)
from backend.provenance import synthesize_query_mirror_debug


## Data filtering
def eval_data_filtering(user_id: int, inject_evaluation: dict, data: dict, context: dict, debug: bool = False) -> Union[bool, tuple]:
    return eval_data_filtering_util(inject_evaluation, data, context, debug = debug)


## Query mirror
def eval_query_mirror(user_id: int, expected_data, data_to_validate, context: dict, debug: bool = False) -> Union[bool, tuple]:
    success = expected_data == data_to_validate
    if debug:
        # query_mirror has no native step trace — synthesize one so the outcome
        # renders in the Debug view like every other strategy.
        return success, synthesize_query_mirror_debug(expected_data, data_to_validate, success)
    return success


## Query search
def eval_query_search(user_id: int, inject_evaluation: dict, data: dict, context: dict, debug: bool = False) -> bool:
    return eval_data_filtering(user_id, inject_evaluation, data, context, debug = debug)

## Python
def eval_python(user_id: int, inject_evaluation: dict, data: dict, context: dict, debug: bool = False) -> bool:
    return eval_python_util(inject_evaluation, data, context, debug=debug)
