# ***********************************************************
# *********************** OPEN WIND *************************
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
# Copyright (c) Stefan Haselwimmer, WeWantWind.org, 2025
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
import geopandas as gpd
import pandas as pd
from requests import Request
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

BUILD_FOLDER                    = 'build-cli/'
QGIS_PYTHON_PATH                = '/usr/bin/python3'
CKAN_URL                        = 'https://data.openwind.energy'
TILESERVER_URL                  = 'http://localhost:8080'

# Allow certain variables to be changed using environment variables

if os.environ.get("BUILD_FOLDER") is not None: BUILD_FOLDER = os.environ.get('BUILD_FOLDER')
if os.environ.get("QGIS_PYTHON_PATH") is not None: QGIS_PYTHON_PATH = os.environ.get('QGIS_PYTHON_PATH')
if os.environ.get("CKAN_URL") is not None: CKAN_URL = os.environ.get('CKAN_URL')
if os.environ.get("TILESERVER_URL") is not None: TILESERVER_URL = os.environ.get('TILESERVER_URL')

DEFAULT_HEIGHT_TO_TIP           = 124.2 # Based on openwind's own manual data on all failed and successful UK onshore wind projects
HEIGHT_TO_TIP                   = DEFAULT_HEIGHT_TO_TIP
OSM_MAIN_DOWNLOAD               = 'https://download.geofabrik.de/europe/united-kingdom-latest.osm.pbf'
OSM_CONFIG_FOLDER               = BUILD_FOLDER + 'osm-export-yml/'
OSM_EXPORT_DATA                 = 'osm-export'
DATASETS_MANUAL_FOLDER          = 'manuallydownloaded/'
DATASETS_DOWNLOADS_FOLDER       = BUILD_FOLDER + 'datasets-downloads/'
OSM_LOOKUP                      = BUILD_FOLDER + 'datasets-osm.json'
STRUCTURE_LOOKUP                = BUILD_FOLDER + 'datasets-structure.json'
BUFFER_LOOKUP                   = BUILD_FOLDER + 'datasets-buffers.json'
STYLE_LOOKUP                    = BUILD_FOLDER + 'datasets-style.json'
MAPAPP_FOLDER                   = BUILD_FOLDER + 'app/'
MAPAPP_JS                       = MAPAPP_FOLDER + 'datasets-latest-style.js'

TILESERVER_FONTS_GITHUB         = 'https://github.com/openmaptiles/fonts'
TILESERVER_SRC_FOLDER           = 'tileserver/'
TILESERVER_FOLDER               = BUILD_FOLDER + 'tileserver/'
TILESERVER_DATA_FOLDER          = TILESERVER_FOLDER + 'data/'
TILESERVER_STYLES_FOLDER        = TILESERVER_FOLDER + 'styles/'
TILEMAKER_DOWNLOAD_SCRIPT       = TILESERVER_SRC_FOLDER + 'get-coastline-landcover.sh'
TILEMAKER_COASTLINE             = 'coastline/'
TILEMAKER_LANDCOVER             = 'landcover/'
TILEMAKER_COASTLINE_CONFIG      = TILESERVER_SRC_FOLDER + 'config-coastline.json'
TILEMAKER_COASTLINE_PROCESS     = TILESERVER_SRC_FOLDER + 'process-coastline.lua'
TILEMAKER_OMT_CONFIG            = TILESERVER_SRC_FOLDER + 'config-openmaptiles.json'
TILEMAKER_OMT_PROCESS           = TILESERVER_SRC_FOLDER + 'process-openmaptiles.lua'
QGIS_OUTPUT_FILE                = BUILD_FOLDER + "windconstraints--latest.qgs"
FINALLAYERS_OUTPUT_FOLDER       = BUILD_FOLDER + 'output/'
FINALLAYERS_CONSOLIDATED        = 'windconstraints'
PERFORM_DOWNLOAD                = True
REGENERATE_INPUT                = False
REGENERATE_OUTPUT               = False
OVERALL_CLIPPING_FILE           = 'uk--clipping.gpkg'
WORKING_CRS                     = 'EPSG:4326'
POSTGRES_HOST                   = os.environ.get("POSTGRES_HOST")
POSTGRES_DB                     = os.environ.get("POSTGRES_DB")
POSTGRES_USER                   = os.environ.get("POSTGRES_USER")
POSTGRES_PASSWORD               = os.environ.get("POSTGRES_PASSWORD")
DEBUG_RUN                       = False
OPENMAPTILES_HOSTED_FONTS       = "https://cdn.jsdelivr.net/gh/open-wind/openmaptiles-fonts/fonts/{fontstack}/{range}.pbf"
SKIP_FONTS_INSTALLATION         = False

# Output grid is used to cut up final output into grid squares 
# in order to improve quality and performance of rendering 

OUTPUT_GRID_SPACING             = 100000 # Size of grid squares in metres, ie. 100km
OUTPUT_GRID_TABLE               = 'uk__output_grid__100000_m'

# Redirect ogr2ogr warnings to log file
os.environ['CPL_LOG'] = 'log.txt'

logging.basicConfig(
    format='%(asctime)s [%(levelname)-2s] %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S')

# ***********************************************************
# ***************** General helper functions ****************
# ***********************************************************

def getJSON(json_path):
    """
    Gets contents of JSON file
    """

    with open(json_path, "r") as json_file: return json.load(json_file)

def makeFolder(folderpath):
    """
    Make folder if it doesn't already exist
    """

    if not exists(folderpath): makedirs(folderpath)

def getFilesInFolder(folderpath):
    """
    Get list of all files in folder
    Create folder if it doesn't exist
    """

    makeFolder(folderpath)
    files = [f for f in listdir(folderpath) if ((f != '.DS_Store') and (isfile(join(folderpath, f))))]
    if files is not None: files.sort()
    return files

def LogMessage(logtext):
    """
    Logs message to console with timestamp
    """

    logging.info(logtext)

def LogError(logtext):
    """
    Logs error message to console with timestamp
    """

    logging.error("*** ERROR *** " + logtext)

def attemptDownloadUntilSuccess(url, file_path):
    """
    Keeps attempting download until successful
    """

    while True:
        try:
            urllib.request.urlretrieve(url, file_path)
            return
        except:
            LogError("Attempt to retrieve " + url + " failed so retrying")
            time.sleep(5)

def attemptGETUntilSuccess(url):
    """
    Keeps attempting GET request until successful
    """

    while True:
        try:
            response = requests.get(url)
            return response
        except:
            LogError("Attempt to retrieve " + url + " failed so retrying")
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
            LogError("Attempt to retrieve " + url + " failed so retrying")
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

    global  BUILD_FOLDER, OSM_MAIN_DOWNLOAD, TILEMAKER_DOWNLOAD_SCRIPT, TILEMAKER_COASTLINE, TILEMAKER_LANDCOVER, TILEMAKER_COASTLINE_CONFIG

    makeFolder(BUILD_FOLDER)

    if not isfile(BUILD_FOLDER + basename(OSM_MAIN_DOWNLOAD)):
        LogMessage("Downloading latest OSM data for britain and ireland")
        runSubprocess(["wget", OSM_MAIN_DOWNLOAD, "-O", BUILD_FOLDER + basename(OSM_MAIN_DOWNLOAD)])

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

def postgisGetAllTables():
    """
    Gets list of all tables in database
    """

    return postgisGetResults("""
    SELECT tables.table_name
    FROM information_schema.tables
    WHERE 
    table_catalog=%s AND 
    table_schema='public' AND 
    table_type='BASE TABLE' AND
    table_name NOT IN ('spatial_ref_sys');
    """, (POSTGRES_DB, ))

