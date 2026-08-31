'''
This script checks for logs where their date is before the cut off date.
If any logs are found this way they are removed from the MySQL server.
This script should be run at a regular interval of 7 days via a task scheduler.
Made: 7/31/26
Edited: 8/5/26
Author(s): James Meyers (james.meyers@nexteer.com)
'''

# Standard Imports
from datetime import datetime, timedelta
import argparse
import logging
from logging.handlers import RotatingFileHandler

# Third Party Imports
import database

# Constants
TABLES = ["All", "destination_count_summary", "source_ip_summary", "top_destination_summary_byte", "top_destination_summary_occurence", "traffic_summary"]

# Setup logger
handler = RotatingFileHandler("rotation.log", maxBytes=1000000, backupCount= 1)
handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
root = logging.getLogger()
root.setLevel(logging.INFO)
root.addHandler(handler)

def main():
    # Process command line args
    parser = argparse.ArgumentParser(description='Deletes FAZ logs from the MySQL DB before the cutoff date')
    parser.add_argument("-d", "--days", type=int, default=1, help="Number of days behind the cutoff date will be (default: 1)")
    parser.add_argument("table", choices=[0, 1, 2, 3, 4, 5], help="Select table to delete logs from. | 0: All | 1: Dest_Count_Sum | 2: Src_IP_Sum | 3: Top_Dest_Sum_Byte | 4: Top_Dest_Sum_Occur | 5: Traffic_Summary |", type=int)
    args = parser.parse_args()

    selected_table = TABLES[args.table]
    cutoff_time = args.days
    cutoff_date = (datetime.now() - timedelta(days=cutoff_time)).strftime("%Y-%m-%d")
    mydb = database.create_db_connection()

    if selected_table == "All":
        root.warning(f"Deleting logs before: {cutoff_date}, from all tables")
        for table in TABLES[1:]:
            database.remove_logs(mydb, cutoff_date, table)
    else:
        root.warning(f"Deleting logs before: {cutoff_date}, from {selected_table}")
        database.remove_logs(mydb, cutoff_date, selected_table)


if __name__ == "__main__":
    main()