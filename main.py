'''
This is the main script for the entire FAZ -> Power BI operation.
This script should be run from a cron job at a specified interval, 10 mins is recommended.
The purpose of this is to make SQL database that provides logs to a Power BI report since Power BI is unable to pull from the Forti Analyzer server correctly.
Made: 7/23/26
Edited: 8/6/26
Author(s): James Meyers (james.meyers@nexteer.com)
'''

# Standard Imports
import argparse
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import logging
from logging.handlers import RotatingFileHandler

# Third Party Imports
import config
import faz_fetcher
import transform
import database

# Constants
ADOM = ["All", "Asia_Pacific", "EMEA-SA", "Labs", "Mexico", "United_States"]

# Setup logger
handler = RotatingFileHandler("app.log", maxBytes=1000000000, backupCount= 1)
handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
root = logging.getLogger()
root.setLevel(logging.INFO)
root.addHandler(handler)


def process_adom(selected_ADOM: str, start_datetime: str, end_datetime: str, args: argparse.Namespace) -> None:
    '''
    This runs the entire log gathering and storing process for one adom.
    '''

    # ----------------------- #
    # ----- FAZ Fetcher ----- #
    # ----------------------- #

    # Login
    session = faz_fetcher.login(config.FAZ_USERNAME, config.FAZ_PASSWORD)
    if not session:
        return
    root.info(f"Session ID = {session}")

    # Start search task
    search_http_status, tid = faz_fetcher.log_search(start_datetime, end_datetime, session, selected_ADOM)
    if search_http_status == 200:
        root.info(f"Task started | TID={tid}")
    else:
        root.warning(f"Task failed to start | HTTP Status = {search_http_status}")
        return

    # Check task status and fetch log pages
    # Reduce threads by 1 for Stage 1 ADOMs running concurrently to prevent API saturation
    if selected_ADOM == "Asia_Pacific" or selected_ADOM == "Labs" or selected_ADOM == "EMEA-SA":
        all_logs = faz_fetcher.check_and_fetch(selected_ADOM, tid, session, args.threads - 1)
    else:
        all_logs = faz_fetcher.check_and_fetch(selected_ADOM, tid, session, args.threads)

    # Logout
    logout_http_status = faz_fetcher.logout(session, config.FAZ_USERNAME, config.FAZ_PASSWORD)
    if logout_http_status == 200:
        root.info("Logged out successfully")

    # ---------------------------- #
    # ---- Normalize & Filter ---- #
    # ---------------------------- #

    # Convert ISO datetime format ('T') to SQL format (' ') and process log summaries
    traffic_summary_logs, source_ip_summary_logs, destination_count_summary, top_destination_occurence, top_destination_bytes = transform.normalize_and_filter(all_logs, args.rawLogs, args.normalizedLogs, selected_ADOM, start_datetime.replace("T", " "))

    # Clear up memory
    del all_logs

    # ---------------------------- #
    # ---- MySQL DB Managment ---- #
    # ---------------------------- #

    # Connect to MySQL and insert all summary log tables
    mydb = database.create_db_connection(config.SQL_USERNAME, config.SQL_PASSWORD)
    database.insert_logs(mydb, traffic_summary_logs, "traffic_summary", selected_ADOM)
    database.insert_logs(mydb, source_ip_summary_logs, "source_ip_summary", selected_ADOM)
    database.insert_logs(mydb, destination_count_summary, "destination_count_summary", selected_ADOM)
    database.insert_logs(mydb, top_destination_occurence, "top_destination_summary_occurence", selected_ADOM)
    database.insert_logs(mydb, top_destination_bytes, "top_destination_summary_byte", selected_ADOM)

def run_pipeline(start_datetime: str, end_datetime: str, args: argparse.Namespace) -> None:
    '''
    Start Asia_Pacific immediately, then let Labs and EMEA-SA run in parallel with it.
    As soon as Labs and EMEA-SA finish, start Mexico then, when finished, run United_States.
    '''
    # Stage 1: Launch Asia_Pacific, Labs, and EMEA-SA in parallel
    root.info("Starting first stage: Asia_Pacific, Labs, EMEA-SA")

    with ThreadPoolExecutor(max_workers=3) as executor:
        asia_future = executor.submit(process_adom, "Asia_Pacific", start_datetime, end_datetime, args)
        labs_future = executor.submit(process_adom, "Labs", start_datetime, end_datetime, args)
        emea_future = executor.submit(process_adom, "EMEA-SA", start_datetime, end_datetime, args)

        # Wait for Labs and EMEA-SA to finish before proceeding
        for future in [labs_future, emea_future]:
            future.result()

        # Stage 2: Launch Mexico after Labs and EMEA-SA complete
        root.info("Labs and EMEA-SA finished; starting second stage: Mexico")
        mexico_future = executor.submit(process_adom, "Mexico", start_datetime, end_datetime, args)
        mexico_future.result()

        # Stage 3: Launch United_States after Mexico completes
        root.info("Mexico finished; starting second stage: United_States")
        us_future = executor.submit(process_adom, "United_States", start_datetime, end_datetime, args)
        us_future.result()

        # Ensure Asia_Pacific finishes before exiting pipeline
        asia_future.result()


def main():
    # Process command line args
    parser = argparse.ArgumentParser(description='Fetch FAZ traffic logs and store in a SQL database')
    parser.add_argument("adom", choices=[0, 1, 2, 3, 4, 5], help="Select ADOM to pull logs from. | 0: All | 1: Asia_Pacific | 2: EMEA-SA | 3: Labs | 4: Mexico | 5: United States |", type=int)
    parser.add_argument("timeRange", help="Pull logs from the last N minutes", type=int)
    parser.add_argument("-t", "--threads", type=int, default=3, help="Number of parallel fetch threads (default: 3)")
    parser.add_argument("-r", "--rawLogs", action="store_true", help="Output raw FAZ logs to {adom}rawLogs.txt")
    parser.add_argument("-n", "--normalizedLogs", action="store_true", help="Output normalized FAZ logs to {adom}normalizedLogs.txt")
    parser.add_argument("-e", "--easteregg", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.easteregg:
        import easter_egg
    else:
        # Calculate ISO 8601 search interval (YYYY-MM-DDTHH:MM:SS) for FortiAnalyzer API query
        selected_ADOM = ADOM[args.adom]
        time_range = args.timeRange
        end_datetime = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        start_datetime = (datetime.now() - timedelta(minutes=time_range)).strftime("%Y-%m-%dT%H:%M:%S")
        root.info(f"Starting Search on ADOM: {selected_ADOM}, Interval: {start_datetime} - {end_datetime}, Threads: {args.threads}")

        print("Starting Fetcher")

        # adom = 0 ("All") runs full multi-stage pipeline, otherwise runs single selected ADOM
        if selected_ADOM == "All":
            run_pipeline(start_datetime, end_datetime, args)
        else:
            process_adom(selected_ADOM, start_datetime, end_datetime, args)


if __name__ == "__main__":
    main()
