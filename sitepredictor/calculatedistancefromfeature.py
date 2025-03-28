# ***********************************************************
# ******************** SITE PREDICTOR ***********************
# ***********************************************************
# ***** Script to estimate probability of site success ******
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
import geojson
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
import pprint as pp
import shapely
import shapely.geometry
from psycopg2 import sql
from psycopg2.extensions import AsIs
from zipfile import ZipFile
from os import listdir, makedirs
from os.path import isfile, isdir, basename, join, exists
from turfpy.measurement import nearest_point, distance, length, along, destination, bbox, bbox_polygon
from turfpy.measurement import points_within_polygon
from geojson import Point, Feature, FeatureCollection, Polygon
from dotenv import load_dotenv

load_dotenv('../.env')

POSTGRES_HOST                       = os.environ.get("POSTGRES_HOST")
POSTGRES_DB                         = os.environ.get("POSTGRES_DB")
POSTGRES_USER                       = os.environ.get("POSTGRES_USER")
POSTGRES_PASSWORD                   = os.environ.get("POSTGRES_PASSWORD")




logging.basicConfig(
    format='%(asctime)s [%(levelname)-2s] %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S')

# ***********************************************************
# ***************** General helper functions ****************
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

def getDatasetParent(file_path):
    """
    Gets dataset parent name from file path
    Parent = 'description', eg 'national-parks'
    """

    file_basename = basename(file_path).split(".")[0]
    return "--".join(file_basename.split("--")[0:1])


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

    global  BUILD_FOLDER, OSM_MAIN_DOWNLOAD, TILEMAKER_DOWNLOAD_SCRIPT, TILEMAKER_COASTLINE, TILEMAKER_LANDCOVER, TILEMAKER_CONFIG

    makeFolder(BUILD_FOLDER)

    if not isfile(BUILD_FOLDER + basename(OSM_MAIN_DOWNLOAD)):
        LogMessage("Downloading latest OSM data for britain and ireland")
        runSubprocess(["wget", OSM_MAIN_DOWNLOAD, "-O", BUILD_FOLDER + basename(OSM_MAIN_DOWNLOAD)])

    LogMessage("Checking all files required for OSM tilemaker...")

    shp_extensions = ['shp', 'shx', 'dbf', 'prj']
    tilemaker_config_json = getJSON(TILEMAKER_CONFIG)
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

    return postgisGetResults("""
    SELECT tables.table_name
    FROM information_schema.tables
    WHERE 
    table_catalog=%s AND 
    table_schema='public' AND 
    table_type='BASE TABLE' AND
    table_name NOT IN ('spatial_ref_sys') AND
    ((table_name LIKE 'tipheight%%') OR (table_name LIKE '%%__clp'));
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

def postgisGetBasicProcessedTables():
    """
    Gets list of all 'basic' processed dataset tables
    ie. where no buffering has been applied
    """

    global POSTGRES_DB

    table_list = postgisGetResults("""
    SELECT tables.table_name
    FROM information_schema.tables
    WHERE 
    table_catalog=%s AND 
    table_schema='public' AND 
    table_type='BASE TABLE' AND
    table_name NOT IN ('spatial_ref_sys') AND 
    table_name LIKE '%%__pro' AND 
    table_name NOT LIKE '%%__buf_%%' AND 
    table_name NOT LIKE 'tipheight_%%' AND 
    table_name NOT LIKE '%%clipping%%';
    """, (POSTGRES_DB, ))
    return [list_item[0] for list_item in table_list]

def postgisGetUKBasicUnprocessedTables():
    """
    Gets list of all UK 'basic' dataset tables where no '__pro' version exists
    This typically occurs with 'Other technical constraints' layers that always 
    require buffering and where this buffering is applied before '__pro' version
    is generated
    """

    global POSTGRES_DB

    basic_processed = postgisGetBasicProcessedTables()
    basic_unprocessed = postgisGetResults("""
    SELECT tables.table_name
    FROM information_schema.tables
    WHERE 
    table_catalog=%s AND 
    table_schema='public' AND 
    table_type='BASE TABLE' AND 
    table_name NOT IN ('spatial_ref_sys') AND 
    table_name LIKE '%%__uk' AND 
    table_name NOT LIKE '%%__pro' AND 
    table_name NOT LIKE '%%__buf_%%' AND 
    table_name NOT LIKE 'tipheight_%%' AND 
    table_name NOT LIKE '%%clipping%%';
    """, (POSTGRES_DB, ))
    basic_unprocessed = [list_item[0] for list_item in basic_unprocessed]
    basic_unprocessed_filtered = []
    for item in basic_unprocessed:
        if (item + '__pro') not in basic_processed: basic_unprocessed_filtered.append(item)

    return basic_unprocessed_filtered

def postgisGetUKBasicProcessedTables():
    """
    Gets list of all UK 'basic' processed dataset tables
    ie. where no buffering has been applied
    """

    global POSTGRES_DB

    table_list = postgisGetResults("""
    SELECT tables.table_name
    FROM information_schema.tables
    WHERE 
    table_catalog=%s AND 
    table_schema='public' AND 
    table_type='BASE TABLE' AND
    table_name NOT IN ('spatial_ref_sys') AND 
    table_name LIKE '%%__uk__pro' AND 
    table_name NOT LIKE '%%__buf_%%';
    """, (POSTGRES_DB, ))
    table_list = [list_item[0] for list_item in table_list]
    table_list.sort()
    return table_list

def postgisDropTable(table_name):
    """
    Drops PostGIS table
    """

    postgisExec("DROP TABLE IF EXISTS %s", (AsIs(table_name), ))

def postgisAmalgamateAndDissolve(target_table, child_tables):
    """
    Amalgamates and dissolves all child tables into target table
    """

    scratch_table_1 = '_scratch_table_1'
    scratch_table_2 = '_scratch_table_2'

    # We run process on all children - even if only one child - as process runs 
    # ST_Union (dissolve) on datasets for first time to eliminate overlapping polygons
     
    children_sql = " UNION ".join(['SELECT geom FROM ' + table_name for table_name in child_tables])

    if postgisCheckTableExists(scratch_table_1): postgisDropTable(scratch_table_1)
    if postgisCheckTableExists(scratch_table_2): postgisDropTable(scratch_table_2)

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

def postgisDistanceToNearestFeature(input_point, dataset_table):
    """
    Calculates distance from point to nearest feature in GIS dataset
    If point is within feature, make distance negative
    """

    global POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD

    if not postgisCheckTableExists(dataset_table):
        LogError("Unable to find requested dataset table - qutting")
        exit()

    conn = psycopg2.connect(host=POSTGRES_HOST, dbname=POSTGRES_DB, user=POSTGRES_USER, password=POSTGRES_PASSWORD)

    # Get standard distance

    cur = conn.cursor()
    cur.execute("SELECT MIN(ST_Distance(ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), 3857), ST_Transform(geom, 3857))) AS distance FROM %s;", \
                    (input_point['lng'], input_point['lat'], AsIs(dataset_table), ))
    distance = cur.fetchone()[0]
    cur.close()

    # If distance = 0, point is on edge or within one or more polygons
    # so perform additional query to get maximum distance inside these containing polygons

    if distance == 0:
        cur = conn.cursor()
        cur.execute("""
        SELECT 
            MAX
            (
                ST_Distance
                (
                    ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), 3857),
                    ST_Transform(ST_ExteriorRing(geom), 3857)
                )
            ) FROM %s 
        WHERE
        ST_Distance 
        (
            ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), 3857),
            ST_Transform(geom, 3857)
        ) = 0;
        """, (input_point['lng'], input_point['lat'], AsIs(dataset_table), input_point['lng'], input_point['lat'], ))
        distance = cur.fetchone()[0]
        cur.close()
        if distance != 0: distance = -distance
    
    return distance

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


# ***********************************************************
# ************** Application logic functions ****************
# ***********************************************************

def removeNonHistoricalTables(table_list):
    """
    Searches list of tables, identifies any historical ones and removes corresponding non-historical one
    """

    historical_tables = []
    for table in table_list:
        if '__hist' in table: historical_tables.append(table)

    for historical_table in historical_tables:
        non_historical_table = historical_table.replace('__hist', '')
        table_list.remove(non_historical_table)

    return table_list

def amalgamateNonUKtables():
    """
    Creates amalgamations of all non UK-specific tables
    eg. ramsar_sites__scotland__pro, ramsar_sites__england__pro, ramsar_sites__northern_ireland__pro => ramsar_sites__uk__pro
    """

    processed_tables = postgisGetBasicProcessedTables()

    tables_to_amalgamate = {}
    for processed_table in processed_tables:
        if '__uk' not in processed_table:
            dataset_code = reformatDatasetName(processed_table)
            dataset_parent = getDatasetParent(dataset_code)
            table_parent = reformatTableName(dataset_parent)
            if table_parent not in tables_to_amalgamate: tables_to_amalgamate[table_parent] = []
            tables_to_amalgamate[table_parent].append(processed_table)

    for parent_table in tables_to_amalgamate.keys():
        target_table = parent_table + '__uk__pro'
        if not postgisCheckTableExists(target_table):
            LogMessage("Amalgamating and dissolving children of parent: " + parent_table)
            postgisAmalgamateAndDissolve(target_table, tables_to_amalgamate[parent_table])

    basic_unprocessed_tables = postgisGetUKBasicUnprocessedTables()
    for basic_unprocessed_table in basic_unprocessed_tables:
        target_table = basic_unprocessed_table + '__pro'
        LogMessage("Processing: " + basic_unprocessed_table)
        postgisAmalgamateAndDissolve(target_table, [basic_unprocessed_table])






testposition = {'lng':0.1405, 'lat': 50.83516}

amalgamateNonUKtables()
tables_to_test = removeNonHistoricalTables(postgisGetUKBasicProcessedTables())
# print(json.dumps(tables_to_test, indent=4))

# testposition = {'lng':-0.06060, 'lat': 50.83516}
# print(testposition, postgisDistanceToNearestFeature(testposition, 'national_parks__uk__pro'))
# testposition = {'lng':-0.05960, 'lat': 50.83516}
# print(testposition, postgisDistanceToNearestFeature(testposition, 'national_parks__uk__pro'))
# testposition = {'lng':-0.05860, 'lat': 50.83516}
# print(testposition, postgisDistanceToNearestFeature(testposition, 'national_parks__uk__pro'))
# testposition = {'lng':-0.05760, 'lat': 50.83516}
# print(testposition, postgisDistanceToNearestFeature(testposition, 'national_parks__uk__pro'))
# testposition = {'lng':-0.05660, 'lat': 50.83516}
# print(testposition, postgisDistanceToNearestFeature(testposition, 'national_parks__uk__pro'))
# testposition = {'lng':-0.05560, 'lat': 50.83516}
# print(testposition, postgisDistanceToNearestFeature(testposition, 'national_parks__uk__pro'))
# testposition = {'lng':-0.05460, 'lat': 50.83516}
# print(testposition, postgisDistanceToNearestFeature(testposition, 'national_parks__uk__pro'))
# testposition = {'lng':0.1405, 'lat': 50.83516}
# print(testposition, postgisDistanceToNearestFeature(testposition, 'national_parks__uk__pro'))


for table_to_test in tables_to_test:
    distance = postgisDistanceToNearestFeature(testposition, table_to_test)
    print("Distance to " + table_to_test + " = " + str(distance))