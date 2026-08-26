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
import mysql.connector
import time

# Local Imports
import config

# Setup logger
logger = logging.getLogger(__name__)

def create_db_connection(username: str = None, password: str = None) -> mysql.connector.connection.MySQLConnection:
    '''
    Establish a connection to the MySQL server with the username and password arguments.
    Falls back to config settings if username/password are not provided.
    Returns a MySQLConnection object if able to connect, otherwise it returns nothing.
    '''
    user = username or config.SQL_USERNAME
    pwd = password or config.SQL_PASSWORD
    try:
        mydb = mysql.connector.connect(host=config.SQL_HOST, user=user, password=pwd, database=config.SQL_DATABASE, allow_local_infile=True)
        return mydb
    except Exception as e:
        logger.error("Error occured when attempting to connect to the database. Error: ", e)
        return

def insert_logs(mydb: mysql.connector.connection.MySQLConnection, logs: list[dict], table: str, adom: str):
    '''
    Inserts logs into the provided database and table.
    Saves logs to a temp csv file which gets sent to the server to speed up insertion.
    '''

    if mydb is None or not logs:
        return

    cursor = mydb.cursor()

    # Map internal summary table names to their SQL table name, column list, and value placeholders
    sql_statements = {
        "traffic_summary": ("traffic_summary",
                            "(interval_start, adom, devname, policyid, policyname, app, appcat, action, srcintf, dstintf, sessions, sentbyte, rcvdbyte, sentpkt, rcvdpkt)",
                            "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"),
        "source_ip_summary": ("source_ip_summary", 
                              "(interval_start, adom, devname, srcip, occurences, sentbyte, rcvdbyte)",
                              "(%s, %s, %s, %s, %s, %s, %s)"),
        "destination_count_summary": ("destination_count_summary", 
                                      "(interval_start, adom, devname, unique_destination_count)",
                                      "(%s, %s, %s, %s)"),
        "top_destination_summary_byte": ("top_destination_summary_byte",
                                         "(interval_start, adom, devname, dstip, occurences, sentbyte, rcvdbyte)",
                                         "(%s, %s, %s, %s, %s, %s, %s)"),
        "top_destination_summary_occurence": ("top_destination_summary_occurence",
                                              "(interval_start, adom, devname, dstip, occurences, sentbyte, rcvdbyte)",
                                              "(%s, %s, %s, %s, %s, %s, %s)")
    }

    # Build parameterized SQL query string and transform dict records into tuple rows matching column order
    sql = f"INSERT INTO {sql_statements[table][0]} {sql_statements[table][1]} VALUES {sql_statements[table][2]}"
    cols = [c.strip() for c in sql_statements[table][1].strip("()").split(",")]
    rows = [tuple(log.get(col) for col in cols) for log in logs]

    # Insert in batches of 1,000 rows with exponential backoff retries for MySQL lock wait timeouts (Error 1205)
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
            except mysql.connector.errors.DatabaseError as e:
                attempt += 1
                if getattr(e, 'errno', None) == 1205 and attempt <= MAX_RETRIES:
                    wait = 2 ** attempt
                    logger.warning(f"Lock wait timeout (1205) inserting to {table} for {adom}, retry {attempt}/{MAX_RETRIES} after {wait}s")
                    time.sleep(wait)
                    continue
                else:
                    logger.exception(f"Failed inserting logs into {table} for {adom}: {e} Batch: {batch}")
                    raise

    logger.info(f"Inserted logs for {adom}, in table {table} (total rows: {len(rows)})")

def remove_logs(mydb: mysql.connector.connection.MySQLConnection, cutoff_date: str, table: str):
    '''
    Deletes logs from the specified MySQL DB table where any time in a log is before the cutoff_date
    '''
    cursor = mydb.cursor()
    sql = f"DELETE FROM {table} WHERE date < '{cutoff_date}'"

    cursor.execute(sql)
    mydb.commit()

    logger.warning(f"{cursor.rowcount} record(s) deleted from {table}")
