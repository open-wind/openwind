# ***********************************************************
# *********************** OPEN WIND *************************
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
import csv
import json
# import geojson
import requests
import os
import urllib.request
import subprocess
import xmltodict
import shutil
import yaml
import sqlite3
import psycopg2
import psycopg2.extras 
import time
import pprint as pp
from psycopg2 import sql
from psycopg2.extensions import AsIs
from zipfile import ZipFile
from os import listdir, makedirs
from os.path import isfile, isdir, basename, join, exists
from dotenv import load_dotenv
from osgeo import gdal, osr, ogr

gdal.DontUseExceptions() 

load_dotenv('../.env')

DATASETS_FOLDER                     = 'datasets/'
OSM_MAIN_DOWNLOAD                   = 'https://download.geofabrik.de/europe/united-kingdom-latest.osm.pbf'
OSM_CONFIG_FOLDER                   = 'osm-export-yml/'
OSM_EXPORT_DATA                     = DATASETS_FOLDER + 'osm-export'
WINDSPEED_URL                       = 'https://wewantwind.org/static/gis/windspeeds.geojson.zip'
WINDSPEED_DATASET                   = 'windspeeds-noabl--uk'
WINDTURBINES_OPERATIONAL_DATASET    = 'windturbines-operational--uk'
WINDTURBINES_ALLPROJECTS_DATASET    = 'windturbines-all-projects--uk'
FOOTPATHS_SINGLELINES_DATASET       = 'public-footpaths--uk'
FOOTPATHS_HISTORICAL_DATASET        = FOOTPATHS_SINGLELINES_DATASET + '--hist'
POSTGRES_HOST                       = os.environ.get("POSTGRES_HOST")
POSTGRES_DB                         = os.environ.get("POSTGRES_DB")
POSTGRES_USER                       = os.environ.get("POSTGRES_USER")
POSTGRES_PASSWORD                   = os.environ.get("POSTGRES_PASSWORD")
OVERALL_CLIPPING_FILE               = 'uk-clipping.geojson'
TURFPY_OPTIONS                      = {'units': 'm'}
PROJECTSIZE_CACHE                   = {}
SEARCHAREA_BUFFER_CACHE             = {}
CENSUS_SEARCH_RADIUS                = 10000
TERRAIN_FILE                        = 'terrain_lowres_withfeatures.tif'
DISTANCE_CACHE_TABLE                = 'sitepredictor__distance_cache'
VIEWSHED_RADIUS                     = 20000
GEOMETRY_TYPES_LOOKUP               = {}
SAMPLING_DISTANCE                   = 1000.0
SAMPLING_GRID                       = "sitepredictor__grid_1000_m__uk"
SAMPLING_GRID_DISTANCES             = "sitepredictor__grid_1000_m_distances__uk"

# For South Lanarkshire, unable to find GIS polygons for 'Clydesdale', 'Hamilton', 'East Kilbride'
# which were district councils before being amalgamated into South Lanarkshire in 1996
# Therefore summed data and created new entry for South Lanarkshire for these years

CSV_CONVERSIONS = {
    "geography code": "geo_code",
    "Qualifications: All categories: Highest level of qualification; measures: Value": "total",
    "Qualifications: No qualifications; measures: Value": "qualifications_no_qualifications",
    "Qualifications: Highest level of qualification: Level 1 qualifications; measures: Value": "qualifications_highest_qualification_level_1",
    "Qualifications: Highest level of qualification: Level 2 qualifications; measures: Value": "qualifications_highest_qualification_level_2",
    "Qualifications: Highest level of qualification: Apprenticeship; measures: Value": " qualifications_highest_qualification_apprenticeship",
    "Qualifications: Highest level of qualification: Level 3 qualifications; measures: Value": "qualifications_highest_qualification_level_3",
    "Qualifications: Highest level of qualification: Level 4 qualifications and above; measures: Value": "qualifications_highest_qualification_level_4",
    "Qualifications: Highest level of qualification: Other qualifications; measures: Value": " qualifications_highest_qualification_other",
    "Qualifications: Schoolchildren and full-time students: Age 16 to 17; measures: Value": " qualifications_schoolchildren_student_16_17",
    "Qualifications: Schoolchildren and full-time students: Age 18 and over; measures: Value": " qualifications_schoolchildren_student_18_over",
    "Qualifications: Full-time students: Age 18 to 74: Economically active: In employment; measures: Value": "qualifications_student_economically_active_employed",
    "Qualifications: Full-time students: Age 18 to 74: Economically active: Unemployed; measures: Value": "qualifications_student_economically_inactive_unemployed",
    "Qualifications: Full-time students: Age 18 to 74: Economically inactive; measures: Value": " qualifications_student_economically_inactive",
    "Age: Age 100 and over; measures: Value": "age_100_over",
    "Age: All categories: Age; measures: Value": "total",
    "Age: Age under 1; measures: Value": "age_under_1",
    "Age: Age " : "age_", 
    "Occupation: All categories: Occupation; measures: Value": "total",
    "Occupation: 1. Managers, directors and senior officials; measures: Value": "occupation_1_managers",
    "Occupation: 2. Professional occupations; measures: Value": "occupation_2_professional",
    "Occupation: 3. Associate professional and technical occupations; measures: Value": "occupation_3_associate_professional",
    "Occupation: 4. Administrative and secretarial occupations; measures: Value": "occupation_4_admin_secretarial",
    "Occupation: 5. Skilled trades occupations; measures: Value": "occupation_5_skilled_trades",
    "Occupation: 6. Caring, leisure and other service occupations; measures: Value": "occupation_6_caring_leisure_service",
    "Occupation: 7. Sales and customer service occupations; measures: Value": "occupation_7_sales_customer_service",
    "Occupation: 8. Process plant and machine operatives; measures: Value": "occupation_8_process_plant_machine_operatives",
    "Occupation: 9. Elementary occupations; measures: Value": "occupation_9_elementary_occupations",
    "Tenure: All households; measures: Value": "total",
    "Tenure: Owned; measures: Value": "tenure_owned",
    "Tenure: Owned: Owned outright; measures: Value": "tenure_owned_outright",
    "Tenure: Owned: Owned with a mortgage or loan; measures: Value": "tenure_owned_mortgage_loan",
    "Tenure: Shared ownership (part owned and part rented); measures: Value": "tenure_owned_shared",
    "Tenure: Social rented; measures: Value": "tenure_rented_social",
    "Tenure: Social rented: Rented from council (Local Authority); measures: Value": "tenure_rented_social_council",
    "Tenure: Social rented: Other; measures: Value": "tenure_rented_social_other",
    "Tenure: Private rented; measures: Value": "tenure_rented_private",
    "Tenure: Private rented: Private landlord or letting agency; measures: Value": "tenure_rented_private_landlord_agency",
    "Tenure: Private rented: Other; measures: Value": "tenure_rented_private_other",
    "Tenure: Living rent free; measures: Value": "tenure_living_rent_free",    
    "; measures: Value": "",
}

