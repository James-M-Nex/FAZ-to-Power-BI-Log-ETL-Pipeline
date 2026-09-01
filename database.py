'''
This script takes the summarized logs and inserts them into the MySQL DB.
This script also manages the connection to the DB and log rolling.
Made: 7/24/26
Edited: 8/6/26
Author(s): James Meyers (james.meyers@nexteer.com)
'''

# Standard Imports
import logging

# Third Party Imports
import mssql_python as mssql
import time

# Local Imports
import config

# Setup logger
logger = logging.getLogger(__name__)

def create_db_connection() -> mssql.Connection:
    '''
    Establish a connection to the MySQL server with the username and password arguments.
    Returns a mssql.Connection object if able to connect, otherwise it returns nothing.
    '''

    try:
        mydb = mssql.connect(server=config.SQL_SERVER, database=config.SQL_DATABASE, uid=config.SQL_USERNAME, pwd=config.SQL_PASSWORD, encrypt="yes")
        return mydb
    except Exception as e:
        logger.error("Error occured when attempting to connect to the database. Error: ", e)
        return

def insert_logs(mydb: mssql.Connection, logs: list[dict], table: str, adom: str):
    '''
    Inserts logs into the provided database and table.
    Inserts in batches to avoid timeouts and overloading the server
    '''

    if mydb is None or not logs:
        logger.error(f"Unable to log {table} for {adom} due to no logs or connection")
        return

    cursor = mydb.cursor()

    # Map internal summary table names to their SQL table name and column list
    sql_statements = {
        "traffic_summary": ("traffic_summary",
                            "(interval_start, adom, devname, policyid, policyname, app, appcat, action, srcintf, dstintf, sessions, sentbyte, rcvdbyte, sentpkt, rcvdpkt)"),
        "source_ip_summary": ("source_ip_summary", 
                              "(interval_start, adom, devname, srcip, crlevel, threats, occurences, sentbyte, rcvdbyte)"),
        "destination_count_summary": ("destination_count_summary", 
                                      "(interval_start, adom, devname, unique_destination_count)"),
        "top_destination_summary_byte": ("top_destination_summary_byte",
                                         "(interval_start, adom, devname, dstip, occurences, sentbyte, rcvdbyte)"),
        "top_destination_summary_occurence": ("top_destination_summary_occurence",
                                              "(interval_start, adom, devname, dstip, occurences, sentbyte, rcvdbyte)")
    }

    # Build parameterized SQL query string and transform dict records into tuple rows matching column order
    table_name, col_str = sql_statements[table]
    cols = [c.strip() for c in col_str.strip("()").split(",")]
    placeholders = ", ".join(["?"] * len(cols))
    sql = f"INSERT INTO {table_name} {col_str} VALUES ({placeholders})"
    rows = [tuple(log.get(col) for col in cols) for log in logs]

    # Insert in batches of 1,000 rows with exponential backoff retries for SQL Server lock wait timeouts/deadlocks (Error 1205)
    BATCH_SIZE = 1000
    MAX_RETRIES = 3

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        attempt = 0
        while True:
            try:
                cursor.executemany(sql, batch)
                mydb.commit()
                break
            except mssql.Error as e:
                attempt += 1
                if (getattr(e, 'errno', None) == 1205 or "1205" in str(e)) and attempt <= MAX_RETRIES:
                    wait = 2 ** attempt
                    logger.warning(f"Lock wait timeout (1205) inserting to {table} for {adom}, retry {attempt}/{MAX_RETRIES} after {wait}s")
                    time.sleep(wait)
                    continue
                else:
                    logger.exception(f"Failed inserting logs into {table} for {adom}: {e} Batch: {batch}")
                    raise

    logger.info(f"Inserted logs for {adom}, in table {table} (total rows: {len(rows)})")

def remove_logs(mydb: mssql.Connection, cutoff_date: str, table: str):
    '''
    Deletes logs from the specified SQL Server DB table where interval_start is before the cutoff_date
    '''
    cursor = mydb.cursor()
    sql = f"DELETE FROM {table} WHERE interval_start < '{cutoff_date}'"

    cursor.execute(sql)
    mydb.commit()

    logger.warning(f"{cursor.rowcount} record(s) deleted from {table}")
