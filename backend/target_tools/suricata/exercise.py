#!/usr/bin/env python3
import os
from typing import Union
import subprocess
import json
import jq

from backend.utils import eval_data_filtering
from backend.appConfig import logger
import backend.db as db
import backend.misp_api as misp_api


runDir = os.path.dirname(os.path.realpath(__file__)) + '/run'
rulesFile = f'{runDir}/local.rules'
eveFile = f'{runDir}/eve.json'

def getInstalledSuricataVersion() -> Union[str, None]:
    try:
        command = [
            "suricata", 
        ]
        result = subprocess.run(command, capture_output = True, text = True)
        version = result.stdout.splitlines()[0]
        return version
    except:
        return None


async def inject_checker_router(user_id: int, inject_evaluation: dict, data: dict, context: dict, debug: bool = False) -> Union[bool, tuple]:
    # suricata is out of scope for the inject-eval-provenance trace capture (its
    # shell-out/pcap result has a different shape). The `debug` param only keeps the
    # router signature uniform with MISP/webhook — it returns an empty trace so a
    # debug-mode caller does not error.
    if getInstalledSuricataVersion() is None:
        return (False, []) if debug else False

    rules = await get_data_to_validate(user_id, inject_evaluation, data)
    if rules is None:
        logger.debug('Could not fetch rules to validate')
        return (False, []) if debug else False

    data_to_validate = getEventsWithVerdictFromRules(rules)
    if inject_evaluation['evaluation_strategy'] == 'simulate_ips':
        outcome = eval_data_filtering(inject_evaluation, data_to_validate, context, False)
        return (outcome, []) if debug else outcome
    return (False, []) if debug else False


async def get_data_to_validate(user_id: int, inject_evaluation: dict, data: dict) -> Union[dict, list, str, None]:
    data_to_validate = await fetch_data(user_id, inject_evaluation)
    return data_to_validate


async def fetch_data(user_id: int, inject_evaluation: dict) -> Union[None, dict]:
    authkey = db.USER_ID_TO_AUTHKEY_MAPPING[user_id]
    base_query_context = {
        'url': '/attributes/restSearch',
        'request_method': 'POST',
        'payload': {
            'published': False,
            'timestamp': '1d',
            "returnFormat": "suricata"
        }
    }
    query_context = inject_evaluation.get('evaluation_context', {}).get('query_context', {})
    query_context_merged = query_context.copy()
    query_context_merged.update(base_query_context)
    search_method = query_context_merged['request_method']
    search_url = query_context_merged['url']
    search_payload = query_context_merged['payload']
    rules  = await misp_api.doRestQuery(authkey, search_method, search_url, search_payload)
    return rules


def createRulesFile(rules: str):
    rules = rules.replace('alert', 'drop')
    with open(rulesFile, 'w') as f:
        f.write(rules)


def purgeEveFile():
    os.unlink(eveFile)

# Run suricata on a pcap
#   -k none ignore truncated flows/paquets
def runRulesOnSuricata():
    pcap_path = f'{runDir}/http_195.208.152.43.pcapng'
    rules_path = rulesFile
    suricata_config_path = f'{runDir}/suricata.yaml'
    command = [
        "suricata", 
        "-r", pcap_path, 
        "-k", "none", 
        "--simulate-ips", 
        "-S", rules_path,
        "-c", suricata_config_path,
        "-l", runDir,
    ]
    subprocess.run(command, stdout = subprocess.DEVNULL)


def getSuricataEventsWithVerdict() -> list:
    verdicts = []
    with open(eveFile) as f:
        events = f.read()
        path = '. | select(.verdict.action=="drop" and .alert.signature ) | .'
        query = jq.compile(path).input_text(events)
        verdicts = query.all()
    return verdicts


def getEventsWithVerdictFromRules(rules: str) -> list:
    createRulesFile(rules)
    purgeEveFile()
    runRulesOnSuricata()
    eventsWithVerdict = getSuricataEventsWithVerdict()
    return eventsWithVerdict
