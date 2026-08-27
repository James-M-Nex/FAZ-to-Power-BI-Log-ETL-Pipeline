'''
Configuration and credentials for FortiAnalyzer (FAZ) ETL Pipeline & MySQL Database.
Values can be overridden using environment variables.
'''

import os

## Replace the defaults with the acutal values

# FortiAnalyzer (FAZ) Credentials & Settings
FAZ_URL = os.getenv("FAZ_URL", "DEFAULT URL")
FAZ_USERNAME = os.getenv("FAZ_USERNAME", "DEFAULT USER")
FAZ_PASSWORD = os.getenv("FAZ_PASSWORD", "DEFAULT PASSWORD")

# MySQL Database Credentials & Settings
SQL_SERVER = os.getenv("SQL_SERVER", "DEFAULT SERVER")
SQL_USERNAME = os.getenv("SQL_USERNAME", "DEFAULT USER")
SQL_PASSWORD = os.getenv("SQL_PASSWORD", "DEFAULT PASSWORD")
SQL_DATABASE = os.getenv("SQL_DATABASE", "DEFAULT DATABASE")