def postgisGetDerivedTables():
    """
    Gets list of all derived tables in database
    """

    # Derived tables:
    # Any 'buf'fered
    # Any 'pro'cessed
    # Any final layer 'tipheight_...'

    return postgisGetResults("""
    SELECT tables.table_name
    FROM information_schema.tables
    WHERE 
    table_catalog=%s AND 
    table_schema='public' AND 
    table_type='BASE TABLE' AND
    table_name NOT IN ('spatial_ref_sys') AND
    (
        (table_name LIEK '%%__buf') OR 
        (table_name LIKE '%%__pro') OR 
        (table_name LIKE 'tipheight%%') 
    );
    """, (POSTGRES_DB, ))

def postgisGetAmalgamatedTables():
    """
    Gets list of all amalgamated tables in database
    """

    return postgisGetResults("""
    SELECT tables.table_name
    FROM information_schema.tables
    WHERE 
    table_catalog=%s AND 
    table_schema='public' AND 
    table_type='BASE TABLE' AND
    table_name NOT IN ('spatial_ref_sys') AND
    table_name LIKE 'tipheight%%';
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

    alltables = postgisGetAllTables()

    for table in alltables:
        table_name, = table
        postgisDropTable(table_name)

def postgisDropDerivedTables():
    """
    Drops all derived tables in schema
    """

    LogMessage(" --> Dropping all tipheight_... and ...__clp tables")

    derivedtables = postgisGetDerivedTables()

    for table in derivedtables:
        table_name, = table
        postgisDropTable(table_name)

def postgisDropAmalgamatedTables():
    """
    Drops all amalgamated tables in schema
    """

    LogMessage(" --> Dropping all tipheight_... tables")

    derivedtables = postgisGetAmalgamatedTables()

    for table in derivedtables:
        table_name, = table
        postgisDropTable(table_name)

def postgisAmalgamateAndDissolve(target_table, child_tables):
    """
    Amalgamates and dissolves all child tables into target table 
    """

    # Delete any tables and files that are derived from this table

    deleteDataset(target_table)

    scratch_table_1 = '_scratch_table_1'
    scratch_table_2 = '_scratch_table_2'

    # We run process on all children - even if only one child - as process runs 
    # ST_Union (dissolve) on datasets for first time to eliminate overlapping polygons
     
    children_sql = " UNION ".join(['SELECT geom FROM ' + table_name for table_name in child_tables])

    if postgisCheckTableExists(scratch_table_1): postgisDropTable(scratch_table_1)
    if postgisCheckTableExists(scratch_table_2): postgisDropTable(scratch_table_2)

    LogMessage("Starting amalgamation and dissolving for: " + target_table)

    LogMessage(" --> Step 1: Amalgamate and dump all tables")
    postgisExec("CREATE TABLE %s AS SELECT (ST_Dump(children.geom)).geom geom FROM (%s) AS children;", \
                (AsIs(scratch_table_1), AsIs(children_sql), ))

    LogMessage(" --> Step 2: Dissolve all geometries")
    postgisExec("CREATE TABLE %s AS SELECT ST_Union(geom) geom FROM %s;", \
                (AsIs(scratch_table_2), AsIs(scratch_table_1), ))

    LogMessage(" --> Step 3: Save dumped geometries")
    postgisExec("CREATE TABLE %s AS SELECT (ST_Dump(geom)).geom geom FROM %s;", \
                (AsIs(target_table), AsIs(scratch_table_2), ))

    LogMessage(" --> COMPLETED: Created amalgamated and dissolved table: " + target_table)

    if postgisCheckTableExists(scratch_table_1): postgisDropTable(scratch_table_1)
    if postgisCheckTableExists(scratch_table_2): postgisDropTable(scratch_table_2)

    postgisExec("CREATE INDEX %s ON %s USING GIST (geom);", (AsIs(target_table + "_idx"), AsIs(target_table), ))

def postgisGetTableBounds(table_name):
    """
    Get bounds of all geometries in table
    """

    global POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD

    conn = psycopg2.connect(host=POSTGRES_HOST, dbname=POSTGRES_DB, user=POSTGRES_USER, password=POSTGRES_PASSWORD)
    cur = conn.cursor()
    cur.execute("""
    SELECT 
        MIN(ST_XMin(geom)) left,
        MIN(ST_YMin(geom)) bottom,
        MAX(ST_XMax(geom)) right,
        MAX(ST_YMax(geom)) top FROM %s;
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
 
def runSubprocess(subprocess_array):
    """
    Runs subprocess
    """

    output = subprocess.run(subprocess_array)

    # print("\n" + " ".join(subprocess_array) + "\n")

    if output.returncode != 0:
        LogError("subprocess.run failed with error code: " + str(output.returncode) + '\n' + " ".join(subprocess_array))
        exit()
    return " ".join(subprocess_array)

def runSubprocessAndOutput(subprocess_array):
    """
    Runs subprocess and prints output of process
    """

    output = subprocess.run(subprocess_array, capture_output=True, text=True)

    LogMessage(output.stdout.strip())

    if output.returncode != 0:
        LogError("subprocess.run failed with error code: " + str(output.returncode) + '\n' + " ".join(subprocess_array))
        exit()

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
                LogMessage(file_path + " has no layers - deleting and quitting")
                os.remove(file_path)
                exit()
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
                LogError("*** Error may be due to lack of memory (increase memory and retry) or corrupt PostGIS table (delete table and rerun) ***")
                exit()
            else:
                firstrow = dict(result[0])
                if firstrow['table_name'] != layer_name:
                    LogError(file_path + " does not have first layer " + layer_name + " - aborting")
                    print(len(result), json.dumps(firstrow, indent=4))
                    # os.remove(file_path)
                    LogError("Reproduce error by manually entering:\n" + inputs)
                    LogError("*** Error may be due to lack of memory (increase memory and retry) or corrupt PostGIS table (delete table and rerun) ***")
                    exit()
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
    """

    datasettitle = normalizeTitle(datasettitle)
    datasettitle = datasettitle.replace('.geojson', '').replace('.gpkg', '')
    reformatted_name = datasettitle.lower().replace(' - ', '--').replace(' ','-').replace('_','-').replace('(', '').replace(')', '')
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

def reformatTableName(name):
    """
    Reformats names, eg. dataset names, to be compatible with Postgres
    """

    return name.replace('.gpkg', '').replace("-", "_")

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

def buildFinalLayerTableName(layername):
    """
    Builds final layer table name
    Test for whether layer is turbine-height dependent and if so incorporate HEIGHT_TO_TIP parameter into name
    """

    global HEIGHT_TO_TIP

    dataset_parent = getDatasetParent(layername)

    if isTurbineHeightDependent(dataset_parent):
        return "tipheight_" + formatValue(HEIGHT_TO_TIP).replace(".", "_") + "m__" + reformatTableName(dataset_parent)
    return "tipheight_any__" + reformatTableName(dataset_parent)

def formatValue(value):
    """
    Formats float value to be short and readable
    """

    return str(round(value, 1)).replace('.0', '')

def getOriginalTable(table_name):
    """
    Gets original table used to generate output file
    """

    global HEIGHT_TO_TIP

    original_table_name = reformatTableName(table_name).replace("latest__", "")

    if 'tipheight' not in original_table_name: original_table_name = buildFinalLayerTableName(original_table_name)

    return original_table_name

def getCoreDatasetName(file_path):
    """
    Gets core dataset name from file path
    Core dataset = 'description--location', eg 'national-parks--scotland'
    """

    file_basename = basename(file_path).split(".")[0]
    elements = file_basename.split("--")
    if elements[0] == 'latest': return "--".join(elements[1:2])
    return "--".join(elements[0:2])

def getFinalLayerCoreDatasetName(table_name):
    """
    Gets core dataset name from final layer table name
    """

    dataset_name = reformatDatasetName(table_name)
    if dataset_name.startswith('tipheight'): dataset_name = '--'.join(dataset_name.split('--')[1:])
    return dataset_name

def getFinalLayerLatestName(table_name):
    """
    Gets latest name from table name, eg. 'tipheight-135m--ecology-and-wildlife...' -> 'latest--ecology-and-wildlife...'
    """

    dataset_name = reformatDatasetName(table_name)
    elements = dataset_name.split("--")
    if len(elements) > 1: return "latest--" + "--".join(elements[1:])
    else: return "latest--" + dataset_name

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
    """

    return "__".join(table_name.split("__")[0:1])

# ***********************************************************
# ********** Application data structure functions ***********
# ***********************************************************

def deleteDatasetFiles(dataset):
    """
    Deletes all files specifically relating to dataset
    """

    global HEIGHT_TO_TIP, DATASETS_DOWNLOADS_FOLDER, FINALLAYERS_OUTPUT_FOLDER, TILESERVER_DATA_FOLDER

    possible_extensions = ['geojson', 'gpkg', 'shp', 'shx', 'dbf', 'prj', 'sld', 'mbtiles']

    table = reformatTableName(dataset)
    height_to_tip_text = formatValue(HEIGHT_TO_TIP).replace('.', '-') + 'm'
    for possible_extension in possible_extensions:
        dataset_basename = dataset + '.' + possible_extension
        latest_basename = getFinalLayerLatestName(table) + '.' + possible_extension
        possible_files = []
        possible_files.append(DATASETS_DOWNLOADS_FOLDER + dataset_basename)
        possible_files.append(FINALLAYERS_OUTPUT_FOLDER + latest_basename)
        possible_files.append(FINALLAYERS_OUTPUT_FOLDER + 'tipheight-any--' + dataset_basename)
        possible_files.append(FINALLAYERS_OUTPUT_FOLDER + 'tipheight-' + height_to_tip_text + '--' + dataset_basename)
        possible_files.append(TILESERVER_DATA_FOLDER + latest_basename)

        for possible_file in possible_files:
            if isfile(possible_file): 
                LogMessage(" --> Deleting: " + possible_file)
                os.remove(possible_file)

def deleteDatasetTables(dataset):
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

    for possible_table in possible_tables:
        if postgisCheckTableExists(possible_table):
            LogMessage(" --> Dropping PostGIS table: " + possible_table)
            postgisDropTable(possible_table)

def deleteDataset(dataset):
    """
    Deletes specific dataset by deleting all files and tables specifically associated 
    with dataset and all ancestor files and ancestor tables containing dataset
    """

    dataset = dataset.split('.')[0]

    LogMessage("Deleting files related to: " + dataset)

    ancestors = getAllAncestors(dataset)

    for ancestor in ancestors:
        deleteDatasetFiles(ancestor)
        deleteDatasetTables(ancestor)

def isSpecificDatasetHeightDependent(dataset_name):
    """
    Returns true or false, depending on whether specific dataset (ignoring children) is turbine-height dependent
    """

    buffer_lookup = getBufferLookup()
    if dataset_name in buffer_lookup:
        buffer_value = buffer_lookup[dataset_name]
        if 'height-to-tip' in buffer_value: return True
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

def getAllAncestors(dataset_name):
    """
    Gets all ancestors of dataset
    """

    global FINALLAYERS_CONSOLIDATED

    # We know FINALLAYERS_CONSOLIDATED is ultimate ancestor of every dataset

    allancestors = [FINALLAYERS_CONSOLIDATED, dataset_name]

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

    global BUILD_FOLDER, MAPAPP_FOLDER, STRUCTURE_LOOKUP, MAPAPP_JS, HEIGHT_TO_TIP, FINALLAYERS_CONSOLIDATED

    makeFolder(BUILD_FOLDER)
    makeFolder(MAPAPP_FOLDER)

    structure_lookup = {}
    style_items = [
    {
        "title": "All constraint layers",
        "color": "darkgrey",
        "dataset": "latest--" + FINALLAYERS_CONSOLIDATED,
        "level": 1,
        "children": [],
        "defaultactive": False,
        'height-to-tip': formatValue(HEIGHT_TO_TIP)
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
                            'height-to-tip': formatValue(HEIGHT_TO_TIP)
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
                                                'height-to-tip': formatValue(HEIGHT_TO_TIP)
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

    javascript_content = 'var openwind_structure = ' + json.dumps({'tipheight': formatValue(HEIGHT_TO_TIP), 'datasets': style_items}, indent=4) + ';'

    with open(STRUCTURE_LOOKUP, "w") as json_file: json.dump(structure_hierarchy_lookup, json_file, indent=4)
    with open(STYLE_LOOKUP, "w") as json_file: json.dump(style_items, json_file, indent=4)
    with open(MAPAPP_JS, "w") as javascript_file: javascript_file.write(javascript_content)
    
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

def getDatasetBuffer(datasetname):
    """
    Gets buffer for dataset 'datasetname'
    """

    global HEIGHT_TO_TIP

    buffer_lookup = getBufferLookup()
    if datasetname not in buffer_lookup: return None

    buffer = buffer_lookup[datasetname]
    if '* height-to-tip' in buffer:
        # Ideally we have more complex parser to allow complex evaluations
        # but allow 'BUFFER * height-to-tip' for now
        buffer = buffer.replace('* height-to-tip','')
        buffer = HEIGHT_TO_TIP * float(buffer)
    else:
        buffer = float(buffer)

    return formatValue(buffer)

# ***********************************************************
# ************** Application logic functions ****************
# ***********************************************************

def getckanpackages(ckanurl):
    """
    Downloads CKAN archive
    """

    ua = 'ckanapiexample/1.0 (+https://wewantwind.org)'
    ckan = RemoteCKAN(ckanurl, user_agent=ua)
    groups = ckan.action.group_list(id='data-explorer')
    packages = ckan.action.package_list(id='data-explorer')

    selectedgroups = {}
    for package in packages:
        ckan_package = ckan.action.package_show(id=package)

        gpkgfound = False
        arcgisfound = False
        buffer, automation, layer = None, None, None
        if 'extras' in ckan_package:
            for extra in ckan_package['extras']:
                if extra['key'] == 'buffer': buffer = extra['value']
                if extra['key'] == 'automation': automation = extra['value']
                if extra['key'] == 'layer': layer = extra['value']

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
    for sorted_group in sorted_groups:
        ckan_group = ckan.action.group_show(id=sorted_group)
        color = ''
        if 'extras' in ckan_group:
            for extra in ckan_group['extras']:
                if extra['key'] == 'color': color = extra['value']
        groups[sorted_group] = {'title': ckan_group['title'], 'color': color, 'datasets': []}
        sorted_packages = sorted(selectedgroups[sorted_group].keys())
        for sorted_package in sorted_packages:
            groups[sorted_group]['datasets'].append(selectedgroups[sorted_group][sorted_package])

    return groups

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

def checkGeoJSONFiles(output_folder):
    """
    Checks validity of GeoJSON files within folder
    This is required in case download process is interrupted and files are incompletely downloaded
    """

    LogMessage("Checking validity of downloaded GeoJSON files...")

    files = getFilesInFolder(output_folder)

    for file in files:

        if not file.endswith('.geojson'): continue

        file_path = output_folder + file

        try:
            json_data = json.load(open(file_path))
        except:
            LogError("GeoJSON file is invalid, deleting: " + file)
            os.remove(file_path)
            return False

    LogMessage("All downloaded GeoJSON files valid")

    return True

def downloaddatasets(ckanurl, output_folder):
    """
    Repeats download process until all files are valid
    """

    while True:

        downloaddatasets_singlepass(ckanurl, output_folder)

        if checkGeoJSONFiles(output_folder): break

        LogMessage("One or more downloaded files invalid, rerunning download process")

def downloaddatasets_singlepass(ckanurl, output_folder):
    """
    Downloads a CKAN archive and processes the ArcGIS, WFS, GeoJSON and osm-export-tool YML files within it
    TODO: Add support for non-ArcGIS/GeoJSON/WFS/osm-export-tool-YML
    """

    global REGENERATE_OUTPUT, BUILD_FOLDER, OSM_MAIN_DOWNLOAD, OSM_CONFIG_FOLDER, WORKING_CRS, OSM_EXPORT_DATA
    global POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD

    makeFolder(BUILD_FOLDER)
    makeFolder(OSM_CONFIG_FOLDER)
    makeFolder(output_folder)

    osmDownloadData()

    LogMessage("Downloading data catalogue from CKAN " + ckanurl)

    ckanpackages = getckanpackages(ckanurl)

    generateStructureLookups(ckanpackages)
    generateBufferLookup(ckanpackages)

    # Batch create all OSM layers first
    # Saves time to run osm-export-tool on single file with all datasets

    yaml_all_filename = 'all.yml'
    osm_layers, yaml_all_content, yaml_all_path = [], {}, OSM_CONFIG_FOLDER + yaml_all_filename
    for ckanpackage in ckanpackages.keys():
        for dataset in ckanpackages[ckanpackage]['datasets']:
            if dataset['type'] != 'osm-export-tool YML': continue

            dataset_title = reformatDatasetName(dataset['title'])
            feature_name = dataset['title']
            feature_layer_url = dataset['url']
            url_basename = basename(dataset['url'])
            downloaded_yml = dataset_title + ".yml"
            downloaded_yml_fullpath = OSM_CONFIG_FOLDER + downloaded_yml

            LogMessage("Downloading osm-export-tool YML: " + url_basename + " -> " + downloaded_yml)

            opener = urllib.request.build_opener()
            opener.addheaders = [('User-agent', 'Mozilla/5.0')]
            urllib.request.install_opener(opener)
            attemptDownloadUntilSuccess(dataset['url'], downloaded_yml_fullpath)

            yaml_content = None
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
    existing_yaml_content = None
    rerun_osm_export_tool = False
    if isfile(yaml_all_path):
        with open(yaml_all_path, "r") as yaml_file: existing_yaml_content = yaml_file.read()

    latest_yaml_content = yaml.dump(yaml_all_content)
    if latest_yaml_content != existing_yaml_content:
        rerun_osm_export_tool = True
        with open(yaml_all_path, "w") as yaml_file: yaml_file.write(latest_yaml_content)

    osm_export_file = BUILD_FOLDER + OSM_EXPORT_DATA + '.gpkg'
    if not isfile(osm_export_file): rerun_osm_export_tool = True

    if rerun_osm_export_tool:
        # Export OSM to GPKG using osm-export-tool
        LogMessage("Running osm-export-tool with aggregated YML: " + yaml_all_filename)
        runSubprocess(["osm-export-tool", BUILD_FOLDER + basename(OSM_MAIN_DOWNLOAD), BUILD_FOLDER + OSM_EXPORT_DATA, "-m", yaml_all_path])

    osm_layers.sort()
    generateOSMLookup(osm_layers)

    # Remove any temp files that may have been left if previous run interrupted
    if isfile('temp.geojson'): os.remove('temp.geojson')
    if isfile('temp.gml'): os.remove('temp.gml')
    if isfile('temp.gpkg'): os.remove('temp.gpkg')

    for ckanpackage in ckanpackages.keys():
        for dataset in ckanpackages[ckanpackage]['datasets']:
            dataset_title = reformatDatasetName(dataset['title'])
            feature_name = dataset['title']
            feature_layer_url = dataset['url']
            temp_output_file = 'temp.geojson'
            output_file = join(output_folder, f'{dataset_title}.geojson')
            output_gpkg_file = join(output_folder, f'{dataset_title}.gpkg')

            # If export file(s) already exists, then skip to next record
            if isfile(output_file) or isfile(output_gpkg_file): continue

            if dataset['type'] == 'KML':

                LogMessage("Downloading KML:     " + feature_name)

                url_basename = basename(dataset['url'])
                kml_file = output_folder + dataset_title + '.kml'
                kmz_file = output_folder + dataset_title + '.kmz'
                zip_folder = output_folder + dataset_title + '/'

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

            elif dataset['type'] == 'WFS':

                temp_output_file = 'temp.gpkg'
                getfeature_url = dataset['url']

                # Attempt to connect to WFS using highest version

                wfs_version = '2.0.0'                
                try:
                    wfs = WebFeatureService(url=dataset['url'], version='2.0.0')
                except:
                    wfs = WebFeatureService(url=dataset['url'])
                    wfs_version = wfs.version

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
                response = requests.get(url)
                result = xmltodict.parse(response.text)

                # For some reason WFS @numberMatched is always 1 bigger than actual number

                totalrecords = int(result['wfs:FeatureCollection']['@numberMatched']) - 1
                batchsize = int(result['wfs:FeatureCollection']['@numberReturned'])

                # If batchsize is 0, suggests that there is no limit so attempt to load all records

                if batchsize == 0: batchsize = totalrecords

                # Download data page by page

                LogMessage("Downloading WFS:     " + feature_name+ " [records: " + str(totalrecords) + "]")

                dataframe, startIndex, recordsdownloaded = None, 0, 0

                while True:

                    recordstodownload = totalrecords - recordsdownloaded
                    if recordstodownload > batchsize: recordstodownload = batchsize

                    wfs_request_url = Request('GET', getfeature_url, params={
                        'service': 'WFS',
                        'version': wfs_version,
                        'request': 'GetFeature',
                        'typename': layer,
                        'count': recordstodownload,
                        'startIndex': startIndex,
                    }).prepare().url

                    LogMessage("--> Downloading: " + str(startIndex + 1) + " to " + str(startIndex + recordstodownload))
                    
                    dataframe_new = gpd.read_file(wfs_request_url).set_crs(crs)

                    if dataframe is None: dataframe = dataframe_new
                    else: dataframe = pd.concat([dataframe, dataframe_new])

                    recordsdownloaded += recordstodownload
                    startIndex += recordstodownload

                    if recordsdownloaded >= totalrecords: break

                dataframe.to_file(temp_output_file)

            elif dataset['type'] == 'GPKG':

                LogMessage("Downloading GPKG:    " + feature_name)
                temp_output_file = 'temp.gpkg'
                attemptDownloadUntilSuccess(dataset['url'], temp_output_file)

            elif dataset['type'] == 'GeoJSON':

                LogMessage("Downloading GeoJSON: " + feature_name)
                attemptDownloadUntilSuccess(dataset['url'], temp_output_file)

            elif dataset['type'] == "ArcGIS GeoServices REST API":

                query_url = f'{feature_layer_url}/query'
                params = {"f": 'json'}
                response = attemptPOSTUntilSuccess(feature_layer_url, params)
                result = json.loads(response.text)
                object_id_field = result['objectIdField']

                params = {
                    "f": 'json',
                    "returnCountOnly": 'true',
                    "where": '1=1'
                }

                response = attemptPOSTUntilSuccess(query_url, params)
                result = json.loads(response.text)
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
                            LogError("Problem with url, retrying after delay...")
                            time.sleep(5)
                            continue

                        if(len(result['features'])):
                            geojson['features'] += result['features']
                            records_downloaded += len(result['features'])
                            object_id = result['features'][len(result['features'])-1]['properties'][object_id_field]
                        else:
                            LogError("Problem with url, retrying after delay...")
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

def purgeall():
    """
    Deletes all database tables and build folder
    """

    global BUILD_FOLDER, TILESERVER_FOLDER, OSM_MAIN_DOWNLOAD, OSM_EXPORT_DATA, OSM_CONFIG_FOLDER, DATASETS_DOWNLOADS_FOLDER, DATASETS_MANUAL_FOLDER

    postgisDropAllTables()

    tileserver_folder_name = basename(TILESERVER_FOLDER[:-1])
    build_files = getFilesInFolder(BUILD_FOLDER)
    for build_file in build_files: os.remove(BUILD_FOLDER + build_file)
    tileserver_files = getFilesInFolder(TILESERVER_FOLDER)
    for tileserver_file in tileserver_files: os.remove(TILESERVER_FOLDER + tileserver_file)

    pwd = os.path.dirname(os.path.realpath(__file__))

    # Delete items in BUILD_FOLDER

    subfolders = [ f.path for f in os.scandir(BUILD_FOLDER) if f.is_dir() ]

    for subfolder in subfolders:

        # Don't delete postgres folder as managed by separate docker instance
        # Also don't delete tileserver folder yet as some elements are managed separately 
        if basename(subfolder) in ['postgres', tileserver_folder_name]: continue

        subfolder_absolute = os.path.abspath(subfolder)

        if len(subfolder_absolute) < len(pwd) or not subfolder_absolute.startswith(pwd):
            LogError("Attempting to delete folder outside current directory, aborting")
            exit()

        shutil.rmtree(subfolder_absolute)

    # Delete selected items in TILESERVER_FOLDER

    subfolders = [ f.path for f in os.scandir(TILESERVER_FOLDER) if f.is_dir() ]

    for subfolder in subfolders:

        # Don't delete 'fonts' or 'sprites' as won't change once installed
        if basename(subfolder) in ['fonts', 'sprites']: continue

        subfolder_absolute = os.path.abspath(subfolder)

        if len(subfolder_absolute) < len(pwd) or not subfolder_absolute.startswith(pwd):
            LogError("Attempting to delete folder outside current directory, aborting")
            exit()

        shutil.rmtree(subfolder_absolute)

def createGridClippedFile(table_name, dataset_name, file_path):
    """
    Create grid clipped version of file to improve rendering and performance when used as mbtiles
    """

    global OUTPUT_GRID_TABLE

    scratch_table_1 = '_scratch_table_1'

    if postgisCheckTableExists(scratch_table_1): postgisDropTable(scratch_table_1)

    postgisExec("CREATE TABLE %s AS SELECT (ST_Dump(ST_Intersection(layer.geom, grid.geom))).geom geom FROM %s layer, %s grid;", \
                (AsIs(scratch_table_1), AsIs(table_name), AsIs(OUTPUT_GRID_TABLE), ))

    inputs = runSubprocess(["ogr2ogr", \
                    file_path, \
                    'PG:host=' + POSTGRES_HOST + ' user=' + POSTGRES_USER + ' password=' + POSTGRES_PASSWORD + ' dbname=' + POSTGRES_DB, \
                    "-overwrite", \
                    "-nln", dataset_name, \
                    scratch_table_1, \
                    "-s_srs", WORKING_CRS, \
                    "-t_srs", 'EPSG:4326'])

    if postgisCheckTableExists(scratch_table_1): postgisDropTable(scratch_table_1)

def processdownloads(output_folder):
    """
    Processes folder of GeoJSON files
    - Adds buffers where appropriate
    - Joins and dissolves child datasets into single parent dataset
    - Joins and dissolves datasets into CKAN groups, one for each group
    - Create single final joined-and-dissolved dataset for entire CKAN database of datasets
    - Converts final files to GeoJSON (EPSG:4326)
    """

    global DEBUG_RUN, HEIGHT_TO_TIP, WORKING_CRS, BUILD_FOLDER, OSM_MAIN_DOWNLOAD, OSM_EXPORT_DATA
    global FINALLAYERS_OUTPUT_FOLDER, FINALLAYERS_CONSOLIDATED, OVERALL_CLIPPING_FILE, REGENERATE_INPUT, REGENERATE_OUTPUT
    global POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
    global OUTPUT_GRID_SPACING, OUTPUT_GRID_TABLE
    global QGIS_OUTPUT_FILE

    if REGENERATE_INPUT: REGENERATE_OUTPUT = True

    scratch_table_1 = '_scratch_table_1'
    scratch_table_2 = '_scratch_table_2'

    # Ensure all necessary folders exists

    makeFolder(BUILD_FOLDER)
    makeFolder(output_folder)
    makeFolder(FINALLAYERS_OUTPUT_FOLDER)

    # Import UK clipping into PostGIS

    clipping_table = reformatTableName(OVERALL_CLIPPING_FILE)

    if not postgisCheckTableExists(clipping_table):

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
                        "-t_srs", WORKING_CRS]) 

    clipping_union_table = buildUnionTableName(clipping_table)

    if not postgisCheckTableExists(clipping_union_table):

        LogMessage("Running ST_Union within PostGIS: " + clipping_table + " -> " + clipping_union_table)

        postgisExec("CREATE TABLE %s AS SELECT ST_Union(geom) geom FROM %s", \
                    (AsIs(clipping_union_table), AsIs(clipping_table), ))
        postgisExec("CREATE INDEX %s ON %s USING GIST (geom);", (AsIs(clipping_union_table + "_idx"), AsIs(clipping_union_table), ))

    # Create output grid

    if not postgisCheckTableExists(OUTPUT_GRID_TABLE):

        LogMessage("Creating output grid overlay to improve performance and rendering quality")

        postgisExec("CREATE TABLE %s AS SELECT ST_Transform((ST_SquareGrid(%s, ST_Transform(geom, 3857))).geom, 4326) geom FROM %s;", 
                    (AsIs(OUTPUT_GRID_TABLE), AsIs(OUTPUT_GRID_SPACING), AsIs(clipping_union_table), ))

    # Import OSM-specific data files

    LogMessage("Processing all OSM-specific data layers...")

    osm_layers = getOSMLookup()
    osm_export_file = BUILD_FOLDER + OSM_EXPORT_DATA + '.gpkg'
    osm_export_projection = getGPKGProjection(osm_export_file)
    for osm_layer in osm_layers:
        table_name = reformatTableName(osm_layer)
        table_exists = postgisCheckTableExists(table_name)
        if (not REGENERATE_INPUT) and table_exists: continue
        LogMessage("Importing " + OSM_EXPORT_DATA + ".gpkg OSM layer into PostGIS: " + osm_layer)
        # Assume 'osm-export-tool' outputs in EPSG:4326 projection
        osm_layer_table = osm_layer
        if DEBUG_RUN: osm_layer_table = 'danger-areas--uk'
        inputs = runSubprocess(["ogr2ogr", \
                                "-f", "PostgreSQL", \
                                'PG:host=' + POSTGRES_HOST + ' user=' + POSTGRES_USER + ' password=' + POSTGRES_PASSWORD + ' dbname=' + POSTGRES_DB, \
                                osm_export_file, \
                                "-overwrite", \
                                "-nln", osm_layer, \
                                "-lco", "GEOMETRY_NAME=geom", \
                                "-lco", "OVERWRITE=YES", \
                                "-dialect", "sqlite", \
                                "-sql", \
                                "SELECT * FROM '" + osm_layer_table + "'", \
                                "-s_srs", osm_export_projection, \
                                "-t_srs", WORKING_CRS])
        # postgisExec("CREATE INDEX %s ON %s USING GIST (geom);", (AsIs(table_name + "_idx"), AsIs(table_name), ))

    LogMessage("Finished processing all OSM-specific data layers")

    # Import all GeoJSON into PostGIS

    LogMessage("Importing downloaded files into PostGIS...")

    downloaded_files = getFilesInFolder(output_folder)
    for downloaded_file in downloaded_files:
        core_dataset_name = getCoreDatasetName(downloaded_file)
        tableexists = postgisCheckTableExists(core_dataset_name)
        if (not REGENERATE_INPUT) and tableexists: continue

        if downloaded_file == 'test.geojson': continue

        LogMessage("Importing into PostGIS: " + downloaded_file)

        if DEBUG_RUN: downloaded_file = 'test.geojson'
        downloaded_file_fullpath = output_folder + downloaded_file

        sql_where_clause = None
        orig_srs = 'EPSG:4326'

        if '.geojson' in downloaded_file:

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
            if not DEBUG_RUN:
                if downloaded_file == 'conservation-areas--england.geojson': sql_where_clause = "Name NOT LIKE 'No data%'"

        # We set CRS=WORKING_CRS during download phase
        if '.gpkg' in downloaded_file: orig_srs = WORKING_CRS

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
                            "-nln", core_dataset_name, \
                            "-s_srs", orig_srs, \
                            "-t_srs", WORKING_CRS]

        if sql_where_clause is not None:
            for extraitem in ["-dialect", "sqlite", "-sql", "SELECT * FROM '" + core_dataset_name + "' WHERE " + sql_where_clause]:
                subprocess_list.append(extraitem)

        inputs = runSubprocess(subprocess_list)
        # postgisExec("CREATE INDEX %s ON %s USING GIST (geom);", (AsIs(core_dataset_name + "_idx"), AsIs(core_dataset_name), ))

    LogMessage("All downloaded files imported into PostGIS")

    # Add buffers where appropriate to GPKG

    LogMessage("Adding buffers to PostGIS and clipping all tables...")

    structure_lookup = getStructureLookup()
    groups = structure_lookup.keys()
    parents_lookup = {}

    for group in groups:
        for parent in structure_lookup[group].keys():
            for dataset_name in structure_lookup[group][parent]:
                buffer = getDatasetBuffer(dataset_name)
                source_table = reformatTableName(dataset_name)
                processed_table = buildProcessedTableName(source_table)
                if buffer is not None:
                    buffered_table = buildBufferTableName(dataset_name, buffer)
                    processed_table = buildProcessedTableName(buffered_table)
                    table_exists = postgisCheckTableExists(buffered_table)
                    if REGENERATE_OUTPUT or (not table_exists):
                        LogMessage("Adding " + buffer + "m buffer: " + source_table + " -> " + buffered_table)
                        if table_exists: postgisDropTable(buffered_table)
                        postgisExec("CREATE TABLE %s AS SELECT ST_Buffer(geom::geography, %s)::geometry geom FROM %s;", \
                                    (AsIs(buffered_table), float(buffer), AsIs(source_table), ))
                        postgisExec("CREATE INDEX %s ON %s USING GIST (geom);", (AsIs(buffered_table + "_idx"), AsIs(buffered_table), ))
                    source_table = buffered_table

                # Dump original or buffered layer and run processing on it

                processed_table_exists = postgisCheckTableExists(processed_table)
                if REGENERATE_OUTPUT or (not processed_table_exists):
                    LogMessage("Processing table: " + source_table)
                    if processed_table_exists: postgisDropTable(processed_table)

                    # Explode geometries with ST_Dump to remove MultiPolygon,
                    # MultiSurface, etc and homogenize processing
                    # Ideally all dumped tables should contain polygons only (either source or buffered source is (Multi)Polygon)
                    # so filter on ST_Polygon

                    if postgisCheckTableExists(scratch_table_1): postgisDropTable(scratch_table_1)
                    if postgisCheckTableExists(scratch_table_2): postgisDropTable(scratch_table_2)

                    LogMessage(" --> Step 1: Select only polygons, dump and make valid")

                    postgisExec("CREATE TABLE %s AS SELECT ST_MakeValid(dumped.geom) geom FROM (SELECT (ST_Dump(geom)).geom geom FROM %s) dumped WHERE ST_geometrytype(dumped.geom) = 'ST_Polygon';", \
                                (AsIs(scratch_table_1), AsIs(source_table), ))
                    
                    postgisExec("CREATE INDEX %s ON %s USING GIST (geom);", (AsIs(scratch_table_1 + "_idx"), AsIs(scratch_table_1), ))

                    LogMessage(" --> Step 2: Clipping partially overlapping polygons")

                    postgisExec("""
                    CREATE TABLE %s AS 
                        SELECT ST_Intersection(clipping.geom, data.geom) geom
                        FROM %s data, %s clipping 
                        WHERE 
                            (NOT ST_Contains(clipping.geom, data.geom) AND 
                            ST_Intersects(clipping.geom, data.geom));""", \
                        (AsIs(scratch_table_2), AsIs(scratch_table_1), AsIs(clipping_union_table), ))

                    LogMessage(" --> Step 3: Adding fully enclosed polygons")

                    postgisExec("""
                    INSERT INTO %s  
                        SELECT data.geom  
                        FROM %s data, %s clipping 
                        WHERE 
                            ST_Contains(clipping.geom, data.geom);""", \
                        (AsIs(scratch_table_2), AsIs(scratch_table_1), AsIs(clipping_union_table), ))

                    LogMessage(" --> Step 4: Dumping and removing non-polygons")

                    postgisExec("CREATE TABLE %s AS SELECT dumped.geom FROM (SELECT (ST_Dump(ST_Union(geom))).geom geom FROM %s) AS dumped WHERE ST_geometrytype(dumped.geom) = 'ST_Polygon';", (AsIs(processed_table), AsIs(scratch_table_2), ))
                    postgisExec("CREATE INDEX %s ON %s USING GIST (geom);", (AsIs(processed_table + "_idx"), AsIs(processed_table), ))

                    if postgisCheckTableExists(scratch_table_1): postgisDropTable(scratch_table_1)
                    if postgisCheckTableExists(scratch_table_2): postgisDropTable(scratch_table_2)

                    LogMessage(" --> COMPLETED: Processed table: " + processed_table)

                parent = getTableParent(source_table)
                if parent not in parents_lookup: parents_lookup[parent] = []
                parents_lookup[parent].append(processed_table)

    LogMessage("All buffers added to PostGIS and all tables clipped")

    # Amalgamating layers with common 'parents'

    LogMessage("Amalgamating and dissolving layers with common parents...")

    finallayers = []
    parents = parents_lookup.keys()
    for parent in parents:
        parent_table = buildFinalLayerTableName(parent)
        finallayers.append(reformatDatasetName(parent_table))
        parent_table_exists = postgisCheckTableExists(parent_table)
        if REGENERATE_OUTPUT or (not parent_table_exists):
            LogMessage("Amalgamating and dissolving children of parent: " + parent)
            if parent_table_exists: postgisDropTable(parent_table)
            postgisAmalgamateAndDissolve(parent_table, parents_lookup[parent])

    LogMessage("All common parent layers amalgamated and dissolved")

    # Amalgamating datasets by group

    LogMessage("Amalgamating and dissolving layers by group...")

    for group in groups:
        group_items = list((structure_lookup[group]).keys())
        if group_items is None: continue
        group_table = buildFinalLayerTableName(group)
        finallayers.append(reformatDatasetName(group_table))
        group_table_exists = postgisCheckTableExists(group_table)
        group_items.sort()
        if REGENERATE_OUTPUT or (not group_table_exists):
            LogMessage("Amalgamating and dissolving datasets of group: " + group)
            # Don't do anything if there is only one element with same name as group
            if (len(group_items) == 1) and (group == group_items[0]): continue
            if group_table_exists: postgisDropTable(group_table)
            children = [buildFinalLayerTableName(table_name) for table_name in group_items]
            postgisAmalgamateAndDissolve(group_table, children)

    LogMessage("All group layers amalgamated and dissolved")

    # Amalgamating all groups as single layer

    LogMessage("Amalgamating and dissolving all groups as single overall layer...")

    alllayers_table = buildFinalLayerTableName(FINALLAYERS_CONSOLIDATED)
    final_file_geojson = FINALLAYERS_OUTPUT_FOLDER + reformatDatasetName(alllayers_table) + '.geojson'
    final_file_gpkg = FINALLAYERS_OUTPUT_FOLDER + reformatDatasetName(alllayers_table) + '.gpkg'
    finallayers.append(reformatDatasetName(alllayers_table))
    alllayers_table_exists = postgisCheckTableExists(alllayers_table)
    if REGENERATE_OUTPUT or (not alllayers_table_exists):
        LogMessage("Amalgamating and dissolving single overall layer: " + FINALLAYERS_CONSOLIDATED)
        if alllayers_table_exists: postgisDropTable(alllayers_table)
        children = [buildFinalLayerTableName(table_name) for table_name in groups]
        postgisAmalgamateAndDissolve(alllayers_table, children)

    LogMessage("All groups amalgamated and dissolved as single layer")

    # Exporting final layers to GeoJSON and GPKG

    LogMessage("Converting final layers to GPKG and GeoJSON...")

    shp_extensions = ['shp', 'dbf', 'shx', 'prj']
    for finallayer in finallayers:
        finallayer_table = reformatTableName(finallayer)
        core_dataset_name = getFinalLayerCoreDatasetName(finallayer_table)
        latest_name = getFinalLayerLatestName(finallayer_table)
        finallayer_file_gpkg = FINALLAYERS_OUTPUT_FOLDER + finallayer + '.gpkg' 
        finallayer_file_shp = FINALLAYERS_OUTPUT_FOLDER + finallayer + '.shp' 
        finallayer_file_geojson = FINALLAYERS_OUTPUT_FOLDER + finallayer + '.geojson' 
        finallayer_latest_file_gpkg = FINALLAYERS_OUTPUT_FOLDER + latest_name + '.gpkg' 
        finallayer_latest_file_shp = FINALLAYERS_OUTPUT_FOLDER + latest_name + '.shp' 
        finallayer_latest_file_geojson = FINALLAYERS_OUTPUT_FOLDER + latest_name + '.geojson' 

        if REGENERATE_OUTPUT or (not isfile(finallayer_file_gpkg)):
            LogMessage("Exporting final layer to: " + finallayer_file_gpkg)
            if isfile(finallayer_file_gpkg): os.remove(finallayer_file_gpkg)
            inputs = runSubprocess(["ogr2ogr", \
                            finallayer_file_gpkg, \
                            'PG:host=' + POSTGRES_HOST + ' user=' + POSTGRES_USER + ' password=' + POSTGRES_PASSWORD + ' dbname=' + POSTGRES_DB, \
                            "-overwrite", \
                            "-nln", core_dataset_name, \
                            "-nlt", 'POLYGON', \
                            finallayer_table, \
                            "-dialect", "sqlite", \
                            "-sql", \
                            "SELECT geom geometry FROM '" + finallayer_table + "'", \
                            "-s_srs", WORKING_CRS, \
                            "-t_srs", 'EPSG:4326'])
            checkGPKGIsValid(finallayer_file_gpkg, core_dataset_name, inputs)
        # Always copy to latest
        if not isfile(finallayer_latest_file_gpkg): 
            shutil.copy(finallayer_file_gpkg, finallayer_latest_file_gpkg)

        if REGENERATE_OUTPUT or (not isfile(finallayer_file_shp)):
            LogMessage("Exporting final layer to: " + finallayer_file_shp)
            for shp_extension in shp_extensions:
                if isfile(finallayer_file_shp.replace('shp', shp_extension)): os.remove(finallayer_file_shp.replace('shp', shp_extension))
                if isfile(finallayer_latest_file_shp.replace('shp', shp_extension)): os.remove(finallayer_latest_file_shp.replace('shp', shp_extension))
            inputs = runSubprocess(["ogr2ogr", \
                            finallayer_file_shp, \
                            'PG:host=' + POSTGRES_HOST + ' user=' + POSTGRES_USER + ' password=' + POSTGRES_PASSWORD + ' dbname=' + POSTGRES_DB, \
                            "-overwrite", \
                            "-nln", core_dataset_name, \
                            "-nlt", 'POLYGON', \
                            finallayer_table, \
                            "-s_srs", WORKING_CRS, \
                            "-t_srs", 'EPSG:4326'])
            # As we've reexported this particular layer, copy to latest
            for shp_extension in shp_extensions:
                shutil.copy(finallayer_file_shp.replace('shp', shp_extension), finallayer_latest_file_shp.replace('shp', shp_extension))

        if REGENERATE_OUTPUT or (not isfile(finallayer_file_geojson)):
            LogMessage("Exporting final layer to: " + finallayer_file_geojson)
            if isfile(finallayer_file_geojson): os.remove(finallayer_file_geojson)
            inputs = runSubprocess(["ogr2ogr", \
                            finallayer_file_geojson, \
                            'PG:host=' + POSTGRES_HOST + ' user=' + POSTGRES_USER + ' password=' + POSTGRES_PASSWORD + ' dbname=' + POSTGRES_DB, \
                            "-overwrite", \
                            "-nln", core_dataset_name, \
                            finallayer_table, \
                            "-s_srs", WORKING_CRS, \
                            "-t_srs", 'EPSG:4326'])
            # As we're outputting new geojson, delete corresponding mbtiles file if exists 
            finallayer_latest_mbtiles = TILESERVER_DATA_FOLDER + basename(finallayer_latest_file_geojson).replace('.geojson', '.mbtiles')
            if isfile(finallayer_latest_mbtiles): os.remove(finallayer_latest_mbtiles)
        # Always copy to latest
        if not isfile(finallayer_latest_file_geojson): 
            shutil.copy(finallayer_file_geojson, finallayer_latest_file_geojson)

    LogMessage("All final layers converted to GPKG and GeoJSON")

    # Build tile server files

    buildTileserverFiles()

    # Build QGIS file

    buildQGISFile()

    # Run layers through tippecanoe
    LogMessage("**** Completed processing ****")

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
******************* OPEN WIND BUILD PROCESS COMPLETE ******************
***********************************************************************\033[0m

Final composite layers for turbine height to tip """ + formatValue(HEIGHT_TO_TIP) + """m created at:

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

    LogMessage("Installing tileserver fonts")

    tileserver_font_folder = TILESERVER_FOLDER + 'fonts/'

    if BUILD_FOLDER == 'build-docker/':

        # On docker openwind-fonts container copies fonts to 'fonts/' folder
        # So need to wait for it to finish this

        while True:
            if isdir(tileserver_font_folder): break
            time.sleep(5)

    else:

        # Download tileserver fonts

        if not isdir(tileserver_font_folder):

            if not isdir(basename(TILESERVER_FONTS_GITHUB)):

                LogMessage("Downloading tileserver fonts")

                inputs = runSubprocess(["git", "clone", TILESERVER_FONTS_GITHUB])

            working_dir = os.getcwd()
            os.chdir(basename(TILESERVER_FONTS_GITHUB))

            LogMessage("Generating PBF fonts")

            inputs = runSubprocess(["npm", "install"])
            inputs = runSubprocess(["node", "./generate.js"])

            os.chdir(working_dir)

            LogMessage("Copying PBF fonts to tileserver folder")

            tileserver_font_folder_src = basename(TILESERVER_FONTS_GITHUB) + '/_output'

            shutil.copytree(tileserver_font_folder_src, tileserver_font_folder)

def buildTileserverFiles():
    """
    Builds files required for tileserver-gl
    """

    global  OVERALL_CLIPPING_FILE, TILESERVER_URL, TILESERVER_FONTS_GITHUB, TILESERVER_SRC_FOLDER, TILESERVER_FOLDER, TILESERVER_DATA_FOLDER, TILESERVER_STYLES_FOLDER, \
            OSM_MAIN_DOWNLOAD, BUILD_FOLDER, FINALLAYERS_OUTPUT_FOLDER, FINALLAYERS_CONSOLIDATED, MAPAPP_FOLDER
    global  TILEMAKER_COASTLINE_CONFIG, TILEMAKER_COASTLINE_PROCESS, TILEMAKER_OMT_CONFIG, TILEMAKER_OMT_PROCESS, SKIP_FONTS_INSTALLATION, OPENMAPTILES_HOSTED_FONTS

    # Run tileserver build process

    LogMessage("Creating tileserver files")

    makeFolder(TILESERVER_FOLDER)
    makeFolder(TILESERVER_DATA_FOLDER)
    makeFolder(TILESERVER_STYLES_FOLDER)

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

    if SKIP_FONTS_INSTALLATION: 
        fonts_url = OPENMAPTILES_HOSTED_FONTS
    else: 
        installTileserverFonts()
        fonts_url = TILESERVER_URL + '/fonts/{fontstack}/{range}.pbf'

    openmaptiles_style_json['glyphs'] = fonts_url

    with open(openmaptiles_style_file_dst, "w") as json_file: json.dump(openmaptiles_style_json, json_file, indent=4)

    attribution = "Source data copyright of multiple organisations. For all data sources, see <a href=\"" + CKAN_URL + "\" target=\"_blank\">" + CKAN_URL.replace('https://', '') + "</a>"
    openwind_style_file = TILESERVER_STYLES_FOLDER + 'openwind.json'
    openwind_style_json = openmaptiles_style_json
    openwind_style_json['name'] = 'Open Wind'
    openwind_style_json['id'] = 'openwind'
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
                                "--input", BUILD_FOLDER + basename(OSM_MAIN_DOWNLOAD), \
                                "--output", basemap_mbtiles, \
                                "--bbox", bbox_unitedkingdom_padded, \
                                "--process", TILEMAKER_COASTLINE_PROCESS, \
                                "--config", TILEMAKER_COASTLINE_CONFIG ])

        LogMessage("Merging " + basename(OSM_MAIN_DOWNLOAD) + " into global coastline mbtiles...")

        inputs = runSubprocess(["tilemaker", \
                                "--input", BUILD_FOLDER + basename(OSM_MAIN_DOWNLOAD), \
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
    styles["openwind"] = {
      "style": "openwind.json",
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

    # Insert overall constraints as first item in list so it appears as first item in tileserver-gl
    overallconstraints = 'latest--' + FINALLAYERS_CONSOLIDATED + '.geojson'
    if overallconstraints in output_files: output_files.remove(overallconstraints)
    if not isfile(FINALLAYERS_OUTPUT_FOLDER + overallconstraints):
        LogError("Final overall constraints layer is missing")
        exit()
    output_files.insert(0, overallconstraints)

    for output_file in output_files:
        if (not output_file.startswith('latest--')) or (not output_file.endswith('.geojson')): continue

        tippecanoe_output = TILESERVER_DATA_FOLDER + output_file.replace('.geojson', '.mbtiles')
        dataset_name = reformatDatasetName(output_file)
        core_dataset_name = getCoreDatasetName(dataset_name)
        table_name = reformatTableName(dataset_name)
        original_table_name = getOriginalTable(table_name)

        if dataset_name not in dataset_style_lookup: continue

        style_id = dataset_name
        style_name = dataset_style_lookup[dataset_name]['title']

        # If tippecanoe failed previously for any reason, delete the output and intermediary file

        tippecanoe_interrupted_file = tippecanoe_output + '-journal'
        if isfile(tippecanoe_interrupted_file):
            os.remove(tippecanoe_interrupted_file)
            if isfile(tippecanoe_output): os.remove(tippecanoe_output)

        # Create grid-clipped version of GeoJSON to input into tippecanoe to improve mbtiles rendering and performance

        if not isfile(tippecanoe_output):
    
            LogMessage("Creating mbtiles for: " + output_file)

            tippecanoe_grid_clipped_file = 'tippecanoe--grid-clipped--temp.geojson'

            if isfile(tippecanoe_grid_clipped_file): os.remove(tippecanoe_grid_clipped_file)

            createGridClippedFile(original_table_name, core_dataset_name, tippecanoe_grid_clipped_file)

            inputs = runSubprocess(["tippecanoe", \
                                    "-Z4", "-z15", \
                                    "-X", \
                                    "--generate-ids", \
                                    "--force", \
                                    "-n", style_name, \
                                    "-l", dataset_name, \
                                    tippecanoe_grid_clipped_file, \
                                    "-o", tippecanoe_output ])

            # if isfile(tippecanoe_grid_clipped_file): os.remove(tippecanoe_grid_clipped_file)

        if not isfile(tippecanoe_output):
            LogError("Failed to create mbtiles: " + basename(tippecanoe_output))
            LogError("*** Aborting process *** ")
            exit()

        LogMessage("Created tileserver-gl style file for: " + output_file)

        style_color = dataset_style_lookup[dataset_name]['color']
        style_level = dataset_style_lookup[dataset_name]['level']
        style_defaultactive = dataset_style_lookup[dataset_name]['defaultactive']
        style_opacity = 0.8 if style_level == 1 else 0.5
        style_file = TILESERVER_STYLES_FOLDER + style_id + '.json'
        style_json = {
            "version": 8,
            "id": style_id,
            "name": style_name,
            "sources": {
              	dataset_name: {
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

        openwind_style_json['sources'][style_id] = style_json['sources'][dataset_name]
        with open(style_file, "w") as json_file: json.dump(style_json, json_file, indent=4)

        openwind_layer = style_json['layers'][0]
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

    with open(openwind_style_file, "w") as json_file: json.dump(openwind_style_json, json_file, indent=4)

    # Creating final tileserver-gl config file

    config_file = TILESERVER_FOLDER + 'config.json'
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
 
    with open(config_file, "w") as json_file: json.dump(config_json, json_file, indent=4)

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

LogMessage("Starting openwind data pipeline...")

postgisWaitRunning()

if len(sys.argv) > 1:
    arg_index = 0
    for arg in sys.argv:
        arg = arg.strip()
        if isfloat(arg):
            HEIGHT_TO_TIP = float(arg)
            LogMessage("************ Using HEIGHT_TO_TIP: " + formatValue(HEIGHT_TO_TIP) + ' metres ************')

        if arg == '--purgeall':
            LogMessage("--purgeall argument passed: Clearing database and all build files")
            REGENERATE_INPUT = True
            REGENERATE_OUTPUT = True
            purgeall()

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
                LogMessage("-regenerate argument passed: Redownloading and rebuilding all tables related to " + regeneratedataset)
                deleteDataset(regeneratedataset)

        if arg == '--help':
            print("""
Command syntax:
                  
python3 openwind.py [HEIGHT TO TIP]
                  
Where 'HEIGHT TO TIP' is height to tip in metres of target wind turbine.
                  
Possible additional arguments:

--purgeall             Clear all downloads and database tables as if starting fresh
--purgedb              Clear all PostGIS tables and reexport final layer files
--purgederived         Clear all derived (ie. non-core data) PostGIS tables and reexport final layer files
--purgeamalgamated     Clear all amalgamated PostGIS tables and reexport final layer files
--skipdownload         Skip download stage and just do PostGIS processing
--skipfonts            Skip font installation stage and use hosted version of openmaptiles fonts
--regenerate dataset   Regenerate specific dataset by redownloading and recreating all tables relating to dataset
--buildtileserver      Rebuild files for tileserver

""")
            exit()

        arg_index += 1

if PERFORM_DOWNLOAD:
    downloaddatasets(CKAN_URL, DATASETS_DOWNLOADS_FOLDER)

processdownloads(DATASETS_DOWNLOADS_FOLDER)