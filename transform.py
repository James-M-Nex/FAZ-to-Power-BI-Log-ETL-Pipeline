'''
This script takes the traffic logs from FAZ and normalizes and filters out any data that is not useful.
The traffic logs are taken in as a list from the faz_fethcher.py scripts check_and_fetch() methods return
After it normalizes and filters the logs it creates summarized versions for the interval of the logs grabbed.
This script returns the summarized lists of logs.
Made: 7/23/26
Edited: 8/6/26
Author(s): James Meyers (james.meyers@nexteer.com)
'''

# Standard Imports
import json
import logging

# Setup logger
logger = logging.getLogger(__name__)

def normalize_and_filter(raw_logs: list[dict], r_flag: bool, n_flag: bool, adom: str, interval_start: str) -> list[dict]:
    '''
    Flatten and filter logs for only the items that are useful.
    '''

    # Whitelist of essential FortiAnalyzer traffic log fields to retain
    selected_fields = (
        "action",
        "policyid",
        "srcip",
        "dstip",
        "sentbyte",
        "rcvdbyte",
        "sentpkt",
        "rcvdpkt",
        "app",
        "appcat",
        "srcintf",
        "dstintf",
        "policyname",
        "devname"
    )

    if not raw_logs:
        return [],[],[],[],[]

    all_logs = []

    for i, page in enumerate(raw_logs):
        if not isinstance(page, dict):
            continue

        result = page.get("result")
        if not isinstance(result, dict):
            continue

        data = result.get("data")
        if not isinstance(data, list):
            continue

        if len(data) != 0:
            for record in data:
                all_logs.append({
                    field: record.get(field)
                    for field in selected_fields
                })

        # Nullify raw log page after processing to allow garbage collection and lower RAM usage
        if not r_flag:
            raw_logs[i] = None


    if n_flag:
        with open(f"{adom}normalizedLogs.txt", "w", encoding="utf-8") as file:
            file.write(json.dumps(all_logs, indent=2))

    if r_flag:
        with open(f"{adom}rawLogs.txt", "w", encoding="utf-8") as file:
            file.write(json.dumps(raw_logs, indent=2))

    logger.info(f"{adom} Normalized log entries: {len(all_logs)}")

    traffic_summary_logs, source_ip_summary_logs, destination_count_summary, top_destination_occurences, top_destination_bytes = aggreagate_log(all_logs, adom, interval_start)

    logger.info(f"{adom} Traffic aggregate log entries: {len(traffic_summary_logs)}")
    logger.info(f"{adom} Source IP aggregate log entries: {len(source_ip_summary_logs)}")
    logger.info(f"{adom} Destination IP aggregate log entries: {len(destination_count_summary)}")
    logger.info(f"{adom} Top Destination IP by Occurences log entries: {len(top_destination_occurences)}")
    logger.info(f"{adom} Top Destination IP by Bytes log entries: {len(top_destination_bytes)}")

    return traffic_summary_logs, source_ip_summary_logs, destination_count_summary, top_destination_occurences, top_destination_bytes

def aggreagate_log(all_logs: list[dict], adom: str, interval_start: str) -> tuple:
    '''
    Creates summary tables from all logs.
    Returns summary tables for traffic, source IP's, and destination IP's in a tuple.
    '''
    # Hash bucket dictionaries for performing fast in-memory aggregation
    traffic_buckets = {}
    source_ip_buckets = {}
    destination_ip_buckets = {}
    destination_count_buckets = {}

    for log in all_logs:

        traffic_key = (
            log.get("devname"),
            log.get("policyid"),
            log.get("app"),
            log.get("action"),
            log.get("srcintf"),
            log.get("dstintf")
        )

        srcip = log.get("srcip")

        if srcip:
            source_ip_key = (
                srcip,
                log.get("devname")
            )

            if source_ip_key not in source_ip_buckets:
                source_ip_buckets[source_ip_key] = {
                    "interval_start": interval_start,
                    "adom": adom,
                    "devname": log.get("devname"),
                    "srcip": srcip,
                    "occurences": 0,
                    "sentbyte": 0,
                    "rcvdbyte": 0
                }

        destination_ip_key = (
            log.get("dstip"),
            log.get("devname")
        )

        destination_count_key = (
            log.get("devname")
        )

        if traffic_key not in traffic_buckets:
            traffic_buckets[traffic_key] = {
                "interval_start": interval_start,
                "adom": adom,
                "devname": log.get("devname"),
                "policyid": log.get("policyid"),
                "policyname": log.get("policyname"),
                "app": log.get("app"),
                "appcat": log.get("appcat"),
                "action": log.get("action"),
                "srcintf": log.get("srcintf"),
                "dstintf": log.get("dstintf"),
                "sessions": 0,
                "sentbyte": 0,
                "rcvdbyte": 0,
                "sentpkt": 0,
                "rcvdpkt": 0,
            }

        if destination_ip_key not in destination_ip_buckets:
            destination_ip_buckets[destination_ip_key] = {
                "interval_start": interval_start,
                "adom": adom,
                "devname": log.get("devname"),
                "dstip": log.get("dstip"),
                "occurences": 0,
                "sentbyte": 0,
                "rcvdbyte": 0
            }

        if destination_count_key not in destination_count_buckets:
            destination_count_buckets[destination_count_key] = set()

        if log.get("dstip"):
            destination_count_buckets[destination_count_key].add(log.get("dstip"))

        traffic_bucket = traffic_buckets[traffic_key]
        source_ip_bucket = source_ip_buckets[source_ip_key]
        destination_ip_bucket = destination_ip_buckets[destination_ip_key]

        traffic_bucket["sessions"] += 1
        source_ip_bucket["occurences"] += 1
        destination_ip_bucket["occurences"] += 1


        traffic_bucket["sentbyte"] += int(log.get("sentbyte", 0) or 0)
        source_ip_bucket["sentbyte"] += int(log.get("sentbyte", 0) or 0)
        destination_ip_bucket["sentbyte"] += int(log.get("sentbyte", 0) or 0)

        traffic_bucket["rcvdbyte"] += int(log.get("rcvdbyte", 0) or 0)
        source_ip_bucket["rcvdbyte"] += int(log.get("rcvdbyte", 0) or 0)
        destination_ip_bucket["rcvdbyte"] += int(log.get("rcvdbyte", 0) or 0)

        traffic_bucket["sentpkt"] += int(log.get("sentpkt", 0) or 0)
        traffic_bucket["rcvdpkt"] += int(log.get("rcvdpkt", 0) or 0)

    # Build unique destination count summary per firewall device
    destination_count_summary = []

    for devname, ip_set in destination_count_buckets.items():
        destination_count_summary.append({
            "interval_start": interval_start,
            "adom": adom,
            "devname": devname,
            "unique_destination_count": len(ip_set)
        })

    # Sort and cap top 1,000 destination IPs by session frequency and byte volume
    top_destination_occurences = sorted(destination_ip_buckets.values(), key=lambda x: x["occurences"], reverse=True)[:1000]
    top_destination_bytes = sorted(destination_ip_buckets.values(), key=lambda x: x["sentbyte"] + x["rcvdbyte"], reverse=True)[:1000]

    return (list(traffic_buckets.values()), list(source_ip_buckets.values()), destination_count_summary, top_destination_occurences, top_destination_bytes)