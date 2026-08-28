# FAZ to Power BI Log ETL Pipeline

An automated Python ETL (Extract, Transform, Load) pipeline designed to pull traffic logs from the **FortiAnalyzer (FAZ)** server via its JSONRPC API, normalize and aggregate the log data, and load it into a local **MySQL database**.

This pipeline bridges FortiAnalyzer and **Power BI**, providing structured, aggregated network traffic metrics for high-performance Power BI reporting and dashboards.

---

## 📌 Architecture & Features

- **Multi-ADOM Parallel Processing:** Fetches and processes logs across multiple Administrative Domains (ADOMs): `Asia_Pacific`, `EMEA-SA`, `Labs`, `Mexico`, and `United_States`.
- **Multithreaded Log Fetching:** Uses Python's `ThreadPoolExecutor` to fetch log pages concurrently from the FortiAnalyzer API.
- **Data Normalization & Aggregation:** Extracts essential traffic log attributes and pre-aggregates raw data into summarized metrics (Traffic Summary, Source IP Summary, Unique Destination Counts, Top Destination IPs by bytes and occurrences) to minimize storage footprint and maximize Power BI query speed.
- **MySQL Integration:** Dynamically inserts aggregated logs in batches with automated retry logic for handling lock wait timeouts.
- **Database Indexing:** Pre-indexed MySQL tables for ultra-fast Power BI date range and regional filtering queries.
- **Centralized Configuration:** Configurable via environment variables or central `config.py`.
- **Log Maintenance & Retention:** Includes an automated log rotation tool (`rotate_logs.py`) to purge historical logs past a configured retention threshold.

---

## ⚡ Performance & System Requirements

| Metric / Resource | Recommendation / Benchmark |
| :--- | :--- |
| **System RAM** | **6–8 GB RAM** required (for a 10-minute runtime or less) |
| **Scheduled Interval** | **Every 10 minutes** (via Cron or Task Scheduler) |
| **Expected Execution Time** | **~8:30 minutes** for a 10-minute fetch window (~85% of allotted interval) |
| **Scaling Rule** | Runtime generally takes **~85% of the allotted time window** for different intervals |
| **Python Version** | Python 3.10+ |
| **Database** | MySQL Server 8.0+ (running locally or accessible over network) |

> [!IMPORTANT]
> **Memory & Execution Notice:** Because log records are held in memory during extraction and aggregation before DB insertion, ensure the host machine has at least **6 to 8 GB of available RAM**. When running on a 10-minute recurring schedule, allow ~8.5 minutes for execution completion before starting the next interval.

---

## 📁 Repository Structure

```
.
├── main.py            # Primary ETL pipeline orchestrator & CLI entry point
├── faz_fetcher.py     # FortiAnalyzer JSONRPC API authentication, polling & multi-threaded fetcher
├── transform.py       # Log normalization, field extraction & bucket aggregation logic
├── database.py        # MySQL database connection management & batch insertion engine
├── rotate_logs.py     # Automated log purging utility for old database records
├── config.py          # Centralized configuration module for credentials and server settings
├── utilities/         # Debugging & validation tools
│   ├── check_data_sections.py  # Utility to inspect JSON payload data section completeness
│   └── Methods.py              # Experimental/standalone testing methods for FAZ JSONRPC API
├── app.log            # Execution log file for main pipeline operations
├── rotation.log       # Maintenance log file for log cleanup tasks
└── README.md          # Project documentation
```

---

## 🛠️ Prerequisites & Setup

### 1. Python Dependencies
Ensure Python 3.10+ is installed. Install the required third-party libraries:

```bash
pip install requests urllib3 mysql-connector-python
```

### 2. MySQL Database Setup with Indexing
Create the database and required tables on your MySQL server. Indexes on `interval_start`, `adom`, and `devname` ensure Power BI dashboards load instantly regardless of table size.

```sql
CREATE DATABASE IF NOT EXISTS faz_api_traffic_logs;
USE faz_api_traffic_logs;

-- Traffic Summary Table
CREATE TABLE IF NOT EXISTS traffic_summary (
    id INT AUTO_INCREMENT PRIMARY KEY,
    interval_start DATETIME NOT NULL,
    adom VARCHAR(30) NOT NULL,
    devname VARCHAR(60) NOT NULL,
    policyid INT NOT NULL,
    policyname VARCHAR(60),
    app VARCHAR(60),
    appcat VARCHAR(60),
    action VARCHAR(45),
    srcintf VARCHAR(45),
    dstintf VARCHAR(45),
    sessions INT,
    sentbyte BIGINT,
    rcvdbyte BIGINT,
    sentpkt BIGINT,
    rcvdpkt BIGINT,
    KEY idx_interval_adom (interval_start, adom),
    KEY idx_devname (devname)
);

-- Source IP Summary Table
CREATE TABLE IF NOT EXISTS source_ip_summary (
    id INT AUTO_INCREMENT PRIMARY KEY,
    interval_start DATETIME NOT NULL,
    adom VARCHAR(30) NOT NULL,
    devname VARCHAR(60) NOT NULL,
    srcip VARCHAR(45),
    crlevel VARCHAR(12),
    threats VARCHAR(45),
    occurences INT,
    sentbyte BIGINT,
    rcvdbyte BIGINT,
    KEY idx_interval_adom (interval_start, adom),
    KEY idx_srcip (srcip)
);

-- Destination Count Summary Table
CREATE TABLE IF NOT EXISTS destination_count_summary (
    id INT AUTO_INCREMENT PRIMARY KEY,
    interval_start DATETIME NOT NULL,
    adom VARCHAR(30) NOT NULL,
    devname VARCHAR(60) NOT NULL,
    unique_destination_count INT,
    KEY idx_interval_adom (interval_start, adom)
);

-- Top Destination Summary (by Byte Volume)
CREATE TABLE IF NOT EXISTS top_destination_summary_byte (
    id INT AUTO_INCREMENT PRIMARY KEY,
    interval_start DATETIME NOT NULL,
    adom VARCHAR(30) NOT NULL,
    devname VARCHAR(60) NOT NULL,
    dstip VARCHAR(45),
    occurences INT,
    sentbyte BIGINT,
    rcvdbyte BIGINT,
    KEY idx_interval_adom (interval_start, adom),
    KEY idx_dstip (dstip)
);

-- Top Destination Summary (by Session Occurrences)
CREATE TABLE IF NOT EXISTS top_destination_summary_occurence (
    id INT AUTO_INCREMENT PRIMARY KEY,
    interval_start DATETIME NOT NULL,
    adom VARCHAR(30) NOT NULL,
    devname VARCHAR(60) NOT NULL,
    dstip VARCHAR(45),
    occurences INT,
    sentbyte BIGINT,
    rcvdbyte BIGINT,
    KEY idx_interval_adom (interval_start, adom),
    KEY idx_dstip (dstip)
);
```

