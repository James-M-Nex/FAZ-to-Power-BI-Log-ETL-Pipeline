'''
Testing methods
'''

import requests
import urllib3
import pandas as pd
import json
import time
from datetime import datetime, timedelta
urllib3.disable_warnings()

FAZ_URL = "https://faz.nexteer.com/jsonrpc"
USERNAME = ""
PASSWORD = ""
ADOM = ["root", "Asia_Pacific", "EMEA-SA", "Labs", "Mexico", "United_States"]
PAGE_SIZE = 100
TIME_RANGE = 1
CHECK_INTERVAL = 0.125

def login() -> str:
    login_payload = {
        "method": "exec",
        "params": [{
            "url": "/sys/login/user",
            "data": {
                "user": USERNAME,
                "passwd": PASSWORD
            }
        }],
        "session": "string",
        "id": 1
    }

    login_response = requests.post(FAZ_URL, json=login_payload, verify=False)
    login_json = login_response.json()
    session = login_json["session"]

    return session

def logout(session: str) -> str:
    logout_payload = {
        "id": 4,
        "method": "exec",
        "params": [{
            "url": "/sys/logout",
            "data": {
                "user": USERNAME,
                "passwd": PASSWORD
            }
        }],
        "session": session
    }

    logout_response = requests.post(FAZ_URL, json=logout_payload, verify=False)
    
    return logout_response.status_code

def log_search(start_datetime: str, end_datetime: str, session: str, selected_ADOM: str) -> tuple[str,str]:
    search_payload = {
        "id": "2",
        "jsonrpc": "2.0",
        "method": "add",
        "params": [
          {
            "apiver": 3,
            "case-sensitive": False,
            "device": [
              {
                "devid": "All_Devices"
              }
            ],
            "filter": "",
            "logtype": "traffic",
            "time-order": "asc",
            "time-range": {
              "start": start_datetime,
              "end": end_datetime
            },
            "url": f"/logview/adom/{selected_ADOM}/logsearch"
          }
        ],
        "session": session
    }

    search_response = requests.post(FAZ_URL, json=search_payload, verify=False)
    search_json = search_response.json()
    http_status = search_response.status_code
    tid = search_json["result"]["tid"]

    return (http_status, tid)

def check_and_fetch(selected_ADOM: str, tid: int, session: str) -> None:
    check_interval = CHECK_INTERVAL
    percentage = 0
    total_count = 1
    offset = 0
    return_lines = 0
    all_logs = []

    while(offset < total_count):

        while(int(percentage) < 100):
            tid_check_payload = {
                "id": "3",
                "jsonrpc": "2.0",
                "method": "get",
                "params": [
                    {
                      "apiver": 3,
                      "url": f"/logview/adom/{selected_ADOM}/logsearch/{tid}",
                      "offset": offset
                    }
                ],
                "session": session
            }

            time.sleep(check_interval)
            tid_response = requests.post(FAZ_URL, json=tid_check_payload, verify=False)
            tid_status_json = tid_response.json()
            percentage = tid_status_json["result"]["percentage"]
            print(percentage)
            total_count = tid_status_json["result"]["total-count"]
            return_lines = tid_status_json["result"]["return-lines"]
            check_interval *= 2
        
        fetch_tid_payload = {
            "id": "4",
            "jsonrpc": "2.0",
            "method": "get",
            "params": [
              {
                "apiver": 3,
                "limit": PAGE_SIZE,
                "offset": offset,
                "url": f"/logview/adom/{selected_ADOM}/logsearch/{tid}"
              }
            ],
            "session": session
        }

        fetch_response = requests.post(FAZ_URL, json=fetch_tid_payload, verify=False)
        fetch_json = fetch_response.json()
        all_logs.append(fetch_json)
        offset += 100
        check_interval = CHECK_INTERVAL
        percentage = 0
        print(f"Offset: {offset}, Total Count: {total_count}, Returned Lines: {return_lines}, All Log Size: {len(all_logs)}")

    with open("output.txt", "w") as file:
        file.write(json.dumps(all_logs, indent=2))