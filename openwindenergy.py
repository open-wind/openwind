# ***********************************************************
# ********************* OPEN WIND ENERGY ********************
# ***********************************************************
# ********** Script to convert data.openwind.energy *********
# ********** data catalogue to composite GIS layers *********
# ***********************************************************
# ***********************************************************
# v1.0

# ***********************************************************
#
# MIT License
#
# Copyright (c) Stefan Haselwimmer, OpenWind.energy, 2025
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import sys
import logging
import json
import requests
import os
import urllib.request
import subprocess
import xmltodict
import shutil
import yaml
import sqlite3
import psycopg2
import time
import math
import geopandas as gpd
import pandas as pd
import shapefile
import multiprocessing
from psycopg2 import errors as postgiserrors
from multiprocessing import Pool, Value
from datetime import datetime
from requests import Request
from pathlib import Path
from owslib.wfs import WebFeatureService
from psycopg2 import sql
from psycopg2.extensions import AsIs
from zipfile import ZipFile
from os import listdir, makedirs
from os.path import isfile, isdir, basename, join, exists
from ckanapi import RemoteCKAN
from dotenv import load_dotenv

# Ideally user has created own .env file. If not copy over template
if not isfile('.env'): 
    print("Default .env file not found, creating it from template")
    shutil.copy('.env-template', '.env')

load_dotenv()

WORKING_FOLDER = str(Path(__file__).absolute().parent) + '/'

BUILD_FOLDER                        = WORKING_FOLDER + 'build-cli/'
QGIS_PYTHON_PATH                    = '/usr/bin/python3'
CKAN_URL                            = 'https://data.openwind.energy'
TILESERVER_URL                      = 'http://localhost:8080'
SERVER_BUILD                        = False

# Allow certain variables to be changed using environment variables

if os.environ.get("SERVER_BUILD") is not None: SERVER_BUILD = True
if os.environ.get("BUILD_FOLDER") is not None: BUILD_FOLDER = os.environ.get('BUILD_FOLDER')
if os.environ.get("QGIS_PYTHON_PATH") is not None: QGIS_PYTHON_PATH = os.environ.get('QGIS_PYTHON_PATH')
if os.environ.get("CKAN_URL") is not None: CKAN_URL = os.environ.get('CKAN_URL')
if os.environ.get("TILESERVER_URL") is not None: TILESERVER_URL = os.environ.get('TILESERVER_URL')

OPENWINDENERGY_VERSION              = "1.0"
TEMP_FOLDER                         = "temp/"
USE_MULTIPROCESSING                 = True
if SERVER_BUILD: USE_MULTIPROCESSING = True
if BUILD_FOLDER == "build-docker/": USE_MULTIPROCESSING = False
DEFAULT_HEIGHT_TO_TIP               = 124.2     # Based on openwind's own manual data on all large (>=75 m to tip-height) failed and successful UK onshore wind projects
DEFAULT_BLADE_RADIUS                = 47.8      # Based on openwind's own manual data on all large (>=75 m to tip-height) failed and successful UK onshore wind projects
HEIGHT_TO_TIP                       = DEFAULT_HEIGHT_TO_TIP
BLADE_RADIUS                        = DEFAULT_BLADE_RADIUS
CUSTOM_CONFIGURATION                = None
CUSTOM_CONFIGURATION_FOLDER         = BUILD_FOLDER + 'configuration/'
CUSTOM_CONFIGURATION_TABLE_PREFIX   = '__'
CUSTOM_CONFIGURATION_FILE_PREFIX    = 'custom--'
LATEST_OUTPUT_FILE_PREFIX           = 'latest--'
OSM_MAIN_DOWNLOAD                   = 'https://download.geofabrik.de/europe/united-kingdom-latest.osm.pbf'
OSM_CONFIG_FOLDER                   = BUILD_FOLDER + 'osm-export-yml/'
OSM_DOWNLOADS_FOLDER                = BUILD_FOLDER + 'osm-downloads/'
OSM_EXPORT_DATA                     = 'osm-export'
OSM_BOUNDARIES                      = 'osm-boundaries'
OSM_BOUNDARIES_YML                  = WORKING_FOLDER + OSM_BOUNDARIES + '.yml'
DATASETS_DOWNLOADS_FOLDER           = BUILD_FOLDER + 'datasets-downloads/'
OSM_LOOKUP                          = BUILD_FOLDER + 'datasets-osm.json'
STRUCTURE_LOOKUP                    = BUILD_FOLDER + 'datasets-structure.json'
BUFFER_LOOKUP                       = BUILD_FOLDER + 'datasets-buffers.json'
STYLE_LOOKUP                        = BUILD_FOLDER + 'datasets-style.json'
MAPAPP_FOLDER                       = BUILD_FOLDER + 'app/'
MAPAPP_JS_STRUCTURE                 = MAPAPP_FOLDER + 'datasets-latest-style.js'
MAPAPP_JS_BOUNDS_CENTER             = MAPAPP_FOLDER + 'bounds-centre.js'
MAPAPP_MAXBOUNDS                    = [[-49.262695,38.548165], [39.990234,64.848937]]
MAPAPP_FITBOUNDS                    = None
MAPAPP_CENTER                       = [-6, 55.273]
TILESERVER_FONTS_GITHUB             = 'https://github.com/openmaptiles/fonts'
TILESERVER_SRC_FOLDER               = WORKING_FOLDER + 'tileserver/'
TILESERVER_FOLDER                   = BUILD_FOLDER + 'tileserver/'
TILESERVER_DATA_FOLDER              = TILESERVER_FOLDER + 'data/'
TILESERVER_STYLES_FOLDER            = TILESERVER_FOLDER + 'styles/'
TILEMAKER_DOWNLOAD_SCRIPT           = TILESERVER_SRC_FOLDER + 'get-coastline-landcover.sh'
TILEMAKER_COASTLINE                 = WORKING_FOLDER + 'coastline/'
TILEMAKER_LANDCOVER                 = WORKING_FOLDER + 'landcover/'
TILEMAKER_COASTLINE_CONFIG          = TILESERVER_SRC_FOLDER + 'config-coastline.json'
TILEMAKER_COASTLINE_PROCESS         = TILESERVER_SRC_FOLDER + 'process-coastline.lua'
TILEMAKER_OMT_CONFIG                = TILESERVER_SRC_FOLDER + 'config-openmaptiles.json'
TILEMAKER_OMT_PROCESS               = TILESERVER_SRC_FOLDER + 'process-openmaptiles.lua'
QGIS_OUTPUT_FILE                    = BUILD_FOLDER + "windconstraints--latest.qgs"
FINALLAYERS_OUTPUT_FOLDER           = BUILD_FOLDER + 'output/'
FINALLAYERS_CONSOLIDATED            = 'windconstraints'
PERFORM_DOWNLOAD                    = True
REGENERATE_INPUT                    = False
REGENERATE_OUTPUT                   = False
OVERALL_CLIPPING_FILE               = 'overall-clipping.gpkg'
WORKING_CRS                         = 'EPSG:4326'
POSTGRES_HOST                       = os.environ.get("POSTGRES_HOST")
POSTGRES_DB                         = os.environ.get("POSTGRES_DB")
POSTGRES_USER                       = os.environ.get("POSTGRES_USER")
POSTGRES_PASSWORD                   = os.environ.get("POSTGRES_PASSWORD")
DEBUG_RUN                           = False
OPENMAPTILES_HOSTED_FONTS           = "https://cdn.jsdelivr.net/gh/open-wind/openmaptiles-fonts/fonts/{fontstack}/{range}.pbf"
SKIP_FONTS_INSTALLATION             = False
CKAN_USER_AGENT                     = 'ckanapi/1.0 (+https://openwind.energy)'
DOWNLOAD_USER_AGENT                 = 'openwindenergy/' + OPENWINDENERGY_VERSION
LOG_SINGLE_PASS                     = WORKING_FOLDER + 'log.txt'
PROCESSING_START                    = None
PROCESSING_STATE_FILE               = 'PROCESSING'
PROCESSING_COMPLETE_FILE            = 'PROCESSINGCOMPLETE'

# Lookup to convert internal areas to OSM names

OSM_NAME_CONVERT                    = \
                                    {
                                        'england': 'England',
                                        'wales': 'Cymru / Wales',
                                        'scotland': 'Alba / Scotland',
                                        'northern-ireland': 'Northern Ireland / Tuaisceart Éireann'
                                    }

# Processing grid is used to cut up core datasets into grid squares
# to reduce memory load on ST_Union. All final layers will have ST_Union
# so it's okay to cut up early datasets before this

PROCESSING_GRID_SPACING             = 500 * 1000 # Size of grid squares in metres, ie. 500km
PROCESSING_GRID_TABLE               = 'uk__processing_grid_' + str(int(PROCESSING_GRID_SPACING)) + '_m'

# Output grid is used to cut up final output into grid squares 
# in order to improve quality and performance of rendering 

OUTPUT_GRID_SPACING                 = 100 * 1000 # Size of grid squares in metres, ie. 100km
OUTPUT_GRID_TABLE                   = 'uk__output_grid__100000_m'

# Redirect ogr2ogr warnings to log file
os.environ['CPL_LOG'] = WORKING_FOLDER + 'log-ogr2ogr.txt'

# ***********************************************************
# ***************** General helper functions ****************
# ***********************************************************

def initLogging():
    """
    Initialises logging
    """

    class PaddedProcessFormatter(logging.Formatter):
        def format(self, record):
            # Pad process ID to 4 digits with leading zeros
            record.process_padded = f"PID:{record.process:08d}"
            return super().format(record)

    log_format = '%(asctime)s,%(msecs)03d [%(process_padded)s] [%(levelname)-2s] %(message)s'
    formatter = PaddedProcessFormatter(log_format, "%Y-%m-%d %H:%M:%S")
    handler_1 = logging.StreamHandler()
    handler_2 = logging.FileHandler(LOG_SINGLE_PASS)
    handler_3 = logging.FileHandler("{0}/{1}.log".format(WORKING_FOLDER, datetime.today().strftime('%Y-%m-%d')))

    handler_1.setFormatter(formatter)
    handler_2.setFormatter(formatter)
    handler_3.setFormatter(formatter)

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(process_padded)s] [%(levelname)-2s] %(message)s',
        handlers=[handler_1, handler_2, handler_3]
    )

def getQueueKey(priority, index):
    """
    Generates dict key from priority and queue index
    """

    # Use float to ensure largest number first; add '9' to prevent loss of '0' in 10, 20...
    return float(str(priority) + "." + str(index) + '9')

def getNumberProcesses():
    """
    Gets number of processes to use in multiprocessing
    If no multiprocessing, then return 1, ie. single process
    """

    global USE_MULTIPROCESSING

    number_processes = 1
    if USE_MULTIPROCESSING: number_processes = None

    return number_processes

def rebuildCommandLine(argv):
    """
    Regenerate full command line from list of arguments
    """

    output_args = []
    for arg in argv:
        if ' ' in arg: arg = "'" + str(arg) + "'"
        output_args.append(arg)

    commandline = ' '.join(output_args)
    commandline = commandline.replace('openwindenergy.py', './build-cli.sh')
    
    return commandline

def convertSHP2GeoJSON(path_shp, path_geojson, dataset_name):
    """
    Convert SHP to GeoJSON using pyshp in low-memory way
    """

    reader = shapefile.Reader(path_shp)
    fields = reader.fields[1:]
    field_names = [field[0] for field in fields]
    geojson = open(path_geojson, "w")
    geojson.write('{"type": "FeatureCollection", "name": "' + dataset_name + '", "features": [')
    numrecords = len(list(reader.iterRecords()))
    recordcount = 0
    for sr in reader.iterShapeRecords():
        atr = dict(zip(field_names, sr.record))
        geom = sr.shape.__geo_interface__
        geojson.write(json.dumps(dict(type="Feature", geometry=geom, properties=atr)))
        recordcount += 1
        if recordcount != numrecords: geojson.write(",\n")
    geojson.write(']}')
    geojson.close()

def getJSON(json_path):
    """
    Gets contents of JSON file
    """

    with open(json_path, "r") as json_file: return json.load(json_file)

def makeFolder(folderpath):
    """
    Make folder if it doesn't already exist
    """

    if folderpath.endswith(os.path.sep): folderpath = folderpath[:-1]
    if not isdir(folderpath): makedirs(folderpath)

def getFilesInFolder(folderpath):
    """
    Get list of all files in folder
    Create folder if it doesn't exist
    """

    makeFolder(folderpath)
    files = [f for f in listdir(folderpath) if ((f != '.DS_Store') and (isfile(join(folderpath, f))))]
    if files is not None: files.sort()
    return files

def LogOutOfMemoryAndQuit():
    """
    Logs out of memory message and quits
    """

    LogError("")
    LogError("*** Build failure likely due to lack of memory ***")
    LogError("If running local install, increase swap disk size to > 10Gb")
    LogError("If running Docker install, increase Docker swap size by editing Docker config file:")
    LogError("1. Edit Docker config file - for locations see https://docs.docker.com/desktop/settings-and-maintenance/settings/")
    LogError("2. Modify 'SwapMiB' and set to 10000")
    LogError("3. Fully quit and restart Docker for new 'SwapMiB' setting to take effect")
    LogError("4. Rerun ./build-docker.sh")

    exit()

def LogMessage(logtext):
    """
    Logs message to console with timestamp
    """

    logger = multiprocessing.get_logger()
    logging.info(logtext)

def LogWarning(logtext):
    """
    Logs warning message to console with timestamp
    """

    logger = multiprocessing.get_logger()
    logging.warning(logtext)

def LogError(logtext):
    """
    Logs error message to console with timestamp
    """

    logger = multiprocessing.get_logger()
    logging.error("*** ERROR *** " + logtext)

def LogFatalError(logtext):
    """
    Logs error message to console with timestamp and aborts
    """

    LogError(logtext)
    exit()

def attemptDownloadUntilSuccess(url, file_path):
    """
    Keeps attempting download until successful
    """

    while True:
        try:
            urllib.request.urlretrieve(url, file_path)
            return
        except Exception as e:
            LogWarning("Attempt to retrieve " + url + " failed so retrying")
            time.sleep(5)

def attemptGETUntilSuccess(url):
    """
    Keeps attempting GET request until successful
    """

    while True:
        try:
            response = requests.get(url)
            return response
        except Exception as e:
            LogWarning("Attempt to retrieve " + url + " failed so retrying")
            time.sleep(5)

def attemptPOSTUntilSuccess(url, params):
    """
    Keeps attempting POST request until successful
    """

    while True:
        try:
            response = requests.post(url, params)
            return response
        except:
            LogWarning("Attempt to retrieve " + url + " failed so retrying")
            time.sleep(5)

def isfloat(val):
    """
    Checks whether string represents float
    From http://stackoverflow.com/questions/736043/checking-if-a-string-can-be-converted-to-float-in-python
    """
    #If you expect None to be passed:
    if val is None:
        return False
    try:
        float(val)
        return True
    except ValueError:
        return False

def reformatGeoJSON(file_path):
    """
    Reformats GeoJSON file by removing 'name' attribute which causes problems when querying with sqlite
    """

    if '.geojson' not in basename(file_path): return

    geojson_data = {}
    with open(file_path) as f:
        geojson_data = json.load(f)
        if 'name' in geojson_data: del geojson_data['name']

    with open(file_path, "w") as json_file: json.dump(geojson_data, json_file) 

def osmDownloadData():
    """
    Downloads core OSM data
    """

    global  BUILD_FOLDER, OSM_MAIN_DOWNLOAD, OSM_DOWNLOADS_FOLDER, TILEMAKER_DOWNLOAD_SCRIPT, TILEMAKER_COASTLINE, TILEMAKER_LANDCOVER, TILEMAKER_COASTLINE_CONFIG

    makeFolder(BUILD_FOLDER)
    makeFolder(OSM_DOWNLOADS_FOLDER)

    if not isfile(OSM_DOWNLOADS_FOLDER + basename(OSM_MAIN_DOWNLOAD)):

        LogMessage("Downloading latest OSM data")

        # Download to temp file in case download interrupted for any reason, eg. user clicks 'Stop processing'

        download_temp = OSM_DOWNLOADS_FOLDER + 'temp.pbf'
        if isfile(download_temp): os.remove(download_temp)

        runSubprocess(["wget", OSM_MAIN_DOWNLOAD, "-O", download_temp])

        shutil.copy(download_temp, OSM_DOWNLOADS_FOLDER + basename(OSM_MAIN_DOWNLOAD))
        if isfile(download_temp): os.remove(download_temp)

    LogMessage("Checking all files required for OSM tilemaker...")

    shp_extensions = ['shp', 'shx', 'dbf', 'prj']
    tilemaker_config_json = getJSON(TILEMAKER_COASTLINE_CONFIG)
    tilemaker_config_layers = list(tilemaker_config_json['layers'].keys())

    all_tilemaker_layers_downloaded = True
    for layer in tilemaker_config_layers:
        layer_elements = tilemaker_config_json['layers'][layer]
        if 'source' in layer_elements:
            for shp_extension in shp_extensions:
                source_file = layer_elements['source'].replace('.shp', '.' + shp_extension)
                if not isfile(source_file):
                    LogMessage("Missing file for OSM tilemaker: " + source_file)
                    all_tilemaker_layers_downloaded = False

    if all_tilemaker_layers_downloaded:
        LogMessage("All files downloaded for OSM tilemaker")
    else:
        LogMessage("Downloading global water and coastline data for OSM tilemaker")
        runSubprocess([TILEMAKER_DOWNLOAD_SCRIPT])

# ***********************************************************
# **************** Multiprocessing functions ****************
# ***********************************************************

def init_globals_boolean(global_bool):
    """
    Manages multiprocessing variables - boolean
    """

    global global_boolean
    global_boolean = global_bool

def init_globals_count(global_cnt):
    """
    Manages multiprocessing variables - count
    """

    global global_count
    global_count = global_cnt

def init_globals_boolean_count(global_bool, global_cnt):
    """
    Manages multiprocessing variables - boolean and count
    """

    global global_boolean, global_count
    global_boolean = global_bool
    global_count = global_cnt

def buildQueuePrefix(queue_id):
    """
    Builds queue prefix string for easier tracking in log files 
    """

    return "[QID:" + str(queue_id).zfill(4) + "] "

def multiprocessDivideChunks(queue_dict, chunksize):
    """
    Splits list of queue items into separate chunks so key field, 
    eg. file size, number records, is more evenly shared across chunks
    This means separate processes can start with parallel largest problems first
    """

    queue_dict = dict(sorted(queue_dict.items(), reverse=True))
    queue_datasets_largest_first = [queue_dict[item] for item in queue_dict]
    processes = math.ceil(len(queue_dict) / chunksize)

    queue_index, chunk_items = 0, {}
    for chunk in range(chunksize):
        for process in range(processes):
            if queue_index >= len(queue_datasets_largest_first): break
            chunk_index = chunk + (process * chunksize)
            chunk_items[chunk_index] = queue_datasets_largest_first[queue_index]
            queue_index += 1
        if queue_index >= len(queue_datasets_largest_first): break

    chunk_dict = dict(sorted(chunk_items.items()))
    queue_datasets = [chunk_dict[item] for item in chunk_dict]
    
    if len(queue_dict) != len(queue_datasets):
        LogError("multiprocessDivideChunks: Mismatched counts")
        exit()

    return queue_datasets

def multiprocessBefore():
    """
    Run code before multiprocessing is started
    """

    LogMessage("************************************************")
    LogMessage("********** STARTING MULTIPROCESSING ************")
    LogMessage("************************************************")

def multiprocessAfter():
    """
    Run code after multiprocessing has finished
    """

    LogMessage("************************************************")
    LogMessage("*********** ENDING MULTIPROCESSING *************")
    LogMessage("************************************************")

def singleprocessFileCopy(copy_parameters):
    """
    Single process file copy using copy_parameters
    """

    copy_description, file_src, file_dst = copy_parameters[0], copy_parameters[1], copy_parameters[2]

    LogMessage(copy_description)

    shutil.copy(file_src, file_dst)

def multiprocessFileCopy(queue_files):
    """
    Copies files using multiprocessing to save time
    """

    if len(queue_files) == 0: return
        
    multiprocessBefore()

    chunksize = int(len(queue_files) / multiprocessing.cpu_count()) + 1

    with Pool(processes=getNumberProcesses()) as p: p.map(singleprocessFileCopy, queue_files, chunksize=chunksize)

    multiprocessAfter()

def singleprocessDownload(download_parameters):
    """
    Single process download using download_parameters
    """

    global DOWNLOAD_USER_AGENT

    download_description, url, file_dst = download_parameters[0], download_parameters[1], download_parameters[2]

    LogMessage(download_description)

    opener = urllib.request.build_opener()
    opener.addheaders = [('User-Agent', DOWNLOAD_USER_AGENT)]
    urllib.request.install_opener(opener)
    attemptDownloadUntilSuccess(url, file_dst)

def multiprocessDownload(queue_download):
    """
    Downloads files using multiprocessing to save time
    """

    if len(queue_download) == 0: return

    multiprocessBefore()

    chunksize = int(len(queue_download) / multiprocessing.cpu_count()) + 1

    with Pool(processes=getNumberProcesses()) as p: p.map(singleprocessDownload, queue_download, chunksize=chunksize)

    multiprocessAfter()

def singleprocessSubprocess(subprocess_parameters):
    """
    Single process subprocess using subprocess_parameters
    """

    output_text, subprocess_array = subprocess_parameters[0], subprocess_parameters[1]

    LogMessage("STARTING: " + output_text)

    runSubprocess(subprocess_array)

    LogMessage("FINISHED: " + output_text)

def multiprocessSubprocess(queue_subprocess):
    """
    Runs subprocess using multiprocessing to save time
    """

    if len(queue_subprocess) == 0: return

    multiprocessBefore()

    chunksize = int(len(queue_subprocess) / multiprocessing.cpu_count()) + 1

    with Pool(processes=getNumberProcesses()) as p: p.map(singleprocessSubprocess, queue_subprocess, chunksize=chunksize)

    multiprocessAfter()

# ***********************************************************
# ******************** PostGIS functions ********************
# ***********************************************************

def postgisWaitRunning():
    """
    Wait until PostGIS is running
    """

    global POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD

    LogMessage("Attempting connection to PostGIS...")

    while True:
        try:
            conn = psycopg2.connect(host=POSTGRES_HOST, dbname=POSTGRES_DB, user=POSTGRES_USER, password=POSTGRES_PASSWORD)
            cur = conn.cursor()
            cur.close()
            break
        except:
            time.sleep(5)

    LogMessage("Connection to PostGIS successful")

def postgisGetAllTables():
    """
    Gets list of all tables
    """

    global POSTGRES_DB

    all_tables = postgisGetResults(r"""
    SELECT tables.table_name
    FROM information_schema.tables
    WHERE 
    table_catalog=%s AND 
    table_schema='public' AND 
    table_type='BASE TABLE' AND
    table_name NOT IN ('spatial_ref_sys')
    ORDER BY table_name;
    """, (POSTGRES_DB, ))
    return [table[0] for table in all_tables]

