'''
This script fetches traffic logs from the Nexteer Forti Analyzer server and returns a JSON log list.
It pulls the logs from the JSONRPC API using a read-only account on the server.
The SQL database provides logs to a Power BI report since Power BI is unable to pull from the Forti Analyzer server correctly.
This script utilizes threading to speed up the logs gathering, meaning the more cores the better.
Made: 6/26/26
Edited: 8/5/26
Author(s): James Meyers (james.meyers@nexteer.com)
'''

# Standard Imports
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import time
import logging

# Third Party Imports
import requests
import urllib3

# Local Imports
import config

# Clear up output warnings
urllib3.disable_warnings()

# Constants
FAZ_URL = config.FAZ_URL
PAGE_SIZE = 800              # Maximum log records returned per JSONRPC request by FAZ
CHECK_INTERVAL = 0.125       # Base polling delay in seconds for checking search completion status
MAX_PAGE_POLL_ATTEMPTS = 6   # Maximum polling attempts before forcing page fetch

# Seutp logger
logger = logging.getLogger(__name__)

def login(username: str, password: str) -> str:
    '''
    Login into FAZ server with the credentials. Returns a session key.
    '''
    login_payload = {
        "method": "exec",
        "params": [{
            "url": "/sys/login/user",
            "data": {
                "user": username,
                "passwd": password
            }
        }],
        "session": "string",
        "id": 1
    }

    try:
        login_response = requests.post(FAZ_URL, json=login_payload, verify=False)
        login_json = login_response.json()
        
        session = login_json["session"]
        return session
    except Exception as e:
        logger.error("Error occured when attempting to login to the FAZ server. Error: ", e)
        return

def logout(session: str, username: str, password: str) -> str:
    '''
    Closes out the provided session with the credentials. Returns the HTTP status code of the response.
    '''

    logout_payload = {
        "id": 4,
        "method": "exec",
        "params": [{
            "url": "/sys/logout",
            "data": {
                "user": username,
                "passwd": password
            }
        }],
        "session": session
    }

    logout_response = requests.post(FAZ_URL, json=logout_payload, verify=False)
    
    return logout_response.status_code

def log_search(start_datetime: str, end_datetime: str, session: str, selected_ADOM: str) -> tuple[int, int]:
    '''
    Starts a search task from the provided session key from the start_datetime to the end_datetime. Returns the HTTP status of the task and the task ID (tid).
    '''

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

def check_and_fetch_page(selected_ADOM: str, tid: int, offset: int, session: str, total_count_holder: dict, count_lock: threading.Lock) -> dict:
    """
    Checks a specific page's completion status until 100%, then fetches it.
    Also updates total count if a higher count is found.
    Returns a dict with 'offset' and 'data' keys to maintain order.
    """
    check_interval = CHECK_INTERVAL
    percentage = 0
    poll_attempts = 0
    last_count = None
    
    # Check this specific page until it reaches 100%
    while int(percentage) < 100:
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
        tid_response = requests.post(FAZ_URL, json=tid_check_payload, verify=False, timeout=30)
        tid_status_json = tid_response.json()
        percentage = tid_status_json["result"].get("percentage", 0)
        current_count = tid_status_json["result"].get("total-count", last_count)
        
        # Update total count if current result shows a higher count
        if current_count is not None:
            with count_lock:
                if current_count > total_count_holder["count"]:
                    total_count_holder["count"] = current_count
                    #print(f"Total count updated to {current_count}")
            last_count = current_count
        
        #print(f"Page offset {offset}: {percentage}%")
        poll_attempts += 1

        # Poll status with exponential backoff until search progress reaches 100%
        if poll_attempts >= MAX_PAGE_POLL_ATTEMPTS:
            break

        check_interval *= 2
    
    # Once page reaches 100%, fetch it
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
    
    #print(f"Fetched page at offset {offset}")
    return {"offset": offset, "data": fetch_json}