ADDITIONAL_DOWNLOADS                =   [
                                            {
                                                'dataset': 'sitepredictor--local-authority-party-composition-1973-2015',
                                                'url': 'https://opencouncildata.co.uk/history1973-2015.csv',
                                                'extension': 'csv',
                                                'sql': ['CREATE TABLE sitepredictor__political__uk AS SELECT authority area, year, con, lab, ld, other FROM sitepredictor__local_authority_party_composition_1973_2015',
                                                        'CREATE INDEX ON sitepredictor__political__uk (area)',
                                                        'CREATE INDEX ON sitepredictor__political__uk (year)',
                                                        "INSERT INTO sitepredictor__political__uk SELECT 'South Lanarkshire', year, SUM(con::int), SUM(lab::int), SUM(ld::int), SUM(other::int) FROM sitepredictor__political__uk WHERE area IN ('Clydesdale', 'Hamilton', 'East Kilbride') GROUP BY year;"]
                                            },
                                            {
                                                'dataset': 'sitepredictor--local-authority-party-composition-2016-2024',
                                                'url': 'https://opencouncildata.co.uk/history2016-2024.csv',
                                                'extension': 'csv',
                                                'sql': ['INSERT INTO sitepredictor__political__uk SELECT authority area, year, con, lab, ld, (green::int + pc::int + snp::int + other::int) other FROM sitepredictor__local_authority_party_composition_2016_2024']
                                            },
                                            {
                                                'dataset': 'sitepredictor--local-authority-districts-2016--uk',
                                                'url': 'https://open-geography-portalx-ons.hub.arcgis.com/api/download/v1/items/7c34f405ad78487eb5172158a4c2b82b/geoPackage?layers=0',
                                                'extension': 'gpkg',
                                                'sql': ["CREATE TABLE sitepredictor__councils__uk AS SELECT lad16nm name, 'lad-2016' AS source, geom FROM sitepredictor__local_authority_districts_2016__uk;",
                                                        'CREATE INDEX sitepredictor__councils__uk_idx ON sitepredictor__councils__uk USING GIST (geom);']
                                            },
                                            {
                                                'dataset': 'sitepredictor--counties-2016--uk',
                                                'url': 'https://open-geography-portalx-ons.hub.arcgis.com/api/download/v1/items/4a9ffa2c087841b1aa71188a78930b96/geoPackage?layers=0',
                                                'extension': 'gpkg',
                                                'sql': ["INSERT INTO sitepredictor__councils__uk SELECT cty16nm, 'cty-2016' AS source, geom FROM sitepredictor__counties_2016__uk;"]
                                            },
                                            {
                                                'dataset': 'sitepredictor--local-authority-districts-2008--uk',
                                                'url': 'https://open-geography-portalx-ons.hub.arcgis.com/api/download/v1/items/e131c4a4989b45c7b94ffdd6bf624781/geoPackage?layers=0',
                                                'extension': 'gpkg',
                                                'sql': ["INSERT INTO sitepredictor__councils__uk SELECT lad08nm name, 'lad-2008' AS source, geom FROM sitepredictor__local_authority_districts_2008__uk WHERE lad08nm NOT IN (SELECT name FROM sitepredictor__councils__uk)"]
                                            },
                                            {
                                                'dataset': 'sitepredictor--local-authority-districts-2021--uk',
                                                'url': 'https://open-geography-portalx-ons.hub.arcgis.com/api/download/v1/items/505b177be82946b284c947cab91eeb31/geoPackage?layers=0',
                                                'extension': 'gpkg',
                                                'sql': ["INSERT INTO sitepredictor__councils__uk SELECT lad21nm name, 'lad-2012' AS source, geom FROM sitepredictor__local_authority_districts_2021__uk WHERE lad21nm NOT IN (SELECT name FROM sitepredictor__councils__uk)"]
                                            },
                                            {
                                                'dataset': 'sitepredictor--local-authority-districts-2024--uk',
                                                'url': 'https://open-geography-portalx-ons.hub.arcgis.com/api/download/v1/items/1d4189a8b5db4c28afea8832ab73f93c/geoPackage?layers=0',
                                                'extension': 'gpkg',
                                                'sql': ["INSERT INTO sitepredictor__councils__uk SELECT lad24nm name, 'lad-2024' AS source, geom FROM sitepredictor__local_authority_districts_2024__uk WHERE lad24nm NOT IN (SELECT name FROM sitepredictor__councils__uk)"]
                                            },
                                            {
                                                'dataset': 'sitepredictor--infuse-lsoa--uk',
                                                'url': 'https://borders.ukdataservice.ac.uk/ukborders/easy_download/prebuilt/shape/infuse_lsoa_lyr_2011.zip',
                                                'extension': 'zip',
                                                'srs': 'EPSG:27700',
                                                'sql': ["CREATE TABLE sitepredictor__census_geography__uk AS SELECT geo_code, name, (ST_Dump(geom)).geom geom FROM sitepredictor__infuse_lsoa__uk WHERE geo_code LIKE 'E%' OR geo_code LIKE 'W%' OR geo_code LIKE 'S%'",
                                                        "CREATE INDEX sitepredictor__census_geography__uk_idx ON sitepredictor__census_geography__uk USING GIST (geom);"]
                                            },
                                            {
                                                'dataset': 'sitepredictor--infuse-oa--uk',
                                                'url': 'https://borders.ukdataservice.ac.uk/ukborders/easy_download/prebuilt/shape/infuse_oa_lyr_2011.zip',
                                                'extension': 'zip',
                                                'srs': 'EPSG:27700',
                                                'sql': ["INSERT INTO sitepredictor__census_geography__uk SELECT geo_code, name, (ST_Dump(geom)).geom geom FROM sitepredictor__infuse_oa__uk WHERE geo_code LIKE 'N%'",
                                                        "UPDATE sitepredictor__census_geography__uk SET geom=ST_MakeValid(geom);"]
                                            },
                                            {
                                                'dataset': 'sitepredictor--census-2011-qualifications--england-wales',
                                                'extension': 'csv',
                                                'sql': ["CREATE TABLE sitepredictor__census_2011_qualifications__uk AS SELECT * FROM sitepredictor__census_2011_qualifications__england_wales",
                                                        "CREATE INDEX ON sitepredictor__census_2011_qualifications__uk (geo_code)"]
                                            },
                                            {
                                                'dataset': 'sitepredictor--census-2011-qualifications--scotland',
                                                'extension': 'csv',
                                                'sql': ["INSERT INTO sitepredictor__census_2011_qualifications__uk SELECT * FROM sitepredictor__census_2011_qualifications__scotland"]
                                            },
                                            {
                                                'dataset': 'sitepredictor--census-2011-qualifications--northern-ireland',
                                                'extension': 'csv',
                                                'sql': ["INSERT INTO sitepredictor__census_2011_qualifications__uk SELECT * FROM sitepredictor__census_2011_qualifications__northern_ireland"]
                                            },
                                            {
                                                'dataset': 'sitepredictor--census-2011-age--england-wales',
                                                'extension': 'csv',
                                                'sql': ["CREATE TABLE sitepredictor__census_2011_age__uk AS SELECT * FROM sitepredictor__census_2011_age__england_wales",
                                                        "CREATE INDEX ON sitepredictor__census_2011_age__uk (geo_code)"]
                                            },
                                            {
                                                'dataset': 'sitepredictor--census-2011-age--scotland',
                                                'extension': 'csv',
                                                'sql': ["INSERT INTO sitepredictor__census_2011_age__uk SELECT * FROM sitepredictor__census_2011_age__scotland"]
                                            },
                                            {
                                                'dataset': 'sitepredictor--census-2011-age--northern-ireland',
                                                'extension': 'csv',
                                                'sql': ["INSERT INTO sitepredictor__census_2011_age__uk SELECT * FROM sitepredictor__census_2011_age__northern_ireland"]
                                            },
                                            {
                                                'dataset': 'sitepredictor--census-2011-occupation--england-wales',
                                                'extension': 'csv',
                                                'sql': ["CREATE TABLE sitepredictor__census_2011_occupation__uk AS SELECT * FROM sitepredictor__census_2011_occupation__england_wales",
                                                        "CREATE INDEX ON sitepredictor__census_2011_occupation__uk (geo_code)"]
                                            },
                                            {
                                                'dataset': 'sitepredictor--census-2011-occupation--scotland',
                                                'extension': 'csv',
                                                'sql': ["INSERT INTO sitepredictor__census_2011_occupation__uk SELECT * FROM sitepredictor__census_2011_occupation__scotland"]
                                            },
                                            {
                                                'dataset': 'sitepredictor--census-2011-occupation--northern-ireland',
                                                'extension': 'csv',
                                                'sql': ["INSERT INTO sitepredictor__census_2011_occupation__uk SELECT * FROM sitepredictor__census_2011_occupation__northern_ireland"]
                                            },
                                            {
                                                'dataset': 'sitepredictor--census-2011-tenure--england-wales',
                                                'extension': 'csv',
                                                'sql': ["CREATE TABLE sitepredictor__census_2011_tenure__uk AS SELECT * FROM sitepredictor__census_2011_tenure__england_wales",
                                                        "CREATE INDEX ON sitepredictor__census_2011_tenure__uk (geo_code)"]
                                            },
                                            {
                                                'dataset': 'sitepredictor--census-2011-tenure--scotland',
                                                'extension': 'csv',
                                                'sql': ["INSERT INTO sitepredictor__census_2011_tenure__uk SELECT * FROM sitepredictor__census_2011_tenure__scotland"]
                                            },
                                            {
                                                'dataset': 'sitepredictor--census-2011-tenure--northern-ireland',
                                                'extension': 'csv',
                                                'sql': ["INSERT INTO sitepredictor__census_2011_tenure__uk SELECT * FROM sitepredictor__census_2011_tenure__northern_ireland"]
                                            }
                                        ]
LOCALAUTHORITY_CONVERSIONS          = 'localauthorityconversion.json'
TABLES_TO_EXCLUDE                   =   [ \
                                            WINDSPEED_DATASET.replace('-', '_'),                    # We don't care about distance on this dataset \
                                            WINDTURBINES_OPERATIONAL_DATASET.replace('-', '_'),     # We running query off wind turbines so ignore wind turbine datasets \
                                            WINDTURBINES_ALLPROJECTS_DATASET.replace('-', '_'),     # We running query off wind turbines so ignore wind turbine datasets \
                                            'public_roads_a_and_b_roads_and_motorways__uk__pro',    # osm-export-tool divides out components \
                                            'power_lines__uk__pro',                                 # osm-export-tool divides out components \
                                        ]

# ***********************************************************
# Parameters that specify how close footpath needs to be to 
# turbines to count as 'turbine-caused' footpath
# All parameters are in metres
# ***********************************************************

# Maximum distance between start/end of footpath and turbine to count as turbine-created footpath
# ie. if a footpath starts or eventually leads to a turbine within 100 metres, then turbine-created footpath

MAXIMUM_DISTANCE_ENDPOINT           = 100

# Maxiumum distance between point along line and turbine to count as turbine-created footpath
# ie. if footpath comes within 50 metres of turbine along its stretch, then turbine-created footpath
# NOTE: 50 metres is typical turbine micrositing distance

MAXIMUM_DISTANCE_LINE               = 50

# Buffer distance when selecting turbine positions based on footpath start/end points

BUFFER_DISTANCE                     = 1000

# Distance to 'walk' along footpath when checking proximity of turbine to segment of footpath line

FOOTPATH_WALK_DISTANCE              = 10



logging.basicConfig(
    format='%(asctime)s [%(levelname)-2s] %(message)s',
    level=logging.INFO)

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

def processCSVFile(file_path):
    """
    Carries out a series of text substitutions using CSV_CONVERSIONS
    """

    global CSV_CONVERSIONS

    with open(file_path, 'r') as f: text_file_content = f.read()

    for text_conversion in CSV_CONVERSIONS.keys():
        text_file_content = text_file_content.replace(text_conversion, CSV_CONVERSIONS[text_conversion])

    with open(file_path, 'w') as f: f.write(text_file_content)

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

def runSubprocess(subprocess_array):
    """
    Runs subprocess
    """

    output = subprocess.run(subprocess_array)

    # print("\n" + " ".join(subprocess_array) + "\n")

    if output.returncode != 0:
        LogError("subprocess.run failed with error code: " + str(output.returncode) + '\n' + " ".join(subprocess_array))
    return " ".join(subprocess_array)

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

def convertGPKG2GeoJSON(input_file):
    """
    Converts GPKG to GeoJSON, creating file at same level with different extension
    """

    input_file_gpkg = input_file
    output_file_geojson = input_file.replace('.gpkg', '.geojson')

    inputs = runSubprocess(["ogr2ogr", \
                            output_file_geojson, \
                            "-overwrite", \
                            input_file_gpkg ])

# ***********************************************************
# ********************** GIS functions **********************
# ***********************************************************