def postgisCheckTableExists(table_name):
    """
    Checks whether table already exists
    """

    global POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD

    table_name = table_name.replace("-", "_")
    conn = psycopg2.connect(host=POSTGRES_HOST, dbname=POSTGRES_DB, user=POSTGRES_USER, password=POSTGRES_PASSWORD)
    cur = conn.cursor()
    cur.execute("SELECT EXISTS(SELECT * FROM information_schema.tables WHERE table_name=%s);", (table_name, ))
    tableexists = cur.fetchone()[0]
    cur.close()
    return tableexists

def postgisCheckColumnExists(table_name, column_name):
    """
    Checks whether column exists in table
    """

    global POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD

    table_name = reformatTableName(table_name)
    conn = psycopg2.connect(host=POSTGRES_HOST, dbname=POSTGRES_DB, user=POSTGRES_USER, password=POSTGRES_PASSWORD)
    cur = conn.cursor()
    cur.execute("SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name=%s AND column_name=%s);", (table_name, column_name, ))
    columnexists = cur.fetchone()[0]
    cur.close()
    return columnexists

def postgisExec(sql_text, sql_parameters):
    """
    Executes SQL statement
    """

    global POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD

    conn = psycopg2.connect(host=POSTGRES_HOST, dbname=POSTGRES_DB, user=POSTGRES_USER, password=POSTGRES_PASSWORD, \
                            keepalives=1, keepalives_idle=30, keepalives_interval=5, keepalives_count=5)
    cur = conn.cursor()
    cur.execute(sql_text, sql_parameters)
    conn.commit()
    conn.close()

def postgisGetResults(sql_text, sql_parameters):
    """
    Runs database query and returns results
    """

    global POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD

    conn = psycopg2.connect(host=POSTGRES_HOST, dbname=POSTGRES_DB, user=POSTGRES_USER, password=POSTGRES_PASSWORD)
    cur = conn.cursor()
    cur.execute(sql_text, sql_parameters)
    results = cur.fetchall()
    conn.close()
    return results

def postgisGetNumberRecords(table_name):
    """
    Gets number of records in table
    """

    results = postgisGetResults("SELECT COUNT(*) FROM %s;", (AsIs(table_name), ))
    return results[0][0]

def postgisGetTableSize(table_name):
    """
    Gets size of table
    """

    results = postgisGetResults("SELECT pg_relation_size(%s);", (table_name, ))
    return results[0][0]

def postgisGetCustomTables():
    """
    Gets list of all custom configuration tables in database
    """

    global CUSTOM_CONFIGURATION_TABLE_PREFIX

    custom_configuration_prefix_escape = CUSTOM_CONFIGURATION_TABLE_PREFIX.replace(r'_', r'\_')

    return postgisGetResults(r"""
    SELECT tables.table_name
    FROM information_schema.tables
    WHERE 
    table_catalog=%s AND 
    table_schema='public' AND 
    table_type='BASE TABLE' AND
    table_name NOT IN ('spatial_ref_sys') AND 
    table_name LIKE '""" + custom_configuration_prefix_escape + r"""%%' 
    ORDER BY table_name;
    """, (POSTGRES_DB, ))

def postgisGetDerivedTables():
    """
    Gets list of all derived tables in database
    """

    # Derived tables:
    # Any 'buf'fered
    # Any 'pro'cessed
    # Any final layer 'tip_...'

    return postgisGetResults(r"""
    SELECT tables.table_name
    FROM information_schema.tables
    WHERE 
    table_catalog=%s AND 
    table_schema='public' AND 
    table_type='BASE TABLE' AND
    table_name NOT IN ('spatial_ref_sys') AND
    (
        (table_name LIKE '%%\_\_buf\_%%') OR 
        (table_name LIKE '%%\_\_pro') OR 
        (table_name LIKE 'tip\_%%') 
    )
    ORDER BY table_name;
    """, (POSTGRES_DB, ))

def postgisGetLegacyTables():
    """
    Gets list of all legacy tables in database
    """

    # Legacy tables:
    # public_roads_a_and_b_roads_and_motorways__uk
    # tipheight_...

    return postgisGetResults(r"""
    SELECT tables.table_name
    FROM information_schema.tables
    WHERE 
    table_catalog=%s AND 
    table_schema='public' AND 
    table_type='BASE TABLE' AND
    table_name NOT IN ('spatial_ref_sys') AND
    (
        (table_name LIKE 'public\_roads\_a\_and\_b\_roads\_and\_motorways\_\_uk%%') OR
        (table_name LIKE 'tipheight\_%%')
    );
    """, (POSTGRES_DB, ))

def postgisGetAmalgamatedTables():
    """
    Gets list of all amalgamated tables in database
    """

    return postgisGetResults(r"""
    SELECT tables.table_name
    FROM information_schema.tables
    WHERE 
    table_catalog=%s AND 
    table_schema='public' AND 
    table_type='BASE TABLE' AND
    table_name NOT IN ('spatial_ref_sys') AND
    table_name LIKE 'tip\_%%';
    """, (POSTGRES_DB, ))

def postgisDropTable(table_name):
    """
    Drops PostGIS table
    """

    postgisExec("DROP TABLE IF EXISTS %s", (AsIs(table_name), ))

def postgisDropAllTables():
    """
    Drops all tables in schema
    """

    global OSM_BOUNDARIES

    # ignore_tables = [reformatTableName(OSM_BOUNDARIES)]
    ignore_tables = []
    all_tables = postgisGetAllTables()

    for table in all_tables:
        if table in ignore_tables: continue
        postgisDropTable(table)

def postgisDropCustomTables():
    """
    Drops all custom configuration tables in schema
    """

    customtables = postgisGetCustomTables()

    for table in customtables:
        table_name, = table
        LogMessage(" --> Dropping custom table: " + table_name)
        postgisDropTable(table_name)

def postgisDropDerivedTables():
    """
    Drops all derived tables in schema
    """

    LogMessage(" --> Dropping all tip_*, *__pro and *__buf_* tables")

    derivedtables = postgisGetDerivedTables()

    for table in derivedtables:
        table_name, = table
        postgisDropTable(table_name)

def postgisDropLegacyTables():
    """
    Drops all legacy tables in schema
    """

    legacytables = postgisGetLegacyTables()

    for table in legacytables:
        table_name, = table
        LogMessage("Removing legacy table: " + table_name)
        postgisDropTable(table_name)

def postgisDropAmalgamatedTables():
    """
    Drops all amalgamated tables in schema
    """

    LogMessage(" --> Dropping all tip_... tables")

    derivedtables = postgisGetAmalgamatedTables()

    for table in derivedtables:
        table_name, = table
        postgisDropTable(table_name)

def postgisDumpGeometriesInBatches(input_table, output_table, batch_size=500):
    """
    Dumps multi-geometries into single geometries in batches to avoid memory issues.
    Creates a new table with individual geometries.
    """

    if postgisCheckTableExists(output_table): postgisDropTable(output_table)

    postgisExec("CREATE TABLE %s (id SERIAL PRIMARY KEY, geom geometry);", (AsIs(output_table), ))

    results = postgisGetResults("SELECT id FROM %s;", (AsIs(input_table), ))
    all_ids = [row[0] for row in results]

    LogMessage(f"postgisDumpGeometriesInBatches: Processing {len(all_ids)} features...")

    # Process in batches
    for i in range(0, len(all_ids), batch_size):
        batch_ids = all_ids[i:i + batch_size]
        LogMessage(f"postgisDumpGeometriesInBatches: [Batch {i // batch_size + 1}] Dumping {len(batch_ids)} features...")

        postgisExec(f"INSERT INTO %s(geom) SELECT (ST_Dump(geom)).geom FROM %s WHERE id = ANY(%s) AND ST_IsValid(geom)", (AsIs(output_table), AsIs(input_table), batch_ids,))

    LogMessage("postgisDumpGeometriesInBatches: Done.")

def singleprocessAmalgamateAndDissolveGridSquareStep1(process_parameters):
    """
    Process single cell of grid square - to allow multiprocessing over multiple cells
    """

    target_table, grid_square_index, grid_square_count, grid_square_id, scratch_table_1, processing_grid, children_sql = \
        process_parameters[0], process_parameters[1], process_parameters[2], process_parameters[3], process_parameters[4], process_parameters[5], process_parameters[6]

    with global_count.get_lock():
        LogMessage("STARTING: " + target_table + ": Grid square " + str(grid_square_index + 1) + "/" + str(grid_square_count) + " [" + str(global_count.value) + " grid square(s) to be processed]")

    try:

        postgisExec("""
        INSERT INTO %s 
            SELECT final.id, final.geom
            FROM
            (
                SELECT 
                    grid.id, 
                    (ST_Dump(ST_Intersection(grid.geom, children.geom))).geom geom
                FROM %s grid, (%s) AS children 
                WHERE grid.id = %s
            ) final WHERE ST_geometrytype(final.geom) = 'ST_Polygon';""", (AsIs(scratch_table_1), AsIs(processing_grid), AsIs(children_sql), AsIs(grid_square_id), ))

    except postgiserrors.InternalError as e:

        LogMessage("ERROR using default SQL, retrying with ST_MakeValid wrapper")

        postgisExec("""
            INSERT INTO %s 
                SELECT final.id, final.geom
                FROM (
                    SELECT 
                        grid.id, 
                        (ST_Dump(ST_Intersection(
                            grid.geom,
                            ST_MakeValid(children.geom)
                        ))).geom AS geom
                    FROM %s grid, (%s) AS children 
                    WHERE grid.id = %s
                ) final 
                WHERE ST_GeometryType(final.geom) = 'ST_Polygon';
        """, (AsIs(scratch_table_1), AsIs(processing_grid), AsIs(children_sql), AsIs(grid_square_id)))

    with global_count.get_lock():
        global_count.value -= 1
        LogMessage("FINISHED: " + target_table + ": Grid square " + str(grid_square_index + 1) + "/" + str(grid_square_count) + " [" + str(global_count.value) + " grid square(s) to be processed]")

def singleprocessAmalgamateAndDissolveGridSquareStep2(process_parameters):
    """
    Process single cell of grid square - to allow multiprocessing over multiple cells
    """

    target_table, grid_square_index, grid_square_count, grid_square_id, scratch_table_1, scratch_table_2 = \
        process_parameters[0], process_parameters[1], process_parameters[2], process_parameters[3], process_parameters[4], process_parameters[5] 

    with global_count.get_lock():
        LogMessage("STARTING: " + target_table + ": Grid square " + str(grid_square_index + 1) + "/" + str(grid_square_count) + " [" + str(global_count.value) + " grid square(s) to be processed]")

    postgisExec("""
    INSERT INTO %s 
        SELECT final.geom
        FROM
        (SELECT (ST_Dump(ST_Union(geom))).geom geom FROM %s AS dataset WHERE id = %s) final 
        WHERE ST_geometrytype(final.geom) = 'ST_Polygon';""", (AsIs(scratch_table_2), AsIs(scratch_table_1), AsIs(grid_square_id), ))

    with global_count.get_lock():
        global_count.value -= 1
        LogMessage("FINISHED: " + target_table + ": Grid square " + str(grid_square_index + 1) + "/" + str(grid_square_count) + " [" + str(global_count.value) + " grid square(s) to be processed]")

def multiprocessAmalgamateAndDissolve(amalgamate_parameters):
    """
    Amalgamates and dissolves all child tables into target table 
    Uses multiprocessing to process grid squares to save time
    """

    amalgamate_id, amalgamate_output, target_table, child_tables, processing_grid_table = amalgamate_parameters[0], amalgamate_parameters[1], amalgamate_parameters[2], amalgamate_parameters[3], amalgamate_parameters[4]

    LogMessage(amalgamate_output)

    amalgamate_id = str(amalgamate_id).zfill(4)

    processing_grid = reformatTableName(processing_grid_table)
    grid_square_ids = postgisGetResults("SELECT id FROM %s;", (AsIs(processing_grid), ))
    grid_square_ids = [item[0] for item in grid_square_ids]
    grid_square_count = len(grid_square_ids)

    scratch_table_1 = '_scratch_table_1_' + amalgamate_id
    scratch_table_2 = '_scratch_table_2_' + amalgamate_id
    scratch_table_3 = '_scratch_table_3_' + amalgamate_id

    # We run process on all children - even if only one child - as process runs
    # ST_Union (dissolve) on datasets for first time to eliminate overlapping polygons

    all_tables_have_id = True
    for table_name in child_tables:
        if not postgisCheckColumnExists(table_name, 'id'): all_tables_have_id = False

    if postgisCheckTableExists(scratch_table_1): postgisDropTable(scratch_table_1)
    if postgisCheckTableExists(scratch_table_2): postgisDropTable(scratch_table_2)
    if postgisCheckTableExists(scratch_table_3): postgisDropTable(scratch_table_3)

    LogMessage("STARTING: Amalgamation and dissolving for: " + target_table)

    LogMessage(target_table + ": Amalgamate and dump all tables")

    if all_tables_have_id:
        children_sql = " UNION ".join(['SELECT id, geom FROM ' + table_name for table_name in child_tables])
        postgisExec("CREATE TABLE %s AS SELECT children.id, (ST_Dump(children.geom)).geom geom FROM (%s) AS children;", \
                    (AsIs(scratch_table_1), AsIs(children_sql), ))
    else:
        children_sql = " UNION ".join(['SELECT geom FROM ' + table_name for table_name in child_tables])

        postgisExec("CREATE TABLE %s (id INTEGER, geom GEOMETRY(Polygon, 4326));", (AsIs(scratch_table_1), ))

        grid_process_queue = []
        for grid_square_index in range(len(grid_square_ids)):
            grid_square_id = grid_square_ids[grid_square_index]
            grid_process_queue.append([target_table, grid_square_index, grid_square_count, grid_square_id, scratch_table_1, processing_grid, children_sql])

        if len(grid_process_queue) != 0:

            num_cells_to_process = Value('i', len(grid_process_queue))
            chunksize = int(len(grid_process_queue) / multiprocessing.cpu_count()) + 1

            multiprocessBefore()

            with Pool(processes=getNumberProcesses(), initializer=init_globals_count, initargs=(num_cells_to_process, )) as p: 
                p.map(singleprocessAmalgamateAndDissolveGridSquareStep1, grid_process_queue, chunksize=chunksize)

            multiprocessAfter()

        postgisExec("CREATE INDEX %s ON %s USING GIST (geom);", (AsIs(scratch_table_1 + "_idx"), AsIs(scratch_table_1), ))

    postgisExec("CREATE INDEX %s ON %s(id);", (AsIs(scratch_table_1 + 'id_idx'), AsIs(scratch_table_1), ))

    LogMessage(target_table + ": Dissolve all geometries for each processing grid square")

    postgisExec("CREATE TABLE %s (geom GEOMETRY(Polygon, 4326));", (AsIs(scratch_table_2), ))

    grid_process_queue = []
    for grid_square_index in range(len(grid_square_ids)):
        grid_square_id = grid_square_ids[grid_square_index]
        grid_process_queue.append([target_table, grid_square_index, grid_square_count, grid_square_id, scratch_table_1, scratch_table_2])

    if len(grid_process_queue) != 0:

        num_cells_to_process = Value('i', len(grid_process_queue))
        chunksize = int(len(grid_process_queue) / multiprocessing.cpu_count()) + 1

        multiprocessBefore()

        with Pool(processes=getNumberProcesses(), initializer=init_globals_count, initargs=(num_cells_to_process, )) as p: 
            p.map(singleprocessAmalgamateAndDissolveGridSquareStep2, grid_process_queue, chunksize=chunksize)

        multiprocessAfter()

    postgisExec("CREATE INDEX %s ON %s USING GIST (geom);", (AsIs(scratch_table_2 + "_idx"), AsIs(scratch_table_2), ))

    LogMessage(target_table + ": Dissolve all geometries across all processing grid squares")

    postgisExec("CREATE TABLE %s AS SELECT ST_Union(geom) geom FROM %s;", \
                (AsIs(scratch_table_3), AsIs(scratch_table_2), ))

    LogMessage(target_table + ": Save dumped geometries")

    # postgisDumpGeometriesInBatches(scratch_table_3, target_table)
    postgisExec("CREATE TABLE %s AS SELECT (ST_Dump(geom)).geom geom FROM %s;", \
                (AsIs(target_table), AsIs(scratch_table_3), ))

    postgisExec("CREATE INDEX %s ON %s USING GIST (geom);", (AsIs(target_table + "_idx"), AsIs(target_table), ))

    LogMessage("FINISHED: Created amalgamated and dissolved table: " + target_table)

    if postgisCheckTableExists(scratch_table_1): postgisDropTable(scratch_table_1)
    if postgisCheckTableExists(scratch_table_2): postgisDropTable(scratch_table_2)
    if postgisCheckTableExists(scratch_table_3): postgisDropTable(scratch_table_3)

def postgisAmalgamateAndDissolve(amalgamate_parameters):
    """
    Amalgamates and dissolves all child tables into target table 
    """

    global CUSTOM_CONFIGURATION, PROCESSING_GRID_TABLE

    amalgamate_id, amalgamate_output, target_table, child_tables, PROCESSING_GRID_TABLE, CUSTOM_CONFIGURATION = \
        amalgamate_parameters[0], amalgamate_parameters[1], amalgamate_parameters[2], amalgamate_parameters[3], amalgamate_parameters[4], amalgamate_parameters[5]

    amalgamate_id = str(amalgamate_id).zfill(4)
    prefix = buildQueuePrefix(amalgamate_id)
    processing_grid = reformatTableName(PROCESSING_GRID_TABLE)
    grid_square_ids = postgisGetResults("SELECT id FROM %s;", (AsIs(processing_grid), ))
    grid_square_ids = [item[0] for item in grid_square_ids]
    grid_square_count = len(grid_square_ids)

    scratch_table_1 = '_scratch_table_1_' + amalgamate_id
    scratch_table_2 = '_scratch_table_2_' + amalgamate_id
    scratch_table_3 = '_scratch_table_3_' + amalgamate_id

    # We run process on all children - even if only one child - as process runs
    # ST_Union (dissolve) on datasets for first time to eliminate overlapping polygons

    all_tables_have_id = True
    for table_name in child_tables:
        if not postgisCheckColumnExists(table_name, 'id'): all_tables_have_id = False

    if postgisCheckTableExists(scratch_table_1): postgisDropTable(scratch_table_1)
    if postgisCheckTableExists(scratch_table_2): postgisDropTable(scratch_table_2)
    if postgisCheckTableExists(scratch_table_3): postgisDropTable(scratch_table_3)

    LogMessage(prefix + "STARTING: Amalgamation and dissolving for: " + target_table)

    LogMessage(prefix + target_table + ": Amalgamate and dump all tables")

    if all_tables_have_id:
        children_sql = " UNION ".join(['SELECT id, geom FROM ' + table_name for table_name in child_tables])
        postgisExec("CREATE TABLE %s AS SELECT children.id, (ST_Dump(children.geom)).geom geom FROM (%s) AS children;", \
                    (AsIs(scratch_table_1), AsIs(children_sql), ))
    else:
        children_sql = " UNION ".join(['SELECT geom FROM ' + table_name for table_name in child_tables])

        postgisExec("CREATE TABLE %s (id INTEGER, geom GEOMETRY(Polygon, 4326));", (AsIs(scratch_table_1), ))

        for grid_square_index in range(len(grid_square_ids)):
            grid_square_id = grid_square_ids[grid_square_index]

            LogMessage(prefix + target_table + " Generating grid square " + str(grid_square_index + 1) + "/" + str(grid_square_count))

            postgisExec("""
            INSERT INTO %s 
                SELECT final.id, final.geom
                FROM
                (
                    SELECT 
                        grid.id, 
                        (ST_Dump(ST_Intersection(grid.geom, children.geom))).geom geom
                    FROM %s grid, (%s) AS children 
                    WHERE grid.id = %s
                ) final WHERE ST_geometrytype(final.geom) = 'ST_Polygon';""", (AsIs(scratch_table_1), AsIs(processing_grid), AsIs(children_sql), AsIs(grid_square_id), ))

        postgisExec("CREATE INDEX %s ON %s USING GIST (geom);", (AsIs(scratch_table_1 + "_idx"), AsIs(scratch_table_1), ))

    postgisExec("CREATE INDEX %s ON %s(id);", (AsIs(scratch_table_1 + 'id_idx'), AsIs(scratch_table_1), ))

    LogMessage(prefix + target_table + ": Dissolve all geometries for each processing grid square")

    postgisExec("CREATE TABLE %s (geom GEOMETRY(Polygon, 4326));", (AsIs(scratch_table_2), ))

    for grid_square_index in range(len(grid_square_ids)):
        grid_square_id = grid_square_ids[grid_square_index]

        LogMessage(prefix + target_table + ": Dissolving grid square " + str(grid_square_index + 1) + "/" + str(grid_square_count))

        postgisExec("""
        INSERT INTO %s 
            SELECT final.geom
            FROM
            (SELECT (ST_Dump(ST_Union(geom))).geom geom FROM %s AS dataset WHERE id = %s) final 
            WHERE ST_geometrytype(final.geom) = 'ST_Polygon';""", (AsIs(scratch_table_2), AsIs(scratch_table_1), AsIs(grid_square_id), ))

    postgisExec("CREATE INDEX %s ON %s USING GIST (geom);", (AsIs(scratch_table_2 + "_idx"), AsIs(scratch_table_2), ))

    LogMessage(prefix + target_table + ": Dissolve all geometries across all processing grid squares")

    postgisExec("CREATE TABLE %s AS SELECT ST_Union(geom) geom FROM %s;", \
                (AsIs(scratch_table_3), AsIs(scratch_table_2), ))

    LogMessage(prefix + target_table + ": Save dumped geometries")

    try:
        postgisExec("CREATE TABLE %s AS SELECT (ST_Dump(geom)).geom geom FROM %s;", \
                    (AsIs(target_table), AsIs(scratch_table_3), ))
    except postgiserrors.InternalError_ as e:
        LogMessage("Postgis error: Geometry possibly too complex - simplifying")
        postgisExec("CREATE TABLE %s AS SELECT (ST_Dump(ST_Simplify(geom, 0.00001))).geom AS geom FROM %s;", 
                    (AsIs(target_table), AsIs(scratch_table_3),))

    postgisExec("CREATE INDEX %s ON %s USING GIST (geom);", (AsIs(target_table + "_idx"), AsIs(target_table), ))

    with global_count.get_lock(): 
        global_count.value -= 1
        LogMessage(prefix + "FINISHED: Created amalgamated and dissolved table: " + target_table + " [" + str(global_count.value) + " dataset(s) to be processed]")

    if postgisCheckTableExists(scratch_table_1): postgisDropTable(scratch_table_1)
    if postgisCheckTableExists(scratch_table_2): postgisDropTable(scratch_table_2)
    if postgisCheckTableExists(scratch_table_3): postgisDropTable(scratch_table_3)