def get_total_count(selected_ADOM: str, tid: int, session: str) -> int:
    """
    Gets the total count from the first page, waiting until it reaches 100% completion.
    """
    check_interval = CHECK_INTERVAL
    percentage = 0
    
    # Wait until offset 0 reaches 100% before returning count
    while int(percentage) < 100:
        check_payload = {
            "id": "3",
            "jsonrpc": "2.0",
            "method": "get",
            "params": [
                {
                  "apiver": 3,
                  "url": f"/logview/adom/{selected_ADOM}/logsearch/{tid}",
                  "limit": PAGE_SIZE,
                  "offset": 0
                }
            ],
            "session": session
        }
        
        time.sleep(check_interval)
        check_response = requests.post(FAZ_URL, json=check_payload, verify=False)
        check_json = check_response.json()
        percentage = check_json["result"]["percentage"]
        #print(f"Initial page: {percentage}%")
        check_interval *= 2
    
    total_count = check_json["result"]["total-count"]
    logger.info(f"Total count: {total_count}")
    
    return total_count

def check_and_fetch(selected_ADOM: str, tid: int, session: str, max_threads: int) -> list:
    """
    Checks and fetches all pages in parallel threads.
    Each thread handles checking and fetching its own page to maintain the API requirement.
    Dynamically discovers new pages if total count grows during fetching.
    Results are reconstructed in order at the end.
    """
    # Get initial total count to determine starting number of pages
    initial_count = get_total_count(selected_ADOM, tid, session)
    
    # Thread-safe container to track dynamic total count updates across worker threads
    total_count_holder = {"count": initial_count}
    count_lock = threading.Lock()
    
    # Calculate page offsets (0, 800, 1600, ...)
    num_pages = (initial_count + PAGE_SIZE - 1) // PAGE_SIZE
    page_offsets = set([i * PAGE_SIZE for i in range(num_pages)])
    submitted_offsets = set()
    
    logger.info(f"Initial total count: {initial_count}, starting with {num_pages} pages...")
    
    # Fetch all pages in parallel using ThreadPoolExecutor
    all_logs_dict = {}
    
    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        future_to_offset = {}
        
        # Submit initial pages
        for offset in page_offsets:
            future = executor.submit(check_and_fetch_page, selected_ADOM, tid, offset, session, total_count_holder, count_lock)
            future_to_offset[future] = offset
            submitted_offsets.add(offset)
        
        # Collect results and check for new pages as they complete
        completed = 0
        while completed < len(submitted_offsets):
            try:
                done_futures = list(as_completed(future_to_offset, timeout=60))
            except TimeoutError:
                # Timeout waiting for futures, continue checking
                done_futures = []
            
            for future in done_futures:
                try:
                    result = future.result()
                    all_logs_dict[result["offset"]] = result["data"]
                    offset = future_to_offset.pop(future)
                    completed += 1
                    #print(f"Page at offset {result['offset']} completed and stored")
                    
                    # Check if total count has grown and submit new pages
                    with count_lock:
                        current_total = total_count_holder["count"]
                    
                    new_num_pages = (current_total + PAGE_SIZE - 1) // PAGE_SIZE
                    new_offsets = set([i * PAGE_SIZE for i in range(new_num_pages)])
                    
                    # Submit any new pages that weren't submitted yet
                    for new_offset in new_offsets - submitted_offsets:
                        #print(f"New page discovered at offset {new_offset}, submitting...")
                        future = executor.submit(check_and_fetch_page, selected_ADOM, tid, new_offset, session, total_count_holder, count_lock)
                        future_to_offset[future] = new_offset
                        submitted_offsets.add(new_offset)
                    
                except Exception as e:
                    logger.warning(f"Error fetching page: {e}")
                    future_to_offset.pop(future, None)
                    completed += 1
    
    # Reconstruct all fetched JSON pages in strict offset order
    all_logs = []
    for offset in sorted(submitted_offsets):
        if offset in all_logs_dict:
            all_logs.append(all_logs_dict[offset])
    
    logger.info(f"All {len(all_logs)} pages fetched and ordered successfully")

    return all_logs
    