def getElevation(position):
    """
    Gets elevation of position (lng, lat)
    """

    global TERRAIN_FILE
    # With thanks to https://stackoverflow.com/questions/74026802/get-elevation-from-lat-long-of-geotiff-data-in-gdal
    ds = gdal.OpenEx(TERRAIN_FILE)
    raster_proj = ds.GetProjection()
    gt = ds.GetGeoTransform()
    ds = None
    source_srs = osr.SpatialReference()
    source_srs.ImportFromWkt(osr.GetUserInputAsWKT("urn:ogc:def:crs:OGC:1.3:CRS84"))
    target_srs = osr.SpatialReference()
    target_srs.ImportFromWkt(raster_proj)
    ct = osr.CoordinateTransformation(source_srs, target_srs)
    mapx, mapy, *_ = ct.TransformPoint(position['lng'], position['lat'])
    gt_inv = gdal.InvGeoTransform(gt) 
    px, py = gdal.ApplyGeoTransform(gt_inv, mapx, mapy)
    py = int(py)
    px = int(px)
    ds = gdal.OpenEx(TERRAIN_FILE)
    elevation_value = ds.ReadAsArray(px, py, 1, 1)
    ds = None
    elevation = elevation_value[0][0]
    return elevation, mapx, mapy

def getViewshed(position, height_to_tip):
    """
    Generates viewshed for turbine of specific height at position (lng, lat)
    """

    global TERRAIN_FILE, VIEWSHED_RADIUS

    uniqueid = str(position['lng']) + '_' + str(position['lat']) + '_' + str(height_to_tip)
    elevation, observerX, observerY = getElevation(position)
    turbinetip_outfile = '/vsimem/' + uniqueid + "_tip.tif"

    src_ds = gdal.Open(TERRAIN_FILE)

    gdal.ViewshedGenerate(
        srcBand = src_ds.GetRasterBand(1),
        driverName = 'GTiff',
        targetRasterName = turbinetip_outfile,
        creationOptions = [],
        observerX = observerX,
        observerY = observerY,
        observerHeight = int(height_to_tip + 0.5),
        targetHeight = 1.5,
        visibleVal = 255.0,
        invisibleVal = 0.0,
        outOfRangeVal = 0.0,
        noDataVal = 0.0,
        dfCurvCoeff = 1.0,
        mode = 1,
        maxDistance = VIEWSHED_RADIUS) 

    turbinetip_geojson = json.loads(polygonizeraster(uniqueid, turbinetip_outfile))

    return turbinetip_geojson

def reprojectrasterto4326(input_file, output_file):
    warp = gdal.Warp(output_file, gdal.Open(input_file), dstSRS='EPSG:4326')
    warp = None

def read_file(filename):
    vsifile = gdal.VSIFOpenL(filename,'r')
    gdal.VSIFSeekL(vsifile, 0, 2)
    vsileng = gdal.VSIFTellL(vsifile)
    gdal.VSIFSeekL(vsifile, 0, 0)
    return gdal.VSIFReadL(1, vsileng, vsifile)

def polygonizeraster(uniqueid, raster_file):
    memory_geojson = '/vsimem/' + uniqueid + ".geojson"
    memory_transformed_raster = '/vsimem/' + uniqueid + '.tif'
    reprojectrasterto4326(raster_file, memory_transformed_raster)

    driver = ogr.GetDriverByName("GeoJSON")
    ds = gdal.OpenEx(memory_transformed_raster)
    raster_proj = ds.GetProjection()
    ds = None
    source_srs = osr.SpatialReference()
    source_srs.ImportFromWkt(raster_proj)
    src_ds = gdal.Open(memory_transformed_raster)
    srs = osr.SpatialReference()
    srs.ImportFromWkt(src_ds.GetProjection())    
    srcband = src_ds.GetRasterBand(1)

    dst_ds = driver.CreateDataSource(memory_geojson)
    dst_layer = dst_ds.CreateLayer("viewshed", srs = source_srs)
    newField = ogr.FieldDefn('Area', ogr.OFTInteger)
    dst_layer.CreateField(newField)
    polygonize = gdal.Polygonize(srcband, srcband, dst_layer, 0, [], callback=None )
    polygonize = None
    del dst_ds

    geojson_content = read_file(memory_geojson)

    return geojson_content
    
# ***********************************************************
# ******************** PostGIS functions ********************
# ***********************************************************

def postgisCheckTableExists(table_name):
    """
    Checks whether table already exists
    """

    global POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD

    table_name = reformatTableName(table_name)
    conn = psycopg2.connect(host=POSTGRES_HOST, dbname=POSTGRES_DB, user=POSTGRES_USER, password=POSTGRES_PASSWORD)
    cur = conn.cursor()
    cur.execute("SELECT EXISTS(SELECT * FROM information_schema.tables WHERE table_name=%s);", (table_name, ))
    tableexists = cur.fetchone()[0]
    cur.close()
    return tableexists

def postgisCheckHistoricalTableExists(table_name):
    """
    Checks whether historical version of table exists
    """

    return postgisCheckTableExists(getHistoricalTableName(table_name))

def postgisExec(sql_text, sql_parameters=None):
    """
    Executes SQL statement
    """

    global POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD

    conn = psycopg2.connect(host=POSTGRES_HOST, dbname=POSTGRES_DB, user=POSTGRES_USER, password=POSTGRES_PASSWORD, \
                            keepalives=1, keepalives_idle=30, keepalives_interval=5, keepalives_count=5)
    cur = conn.cursor()
    if sql_parameters is None: cur.execute(sql_text)
    else: cur.execute(sql_text, sql_parameters)
    conn.commit()
    conn.close()

def postgisImportDatasetGIS(dataset_path, dataset_table, orig_srs='EPSG:4326'):
    """
    Imports GIS file to PostGIS table
    """

    global POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD

    LogMessage("Importing into PostGIS: " + dataset_table)

    if '.gpkg' in dataset_path: orig_srs = getGPKGProjection(dataset_path)

    inputs = runSubprocess(["ogr2ogr", \
                            "-f", "PostgreSQL", \
                            'PG:host=' + POSTGRES_HOST + ' user=' + POSTGRES_USER + ' password=' + POSTGRES_PASSWORD + ' dbname=' + POSTGRES_DB, \
                            dataset_path, \
                            "-overwrite", \
                            "-nln", dataset_table, \
                            "-nlt", 'POLYGON', \
                            "--config", "OGR_PG_ENABLE_METADATA=NO", \
                            "-lco", "GEOMETRY_NAME=geom", \
                            "-lco", "OVERWRITE=YES", \
                            "-s_srs", orig_srs, \
                            "-t_srs", 'EPSG:4326'])

    LogMessage("Created PostGIS table: " + dataset_table)

def postgisExportExplodedDataset(dataset, filepath, geometrytype):
    """
    Exports PostGIS to file
    """

    global POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD

    table = reformatTableName(dataset)
    runSubprocess([ "ogr2ogr", \
                    "-f", "GeoJSON", \
                    filepath, \
                    'PG:host=' + POSTGRES_HOST + ' user=' + POSTGRES_USER + ' password=' + POSTGRES_PASSWORD + ' dbname=' + POSTGRES_DB, \
                    "--config", "OGR_PG_ENABLE_METADATA=NO", \
                    "-nln", dataset, \
                    "-dialect", "sqlite", \
                    "-explodecollections", \
                    "-sql", "SELECT fid, geom FROM '" + table + "' WHERE ST_GeometryType(geom)='" + geometrytype + "'"]) 
    
def postgisGetResults(sql_text, sql_parameters=None):
    """
    Runs database query and returns results
    """

    global POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD

    conn = psycopg2.connect(host=POSTGRES_HOST, dbname=POSTGRES_DB, user=POSTGRES_USER, password=POSTGRES_PASSWORD)
    cur = conn.cursor()
    if sql_parameters is None: cur.execute(sql_text)
    else: cur.execute(sql_text, sql_parameters)
    results = cur.fetchall()
    conn.close()
    return results

def postgisGetResultsAsDict(sql_text, sql_parameters=None):
    """
    Runs database query and returns results
    """

    global POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD

    conn = psycopg2.connect(host=POSTGRES_HOST, dbname=POSTGRES_DB, user=POSTGRES_USER, password=POSTGRES_PASSWORD)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if sql_parameters is None: cur.execute(sql_text)
    else: cur.execute(sql_text, sql_parameters)
    results = cur.fetchall()
    conn.close()
    return results