def postgisGetTableBounds(table_name):
    """
    Get bounds of all geometries in table
    """

    global POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD

    conn = psycopg2.connect(host=POSTGRES_HOST, dbname=POSTGRES_DB, user=POSTGRES_USER, password=POSTGRES_PASSWORD)
    cur = conn.cursor()
    cur.execute("""
    SELECT 
        MIN(ST_XMin(geom)) AS left,
        MIN(ST_YMin(geom)) AS bottom,
        MAX(ST_XMax(geom)) AS right,
        MAX(ST_YMax(geom)) AS top FROM %s;
    """, (AsIs(table_name), ))
    left, bottom, right, top = cur.fetchone()
    conn.close()
    return {'left': left, 'bottom': bottom, 'right': right, 'top': top}

def subprocessGetLayerName(subprocess_array):
    """
    Gets layer name from subprocess array
    """

    for index in range(len(subprocess_array)):
        if subprocess_array[index] == '-nln': return subprocess_array[index + 1].replace("-", "_")

    return None

def runSubprocessWithEnv(subprocess_array, env):
    """
    Runs subprocess with environment variables
    """

    output = subprocess.run(subprocess_array, env=env)

    # print("\n" + " ".join(subprocess_array) + "\n")

    if output.returncode != 0: LogFatalError("subprocess.run failed with error code: " + str(output.returncode) + '\n' + " ".join(subprocess_array))
    return " ".join(subprocess_array)

def runSubprocess(subprocess_array):
    """
    Runs subprocess
    """

    global SERVER_BUILD, USE_MULTIPROCESSING

    if (not SERVER_BUILD) and (not USE_MULTIPROCESSING):
        if subprocess_array[0] == 'ogr2ogr': subprocess_array.append('-progress')

    output = subprocess.run(subprocess_array)

    # print("\n" + " ".join(subprocess_array) + "\n")

    if output.returncode != 0: LogFatalError("subprocess.run failed with error code: " + str(output.returncode) + '\n' + " ".join(subprocess_array))
    return " ".join(subprocess_array)

def runSubprocessReturnBoolean(subprocess_array):
    """
    Runs subprocess and returns True or False depending on whether successful or not
    """

    global SERVER_BUILD

    if not SERVER_BUILD:
        if subprocess_array[0] == 'ogr2ogr': subprocess_array.append('-progress')

    output = subprocess.run(subprocess_array)

    # print("\n" + " ".join(subprocess_array) + "\n")

    if output.returncode == 0: return True

    return False

def runSubprocessAndOutput(subprocess_array):
    """
    Runs subprocess and prints output of process
    """

    output = subprocess.run(subprocess_array, capture_output=True, text=True)

    LogMessage(output.stdout.strip())

    if output.returncode != 0: LogFatalError("subprocess.run failed with error code: " + str(output.returncode) + '\n' + " ".join(subprocess_array))