#### Why Indexes Matter for Power BI:
Without indexes, MySQL must perform a **full table scan** (reading every single row in the database) to display metrics for a specific date range or region. With `KEY idx_interval_adom` and column-specific indexes, MySQL jumps directly to the matching rows, keeping Power BI query responses under a second.

---

### 3. Credentials & Configuration
All settings and credentials are managed through `config.py`. You can override defaults using system environment variables:

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `FAZ_URL` | `#####` | FortiAnalyzer JSONRPC endpoint |
| `FAZ_USERNAME` | `#####` | FortiAnalyzer API username |
| `FAZ_PASSWORD` | `#####` | FortiAnalyzer API password |
| `SQL_HOST` | `#####` | MySQL server hostname / IP |
| `SQL_USERNAME` | `#####` | MySQL user account |
| `SQL_PASSWORD` | `######` | MySQL password |
| `SQL_DATABASE` | `######` | Target MySQL database name |

---

## 🚀 Usage

### Running the ETL Pipeline (`main.py`)

Execute the pipeline using positional arguments:

```bash
python main.py <adom_index> <time_range_minutes> [options]
```

#### Arguments & Options
- `adom_index` (Required):
  - `0`: All ADOMs (runs staged pipeline execution)
  - `1`: `Asia_Pacific`
  - `2`: `EMEA-SA`
  - `3`: `Labs`
  - `4`: `Mexico`
  - `5`: `United_States`
- `time_range_minutes` (Required): Minutes of log history to pull prior to current time (e.g., `10`).
- `-t`, `--threads` (Optional): Parallel worker thread count (default: `3`).
- `-r`, `--rawLogs` (Optional): Save raw JSON logs to `{adom}rawLogs.txt`.
- `-n`, `--normalizedLogs` (Optional): Save normalized JSON logs to `{adom}normalizedLogs.txt`.

#### Examples

Fetch and process all ADOMs for the last 10 minutes (Recommended for Cron / Scheduled Task):
```bash
python main.py 0 10
```

Fetch only the `United_States` ADOM for the last 15 minutes using 4 threads:
```bash
python main.py 5 15 -t 4
```

---

### Running Log Rotation (`rotate_logs.py`)

Purge records older than a specified number of days to manage MySQL table growth:

```bash
python rotate_logs.py <table_index> [-d DAYS]
```

#### Table Index Mapping:
- `0`: All tables
- `1`: `destination_count_summary`
- `2`: `source_ip_summary`
- `3`: `top_destination_summary_byte`
- `4`: `top_destination_summary_occurence`
- `5`: `traffic_summary`

#### Example (Purge logs older than 7 days from all tables):
```bash
python rotate_logs.py 0 -d 7
```

---

## ⚙️ Cron / Task Scheduler Setup

To ensure continuous data feed into Power BI, set up a recurring task every 10 minutes:

### Linux Cron (crontab):
```cron
*/10 * * * * /usr/bin/python3 /path/to/PythonStuff/main.py 0 10 >> /path/to/PythonStuff/cron.log 2>&1
0 2 * * 0 /usr/bin/python3 /path/to/PythonStuff/rotate_logs.py 0 -d 7 >> /path/to/PythonStuff/rotation.log 2>&1
```

### Windows Task Scheduler:
- **Trigger**: Daily, repeating every **10 minutes** indefinitely.
- **Action**: Start a program (`python.exe`) with arguments `main.py 0 10` in the script directory.

---

## 📝 Logging & Monitoring

- Operational output for the ETL pipeline is recorded in `app.log` using a rotating log handler (1 MB cap per log file).
- Database purge operations are logged in `rotation.log`.

---

## 👤 Author & Support

- **Author:** James Meyers (`james.meyers@nexteer.com`)
- **Project:** FAZ Dashboard / Power BI Connector Pipeline
- **If Your Bored:** Try adding the `-e` flag