def postgisAddProportionalFields(table):
    """
    Adds '__prop' fields to UK census tables containing proportional values (assuming 'total' field exists)
    """

    # Only apply to UK census tables

    if 'census' not in table: return

    fields = postgisGetResults("SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = %s", (table, ))
    fields = [field[0] for field in fields]
    if 'total' not in fields: return
    for field in ['total', 'geom', 'ogc_fid', 'date', 'year', 'geography', 'geo_code']:
        if field in fields: fields.remove(field)

    # print(json.dumps(fields, indent=4))
    for field in fields:
        if '__prop' in field: continue
        proportional_field = field + '__prop'
        if proportional_field in fields: continue

        postgisExec('ALTER TABLE %s ADD COLUMN %s FLOAT;', (AsIs(table), AsIs(proportional_field), ))
        postgisExec('UPDATE %s SET %s = (%s::float / total::float)', (AsIs(table), AsIs(proportional_field), AsIs(field), ))

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
    table_name NOT LIKE '%%clipping%%' AND 
    table_name NOT LIKE '_scratch%%' AND 
    table_name NOT LIKE 'sitepredictor__%%' AND 
    table_name NOT LIKE '%%__3857';
    """, (POSTGRES_DB, ))
    return [list_item[0] for list_item in table_list]

def postgisGetBasicUnprocessedTables():
    """
    Gets list of all 'basic' unprocessed dataset tables
    ie. where no buffering has been applied
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
    table_name NOT LIKE '%%__pro' AND 
    table_name NOT LIKE '%%__buf_%%' AND 
    table_name NOT LIKE 'tipheight_%%' AND 
    table_name NOT LIKE '%%clipping%%' AND 
    table_name NOT LIKE '_scratch%%' AND
    table_name NOT LIKE 'sitepredictor__%%' AND 
    table_name NOT LIKE '%%__3857';
    """, (POSTGRES_DB, ))
    basic_unprocessed = [list_item[0] for list_item in basic_unprocessed]
    basic_unprocessed_filtered = []
    for item in basic_unprocessed:
        if (item + '__pro') not in basic_processed: basic_unprocessed_filtered.append(item)

    return basic_unprocessed_filtered

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
    table_name NOT LIKE '%%clipping%%' AND 
    table_name NOT LIKE '_scratch%%' AND 
    table_name NOT LIKE 'sitepredictor__%%' AND 
    table_name NOT LIKE '%%__3857';
    """, (POSTGRES_DB, ))
    basic_unprocessed = [list_item[0] for list_item in basic_unprocessed]
    print(json.dumps(basic_unprocessed, indent=4))
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
    table_name NOT LIKE '%%__buf_%%' AND 
    table_name NOT LIKE 'sitepredictor__%%' AND 
    table_name NOT LIKE '%%__3857';
    """, (POSTGRES_DB, ))
    table_list = [list_item[0] for list_item in table_list]
    table_list.sort()
    return table_list

def postgisDropTable(table_name):
    """
    Drops PostGIS table
    """

    table_name = reformatTableName(table_name)
    postgisExec("DROP TABLE IF EXISTS %s", (AsIs(table_name), ))

def postgisProcessTable(source_table, processed_table):
    """
    Processes table 
    - Performs clipping
    - Dumps out geometry
    - NOTE: Does not remove non-polygons as we may require points for site prediction
    """

    scratch_table_1 = '_scratch_table_1'
    scratch_table_2 = '_scratch_table_2'

    clipping_table = reformatTableName(OVERALL_CLIPPING_FILE)
    clipping_union_table = buildUnionTableName(clipping_table)

    LogMessage("Processing table: " + source_table)

    if postgisCheckTableExists(processed_table): postgisDropTable(processed_table)

    # Explode geometries with ST_Dump to remove MultiPolygon,
    # MultiSurface, etc and homogenize processing
    # NOTE: Does not remove non-polygons as we may require points for site prediction

    if postgisCheckTableExists(scratch_table_1): postgisDropTable(scratch_table_1)
    if postgisCheckTableExists(scratch_table_2): postgisDropTable(scratch_table_2)

    LogMessage(" --> Step 1: Dump geometries and make valid")

    postgisExec("CREATE TABLE %s AS SELECT ST_MakeValid(dumped.geom) geom FROM (SELECT (ST_Dump(geom)).geom geom FROM %s) dumped;", \
                (AsIs(scratch_table_1), AsIs(source_table), ))
    
    postgisExec("CREATE INDEX %s ON %s USING GIST (geom);", (AsIs(scratch_table_1 + "_idx"), AsIs(scratch_table_1), ))

    LogMessage(" --> Step 2: Clipping partially overlapping geometries")

    postgisExec("""
    CREATE TABLE %s AS 
        SELECT ST_Intersection(clipping.geom, data.geom) geom
        FROM %s data, %s clipping 
        WHERE 
            (NOT ST_Contains(clipping.geom, data.geom) AND 
            ST_Intersects(clipping.geom, data.geom));""", \
        (AsIs(scratch_table_2), AsIs(scratch_table_1), AsIs(clipping_union_table), ))

    LogMessage(" --> Step 3: Adding fully enclosed geometries")

    postgisExec("""
    INSERT INTO %s  
        SELECT data.geom  
        FROM %s data, %s clipping 
        WHERE 
            ST_Contains(clipping.geom, data.geom);""", \
        (AsIs(scratch_table_2), AsIs(scratch_table_1), AsIs(clipping_union_table), ))

    LogMessage(" --> Step 4: Dumping geometries")

    postgisExec("CREATE TABLE %s AS SELECT dumped.geom FROM (SELECT (ST_Dump(geom)).geom geom FROM %s) AS dumped;", (AsIs(processed_table), AsIs(scratch_table_2), ))
    postgisExec("CREATE INDEX %s ON %s USING GIST (geom);", (AsIs(processed_table + "_idx"), AsIs(processed_table), ))

    if postgisCheckTableExists(scratch_table_1): postgisDropTable(scratch_table_1)
    if postgisCheckTableExists(scratch_table_2): postgisDropTable(scratch_table_2)

    LogMessage(" --> COMPLETED: Processed table: " + processed_table)
    
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

def postgisDistanceToNearestFeature(ogc_fid, dataset_table):
    """
    Gets distance of turbine from specific layer from cache using turbine's ogc_fid
    """

    global DISTANCE_CACHE_TABLE

    # createDistanceCache([dataset_table])

    distance = postgisGetResults(   "SELECT distance FROM %s WHERE ogc_fid = %s AND table_name = %s;", \
                                    (AsIs(DISTANCE_CACHE_TABLE), \
                                    AsIs(ogc_fid), \
                                    dataset_table))
    distance = distance[0][0]

    return distance

def createTransformedTable(dataset_table):
    """
    Creates fresh transformed table with EPSG:3857 projection
    """

    dataset_table_transformed = dataset_table + '__3857'
    if not postgisCheckTableExists(dataset_table_transformed):         

        LogMessage("Recreating EPSG:3857 projected version of: " + dataset_table)

        postgisExec("CREATE TABLE %s AS SELECT ST_Transform(geom, 3857) geom FROM %s", (AsIs(dataset_table_transformed), AsIs(dataset_table), ))
        postgisExec("CREATE INDEX %s ON %s USING GIST (geom);", (AsIs(dataset_table_transformed + "_idx"), AsIs(dataset_table_transformed), ))

    return dataset_table_transformed

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

    return name.replace('.gpkg', '').replace('.geojson', '').replace("-", "_")

def getHistoricalTableName(table):
    """
    Gets historical equivalent of table
    """

    table = reformatTableName(table)
    return table.replace('__uk__pro', '__uk__hist__pro')

def getDatasetParent(file_path):
    """
    Gets dataset parent name from file path
    Parent = 'description', eg 'national-parks'
    """

    file_basename = basename(file_path).split(".")[0]
    return "--".join(file_basename.split("--")[0:1])

def removeNonEssentialTablesForDistance(table_list):
    """
    Removes any tables we don't want to conduct distance analysis on
    """

    global TABLES_TO_EXCLUDE

    table_list_removed_historical = removeNonHistoricalTables(table_list)

    table_list_final = []
    for table in table_list_removed_historical:

        # Exclude all internal tables
        if table.startswith('_'): continue

        # Exclude tables specifically listed in TABLES_TO_EXCLUDE
        if table not in TABLES_TO_EXCLUDE: table_list_final.append(table)

    return table_list_final

def removeNonHistoricalTables(table_list):
    """
    Searches list of tables, identifies any historical ones and removes corresponding non-historical one
    """

    final_tables = []
    for table in table_list:
        if postgisCheckHistoricalTableExists(table): final_tables.append(getHistoricalTableName(table))
        else: final_tables.append(table)

    return final_tables

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

# ***********************************************************
# ************** Application logic functions ****************
# ***********************************************************

def amalgamateNonUKtables():
    """
    Creates amalgamations of all non UK-specific tables
    eg. ramsar_sites__scotland__pro, ramsar_sites__england__pro, ramsar_sites__northern_ireland__pro => ramsar_sites__uk__pro
    """

    global TABLES_TO_EXCLUDE

    # Process any unprocessed 'basic' (ie. non-buffered) tables

    basic_unprocessed_tables = postgisGetBasicUnprocessedTables()
    for basic_unprocessed_table in basic_unprocessed_tables:
        if basic_unprocessed_table in TABLES_TO_EXCLUDE: continue
        postgisProcessTable(basic_unprocessed_table, buildProcessedTableName(basic_unprocessed_table))

    # Iterate through all processed basic tables and create 
    # list of all amalgamations that need to exist

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

def osmDownloadData():
    """
    Downloads core OSM data
    """

    global OSM_MAIN_DOWNLOAD, DATASETS_FOLDER, OSM_EXPORT_DATA, OSM_CONFIG_FOLDER, OVERALL_CLIPPING_FILE

    makeFolder(DATASETS_FOLDER)

    if not isfile(DATASETS_FOLDER + basename(OSM_MAIN_DOWNLOAD)):

        LogMessage("Downloading latest OSM data for britain and ireland")

        runSubprocess(["wget", OSM_MAIN_DOWNLOAD, "-O", DATASETS_FOLDER + basename(OSM_MAIN_DOWNLOAD)])

    yaml_all_filename, yaml_all_content = OSM_CONFIG_FOLDER + 'all.yml', {}

    if (not isfile(OSM_EXPORT_DATA + '.gpkg')) or (not isfile(yaml_all_filename)):

        LogMessage("Missing " + OSM_EXPORT_DATA + ".gpkg, running osm-export-tool to generate it using: " + yaml_all_filename)

        yaml_files = getFilesInFolder(OSM_CONFIG_FOLDER)
        for yaml_file in yaml_files:
            if yaml_file == yaml_all_filename: continue

            with open(OSM_CONFIG_FOLDER + yaml_file) as stream:
                try:
                    yaml_content = yaml.safe_load(stream)
                except yaml.YAMLError as exc:
                    LogMessage(exc)
                    exit()

            if yaml_content is None: continue
            yaml_content_keys = list(yaml_content.keys())
            if len(yaml_content_keys) == 0: continue

            for yaml_content_key in yaml_content_keys: 
                yaml_all_content[yaml_content_key] = yaml_content[yaml_content_key]

        with open(yaml_all_filename, "w") as yaml_file: yaml_file.write(yaml.dump(yaml_all_content))

        runSubprocess(["osm-export-tool", DATASETS_FOLDER + basename(OSM_MAIN_DOWNLOAD), OSM_EXPORT_DATA, "-m", yaml_all_filename, "--clip", OVERALL_CLIPPING_FILE])

    with open(yaml_all_filename) as stream:
        try:
            yaml_content = yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            LogMessage(exc)
            exit()

    if yaml_content is not None: 
        yaml_content_keys = list(yaml_content.keys())

        for yaml_content_key in yaml_content_keys:
            if not postgisCheckTableExists(yaml_content_key):

                LogMessage("Importing dataset: " + yaml_content_key)

                inputs = runSubprocess(["ogr2ogr", \
                                        "-f", "PostgreSQL", \
                                        'PG:host=' + POSTGRES_HOST + ' user=' + POSTGRES_USER + ' password=' + POSTGRES_PASSWORD + ' dbname=' + POSTGRES_DB, \
                                        OSM_EXPORT_DATA + '.gpkg', \
                                        "-overwrite", \
                                        "-nln", reformatTableName(yaml_content_key), \
                                        "-lco", "GEOMETRY_NAME=geom", \
                                        "-lco", "OVERWRITE=YES", \
                                        "-dialect", "sqlite", \
                                        "-sql", \
                                        "SELECT * FROM '" + yaml_content_key + "'" ])

def clipDataset(input_file_path, output_file_path):
    """
    Clips dataset
    """

    global OVERALL_CLIPPING_FILE

    LogMessage("Clipping file: " + input_file_path)

    inputs = runSubprocess(["ogr2ogr", \
                            output_file_path, \
                            "-overwrite", \
                            "--config", "OGR_PG_ENABLE_METADATA=NO", \
                            "-clipsrc", input_file_path, \
                            OVERALL_CLIPPING_FILE ])

def exportGeoJSONFootpaths():
    """
    Downloads all footpaths as single lines
    ie. if single line leads to turbine or very close to turbine, it's probably new footpath created for turbine
    """

    global DATASETS_FOLDER, FOOTPATHS_SINGLELINES_DATASET

    makeFolder(DATASETS_FOLDER)

    footpaths_singlelines_path = DATASETS_FOLDER + FOOTPATHS_SINGLELINES_DATASET + '.geojson'

    if not isfile(footpaths_singlelines_path):

        LogMessage("Exporting PostGIS footpaths to: " + footpaths_singlelines_path)

        postgisExportExplodedDataset(FOOTPATHS_SINGLELINES_DATASET, footpaths_singlelines_path, 'LINESTRING')

def exportGeoJSONWindTurbines():
    """
    Downloads wind turbines from PostGIS
    """

    global POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
    global DATASETS_FOLDER, WINDTURBINES_OPERATIONAL_DATASET

    makeFolder(DATASETS_FOLDER)

    windturbines_operational_path = DATASETS_FOLDER + WINDTURBINES_OPERATIONAL_DATASET + '.geojson'

    if not isfile(windturbines_operational_path):

        LogMessage("Exporting PostGIS onshore wind turbines to: " + windturbines_operational_path)

        postgisExportExplodedDataset(WINDTURBINES_OPERATIONAL_DATASET, windturbines_operational_path, 'POINT')

def generateHistoricalFootpaths():
    """
    Process footpaths to remove those likely to have been created to provide access to new turbines
    ie. leaving only those footpaths likely to have existed before specific wind turbines were built
    """

    global FOOTPATHS_SINGLELINES_DATASET, FOOTPATHS_HISTORICAL_DATASET, WINDTURBINES_OPERATIONAL_DATASET
    global MAXIMUM_DISTANCE_ENDPOINT, MAXIMUM_DISTANCE_LINE

    osmDownloadData()

    footpaths_original_table = reformatTableName(FOOTPATHS_SINGLELINES_DATASET) + '__pro__3857'
    footpaths_historical_table = reformatTableName(FOOTPATHS_HISTORICAL_DATASET) + '__pro__3857'
    windturbines_operational_table = reformatDatasetName(WINDTURBINES_OPERATIONAL_DATASET)

    if not postgisCheckTableExists(footpaths_historical_table):

        LogMessage("Historical footpaths recreation: creating copy of footpaths in table " + footpaths_historical_table)

        postgisExec("CREATE TABLE %s AS SELECT * FROM %s;", (AsIs(footpaths_historical_table), AsIs(footpaths_original_table), ))
        postgisExec("CREATE INDEX " + FOOTPATHS_HISTORICAL_DATASET + "_idx ON %s USING GIST (geom);", (AsIs(FOOTPATHS_HISTORICAL_DATASET), ))

        LogMessage("Historical footpaths recreation: Deleting footpaths whose start or end points within " + str(MAXIMUM_DISTANCE_ENDPOINT) + " metres of turbine...")

        postgisExec("""
        DELETE FROM %s footpath 
        WHERE 
        ((SELECT MIN(ST_Distance(ST_StartPoint(footpath.geom), ST_Transform(turbine.geom, 3857))) FROM %s turbine) < %s) OR 
        ((SELECT MIN(ST_Distance(ST_EndPoint(footpath.geom), ST_Transform(turbine.geom, 3857))) FROM %s turbine) < %s)""", \
        (   AsIs(footpaths_historical_table), \
            AsIs(windturbines_operational_table), \
            AsIs(MAXIMUM_DISTANCE_ENDPOINT), \
            AsIs(windturbines_operational_table), \
            AsIs(MAXIMUM_DISTANCE_ENDPOINT), ))

        LogMessage("Historical footpaths recreation: Deleting footpaths that at some point along length within " + str(MAXIMUM_DISTANCE_LINE) + " metres of turbine...")

        postgisExec("""
        DELETE FROM %s footpath 
        WHERE 
        ((SELECT MIN(ST_Distance(footpath.geom, ST_Transform(turbine.geom, 3857))) FROM %s turbine) < %s)""", \
        (AsIs(footpaths_historical_table), AsIs(windturbines_operational_table), AsIs(MAXIMUM_DISTANCE_LINE), ))

        LogMessage("Historical footpaths recreation: COMPLETED")

def downloadWindSpeeds():
    """
    Download wind speed data
    """

    global DATASETS_FOLDER, WINDSPEED_URL, WINDSPEED_DATASET

    windspeed_download_zip_path = DATASETS_FOLDER + basename(WINDSPEED_URL)
    windspeed_download_unzip_path = windspeed_download_zip_path.replace('.zip', '')
    windspeed_dataset_path = DATASETS_FOLDER + WINDSPEED_DATASET + '.geojson'
    windspeed_table = reformatTableName(WINDSPEED_DATASET)

    if not isfile(windspeed_dataset_path):

        LogMessage("Downloading NOABL wind speed data...")

        attemptDownloadUntilSuccess(WINDSPEED_URL, windspeed_download_zip_path)

        with ZipFile(windspeed_download_zip_path, 'r') as zip_ref: zip_ref.extractall(DATASETS_FOLDER)
        os.remove(windspeed_download_zip_path)
        shutil.move(windspeed_download_unzip_path, windspeed_dataset_path)

    if not postgisCheckTableExists(windspeed_table):

        LogMessage("Importing wind speed data into PostGIS...")

        postgisImportDatasetGIS(windspeed_dataset_path, windspeed_table)

def getWindSpeed(position):
    """
    Gets wind speed at specific point
    """

    global WINDSPEED_DATASET

    windspeeds = postgisGetResults("SELECT MAX(windspeed) FROM %s WHERE ST_Intersects(geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326))", \
                                   (AsIs(reformatTableName(WINDSPEED_DATASET)), position['lng'], position['lat'], ))

    if len(windspeeds) == 0: return None

    return windspeeds[0][0]

def importAllWindProjects():
    """
    Imports manually curated list of all failed and successful wind turbine positions
    """

    global WINDTURBINES_ALLPROJECTS_DATASET

    onshore_allprojects_dataset_path = WINDTURBINES_ALLPROJECTS_DATASET + '.geojson'

    if not isfile(onshore_allprojects_dataset_path):

        LogError("No data file containing all turbine coordinates for failed and successful projects - ABORTING")
        exit()

    if not postgisCheckTableExists(WINDTURBINES_ALLPROJECTS_DATASET): 
        
        LogMessage("Importing all failed and successful wind turbine projects...")

        postgisImportDatasetGIS(onshore_allprojects_dataset_path, WINDTURBINES_ALLPROJECTS_DATASET)

        LogMessage("All failed and successful wind turbine projects imported")

def getAllWindProjects():
    """
    Gets all wind projects
    """

    global WINDTURBINES_ALLPROJECTS_DATASET

    return postgisGetResultsAsDict("""
    SELECT *, 
    ST_X (ST_Transform (geom, 4326)) AS lng,
    ST_Y (ST_Transform (geom, 4326)) AS lat 
    FROM %s ORDER BY project_guid
    """, (AsIs(reformatTableName(WINDTURBINES_ALLPROJECTS_DATASET)), ))

def getOperationalBeforeDateWithinDistance(date, position, distance):
    """
    Gets number of operational wind turbines before 'date' and within 'distance'
    """

    if date == '': return None

    results = postgisGetResults("""
    SELECT COUNT(*) 
    FROM windturbines_all_projects__uk 
    WHERE 
    (project_date_operational IS NOT NULL) AND 
    (project_date_operational < %s) AND 
    ST_Distance(ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), 3857), ST_Transform(geom, 3857)) < %s;
    """, (date, position['lng'], position['lat'], distance, ))
    return results[0][0]

def getApprovedBeforeDateWithinDistance(date, position, distance):
    """
    Gets number of approved wind turbines before 'date' and within 'distance'
    """

    if date == '': return None

    results = postgisGetResults("""
    SELECT COUNT(*) 
    FROM windturbines_all_projects__uk 
    WHERE 
    (project_date_end IS NOT NULL) AND 
    (project_date_end < %s) AND 
    (project_status IN ('Decommissioned', 'Application Granted', 'Awaiting Construction', 'Under Construction', 'Operational')) AND 
    ST_Distance(ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), 3857), ST_Transform(geom, 3857)) < %s;
    """, (date, position['lng'], position['lat'], distance, ))
    return results[0][0]

def getAppliedBeforeDateWithinDistance(date, position, distance):
    """
    Gets number of wind turbine applications before 'date' and within 'distance'
    """

    if date == '': return None

    results = postgisGetResults("""
    SELECT COUNT(*) 
    FROM windturbines_all_projects__uk 
    WHERE 
    (project_date_start IS NOT NULL) AND 
    (project_date_start < %s) AND 
    (project_status IN ('Application Submitted', 'Appeal Lodged')) AND 
    ST_Distance(ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), 3857), ST_Transform(geom, 3857)) < %s;
    """, (date, position['lng'], position['lat'], distance, ))
    return results[0][0]
 
def getRejectedBeforeDateWithinDistance(date, position, distance):
    """
    Gets number of rejected wind turbines before 'date' and within 'distance'
    """

    if date == '': return None

    results = postgisGetResults("""
    SELECT COUNT(*) 
    FROM windturbines_all_projects__uk 
    WHERE 
    (project_date_end IS NOT NULL) AND 
    (project_date_end < %s) AND 
    (project_status IN ('Application Refused', 'Appeal Refused', 'Appeal Withdrawn')) AND 
    ST_Distance(ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), 3857), ST_Transform(geom, 3857)) < %s;
    """, (date, position['lng'], position['lat'], distance, ))
    return results[0][0]

def getAverageTipHeight():
    """
    Get average height to tip for all turbines where this is defined
    """

    results = postgisGetResults("SELECT AVG(turbine_tipheight) FROM windturbines_all_projects__uk WHERE turbine_tipheight IS NOT NULL;", ())
    return results[0][0]

def updateMissingTipHeights(tipheight):
    """
    Sets tip height for all turbines where this is undefined
    """

    postgisExec("""
    UPDATE windturbines_all_projects__uk 
    SET turbine_tipheight = %s, 
        project_notes = CONCAT('AVERAGED TIPHEIGHT. ', project_notes) 
    WHERE turbine_tipheight IS NULL;
    """, (tipheight, ))

def getProjectSize(projectid):
    """
    Gets aggregate project size
    Computes sum of all turbine height-to-tips for project - better correlate to capacity + visual impact than quoted capacity figures 
    """

    global PROJECTSIZE_CACHE

    if projectid not in PROJECTSIZE_CACHE:
        results = postgisGetResults("SELECT SUM(turbine_tipheight) FROM windturbines_all_projects__uk WHERE project_guid = %s", (projectid, ))
        PROJECTSIZE_CACHE[projectid] = results[0][0]
    return PROJECTSIZE_CACHE[projectid]

def getPoliticalAverage(year):
    """
    Gets political breakdown of all councils that have data for specific year
    """

    results = postgisGetResultsAsDict("""
    SELECT political.con AS political_con, political.lab AS political_lab, political.ld AS political_ld, political.other AS political_other 
    FROM 
    sitepredictor__political__uk political
    WHERE 
    political.year = %s
    """, (year, ))

    # Compute proportions
    if len(results) != 0:
        for result in results:
            total = int(result['political_con']) + int(result['political_lab']) + int(result['political_ld']) + int(result['political_other'])
            result['political_proportion_con'] = float(result['political_con']) / total
            result['political_proportion_lab'] = float(result['political_lab']) / total
            result['political_proportion_ld'] = float(result['political_ld']) / total
            result['political_proportion_other'] = float(result['political_other']) / total

    return results

def getPolitical(position, year):
    """
    Gets political breakdown of council for geographical position and year
    """

    results = postgisGetResultsAsDict("""
    SELECT political.con AS political_con, political.lab AS political_lab, political.ld AS political_ld, political.other AS political_other 
    FROM 
    sitepredictor__political__uk political,
    sitepredictor__councils__uk area
    WHERE 
    political.year = %s AND
    political.area = area.name AND 
    ST_Intersects(area.geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326));""", (year, position['lng'], position['lat'], ))

    # Compute proportions
    if len(results) != 0:
        for result in results:
            total = int(result['political_con']) + int(result['political_lab']) + int(result['political_ld']) + int(result['political_other'])
            result['political_total'] = total
            result['political_proportion_con'] = float(result['political_con']) / total
            result['political_proportion_lab'] = float(result['political_lab']) / total
            result['political_proportion_ld'] = float(result['political_ld']) / total
            result['political_proportion_other'] = float(result['political_other']) / total
    else:
        return getPoliticalAverage(year)

    return results

def getSpecificCensusSingleGeography(position, category):
    """
    Get specific census data for single geography containing position using category
    """

    census_data_table = 'sitepredictor__census_2011_' + category + '__uk'

    results = postgisGetResultsAsDict("""
    SELECT 
    data.total """ + category + """_total,
    data.* 
    FROM 
    %s data, 
    sitepredictor__census_geography__uk area
    WHERE 
    ST_Intersects(area.geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326)) AND 
    data.geo_code = area.geo_code""", (AsIs(census_data_table), position['lng'], position['lat'], ))

    if len(results) == 0:
        print("Error retrieving census data for", category, position)
        exit()

    if len(results) > 1:
        print("Retrieving more than one record for census data", category, position)
        exit()

    results = results[0]
    delete_fields = ['ogc_fid', 'geo_code', 'date', 'geography', 'total', 'geom']
    for delete_field in delete_fields:
        if delete_field in results: del results[delete_field]
    
    return results

def getSpecificCensusSearchRadius(position, category, radius):
    """
    Gets aggregated census data for all geographies within radius of position using category
    """

    census_data_table = 'sitepredictor__census_2011_' + category + '__uk'

    results = postgisGetResultsAsDict("""
    SELECT 
    data.* 
    FROM 
    %s data, 
    sitepredictor__census_geography__uk area
    WHERE 
    ST_Intersects(area.geom, ST_Buffer(ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s)::geometry) AND 
    data.geo_code = area.geo_code""", (AsIs(census_data_table), position['lng'], position['lat'], radius ))

    if len(results) == 0:
        print("Error retrieving census data for", category, position)
        exit()

    aggregateresults = {}
    delete_fields = ['ogc_fid', 'geo_code', 'date', 'geography', 'geom']
    for result in results:
        for field in result.keys():
            if field in delete_fields: continue
            # As we're summing all values, proportional '__pro' field should be ignored
            if '__pro' in field: continue
            if field not in aggregateresults: aggregateresults[field] = int(result[field])
            else: aggregateresults[field] += int(result[field])

    total = aggregateresults['total']
    del aggregateresults['total']
    aggregateresults[category + '_total'] = total
    finalresults = json.loads(json.dumps(aggregateresults))
    for field in aggregateresults.keys():
        if 'total' in field: continue
        finalresults[field + '__prop'] = aggregateresults[field] / total
    
    return finalresults

def getCensus(position, radius=None, year='2011'):
    """
    Get census data for position
    Note: year not yet implemented - ideally include multiple censuses and use regression to fill gaps
    Currently uses UK 2011 census (all countries)
    England / Wales: LSOA
    Scotland: Data Zones
    Northern Ireland: Small Areas
    """

    categories = ['age', 'occupation', 'qualifications', 'tenure']
    final_fields = {}
    for category in categories:
        if radius is None: census_data = getSpecificCensusSingleGeography(position, category)
        else: census_data = getSpecificCensusSearchRadius(position, category, radius)
        for data_field in census_data.keys():
            if ('total' not in data_field) and ('__prop' not in data_field): continue
            data_field_readable = data_field.replace('__prop', '_proportional')
            final_fields[data_field_readable] = census_data[data_field]

    return final_fields    

def getCountry(position):
    """
    Gets country of turbine using letter prefix of census geographies
    """

    results = postgisGetResults("""
    SELECT geo_code FROM sitepredictor__census_geography__uk WHERE 
    ST_Intersects(geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326))""", (position['lng'], position['lat'], ))
    if len(results) == 0: return None
    geo_code = results[0][0]

    if geo_code.startswith("E"): return 'England'
    if geo_code.startswith("W"): return 'Wales'
    if geo_code.startswith("S"): return 'Scotland'
    if geo_code.startswith("N"): return 'Northern Ireland'
    return None

def getGeometryType(table):
    """
    Gets primary geometry type of table
    """

    global GEOMETRY_TYPES_LOOKUP

    if table not in GEOMETRY_TYPES_LOOKUP: 

        results = postgisGetResultsAsDict("SELECT ST_GeometryType(geom) type, COUNT(*) count FROM %s GROUP BY ST_GeometryType(geom) ORDER BY count DESC;", (AsIs(table), ))
        GEOMETRY_TYPES_LOOKUP[table] = results[0]['type']

    return GEOMETRY_TYPES_LOOKUP[table]

def getOverlapMetrics(source_table, overlay_table):
    """
    Gets overlap between source_table and overlay_table and determines
    total number of points, total length of lines and total area in overlapped area
    """

    scratch_table_3 = '_scratch_table_3'

    if postgisCheckTableExists(scratch_table_3): postgisDropTable(scratch_table_3)

    postgisExec("CREATE TABLE %s AS (SELECT (ST_Dump(ST_Intersection(source.geom, overlay.geom))).geom geom FROM %s source, %s overlay);", \
                (AsIs(scratch_table_3), AsIs(source_table), AsIs(overlay_table), ))
    postgisExec("CREATE INDEX %s ON %s USING GIST (geom);", (AsIs(scratch_table_3 + '_idx'), AsIs(scratch_table_3), ))

    results = postgisGetResultsAsDict("""
    SELECT ST_GeometryType(geom) geometrytype, COUNT(*) number, SUM(ST_Length(geom)) line_length, SUM(ST_Area(geom)) area FROM %s GROUP BY ST_GeometryType(geom);
    """, (AsIs(scratch_table_3), ))

    if postgisCheckTableExists(scratch_table_3): postgisDropTable(scratch_table_3)

    output_results = {
        'number_points': 0,
        'line_length': 0.0,
        'area': 0.0
    }

    for result in results:
        if result['geometrytype'] == 'ST_Point': output_results['number_points'] = result['number']
        # Convert results into km or km2
        if result['geometrytype'] == 'ST_LineString': output_results['line_length'] = result['line_length'] / 1000
        if result['geometrytype'] == 'ST_Polygon': output_results['area'] = result['area'] / 1000000

    return output_results

def filterRelevantViewshedLayers(tables):
    """
    Due to computationally intensive nature of calculating viewshed overlaps, 
    artificially restrict calculations to those layers we a priori think are 
    likely to be relevant
    """

    relevant_layers = [ 'areas_of_outstanding_natural_beauty', \
                        'conservation_areas', \
                        'listed_buildings', \
                        'local_nature_reserves', \
                        'national_nature_reserves', \
                        'national_parks', \
                        'registered_historic_battlefields', \
                        'registered_parks_and_gardens', \
                        'scheduled_ancient_monuments', \
                        'separation_distance_from_residential', \
                        'special_areas_of_conservation', \
                        'wild_land_areas', \
                        'windturbines_operational', \
                        'world heritage sites' ]

    output_tables = []
    for table in tables:
        for relevant_layer in relevant_layers:
            if relevant_layer in table: 
                output_tables.append(table)
                continue
    
    return output_tables

def getViewshedOverlaps(position, height, categories):
    """
    Gets visibility viewshed overlap of position for every category
    """

    global VIEWSHED_RADIUS

    # Artificially limit categories to save time 
    # Not ideal... ideally you run things for every layer
    # without judging in advance which might be relevant

    categories = filterRelevantViewshedLayers(categories)

    # In some cases, we have mix of geometries and need to homogenise how
    # we count any overlap. For example listed buildings are polygons in England
    # but points in Scotland so if we judge source table by most numerous 
    # geometry type, we will discount less numerous - but still crucial - geometries
    # Therefore:
    # - Listed building points given 50 metre radius circle

    specialcases = {
        'listed_buildings__uk__pro__3857': {
            'multiply_number_points_by_area': 3.14 * 50 * 50
        }
    }

    scratch_table_1 = '_scratch_table_1'
    scratch_table_2 = '_scratch_table_2'

    viewshed_geojson = getViewshed(position, height)

    if postgisCheckTableExists(scratch_table_1): postgisDropTable(scratch_table_1)
    if postgisCheckTableExists(scratch_table_2): postgisDropTable(scratch_table_2)

    postgisExec("CREATE TABLE %s (geom geometry)", (AsIs(scratch_table_1), ))
    postgisExec("CREATE INDEX %s ON %s USING GIST (geom);", (AsIs(scratch_table_1 + '_idx'), AsIs(scratch_table_1), ))

    for feature in viewshed_geojson['features']:
        postgisExec("INSERT INTO %s VALUES (ST_Transform(ST_GeomFromGeoJSON(%s), 3857))", (AsIs(scratch_table_1), json.dumps(feature['geometry']), ))

    postgisExec("CREATE TABLE %s AS SELECT ST_Union(geom) geom FROM %s;", (AsIs(scratch_table_2), AsIs(scratch_table_1), ))
    postgisExec("CREATE INDEX %s ON %s USING GIST (geom);", (AsIs(scratch_table_2 + '_idx'), AsIs(scratch_table_2), ))

    overlap_values = {}

    results = postgisGetResults("SELECT SUM(ST_Area(geom)) FROM %s;", (AsIs(scratch_table_1), ))
    overlap_values["viewshed_" + str(int(VIEWSHED_RADIUS / 1000)) + "km_radius_total_area_km2"] = results[0][0] / 1000000

    for category in categories:
        geometrytype = getGeometryType(category)
        overlapmetrics = getOverlapMetrics(category, scratch_table_2)
        parametername, finalvalue = None, None

        if category in specialcases:
            rule = specialcases[category]
            if 'multiply_number_points_by_area' in rule:
                parametername = 'area'
                additional_area = rule['multiply_number_points_by_area'] * overlapmetrics['number_points']
                finalvalue = additional_area + overlapmetrics['area']
        else:
            if geometrytype == 'ST_Point': 
                parametername = 'number_points'
                finalvalue = overlapmetrics['number_points']
            if geometrytype == 'ST_LineString': 
                parametername = 'line_length'                
                finalvalue = overlapmetrics['line_length']
            if geometrytype == 'ST_Polygon': 
                parametername = 'area'
                finalvalue = overlapmetrics['area']

        if finalvalue is not None:
            readable_category = category.replace('__uk__pro__3857', '')
            overlap_values[readable_category + "_viewshed_" + str(int(VIEWSHED_RADIUS / 1000)) + 'km_radius_' + parametername] = finalvalue

    if postgisCheckTableExists(scratch_table_1): postgisDropTable(scratch_table_1)
    if postgisCheckTableExists(scratch_table_2): postgisDropTable(scratch_table_2)

    return overlap_values

def getAllProjectNames():
    """
    Gets all project names ordered alphabetically
    """

    results = postgisGetResults("SELECT DISTINCT project_name FROM windturbines_all_projects__uk ORDER BY project_name;", ())
    names = []
    for result in results:
        name = result[0].strip()
        if 'wind ' not in (name.lower() + ' '): name += ' Wind Farm'
        names.append(name)

    return names

def createDistanceCache(tables):
    """
    Runs efficient PostGIS queries across entire dataset to save time
    """

    global DISTANCE_CACHE_TABLE

    if not postgisCheckTableExists(DISTANCE_CACHE_TABLE):
        postgisExec("CREATE TABLE %s (ogc_fid INTEGER, table_name VARCHAR(70), distance DOUBLE PRECISION)", (AsIs(DISTANCE_CACHE_TABLE), ))
        postgisExec("CREATE INDEX ON %s (ogc_fid)", (AsIs(DISTANCE_CACHE_TABLE), ))
        postgisExec("CREATE INDEX ON %s (table_name)", (AsIs(DISTANCE_CACHE_TABLE), ))

    number_turbines = postgisGetResults("SELECT COUNT(*) FROM windturbines_all_projects__uk;")
    number_turbines = number_turbines[0][0]

    for table in tables:
        number_cached_records = postgisGetResults("SELECT COUNT(*) FROM %s WHERE table_name = %s", (AsIs(DISTANCE_CACHE_TABLE), table, ))
        number_cached_records = number_cached_records[0][0]
        if number_cached_records != number_turbines:
            LogMessage("Creating bulk point-to-feature distance cache for table: " + table)
            postgisExec("DELETE FROM %s WHERE table_name = %s", (AsIs(DISTANCE_CACHE_TABLE), table, ))

            LogMessage("Caching for points where distance >= 0")

            postgisExec("""
            INSERT INTO %s 
            SELECT turbine.ogc_fid, %s AS table_name, MIN(ST_Distance(ST_Transform(turbine.geom, 3857), dataset.geom)) AS distance 
            FROM windturbines_all_projects__uk turbine, %s dataset GROUP BY turbine.ogc_fid
            """, (AsIs(DISTANCE_CACHE_TABLE), table, AsIs(table), ))

            LogMessage("Caching for points where inside feature - distance < 0")

            postgisExec("""
            UPDATE %s cache SET distance = 
            (
                SELECT -MIN(ST_Distance(ST_Transform(turbine.geom, 3857), ST_ExteriorRing(dataset.geom))) FROM 
                windturbines_all_projects__uk turbine, %s dataset
                WHERE turbine.ogc_fid = cache.ogc_fid AND ST_Contains(dataset.geom, ST_Transform(turbine.geom, 3857))
            )
            WHERE 
            cache.distance = 0 AND cache.table_name = %s;
            """, (AsIs(DISTANCE_CACHE_TABLE), AsIs(table), table, ))

def createSamplingGrid():
    """
    Creates sampling grid for use in building final result maps
    """

    global SAMPLING_DISTANCE, SAMPLING_GRID, SAMPLING_GRID_DISTANCES

    if not postgisCheckTableExists(SAMPLING_GRID):

        LogMessage("Creating sampling grid with points spaced at " + str(SAMPLING_DISTANCE) + " metres")

        postgisExec("CREATE TABLE %s AS SELECT (ST_PixelAsCentroids(ST_AsRaster(ST_Transform(geom, 3857), %s, %s))).geom FROM uk_clipping__union;", \
                    (AsIs(SAMPLING_GRID), AsIs(SAMPLING_DISTANCE), AsIs(SAMPLING_DISTANCE), ))
        postgisExec("ALTER TABLE %s ADD COLUMN id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY;", (AsIs(SAMPLING_GRID), ))

def computeSamplingGridDistances(tables):
    """
    Computes distances for all points in sampling grid for each table of features in list of tables
    """

    global SAMPLING_GRID, SAMPLING_GRID_DISTANCES

    if not postgisCheckTableExists(SAMPLING_GRID_DISTANCES):
        postgisExec("CREATE TABLE %s (point_id INTEGER, table_name VARCHAR(70), distance DOUBLE PRECISION);", (AsIs(SAMPLING_GRID_DISTANCES), ))
        postgisExec("CREATE INDEX ON %s (point_id)", (AsIs(SAMPLING_GRID_DISTANCES), ))
        postgisExec("CREATE INDEX ON %s (table_name)", (AsIs(SAMPLING_GRID_DISTANCES), ))

        for table in tables:

            LogMessage("Creating bulk point-to-feature distance cache for table: " + table)
            postgisExec("DELETE FROM %s WHERE table_name = %s", (AsIs(SAMPLING_GRID_DISTANCES), table, ))

            LogMessage("Caching for points where distance >= 0")

            postgisExec("""
            INSERT INTO %s 
            SELECT samplinggrid.id AS point_id, %s AS table_name, MIN(ST_Distance(ST_Transform(samplinggrid.geom, 3857), dataset.geom)) AS distance 
            FROM %s samplinggrid, %s dataset GROUP BY samplinggrid.id
            """, (AsIs(SAMPLING_GRID_DISTANCES), table, AsIs(SAMPLING_GRID), AsIs(table), ))

            LogMessage("Caching for points where inside feature - distance < 0")

            postgisExec("""
            UPDATE %s cache SET distance = 
            (
                SELECT -MIN(ST_Distance(ST_Transform(samplinggrid.geom, 3857), ST_ExteriorRing(dataset.geom))) FROM 
                %s samplinggrid, %s dataset
                WHERE samplinggrid.id = cache.point_id AND ST_Contains(dataset.geom, ST_Transform(samplinggrid.geom, 3857))
            )
            WHERE 
            cache.distance = 0 AND cache.table_name = %s;
            """, (AsIs(SAMPLING_GRID_DISTANCES), AsIs(SAMPLING_GRID), AsIs(table), table, ))

def runAdditionalDownloads():
    """
    Carry out any additional downloads
    """

    global ADDITIONAL_DOWNLOADS, DATASETS_FOLDER

    possible_extensions_unzipped = ['shp', 'geojson', 'gpkg']
    for additional_download in ADDITIONAL_DOWNLOADS:
        dataset = additional_download['dataset']
        file_extension = additional_download['extension']
        additional_download_path = DATASETS_FOLDER + dataset + '.' + file_extension
        additional_download_directory = DATASETS_FOLDER + dataset + '/'
        additional_download_table = reformatTableName(dataset)
        if 'url' in additional_download:
            if  ((file_extension != 'zip') and (not isfile(additional_download_path))) or \
                ((file_extension == 'zip') and (not isdir(additional_download_directory))):
                LogMessage("Downloading: " + dataset)
                attemptDownloadUntilSuccess(additional_download['url'], additional_download_path)

        if (file_extension == 'zip') and (not isdir(additional_download_directory)):
            LogMessage("Unzipping: " + dataset)
            with ZipFile(additional_download_path, 'r') as zip_ref: zip_ref.extractall(additional_download_directory)
            os.remove(additional_download_path)

        if not postgisCheckTableExists(additional_download_table):

            srs = 'EPSG:4326'
            if 'srs' in additional_download: srs = additional_download['srs']
            if file_extension == 'zip':
                unzipped_files = getFilesInFolder(additional_download_directory)
                for unzipped_file in unzipped_files:
                    unzipped_file_extension = unzipped_file.split('.')[1]
                    if unzipped_file_extension in possible_extensions_unzipped:
                        additional_download_path = DATASETS_FOLDER + dataset + '/' + unzipped_file
                        break

            # Harmonize field names in CSV files - needed for Census data that has long field names
            if file_extension == 'csv': processCSVFile(additional_download_path)

            postgisImportDatasetGIS(additional_download_path, additional_download_table, srs)
            postgisAddProportionalFields(additional_download_table)

            if 'sql' not in additional_download: continue
            if additional_download['sql'] is None: continue
            if len(additional_download['sql']) == 0: continue

            for sql in additional_download['sql']: postgisExec(sql)
    
    local_authority_canonical = getJSON('local_authority_canonical.json')
    for conversion_from in local_authority_canonical.keys():
        conversion_to = local_authority_canonical[conversion_from]
        postgisExec('UPDATE sitepredictor__political__uk SET area = %s WHERE area = %s', (conversion_to, conversion_from, ))


def runSitePredictor():
    """
    Runs entire site predictor pipeline
    """

    global CENSUS_SEARCH_RADIUS

    # Download all necessary OSM data
    osmDownloadData()

    # Download wind speed data
    downloadWindSpeeds()

    # Perform additional downloads
    runAdditionalDownloads()

    # Generate historical footpaths to account for turbine-created footpaths creating misleading data
    # generateHistoricalFootpaths()

    # Import all failed and successful project
    importAllWindProjects()

    # Amalgamate any location-specific tables that don't cover whole of UK
    amalgamateNonUKtables()

    # Get list of tables to run distance testing on    
    tables_to_test_unprojected = removeNonEssentialTablesForDistance(postgisGetUKBasicProcessedTables())

    # Creates reprojected version of all testing tables to improve performance
    tables_to_test = []
    for table in tables_to_test_unprojected:
        tables_to_test.append(createTransformedTable(table))

    tables_to_test = removeNonEssentialTablesForDistance(tables_to_test)

    # Create distance-to-turbine cache
    createDistanceCache(tables_to_test)

    # Create sampling grid - ie. grid of 1km spaced points - and sampling points cache
    # This cache saves time once we have ML algorithm working as we don't know in advance 
    # of ML work how important or irrelevant distances to features are
    # Therefore compute in advance / in background just to be safe

    createSamplingGrid()
    # computeSamplingGridDistances(tables_to_test)

    # Get all failed and successful project names
    all_projectnames = getAllProjectNames()

    # Get all failed and successful wind turbines
    all_turbines = getAllWindProjects()

    # exit()

    outputdata = 'finaldata.csv'
    if isfile(outputdata): os.remove(outputdata)

    # turbine_position = {'lng':0.1405, 'lat': 50.83516}

    index, firstrowwritten, totalrecords, fieldnames = 0, False, len(all_turbines), None
    distance_ranges = [10, 20, 30, 40]
    updateMissingTipHeights(getAverageTipHeight())

    for turbine in all_turbines:

        # if index < 91: 
        #     index += 1
        #     continue
        LogMessage("Processing turbine: " + str(index + 1) + "/" + str(totalrecords))

        # Convert dates to text 
        # Note: import creates date type fields unprompted
        if turbine['project_date_operational'] is not None:
            turbine['project_date_operational'] = turbine['project_date_operational'].strftime('%Y-%m-%d')
        if turbine['project_date_underconstruction'] is not None:
            turbine['project_date_underconstruction'] = turbine['project_date_underconstruction'].strftime('%Y-%m-%d')
        if turbine['project_date_start'] is None: turbine['project_year'] = None
        else: turbine['project_year'] = turbine['project_date_start'][0:4]

        # Improve ordering of fields
        turbine_lnglat = {'lng': turbine['lng'], 'lat': turbine['lat']}
        turbine['turbine_country'] = getCountry(turbine_lnglat)
        turbine['turbine_elevation'] = getElevation(turbine_lnglat)[0]
        turbine['turbine_grid_coordinates_srs'] = turbine['turbine_srs']
        turbine['turbine_grid_coordinates_easting'] = turbine['turbine_easting']
        turbine['turbine_grid_coordinates_northing'] = turbine['turbine_northing']
        turbine['turbine_lnglat_lng'] = turbine['lng']
        turbine['turbine_lnglat_lat'] = turbine['lat']
        del turbine['lng']
        del turbine['lat']
        del turbine['turbine_srs']
        del turbine['turbine_easting']
        del turbine['turbine_northing']
        del turbine['geom']

        turbine['windspeed'] = getWindSpeed(turbine_lnglat)
        turbine['project_size'] = getProjectSize(turbine['project_guid'])

        # Get viewshed visibility overlaps for (subset of) layers
        # *** Currently selects subset of layers using filterRelevantViewshedLayers() 
        # *** to save computation time but this is not ideal
        # *** Ideally optimise computation and run on all layers 
        # *** in order to avoid prejudging which might be salient

        viewshedoverlaps = getViewshedOverlaps(turbine_lnglat, turbine['turbine_tipheight'], tables_to_test)
        for viewshedoverlaps_key in viewshedoverlaps.keys(): turbine[viewshedoverlaps_key] = viewshedoverlaps[viewshedoverlaps_key]

        # Get demographics for a number of radius circles
        for census_radius in [10, 20, 30, 40]:        
            census = getCensus(turbine_lnglat, census_radius * 1000)
            for census_key in census.keys(): turbine[str(census_radius) + 'km_' + census_key] = census[census_key]

        political = [{
            'political_con': None,
            'political_lab': None,
            'political_ld': None,
            'political_other': None,
            'political_total': None,
            'political_proportion_con': None,
            'political_proportion_lab': None,
            'political_proportion_ld': None,
            'political_proportion_other': None,
        }]

        if (turbine['project_date_start'] is not None) and (turbine['project_date_start'] != ''):
            year = turbine['project_date_start'][0:4]
            political = getPolitical(turbine_lnglat, year)

        for political_key in political[0].keys(): turbine[political_key] = political[0][political_key]

        for distance_range in distance_ranges:
            turbine['count__operational_within_' + str(distance_range)+'km']    = getOperationalBeforeDateWithinDistance(turbine['project_date_start'], turbine_lnglat, 1000 * distance_range)
            turbine['count__approved_within_' + str(distance_range)+'km']       = getApprovedBeforeDateWithinDistance(turbine['project_date_start'], turbine_lnglat, 1000 * distance_range)
            turbine['count__applied_within_' + str(distance_range)+'km']        = getAppliedBeforeDateWithinDistance(turbine['project_date_start'], turbine_lnglat, 1000 * distance_range)
            turbine['count__rejected_within_' + str(distance_range)+'km']       = getRejectedBeforeDateWithinDistance(turbine['project_date_start'], turbine_lnglat, 1000 * distance_range)

        for table_to_test in tables_to_test:
            distance = postgisDistanceToNearestFeature(turbine['ogc_fid'], table_to_test)
            # Remove internal table suffixes to improve readability
            table_to_test = table_to_test.replace('__pro__3857', '')
            # We don't need more precision than 1 metre
            if distance is None:
                print("Distance is NONE:", table_to_test)
                turbine['distance__' + table_to_test] = 10000000
            else:
                turbine['distance__' + table_to_test] = int(distance)

        if not firstrowwritten:
            with open(outputdata, 'w', newline='') as csvfile:
                fieldnames = turbine.keys()
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
            firstrowwritten = True

        with open(outputdata, 'a', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writerow(turbine)

        index += 1


runSitePredictor()