def getGPKGProjection(file_path):
    """
    Gets projection in GPKG
    """

    if isfile(file_path):
        with sqlite3.connect(file_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("select a.srs_id from gpkg_contents as a;")
            result = cursor.fetchall()
            if len(result) == 0:
                LogMessage(file_path + " has no layers - deleting")
                os.remove(file_path)
                return None
            else:
                firstrow = result[0]
                return 'EPSG:' + str(dict(firstrow)['srs_id'])

def checkGPKGIsValid(file_path, layer_name, inputs):
    """
    Checks whether GPKG has correct layer name
    """

    if isfile(file_path):
        with sqlite3.connect(file_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
            select
                    a.table_name, a.data_type, a.srs_id,
                    b.column_name, b.geometry_type_name,
                    c.feature_count
            from gpkg_contents as a
            left join gpkg_geometry_columns as b
                    on a.table_name = b.table_name
            left join gpkg_ogr_contents as c
                    on a.table_name = c.table_name
            ;
            """)
            result = cursor.fetchall()
            if len(result) == 0:
                LogError(file_path + " has no layers - aborting")
                # os.remove(file_path)
                LogError("Reproduce error by manually entering:\n" + inputs)
                LogFatalError("*** Error may be due to lack of memory (increase memory and retry) or corrupt PostGIS table (delete table and rerun) ***")
            else:
                firstrow = dict(result[0])
                if firstrow['table_name'] != layer_name:
                    LogError(file_path + " does not have first layer " + layer_name + " - aborting")
                    print(len(result), json.dumps(firstrow, indent=4))
                    # os.remove(file_path)
                    LogError("Reproduce error by manually entering:\n" + inputs)
                    LogFatalError("*** Error may be due to lack of memory (increase memory and retry) or corrupt PostGIS table (delete table and rerun) ***")
                return True

# ***********************************************************
# **************** Standardisation functions ****************
# ***********************************************************

def reformatDatasetName(datasettitle):
    """
    Reformats dataset title for compatibility purposes

    - Removes .geojson or .gpkg file extension
    - Replaces spaces with hyphen
    - Replaces ' - ' with double hyphen
    - Replaces _ with hyphen
    - Standardises local variations in dataset names, eg. 'Areas of Special Scientific Interest' (Northern Ireland) -> 'Sites of Special Scientific Interest'
    - For specific very long dataset names, eg. 'Public roads, A and B roads and motorways', shorten as this breaks PostGIS when adding prefixes/suffixes
    - Remove CUSTOM_CONFIGURATION_TABLE_PREFIX and CUSTOM_CONFIGURATION_FILE_PREFIX
    """

    datasettitle = normalizeTitle(datasettitle)
    datasettitle = datasettitle.replace('.geojson', '').replace('.gpkg', '')
    datasettitle = removeCustomConfigurationTablePrefix(datasettitle)
    datasettitle = removeCustomConfigurationFilePrefix(datasettitle)
    reformatted_name = datasettitle.lower().replace(' - ', '--').replace(' ','-').replace('_','-').replace('(', '').replace(')', '')
    reformatted_name = reformatted_name.replace('public-roads-a-and-b-roads-and-motorways', 'public-roads-a-b-motorways')
    reformatted_name = reformatted_name.replace('areas-of-special-scientific-interest', 'sites-of-special-scientific-interest')
    reformatted_name = reformatted_name.replace('conservation-area-boundaries', 'conservation-areas')
    reformatted_name = reformatted_name.replace('scheduled-historic-monument-areas', 'scheduled-ancient-monuments')
    reformatted_name = reformatted_name.replace('priority-habitats--woodland', 'ancient-woodlands')
    reformatted_name = reformatted_name.replace('local-wildlife-reserves', 'local-nature-reserves')
    reformatted_name = reformatted_name.replace('national-scenic-areas-equiv-to-aonb', 'areas-of-outstanding-natural-beauty')
    reformatted_name = reformatted_name.replace('explosive-safeguarded-areas,-danger-areas-near-ranges', 'danger-areas')
    reformatted_name = reformatted_name.replace('separation-distance-to-residential-properties', 'separation-distance-from-residential')

    return reformatted_name

def normalizeTitle(title):
    """
    Converts local variants to use same name
    eg. Areas of Special Scientific Interest -> Sites of Special Scientific Interest
    """

    title = title.replace('Areas of Special Scientific Interest', 'Sites of Special Scientific Interest')
    title = title.replace('Conservation Area Boundaries', 'Conservation Areas')
    title = title.replace('Scheduled Historic Monument Areas', 'Scheduled Ancient Monuments')
    title = title.replace('Priority Habitats - Woodland', 'Ancient woodlands')
    title = title.replace('National Scenic Areas (equiv to AONB)', 'Areas of Outstanding Natural Beauty')

    return title

def reformatTableNameAbsolute(name):
    """
    Reformats names, eg. dataset names, ignoring custom settings (so absolute) to be compatible with Postgres
    Different from 'reformatTableName' which will add CUSTOM_CONFIGURATION_TABLE_PREFIX if using custom configuration
    """

    return name.replace('.gpkg', '').replace("-", "_")

def reformatTableName(name):
    """
    Reformats names, eg. dataset names, to be compatible with Postgres
    Also adds in CUSTOM_CONFIGURATION_TABLE_PREFIX in case we're using custom configuration file§
    """

    global CUSTOM_CONFIGURATION, CUSTOM_CONFIGURATION_TABLE_PREFIX

    table = reformatTableNameAbsolute(name)

    if CUSTOM_CONFIGURATION is not None:
        if not table.startswith(CUSTOM_CONFIGURATION_TABLE_PREFIX): table = CUSTOM_CONFIGURATION_TABLE_PREFIX + table

    return table

def getDatasetReadableTitle(dataset):
    """
    Gets readable title from dataset internal code
    """

    readabletitle = dataset.strip()
    readabletitle = readabletitle.replace("dcat--", "").replace("mv--", "").replace("fn--", "").replace("--", " _ ").replace("-", " ").replace(" _ ", " - ").capitalize()
    precountry = " - ".join(readabletitle.split(" - ")[:-1])
    country = readabletitle.split(" - ")[-1].title()
    country = country.replace("Uk", "UK")
    if precountry == '': return readabletitle
    return precountry + " - " + country

def buildBufferLayerPath(folder, layername, buffer):
    """
    Builds buffer layer path
    """

    return folder + layername.replace('.gpkg', '') + '--buf-' + buffer + 'm.gpkg'

def buildClippedLayerPath(folder, layername):
    """
    Builds clipped layer path
    """

    return folder + layername.replace('.gpkg', '') + '--clp.gpkg'

def buildBufferTableName(layername, buffer):
    """
    Builds buffer table name
    """

    return reformatTableName(layername) + '__buf_' + buffer.replace(".", "_") + 'm'

def buildProcessedTableName(layername):
    """
    Builds processed table name
    """

    return reformatTableName(layername) + '__pro'

def buildUnionTableName(layername):
    """
    Builds union table name
    """

    return reformatTableName(layername) + '__union'

def removeCustomConfigurationTablePrefix(layername):
    """
    Remove CUSTOM_CONFIGURATION_TABLE_PREFIX if set
    """

    global CUSTOM_CONFIGURATION_TABLE_PREFIX

    custom_configuration_prefix_table_style = CUSTOM_CONFIGURATION_TABLE_PREFIX.replace('-', '_')
    custom_configuration_prefix_dataset_style = CUSTOM_CONFIGURATION_TABLE_PREFIX.replace('_', '-')

    if layername.startswith(custom_configuration_prefix_table_style): layername = layername[len(custom_configuration_prefix_table_style):]
    elif layername.startswith(custom_configuration_prefix_dataset_style): layername = layername[len(custom_configuration_prefix_dataset_style):]

    return layername

def removeCustomConfigurationFilePrefix(layername):
    """
    Remove CUSTOM_CONFIGURATION_FILE_PREFIX if set
    """

    global CUSTOM_CONFIGURATION_FILE_PREFIX

    custom_configuration_prefix_table_style = CUSTOM_CONFIGURATION_FILE_PREFIX.replace('-', '_')
    custom_configuration_prefix_dataset_style = CUSTOM_CONFIGURATION_FILE_PREFIX.replace('_', '-')

    if layername.startswith(custom_configuration_prefix_table_style): layername = layername[len(custom_configuration_prefix_table_style):]
    elif layername.startswith(custom_configuration_prefix_dataset_style): layername = layername[len(custom_configuration_prefix_dataset_style):]

    return layername

def buildTurbineParametersPrefix():
    """
    Builds turbine parameters prefix that is used in table names and output files
    """

    global HEIGHT_TO_TIP, BLADE_RADIUS

    return "tip_" + formatValue(HEIGHT_TO_TIP).replace(".", "_") + "m_bld_" + formatValue(BLADE_RADIUS).replace(".", "_") + "m__"

def buildFinalLayerTableName(layername):
    """
    Builds final layer table name
    Test for whether layer is turbine-height dependent and if so incorporate HEIGHT_TO_TIP and BLADE_RADIUS parameters into name
    """

    dataset_parent = getDatasetParent(layername)
    dataset_parent_no_custom = removeCustomConfigurationTablePrefix(dataset_parent)

    if isTurbineHeightDependent(dataset_parent_no_custom):
        return reformatTableName(buildTurbineParametersPrefix() + reformatTableNameAbsolute(dataset_parent_no_custom))
    return reformatTableName("tip_any__" + reformatTableNameAbsolute(dataset_parent_no_custom))

def formatValue(value):
    """
    Formats float value to be short and readable
    """

    return str(round(value, 1)).replace('.0', '')

def getOutputFileOriginalTable(output_file_path):
    """
    Gets original table used to generate output file
    """

    global HEIGHT_TO_TIP, CUSTOM_CONFIGURATION_FILE_PREFIX

    output_file_basename = basename(output_file_path).split(".")[0]
    original_table_name = reformatTableName(output_file_basename).replace("latest__", "").replace(CUSTOM_CONFIGURATION_FILE_PREFIX.replace("-", "_"), "")

    if 'tip_' not in original_table_name: original_table_name = buildFinalLayerTableName(original_table_name)

    return original_table_name

def getCoreDatasetName(file_path):
    """
    Gets core dataset name from file path
    Core dataset = 'description--location', eg 'national-parks--scotland'
    Remove any 'custom--', 'latest--' or 'tip-..--' prefixes that may have been added to file name
    """

    global CUSTOM_CONFIGURATION, CUSTOM_CONFIGURATION_FILE_PREFIX, LATEST_OUTPUT_FILE_PREFIX

    file_basename = basename(file_path).split(".")[0]

    if CUSTOM_CONFIGURATION is not None:
        if file_basename.startswith(CUSTOM_CONFIGURATION_FILE_PREFIX):
            file_basename = file_basename[len(CUSTOM_CONFIGURATION_FILE_PREFIX):]

    if file_basename.startswith(LATEST_OUTPUT_FILE_PREFIX) or file_basename.startswith('tip-'):
        elements = file_basename.split("--")
        file_basename = "--".join(elements[1:])

    elements = file_basename.split("--")
    return "--".join(elements[0:2])

def getFinalLayerCoreDatasetName(table_name):
    """
    Gets core dataset name from final layer table name
    """

    dataset_name = reformatDatasetName(table_name)
    if dataset_name.startswith('tip'): dataset_name = '--'.join(dataset_name.split('--')[1:])
    return dataset_name

def getFinalLayerLatestName(table_name):
    """
    Gets latest name from table name, eg. 'tip-135m-bld-40m--ecology-and-wildlife...' -> 'latest--ecology-and-wildlife...'
    If CUSTOM_CONFIGURATION, add CUSTOM_CONFIGURATION_FILE_PREFIX
    """

    global LATEST_OUTPUT_FILE_PREFIX, CUSTOM_CONFIGURATION, CUSTOM_CONFIGURATION_FILE_PREFIX

    custom_configuration_prefix = ''
    if CUSTOM_CONFIGURATION is not None: custom_configuration_prefix = CUSTOM_CONFIGURATION_FILE_PREFIX

    dataset_name = reformatDatasetName(table_name)
    elements = dataset_name.split("--")
    if len(elements) > 1: latest_name = custom_configuration_prefix + LATEST_OUTPUT_FILE_PREFIX + "--".join(elements[1:])
    else: latest_name = custom_configuration_prefix + LATEST_OUTPUT_FILE_PREFIX + dataset_name

    return latest_name

def getDatasetParent(file_path):
    """
    Gets dataset parent name from file path
    Parent = 'description', eg 'national-parks' in 'national-parks--scotland'
    """

    file_basename = basename(file_path).split(".")[0]
    return "--".join(file_basename.split("--")[0:1])

def getDatasetParentTitle(title):
    """
    Gets parent of dataset and normalizes specific values
    """

    title = normalizeTitle(title)
    return title.split(" - ")[0]

def getTableParent(table_name):
    """
    Gets table parent name from table name
    Parent = 'description', eg 'national_parks'
    If using custom configuration, table parent will include 
    """

    global CUSTOM_CONFIGURATION

    parent_table = "__".join(table_name.split("__")[0:1])

    if CUSTOM_CONFIGURATION is not None: parent_table = "__".join(table_name.split("__")[0:2])

    return parent_table


# ***********************************************************
# ********** Application data structure functions ***********
# ***********************************************************

def deleteDatasetFiles(dataset):
    """
    Deletes all files specifically relating to dataset
    """

    global CUSTOM_CONFIGURATION, CUSTOM_CONFIGURATION_FILE_PREFIX
    global HEIGHT_TO_TIP, DATASETS_DOWNLOADS_FOLDER, FINALLAYERS_OUTPUT_FOLDER, TILESERVER_DATA_FOLDER

    possible_extensions = ['geojson', 'gpkg', 'shp', 'shx', 'dbf', 'prj', 'sld', 'mbtiles']

    custom_configuration_prefix = ''
    if CUSTOM_CONFIGURATION is not None: custom_configuration_prefix = CUSTOM_CONFIGURATION_FILE_PREFIX

    table = reformatTableName(dataset)
    turbine_parameters_file_prefix = buildTurbineParametersPrefix().replace('_', '-')
    for possible_extension in possible_extensions:
        dataset_basename = dataset + '.' + possible_extension
        latest_basename = getFinalLayerLatestName(table) + '.' + possible_extension
        possible_files = []
        possible_files.append(DATASETS_DOWNLOADS_FOLDER + dataset_basename)
        possible_files.append(FINALLAYERS_OUTPUT_FOLDER + latest_basename)
        possible_files.append(FINALLAYERS_OUTPUT_FOLDER + custom_configuration_prefix + 'tip-any--' + dataset_basename)
        possible_files.append(FINALLAYERS_OUTPUT_FOLDER + custom_configuration_prefix + turbine_parameters_file_prefix + dataset_basename)
        possible_files.append(TILESERVER_DATA_FOLDER + latest_basename)

        for possible_file in possible_files:
            if isfile(possible_file): 
                LogMessage(" --> Deleting: " + possible_file)
                os.remove(possible_file)

def deleteDatasetTables(dataset, all_tables):
    """
    Deletes all tables specifically relating to dataset
    """

    table = reformatTableName(dataset)
    buffer = getDatasetBuffer(dataset)

    possible_tables = []
    possible_tables.append(table)
    possible_tables.append(buildProcessedTableName(table))
    possible_tables.append(buildFinalLayerTableName(table))
    if buffer is not None:
        bufferedTable = buildBufferTableName(table, buffer)
        possible_tables.append(bufferedTable)
        possible_tables.append(buildProcessedTableName(bufferedTable))

    # We update internal array of all_tables to minimise load on PostGIS
    for possible_table in possible_tables:
        if possible_table in all_tables:
            LogMessage(" --> Dropping PostGIS table: " + possible_table)
            postgisDropTable(possible_table)
            all_tables.remove(possible_table)

    return all_tables

def deleteAncestors(dataset, all_tables=None):
    """
    Deletes parent/ancestor files and parent/ancestor tables derived from dataset
    """

    dataset = dataset.split('.')[0]

    if all_tables is None: all_tables = postgisGetAllTables()

    LogMessage("Deleting files and tables derived from: " + dataset)

    dataset = reformatDatasetName(dataset)
    core_dataset = getCoreDatasetName(dataset)
    ancestors = getAllAncestors(core_dataset, include_initial_dataset=False)

    for ancestor in ancestors:
        deleteDatasetFiles(ancestor)
        all_tables = deleteDatasetTables(ancestor, all_tables)

    return all_tables

def deleteDatasetAndAncestors(dataset, all_tables=None):
    """
    Deletes specific dataset by deleting all files and tables specifically associated 
    with dataset and all parent/ancestor files and parent/ancestor tables derived from dataset
    """

    dataset = dataset.split('.')[0]

    if all_tables is None: all_tables = postgisGetAllTables()

    LogMessage("Deleting files and tables derived from: " + dataset)

    dataset = reformatDatasetName(dataset)
    core_dataset = getCoreDatasetName(dataset)
    ancestors = getAllAncestors(core_dataset)

    for ancestor in ancestors:
        deleteDatasetFiles(ancestor)
        all_tables = deleteDatasetTables(ancestor, all_tables)

    return all_tables

def isSpecificDatasetHeightDependent(dataset_name):
    """
    Returns true or false, depending on whether specific dataset (ignoring children) is turbine-height dependent
    """

    buffer_lookup = getBufferLookup()
    if dataset_name in buffer_lookup:
        buffer_value = str(buffer_lookup[dataset_name])
        if 'height-to-tip' in buffer_value: return True
        if 'blade-radius' in buffer_value: return True
    return False

def isTurbineHeightDependent(dataset_name):
    """
    Returns true or false, depending on whether dataset is turbine-height dependent
    """

    global FINALLAYERS_CONSOLIDATED

    structure_lookup = getStructureLookup()
    dataset_name = reformatDatasetName(dataset_name)

    # We assume overall layer is turbine-height dependent
    if dataset_name == FINALLAYERS_CONSOLIDATED: return True

    children_lookup = {}
    groups = list(structure_lookup.keys())
    for group in groups:
        group_children = list(structure_lookup[group].keys())
        children_lookup[group] = group_children
        for group_child in group_children:
            children_lookup[group_child] = structure_lookup[group][group_child]

    core_dataset_name = getCoreDatasetName(dataset_name)
    alldescendants = getAllDescendants(children_lookup, core_dataset_name)

    for descendant in alldescendants:
        if isSpecificDatasetHeightDependent(descendant): return True
    return False

def getAllDescendants(children_lookup, dataset_name):
    """
    Gets all descendants of dataset
    """

    alldescendants = set()
    if dataset_name in children_lookup:
        for child in children_lookup[dataset_name]:
            alldescendants.add(child)
            descendants = getAllDescendants(children_lookup, child)
            for descendant in descendants:
                alldescendants.add(descendant)
        return list(alldescendants)
    else: return []

def getAllAncestors(dataset_name, include_initial_dataset=True):
    """
    Gets all ancestors of dataset
    """

    global FINALLAYERS_CONSOLIDATED

    # We know FINALLAYERS_CONSOLIDATED is ultimate ancestor of every dataset

    allancestors = [FINALLAYERS_CONSOLIDATED]
    if include_initial_dataset: allancestors.append(dataset_name)

    # Add parent

    parent = getDatasetParent(dataset_name)
    if parent not in allancestors: allancestors.append(parent)

    # Finally check which group grandparent - if any - parent is in

    structure_lookup = getStructureLookup()
    groups = list(structure_lookup.keys())
    for group in groups:
        group_children = list(structure_lookup[group].keys())
        if parent in group_children: allancestors.append(group)

    return allancestors


def generateOSMLookup(osm_data):
    """
    Generates OSM JSON lookup file
    """

    global OSM_LOOKUP

    with open(OSM_LOOKUP, "w") as json_file: json.dump(osm_data, json_file, indent=4)

def generateStructureLookups(ckanpackages):
    """
    Generates structure JSON lookup files including style files for map app
    """

    global CUSTOM_CONFIGURATION, BUILD_FOLDER, MAPAPP_FOLDER, STRUCTURE_LOOKUP, MAPAPP_JS_STRUCTURE, HEIGHT_TO_TIP, BLADE_RADIUS, FINALLAYERS_CONSOLIDATED, TILESERVER_URL

    makeFolder(BUILD_FOLDER)
    makeFolder(MAPAPP_FOLDER)

    structure_lookup = {}
    configuration = ''
    if CUSTOM_CONFIGURATION is not None: configuration = CUSTOM_CONFIGURATION['configuration']

    style_items = [
    {
        "title": "All constraint layers",
        "color": "darkgrey",
        "dataset": getFinalLayerLatestName(FINALLAYERS_CONSOLIDATED),
        "level": 1,
        "children": [],
        "defaultactive": False,
        'height-to-tip': formatValue(HEIGHT_TO_TIP),
        'blade-radius': formatValue(BLADE_RADIUS),
        'configuration': configuration
    }]

    for ckanpackage in ckanpackages.keys():
        ckanpackage_group = reformatDatasetName(ckanpackage)
        structure_lookup[ckanpackage_group] = []
        finallayer_name = getFinalLayerLatestName(ckanpackage_group)
        style_item =   {
                            'title': ckanpackages[ckanpackage]['title'],
                            'color': ckanpackages[ckanpackage]['color'],
                            'dataset': finallayer_name,
                            'level': 1,
                            'defaultactive': True,
                            'height-to-tip': formatValue(HEIGHT_TO_TIP),
                            'blade-radius': formatValue(BLADE_RADIUS)
                        }
        children = {}
        for dataset in ckanpackages[ckanpackage]['datasets']:
            dataset_code = reformatDatasetName(dataset['title'])
            dataset_parent = getDatasetParent(dataset_code)
            if dataset_parent not in children:
                children[dataset_parent] =   {
                                                'title': getDatasetParentTitle(dataset['title']),
                                                'color': ckanpackages[ckanpackage]['color'],
                                                'dataset': getFinalLayerLatestName(dataset_parent),
                                                'level': 2,
                                                'defaultactive': False,
                                                'height-to-tip': formatValue(HEIGHT_TO_TIP),
                                                'blade-radius': formatValue(BLADE_RADIUS)
                                            }
            structure_lookup[ckanpackage_group].append(dataset_code)
        style_item['children'] = [children[children_key] for children_key in children.keys()]
        # If only one child, set parent to only child and remove children
        if len(style_item['children']) == 1:
            style_item = style_item['children'][0]
            style_item['level'] = 1
            style_item['defaultactive'] = True
        style_items.append(style_item)
        structure_lookup[ckanpackage_group] = sorted(structure_lookup[ckanpackage_group])

    structure_hierarchy_lookup = {}
    for ckanpackage in structure_lookup.keys():
        structure_hierarchy_lookup[ckanpackage] = {}
        for dataset in structure_lookup[ckanpackage]:
            layer_parent = "--".join(dataset.split("--")[0:1])
            if layer_parent not in structure_hierarchy_lookup[ckanpackage]: structure_hierarchy_lookup[ckanpackage][layer_parent] = []
            structure_hierarchy_lookup[ckanpackage][layer_parent].append(dataset)

    javascript_content = """
var url_tileserver_style_json = '""" + TILESERVER_URL + """/styles/openwindenergy/style.json';
var openwind_structure = """ + json.dumps({\
        'tipheight': formatValue(HEIGHT_TO_TIP), \
        'bladeradius': formatValue(BLADE_RADIUS), \
        'configuration': configuration, \
        'datasets': style_items\
    }, indent=4) + """;"""

    with open(STRUCTURE_LOOKUP, "w") as json_file: json.dump(structure_hierarchy_lookup, json_file, indent=4)
    with open(STYLE_LOOKUP, "w") as json_file: json.dump(style_items, json_file, indent=4)
    with open(MAPAPP_JS_STRUCTURE, "w") as javascript_file: javascript_file.write(javascript_content)

def outputBoundsAndCenterJavascript():
    """
    Generate Javascript variables MAPAPP_BOUNDS and MAPAPP_CENTER for use in mapapp
    """

    global MAPAPP_JS_BOUNDS_CENTER, MAPAPP_MAXBOUNDS, MAPAPP_FITBOUNDS, MAPAPP_CENTER

    makeFolder(BUILD_FOLDER)
    makeFolder(MAPAPP_FOLDER)

    javascript_content = """
var MAPAPP_MAXBOUNDS = """ + json.dumps(MAPAPP_MAXBOUNDS) + """;
var MAPAPP_FITBOUNDS = """ + json.dumps(MAPAPP_FITBOUNDS) + """;
var MAPAPP_CENTER = """ + json.dumps(MAPAPP_CENTER) + """;"""

    with open(MAPAPP_JS_BOUNDS_CENTER, "w") as javascript_file: javascript_file.write(javascript_content)

def generateBufferLookup(ckanpackages):
    """
    Generates buffer JSON lookup file
    """

    global BUFFER_LOOKUP

    buffer_lookup = {}
    for ckanpackage in ckanpackages.keys():
        for dataset in ckanpackages[ckanpackage]['datasets']:
            if 'buffer' in dataset:
                dataset_title = reformatDatasetName(dataset['title'])
                if dataset['buffer'] is not None:
                    buffer_lookup[dataset_title] = dataset['buffer']

    with open(BUFFER_LOOKUP, "w") as json_file: json.dump(buffer_lookup, json_file, indent=4)

def getOSMLookup():
    """
    Get OSM lookup JSON
    """

    global OSM_LOOKUP
    return getJSON(OSM_LOOKUP)

def getStructureLookup():
    """
    Get structure lookup JSON
    """

    global STRUCTURE_LOOKUP
    return getJSON(STRUCTURE_LOOKUP)

def getBufferLookup():
    """
    Get buffer lookup JSON
    """

    global BUFFER_LOOKUP
    return getJSON(BUFFER_LOOKUP)

def getStyleLookup():
    """
    Get style lookup JSON
    """

    global STYLE_LOOKUP

    return getJSON(STYLE_LOOKUP)

def getStructureDatasets():
    """
    Gets flat list of all datasets in structure
    """

    structure_lookup = getStructureLookup()
    datasets = []
    for group in structure_lookup.keys():
        for parent in structure_lookup[group].keys():
            for child in structure_lookup[group][parent]: datasets.append(child)

    return datasets

def getDatasetBuffer(datasetname):
    """
    Gets buffer for dataset 'datasetname'
    """

    global HEIGHT_TO_TIP, BLADE_RADIUS

    buffer_lookup = getBufferLookup()
    if datasetname not in buffer_lookup: return None

    try:
        buffer = str(buffer_lookup[datasetname])
        if '* height-to-tip' in buffer:
            # Ideally we have more complex parser to allow complex evaluations
            # but allow 'BUFFER * height-to-tip' for now
            buffer = buffer.replace('* height-to-tip','').strip()
            buffer = HEIGHT_TO_TIP * float(buffer)
        elif '* blade-radius' in buffer:
            # Ideally we have more complex parser to allow complex evaluations
            # but allow 'BUFFER * blade-radius' for now
            buffer = buffer.replace('* blade-radius','').strip()
            buffer = BLADE_RADIUS * float(buffer)
        else:
            buffer = float(buffer)
    except:
        LogFatalError("Problem with buffer value for " + datasetname + ", possible error in configuration file. Is it a single element without '-'?")

    return formatValue(buffer)

# ***********************************************************
# ************** Application logic functions ****************
# ***********************************************************

def getCKANPackages(ckanurl):
    """
    Downloads CKAN archive
    """

    global CUSTOM_CONFIGURATION, CKAN_USER_AGENT

    ckan = RemoteCKAN(ckanurl, user_agent=CKAN_USER_AGENT)
    groups = ckan.action.group_list(id='data-explorer')
    packages = ckan.action.package_list(id='data-explorer')

    selectedgroups = {}
    for package in packages:
        ckan_package = ckan.action.package_show(id=package)

        gpkgfound = False
        arcgisfound = False
        buffer, automation, layer, test = None, None, None, False
        if 'extras' in ckan_package:
            for extra in ckan_package['extras']:
                if extra['key'] == 'buffer': buffer = extra['value']
                if extra['key'] == 'automation': automation = extra['value']
                if extra['key'] == 'layer': layer = extra['value']
                if extra['key'] == 'test': test = True

        if automation == 'exclude': continue
        if automation == 'intersect': continue

        # Prioritise GPKG GeoServices
        for resource in ckan_package['resources']:
            package_link = {'title': ckan_package['title'], 'type': resource['format'], 'url': resource['url'], 'buffer': buffer}
            if resource['format'] == 'GPKG':
                gpkgfound = True
                groups = [group['name'] for group in ckan_package['groups']]
                for group in groups:
                    if group not in selectedgroups: selectedgroups[group] = {}
                    selectedgroups[group][ckan_package['title']] = package_link

        if gpkgfound is False:
            for resource in ckan_package['resources']:
                package_link = {'title': ckan_package['title'], 'type': resource['format'], 'url': resource['url'], 'buffer': buffer}
                if resource['format'] == 'ArcGIS GeoServices REST API':
                    arcgisfound = True
                    groups = [group['name'] for group in ckan_package['groups']]
                    for group in groups:
                        if group not in selectedgroups: selectedgroups[group] = {}
                        selectedgroups[group][ckan_package['title']] = package_link

        # If no ArcGis GeoServices, search for WMS or WMTS
        if (gpkgfound is False) and (arcgisfound is False):
            for resource in ckan_package['resources']:
                resource['format'] = resource['format'].strip()

                package_link = {'title': ckan_package['title'], 'type': resource['format'], 'url': resource['url'], 'buffer': buffer, 'layer': layer}
                if ((resource['format'] == 'GeoJSON') or (resource['format'] == 'WFS') or (resource['format'] == 'osm-export-tool YML') or (resource['format'] == 'KML')):
                    groups = [group['name'] for group in ckan_package['groups']]
                    for group in groups:
                        if group not in selectedgroups: selectedgroups[group] = {}
                        selectedgroups[group][ckan_package['title']] = package_link
                    break

    sorted_groups = sorted(selectedgroups.keys())
    groups = {}

    # Custom configuration allows overriding of groups and datasets we actually use

    custom_groups, custom_buffers, custom_areas, custom_style = None, {}, None, {}
    if CUSTOM_CONFIGURATION is not None: 
        if 'structure' in CUSTOM_CONFIGURATION: custom_groups = CUSTOM_CONFIGURATION['structure']
        if 'buffers' in CUSTOM_CONFIGURATION: custom_buffers = CUSTOM_CONFIGURATION['buffers']
        if 'areas' in CUSTOM_CONFIGURATION: custom_areas = CUSTOM_CONFIGURATION['areas']
        if 'style' in CUSTOM_CONFIGURATION: custom_style = CUSTOM_CONFIGURATION['style']

    for sorted_group in sorted_groups:
        ckan_group = ckan.action.group_show(id=sorted_group)
        color = ''
        if 'extras' in ckan_group:
            for extra in ckan_group['extras']:
                if extra['key'] == 'color': color = extra['value']

        # Allow CUSTOM_CONFIGURATION to override group properties/datasets

        custom_datasets = None
        if custom_groups is not None:
            if reformatDatasetName(sorted_group) not in custom_groups: continue
            custom_datasets = custom_groups[reformatDatasetName(sorted_group)]

        if reformatDatasetName(sorted_group) in custom_style:
            custom_group_style = custom_style[reformatDatasetName(sorted_group)]
            if 'color' in custom_group_style: color = custom_group_style['color']

        groups[sorted_group] = {'title': ckan_group['title'], 'color': color, 'datasets': []}
        sorted_packages = sorted(selectedgroups[sorted_group].keys())
        for sorted_package in sorted_packages:
            dataset = selectedgroups[sorted_group][sorted_package]
            dataset_code = reformatDatasetName(dataset['title'])
            if custom_datasets is not None:
                if dataset_code not in custom_datasets: continue
                if dataset_code in custom_buffers: dataset['buffer'] = custom_buffers[dataset_code]
            if custom_areas is not None:
                dataset_in_customarea = False
                for custom_area in custom_areas:
                    if custom_area in dataset_code: dataset_in_customarea = True
                if not dataset_in_customarea: continue
            groups[sorted_group]['datasets'].append(dataset)

    return groups

def processCustomConfiguration(customconfig):
    """
    Processes custom configuration value
    """

    global CKAN_URL, CKAN_USER_AGENT, CUSTOM_CONFIGURATION_FOLDER, CUSTOM_CONFIGURATION_TABLE_PREFIX
    global OSM_MAIN_DOWNLOAD, OSM_EXPORT_DATA, HEIGHT_TO_TIP, BLADE_RADIUS

    makeFolder(CUSTOM_CONFIGURATION_FOLDER)

    config_downloaded = False
    config_basename = basename(customconfig).lower()
    config_saved_path = CUSTOM_CONFIGURATION_FOLDER + config_basename.replace('.yml', '') + '.yml'
    if isfile(config_saved_path): os.remove(config_saved_path)

    # If '.yml' isn't ending of customconfig, can only be a custom configuration reference on CKAN

    # Open Wind Energy CKAN requires special user-agent for downloads as protection against data crawlers
    opener = urllib.request.build_opener()
    opener.addheaders = [('User-Agent', CKAN_USER_AGENT)]
    urllib.request.install_opener(opener)

    if not config_basename.endswith('.yml'):

        LogMessage("Custom configuration: Attempting to locate '" + config_basename + "' on " + CKAN_URL)

        ckan = RemoteCKAN(CKAN_URL, user_agent=CKAN_USER_AGENT)
        packages = ckan.action.package_list(id='data-explorer')
        config_code = reformatDatasetName(config_basename)

        for package in packages:
            ckan_package = ckan.action.package_show(id=package)

            # Check to see if name of customconfig matches CKAN reformatted package title 

            if reformatDatasetName(ckan_package['title'].strip()) != config_code: continue

            # If matches, search for YML file in resources

            for resource in ckan_package['resources']:
                if ('YML' in resource['format']):
                    attemptDownloadUntilSuccess(resource['url'], config_saved_path)
                    config_downloaded = True
                    break

            if config_downloaded: break

    elif customconfig.startswith('http://') or customconfig.startswith('https://'):
        attemptDownloadUntilSuccess(customconfig, config_saved_path)
        config_downloaded = True

    # Revert user-agent to defaults
    opener = urllib.request.build_opener()
    urllib.request.install_opener(opener)

    if not config_downloaded:
        if isfile(customconfig):
            shutil.copy(customconfig, config_saved_path)
            config_downloaded = True

    if not config_downloaded:

        LogMessage("Unable to access custom configuration '" + customconfig + "'")
        LogMessage(" --> IGNORING CUSTOM CONFIGURATION")

        return None

    yaml_content = None
    with open(config_saved_path) as stream:
        try:
            yaml_content = yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            LogFatalError(exc)

    if yaml_content is not None:

        yaml_content['configuration'] = customconfig

        # Dropping all custom configuration tables
        # If we don't do this, things gets very complicated if you start running things across many config files

        LogMessage("Custom configuration: Note all generated tables for custom configuration will have '" + CUSTOM_CONFIGURATION_TABLE_PREFIX + "' prefix")

        LogMessage("Custom configuration: Dropping previous custom configuration database tables")

        postgisDropCustomTables()

    if 'osm' in yaml_content:
        OSM_MAIN_DOWNLOAD = yaml_content['osm']
        LogMessage("Custom configuration: Setting OSM download to " + yaml_content['osm'])

    if 'tip-height' in yaml_content:
        HEIGHT_TO_TIP = float(formatValue(yaml_content['tip-height']))
        LogMessage("Custom configuration: Setting tip-height to " + str(HEIGHT_TO_TIP))

    if 'blade-radius' in yaml_content:
        BLADE_RADIUS = float(formatValue(yaml_content['blade-radius']))
        LogMessage("Custom configuration: Setting blade-radius to " + str(BLADE_RADIUS))

    if 'clipping' in yaml_content:
        LogMessage("Custom configuration: Clipping area(s) [" + ", ".join(yaml_content['clipping']) + "]")

    if 'areas' in yaml_content:
        LogMessage("Custom configuration: Selecting specific area(s) [" + ", ".join(yaml_content['areas']) + "]")

    return yaml_content

def processClippingArea(clippingarea):
    """
    Process custom clipping area
    """

    global CUSTOM_CONFIGURATION, CUSTOM_CONFIGURATION_TABLE_PREFIX

    countries = ['england', 'scotland', 'wales', 'northern-ireland']

    if clippingarea.lower() == 'uk': return CUSTOM_CONFIGURATION # The default setup so change nothing
    if clippingarea.lower().replace(' ', '-') in countries: country = clippingarea.lower()
    else: country = getCountryFromArea(clippingarea)

    if CUSTOM_CONFIGURATION is None: CUSTOM_CONFIGURATION = {'configuration': '--clip ' + clippingarea}
    CUSTOM_CONFIGURATION['clipping'] = [clippingarea]

    if 'areas' not in CUSTOM_CONFIGURATION: CUSTOM_CONFIGURATION['areas'] = [country, 'uk']
    elif country not in CUSTOM_CONFIGURATION: CUSTOM_CONFIGURATION['areas'].append(country)

    LogMessage("Custom clipping area: Clipping on '" + clippingarea + "'")
    LogMessage("Custom clipping area: Selecting country-specific datasets for '" + country + "'")
    LogMessage("Custom clipping area: Note all generated tables for custom configuration will have '" + CUSTOM_CONFIGURATION_TABLE_PREFIX + "' prefix")
    LogMessage("Custom clipping area: Dropping previous custom configuration database tables")
    postgisDropCustomTables()

    return CUSTOM_CONFIGURATION

def guessWFSLayerIndex(layers):
    """
    Get WFS index from array of layers
    We check the title of the layer to see if if has 'boundary' or 'boundaries' in it - if so, select
    """

    layer_index = 0
    for layer in layers:
        if 'Title' in layer:
            if 'boundary' in layer['Title'].lower(): return layer_index
            if 'boundaries' in layer['Title'].lower(): return layer_index
        layer_index += 1

    return 0

def checkGeoJSONFile(file_path):
    """
    Checks validity of single GeoJSON file
    """

    file = basename(file_path)

    try:
        json_data = json.load(open(file_path))
        LogMessage("GeoJSON file valid: " + file)
    except:
        LogWarning("GeoJSON file invalid, deleting: " + file)
        os.remove(file_path)
        with global_boolean.get_lock(): global_boolean.value = 0

def checkGeoJSONFiles(output_folder):
    """
    Checks validity of GeoJSON files within folder
    This is required in case download process is interrupted and files are incompletely downloaded
    """

    LogMessage("Checking validity of downloaded GeoJSON files...")

    files = getFilesInFolder(output_folder)

    files_to_check = []
    for file in files:
        if not file.endswith('.geojson'): continue
        file_path = output_folder + file
        files_to_check.append(file_path)

    global_boolean = Value('i', 1)

    multiprocessBefore()

    chunksize = int(len(files_to_check) / multiprocessing.cpu_count()) + 1

    with Pool(processes=getNumberProcesses(), initializer=init_globals_boolean, initargs=(global_boolean,)) as p:
        p.map(checkGeoJSONFile, files_to_check, chunksize=chunksize)

    multiprocessAfter()

    all_valid = (bool)(global_boolean.value)

    if all_valid: LogMessage("All downloaded GeoJSON files valid")

    return all_valid

def downloadDatasets(ckanurl, output_folder):
    """
    Repeats download process until all files are valid
    """

    global TEMP_FOLDER

    makeFolder(TEMP_FOLDER)

    while True:

        all_downloaded = downloadDatasetsSinglePass(ckanurl, output_folder)

        if checkGeoJSONFiles(output_folder) and all_downloaded: break

        LogMessage("One or more downloaded files invalid, rerunning download process")

    if isdir(TEMP_FOLDER): shutil.rmtree(TEMP_FOLDER)

def downloadDatasetsSinglePass(ckanurl, output_folder):
    """
    Downloads a CKAN archive and processes the ArcGIS, WFS, GeoJSON and osm-export-tool YML files within it
    TODO: Add support for non-ArcGIS/GeoJSON/WFS/osm-export-tool-YML
    """

    global DOWNLOAD_USER_AGENT
    global CUSTOM_CONFIGURATION, CUSTOM_CONFIGURATION_FILE_PREFIX, OSM_NAME_CONVERT, OVERALL_CLIPPING_FILE
    global REGENERATE_OUTPUT, BUILD_FOLDER, OSM_DOWNLOADS_FOLDER, OSM_MAIN_DOWNLOAD, OSM_CONFIG_FOLDER, WORKING_CRS, OSM_EXPORT_DATA
    global POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD

    makeFolder(BUILD_FOLDER)
    makeFolder(OSM_CONFIG_FOLDER)
    makeFolder(output_folder)

    osmDownloadData()

    LogMessage("Downloading data catalogue from CKAN " + ckanurl)

    ckanpackages = getCKANPackages(ckanurl)

    generateStructureLookups(ckanpackages)
    generateBufferLookup(ckanpackages)

    # Batch create all OSM layers first
    # Saves time to run osm-export-tool on single file with all datasets

    custom_prefix = ''
    if CUSTOM_CONFIGURATION is not None: custom_prefix = CUSTOM_CONFIGURATION_FILE_PREFIX 

    yaml_all_filename = custom_prefix + 'all.yml'

    osm_layers, yaml_all_content, yaml_all_path = [], {}, OSM_CONFIG_FOLDER + yaml_all_filename
    existing_yaml_content = None
    rerun_osm_export_tool = False

    # Build list of YML files to download, download using multiprocessing then process all downloads

    queue_download, dataset_titles = [], []
    for ckanpackage in ckanpackages.keys():
        for dataset in ckanpackages[ckanpackage]['datasets']:
            if dataset['type'] != 'osm-export-tool YML': continue

            dataset_title = reformatDatasetName(dataset['title'])
            dataset_titles.append(dataset_title)
            url_basename = basename(dataset['url'])
            downloaded_yml = dataset_title + ".yml"
            downloaded_yml_fullpath = OSM_CONFIG_FOLDER + downloaded_yml
            queue_download.append(["Downloading osm-export-tool YML: " + url_basename + " -> " + downloaded_yml, dataset['url'], downloaded_yml_fullpath])

    multiprocessDownload(queue_download)

    for dataset_title in dataset_titles:
        yaml_content = None
        downloaded_yml = dataset_title + ".yml"
        downloaded_yml_fullpath = OSM_CONFIG_FOLDER + downloaded_yml
        
        with open(downloaded_yml_fullpath) as stream:
            try:
                yaml_content = yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                LogMessage(exc)
                exit()

        if yaml_content is None: continue
        yaml_content_keys = list(yaml_content.keys())
        if len(yaml_content_keys) == 0: continue

        # Rename yaml layer with dataset_title and add to aggregate yaml data structure
        yaml_content_firstkey = yaml_content_keys[0]
        yaml_all_content[dataset_title] = yaml_content[yaml_content_firstkey]
        osm_layers.append(dataset_title)

    # Check whether latest yaml matches existing aggregated yaml (if exists)
    # If not, dump out aggregate yaml data structure and process with osm-export-tool

    if isfile(yaml_all_path):
        with open(yaml_all_path, "r") as yaml_file: existing_yaml_content = yaml_file.read()

    # By adding comment specifying which OSM download will be used, we avoid rerunning osm-export-tool unnecessarily
    latest_yaml_content = '# Will be run on ' + OSM_MAIN_DOWNLOAD + '\n\n' + yaml.dump(yaml_all_content)
    if latest_yaml_content != existing_yaml_content:
        rerun_osm_export_tool = True
        with open(yaml_all_path, "w") as yaml_file: yaml_file.write(latest_yaml_content)

    osm_export_base = BUILD_FOLDER + custom_prefix + OSM_EXPORT_DATA
    osm_export_file = osm_export_base + '.gpkg'

    # Attempt to get projection for osm_export_file - if file is broken, it will be deleted
    if isfile(osm_export_file): osm_export_projection = getGPKGProjection(osm_export_file)

    if not isfile(osm_export_file): rerun_osm_export_tool = True

    osm_layers.sort()
    generateOSMLookup(osm_layers)

    all_datasets_downloaded = Value('i', 1)
    num_datasets_downloaded = Value('i', 0)
    dataset_index, datasets_queue = 0, []

    # Add osm-export-tool to datasets queue to be processed with multiprocessing
    # This ensures long-run processes like osm-export-tool start early as possible
    if rerun_osm_export_tool:
        dataset_index += 1
        datasets_queue.append(  {\
                                'subprocess': ["osm-export-tool", OSM_DOWNLOADS_FOLDER + basename(OSM_MAIN_DOWNLOAD), osm_export_base, "-m", yaml_all_path], \
                                'log': ("Running osm-export-tool with aggregated YML '" + yaml_all_filename + "' on: " + basename(OSM_MAIN_DOWNLOAD)) \
                                })

    # Add main downloads to datasets queue to be processed with multiprocessing
    for ckanpackage in ckanpackages.keys():
        for dataset in ckanpackages[ckanpackage]['datasets']:
            dataset_index += 1
            datasets_queue.append(  { \
                                    'dataset_index': dataset_index, \
                                    'dataset': dataset, \
                                    'output_folder': output_folder \
                                    })

    multiprocessBefore()

    LogMessage("Downloading missing datasets or running early-stage data processing...")

    chunksize = 1
    with Pool(processes=getNumberProcesses(), initializer=init_globals_boolean_count, initargs=(all_datasets_downloaded, num_datasets_downloaded, )) as p:
        p.map(downloadDataset, datasets_queue, chunksize=chunksize)
    
    num_downloaded = num_datasets_downloaded.value
    if num_downloaded == 0: LogMessage("All datasets already downloaded")
    else: LogMessage(str(num_downloaded) + " dataset(s) downloaded or processed in this pass")

    multiprocessAfter()

    return (bool)(all_datasets_downloaded.value)

def downloadDataset(dataset_parameters):
    """
    Downloads single dataset
    """

    global CKAN_USER_AGENT, TEMP_FOLDER

    # Check to see if dataset download is really long-running pre-processing step, eg. osm-export-tool
    if 'subprocess' in dataset_parameters:
        LogMessage("STARTING:            " + dataset_parameters['log'])
        runSubprocess(dataset_parameters['subprocess'])
        LogMessage("FINISHED:            " + dataset_parameters['log'])
        with global_count.get_lock(): global_count.value += 1
        return 

    dataset_index = dataset_parameters['dataset_index']
    dataset = dataset_parameters['dataset']
    output_folder = dataset_parameters['output_folder']

    # Don't do anything if osm-export-tool dataset
    if dataset['type'] == 'osm-export-tool YML': return

    dataset_title = reformatDatasetName(dataset['title'])
    feature_name = dataset['title']
    feature_layer_url = dataset['url']
    temp_base = join(TEMP_FOLDER, 'temp_' + str(dataset_index))

    opener = urllib.request.build_opener()
    opener.addheaders = [('User-Agent', CKAN_USER_AGENT)]
    urllib.request.install_opener(opener)

    # Remove any temp files that may have been left if previous run interrupted
    for possible_extension in ['.geojson', '.gml', '.gpkg']:
        if isfile(temp_base + possible_extension): os.remove(temp_base + possible_extension)

    temp_output_file = temp_base + '.geojson'
    output_file = join(output_folder, f'{dataset_title}.geojson')
    output_gpkg_file = join(output_folder, f'{dataset_title}.gpkg')
    zip_folder = output_folder + dataset_title + '/'

    # If export file(s) already exists, quit
    if isfile(output_file) or isfile(output_gpkg_file): return

    LogMessage("STARTING:            " + feature_name)

    if dataset['type'] == 'KML':

        LogMessage("Downloading KML:     " + feature_name)

        url_basename = basename(dataset['url'])
        kml_file = output_folder + dataset_title + '.kml'
        kmz_file = output_folder + dataset_title + '.kmz'

        if url_basename[-4:] == '.kml':
            attemptDownloadUntilSuccess(dataset['url'], kml_file)
        # If kmz then unzip to folder
        elif url_basename[-4:] == '.kmz':
            attemptDownloadUntilSuccess(dataset['url'], kmz_file)
            with ZipFile(kmz_file, 'r') as zip_ref: zip_ref.extractall(zip_folder)
            os.remove(kmz_file)
        # If zip then download and unzip
        elif url_basename[-4:] == '.zip':
            zip_file = output_folder + dataset_title + '.zip'
            attemptDownloadUntilSuccess(dataset['url'], zip_file)
            with ZipFile(zip_file, 'r') as zip_ref: zip_ref.extractall(zip_folder)
            os.remove(zip_file)
            unzipped_files = getFilesInFolder(zip_folder)
            for unzipped_file in unzipped_files:
                if (unzipped_file[-4:] == '.kmz'):
                    with ZipFile(zip_folder + unzipped_file, 'r') as zip_ref: zip_ref.extractall(zip_folder)

        if isdir(zip_folder):
            unzipped_files = getFilesInFolder(zip_folder)
            for unzipped_file in unzipped_files:
                if (unzipped_file[-4:] == '.kml'):
                    shutil.copy(zip_folder + unzipped_file, kml_file)
            shutil.rmtree(zip_folder)

        if isfile(kml_file):
            # Forced to use togeojson as KML support in ogr2ogr is unpredictable on MacOS
            with open(temp_output_file, "w") as geojson_file:
                    subprocess.call(["togeojson", kml_file], stdout = geojson_file)
            os.remove(kml_file)

        with global_count.get_lock(): global_count.value += 1

    elif dataset['type'] == 'WFS':

        temp_output_file = temp_base + '.gpkg'
        getfeature_url = dataset['url']
        # We need DOWNLOAD_USER_AGENT 'User-Agent' header to allow access to scot.gov's WFS AWS servers
        # Following direct communication with data providers (12/05/2025), 
        # they added DOWNLOAD_USER_AGENT ('openwindenergy/*') as exception to their blacklist
        LogMessage("Setting 'User-Agent' to " + DOWNLOAD_USER_AGENT + " to enable WFS download from specific data providers")
        headers = {'User-Agent': DOWNLOAD_USER_AGENT}

        # Attempt to connect to WFS using highest version

        wfs_version = '2.0.0'
        try:
            wfs = WebFeatureService(url=dataset['url'], version='2.0.0', headers=headers)
        except:
            try:
                wfs = WebFeatureService(url=dataset['url'], headers=headers)
                wfs_version = wfs.version
            except:
                LogError("Problem accessing WFS: " + getfeature_url)
                with global_boolean.get_lock(): global_boolean.value = 0
                return

        # Get correct url for 'GetFeature' as this may different from
        # initial url providing capabilities information

        methods = wfs.getOperationByName('GetFeature').methods
        for method in methods:
            if method['type'].lower() == 'get': getfeature_url = method['url']

        # We default to first available layer in WFS
        # If different layer is needed, set 'layer' custom field in CKAN

        layers = list(wfs.contents)
        layer = layers[0]
        if ('layer' in dataset) and (dataset['layer'] is not None): layer = dataset['layer']

        # Extract CRS from WFS layer info

        crs = str(wfs[layer].crsOptions[0]).replace('urn:ogc:def:crs:', '').replace('::', ':').replace('OGC:1.3:CRS84', 'EPSG:4326')

        # Perform initial 'hits' query to get total records and pagination batch size

        params={
            'SERVICE': 'WFS',
            'VERSION': wfs_version,
            'REQUEST': 'GetFeature',
            'RESULTTYPE': 'hits',
            'TYPENAME': layer
        }
        url = getfeature_url.split('?')[0] + '?' + urllib.parse.urlencode(params)
        response = requests.get(url, headers=headers)
        result = xmltodict.parse(response.text)

        # Return False if incorrect response so we can retry again

        if not ('wfs:FeatureCollection' in result):
            LogError("Missing wfs:FeatureCollection in response from: " + getfeature_url)
            with global_boolean.get_lock(): global_boolean.value = 0
            return

        if not ('@numberMatched' in result['wfs:FeatureCollection']):
            LogError("Missing @numberMatched in response from: " + getfeature_url)
            with global_boolean.get_lock(): global_boolean.value = 0
            return

        if not ('@numberReturned' in result['wfs:FeatureCollection']):
            LogError("Missing @numberReturned in response from: " + getfeature_url)
            with global_boolean.get_lock(): global_boolean.value = 0
            return

        totalrecords = int(result['wfs:FeatureCollection']['@numberMatched'])
        batchsize = int(result['wfs:FeatureCollection']['@numberReturned'])

        # If batchsize is 0, suggests that there is no limit so attempt to load all records

        if batchsize == 0: batchsize = totalrecords

        # Download data page by page

        LogMessage("Downloading WFS:     " + feature_name+ " [records: " + str(totalrecords) + "]")

        dataframe, startIndex, recordsdownloaded = None, 0, 0

        while True:

            recordstodownload = totalrecords - recordsdownloaded
            if recordstodownload > batchsize: recordstodownload = batchsize

            wfs_request_url = Request('GET', getfeature_url, headers=headers, params={
                'service': 'WFS',
                'version': wfs_version,
                'request': 'GetFeature',
                'typename': layer,
                'count': recordstodownload,
                'startIndex': startIndex,
            }).prepare().url

            LogMessage("--> Downloading: " + str(startIndex + 1) + " to " + str(startIndex + recordstodownload))

            try:
                dataframe_new = gpd.read_file(wfs_request_url).set_crs(crs)

                if dataframe is None: dataframe = dataframe_new
                else: dataframe = pd.concat([dataframe, dataframe_new])

                recordsdownloaded += recordstodownload
                startIndex += recordstodownload

                if recordsdownloaded >= totalrecords: break
            except:
                LogMessage("--> Unable to download records - possible incorrect record count from WFS [numberMatched:" + str(totalrecords) + ", numberReturned:" + str(batchsize) + "] - retrying with reduced number")

                recordstodownload -= 1
                totalrecords -= 1
                if recordstodownload == 0: break

        dataframe.to_file(temp_output_file)

        with global_count.get_lock(): global_count.value += 1

    elif dataset['type'] == 'GPKG':

        LogMessage("Downloading GPKG:    " + feature_name)

        temp_output_file = temp_base + '.gpkg'

        # Handle non-zipped or zipped version of GPKG

        if not dataset['url'].endswith('.zip'):
            attemptDownloadUntilSuccess(dataset['url'], temp_output_file)
        else:
            zip_file = output_folder + dataset_title + '.zip'
            attemptDownloadUntilSuccess(dataset['url'], zip_file)
            with ZipFile(zip_file, 'r') as zip_ref: zip_ref.extractall(zip_folder)
            os.remove(zip_file)

            if isdir(zip_folder):
                unzipped_files = getFilesInFolder(zip_folder)
                for unzipped_file in unzipped_files:
                    if unzipped_file.endswith('.gpkg'):
                        shutil.copy(zip_folder + unzipped_file, temp_output_file)
                shutil.rmtree(zip_folder)

        with global_count.get_lock(): global_count.value += 1

    elif dataset['type'] == 'GeoJSON':

        LogMessage("Downloading GeoJSON: " + feature_name)

        # Handle non-zipped or zipped version of GeoJSON

        if dataset['url'][-4:] != '.zip':
            attemptDownloadUntilSuccess(dataset['url'], temp_output_file)
        else:
            zip_file = output_folder + dataset_title + '.zip'
            attemptDownloadUntilSuccess(dataset['url'], zip_file)
            with ZipFile(zip_file, 'r') as zip_ref: zip_ref.extractall(zip_folder)
            os.remove(zip_file)

            if isdir(zip_folder):
                unzipped_files = getFilesInFolder(zip_folder)
                for unzipped_file in unzipped_files:
                    if (unzipped_file[-8:] == '.geojson'):
                        shutil.copy(zip_folder + unzipped_file, temp_output_file)
                shutil.rmtree(zip_folder)

        with global_count.get_lock(): global_count.value += 1

    elif dataset['type'] == "ArcGIS GeoServices REST API":

        query_url = f'{feature_layer_url}/query'
        params = {"f": 'json'}
        response = attemptPOSTUntilSuccess(feature_layer_url, params)
        result = json.loads(response.text)
        if 'objectIdField' not in result:
            error_message = feature_name + " - objectIdField missing from response to url: " + feature_layer_url
            if 'error' in result:
                if 'code' in result['error']: error_message = '[' + str(result['error']['code']) + "] " + feature_name + ' - ' + feature_layer_url
            LogError(error_message)
            LogError("Check URL and, if necessary, notify original data provider of potential problem with their data feed")
            with global_boolean.get_lock(): global_boolean.value = 0
            return

        object_id_field = result['objectIdField']

        params = {
            "f": 'json',
            "returnCountOnly": 'true',
            "where": '1=1'
        }

        response = attemptPOSTUntilSuccess(query_url, params)
        result = json.loads(response.text)
        if 'count' not in result: 
            error_message = feature_name + " - 'count' missing from response to url: " + query_url
            if 'error' in result:
                if 'code' in result['error']: error_message = '[' + str(result['error']['code']) + "] " + feature_name + ' - ' + query_url
            LogError(error_message)
            LogError("Check URL and, if necessary, notify original data provider of potential problem with their data feed")
            with global_boolean.get_lock(): global_boolean.value = 0
            return

        no_of_records = result['count']

        LogMessage("Downloading ArcGIS:  " + feature_name + " [records: " + str(no_of_records) + "]")

        records_downloaded = 0
        object_id = -1

        geojson = {
            "type": "FeatureCollection",
            "features": []
        }

        while records_downloaded < no_of_records:
            params = {
                "f": 'geojson',
                "outFields": '*',
                "outSR": 4326, # change the spatial reference if needed (normally GeoJSON uses 4326 for the spatial reference)
                "returnGeometry": 'true',
                "where": f'{object_id_field} > {object_id}'
            }

            firstpass = True

            while True:

                if not firstpass: LogMessage("Attempting to download after first failed attempt: " + query_url)
                firstpass = False

                response = attemptPOSTUntilSuccess(query_url, params)
                result = json.loads(response.text)

                if 'features' not in result:
                    LogWarning("Problem with url, retrying after delay...")
                    time.sleep(5)
                    continue

                if(len(result['features'])):
                    geojson['features'] += result['features']
                    records_downloaded += len(result['features'])
                    object_id = result['features'][len(result['features'])-1]['properties'][object_id_field]
                else:
                    LogWarning("Problem with url, retrying after delay...")
                    time.sleep(5)

                    '''
                        this should not be needed but is here as an extra step to avoid being
                        stuck in a loop if there is something wrong with the service, i.e. the
                        record count stored with the service is incorrect and does not match the
                        actual record count (which can happen).
                    '''
                break

        if(records_downloaded != no_of_records):
            LogMessage("--- ### Note, the record count for the feature layer (" + feature_name + ") is incorrect - this is a bug in the service itself ### ---")

        with open(temp_output_file, 'w') as f:
            f.write(json.dumps(geojson, indent=2))

        with global_count.get_lock(): global_count.value += 1

    # Produces final GeoJSON/GPKG by converting and applying 'dataset_title' as layer name
    if isfile(temp_output_file):
        if ('.geojson' in temp_output_file):
            reformatGeoJSON(temp_output_file)
            inputs = runSubprocess(["ogr2ogr", "-f", "GeoJSON", "-nln", dataset_title, "-nlt", "GEOMETRY", output_file, temp_output_file])
        if ('.gpkg' in temp_output_file):
            orig_srs = getGPKGProjection(temp_output_file)
            inputs = runSubprocess([ "ogr2ogr", \
                            "-f", "gpkg", \
                            "-nln", dataset_title, \
                            "-nlt", "GEOMETRY", \
                            output_gpkg_file, \
                            temp_output_file, \
                            "-s_srs", orig_srs, \
                            "-t_srs", WORKING_CRS])
        os.remove(temp_output_file)
    
    LogMessage("FINISHED:            " + feature_name)

def deleteFolderContentsKeepFolder(folder):
    """
    Deletes contents of folder but keep folder - needed for when docker compose manages folder mappings
    """

    if not isdir(folder): return

    files = getFilesInFolder(folder)
    for file in files: os.remove(folder + file)

    subfolders = [ f.path for f in os.scandir(folder) if f.is_dir() ]

    for subfolder in subfolders:
        subfolder_absolute = os.path.abspath(subfolder)
        if len(subfolder_absolute) < len(folder) or not subfolder_absolute.startswith(folder):
            LogFatalError("Attempting to delete folder outside selected folder, aborting")
        shutil.rmtree(subfolder_absolute)

def purgeAll():
    """
    Deletes all database tables and build folder
    """

    global WORKING_FOLDER, BUILD_FOLDER, TILESERVER_FOLDER, OSM_DOWNLOADS_FOLDER, OSM_EXPORT_DATA, OSM_CONFIG_FOLDER, DATASETS_DOWNLOADS_FOLDER

    postgisDropAllTables()

    tileserver_folder_name = basename(TILESERVER_FOLDER[:-1])
    build_files = getFilesInFolder(BUILD_FOLDER)
    for build_file in build_files: 
        # Don't delete log files from BUILD_FOLDER
        if not build_file.endswith('.log'): os.remove(BUILD_FOLDER + build_file)
    osm_files = getFilesInFolder(OSM_DOWNLOADS_FOLDER)
    for osm_file in osm_files: os.remove(OSM_DOWNLOADS_FOLDER + osm_file)
    tileserver_files = getFilesInFolder(TILESERVER_FOLDER)
    for tileserver_file in tileserver_files: os.remove(TILESERVER_FOLDER + tileserver_file)

    pwd = os.path.dirname(os.path.realpath(__file__))

    # Delete items in BUILD_FOLDER

    subfolders = [ f.path for f in os.scandir(BUILD_FOLDER) if f.is_dir() ]
    absolute_build_folder = os.path.abspath(BUILD_FOLDER)

    for subfolder in subfolders:

        # Don't delete 'postgres' folder as managed by separate docker instance
        # Don't delete 'tileserver' folder yet as some elements are managed separately 
        # Don't delete 'landcover' and 'coastline' folders as managed by docker compose 
        if basename(subfolder) in ['postgres', tileserver_folder_name, 'coastline', 'landcover']: continue

        subfolder_absolute = os.path.abspath(subfolder)

        if len(subfolder_absolute) < len(absolute_build_folder) or not subfolder_absolute.startswith(absolute_build_folder):
            LogFatalError("Attempting to delete folder outside build folder, aborting")

        shutil.rmtree(subfolder_absolute)

    # Delete all items in 'landcover' and 'coastline' folders but keep folders in case managed by docker

    deleteFolderContentsKeepFolder(WORKING_FOLDER + 'coastline/')
    deleteFolderContentsKeepFolder(WORKING_FOLDER + 'landcover/')

    # Delete selected items in TILESERVER_FOLDER

    subfolders = [ f.path for f in os.scandir(TILESERVER_FOLDER) if f.is_dir() ]
    absolute_tileserver_folder = os.path.abspath(TILESERVER_FOLDER)

    for subfolder in subfolders:

        # Don't delete 'fonts' as this is created by openwindenergy-fonts
        if basename(subfolder) in ['fonts']: continue

        subfolder_absolute = os.path.abspath(subfolder)

        if len(subfolder_absolute) < len(absolute_tileserver_folder) or not subfolder_absolute.startswith(absolute_tileserver_folder):
            LogFatalError("Attempting to delete folder outside tileserver folder, aborting")

        shutil.rmtree(subfolder_absolute)

def createGridClippedFile(parameters):
    """
    Create grid clipped version of file to improve rendering and performance when used as mbtiles
    """

    global OUTPUT_GRID_TABLE

    with global_count.get_lock():
        LogMessage("STARTING: Create grid-sliced tippecanoe input file for: " + parameters['table_name'] + " [" + str(global_count.value) + " table(s) to be processed]")

    scratch_table_1 = '_scr_' + parameters['table_name']
    output_grid = reformatTableName(OUTPUT_GRID_TABLE)

    # Remove existing file and scratch table
    if isfile(parameters['tippecanoe_input']): os.remove(parameters['tippecanoe_input'])
    if postgisCheckTableExists(scratch_table_1): postgisDropTable(scratch_table_1)

    postgisExec("CREATE TABLE %s AS SELECT (ST_Dump(ST_Intersection(layer.geom, grid.geom))).geom geom FROM %s layer, %s grid;", \
                (AsIs(scratch_table_1), AsIs(parameters['table_name']), AsIs(output_grid), ))

    inputs = runSubprocess(["ogr2ogr", \
                    parameters['tippecanoe_input'], \
                    'PG:host=' + POSTGRES_HOST + ' user=' + POSTGRES_USER + ' password=' + POSTGRES_PASSWORD + ' dbname=' + POSTGRES_DB, \
                    "-overwrite", \
                    "-nln", parameters['dataset_name'], \
                    scratch_table_1, \
                    "-s_srs", WORKING_CRS, \
                    "-t_srs", 'EPSG:4326'])

    if postgisCheckTableExists(scratch_table_1): postgisDropTable(scratch_table_1)

    # Check for no features as GeoJSON with no features causes problem for tippecanoe
    # If no features, add dummy point so Tippecanoe creates mbtiles

    if os.path.getsize(parameters['tippecanoe_input']) < 1000:
        with open(parameters['tippecanoe_input'], "r") as json_file: geojson_content = json.load(json_file)
        if ('features' not in geojson_content) or (len(geojson_content['features']) == 0):
            geojson_content['features'] = [{"type":"Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [0,0]}}]
            with open(parameters['tippecanoe_input'], "w") as json_file: json.dump(geojson_content, json_file)

    with global_count.get_lock():
        global_count.value -= 1
        LogMessage("FINISHED: Create grid-sliced tippecanoe input file for: " + parameters['table_name'] + " [" + str(global_count.value) + " table(s) to be processed]")

def initPipeline(command_line):
    """
    Carry out tasks essential to subsequent tasks
    """

    global OSM_DOWNLOADS_FOLDER, OSM_MAIN_DOWNLOAD, BUILD_FOLDER, OSM_BOUNDARIES, OSM_BOUNDARIES_YML, OVERALL_CLIPPING_FILE, WORKING_FOLDER
    global POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, WORKING_CRS
    global PROCESSING_STATE_FILE

    with open(PROCESSING_STATE_FILE, 'w') as file: file.write(command_line)

    postgisDropLegacyTables()

    osm_main_download_path = OSM_DOWNLOADS_FOLDER + basename(OSM_MAIN_DOWNLOAD)
    osm_boundaries_table = reformatTableNameAbsolute(OSM_BOUNDARIES)
    osm_boundaries_osm_export_path = BUILD_FOLDER + OSM_BOUNDARIES
    osm_boundaries_gpkg = osm_boundaries_osm_export_path + '.gpkg'

    # If osm_boundaries_gkpg file does exist, quickly check layers - if no layers (likely that processing was interrupted), getGPKGProjection will delete it
    if isfile(osm_boundaries_gpkg): getGPKGProjection(osm_boundaries_gpkg)

    # If osm_boundaries_gpkg file doesn't exist, carry out OSM download using default OSM specification
    # (before any custom configuration) and run osm-export-tool on osm_boundaries_yml to generate osm_boundaries_gpkg

    if not isfile(osm_boundaries_gpkg):

        osmDownloadData()

        LogMessage("Generating " + basename(osm_boundaries_gpkg) + " from " + basename(OSM_MAIN_DOWNLOAD))

        if not isfile(OSM_BOUNDARIES_YML): LogFatalError("Missing file: " + OSM_BOUNDARIES_YML + ", aborting")

        # Note: 'osm-export-tool' needs path to .gpkg to be output but without .gpkg extension
        runSubprocess([ "osm-export-tool", osm_main_download_path, osm_boundaries_osm_export_path, "-m", OSM_BOUNDARIES_YML])

    osm_boundaries_projection = getGPKGProjection(osm_boundaries_gpkg)

    if not postgisCheckTableExists(osm_boundaries_table):

        LogMessage("Importing into PostGIS: " + basename(osm_boundaries_gpkg))

        scratch_table_1 = '_scratch_table_clipping'
        scratch_table_2 = '_scratch_table_preclipped_boundaries'
        overall_clipping_layer = reformatTableName(OVERALL_CLIPPING_FILE)

        if postgisCheckTableExists(scratch_table_1): postgisDropTable(scratch_table_1)
        if postgisCheckTableExists(scratch_table_2): postgisDropTable(scratch_table_2)

        LogMessage(" --> Step 1: Importing overall clipping layer (dissolved) into scratch table")

        runSubprocess([ "ogr2ogr", \
                        "-f", "PostgreSQL", \
                        'PG:host=' + POSTGRES_HOST + ' user=' + POSTGRES_USER + ' password=' + POSTGRES_PASSWORD + ' dbname=' + POSTGRES_DB, \
                        OVERALL_CLIPPING_FILE, \
                        "-nln", scratch_table_1, \
                        "-nlt", "MULTIPOLYGON", \
                        "-sql", \
                        "SELECT ST_Union(geom) geom FROM 'uk-clipping'", \
                        "--config", "OGR_PG_ENABLE_METADATA", "NO", \
                        "--config", "PG_USE_COPY", "YES" ])

        LogMessage(" --> Step 2: Importing unclipped boundaries into scratch table")

        # Note: clipping on OVERALL_CLIPPING_FILE as some osm boundaries - esp UK nations - are not clipped tightly on coastlines
        runSubprocess([ "ogr2ogr", \
                        "-f", "PostgreSQL", \
                        'PG:host=' + POSTGRES_HOST + ' user=' + POSTGRES_USER + ' password=' + POSTGRES_PASSWORD + ' dbname=' + POSTGRES_DB, \
                        osm_boundaries_gpkg, \
                        "-nln", scratch_table_2, \
                        "-nlt", "MULTIPOLYGON", \
                        "--config", "OGR_PG_ENABLE_METADATA", "NO", \
                        "--config", "PG_USE_COPY", "YES" ])

        LogMessage(" --> Step 3: Clipping partially overlapping polygons")

        postgisExec("""
        CREATE TABLE %s AS 
            SELECT data.fid, data.osm_id, data.name, data.council_name, data.boundary, data.admin_level, ST_Intersection(clipping.geom, data.geom) geom
            FROM %s data, %s clipping 
            WHERE 
                (NOT ST_Contains(clipping.geom, data.geom) AND 
                ST_Intersects(clipping.geom, data.geom));""", \
            (AsIs(osm_boundaries_table), AsIs(scratch_table_2), AsIs(scratch_table_1), ))

        LogMessage(" --> Step 4: Adding fully enclosed polygons")

        postgisExec("""
        INSERT INTO %s  
            SELECT data.fid, data.osm_id, data.name, data.council_name, data.boundary, data.admin_level, data.geom  
            FROM %s data, %s clipping 
            WHERE 
                ST_Contains(clipping.geom, data.geom);""", \
            (AsIs(osm_boundaries_table), AsIs(scratch_table_2), AsIs(scratch_table_1), ))

        if postgisCheckTableExists(scratch_table_1): postgisDropTable(scratch_table_1)
        if postgisCheckTableExists(scratch_table_2): postgisDropTable(scratch_table_2)

        LogMessage(" --> COMPLETED: Processed table: " + osm_boundaries_table)
        LogMessage("------------------------------------------------------------")

        # Once imported, add index to 'name', 'council_name' and 'admin_level' fields
        if postgisCheckTableExists(osm_boundaries_table):
            postgisExec("CREATE INDEX ON %s (name)", (AsIs(osm_boundaries_table), ))
            postgisExec("CREATE INDEX ON %s (council_name)", (AsIs(osm_boundaries_table), ))
            postgisExec("CREATE INDEX ON %s (admin_level)", (AsIs(osm_boundaries_table), ))

def getCountryFromArea(area):
    """
    Determine country that area is in using OSM_BOUNDARIES_GPKG
    """

    global OSM_BOUNDARIES
    global POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, WORKING_CRS
    global OSM_NAME_CONVERT

    osm_boundaries_table = reformatTableNameAbsolute(OSM_BOUNDARIES)
    countries = [OSM_NAME_CONVERT[country] for country in OSM_NAME_CONVERT.keys()]

    results = postgisGetResults("""
    WITH primaryarea AS
    (
        SELECT geom FROM %s WHERE (name = %s) OR (council_name = %s) LIMIT 1
    )
    SELECT 
        name, 
        ST_Area(ST_Intersection(primaryarea.geom, secondaryarea.geom)) geom_intersection 
    FROM %s secondaryarea, primaryarea 
    WHERE name = ANY (%s) AND ST_Intersects(primaryarea.geom, secondaryarea.geom) ORDER BY geom_intersection DESC LIMIT 1;
    """, (AsIs(osm_boundaries_table) , area, area, AsIs(osm_boundaries_table), countries, ))

    containing_country = results[0][0]

    for canonical_country in OSM_NAME_CONVERT.keys():
        if OSM_NAME_CONVERT[canonical_country] == containing_country: return canonical_country

    return None

def importDataset(dataset_parameters):
    """
    Imports dataset into PostGIS
    """

    downloaded_file, output_folder, imported_table, core_dataset_name = dataset_parameters[0], dataset_parameters[1], dataset_parameters[2], dataset_parameters[3]

    LogMessage("STARTING: Importing into PostGIS: " + downloaded_file)

    downloaded_file_fullpath = output_folder + downloaded_file

    sql_where_clause = None
    orig_srs = 'EPSG:4326'

    if downloaded_file.endswith('.geojson'):

        # Check GeoJSON for crs
        # If missing and in Northern Ireland, then use EPSG:29903
        # If missing and not in Northern Ireland, use EPSG:27700

        json_data = json.load(open(downloaded_file_fullpath))

        if 'crs' in json_data:
            orig_srs = json_data['crs']['properties']['name'].replace('urn:ogc:def:crs:', '').replace('::', ':').replace('OGC:1.3:CRS84', 'EPSG:4326')
        else:
            # DataMapWales' GeoJSON use EPSG:27700 even though default SRS for GeoJSON is EPSG:4326
            if 'wales' in downloaded_file: orig_srs = 'EPSG:27700'
            # Improvement Service GeoJSON uses EPSG:27700
            if 'local-nature-reserves--scotland' in downloaded_file: orig_srs = 'EPSG:27700'

            # Tricky - Northern Ireland could be in correct GeoJSON without explicit crs (so EPSG:4326) or could be incorrect non-EPSG:4326 meters with non GB datum
            if 'northern-ireland' in downloaded_file: orig_srs = 'EPSG:29903'
            # ... so provide exceptions
            if downloaded_file in ['world-heritage-sites--northern-ireland.geojson']: orig_srs = 'EPSG:4326'

        # Historic England Conservation Areas includes 'no data' polygons so remove as too restrictive
        if downloaded_file == 'conservation-areas--england.geojson': sql_where_clause = "Name NOT LIKE 'No data%'"

    # We set CRS=WORKING_CRS during download phase
    if downloaded_file.endswith('.gpkg'): orig_srs = WORKING_CRS

    # Strange bug in ogr2ogr where sometimes fails on GeoJSON with sqlite
    # Therefore avoid using sqlite unless absolutely necessary
    # Don't specify geometry type yet in order to preserve lines and polygons
    subprocess_list = [ "ogr2ogr", \
                        "-f", "PostgreSQL", \
                        'PG:host=' + POSTGRES_HOST + ' user=' + POSTGRES_USER + ' password=' + POSTGRES_PASSWORD + ' dbname=' + POSTGRES_DB, \
                        downloaded_file_fullpath, \
                        "-makevalid", \
                        "-overwrite", \
                        "-lco", "GEOMETRY_NAME=geom", \
                        "-lco", "OVERWRITE=YES", \
                        "-nln", imported_table, \
                        "-nlt", "PROMOTE_TO_MULTI", \
                        "-skipfailures", \
                        "-s_srs", orig_srs, \
                        "-t_srs", WORKING_CRS, \
                        "--config", "PG_USE_COPY", "YES" ]

    if sql_where_clause is not None:
        for extraitem in ["-dialect", "sqlite", "-sql", "SELECT * FROM '" + core_dataset_name + "' WHERE " + sql_where_clause]:
            subprocess_list.append(extraitem)

    for extraconfig in ["--config", "OGR_PG_ENABLE_METADATA", "NO"]: subprocess_list.append(extraconfig)

    runSubprocess(subprocess_list)

    LogMessage("FINISHED: Importing into PostGIS: " + downloaded_file)

def processDataset(dataset_parameters):
    """
    Process dataset
    """

    global PROCESSING_GRID_TABLE, HEIGHT_TO_TIP, BLADE_RADIUS, CUSTOM_CONFIGURATION

    dataset_id, dataset_name, clipping_union_table, REGENERATE_OUTPUT, HEIGHT_TO_TIP, BLADE_RADIUS, CUSTOM_CONFIGURATION = \
        dataset_parameters[0], dataset_parameters[1], dataset_parameters[2], dataset_parameters[3], dataset_parameters[4], dataset_parameters[5], dataset_parameters[6]

    dataset_id = str(dataset_id).zfill(4)
    prefix = buildQueuePrefix(dataset_id)

    scratch_table_1 = '_scratch_table_1_' + dataset_id
    scratch_table_2 = '_scratch_table_2_' + dataset_id
    scratch_table_3 = '_scratch_table_3_' + dataset_id

    if postgisCheckTableExists(scratch_table_1): postgisDropTable(scratch_table_1)
    if postgisCheckTableExists(scratch_table_2): postgisDropTable(scratch_table_2)
    if postgisCheckTableExists(scratch_table_3): postgisDropTable(scratch_table_3)

    processing_grid = reformatTableName(PROCESSING_GRID_TABLE)
    grid_square_ids = postgisGetResults("SELECT id FROM %s;", (AsIs(processing_grid), ))
    grid_square_ids = [item[0] for item in grid_square_ids]
    grid_square_count = len(grid_square_ids)

    buffer = getDatasetBuffer(dataset_name)
    source_table = reformatTableName(dataset_name)
    processed_table = buildProcessedTableName(source_table)

    with global_count.get_lock(): 
        LogMessage(prefix + "STARTING: Processing: " + source_table + " [" + str(global_count.value) + " dataset(s) to be processed]")

    if buffer is not None:
        buffered_table = buildBufferTableName(dataset_name, buffer)
        processed_table = buildProcessedTableName(buffered_table)
        table_exists = postgisCheckTableExists(buffered_table)
        if REGENERATE_OUTPUT or (not table_exists):
            LogMessage(prefix + "Adding " + buffer + "m buffer: " + source_table + " -> " + buffered_table)
            if table_exists: postgisDropTable(buffered_table)

            # Make special exception for hedgerow as hedgerow polygons represent boundaries that should be buffered as lines
            buffer_polygons_as_lines = False
            if 'hedgerow' in buffered_table: buffer_polygons_as_lines = True

            if buffer_polygons_as_lines:
                postgisExec("""
                CREATE TABLE %s AS 
                (
                    (SELECT ST_Buffer(geom::geography, %s)::geometry geom FROM %s WHERE ST_geometrytype(geom) = 'ST_LineString') UNION 
                    (SELECT ST_Buffer(ST_Boundary(geom)::geography, %s)::geometry geom FROM %s WHERE ST_geometrytype(geom) IN ('ST_Polygon', 'ST_MultiPolygon'))
                );""", \
                    (AsIs(buffered_table), float(buffer), AsIs(source_table), float(buffer), AsIs(source_table), ))
            else:
                postgisExec("CREATE TABLE %s AS SELECT ST_Buffer(geom::geography, %s)::geometry geom FROM %s;", \
                            (AsIs(buffered_table), float(buffer), AsIs(source_table), ))
            postgisExec("CREATE INDEX %s ON %s USING GIST (geom);", (AsIs(buffered_table + "_idx"), AsIs(buffered_table), ))
        source_table = buffered_table

    # Dump original or buffered layer and run processing on it

    processed_table_exists = postgisCheckTableExists(processed_table)
    if REGENERATE_OUTPUT or (not processed_table_exists):
        if processed_table_exists: postgisDropTable(processed_table)

        # Explode geometries with ST_Dump to remove MultiPolygon,
        # MultiSurface, etc and homogenize processing
        # Ideally all dumped tables should contain polygons only (either source or buffered source is (Multi)Polygon)
        # so filter on ST_Polygon

        LogMessage(prefix + source_table + ": Select only polygons, dump and make valid")

        postgisExec("CREATE TABLE %s AS SELECT ST_MakeValid(dumped.geom) geom FROM (SELECT (ST_Dump(geom)).geom geom FROM %s) dumped WHERE ST_geometrytype(dumped.geom) = 'ST_Polygon';", \
                    (AsIs(scratch_table_1), AsIs(source_table), ))

        postgisExec("CREATE INDEX %s ON %s USING GIST (geom);", (AsIs(scratch_table_1 + "_idx"), AsIs(scratch_table_1), ))

        LogMessage(prefix + source_table + ": Clipping partially overlapping polygons")

        postgisExec("""
        CREATE TABLE %s AS 
            SELECT ST_Intersection(clipping.geom, data.geom) geom
            FROM %s data, %s clipping 
            WHERE 
                (NOT ST_Contains(clipping.geom, data.geom) AND 
                ST_Intersects(clipping.geom, data.geom));""", \
            (AsIs(scratch_table_2), AsIs(scratch_table_1), AsIs(clipping_union_table), ))

        LogMessage(prefix + source_table + ": Adding fully enclosed polygons")

        postgisExec("""
        INSERT INTO %s  
            SELECT data.geom  
            FROM %s data, %s clipping 
            WHERE 
                ST_Contains(clipping.geom, data.geom);""", \
            (AsIs(scratch_table_2), AsIs(scratch_table_1), AsIs(clipping_union_table), ))

        LogMessage(prefix + source_table + ": Dumping geometries")

        postgisExec("CREATE TABLE %s AS SELECT (ST_Dump(geom)).geom geom FROM %s;", (AsIs(scratch_table_3), AsIs(scratch_table_2), ))
        postgisExec("CREATE INDEX %s ON %s USING GIST (geom);", (AsIs(scratch_table_3 + "_idx"), AsIs(scratch_table_3), ))

        LogMessage(prefix + source_table + ": Dissolving dataset")

        if postgisCheckTableExists(processed_table): postgisDropTable(processed_table)
        postgisExec("CREATE TABLE %s (id INTEGER, geom GEOMETRY(Polygon, 4326));", (AsIs(processed_table), ))
        postgisExec("CREATE INDEX %s ON %s(id);", (AsIs(processed_table + 'id_idx'), AsIs(processed_table), ))

        for grid_square_index in range(len(grid_square_ids)):
            grid_square_id = grid_square_ids[grid_square_index]

            LogMessage(prefix + source_table + ": Processing grid square " + str(grid_square_index + 1) + "/" + str(grid_square_count))

            postgisExec("""
            INSERT INTO %s 
                SELECT 
                    grid.id, 
                    (ST_Dump(ST_Union(ST_Intersection(grid.geom, dataset.geom)))).geom geom 
                FROM %s grid, %s dataset 
                WHERE grid.id = %s AND ST_geometrytype(dataset.geom) = 'ST_Polygon' GROUP BY grid.id""", (AsIs(processed_table), AsIs(processing_grid), AsIs(scratch_table_3), AsIs(grid_square_id), ))

        postgisExec("CREATE INDEX %s ON %s USING GIST (geom);", (AsIs(processed_table + "_idx"), AsIs(processed_table), ))

        if postgisCheckTableExists(scratch_table_1): postgisDropTable(scratch_table_1)
        if postgisCheckTableExists(scratch_table_2): postgisDropTable(scratch_table_2)
        if postgisCheckTableExists(scratch_table_3): postgisDropTable(scratch_table_3)

    with global_count.get_lock():
        global_count.value -= 1
        LogMessage(prefix + "FINISHED: Processed table: " + processed_table + " [" + str(global_count.value) + " dataset(s) to be processed]")

def runProcessingOnDownloads(output_folder):
    """
    Processes folder of GeoJSON and GPKG files
    - Adds buffers where appropriate
    - Joins and dissolves child datasets into single parent dataset
    - Joins and dissolves datasets into CKAN groups, one for each group
    - Create single final joined-and-dissolved dataset for entire CKAN database of datasets
    - Converts final files to GeoJSON (EPSG:4326)
    """

    global CUSTOM_CONFIGURATION, CUSTOM_CONFIGURATION_FILE_PREFIX, PROCESSING_START
    global DEBUG_RUN, HEIGHT_TO_TIP, WORKING_CRS, BUILD_FOLDER, OSM_MAIN_DOWNLOAD, OSM_EXPORT_DATA, OSM_BOUNDARIES
    global FINALLAYERS_OUTPUT_FOLDER, FINALLAYERS_CONSOLIDATED, OVERALL_CLIPPING_FILE, REGENERATE_INPUT, REGENERATE_OUTPUT
    global POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
    global OUTPUT_GRID_SPACING, OUTPUT_GRID_TABLE
    global PROCESSING_GRID_SPACING, PROCESSING_GRID_TABLE
    global QGIS_OUTPUT_FILE
    global MAPAPP_FITBOUNDS, MAPAPP_CENTER

    if REGENERATE_INPUT: REGENERATE_OUTPUT = True

    scratch_table_1 = '_scratch_table_1'
    scratch_table_2 = '_scratch_table_2'
    scratch_table_3 = '_scratch_table_3'

    # Prefix all output files with custom_configuration_prefix is CUSTOM_CONFIGURATION set

    custom_configuration_prefix = ''
    if CUSTOM_CONFIGURATION is not None: custom_configuration_prefix = CUSTOM_CONFIGURATION_FILE_PREFIX

    # Ensure all necessary folders exists

    makeFolder(BUILD_FOLDER)
    makeFolder(output_folder)
    makeFolder(FINALLAYERS_OUTPUT_FOLDER)

    # Import OSM-specific data files

    LogMessage("Processing all OSM-specific data layers...")

    custom_prefix = ''
    if CUSTOM_CONFIGURATION is not None: custom_prefix = CUSTOM_CONFIGURATION_FILE_PREFIX

    osm_layers = getOSMLookup()
    osm_export_file = BUILD_FOLDER + custom_prefix + OSM_EXPORT_DATA + '.gpkg'
    osm_export_projection = getGPKGProjection(osm_export_file)

    queue_subprocess = []
    for osm_layer in osm_layers:

        # reformatTableName will add CUSTOM_CONFIGURATION_TABLE_PREFIX to table name if using custom configuration file
        table_name = reformatTableName(osm_layer)
        table_exists = postgisCheckTableExists(table_name)

        if (not REGENERATE_INPUT) and table_exists: continue

        if postgisCheckTableExists(table_name): postgisDropTable(table_name)

        deleteAncestors(table_name)

        # Assume 'osm-export-tool' outputs in EPSG:4326 projection
        import_array = ["ogr2ogr", \
                        "-f", "PostgreSQL", \
                        'PG:host=' + POSTGRES_HOST + ' user=' + POSTGRES_USER + ' password=' + POSTGRES_PASSWORD + ' dbname=' + POSTGRES_DB, \
                        osm_export_file, \
                        "-overwrite", \
                        "-nln", table_name, \
                        "-lco", "GEOMETRY_NAME=geom", \
                        "-lco", "OVERWRITE=YES", \
                        "-dialect", "sqlite", \
                        "-sql", \
                        "SELECT * FROM '" + osm_layer + "'", \
                        "-s_srs", osm_export_projection, \
                        "-t_srs", WORKING_CRS, \
                        "--config", "OGR_PG_ENABLE_METADATA", "NO", \
                        "--config", "PG_USE_COPY", "YES" ]

        queue_subprocess.append(["Importing " + custom_prefix + OSM_EXPORT_DATA + ".gpkg OSM layer into PostGIS: " + osm_layer, import_array])

    multiprocessSubprocess(queue_subprocess)

    LogMessage("Finished processing all OSM-specific data layers")

    # Import overall clipping into PostGIS

    # If custom configuration has 'clipping' defined, use this instead of default overall clipping

    clipping = None
    if CUSTOM_CONFIGURATION is not None:
        if 'clipping' in CUSTOM_CONFIGURATION:
            clipping = CUSTOM_CONFIGURATION['clipping']

            # Convert area names into OSM names
            # For example convert 'northern-ireland' (internal area name) to 'Northern Ireland / Tuaisceart Éireann' (OSM name)
            for clipping_index in range(len(clipping)):
                clipping_current = clipping[clipping_index].lower()
                if clipping_current in OSM_NAME_CONVERT: clipping[clipping_index] = OSM_NAME_CONVERT[clipping_current]
                clipping[clipping_index] = "'" + clipping[clipping_index] + "'"

    # reformatTableName will add CUSTOM_CONFIGURATION_TABLE_PREFIX to table name if using custom configuration file
    # so if using custom config, new copy of clipping_table will be created at CUSTOM_CONFIGURATION_TABLE_PREFIX + 'overall_clipping'

    clipping_table = reformatTableName(OVERALL_CLIPPING_FILE)

    if not postgisCheckTableExists(clipping_table):

        # If CUSTOM_CONFIGURATION requires specific area, modify how we create overall clipping area

        if clipping is None:

            LogMessage("Importing into PostGIS: " + OVERALL_CLIPPING_FILE)

            clipping_file_projection = getGPKGProjection(OVERALL_CLIPPING_FILE)

            runSubprocess([ "ogr2ogr", \
                            "-f", "PostgreSQL", \
                            'PG:host=' + POSTGRES_HOST + ' user=' + POSTGRES_USER + ' password=' + POSTGRES_PASSWORD + ' dbname=' + POSTGRES_DB, \
                            OVERALL_CLIPPING_FILE, \
                            "-overwrite", \
                            "-nln", clipping_table, \
                            "-lco", "GEOMETRY_NAME=geom", \
                            "-lco", "OVERWRITE=YES", \
                            "-s_srs", clipping_file_projection, \
                            "-t_srs", WORKING_CRS, \
                            "--config", "OGR_PG_ENABLE_METADATA", "NO"])

        else:

            osm_boundaries_table = reformatTableNameAbsolute(OSM_BOUNDARIES)

            if not postgisCheckTableExists(osm_boundaries_table): LogFatalError("Essential boundaries table '" + osm_boundaries_table + "' missing - aborting")

            LogMessage("Creating custom clipping boundaries for " + ",".join(clipping) + " from " + osm_boundaries_table)

            postgisExec("CREATE TABLE %s AS SELECT geom FROM %s WHERE (name IN (%s)) OR (council_name IN (%s)) ", (AsIs(clipping_table), AsIs(osm_boundaries_table), AsIs(",".join(clipping)), AsIs(",".join(clipping)), ))
            postgisExec("CREATE INDEX %s ON %s USING GIST (geom);", (AsIs(clipping_table + "_idx"), AsIs(clipping_table), ))

    LogMessage("Checking/creating union of clipping layer - may be default clipping layer or custom clipping layer...")

    clipping_union_table = buildUnionTableName(clipping_table)

    if not postgisCheckTableExists(clipping_union_table):

        LogMessage("Running ST_Union within PostGIS: " + clipping_table + " -> " + clipping_union_table)

        postgisExec("CREATE TABLE %s AS SELECT ST_Union(geom) geom FROM %s", \
                    (AsIs(clipping_union_table), AsIs(clipping_table), ))
        postgisExec("CREATE INDEX %s ON %s USING GIST (geom);", (AsIs(clipping_union_table + "_idx"), AsIs(clipping_union_table), ))

    LogMessage("Finished checking/creating union of clipping layer")

    # If custom clipping, get bounds and centre

    if CUSTOM_CONFIGURATION is not None:
        if 'clipping' in CUSTOM_CONFIGURATION:
            bounds = postgisGetResults("""
            SELECT 
                ST_XMin(ST_Envelope(geom)) AS min_x, 
                ST_YMin(ST_Envelope(geom)) AS min_y,
                ST_XMax(ST_Envelope(geom)) AS max_x,
                ST_YMax(ST_Envelope(geom)) AS max_y
            FROM
                %s;""", (AsIs(clipping_union_table), ))
            bounds = bounds[0]
            MAPAPP_FITBOUNDS = [[bounds[0], bounds[1]], [bounds[2], bounds[3]]]
            MAPAPP_CENTER = [float((bounds[0] + bounds[2]) / 2), float((bounds[1] + bounds[3]) / 2)]

    # Output bounds and center Javascript for use in map app

    outputBoundsAndCenterJavascript()

    # Create output grid

    output_grid = reformatTableName(OUTPUT_GRID_TABLE)

    if not postgisCheckTableExists(output_grid):

        LogMessage("Creating grid overlay to improve mbtiles rendering performance and quality")

        postgisExec("CREATE TABLE %s AS SELECT ST_Transform((ST_SquareGrid(%s, ST_Transform(geom, 3857))).geom, 4326) geom FROM %s;",
                    (AsIs(output_grid), AsIs(OUTPUT_GRID_SPACING), AsIs(clipping_union_table), ))

    # Create processing grid

    processing_grid = reformatTableName(PROCESSING_GRID_TABLE)

    if not postgisCheckTableExists(processing_grid):

        LogMessage("Creating grid overlay to reduce memory load during ST_Union")

        postgisExec("CREATE TABLE %s AS SELECT ST_Transform((ST_SquareGrid(%s, ST_Transform(geom, 3857))).geom, 4326) geom FROM %s;",
                    (AsIs(processing_grid), AsIs(PROCESSING_GRID_SPACING), AsIs(clipping_union_table), ))
        postgisExec("ALTER TABLE %s ADD COLUMN id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY", (AsIs(processing_grid), ))
        postgisExec("DELETE FROM %s WHERE id IN (SELECT grid.id FROM %s grid, %s clipping WHERE ST_Intersects(grid.geom, clipping.geom) IS FALSE);", \
                    (AsIs(processing_grid), AsIs(processing_grid), AsIs(clipping_union_table), ))
        postgisExec("CREATE INDEX %s ON %s USING GIST (geom);", (AsIs(processing_grid + "_idx"), AsIs(processing_grid), ))

    # Populate list of grid square ids

    grid_square_ids = postgisGetResults("SELECT id FROM %s;", (AsIs(processing_grid), ))
    grid_square_ids = [item[0] for item in grid_square_ids]
    grid_square_count = len(grid_square_ids)

    # Import all GeoJSON into PostGIS

    LogMessage("Importing downloaded files into PostGIS...")

    current_datasets = getStructureDatasets()
    downloaded_files = getFilesInFolder(output_folder)

    # Create in-memory list of PostGIS tables and update whenever table dropped to save time
    all_tables = postgisGetAllTables()
    
    queue_index, queue_dict, queue_import = 1, {}, []
    for downloaded_file in downloaded_files:
        queue_index += 1

        core_dataset_name = getCoreDatasetName(downloaded_file)

        # reformatTableName will add CUSTOM_CONFIGURATION_TABLE_PREFIX to table name if using custom configuration file

        imported_table = reformatTableName(core_dataset_name)
        tableexists = (imported_table in all_tables)

        if (not REGENERATE_INPUT) and tableexists: continue

        # If CUSTOM_CONFIGURATION set, only import specific files in custom configuration
        # But typically we import everything in downloads folder

        if CUSTOM_CONFIGURATION is not None:
            if core_dataset_name not in current_datasets: continue

        # If importing dataset, delete import table and all derived files and tables as data may have changed
        if tableexists: 
            postgisDropTable(imported_table)
            all_tables.remove(imported_table)

        # Important to update all_tables (list of active PostGIS tables) in case deleteAncestors drops tables
        all_tables = deleteAncestors(imported_table, all_tables)

        priority = os.path.getsize(join(output_folder, downloaded_file))
        if downloaded_file.endswith('.geojson'): priority = (4 * priority)
        queue_dict_index = getQueueKey(priority, queue_index)
        queue_dict[queue_dict_index] = [downloaded_file, output_folder, imported_table, core_dataset_name]

    if len(queue_dict) != 0:

        queue_dict = dict(sorted(queue_dict.items(), reverse=True))
        queue_datasets = [queue_dict[item] for item in queue_dict]
        chunksize = 1

        multiprocessBefore()

        with Pool(processes=getNumberProcesses()) as p: p.map(importDataset, queue_datasets, chunksize=chunksize)

        multiprocessAfter()

    LogMessage("All downloaded files imported into PostGIS")

    # Add buffers where appropriate to GPKG

    LogMessage("Adding buffers to PostGIS and clipping all tables...")
    LogMessage("------------------------------------------------------------")

    structure_lookup = getStructureLookup()
    groups = structure_lookup.keys()
    parents_lookup = {}

    queue_index, queue_dict = 0, {}
    for group in groups:
        for parent in structure_lookup[group].keys():
            for dataset_name in structure_lookup[group][parent]:
                queue_index += 1
                priority_multiplier = 1
                buffer = getDatasetBuffer(dataset_name)
                orig_table = reformatTableName(dataset_name)
                source_table = reformatTableName(dataset_name)
                processed_table = buildProcessedTableName(source_table)
                if buffer is not None:
                    buffered_table = buildBufferTableName(dataset_name, buffer)
                    processed_table = buildProcessedTableName(buffered_table)
                    source_table = buffered_table
                    # Buffered tables prioritised as inherently more time-consuming
                    priority_multiplier = 100
                parent = getTableParent(source_table)
                if parent not in parents_lookup: parents_lookup[parent] = []
                parents_lookup[parent].append(processed_table)

                priority = priority_multiplier * postgisGetTableSize(orig_table)
                queue_dict_index = getQueueKey(priority, queue_index)
                queue_dict[queue_dict_index] = [queue_index, dataset_name, clipping_union_table, REGENERATE_OUTPUT, HEIGHT_TO_TIP, BLADE_RADIUS, CUSTOM_CONFIGURATION]

    if len(queue_dict) != 0:

        num_datasets_to_process = Value('i', len(queue_dict))
        queue_dict = dict(sorted(queue_dict.items(), reverse=True))
        queue_datasets = [queue_dict[item] for item in queue_dict]
        chunksize = 1

        multiprocessBefore()

        with Pool(processes=getNumberProcesses(), initializer=init_globals_count, initargs=(num_datasets_to_process, )) as p:
            p.map(processDataset, queue_datasets, chunksize=chunksize)

        multiprocessAfter()

    LogMessage("============================================================")
    LogMessage("*** All buffers added to PostGIS and all tables clipped ****")
    LogMessage("============================================================")

    # Amalgamating layers with common 'parents'

    LogMessage("Amalgamating and dissolving layers with common parents...")

    queue_index, finallayers, queue_dict = 0, [], {}
    parents = parents_lookup.keys()
    for parent in parents:
        parent_table = buildFinalLayerTableName(parent)
        finallayers.append(reformatDatasetName(parent_table))
        parent_table_exists = postgisCheckTableExists(parent_table)
        if REGENERATE_OUTPUT or (not parent_table_exists):
            queue_index += 1
            amalgamate_output = "Amalgamating and dissolving children of parent: " + parent
            if parent_table_exists: postgisDropTable(parent_table)
            # Delete any tables and files that are derived from this table
            deleteDatasetAndAncestors(parent_table)
            priority = 0
            for child in parents_lookup[parent]: priority += postgisGetTableSize(child)
            queue_dict_index = getQueueKey(priority, queue_index)
            queue_dict[queue_dict_index] = [queue_index, amalgamate_output, parent_table, parents_lookup[parent], PROCESSING_GRID_TABLE, CUSTOM_CONFIGURATION]

    if len(queue_dict) != 0:

        num_datasets_to_process = Value('i', len(queue_dict))
        queue_dict = dict(sorted(queue_dict.items(), reverse=True))
        queue_datasets = [queue_dict[item] for item in queue_dict]
        chunksize = 1

        multiprocessBefore()

        with Pool(processes=getNumberProcesses(), initializer=init_globals_count, initargs=(num_datasets_to_process, )) as p:
            p.map(postgisAmalgamateAndDissolve, queue_datasets, chunksize=chunksize)

        multiprocessAfter()

    LogMessage("============================================================")
    LogMessage("**** All common parent layers amalgamated and dissolved ****")
    LogMessage("============================================================")

    # Amalgamating datasets by group

    LogMessage("Amalgamating and dissolving layers by group...")

    queue_index, queue_dict = 0, {}
    for group in groups:
        group_items = list((structure_lookup[group]).keys())
        if group_items is None: continue
        group_table = buildFinalLayerTableName(group)
        finallayers.append(reformatDatasetName(group_table))
        group_table_exists = postgisCheckTableExists(group_table)
        group_items.sort()
        if REGENERATE_OUTPUT or (not group_table_exists):
            queue_index += 1
            amalgamate_output = "Amalgamating and dissolving datasets of group: " + group
            # Don't do anything if there is only one element with same name as group
            if (len(group_items) == 1) and (group == group_items[0]): continue
            if group_table_exists: postgisDropTable(group_table)
            # Delete any tables and files that are derived from this table
            deleteDatasetAndAncestors(group_table)
            children = [buildFinalLayerTableName(table_name) for table_name in group_items]
            priority = 0
            for child in children: priority += postgisGetTableSize(child)
            queue_dict_index = getQueueKey(priority, queue_index)
            queue_dict[queue_dict_index] = [queue_index, amalgamate_output, group_table, children, PROCESSING_GRID_TABLE, CUSTOM_CONFIGURATION]

    if len(queue_dict) != 0:

        num_datasets_to_process = Value('i', len(queue_dict))
        queue_dict = dict(sorted(queue_dict.items(), reverse=True))
        queue_datasets = [queue_dict[item] for item in queue_dict]
        chunksize = 1

        multiprocessBefore()

        with Pool(processes=getNumberProcesses(), initializer=init_globals_count, initargs=(num_datasets_to_process, )) as p:
            p.map(postgisAmalgamateAndDissolve, queue_datasets, chunksize=chunksize)

        multiprocessAfter()

    LogMessage("============================================================")
    LogMessage("******* All group layers amalgamated and dissolved *********")
    LogMessage("============================================================")

    # Amalgamating all groups as single layer

    # TODO: Implement multiprocessing version of postgisAmalgamateAndDissolve to improve performance when running it once on final layer

    LogMessage("Amalgamating and dissolving all groups as single overall layer...")

    alllayers_table = buildFinalLayerTableName(FINALLAYERS_CONSOLIDATED)
    final_file_geojson = FINALLAYERS_OUTPUT_FOLDER + custom_configuration_prefix + reformatDatasetName(alllayers_table) + '.geojson'
    final_file_gpkg = FINALLAYERS_OUTPUT_FOLDER + custom_configuration_prefix + reformatDatasetName(alllayers_table) + '.gpkg'
    finallayers.append(reformatDatasetName(alllayers_table))
    alllayers_table_exists = postgisCheckTableExists(alllayers_table)
    if REGENERATE_OUTPUT or (not alllayers_table_exists):
        amalgamate_output = "Amalgamating and dissolving single overall layer: " + FINALLAYERS_CONSOLIDATED
        if alllayers_table_exists: postgisDropTable(alllayers_table)
        children = [buildFinalLayerTableName(table_name) for table_name in groups]
        multiprocessAmalgamateAndDissolve([0, amalgamate_output, alllayers_table, children, PROCESSING_GRID_TABLE])

    LogMessage("============================================================")
    LogMessage("*** All groups amalgamated and dissolved as single layer ***")
    LogMessage("============================================================")

    # Exporting final layers to GeoJSON and GPKG

    LogMessage("Converting final layers to GPKG, SHP and GeoJSON...")

    shp_extensions = ['shp', 'dbf', 'shx', 'prj']

    is_custom_configuration = (CUSTOM_CONFIGURATION is not None)

    # Export from database first...

    filecopy_queue = []
    for finallayer in finallayers:
        finallayer_table = reformatTableName(finallayer)
        core_dataset_name = getFinalLayerCoreDatasetName(finallayer_table)
        latest_name = getFinalLayerLatestName(finallayer_table)
        temp_gpkg = FINALLAYERS_OUTPUT_FOLDER  + 'temp.gpkg'
        finallayer_file_gpkg = FINALLAYERS_OUTPUT_FOLDER + custom_configuration_prefix + finallayer + '.gpkg'

        if isfile(temp_gpkg): os.remove(temp_gpkg)

        # We don't need custom prefix for latest file as it's always just latest
        finallayer_latest_file_gpkg = FINALLAYERS_OUTPUT_FOLDER + latest_name + '.gpkg' 

        if is_custom_configuration or REGENERATE_OUTPUT or (not isfile(finallayer_file_gpkg)):
            LogMessage("Exporting final layer to: " + finallayer_file_gpkg)
            if isfile(finallayer_file_gpkg): os.remove(finallayer_file_gpkg)
            inputs = runSubprocess(["ogr2ogr", \
                            temp_gpkg, \
                            'PG:host=' + POSTGRES_HOST + ' user=' + POSTGRES_USER + ' password=' + POSTGRES_PASSWORD + ' dbname=' + POSTGRES_DB, \
                            "-overwrite", \
                            "-nln", core_dataset_name, \
                            "-nlt", 'POLYGON', \
                            "-dialect", "sqlite", \
                            "-sql", \
                            "SELECT geom geometry FROM '" + finallayer_table + "'", \
                            "-s_srs", WORKING_CRS, \
                            "-t_srs", 'EPSG:4326'])
            checkGPKGIsValid(temp_gpkg, core_dataset_name, inputs)
            # Only copy file to final destination once process has completed - this prevents half-finished files being created
            shutil.copy(temp_gpkg, finallayer_file_gpkg)
            if isfile(temp_gpkg): os.remove(temp_gpkg)

        # Always copy to latest just to be safe
        filecopy_queue.append(["Copying final layer GPKG to: " + finallayer_latest_file_gpkg, finallayer_file_gpkg, finallayer_latest_file_gpkg])

    multiprocessFileCopy(filecopy_queue)

    # Then use ogr2ogr without PostGIS to convert exported GPKG to other formats - GeoJSON and SHP

    filecopy_queue = []
    for finallayer in finallayers:
        finallayer_table = reformatTableName(finallayer)
        core_dataset_name = getFinalLayerCoreDatasetName(finallayer_table)
        latest_name = getFinalLayerLatestName(finallayer_table)
        temp_geojson = FINALLAYERS_OUTPUT_FOLDER + 'temp.geojson'
        temp_shp = FINALLAYERS_OUTPUT_FOLDER + 'temp.shp'
        finallayer_file_gpkg = FINALLAYERS_OUTPUT_FOLDER + custom_configuration_prefix + finallayer + '.gpkg'
        finallayer_file_shp = FINALLAYERS_OUTPUT_FOLDER + custom_configuration_prefix + finallayer + '.shp'
        finallayer_file_geojson = FINALLAYERS_OUTPUT_FOLDER + custom_configuration_prefix + finallayer + '.geojson'

        if isfile(temp_geojson): os.remove(temp_geojson)
        if isfile(temp_shp):
            for shp_extension in shp_extensions:
                temp_individual_shp = FINALLAYERS_OUTPUT_FOLDER + 'temp.' + shp_extension
                if isfile(temp_individual_shp): os.remove(temp_individual_shp)

        # We don't need custom prefix for latest file as it's always just latest
        finallayer_latest_file_shp = FINALLAYERS_OUTPUT_FOLDER + latest_name + '.shp'
        finallayer_latest_file_geojson = FINALLAYERS_OUTPUT_FOLDER + latest_name + '.geojson'

        if is_custom_configuration or REGENERATE_OUTPUT or (not isfile(finallayer_file_shp)):
            LogMessage("Converting final layer GPKG to: " + finallayer_file_shp)
            for shp_extension in shp_extensions:
                if isfile(finallayer_file_shp.replace('shp', shp_extension)): os.remove(finallayer_file_shp.replace('shp', shp_extension))
                if isfile(finallayer_latest_file_shp.replace('shp', shp_extension)): os.remove(finallayer_latest_file_shp.replace('shp', shp_extension))
            if not runSubprocessReturnBoolean(["ogr2ogr", temp_shp, finallayer_file_gpkg]): LogOutOfMemoryAndQuit()

            for shp_extension in shp_extensions:
                temp_individual_shp = FINALLAYERS_OUTPUT_FOLDER + 'temp.' + shp_extension
                shutil.copy(temp_individual_shp, finallayer_file_shp.replace('shp', shp_extension))
                if isfile(temp_individual_shp): os.remove(temp_individual_shp)

        # Always copy to latest just to be safe - can't easily use multiprocessFileCopy as we need SHP to convert to GeoJSON
        LogMessage("Copying final layer SHP to: " + finallayer_latest_file_shp)
        for shp_extension in shp_extensions:
            shutil.copy(finallayer_file_shp.replace('shp', shp_extension), finallayer_latest_file_shp.replace('shp', shp_extension))

        if is_custom_configuration or REGENERATE_OUTPUT or (not isfile(finallayer_file_geojson)):
            LogMessage("Converting final layer SHP to: " + finallayer_file_geojson)
            if isfile(finallayer_file_geojson): os.remove(finallayer_file_geojson)
            # Convert existing output .shp to .geojson to using pyshp streaming to reduce memory load
            convertSHP2GeoJSON(finallayer_latest_file_shp, temp_geojson, core_dataset_name)

            # As we're outputting new geojson, delete corresponding mbtiles file if exists
            finallayer_latest_mbtiles = TILESERVER_DATA_FOLDER + basename(finallayer_latest_file_geojson).replace('.geojson', '.mbtiles')
            if isfile(finallayer_latest_mbtiles): os.remove(finallayer_latest_mbtiles)
            # Only copy file to final destination once process has completed - this prevents half-finished files being processed by mistake
            shutil.copy(temp_geojson, finallayer_file_geojson)
            if isfile(temp_geojson): os.remove(temp_geojson)

        # Always copy to latest just to be safe
        filecopy_queue.append(["Copying final layer GeoJSON to: " + finallayer_latest_file_geojson, finallayer_file_geojson, finallayer_latest_file_geojson])

    multiprocessFileCopy(filecopy_queue)

    LogMessage("All final layers converted to GPKG, SHP and GeoJSON")

    # Build tile server files

    buildTileserverFiles()

    # Build QGIS file

    buildQGISFile()

    processing_time = time.time() - PROCESSING_START
    processing_time_minutes = round(processing_time / 60, 1)
    processing_time_hours = round(processing_time / (60 * 60), 1)
    time_text = str(processing_time_minutes) + " minutes (" + str(processing_time_hours) + " hours) to complete"
    LogMessage("**** Completed processing - " + time_text + " ****")

    run_script = './run-cli.sh'
    if BUILD_FOLDER == 'build-docker/': run_script = './run-docker.sh'

    qgis_text = ''
    if isfile(QGIS_OUTPUT_FILE):
        qgis_text = """QGIS file created at:

\033[1;94m""" + QGIS_OUTPUT_FILE + """\033[0m


"""

    if isfile(final_file_geojson) and isfile(final_file_gpkg):
        print("""
\033[1;34m***********************************************************************
**************** OPEN WIND ENERGY BUILD PROCESS COMPLETE **************
***********************************************************************\033[0m

Final composite layers for turbine height to tip """ + formatValue(HEIGHT_TO_TIP) + """m, blade radius """ + formatValue(BLADE_RADIUS) + """m created at:

\033[1;94m""" + final_file_geojson + """
""" + final_file_gpkg + """\033[0m


To view latest wind constraint layers as map, enter:

\033[1;94m""" + run_script + """\033[0m


""" + qgis_text)

    else:
        LogMessage("ERROR: Failed to created one or more final files")

def installTileserverFonts():
    """
    Installs fonts required for tileserver-gl
    """

    global BUILD_FOLDER, TILESERVER_FOLDER

    LogMessage("Attempting tileserver fonts installation...")

    tileserver_font_folder = TILESERVER_FOLDER + 'fonts/'

    if BUILD_FOLDER == 'build-docker/':

        # On docker openwindenergy-fonts container copies fonts to 'fonts/' folder
        # So need to wait for it to finish this

        while True:
            if isdir(tileserver_font_folder):
                LogMessage("Tileserver fonts folder already exists - SUCCESS")
                return True
            time.sleep(5)

    else:

        # Server build clones fonts from https://github.com/open-wind/openmaptiles-fonts.git
        if isdir(tileserver_font_folder): 
            LogMessage("Tileserver fonts folder already exists - SUCCESS")
            return True

        # Download tileserver fonts

        if not isdir(basename(TILESERVER_FONTS_GITHUB)):

            LogMessage("Downloading tileserver fonts")

            inputs = runSubprocess(["git", "clone", TILESERVER_FONTS_GITHUB])

        working_dir = os.getcwd()
        os.chdir(basename(TILESERVER_FONTS_GITHUB))

        LogMessage("Generating PBF fonts")

        if not runSubprocessReturnBoolean(["npm", "install"]):
            os.chdir(working_dir)
            return False

        if not runSubprocessReturnBoolean(["node", "./generate.js"]):
            os.chdir(working_dir)
            return False

        os.chdir(working_dir)

        LogMessage("Copying PBF fonts to tileserver folder")

        tileserver_font_folder_src = basename(TILESERVER_FONTS_GITHUB) + '/_output'

        shutil.copytree(tileserver_font_folder_src, tileserver_font_folder)

        return True

def generateTippecanoeInput():
    """
    Generates grid-sliced GeoJSON ready for Tippecanoe
    """

def buildTileserverFiles():
    """
    Builds files required for tileserver-gl
    """

    global  CUSTOM_CONFIGURATION, CUSTOM_CONFIGURATION_FILE_PREFIX, LATEST_OUTPUT_FILE_PREFIX, TEMP_FOLDER
    global  OVERALL_CLIPPING_FILE, TILESERVER_URL, TILESERVER_FONTS_GITHUB, TILESERVER_SRC_FOLDER, TILESERVER_FOLDER, TILESERVER_DATA_FOLDER, TILESERVER_STYLES_FOLDER, \
            OSM_DOWNLOADS_FOLDER, OSM_MAIN_DOWNLOAD, BUILD_FOLDER, FINALLAYERS_OUTPUT_FOLDER, FINALLAYERS_CONSOLIDATED, MAPAPP_FOLDER
    global  TILEMAKER_COASTLINE_CONFIG, TILEMAKER_COASTLINE_PROCESS, TILEMAKER_OMT_CONFIG, TILEMAKER_OMT_PROCESS, SKIP_FONTS_INSTALLATION, OPENMAPTILES_HOSTED_FONTS

    # Run tileserver build process

    LogMessage("Creating tileserver files")

    makeFolder(TILESERVER_FOLDER)
    makeFolder(TILESERVER_DATA_FOLDER)
    makeFolder(TILESERVER_STYLES_FOLDER)
    makeFolder(TEMP_FOLDER)

    # Legacy issue: housekeeping of final output and tileserver folders due to shortening of
    # specific dataset names leaving old files with old names that cause problems
    # Also general shortening of output filenames to allow for blade radius information

    legacy_delete_items = ['tipheight-', 'public-roads-a-and-b-roads-and-motorways', 'openwind.json']
    for legacy_delete_item in legacy_delete_items:
        for file_name in getFilesInFolder(FINALLAYERS_OUTPUT_FOLDER):
            if legacy_delete_item in file_name: os.remove(FINALLAYERS_OUTPUT_FOLDER + file_name)
        for file_name in getFilesInFolder(TILESERVER_DATA_FOLDER):
            if legacy_delete_item in file_name: os.remove(TILESERVER_DATA_FOLDER + file_name)
        for file_name in getFilesInFolder(TILESERVER_STYLES_FOLDER):
            if legacy_delete_item in file_name: os.remove(TILESERVER_STYLES_FOLDER + file_name)

    # Copy 'sprites' folder

    if not isdir(TILESERVER_FOLDER + 'sprites/'):
        shutil.copytree(TILESERVER_SRC_FOLDER + 'sprites/', TILESERVER_FOLDER + 'sprites/')

    # Copy index.html

    shutil.copy(TILESERVER_SRC_FOLDER + 'index.html', MAPAPP_FOLDER + 'index.html')

    # Modify 'openmaptiles.json' and export to tileserver folder

    openmaptiles_style_file_src = TILESERVER_SRC_FOLDER + 'openmaptiles.json'
    openmaptiles_style_file_dst = TILESERVER_STYLES_FOLDER + 'openmaptiles.json'
    openmaptiles_style_json = getJSON(openmaptiles_style_file_src)
    openmaptiles_style_json['sources']['openmaptiles']['url'] = TILESERVER_URL + '/data/openmaptiles.json'

    # Either use hosted version of fonts or install local fonts folder

    use_font_folder = False
    if SKIP_FONTS_INSTALLATION:
        fonts_url = OPENMAPTILES_HOSTED_FONTS
    else:
        if installTileserverFonts():
            use_font_folder = True
            fonts_url = TILESERVER_URL + '/fonts/{fontstack}/{range}.pbf'
        else:
            LogMessage("Attempt to build fonts failed, using hosted fonts instead")
            fonts_url = OPENMAPTILES_HOSTED_FONTS

    openmaptiles_style_json['glyphs'] = fonts_url

    with open(openmaptiles_style_file_dst, "w") as json_file: json.dump(openmaptiles_style_json, json_file, indent=4)

    attribution = "Source data copyright of multiple organisations. For all data sources, see <a href=\"" + CKAN_URL + "\" target=\"_blank\">" + CKAN_URL.replace('https://', '') + "</a>"
    openwind_style_file = TILESERVER_STYLES_FOLDER + 'openwindenergy.json'
    openwind_style_json = openmaptiles_style_json
    openwind_style_json['name'] = 'Open Wind Energy'
    openwind_style_json['id'] = 'openwindenergy'
    openwind_style_json['sources']['attribution']['attribution'] += " " + attribution

    basemap_mbtiles = TILESERVER_DATA_FOLDER + basename(OSM_MAIN_DOWNLOAD).replace(".osm.pbf", ".mbtiles")

    # Create basemap mbtiles

    if not isfile(basemap_mbtiles):

        osmDownloadData()

        LogMessage("Creating basemap: " + basename(basemap_mbtiles))

        LogMessage("Generating global coastline mbtiles...")

        bbox_entireworld = "-180,-85,180,85"
        bbox_unitedkingdom_padded = "-49.262695,38.548165,39.990234,64.848937"

        inputs = runSubprocess(["tilemaker", \
                                "--input", OSM_DOWNLOADS_FOLDER + basename(OSM_MAIN_DOWNLOAD), \
                                "--output", basemap_mbtiles, \
                                "--bbox", bbox_unitedkingdom_padded, \
                                "--process", TILEMAKER_COASTLINE_PROCESS, \
                                "--config", TILEMAKER_COASTLINE_CONFIG ])

        LogMessage("Merging " + basename(OSM_MAIN_DOWNLOAD) + " into global coastline mbtiles...")

        inputs = runSubprocess(["tilemaker", \
                                "--input", OSM_DOWNLOADS_FOLDER + basename(OSM_MAIN_DOWNLOAD), \
                                "--output", basemap_mbtiles, \
                                "--merge", \
                                "--process", TILEMAKER_OMT_PROCESS, \
                                "--config", TILEMAKER_OMT_CONFIG ])

        LogMessage("Basemap mbtiles created: " + basename(basemap_mbtiles))

    # Run tippecanoe regardless of whether existing mbtiles exist

    style_lookup = getStyleLookup()
    dataset_style_lookup = {}
    for style_item in style_lookup:
        dataset_id = style_item['dataset']
        dataset_style_lookup[dataset_id] = {'title': style_item['title'], 'color': style_item['color'], 'level': style_item['level'], 'defaultactive': style_item['defaultactive']}
        if 'children' in style_item:
            for child in style_item['children']:
                child_dataset_id = child['dataset']
                dataset_style_lookup[child_dataset_id] = {'title': child['title'], 'color': child['color'], 'level': child['level'], 'defaultactive': child['defaultactive']}

    # Get bounds of clipping area for use in tileserver-gl config file creation

    clipping_table = reformatTableName(OVERALL_CLIPPING_FILE)
    clipping_union_table = buildUnionTableName(clipping_table)
    clipping_bounds_dict = postgisGetTableBounds(clipping_union_table)
    clipping_bounds = [clipping_bounds_dict['left'], clipping_bounds_dict['bottom'], clipping_bounds_dict['right'], clipping_bounds_dict['top']]

    output_files = getFilesInFolder(FINALLAYERS_OUTPUT_FOLDER)
    styles, data = {}, {}
    styles["openwindenergy"] = {
      "style": "openwindenergy.json",
      "tilejson": {
        "type": "overlay",
        "bounds": clipping_bounds
      }
    }
    styles["openmaptiles"] = {
      "style": "openmaptiles.json",
      "tilejson": {
        "type": "overlay",
        "bounds": clipping_bounds
      }
    }
    data["openmaptiles"] = {
      "mbtiles": basename(basemap_mbtiles)
    }

    custom_configuration_file_prefix = ''
    if CUSTOM_CONFIGURATION is not None: custom_configuration_file_prefix = CUSTOM_CONFIGURATION_FILE_PREFIX

    # Insert overall constraints as first item in list so it appears as first item in tileserver-gl
    overallconstraints = getFinalLayerLatestName(FINALLAYERS_CONSOLIDATED) + '.geojson'

    if overallconstraints in output_files: output_files.remove(overallconstraints)
    if not isfile(FINALLAYERS_OUTPUT_FOLDER + overallconstraints): LogFatalError("Final overall constraints layer is missing")

    # Set prefix for only those files we're interested in processing with Tippecanoe
    required_prefix = custom_configuration_file_prefix + LATEST_OUTPUT_FILE_PREFIX

    # Tippecanoe is used to create mbtiles for all 'latest--...' / 'custom--latest...' GeoJSONs

    queue_index, queue_dict = 0, {}
    output_files.insert(0, overallconstraints)
    for output_file in output_files:
        queue_index += 1

        # Only process GeoJSONs with required_prefix
        if (not output_file.startswith(required_prefix)) or (not output_file.endswith('.geojson')): continue

        # derived_dataset_name will begin with required_prefix, ie. 'latest--'
        # or 'custom--latest--' as we've specifically filtered on required_prefix
        derived_dataset_name = basename(output_file).replace('.geojson', '')

        # Don't process any datasets that are not in dataset_style_lookup (flat list of all used outputted datasets)
        if derived_dataset_name not in dataset_style_lookup: continue

        # original_table_name for all outputs will begin 'tip-...'
        # as we store pre-output geometries with these specific table names
        original_table_name = getOutputFileOriginalTable(output_file)

        # core_dataset_name refers to essential dataset, eg. 'scheduled-ancient-monuments'
        # or 'ecology-and-wildlife', which is shared between non-custom and custom modes
        # and also across some early-stage and pre-output database tables.
        # For example:
        # derived_dataset_name = 'custom--latest--ecology-and-wildlife'
        # core_dataset_name = 'ecology-and-wildlife'
        core_dataset_name = getCoreDatasetName(derived_dataset_name)

        tippecanoe_output = TILESERVER_DATA_FOLDER + output_file.replace('.geojson', '.mbtiles')

        style_id = derived_dataset_name
        style_name = dataset_style_lookup[derived_dataset_name]['title']

        # If tippecanoe failed previously for any reason, delete the output and intermediary file

        tippecanoe_interrupted_file = tippecanoe_output + '-journal'
        if isfile(tippecanoe_interrupted_file):
            os.remove(tippecanoe_interrupted_file)
            if isfile(tippecanoe_output): os.remove(tippecanoe_output)

        # Create grid-clipped version of GeoJSON to input into tippecanoe to improve mbtiles rendering and performance

        if not isfile(tippecanoe_output):

            tippecanoe_grid_clipped_file = join(TEMP_FOLDER,  'tippecanoe--grid-clipped--' + core_dataset_name + '.geojson')
            queue_parameters =  { \
                                    'dataset_name': core_dataset_name, \
                                    'derived_dataset_name': derived_dataset_name, \
                                    'table_name': original_table_name, \
                                    'style_name': style_name, \
                                    'tippecanoe_input': tippecanoe_grid_clipped_file, \
                                    'tippecanoe_output': tippecanoe_output
                                }
            
            priority = os.path.getsize(join(FINALLAYERS_OUTPUT_FOLDER, output_file))
            queue_dict_index = getQueueKey(priority, queue_index)
            queue_dict[queue_dict_index] = queue_parameters

        LogMessage("Created tileserver-gl style file for: " + output_file)

        style_color = dataset_style_lookup[derived_dataset_name]['color']
        style_level = dataset_style_lookup[derived_dataset_name]['level']
        style_defaultactive = dataset_style_lookup[derived_dataset_name]['defaultactive']
        style_opacity = 0.8 if style_level == 1 else 0.5
        style_file = TILESERVER_STYLES_FOLDER + style_id + '.json'
        style_json = {
            "version": 8,
            "id": style_id,
            "name": style_name,
            "sources": {
              	derived_dataset_name: {
                    "type": "vector",
                    "buffer": 512,
                    "url": TILESERVER_URL + "/data/" + style_id + ".json",
                    "attribution": attribution
                }
            },
            "glyphs": fonts_url,
            "layers": [
                {
                    "id": style_id,
                    "source": style_id,
                    "source-layer": style_id,
                    "type": "fill",
                    "paint": {
                        "fill-opacity": style_opacity,
                        "fill-color": style_color
                    }
                }
            ]
        }

        openwind_style_json['sources'][style_id] = style_json['sources'][derived_dataset_name]
        with open(style_file, "w") as json_file: json.dump(style_json, json_file, indent=4)

        openwind_layer = style_json['layers'][0]
        # Temporary workaround as setting 'fill-outline-color'='#FFFFFF00' on individual style breaks WMTS
        openwind_layer['paint']['fill-outline-color'] = "#FFFFFF00"
        if style_defaultactive: openwind_layer['layout'] = {'visibility': 'visible'}
        else: openwind_layer['layout'] = {'visibility': 'none'}

        # Hide overall constraint layer
        if core_dataset_name == FINALLAYERS_CONSOLIDATED: openwind_layer['layout'] = {'visibility': 'none'}

        openwind_style_json['layers'].append(openwind_layer)

        styles[style_id] = {
            "style": basename(style_file),
            "tilejson": {
                "type": "overlay",
                "bounds": clipping_bounds
            }
        }
        data[style_id] = {
            "mbtiles": basename(tippecanoe_output)
        }

    # Run multiprocessing to create Tippecanoe grid-sliced input files

    num_items_to_process = Value('i', len(queue_dict))
    queue_dict = dict(sorted(queue_dict.items(), reverse=True))
    queue_items = [queue_dict[item] for item in queue_dict]
    chunksize = 1

    multiprocessBefore()

    with Pool(processes=getNumberProcesses(), initializer=init_globals_count, initargs=(num_items_to_process, )) as p:
        p.map(createGridClippedFile, queue_items, chunksize=chunksize)

    multiprocessAfter()

    with open(openwind_style_file, "w") as json_file: json.dump(openwind_style_json, json_file, indent=4)

    # Creating final tileserver-gl config file

    config_file = TILESERVER_FOLDER + 'config.json'
    if use_font_folder:
        config_json = {
            "options": {
                "paths": {
                "root": "",
                "fonts": "fonts",
                "sprites": "sprites",
                "styles": "styles",
                "mbtiles": "data"
                }
            },
            "styles": styles,
            "data": data
        }
    else:
        config_json = {
            "options": {
                "paths": {
                "root": "",
                "sprites": "sprites",
                "styles": "styles",
                "mbtiles": "data"
                }
            },
            "styles": styles,
            "data": data
        }

    for item in queue_items:
            
        LogMessage("Creating mbtiles for: " + item['table_name'])

        inputs = runSubprocess(["tippecanoe", \
                                "-Z4", "-z15", \
                                "-X", \
                                "--generate-ids", \
                                "--force", \
                                "-n", item['style_name'], \
                                "-l", item['derived_dataset_name'], \
                                item['tippecanoe_input'], \
                                "-o", item['tippecanoe_output'] ])

        if isfile(item['tippecanoe_input']): os.remove(item['tippecanoe_input'])

        if not isfile(item['tippecanoe_output']):
            LogError("Failed to create mbtiles: " + basename(item['tippecanoe_output']))
            LogFatalError("*** Aborting process *** ")

    with open(config_file, "w") as json_file: json.dump(config_json, json_file, indent=4)

    if isdir(TEMP_FOLDER): shutil.rmtree(TEMP_FOLDER)

    LogMessage("All tileserver files created")

def buildQGISFile():
    """
    Builds QGIS file
    """

    # Uses separate process to allow use of QGIS-specific Python

    global QGIS_PYTHON_PATH, QGIS_OUTPUT_FILE

    LogMessage("Attempting to generate QGIS file...")

    if not isfile(QGIS_PYTHON_PATH):

        LogMessage(" --> Unable to locate QGIS Python at: " + QGIS_PYTHON_PATH)
        LogMessage(" --> Edit your .env file to include the full path to QGIS's Python and rerun")
        LogMessage(" --> *** SKIPPING QGIS FILE CREATION ***")

    else:

        runSubprocessAndOutput([QGIS_PYTHON_PATH, 'build-qgis.py', QGIS_OUTPUT_FILE])


# ***********************************************************
# ***********************************************************
# ********************* MAIN APPLICATION ********************
# ***********************************************************
# ***********************************************************

def main():
    """
    Main function - put here to allow multiprocessing to work
    """

    global SERVER_BUILD, PROCESSING_START
    global BUILD_FOLDER, LOG_SINGLE_PASS, PROCESSING_COMPLETE_FILE, HEIGHT_TO_TIP, BLADE_RADIUS
    global CUSTOM_CONFIGURATION, REGENERATE_INPUT, REGENERATE_OUTPUT, PERFORM_DOWNLOAD, SKIP_FONTS_INSTALLATION
    global CKAN_URL, DATASETS_DOWNLOADS_FOLDER, PROCESSING_COMPLETE_FILE, PROCESSING_STATE_FILE

    PROCESSING_START = time.time()

    makeFolder(BUILD_FOLDER)

    if SERVER_BUILD:
        if isfile(PROCESSING_COMPLETE_FILE):
            LogMessage("Previous build run complete, aborting this run")
            exit(0)

    time.sleep(3)

    print("""\033[1;34m
***********************************************************************
******************** OPEN WIND ENERGY DATA PIPELINE *******************
***********************************************************************
\033[0m""")

    with open('PROCESSINGSTART', 'w', encoding='utf-8') as file: 
        file.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S,000 Processing started"))

    LogMessage("***********************************************************************")
    LogMessage("*************** Starting Open Wind Energy data pipeline ***************")
    LogMessage("***********************************************************************")
    LogMessage("")

    postgisWaitRunning()

    LogMessage("Processing command line arguments...")

    if len(sys.argv) > 1:
        arg_index, height_to_tip_set, blade_radius_set = 0, False, False
        for arg in sys.argv:
            arg = arg.strip()
            if isfloat(arg):
                if not height_to_tip_set:
                    HEIGHT_TO_TIP = float(arg)
                    height_to_tip_set = True
                    LogMessage("************ Using HEIGHT_TO_TIP value: " + formatValue(HEIGHT_TO_TIP) + ' metres ************')
                else:
                    BLADE_RADIUS = float(arg)
                    blade_radius_set = True
                    LogMessage("************ Using BLADE_RADIUS value: " + formatValue(BLADE_RADIUS) + ' metres ************')

            if arg == '--custom':
                if len(sys.argv) > arg_index:
                    customconfig = sys.argv[arg_index + 1]
                    LogMessage("--custom argument passed: Using custom configuration '" + customconfig + "'")
                    CUSTOM_CONFIGURATION = processCustomConfiguration(customconfig)

            if arg == '--clip':
                if len(sys.argv) > arg_index:
                    # *** This will override any 'clipping' setting in '--custom', above
                    clippingarea = sys.argv[arg_index + 1]
                    LogMessage("--clip argument passed: Using custom clipping area '" + clippingarea + "'")
                    CUSTOM_CONFIGURATION = processClippingArea(clippingarea)

            if arg == '--purgeall':
                LogMessage("--purgeall argument passed: Clearing database and all build files")
                REGENERATE_INPUT = True
                REGENERATE_OUTPUT = True
                purgeAll()

            if arg == '--purgedb':
                LogMessage("--purgedb argument passed: Clearing database")
                REGENERATE_INPUT = True
                REGENERATE_OUTPUT = True
                postgisDropAllTables()

            if arg == '--purgederived':
                LogMessage("--purgederived argument passed: Clearing derived database tables")
                REGENERATE_OUTPUT = True
                postgisDropDerivedTables()

            if arg == '--purgeamalgamated':
                LogMessage("--purgeamalgamated argument passed: Clearing amalgamated database tables")
                REGENERATE_OUTPUT = True
                postgisDropAmalgamatedTables()

            if arg == '--skipdownload':
                LogMessage("--skipdownload argument passed: Skipping download stage")
                PERFORM_DOWNLOAD = False

            if arg == '--skipfonts':
                LogMessage("--skipfonts argument passed: Skipping font installation and using hosted CDN fonts")
                SKIP_FONTS_INSTALLATION = True

            if arg == '--buildtileserver':
                LogMessage("--buildtileserver argument passed: Building files required for tileserver")
                buildTileserverFiles()
                exit()

            if arg == '--regenerate':
                if len(sys.argv) > arg_index:
                    regeneratedataset = sys.argv[arg_index + 1]
                    LogMessage("--regenerate argument passed: Redownloading and rebuilding all tables related to " + regeneratedataset)
                    deleteDatasetAndAncestors(regeneratedataset)

            if arg == '--help':
                print("""
Command syntax:

python3 openwindenergy.py
- Uses default values for turbine height-to-tip and blade-radius values.

python3 openwindenergy.py [HEIGHT TO TIP]
- Where 'HEIGHT TO TIP' is height-to-tip in metres of target wind turbine. Uses default blade-radius.

python3 openwindenergy.py [HEIGHT TO TIP] [BLADE RADIUS]
- Where 'HEIGHT TO TIP' is height-to-tip in metres and 'BLADE RADIUS' is blade-radius in metres of target wind turbine.

Possible additional arguments:

--custom               Supply custom YML configuration file. Can be local file path, internet url or name on CKAN open data portal (https://data.openwind.energy).
--clip                 Supply custom area for clipping. Uses OSM name from osm-boundaries.gpkg. Overrides any 'clipping' setting in custom YML.
--purgeall             Clear all downloads and database tables as if starting fresh.
--purgedb              Clear all PostGIS tables and reexport final layer files.
--purgederived         Clear all derived (ie. non-core data) PostGIS tables and reexport final layer files.
--purgeamalgamated     Clear all amalgamated PostGIS tables and reexport final layer files.
--skipdownload         Skip download stage and just do PostGIS processing.
--skipfonts            Skip font installation stage and use hosted version of openmaptiles fonts.
--regenerate dataset   Regenerate specific dataset by redownloading and recreating all tables relating to dataset.
--buildtileserver      Rebuild files for tileserver.

""")
                exit()

            arg_index += 1

    initPipeline(rebuildCommandLine(sys.argv))

    if PERFORM_DOWNLOAD:
        downloadDatasets(CKAN_URL, DATASETS_DOWNLOADS_FOLDER)

    runProcessingOnDownloads(DATASETS_DOWNLOADS_FOLDER)
    
    # Set up status flag files

    with open(PROCESSING_COMPLETE_FILE, 'w') as file: file.write("PROCESSINGCOMPLETE")
    if isfile(PROCESSING_STATE_FILE): os.remove(PROCESSING_STATE_FILE)

# Only remove log file on main thread
if __name__ == "__main__":
    if isfile(LOG_SINGLE_PASS): os.remove(LOG_SINGLE_PASS)

# Always initialise logging so multiprocessing threads get logged
initLogging()

if __name__ == "__main__": main()
