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
import csv
import json
# import geojson
import pyproj
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
import rasterio
import h2o
import pandas as pd
import numpy as np
import geopandas as gpd
import multiprocessing
import hashlib
import glob
from h2o.estimators.deeplearning import H2ODeepLearningEstimator
from multiprocessing import Pool, Value
from rasterio.transform import from_origin
from datetime import datetime
from pathlib import Path
from psycopg2 import sql
from psycopg2.extensions import AsIs
from zipfile import ZipFile
from os import listdir, makedirs
from os.path import isfile, isdir, basename, join, exists
from dotenv import load_dotenv
from osgeo import gdal, osr, ogr
from h2o.automl import H2OAutoML
from h2o.model.regression import h2o_mean_squared_error

pd.options.plotting.backend = "plotly"

gdal.DontUseExceptions()

if not isfile('../.env-sitepredictor'): shutil.copy('../.env', '../.env-sitepredictor')

# load_dotenv('../.env')
load_dotenv('../.env-sitepredictor')

WORKING_FOLDER                      = str(Path(__file__).absolute().parent) + '/'
DATASETS_FOLDER                     = WORKING_FOLDER + 'datasets/'
OUTPUT_FOLDER                       = WORKING_FOLDER + 'output/'
CLIPPING_FOLDER                     = WORKING_FOLDER + 'clipping/'
OSM_MAIN_DOWNLOAD                   = 'https://download.geofabrik.de/europe/united-kingdom-latest.osm.pbf'
OSM_CONFIG_FOLDER                   = 'osm-export-yml/'
OSM_EXPORT_DATA                     = DATASETS_FOLDER + 'osm-export'
DTM_GEOTIFF_URL                     = 'https://openwindenergy.s3.us-east-1.amazonaws.com/terrain_lowres_withfeatures.tif'
WINDSPEED_URL                       = 'https://openwindenergy.s3.us-east-1.amazonaws.com/windspeeds-noabl--uk.geojson.zip'
WINDSPEED_DATASET                   = 'windspeeds-noabl--uk'
CUSTOM_CONFIGURATION_PREFIX         = '__'
CENSUS_2011_ZIP_URL                 = 'https://data.openwind.energy/dataset/6b00ae5f-850c-4c1d-9b65-e2a78715b85e/resource/73141902-5898-4124-90cb-40c6b5ea8059/download/sitepredictor-census-2011.zip'
WINDTURBINES_ALLPROJECTS_URL        = 'https://data.openwind.energy/dataset/308b0001-8c70-4a64-adb3-068a94c775c4/resource/2b325fd4-dad2-4e62-8d7b-7a87c339a501/download/windturbines-all-projects-uk.geojson'
WINDTURBINES_ALLPROJECTS_DATASET    = basename(WINDTURBINES_ALLPROJECTS_URL).replace('.geojson', '').replace('-uk', '--uk')
WINDTURBINES_OPERATIONAL_DATASET    = 'windturbines-operational--uk'
WINDTURBINES_MIN_HEIGHTTIP          = 75 # Minimum height to tip in metres for including failed + successful wind turbines in analysis
FOOTPATHS_SINGLELINES_DATASET       = 'public-footpaths--uk'
FOOTPATHS_HISTORICAL_DATASET        = FOOTPATHS_SINGLELINES_DATASET + '--hist'
MINORROADS_SINGLELINES_DATASET      = 'minor_roads__uk'
MINORROADS_HISTORICAL_DATASET       = MINORROADS_SINGLELINES_DATASET + '--hist'
POSTGRES_HOST                       = os.environ.get("POSTGRES_HOST")
POSTGRES_DB                         = os.environ.get("POSTGRES_DB")
POSTGRES_USER                       = os.environ.get("POSTGRES_USER")
POSTGRES_PASSWORD                   = os.environ.get("POSTGRES_PASSWORD")
OVERALL_CLIPPING_FILE               = 'overall-clipping.geojson'
CLIPPING_PATH                       = '../overall-clipping.gpkg'
TURFPY_OPTIONS                      = {'units': 'm'}
PROJECTSIZE_CACHE                   = {}
SEARCHAREA_BUFFER_CACHE             = {}
CENSUS_SEARCH_RADIUS                = 10000
TERRAIN_FILE                        = WORKING_FOLDER + 'terrain_lowres_withfeatures.tif'
DISTANCE_CACHE_TABLE                = 'sitepredictor__distance_cache'
DISTANCE_CACHE_VALUES               = {}
VIEWSHED_RADIUS                     = 20000
GEOMETRY_TYPES_LOOKUP               = {}
TRANSFORMER_FROM_29903              = None
TRANSFORMER_FROM_27700              = None
TRANSFORMER_SOURCE_4326             = None
TRANSFORMER_DEST_27700              = None
TRANSFORMER_TO_27700                = None
RASTER_RESOLUTION                   = 1000 # Number of metres per raster grid square
RASTER_XMIN                         = 0
RASTER_YMIN                         = 7250
RASTER_XMAX                         = 664000
RASTER_YMAX                         = 1296000
# DEFAULT_BATCH_GRID_SPACING          = 50000
DEFAULT_BATCH_GRID_SPACING          = 400000
SAMPLING_GRID                       = "sitepredictor__sampling"
BATCH_SAMPLING_GRID                 = "sitepredictor__batch_points"
TEST_SAMPLING_GRID_SIZE             = 16000
QUIET_MODE                          = True
RASTER_OUTPUT_FOLDER                = WORKING_FOLDER + "rasters/"
if os.environ.get("RASTER_OUTPUT_FOLDER") is not None: RASTER_OUTPUT_FOLDER = os.environ.get("RASTER_OUTPUT_FOLDER")
GEOCODE_POSITION_LOOKUP             = {}
COUNCIL_POSITION_LOOKUP             = {}
CENSUS_CACHE                        = {}
POLITICAL_CACHE                     = {}
WINDSPEED_CACHE                     = {}
OUTPUT_DATA_ALLTURBINES             = OUTPUT_FOLDER + 'output-turbines.csv'
OUTPUT_DATA_SAMPLEGRID              = OUTPUT_FOLDER + 'output-samplegrid.csv'
OUTPUT_ML_GEOJSON                   = OUTPUT_FOLDER + 'output-machinelearning.geojson'
OUTPUT_ML_CSV                       = OUTPUT_FOLDER + 'output-machinelearning.csv'
OUTPUT_ML_RASTER                    = OUTPUT_FOLDER + 'output-machinelearning.tif'
ML_FOLDER                           = WORKING_FOLDER + "machinelearning/"
PASSES_FOLDER                       = WORKING_FOLDER + "passes/"
# ML_MAX_RUNTIME_SECS                 = 5*60
ML_MAX_RUNTIME_SECS                 = 30*60
ML_MAX_MODELS                       = 20
# ML_MAX_MODELS                       = 3
ML_STATUS_SUCCESS                   = ['Operational', 'Awaiting Construction', 'Under Construction', 'Decommissioned', 'Planning Permission Expired']
ML_STATUS_FAILURE                   = ['Application Refused', 'Abandoned', 'Appeal Withdrawn', 'Application Withdrawn', 'Appeal Refused']
ML_STATUS_PENDING                   = ['Revised', 'Application Submitted', 'Appeal Lodged', 'No Application Required']
ALLTURBINES_DF                      = None
ALLTURBINES_GDF                     = None
CKAN_USER_AGENT                     = 'ckanapi/1.0 (+https://openwind.energy)'
LOG_SINGLE_PASS                     = WORKING_FOLDER + '../log.txt'
TEST_POINT                          = {'lng': 0, 'lat': 51} # In --test, use only one sample grid square containing TEST_POINT
MAX_RANDOM_STDDEV                   = 0.2887
NODATA_VALUE                        = -9999

# We try and include as many columns as possible to ML
# but there are some columns that are clearly irrelevant to prediction

ML_IGNORE_COLUMNS                   = [
                                        'ogc_fid','planningapplication_guid','planningapplication_urls','project_address','project_guid',\
                                        'project_name','project_notes','project_osm','project_pk','source','turbine_bladeradius','turbine_hubheight',\
                                        'turbine_name','turbine_grid_coordinates_srs','turbine_grid_coordinates_easting','turbine_grid_coordinates_northing',\
                                        'turbine_lnglat_lng','turbine_lnglat_lat', 'project_operator',\
                                        'political_majority',\
                                        'project_date_start', 'project_date_end', 'project_date_operational', 'project_date_underconstruction', \
                                    ]

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
                                                'sql': ['CREATE TABLE sitepredictor__political__uk AS SELECT authority area, year, total, con, lab, ld, other, nat, majority FROM sitepredictor__local_authority_party_composition_1973_2015',
                                                        'CREATE INDEX ON sitepredictor__political__uk (area)',
                                                        'CREATE INDEX ON sitepredictor__political__uk (year)',
                                                        "INSERT INTO sitepredictor__political__uk SELECT 'South Lanarkshire', year, SUM(total::int), SUM(con::int), SUM(lab::int), SUM(ld::int), SUM(other::int), SUM(nat::int), '-' FROM sitepredictor__political__uk WHERE area IN ('Clydesdale', 'Hamilton', 'East Kilbride') GROUP BY year;"]
                                            },
                                            {
                                                'dataset': 'sitepredictor--local-authority-party-composition-2016-2024',
                                                'url': 'https://opencouncildata.co.uk/history2016-2024.csv',
                                                'extension': 'csv',
                                                'sql': ['INSERT INTO sitepredictor__political__uk SELECT authority area, year, total, con, lab, ld, (green::int + other::int) other, (pc::int + snp::int) nat, majority other FROM sitepredictor__local_authority_party_composition_2016_2024']
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
LOCALAUTHORITY_CONVERSIONS          = 'local_authority_canonical.json'
TABLES_TO_EXCLUDE                   =   [ \
                                            SAMPLING_GRID, \
                                            'uk__output_grid__100000_m', \
                                            WINDSPEED_DATASET.replace('-', '_'),                    # We don't care about distance on this dataset \
                                            WINDTURBINES_OPERATIONAL_DATASET.replace('-', '_'),     # We are running query off wind turbines so ignore wind turbine datasets \
                                            WINDTURBINES_ALLPROJECTS_DATASET.replace('-', '_'),     # We are running query off wind turbines so ignore wind turbine datasets \
                                            'public_roads_a_and_b_roads_and_motorways__uk__pro',    # osm-export-tool divides out components \
                                            'power_lines__uk__pro',                                 # osm-export-tool divides out components \
                                        ]

# ***********************************************************
# Parameters that specify how close footpath/service-road
# needs to be to turbines to count as 'turbine-caused'
# footpath/service-road.
# All parameters are in metres
# ***********************************************************

# Maximum distance between start/end of footpath/service-road
# and turbine to count as turbine-created footpath/service-road
# ie. if a footpath or service road starts or eventually
# leads to a turbine within 100 metres, then => turbine-created
# footpath/service-road. In contrat to MAXIMUM_DISTANCE_LINE,
# below, this is unlikely to distort ML results in trivial way

MAXIMUM_DISTANCE_ENDPOINT           = 100

# Maxiumum distance between point along line and turbine to
# count as turbine-created footpath/service-road
# ie. if footpath comes within 50 metres of turbine along
# its stretch, then => turbine-created footpath/service-road
# NOTE: 50 metres is typical turbine micrositing distance
# ******************* WARNING ***************************
# This will mean there is likely to be minimum 50 metre
# buffer around footpaths and service roads in final ML
# as we're eliminating any footpaths/service-roads < 50m
# However, this is better than distorting results with
# footpaths and service roads that weren't there before
# construction - which will result in 'being close to
# footpaths/service-roads' significantly increasing
# P(SUCCESS) - because almost all successful projects
# have access footpaths/service-roads.
# *******************************************************

MAXIMUM_DISTANCE_LINE               = 50

# ***********************************************************
# ***************** General helper functions ****************
# ***********************************************************

def hash_dataframe(df: pd.DataFrame) -> str:
    """
    Create a reproducible hash of a DataFrame, including row order and content.
    """

    df_bytes = pd.util.hash_pandas_object(df, index=True).values.tobytes()
    return hashlib.sha256(df_bytes).hexdigest()

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

def init_globals(counter):
    """
    Used as counter across multiprocessing threads
    """

    global cnt
    cnt = counter

def init_counter_total_globals(counter, totalnum):
    """
    Used as counter across multiprocessing threads
    """

    global cnt, total
    cnt = counter
    total = totalnum

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

def LogMissingData(logtext):
    """
    Logs missing data message - easy to switch on and off here
    """

    # LogMessage(logstage)

def LogStage(logstage):
    """
    Logs stage for debugging purposes - easy to switch on and off here
    """

    # LogMessage(logstage)

def LogMessage(logtext):
    """
    Logs message to console with timestamp
    """

    logger = multiprocessing.get_logger()
    logging.info(logtext)

def LogError(logtext):
    """
    Logs error message to console with timestamp
    """

    logger = multiprocessing.get_logger()
    logging.error("*** ERROR *** " + logtext)

def attemptDownloadUntilSuccess(url, file_path):
    """
    Keeps attempting download until successful
    """

    global CKAN_USER_AGENT

    opener = urllib.request.build_opener()
    opener.addheaders = [('User-agent', CKAN_USER_AGENT)]
    urllib.request.install_opener(opener)

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

    global QUIET_MODE

    if QUIET_MODE:
        if subprocess_array[0] in ['gdal_proximity.py', 'gdalwarp', 'gdal_rasterize']: subprocess_array.append('-q')
        if subprocess_array[0] in ['gdal_create', 'gdal_calc.py']: subprocess_array.append('--quiet')

    output = subprocess.run(subprocess_array)

    # print("\n" + " ".join(subprocess_array) + "\n")

    if output.returncode != 0:
        LogError("subprocess.run failed with error code: " + str(output.returncode) + '\n' + " ".join(subprocess_array))
        exit()
    return " ".join(subprocess_array)

def getGPKGProjection(file_path):
    """
    Gets projection in GPKG
    """

    if isfile(file_path):
        try:
            with sqlite3.connect(file_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("select a.srs_id from gpkg_contents as a;")
                result = cursor.fetchall()
                if len(result) == 0:
                    LogMessage(file_path + " has no layers - deleting and quitting")
                    os.remove(file_path)
                    return None
                else:
                    firstrow = result[0]
                    return 'EPSG:' + str(dict(firstrow)['srs_id'])
        except:
            LogMessage("Problem retrieving projection, possible corrupted download: " + basename(file_path))
            os.remove(file_path)
            return None

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

def createFeaturesRaster(raster_resolution, table, output):
    """
    Creates basic raster of features
    """

    global RASTER_XMIN, RASTER_YMIN, RASTER_XMAX, RASTER_YMAX
    global POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD

    LogMessage("Creating features raster from: " + table)

    if isfile(output): os.remove(output)

    sql = "SELECT ST_Transform(geom, 27700) FROM " + table

    if 'listed_buildings' in table:
        sql = "SELECT ST_Transform(ST_Centroid(geom), 27700) FROM " + table + " WHERE ST_geometrytype(geom) = 'ST_Polygon' UNION SELECT ST_Transform(geom, 27700) FROM " + table + " WHERE ST_geometrytype(geom) = 'ST_Point'"

    runSubprocess([ "gdal_rasterize", \
                    "-burn", "1", \
                    "-tr", str(raster_resolution), str(raster_resolution), \
                    "-te", str(RASTER_XMIN), str(RASTER_YMIN), str(RASTER_XMAX), str(RASTER_YMAX), \
                    "-a_nodata", "-9999", \
                    "-ot", "Float64", \
                    "-of", "GTiff", \
                    'PG:host=' + POSTGRES_HOST + ' user=' + POSTGRES_USER + ' password=' + POSTGRES_PASSWORD + ' dbname=' + POSTGRES_DB, \
                    "-sql", sql, \
                    output])

def cropRaster(input, output):
    """
    Crops raster to clipping path
    """

    global CLIPPING_PATH

    LogMessage("Cropping: " + output)

    if isfile(output): os.remove(output)

    runSubprocess([ "gdalwarp", \
                    "-of", "GTiff", \
                    "-cutline", CLIPPING_PATH, \
                    "-dstnodata", "-9999", \
                    "-crop_to_cutline", input, \
                    output ])

def getDistanceRasterPath(raster_resolution, table):
    """
    Gets path of distance raster from table
    """

    global RASTER_OUTPUT_FOLDER

    table = table.replace('__27700', '__27700')

    return RASTER_OUTPUT_FOLDER + 'distance__' + str(raster_resolution) + '_m_resolution__' + table + '.tif'


def createDistanceRaster(raster_resolution, input, output, batch_index, batch_grid_spacing):
    """
    Creates distance raster from feature raster
    """

    global POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
    global CLIPPING_PATH, RASTER_OUTPUT_FOLDER

    if not isfile(output):

        inverted_file = input.replace('.tif', '__inverted.tif')

        LogMessage("Creating inversion of original feature: " + basename(inverted_file))

        runSubprocess([ "gdal_calc.py", \
                        "-A", input, \
                        "--outfile=" + inverted_file, \
                        '--calc="(1*(A==-9999))+(-9999*(A==1))"', \
                        "--hideNoData", \
                        "--NoDataValue=-9999"])

        original_distance_file = RASTER_OUTPUT_FOLDER + basename(input).replace('.tif', '') + '__distance.tif'
        inverted_distance_file = RASTER_OUTPUT_FOLDER + basename(inverted_file).replace('.tif', '') + '__distance.tif'

        if isfile(original_distance_file): os.remove(original_distance_file)
        if isfile(inverted_distance_file): os.remove(inverted_distance_file)

        LogMessage("Creating distance raster from: " + basename(input))

        runSubprocess([ "gdal_proximity.py", \
                        input, original_distance_file, \
                        "-values", "1", \
                        "-distunits", "GEO"])

        if isfile(input): os.remove(input)

        LogMessage("Creating distance raster from: " + basename(inverted_file))

        runSubprocess([ "gdal_proximity.py", \
                        inverted_file, inverted_distance_file, \
                        "-values", "1", \
                        "-distunits", "GEO"])

        if isfile(inverted_file): os.remove(inverted_file)

        LogMessage("Creating composite distance raster from: " + basename(original_distance_file) + ' + ' + basename(inverted_distance_file))

        runSubprocess([ "gdal_calc.py", \
                        "-A", original_distance_file, \
                        "-B", inverted_distance_file, \
                        "--outfile=" + output, \
                        '--calc="(A-B)"', \
                        "--NoDataValue=-9999"])

        if isfile(original_distance_file): os.remove(original_distance_file)
        if isfile(inverted_distance_file): os.remove(inverted_distance_file)

    # If processing batches, clip core distance raster to batch cell and save as batch-specific raster
    if batch_index is not None:

        batch_output = buildBatchRasterFilename(raster_resolution, output, batch_index, batch_grid_spacing)
        batch_clipping = buildBatchRasterClippingFilename(batch_index, batch_grid_spacing)

        if not isfile(batch_clipping):
            LogMessage("Exporting batch clipping path at: " + batch_clipping)

            batch_cell_table = buildBatchCellTableName(batch_index, batch_grid_spacing)

            runSubprocess([ "ogr2ogr", \
                            "-f", "GeoJSON", \
                            batch_clipping, \
                            'PG:host=' + POSTGRES_HOST + ' user=' + POSTGRES_USER + ' password=' + POSTGRES_PASSWORD + ' dbname=' + POSTGRES_DB, \
                            "-dialect", "sqlite", \
                            "-sql", \
                            "SELECT ST_Buffer(geom, " + str(raster_resolution) + ") geometry FROM " + batch_cell_table, \
                            "-nln", "batch_clipping",
                            "--config", "OGR_PG_ENABLE_METADATA", "NO" ])

        LogMessage("Batch clipping: " + basename(output))

        runSubprocess([ "gdalwarp", \
                        "-of", "GTiff", \
                        "-cutline", batch_clipping, \
                        "-dstnodata", "-9999", \
                        "-crop_to_cutline", output, \
                        batch_output ])

def createCappedDistanceRaster(input, output, capvalue):
    """
    Creates distance where values over 'capvalue' are set to 'capvalue'
    """

    LogMessage("Capping value on raster at " + str(capvalue) + " and outputting to: " + output)

    if isfile(output): os.remove(output)

    runSubprocess([ "gdal_calc.py", \
                    "-A", input, \
                    "--outfile=" + output, \
                    '--calc="(A*(A<=' + str(capvalue) + '))+(' + str(capvalue) + '*(A>' + str(capvalue) + '))"' ])

def createRasterFromGeoJSON(runtest, batch_grid_spacing, raster_resolution, geojson_path, raster_path):
    """
    Creates raster from GeoJSON
    """

    global OUTPUT_ML_CSV

    gridsquare_offset_negative = int(raster_resolution / 2)
    output_ml = buildOutputPath(runtest, OUTPUT_ML_CSV, batch_grid_spacing, raster_resolution)

    raster_data = getJSON(geojson_path)

    LogMessage("Converting GeoJSON file with 'prediction' property for all points into raster...")

    LogMessage("Converting GeoJSON into CSV")

    with open(output_ml, 'w', newline='') as csvfile:
        fieldnames = ['easting', 'northing', 'probability']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

    with open(output_ml, 'a', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        for raster_item in raster_data['features']:
            coordinates = raster_item['geometry']['coordinates']
            easting, northing = lnglat_to_bngrs(coordinates[0], coordinates[1])
            writer.writerow({'easting': int(easting), 'northing': int(northing), 'probability': raster_item['properties']['prediction']})

    LogMessage("Finished converting GeoJSON into CSV")

    LogMessage("Generating GeoTIFF raster")

    df = pd.read_csv(output_ml)

    nodata_val = -9999
    x_min = df['easting'].min()
    x_max = df['easting'].max()
    y_min = df['northing'].min()
    y_max = df['northing'].max()
    width = int(np.ceil((x_max - x_min) / raster_resolution)) + 1
    height = int(np.ceil((y_max - y_min) / raster_resolution)) + 1
    raster = np.full((height, width), nodata_val, dtype=np.float32)

    for _, row in df.iterrows():
        col = round((row["easting"] - x_min) / raster_resolution)
        row_idx = round((y_max - row["northing"]) / raster_resolution)
        raster[row_idx, col] = row["probability"]

    transform = from_origin(x_min - gridsquare_offset_negative, y_max + gridsquare_offset_negative, raster_resolution, raster_resolution)

    temp_raster_path = 'temp.tif'
    if isfile(temp_raster_path): os.remove(temp_raster_path)

    with rasterio.open(
        raster_path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype=np.float32,
        crs="EPSG:27700",
        transform=transform,
        nodata=nodata_val,
    ) as dst:
        dst.write(raster, 1)

    # cropRaster(temp_raster_path, raster_path)
    if isfile(temp_raster_path): os.remove(temp_raster_path)

    LogMessage("Finished generating GeoTIFF raster")

def ingrs_to_lnglat(easting, northing):
    """
    Transforms Ireland NG to lng, lat
    """

    global TRANSFORMER_FROM_29903

    if TRANSFORMER_FROM_29903 is None: TRANSFORMER_FROM_29903 = pyproj.Transformer.from_crs("EPSG:29903", "EPSG:4326")

    lat, lng = TRANSFORMER_FROM_29903.transform(easting, northing)

    return lng, lat

def bngrs_to_lnglat(easting, northing):
    """
    Transforms British NG to lng, lat
    """

    global TRANSFORMER_FROM_27700

    if TRANSFORMER_FROM_27700 is None: TRANSFORMER_FROM_27700 = pyproj.Transformer.from_crs("EPSG:27700", "EPSG:4326")

    lat, lng = TRANSFORMER_FROM_27700.transform(easting, northing)

    return lng, lat

def lnglat_to_bngrs(longitude, latitude):
    """
    Transforms lng, lat to British NG
    """

    global TRANSFORMER_SOURCE_4326, TRANSFORMER_DEST_27700, TRANSFORMER_TO_27700

    if TRANSFORMER_SOURCE_4326 is None:
        TRANSFORMER_SOURCE_4326 = crs_source = pyproj.CRS("EPSG:4326")  # WGS84 (longitude/latitude)
        TRANSFORMER_DEST_27700 = crs_destination = pyproj.CRS("EPSG:27700")  # British National Grid
        TRANSFORMER_TO_27700 = pyproj.Transformer.from_crs(TRANSFORMER_SOURCE_4326, TRANSFORMER_DEST_27700, always_xy=True)

    easting, northing = TRANSFORMER_TO_27700.transform(longitude, latitude)

    return easting, northing

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

def postgisExecDelete(sql_text, sql_parameters=None):
    """
    Executes DELETE SQL statement and returns number of deleted rows
    """

    global POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD

    conn = psycopg2.connect(host=POSTGRES_HOST, dbname=POSTGRES_DB, user=POSTGRES_USER, password=POSTGRES_PASSWORD, \
                            keepalives=1, keepalives_idle=30, keepalives_interval=5, keepalives_count=5)
    cur = conn.cursor()
    if sql_parameters is None: cur.execute(sql_text)
    else: cur.execute(sql_text, sql_parameters)
    conn.commit()
    deleted_rows = cur.rowcount
    conn.close()
    return deleted_rows

def postgisImportDatasetGIS(dataset_path, dataset_table, orig_srs='EPSG:4326'):
    """
    Imports GIS file to PostGIS table
    """

    global POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD

    LogMessage("Importing into PostGIS: " + dataset_table)

    if '.gpkg' in dataset_path: orig_srs = getGPKGProjection(dataset_path)

    ogr2ogr_array = ["ogr2ogr", \
                            "-f", "PostgreSQL", \
                            'PG:host=' + POSTGRES_HOST + ' user=' + POSTGRES_USER + ' password=' + POSTGRES_PASSWORD + ' dbname=' + POSTGRES_DB, \
                            dataset_path, \
                            "-overwrite", \
                            "-nln", dataset_table, \
                            "-lco", "GEOMETRY_NAME=geom", \
                            "-lco", "OVERWRITE=YES", \
                            "-s_srs", orig_srs, \
                            "-t_srs", 'EPSG:4326']

    if dataset_table in ['sitepredictor__infuse_lsoa__uk', 'sitepredictor__infuse_oa__uk']:
        ogr2ogr_array.append("-nlt")
        ogr2ogr_array.append("MULTIPOLYGON")

    ogr2ogr_array += ["--config", "OGR_PG_ENABLE_METADATA", "NO"]

    runSubprocess(ogr2ogr_array)

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

    for field in fields:
        if '__prop' in field: continue
        proportional_field = field + '__prop'
        if proportional_field in fields: continue

        postgisExec('ALTER TABLE %s ADD COLUMN %s FLOAT;', (AsIs(table), AsIs(proportional_field), ))
        postgisExec('UPDATE %s SET %s = (%s::float / total::float)', (AsIs(table), AsIs(proportional_field), AsIs(field), ))

def postgisGetTableBounds(table_name):
    """
    Get bounds of all geometries in table
    """

    global POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD

    conn = psycopg2.connect(host=POSTGRES_HOST, dbname=POSTGRES_DB, user=POSTGRES_USER, password=POSTGRES_PASSWORD)
    cur = conn.cursor()
    cur.execute("""
    SELECT 
        MIN(easting) AS left,
        MIN(northing) AS bottom,
        MAX(easting) AS right,
        MAX(northing) AS top FROM %s;
    """, (AsIs(table_name), ))
    left, bottom, right, top = cur.fetchone()
    conn.close()
    return {'left': left, 'bottom': bottom, 'right': right, 'top': top}

def postgisGetBasicProcessedTables():
    """
    Gets list of all 'basic' processed dataset tables
    ie. where no buffering has been applied
    """

    global POSTGRES_DB, CUSTOM_CONFIGURATION_PREFIX

    custom_configuration_prefix_escape = CUSTOM_CONFIGURATION_PREFIX.replace(r'_', r'\_')

    table_list = postgisGetResults(r"""
    SELECT tables.table_name
    FROM information_schema.tables
    WHERE 
    table_catalog=%s AND 
    table_schema='public' AND 
    table_type='BASE TABLE' AND
    table_name NOT IN ('spatial_ref_sys') AND 
    table_name LIKE '%%\_\_pro' AND 
    table_name NOT LIKE '%%\_\_buf\_%%' AND 
    table_name NOT LIKE 'tip%%' AND 
    table_name NOT LIKE 'uk\_\_%%' AND 
    table_name NOT LIKE '%%clipping%%' AND 
    table_name NOT LIKE 'osm_boundaries' AND 
    table_name NOT LIKE '\_scratch%%' AND
    table_name NOT LIKE '""" + custom_configuration_prefix_escape + r"""%%' AND
    table_name NOT LIKE 'sitepredictor\_\_%%' AND 
    table_name NOT LIKE '%%\_\_27700';
    """, (POSTGRES_DB, ))
    return [list_item[0] for list_item in table_list]

def postgisGetBasicUnprocessedTables():
    """
    Gets list of all 'basic' unprocessed dataset tables
    ie. where no buffering has been applied
    """

    global POSTGRES_DB, CUSTOM_CONFIGURATION_PREFIX

    custom_configuration_prefix_escape = CUSTOM_CONFIGURATION_PREFIX.replace(r'_', r'\_')

    basic_processed = postgisGetBasicProcessedTables()
    basic_unprocessed = postgisGetResults(r"""
    SELECT tables.table_name
    FROM information_schema.tables
    WHERE 
    table_catalog=%s AND 
    table_schema='public' AND 
    table_type='BASE TABLE' AND
    table_name NOT IN ('spatial_ref_sys') AND 
    table_name NOT LIKE '%%\_\_pro' AND 
    table_name NOT LIKE '%%\_\_buf\_%%' AND 
    table_name NOT LIKE 'tip%%' AND 
    table_name NOT LIKE 'uk\_\_%%' AND 
    table_name NOT LIKE '%%clipping%%' AND 
    table_name NOT LIKE 'osm_boundaries' AND 
    table_name NOT LIKE '\_scratch%%' AND
    table_name NOT LIKE '""" + custom_configuration_prefix_escape + r"""%%' AND
    table_name NOT LIKE 'temp\_%%' AND
    table_name NOT LIKE 'test\_%%' AND
    table_name NOT LIKE 'sitepredictor\_\_%%' AND 
    table_name NOT LIKE '%%\_\_27700';
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

    global POSTGRES_DB, CUSTOM_CONFIGURATION_PREFIX

    custom_configuration_prefix_escape = CUSTOM_CONFIGURATION_PREFIX.replace(r'_', r'\_')

    basic_processed = postgisGetBasicProcessedTables()
    basic_unprocessed = postgisGetResults(r"""
    SELECT tables.table_name
    FROM information_schema.tables
    WHERE 
    table_catalog=%s AND 
    table_schema='public' AND 
    table_type='BASE TABLE' AND 
    table_name NOT IN ('spatial_ref_sys') AND 
    table_name LIKE '%%\_\_uk' AND 
    table_name NOT LIKE '%%\_\_pro' AND 
    table_name NOT LIKE '%%\_\_buf\_%%' AND 
    table_name NOT LIKE 'tip%%' AND 
    table_name NOT LIKE 'uk\_\_%%' AND 
    table_name NOT LIKE '%%clipping%%' AND 
    table_name NOT LIKE 'osm_boundaries' AND 
    table_name NOT LIKE '\_scratch%%' AND 
    table_name NOT LIKE '""" + custom_configuration_prefix_escape + r"""%%' AND
    table_name NOT LIKE 'sitepredictor\_\_%%' AND 
    table_name NOT LIKE '%%\_\_27700';
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

    global POSTGRES_DB, CUSTOM_CONFIGURATION_PREFIX

    custom_configuration_prefix_escape = CUSTOM_CONFIGURATION_PREFIX.replace(r'_', r'\_')

    table_list = postgisGetResults(r"""
    SELECT tables.table_name
    FROM information_schema.tables
    WHERE 
    table_catalog=%s AND 
    table_schema='public' AND 
    table_type='BASE TABLE' AND
    table_name NOT IN ('spatial_ref_sys') AND 
    table_name LIKE '%%\_\_uk\_\_pro' AND 
    table_name NOT LIKE '%%\_\_buf\_%%' AND 
    table_name NOT LIKE '""" + custom_configuration_prefix_escape + r"""%%' AND
    table_name NOT LIKE 'sitepredictor\_\_%%' AND 
    table_name NOT LIKE '%%\_\_27700';
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

    scratch_table_1 = '_scratch_table_10'
    scratch_table_2 = '_scratch_table_11'

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

    scratch_table_1 = '_scratch_table_10'
    scratch_table_2 = '_scratch_table_11'

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

def postgisDistanceToNearestFeatureNonCache(position, dataset_table):
    """
    Gets distance of turbine from specific feature layer using direct PostGIS query
    """

    results = postgisGetResults("SELECT MIN(ST_Distance(ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), 27700), geom)) AS distance FROM %s;", \
                                (position['lng'], position['lat'], AsIs(reformatTableName(dataset_table)), ))
    distance = results[0][0]

    if distance == 0:

        results = postgisGetResults("SELECT -MIN(ST_Distance(ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), 27700), ST_ExteriorRing(geom))) FROM %s;",\
                                    (position['lng'], position['lat'], AsIs(reformatTableName(dataset_table)), ))
        distance = results[0][0]

        # If empty results, feature must be line and has no 'inside'

        if distance is None: return 0

    return distance

def postgisDistanceToNearestFeature(ogc_fid, table):
    """
    Gets distance of turbine from specific feature layer from cache using turbine's ogc_fid
    """

    global DISTANCE_CACHE_TABLE, DISTANCE_CACHE_VALUES

    # createDistanceCache([dataset_table])

    if ogc_fid not in DISTANCE_CACHE_VALUES:
        DISTANCE_CACHE_VALUES[ogc_fid] = {}
        items = postgisGetResults("SELECT table_name, distance FROM %s WHERE ogc_fid = %s;", (AsIs(DISTANCE_CACHE_TABLE), AsIs(ogc_fid), ))
        if len(items) is None: DISTANCE_CACHE_VALUES[ogc_fid] = None
        for item in items: 
            item_table, item_distance = item[0], item[1]
            DISTANCE_CACHE_VALUES[ogc_fid][item_table] = item_distance

    # If no cache entry for specific ogc_fid and table, this must be because (external) distance = 0 and LineString
    if table not in DISTANCE_CACHE_VALUES[ogc_fid]: return 0

    return DISTANCE_CACHE_VALUES[ogc_fid][table]

def createTransformedTable(dataset_table):
    """
    Creates fresh transformed table with EPSG:27700 projection
    """

    dataset_table_transformed = dataset_table + '__27700'
    if not postgisCheckTableExists(dataset_table_transformed):

        LogMessage("Recreating EPSG:27700 projected version of: " + dataset_table)

        postgisExec("CREATE TABLE %s AS SELECT ST_Transform(geom, 27700) geom FROM %s", (AsIs(dataset_table_transformed), AsIs(dataset_table), ))
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

def buildOutputPath(runtest, basepath, batch_grid_spacing, raster_resolution):
    """
    Builds output path adding raster_resolution
    """

    outputpath_dir = os.path.dirname(basepath)
    outputpath_basename = basename(basepath)
    if runtest: outputpath_basename = 'test--' + str(batch_grid_spacing) + '-m-' + outputpath_basename
    outputpath_basename_elements = outputpath_basename.split('.')

    output_path = join(outputpath_dir, outputpath_basename_elements[0] + '--' + str(raster_resolution) + "-m." + outputpath_basename_elements[1])

    return output_path

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

def buildBatchSamplingGridTableName(batch_index, batch_grid_spacing):
    """
    Builds batch sampling grid table name
    """

    global BATCH_SAMPLING_GRID

    return BATCH_SAMPLING_GRID + "__idx_" + str(batch_index) + "_spc_" + str(batch_grid_spacing) + "_m__uk"

def buildBatchFilename(file_name, batch_index, batch_grid_spacing):
    """
    Builds batch grid generic filename
    """

    file_name = file_name.replace('.csv', '').replace('.geojson', '').replace('.tif', '')

    return file_name + '-batch-' + str(batch_index) + '-' + str(batch_grid_spacing) + 'm'

def buildBatchGridOutputData(output_data, batch_index, batch_grid_spacing):
    """
    Builds batch grid output data filename
    """

    if batch_index is None: return output_data

    return buildBatchFilename(output_data, batch_index, batch_grid_spacing) + '.csv'

def buildBatchGridOutputGeoJSON(output_data, batch_index, batch_grid_spacing):
    """
    Builds batch grid output GeoJSON filename
    """

    if batch_index is None: return output_data

    return buildBatchFilename(output_data, batch_index, batch_grid_spacing) + '.geojson'

def buildBatchGridOutputGeoTIFF(output_data, batch_index, batch_grid_spacing):
    """
    Builds batch grid output GeoTIFF filename
    """

    if batch_index is None: return output_data

    return buildBatchFilename(output_data, batch_index, batch_grid_spacing) + '.tif'

def buildBatchGridTableName(runtest, batch_grid_spacing):
    """
    Builds batch grid table name
    """

    if runtest: return "sitepredictor__test_batch_grid__spc_" + str(batch_grid_spacing) + "_m__uk" 
    return "sitepredictor__batch_grid__spc_" + str(batch_grid_spacing) + "_m__uk"

def buildBatchCellTableName(batch_index, batch_grid_spacing):
    """
    Builds batch cell table name
    """

    return "sitepredictor__batch_grid__idx_" + str(batch_index) + "_spc_" + str(batch_grid_spacing) + "_m__uk"

def buildBatchRasterFilename(raster_resolution, output, batch_index, batch_grid_spacing):
    """
    Builds batch raster filename
    """

    return output.replace('.tif', '') + '_batch_' + str(batch_index) + '_' + str(batch_grid_spacing) + 'm.tif'

def buildBatchRasterClippingFilename(batch_index, batch_grid_spacing):
    """
    Builds batch raster filename
    """

    global CLIPPING_FOLDER

    if not isdir('clipping'): makeFolder(CLIPPING_FOLDER)

    return CLIPPING_FOLDER + 'clipping_batch_' + str(batch_index) + '_' + str(batch_grid_spacing) + 'm.geojson'


# ***********************************************************
# *************** Machine learning functions ****************
# ***********************************************************

def machinelearningInitialize():
    """
    Initializes machine learning
    """

    global ML_FOLDER

    LogMessage("Initializing h2o machine learning")

    os.environ["JAVA_OPTIONS"] = "-XX:ActiveProcessorCount=4"

    try:
        h2o.init(start_h2o=False)
    except Exception as e:
        h2o.init()

    h2o.remove_all()  # Ensure clean environment

    makeFolder(ML_FOLDER)

def machinelearningModelExists():
    """
    Checks to see if existing machine learning model exists
    """

    global ML_FOLDER

    savedmodels = getFilesInFolder(ML_FOLDER)
    if len(savedmodels) > 0: return True
    return False

def machinelearningDeleteSavedModels():
    """
    Deletes all saved models
    """

    global ML_FOLDER

    LogMessage("Deleting existing saved machine learning models")

    savedmodels = getFilesInFolder(ML_FOLDER)
    for savedmodel in savedmodels: os.remove(ML_FOLDER + savedmodel)

def machinelearningGetSavedModel():
    """
    Gets path of first saved model in ML_FOLDER
    """

    global ML_FOLDER

    LogMessage("Loading saved machine learning model")

    savedmodels = getFilesInFolder(ML_FOLDER)

    if len(savedmodels) == 0: return None

    return ML_FOLDER + savedmodels[0]

def machinelearningBuildModel(pass_index):
    """
    Builds machine learning model using AutoML - h2o
    """

    global ML_FOLDER, ML_MAX_RUNTIME_SECS, ML_MAX_MODELS

    LogMessage("Building machine learning model...")

    # Initialize machine learning
    machinelearningInitialize()

    # Load dataset to use for training
    df_train = machinelearningPrepareTrainingData(pass_index)

    # Create hash for reproducibility audit
    df_hash = hash_dataframe(df_train)
    LogMessage("Data hash before AutoML: " + df_hash)

    # Set up machine learning training set
    h2o_frame = h2o.H2OFrame(df_train)
    x = h2o_frame.columns
    y = 'success'
    x.remove(y)

    LogMessage("Running machine learning training using training data")

    # Run machine learning on training set
    # h2o_automl = H2OAutoML(sort_metric='mse', max_runtime_secs=ML_MAX_RUNTIME_SECS, seed=pass_index)
    ML_MAX_MODELS = 40
    # h2o_automl = H2OAutoML(sort_metric='mse', max_models=ML_MAX_MODELS, seed=pass_index, exclude_algos = ["DeepLearning", "XGBoost"], keep_cross_validation_predictions=True)
    # h2o_automl = H2OAutoML(sort_metric='mse', max_models=ML_MAX_MODELS, seed=pass_index, include_algos = ["DeepLearning"], keep_cross_validation_predictions=True)
    # h2o_automl.train(x=x, y=y, training_frame=h2o_frame)

    # # Show final leaderboard of AutoML machine learning to user
    # h2o_models = h2o.automl.get_leaderboard(h2o_automl, extra_columns = "ALL")
    # print(h2o_models)

    # # Delete any existing models
    # machinelearningDeleteSavedModels()

    # # Save 'leader', ie. most optimized model, of all machine learning models
    # LogMessage("Saving machine learning model")
    # h2o.save_model(model=h2o_automl.leader, path=ML_FOLDER, force=True)

    h2o_model = H2ODeepLearningEstimator(
        activation="MaxoutWithDropout",
        hidden=[200, 200, 200, 200, 200, 200, 200, 200],
        input_dropout_ratio=0.1,
        hidden_dropout_ratios=[0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2],
        epochs=1000,
        l1=1e-5,
        l2=1e-5,
        adaptive_rate=True,
        seed=1234,
        stopping_metric="AUTO",  # or use "MSE", "AUC", etc.
        stopping_rounds=5,
        stopping_tolerance=1e-4
    )
    h2o_model.train(x=x, y=y, training_frame=h2o_frame)

    # Delete any existing models
    machinelearningDeleteSavedModels()

    # Save single specific model
    LogMessage("Saving machine learning model")
    h2o.save_model(model=h2o_model, path=ML_FOLDER, force=True)

def machinelearningTestModel(df_test):
    """
    Tests saved machine learning model with df_test dataframe
    """

    # Initialize machine learning
    machinelearningInitialize()

    # Load saved model
    model_path = machinelearningGetSavedModel()
    h2o_automl = h2o.load_model(model_path)

    # Set up data frame with data to test
    h2o_frame = h2o.H2OFrame(df_test)

    # Make predictions using machine learning model
    LogMessage("Applying machine learning model to new data")
    y_pred = h2o_automl.predict(h2o_frame)
    df_predicted = y_pred.as_data_frame().to_numpy().ravel()

    # Show sample predictions to user as sanity check
    LogMessage(str(y_pred.as_data_frame()))

    # Plot results
    h2o_compare = pd.DataFrame(data={'actual': df_test['success'], 'predicted': df_predicted})
    fig = h2o_compare.plot()
    fig.show(block=True)

    return df_predicted

def machinelearningPrepareTrainingData(pass_index):
    """
    Prepares training data for machine learning
    """

    global ML_IGNORE_COLUMNS, OUTPUT_DATA_ALLTURBINES

    LogMessage("Loading machine learning training data")

    # Load dataset
    df = pd.read_csv(OUTPUT_DATA_ALLTURBINES, delimiter=',', low_memory=False)

    # # Randomly shuffle all rows so any test subset contains mix of success values
    df = df.sample(frac=1, random_state=pass_index)

    # Use 'project_date_end' as 'date_time' x-axis - useful for displaying all results on plot
    df['date_time'] = pd.to_datetime(df['project_date_end'], format='%Y-%m-%d')

    # Remove records where status is pending
    df = df[~df['project_status'].isin(ML_STATUS_PENDING)]
    df["success"] = np.where(df["project_status"].isin(ML_STATUS_SUCCESS), 1, 0)

    # Remove 'project_status' from columns as essential this is not a feature used to build model
    df = df.drop('project_status', axis=1)

    # Sort results by 'date_time'
    df = df.set_index('date_time').sort_index()

    # Drop any rows that don't have 'project_date_end' set
    df = df.dropna(subset=['project_date_end'])

    # Make copy of original dataset
    df_original = df.copy()

    # Remove extraneous columns
    for column_to_remove in ML_IGNORE_COLUMNS: df = df.drop(column_to_remove, axis=1)

    # Split train and test sets - currently redundant as we train on all results
    sample_size = df.shape[0]
    df_train = df.iloc[:sample_size].copy()
    # df_test = df.iloc[:sample_size].copy()

    return df_train

def machinelearningRunModelOnSamplingGrid(runtest, batch_grid_spacing, raster_resolution):
    """
    Runs machine learning model on sample grid
    """

    global OUTPUT_DATA_SAMPLEGRID, OUTPUT_ML_GEOJSON, OUTPUT_ML_RASTER

    output_data = buildOutputPath(runtest, OUTPUT_DATA_SAMPLEGRID, batch_grid_spacing, raster_resolution)
    output_ml_geojson = buildOutputPath(runtest, OUTPUT_ML_GEOJSON, batch_grid_spacing, raster_resolution)
    output_ml_geotiff = buildOutputPath(runtest, OUTPUT_ML_RASTER, batch_grid_spacing, raster_resolution)

    if not isfile(output_ml_geojson):

        # Initialize machine learning
        machinelearningInitialize()

        # Load dataset to test
        LogMessage("Loading dataset to test")
        df_samplegrid = pd.read_csv(output_data, delimiter=',', low_memory=False)

        # Use project_date_end as date_time x-axis
        df_samplegrid['date_time'] = pd.to_datetime(df_samplegrid['project_date_end'], format='%Y-%m-%d')
        df_samplegrid = df_samplegrid.set_index('date_time').sort_index()

        # Make copy of sample grid before we make further changes so we
        # can use when generating output results (GeoJSON or GeoTIFF)
        LogMessage("Copying dataset")
        df_original = df_samplegrid.copy()

        # Remove extraneous columns
        LogMessage("Removing extraneous columns")
        for column_to_remove in ML_IGNORE_COLUMNS:
            if column_to_remove in df_samplegrid:
                df_samplegrid = df_samplegrid.drop(column_to_remove, axis=1)

        # Load saved machine leraning model
        LogMessage("Loading machine learning model")
        model_path = machinelearningGetSavedModel()
        h2o_automl = h2o.load_model(model_path)

        # Build dataframe from sample grid
        LogMessage("Loading dataset to test")
        h2o_frame_test = h2o.H2OFrame(df_samplegrid)

        # Run machine learning model with sample grid data
        LogMessage("Applying machine learning model to new data")
        y_pred = h2o_automl.predict(h2o_frame_test)

        df_predicted = y_pred.as_data_frame().to_numpy().ravel()
        print(y_pred.as_data_frame())

        machinelearningOutputGridResultsAsGeoJSON(runtest, batch_grid_spacing, raster_resolution, df_original, df_predicted)

    if not isfile(output_ml_geotiff):
        createRasterFromGeoJSON(runtest, batch_grid_spacing, raster_resolution, output_ml_geojson, output_ml_geotiff)

def machinelearningOutputGridResultsAsGeoJSON(runtest, batch_grid_spacing, raster_resolution, df_original, df_predicted):
    """
    Output results of machine learning predictions for array of points
    """

    global OUTPUT_ML_GEOJSON

    output_ml_geojson = buildOutputPath(runtest, OUTPUT_ML_GEOJSON, batch_grid_spacing, raster_resolution)

    features = []
    count = 0

    LogMessage("Creating output GeoJSON with prediction value as property")

    for index, row in df_original.iterrows():
        features.append({
            'type': 'Feature',
            'properties': {'prediction': df_predicted[count]},
            'geometry': {
                'type': 'Point',
                'coordinates': [
                    row['turbine_lnglat_lng'],
                    row['turbine_lnglat_lat']
                ]
            }
        })

        count += 1

    featurecollection = {
        'type': 'FeatureCollection',
        'features': features
    }

    with open(output_ml_geojson, "w", encoding='UTF-8') as writerfileobj:
        json.dump(featurecollection, writerfileobj, ensure_ascii=False, indent=4)


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
    global POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD

    makeFolder(DATASETS_FOLDER)

    if not isfile(DATASETS_FOLDER + basename(OSM_MAIN_DOWNLOAD)):

        LogMessage("Downloading latest OSM data for United Kingdom")

        runSubprocess(["wget", OSM_MAIN_DOWNLOAD, "-O", DATASETS_FOLDER + basename(OSM_MAIN_DOWNLOAD)])

    yaml_all_filename, yaml_all_content = OSM_CONFIG_FOLDER + 'all.yml', {}

    if (not isfile(OSM_EXPORT_DATA + '.gpkg')) or (not isfile(yaml_all_filename)):

        LogMessage("Missing " + basename(OSM_EXPORT_DATA) + ".gpkg, running osm-export-tool to generate it using: " + yaml_all_filename)

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

        if not isfile(OVERALL_CLIPPING_FILE):

            LogMessage("Generating " + OVERALL_CLIPPING_FILE + " for overall clipping when using osm-export-tool")

            clipping_table = reformatTableName(OVERALL_CLIPPING_FILE)
            clipping_union_table = buildUnionTableName(clipping_table)

            inputs = runSubprocess(["ogr2ogr", \
                                    OVERALL_CLIPPING_FILE, \
                                    'PG:host=' + POSTGRES_HOST + ' user=' + POSTGRES_USER + ' password=' + POSTGRES_PASSWORD + ' dbname=' + POSTGRES_DB, \
                                    "-overwrite", \
                                    "-nln", clipping_union_table, \
                                    "-nlt", 'MULTIPOLYGON', \
                                    "-dialect", "sqlite", \
                                    "-sql", \
                                    "SELECT geom geometry FROM '" + clipping_union_table + "'", \
                                    "--config", "OGR_PG_ENABLE_METADATA", "NO" ])

        LogMessage("Running osm-export-tool to generate additional datasets")

        runSubprocess(['/bin/bash', "./osm-export.sh", DATASETS_FOLDER + basename(OSM_MAIN_DOWNLOAD), OSM_EXPORT_DATA, "-m", yaml_all_filename, "--clip", OVERALL_CLIPPING_FILE])

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

def findErrorTurbines():
    """
    Find all turbines with missing distance error
    """

    # Get list of tables to run distance testing on
    tables_to_test_unprojected = removeNonEssentialTablesForDistance(postgisGetUKBasicProcessedTables())

    # Creates reprojected version of all testing tables to improve performance
    tables_to_test = []
    for table in tables_to_test_unprojected:
        tables_to_test.append(createTransformedTable(table))

    tables_to_test = removeNonEssentialTablesForDistance(tables_to_test)

    # Get all failed and successful wind turbines
    all_turbines = getAllWindProjects()

    index, totalrecords = 0, len(all_turbines)

    for turbine in all_turbines:

        # LogMessage("Processing turbine: " + str(index + 1) + "/" + str(totalrecords))

        # Improve ordering of fields
        turbine_lnglat = {'lng': turbine['lng'], 'lat': turbine['lat']}

        for table_to_test in tables_to_test:
            distance = postgisDistanceToNearestFeature(turbine['ogc_fid'], table_to_test)
            # Remove internal table suffixes to improve readability
            # We don't need more precision than 1 metre
            if distance is None:
                print("Distance is NONE:", index, turbine['ogc_fid'], table_to_test, turbine_lnglat)
                distance = postgisDistanceToNearestFeatureNonCache(turbine_lnglat, table_to_test)
                print("Direct PostGIS query distance:", distance)
                # exit()

        index += 1

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

def generateHistoricalFootpathsForTurbine(turbine_parameters):
    """
    Deletes turbine-generated footpaths for turbine with id turbine_fid
    """

    global FOOTPATHS_SINGLELINES_DATASET, FOOTPATHS_HISTORICAL_DATASET, WINDTURBINES_OPERATIONAL_DATASET
    global MAXIMUM_DISTANCE_ENDPOINT, MAXIMUM_DISTANCE_LINE

    turbine_fid, turbine_index = turbine_parameters[0], turbine_parameters[1]

    footpaths_historical_table = reformatTableName(FOOTPATHS_HISTORICAL_DATASET) + '__pro__27700'
    windturbines_operational_table = reformatTableName(WINDTURBINES_OPERATIONAL_DATASET)

    with cnt.get_lock():
        if (cnt.value % 1000) == 0: LogMessage(" --> Deleting turbine-specific footpaths for turbine " + str(cnt.value))
        cnt.value += 1

    scratch_table_1 = '_scratch_historical_footpaths_' + str(turbine_index)

    if postgisCheckTableExists(scratch_table_1): postgisDropTable(scratch_table_1)

    # Create 1km search bounding box to speed up MIN(ST_Distance)
    postgisExec("CREATE TABLE %s AS SELECT ST_Envelope(ST_Buffer(ST_Transform(geom, 27700), 1000)) geom FROM %s WHERE fid=%s;", (AsIs(scratch_table_1), AsIs(windturbines_operational_table), turbine_fid))

    num_deleted_startend = postgisExecDelete("""
    DELETE FROM %s footpath 
    WHERE 
    ST_Intersects(footpath.geom, (SELECT geom FROM %s)) AND
    (
    ((SELECT MIN(ST_Distance(ST_StartPoint(footpath.geom), ST_Transform(turbine.geom, 27700))) FROM (SELECT geom FROM %s WHERE fid=%s) turbine) < %s) OR 
    ((SELECT MIN(ST_Distance(ST_EndPoint(footpath.geom), ST_Transform(turbine.geom, 27700))) FROM (SELECT geom FROM %s WHERE fid=%s) turbine) < %s)
    );
    """, \
    (   AsIs(footpaths_historical_table), \
        AsIs(scratch_table_1), \
        AsIs(windturbines_operational_table), \
        turbine_fid,\
        AsIs(MAXIMUM_DISTANCE_ENDPOINT), \
        AsIs(windturbines_operational_table), \
        turbine_fid,\
        AsIs(MAXIMUM_DISTANCE_ENDPOINT), ))

    num_deleted_length = postgisExecDelete("""
    DELETE FROM %s footpath 
    WHERE 
    ST_Intersects(footpath.geom, (SELECT geom FROM %s)) AND
    ((SELECT MIN(ST_Distance(footpath.geom, ST_Transform(turbine.geom, 27700))) FROM (SELECT geom FROM %s WHERE fid=%s) turbine) < %s);
    """, \
    (AsIs(footpaths_historical_table), AsIs(scratch_table_1), AsIs(windturbines_operational_table), turbine_fid, AsIs(MAXIMUM_DISTANCE_LINE), ))

    if postgisCheckTableExists(scratch_table_1): postgisDropTable(scratch_table_1)


def generateHistoricalFootpaths():
    """
    Process footpaths to remove those likely to have been created to provide access to new turbines
    ie. leaving only those footpaths likely to have existed before specific wind turbines were built
    """

    global FOOTPATHS_SINGLELINES_DATASET, FOOTPATHS_HISTORICAL_DATASET, WINDTURBINES_OPERATIONAL_DATASET
    global MAXIMUM_DISTANCE_ENDPOINT, MAXIMUM_DISTANCE_LINE

    osmDownloadData()

    footpaths_original_table = reformatTableName(FOOTPATHS_SINGLELINES_DATASET) + '__pro__27700'
    footpaths_historical_table = reformatTableName(FOOTPATHS_HISTORICAL_DATASET) + '__pro__27700'
    windturbines_operational_table = reformatTableName(WINDTURBINES_OPERATIONAL_DATASET)

    if not postgisCheckTableExists(footpaths_historical_table):

        LogMessage("Historical footpaths recreation: creating copy of footpaths in table " + footpaths_historical_table)

        postgisExec("CREATE TABLE %s AS SELECT * FROM %s;", (AsIs(footpaths_historical_table), AsIs(footpaths_original_table), ))
        postgisExec("CREATE INDEX " + footpaths_historical_table + "_idx ON %s USING GIST (geom);", (AsIs(footpaths_historical_table), ))

        LogMessage("Historical footpaths recreation: Retrieving operational turbines")

        operational_turbines = postgisGetResults("SELECT fid FROM %s ORDER BY fid;", (AsIs(windturbines_operational_table), ))

        LogMessage("Historical footpaths recreation: Deleting turbine-specific footpaths...")

        cnt = Value('i', 0)
        turbine_fids = []
        for i in range(len(operational_turbines)):
            turbine_fids.append([operational_turbines[i][0] , i])

        LogMessage("************************************************")
        LogMessage("********** STARTING MULTIPROCESSING ************")
        LogMessage("************************************************")

        # Run multiprocessing pool
        with Pool(initializer=init_globals, initargs=(cnt,)) as p:
            p.map(generateHistoricalFootpathsForTurbine, turbine_fids)

        LogMessage("************************************************")
        LogMessage("*********** ENDING MULTIPROCESSING *************")
        LogMessage("************************************************")

    LogMessage("Historical footpaths recreation: COMPLETED")

def generateHistoricalMinorRoadsForTurbine(turbine_parameters):
    """
    Deletes turbine-generated minor roads for turbine with id turbine_fid
    """

    global FOOTPATHS_SINGLELINES_DATASET, FOOTPATHS_HISTORICAL_DATASET, WINDTURBINES_OPERATIONAL_DATASET
    global MAXIMUM_DISTANCE_ENDPOINT, MAXIMUM_DISTANCE_LINE

    turbine_fid, turbine_index = turbine_parameters[0], turbine_parameters[1]

    minorroads_historical_table = reformatTableName(MINORROADS_HISTORICAL_DATASET) + '__pro__27700'
    windturbines_operational_table = reformatTableName(WINDTURBINES_OPERATIONAL_DATASET)

    with cnt.get_lock():
        if (cnt.value % 1000) == 0: LogMessage(" --> Deleting turbine-specific minor roads for turbine " + str(cnt.value))
        cnt.value += 1

    scratch_table_1 = '_scratch_historical_minorroads_' + str(turbine_index)

    if postgisCheckTableExists(scratch_table_1): postgisDropTable(scratch_table_1)

    # Create 1km search bounding box to speed up MIN(ST_Distance)
    postgisExec("CREATE TABLE %s AS SELECT ST_Envelope(ST_Buffer(ST_Transform(geom, 27700), 1000)) geom FROM %s WHERE fid=%s;", (AsIs(scratch_table_1), AsIs(windturbines_operational_table), turbine_fid))

    num_deleted_startend = postgisExecDelete("""
    DELETE FROM %s minorroad 
    WHERE 
    ST_Intersects(minorroad.geom, (SELECT geom FROM %s)) AND
    minorroad.highway = 'service' AND 
    (
        ((SELECT MIN(ST_Distance(ST_StartPoint(minorroad.geom), ST_Transform(turbine.geom, 27700))) FROM (SELECT geom FROM %s WHERE fid=%s) turbine) < %s) OR 
        ((SELECT MIN(ST_Distance(ST_EndPoint(minorroad.geom), ST_Transform(turbine.geom, 27700))) FROM (SELECT geom FROM %s WHERE fid=%s) turbine) < %s)
    )""", \
    (   AsIs(minorroads_historical_table), \
        AsIs(scratch_table_1), \
        AsIs(windturbines_operational_table), \
        turbine_fid,\
        AsIs(MAXIMUM_DISTANCE_ENDPOINT), \
        AsIs(windturbines_operational_table), \
        turbine_fid,\
        AsIs(MAXIMUM_DISTANCE_ENDPOINT), ))

    num_deleted_length = postgisExecDelete("""
    DELETE FROM %s minorroad 
    WHERE 
    ST_Intersects(minorroad.geom, (SELECT geom FROM %s)) AND
    minorroad.highway = 'service' AND
    ((SELECT MIN(ST_Distance(minorroad.geom, ST_Transform(turbine.geom, 27700))) FROM (SELECT geom FROM %s WHERE fid=%s) turbine) < %s)""", \
    (AsIs(minorroads_historical_table), AsIs(scratch_table_1), AsIs(windturbines_operational_table), turbine_fid, AsIs(MAXIMUM_DISTANCE_LINE), ))

    if postgisCheckTableExists(scratch_table_1): postgisDropTable(scratch_table_1)

def generateHistoricalMinorRoads():
    """
    Process minor roads to remove those service roads likely to have been created to provide access to new turbines
    ie. leaving only those minor roads likely to have existed before specific wind turbines were built
    """

    global MINORROADS_SINGLELINES_DATASET, MINORROADS_HISTORICAL_DATASET, WINDTURBINES_OPERATIONAL_DATASET
    global MAXIMUM_DISTANCE_ENDPOINT, MAXIMUM_DISTANCE_LINE

    osmDownloadData()

    minorroads_original_table = reformatTableName(MINORROADS_SINGLELINES_DATASET)
    minorroads_historical_table = reformatTableName(MINORROADS_HISTORICAL_DATASET) + '__pro__27700'
    windturbines_operational_table = reformatTableName(WINDTURBINES_OPERATIONAL_DATASET)

    if not postgisCheckTableExists(minorroads_historical_table):

        LogMessage("Historical minor roads recreation: creating copy of minor roads in table " + minorroads_historical_table)

        # We need access to 'highway' field so copy from originally imported table rather than '__pro__27700' version
        postgisExec("CREATE TABLE %s AS SELECT fid, highway, ST_Transform(geom, 27700) geom FROM %s;", (AsIs(minorroads_historical_table), AsIs(minorroads_original_table), ))
        postgisExec("CREATE INDEX " + minorroads_historical_table + "_idx ON %s USING GIST (geom);", (AsIs(minorroads_historical_table), ))
        postgisExec("CREATE INDEX highway_idx ON " + minorroads_historical_table + "(highway);")

        LogMessage("Historical minor roads recreation: Retrieving operational turbines")

        operational_turbines = postgisGetResults("SELECT fid FROM %s ORDER BY fid;", (AsIs(windturbines_operational_table), ))

        LogMessage("Historical minor roads recreation: Deleting turbine-specific minor service roads...")

        cnt = Value('i', 0)
        turbine_fids = []
        for i in range(len(operational_turbines)):
            turbine_fids.append([operational_turbines[i][0] , i])

        LogMessage("************************************************")
        LogMessage("********** STARTING MULTIPROCESSING ************")
        LogMessage("************************************************")

        # Run multiprocessing pool
        with Pool(initializer=init_globals, initargs=(cnt,)) as p:
            p.map(generateHistoricalMinorRoadsForTurbine, turbine_fids)

        LogMessage("************************************************")
        LogMessage("*********** ENDING MULTIPROCESSING *************")
        LogMessage("************************************************")

    LogMessage("Historical minor roads recreation: COMPLETED")

def downloadTerrainGeoTIFF():
    """
    Download terrain GeoTIFF used to determine elevation at specific positions
    """

    global DTM_GEOTIFF_URL

    geotiff_path = basename(DTM_GEOTIFF_URL)

    if not isfile(geotiff_path):

        LogMessage("Downloading Terrain GeoTIFF")

        attemptDownloadUntilSuccess(DTM_GEOTIFF_URL, geotiff_path)

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

    global WINDSPEED_DATASET, WINDSPEED_CACHE

    position_index = str(position['lng']) + '_' + str(position['lat'])

    if position_index not in WINDSPEED_CACHE:

        results = postgisGetResults("SELECT MAX(windspeed) FROM %s WHERE ST_Intersects(geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326))", \
                                    (AsIs(reformatTableName(WINDSPEED_DATASET)), position['lng'], position['lat'], ))

        if len(results) == 0: return None

        WINDSPEED_CACHE[position_index] = results[0][0]

    return WINDSPEED_CACHE[position_index]

def importAllWindProjects():
    """
    Imports manually curated list of all failed and successful wind turbine positions
    """

    global WINDTURBINES_ALLPROJECTS_URL, DATASETS_FOLDER, WINDTURBINES_ALLPROJECTS_DATASET

    onshore_allprojects_dataset_path = DATASETS_FOLDER + WINDTURBINES_ALLPROJECTS_DATASET + '.geojson'

    if not isfile(onshore_allprojects_dataset_path):

        LogMessage("No data file containing all turbine coordinates for failed and successful projects - initiating download")

        attemptDownloadUntilSuccess(WINDTURBINES_ALLPROJECTS_URL, onshore_allprojects_dataset_path)

        LogMessage("Failed and successful wind turbines downloaded")

    if not postgisCheckTableExists(WINDTURBINES_ALLPROJECTS_DATASET):

        LogMessage("Importing all failed and successful wind turbine projects...")

        postgisImportDatasetGIS(onshore_allprojects_dataset_path, WINDTURBINES_ALLPROJECTS_DATASET)

        postgisExec("ALTER TABLE windturbines_all_projects__uk ADD COLUMN geom_27700 geometry(Point,27700);")
        postgisExec("UPDATE windturbines_all_projects__uk SET geom_27700 = ST_Transform(geom, 27700);")
        postgisExec("CREATE INDEX geom_27700_idx ON windturbines_all_projects__uk USING GIST (geom_27700);")
        postgisExec("CREATE INDEX project_status_idx ON windturbines_all_projects__uk(project_status);")
        postgisExec("CREATE INDEX project_date_start_idx ON windturbines_all_projects__uk(project_date_start);")
        postgisExec("CREATE INDEX project_date_end_idx ON windturbines_all_projects__uk(project_date_end);")
        postgisExec("CREATE INDEX project_date_operational_idx ON windturbines_all_projects__uk(project_date_operational);")

        LogMessage("Snapping all OSM turbine positions from historical import to latest OSM turbine positions...")

        # We assume if operational turbine is within 50 metres of imported OSM turbine position then operational turbine should replace imported position

        postgisExec("""
        UPDATE 
            windturbines_all_projects__uk allprojects
        SET 
            geom        = closestoperational.geom, 
            geom_27700  = ST_Transform(closestoperational.geom, 27700)
        FROM 
        (
            SELECT 
                ogc_fid, 
                (SELECT geom FROM windturbines_operational__uk WHERE ST_Distance(sq.geom::geography, geom::geography) = closestdistance LIMIT 1) geom
            FROM
            (
                SELECT 
                    ogc_fid, 
                    geom,
                    (SELECT MIN(ST_Distance(operational.geom::geography, allprojects_initial.geom::geography)) FROM windturbines_operational__uk operational) closestdistance
                FROM 
                    windturbines_all_projects__uk allprojects_initial
                WHERE 
                    allprojects_initial.source = 'OPENSTREETMAP'
            ) sq 
            WHERE 
                (closestdistance > 0) AND (closestdistance < 50)
        ) closestoperational
        WHERE 
            allprojects.ogc_fid = closestoperational.ogc_fid;
        """)

        LogMessage("All failed and successful wind turbine projects imported")

def getAllWindProjects():
    """
    Gets all wind projects
    """

    global WINDTURBINES_ALLPROJECTS_DATASET

    return postgisGetResultsAsDict("""
    SELECT *, 
    ST_X (ST_Transform (geom, 4326)) AS lng,
    ST_Y (ST_Transform (geom, 4326)) AS lat, 
    ST_X (geom_27700) AS x,
    ST_Y (geom_27700) AS y 
    FROM %s ORDER BY project_guid, lng, lat
    """, (AsIs(reformatTableName(WINDTURBINES_ALLPROJECTS_DATASET)), ))

def getAllLargeWindProjects():
    """
    Gets all large wind projects (>= WINDTURBINES_MIN_HEIGHTTIP height-to-tip)
    """

    global WINDTURBINES_ALLPROJECTS_DATASET, WINDTURBINES_MIN_HEIGHTTIP

    return postgisGetResultsAsDict("""
    SELECT *, 
    ST_X (ST_Transform (geom, 4326)) AS lng,
    ST_Y (ST_Transform (geom, 4326)) AS lat, 
    ST_X (geom_27700) AS x,
    ST_Y (geom_27700) AS y 
    FROM %s 
    WHERE turbine_tipheight >= %s
    ORDER BY project_guid, lng, lat 
    """, (AsIs(reformatTableName(WINDTURBINES_ALLPROJECTS_DATASET)), AsIs(WINDTURBINES_MIN_HEIGHTTIP), ))

def getOperationalBeforeDateWithinDistance(radiuspoints, date):
    """
    Gets number of operational wind turbines before 'date' and within 'distance'
    """

    if date == '': return None
    if date is None: return None
    date = str(date)
    radiuspoints = radiuspoints.loc[radiuspoints['project_date_operational'] != None]
    radiuspoints = radiuspoints.loc[radiuspoints['project_date_operational'] < datetime.strptime(date, '%Y-%m-%d').date()]

    return len(radiuspoints)

def getApprovedBeforeDateWithinDistance(radiuspoints, date):
    """
    Gets number of approved wind turbines before 'date' and within 'distance'
    """

    if date == '': return None
    if date is None: return None
    date = str(date)
    radiuspoints = radiuspoints.loc[radiuspoints['project_date_end'] != None]
    radiuspoints = radiuspoints.loc[radiuspoints['project_date_end'] < datetime.strptime(date, '%Y-%m-%d').date()]
    radiuspoints = radiuspoints[radiuspoints['project_status'].isin(['Decommissioned', 'Application Granted', 'Awaiting Construction', 'Under Construction', 'Operational'])]

    return len(radiuspoints)


def getAppliedBeforeDateWithinDistance(radiuspoints, date):
    """
    Gets number of wind turbine applications before 'date' and within 'distance'
    """

    if date == '': return None
    if date is None: return None
    date = str(date)
    radiuspoints = radiuspoints.loc[radiuspoints['project_date_start'] != None]
    radiuspoints = radiuspoints.loc[radiuspoints['project_date_start'] < datetime.strptime(date, '%Y-%m-%d').date()]
    radiuspoints = radiuspoints[radiuspoints['project_status'].isin(['Application Submitted', 'Appeal Lodged'])]

    return len(radiuspoints)
 
def getRejectedBeforeDateWithinDistance(radiuspoints, date):
    """
    Gets number of rejected wind turbines before 'date' and within 'distance'
    """

    if date == '': return None
    if date is None: return None
    date = str(date)
    radiuspoints = radiuspoints.loc[radiuspoints['project_date_end'] != None]
    radiuspoints = radiuspoints.loc[radiuspoints['project_date_end'] < datetime.strptime(date, '%Y-%m-%d').date()]
    radiuspoints = radiuspoints[radiuspoints['project_status'].isin(['Application Refused', 'Appeal Refused', 'Appeal Withdrawn'])]

    return len(radiuspoints)

def initialiseAllLargeWindProjectsDataFrame(boundingbox=None):
    """
    Initialises turbine data frame with all large turbine positions
    """

    global ALLTURBINES_DF, WINDTURBINES_MIN_HEIGHTTIP

    if ALLTURBINES_DF is None:
        if boundingbox is None:
            LogMessage("Loading all large turbine positions into dataframe...")
            ALLTURBINES_DF = pd.DataFrame(postgisGetResultsAsDict(\
                "SELECT ST_X(geom_27700) x, ST_Y(geom_27700) y, * FROM windturbines_all_projects__uk WHERE turbine_tipheight >= " + str(WINDTURBINES_MIN_HEIGHTTIP) + ";"))
        else:
            boundingbox_str = ",".join([str(boundingbox['left']), str(boundingbox['bottom']), str(boundingbox['right']), str(boundingbox['top'])])
            LogMessage("Loading all large turbine positions within bounding box [" + boundingbox_str + "] into dataframe...")
            ALLTURBINES_DF = pd.DataFrame(postgisGetResultsAsDict(\
                "SELECT ST_X(geom_27700) x, ST_Y(geom_27700) y, * FROM windturbines_all_projects__uk WHERE turbine_tipheight >= " + \
                    str(WINDTURBINES_MIN_HEIGHTTIP) + " AND (geom_27700 @ ST_MakeEnvelope(%s, %s, %s, %s, 27700));", \
                (AsIs(boundingbox['left']), AsIs(boundingbox['bottom']), AsIs(boundingbox['right']), AsIs(boundingbox['top']), )))
        LogMessage("All large turbine positions loaded into dataframe, size: " + str(len(ALLTURBINES_DF)))

def runRadiusSearch(searchposition, distance, REPD, boundingbox=None):
    """
    Runs radius search on all turbines within 'distance' of 'searchposition'
    """

    global ALLTURBINES_DF, ALLTURBINES_GDF

    initialiseAllLargeWindProjectsDataFrame(boundingbox)

    if (ALLTURBINES_GDF is None) or (REPD is not None):
        if REPD is None: df_otherprojects = ALLTURBINES_DF
        else: df_otherprojects = ALLTURBINES_DF.loc[ALLTURBINES_DF['project_guid'] != REPD]

        ALLTURBINES_GDF = gpd.GeoDataFrame(
            df_otherprojects,
            geometry=gpd.points_from_xy(
                df_otherprojects["x"],
                df_otherprojects["y"],
            ),
            crs="EPSG:27700",
        )

    poi_df = pd.DataFrame([searchposition])
    poi_gdf = gpd.GeoDataFrame(
        poi_df,
        geometry=gpd.points_from_xy(
            poi_df['x'],
            poi_df['y'],
        ),
        crs="EPSG:27700",
    )

    # x = poi_gdf.buffer(distance).union_all()
    # neighbours = ALLTURBINES_GDF["geometry"].intersection(x)
    # neighbours = ALLTURBINES_GDF[~neighbours.is_empty]

    xmin, ymin, xmax, ymax = (searchposition['x'] - distance), (searchposition['y'] - distance), (searchposition['x'] + distance), (searchposition['y'] + distance) 
    allturbines_bounded = ALLTURBINES_GDF.cx[xmin:xmax, ymin:ymax]
    if len(allturbines_bounded) == 0: return None

    # neighbours = ALLTURBINES_GDF.sjoin_nearest(poi_gdf, max_distance=distance)
    neighbours = allturbines_bounded.sjoin_nearest(poi_gdf, max_distance=distance)
    neighbours = neighbours[neighbours.index != poi_gdf.index[0]]

    return neighbours

def getOperationalBeforeDateWithinDistanceLegacy(date, position, distance):
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
    ST_Distance(ST_SetSRID(ST_MakePoint(%s, %s), 27700), geom_27700) < %s;
    """, (date, position['x'], position['y'], distance, ))
    return results[0][0]

def getApprovedBeforeDateWithinDistanceLegacy(date, position, distance):
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
    ST_Distance(ST_SetSRID(ST_MakePoint(%s, %s), 27700), geom_27700) < %s;
    """, (date, position['x'], position['y'], distance, ))
    return results[0][0]

def getAppliedBeforeDateWithinDistanceLegacy(date, position, distance):
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
    ST_Distance(ST_SetSRID(ST_MakePoint(%s, %s), 27700), geom_27700) < %s;
    """, (date, position['x'], position['y'], distance, ))
    return results[0][0]

def getRejectedBeforeDateWithinDistanceLegacy(date, position, distance):
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
    ST_Distance(ST_SetSRID(ST_MakePoint(%s, %s), 27700), geom_27700) < %s;
    """, (date, position['x'], position['y'], distance, ))
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

    global POLITICAL_CACHE

    average_key = 'average_' + str(year)

    if average_key not in POLITICAL_CACHE:

        results = postgisGetResultsAsDict("""
        SELECT 
        SUM(political.total::int) AS political_total, 
        SUM(political.con::int) AS political_con, 
        SUM(political.lab::int) AS political_lab, 
        SUM(political.ld::int) AS political_ld, 
        SUM(political.other::int) AS political_other, 
        SUM(political.nat::int) AS political_nat,
        '-' AS political_majority
        FROM 
        sitepredictor__political__uk political
        WHERE 
        political.year = %s 
        GROUP BY political.year
        """, (year, ))

        # Compute proportions
        if len(results) != 0:
            for result in results:
                total = int(result['political_total'])
                result['political_proportion_con'] = float(result['political_con']) / total
                result['political_proportion_lab'] = float(result['political_lab']) / total
                result['political_proportion_ld'] = float(result['political_ld']) / total
                result['political_proportion_other'] = float(result['political_other']) / total
                result['political_proportion_nat'] = float(result['political_nat']) / total

        POLITICAL_CACHE[average_key] = results[0]

    return POLITICAL_CACHE[average_key]

def getPolitical(position, year):
    """
    Gets political breakdown of council for geographical position and year
    """

    global POLITICAL_CACHE

    council = convertPosition2Council(position)

    if council is None: return None

    political_key = str(year) + '_' + council

    if political_key not in POLITICAL_CACHE:

        results = postgisGetResultsAsDict("""
        SELECT 
        total political_total, 
        con political_con, 
        lab political_lab, 
        ld political_ld, 
        other political_other, 
        nat political_nat,
        majority political_majority
        FROM sitepredictor__political__uk 
        WHERE year = %s AND area = %s;""", (year, council, ))

        # Compute proportions
        if len(results) != 0:
            for result in results:
                total = int(result['political_total'])
                result['political_proportion_con'] = float(result['political_con']) / total
                result['political_proportion_lab'] = float(result['political_lab']) / total
                result['political_proportion_ld'] = float(result['political_ld']) / total
                result['political_proportion_other'] = float(result['political_other']) / total
                result['political_proportion_nat'] = float(result['political_nat']) / total

            if len(results) > 1:
                LogError("More than one set of political data for council: " + political_key)
                print(len(results), json.dumps(results, indent=4))
                # exit()

            results = results[0]
        else:
            results = getPoliticalAverage(year)

        POLITICAL_CACHE[political_key] = results

    return POLITICAL_CACHE[political_key]

def convertPosition2Geocode(position):
    """
    Converts position to census Geocode using cache
    """

    global GEOCODE_POSITION_LOOKUP

    position_index = str(position['lng']) + '_' + str(position['lat'])

    if position_index not in GEOCODE_POSITION_LOOKUP:

        results = postgisGetResults("""
        SELECT geo_code FROM sitepredictor__census_geography__uk WHERE ST_Intersects(geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
        """, (position['lng'], position['lat'], ))

        if len(results) == 0: GEOCODE_POSITION_LOOKUP[position_index] = None
        else: GEOCODE_POSITION_LOOKUP[position_index] = results[0][0]

    return GEOCODE_POSITION_LOOKUP[position_index]

def convertPosition2Council(position):
    """
    Converts position to council name using cache
    """

    global COUNCIL_POSITION_LOOKUP

    position_index = str(position['lng']) + '_' + str(position['lat'])

    if position_index not in COUNCIL_POSITION_LOOKUP:

        # In the event of point being in more than one council, we select smallest council
        results = postgisGetResults("""
        SELECT name FROM sitepredictor__councils__uk WHERE ST_Intersects(geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326)) 
        ORDER BY ST_Area(ST_Transform(geom, 27700)) ASC
        """, (position['lng'], position['lat'], ))

        if len(results) == 0: COUNCIL_POSITION_LOOKUP[position_index] = None
        else: COUNCIL_POSITION_LOOKUP[position_index] = results[0][0]

    return COUNCIL_POSITION_LOOKUP[position_index]

def populateLookupsWithAllTurbines():
    """
    Populates Geocode and council lookup with all turbines
    """

    global GEOCODE_POSITION_LOOKUP, COUNCIL_POSITION_LOOKUP

    LogMessage("Populating lookup tables with all turbines...")

    results = postgisGetResultsAsDict("""
    SELECT ST_X(turbine.geom) lng, ST_Y(turbine.geom) lat, area.geo_code geocode
    FROM windturbines_all_projects__uk turbine, sitepredictor__census_geography__uk area 
    WHERE ST_Intersects(turbine.geom, area.geom);""")

    for result in results:
        GEOCODE_POSITION_LOOKUP[str(result['lng']) + '_' + str(result['lat'])] = result['geocode']

    results = postgisGetResultsAsDict("""
    SELECT ST_X(turbine.geom) lng, ST_Y(turbine.geom) lat, area.name council
    FROM windturbines_all_projects__uk turbine, sitepredictor__councils__uk area 
    WHERE ST_Intersects(turbine.geom, area.geom);""")

    for result in results:
        COUNCIL_POSITION_LOOKUP[str(result['lng']) + '_' + str(result['lat'])] = result['council']

    LogMessage("Finished populating lookup tables")

def populateLookupsWithSamplingGrid(batch_index, batch_grid_spacing):
    """
    Populates Geocode and council lookup and windspeed cache with all sampling grid positions
    """

    global GEOCODE_POSITION_LOOKUP, COUNCIL_POSITION_LOOKUP, SAMPLING_GRID, WINDSPEED_DATASET, WINDSPEED_CACHE

    sampling_grid_to_use = SAMPLING_GRID
    if batch_index is not None: sampling_grid_to_use = buildBatchSamplingGridTableName(batch_index, batch_grid_spacing)

    LogMessage("Populating lookup tables with all sampling positions...")

    LogMessage("Populating lookup tables with census areas")

    results = postgisGetResultsAsDict("""
    SELECT ST_X(turbine.geom) lng, ST_Y(turbine.geom) lat, area.geo_code geocode
    FROM %s turbine, sitepredictor__census_geography__uk area 
    WHERE ST_Intersects(turbine.geom, area.geom);""", (AsIs(sampling_grid_to_use), ))

    for result in results:
        GEOCODE_POSITION_LOOKUP[str(result['lng']) + '_' + str(result['lat'])] = result['geocode']

    LogMessage("Populating lookup tables with council areas")

    if not postgisCheckColumnExists('sitepredictor__councils__uk', 'size'):

        LogMessage("Creating 'size' column on sitepredictor__councils__uk to reduce query time")

        postgisExec("ALTER TABLE sitepredictor__councils__uk ADD size INT;")
        postgisExec("UPDATE sitepredictor__councils__uk SET size = (ST_Area(ST_Transform(geom, 27700))/1000000);")
        postgisExec("CREATE INDEX ON sitepredictor__councils__uk (size);")

    results = postgisGetResultsAsDict("""
    SELECT ST_X(turbine.geom) lng, ST_Y(turbine.geom) lat, area.name council
    FROM %s turbine, sitepredictor__councils__uk area 
    WHERE ST_Intersects(turbine.geom, area.geom) ORDER BY area.size DESC;""", (AsIs(sampling_grid_to_use), ))

    for result in results:
        COUNCIL_POSITION_LOOKUP[str(result['lng']) + '_' + str(result['lat'])] = result['council']

    LogMessage("Populating lookup tables with windspeeds")

    results = postgisGetResultsAsDict("""
    SELECT ST_X(turbine.geom) lng, ST_Y(turbine.geom) lat, windspeed.windspeed
    FROM %s turbine, %s windspeed 
    WHERE ST_Intersects(turbine.geom, windspeed.geom) ORDER BY windspeed;""", (AsIs(sampling_grid_to_use), AsIs(reformatTableName(WINDSPEED_DATASET)), ))

    for result in results:
        WINDSPEED_CACHE[str(result['lng']) + '_' + str(result['lat'])] = result['windspeed']

    LogMessage("Finished populating lookup tables")

def getSpecificCensusSingleGeography(position, category):
    """
    Get specific census data for single geography containing position using category
    """

    global CENSUS_CACHE

    geocode = convertPosition2Geocode(position)

    if geocode is None: return None

    # Attempt to retrieve data from memory cache

    if geocode not in CENSUS_CACHE: CENSUS_CACHE[geocode] = {}
    if category in CENSUS_CACHE[geocode]: return CENSUS_CACHE[geocode][category]

    # If nothing in cache, run PostGIS query

    census_data_table = 'sitepredictor__census_2011_' + category + '__uk'
    results = postgisGetResultsAsDict("""
    SELECT total """ + category + """_total, * FROM %s WHERE geo_code = %s""", (AsIs(census_data_table), geocode, ))

    if len(results) == 0:
        print("Error retrieving census data for", category, geocode, position)
        exit()

    if len(results) > 1:
        print("Retrieving more than one record for census data", category, geocode, position)
        exit()

    aggregateresults = {}
    result = results[0]
    delete_fields = ['ogc_fid', 'geo_code', 'date', 'geography', 'geom']
    # Existing age data is broken down by year which is too much granularity so aggregate
    final_result = result
    if category == 'age':
        finalresults = groupAgeData(result)
    else:
        for field in final_result.keys():
            if field in delete_fields: continue
            aggregateresults[field] = int(final_result[field])

        total = aggregateresults['total']
        del aggregateresults['total']
        aggregateresults[category + '_total'] = total

        finalresults = json.loads(json.dumps(aggregateresults))
        for field in aggregateresults.keys():
            if 'total' in field: continue
            if '__prop' in field: continue
            finalresults[field + '__prop'] = aggregateresults[field] / total

    CENSUS_CACHE[geocode][category] = finalresults

    return finalresults

def groupAgeData(result):
    """
    Groups fine-grained age data into smaller 'number_ranges' groups
    eg. if number_ranges = 5 then groups of 0-19, 20-39, etc (and add in 100 to 80-99)
    """

    number_ranges = 5
    max_value = 100
    # We assume exact division of max_value into number_ranges
    steps = int(max_value / number_ranges)

    result['age_0'] = result['age_under_1']
    result['age_100'] = result['age_100_over']

    median_position = float(result['age_total']) / 2

    final_result = {'age_total': result['age_total']}
    weighted_total, median, median_count, running_total = 0, None, 0, 0
    for step_index in range(steps):

        step_start = step_index * number_ranges
        step_end = ((step_index + 1) * number_ranges) - 1
        step_total = 0

        for individual_step_index in range(step_start, step_end + 1):
            age_frequency = int(result['age_' + str(individual_step_index)])
            step_total += age_frequency
            running_total += age_frequency
            median_count += age_frequency
            weighted_total += (individual_step_index * age_frequency)
            if (median is None) and (median_count >= median_position): median = individual_step_index

        if step_index == (steps - 1):
            step_end += 1
            last_age_frequency = int(result['age_' + str(step_end)])
            weighted_total += (step_end * last_age_frequency)
            step_total += last_age_frequency
            running_total += last_age_frequency

        final_result['age_range_' + str(step_start) + "_" + str(step_end) + '__prop'] = step_total / int(result['age_total'])

    final_result['age_mean'] = weighted_total / int(result['age_total'])
    final_result['age_median'] = median

    return final_result

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
        # Existing age data is broken down by year which is too much granularity so aggregate
        final_result = result
        if category == 'age': final_result = groupAgeData(result)
        for field in final_result.keys():
            if field in delete_fields: continue
            # As we're summing all values, proportional '__pro' field should be ignored
            if '__pro' in field: continue
            if field not in aggregateresults: aggregateresults[field] = int(final_result[field])
            else: aggregateresults[field] += int(final_result[field])

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
        if census_data is None: return None
        for data_field in census_data.keys():
            # Non-proportional values are unlikely to be useful unless in special cases, ie. mean, median, total
            if  ('mean' not in data_field) and \
                ('median' not in data_field) and \
                ('total' not in data_field) and \
                ('__prop' not in data_field): continue
            data_field_readable = data_field.replace('__prop', '_proportional')
            final_fields[data_field_readable] = census_data[data_field]

    return final_fields

def getCountry(position):
    """
    Gets country of turbine using letter prefix of census geographies
    """

    geocode = convertPosition2Geocode(position)

    if geocode is None: return None
    if geocode.startswith("E"): return 'England'
    if geocode.startswith("W"): return 'Wales'
    if geocode.startswith("S"): return 'Scotland'
    if geocode.startswith("N"): return 'Northern Ireland'

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

    scratch_table_3 = '_scratch_table_12'

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
        'listed_buildings__uk__pro__27700': {
            'multiply_number_points_by_area': (3.14 * 50 * 50) / 1000000
        }
    }

    scratch_table_1 = '_scratch_table_10'
    scratch_table_2 = '_scratch_table_11'

    viewshed_geojson = getViewshed(position, height)

    if postgisCheckTableExists(scratch_table_1): postgisDropTable(scratch_table_1)
    if postgisCheckTableExists(scratch_table_2): postgisDropTable(scratch_table_2)

    postgisExec("CREATE TABLE %s (geom geometry)", (AsIs(scratch_table_1), ))
    postgisExec("CREATE INDEX %s ON %s USING GIST (geom);", (AsIs(scratch_table_1 + '_idx'), AsIs(scratch_table_1), ))

    for feature in viewshed_geojson['features']:
        postgisExec("INSERT INTO %s VALUES (ST_Transform(ST_GeomFromGeoJSON(%s), 27700))", (AsIs(scratch_table_1), json.dumps(feature['geometry']), ))

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
            readable_category = category.replace('__uk__pro__27700', '')
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

def createTableDistanceCache(table_parameters):
    """
    Creates distance cache for specific table
    """

    global DISTANCE_CACHE_TABLE, WINDTURBINES_ALLPROJECTS_DATASET

    table, table_index, table_count = table_parameters[0], table_parameters[1], table_parameters[2]
    search_bounding_box_size = 10000
    windturbines_all_table = reformatTableName(WINDTURBINES_ALLPROJECTS_DATASET)

    LogMessage("************ STARTING DISTANCE CACHE CREATION: " + table + " ************")
    LogMessage("Creating bulk point-to-feature distance cache for table: " + table + " (" + str(table_index) + "/" + str(table_count) + ")")
    postgisExec("DELETE FROM %s WHERE table_name = %s", (AsIs(DISTANCE_CACHE_TABLE), table, ))

    all_turbines = postgisGetResults("SELECT ogc_fid FROM %s;", (AsIs(windturbines_all_table), ))
    number_turbines = len(all_turbines)
    scratch_table_1 = '_sp_dis_' + table

    num_outside_bounding_box = 0
    for count in range(len(all_turbines)):

        if count % 1000 == 0:
            LogMessage("Getting minimum distance to " + table + " for turbine: " + str(count + 1) + "/" + str(number_turbines))

        turbine_fid = all_turbines[count][0]

        if postgisCheckTableExists(scratch_table_1): postgisDropTable(scratch_table_1)

        # Create search bounding box to speed up MIN(ST_Distance)
        postgisExec("""
        CREATE TABLE %s AS
        SELECT dataset.geom FROM %s dataset, 
        (SELECT ST_Envelope(ST_Buffer(ST_Transform(geom, 27700), %s)) geom FROM %s WHERE ogc_fid=%s) boundingbox
        WHERE ST_Intersects(dataset.geom, boundingbox.geom);
        """, (AsIs(scratch_table_1), AsIs(table), AsIs(search_bounding_box_size), AsIs(windturbines_all_table), turbine_fid))
        postgisExec("CREATE INDEX %s ON %s USING GIST (geom);", (AsIs(scratch_table_1 + "_idx"), AsIs(scratch_table_1), ))

        # Check to see if any features within bounding box
        # - if no, use global search
        # - if yes, use to select nearest feature

        num_features = postgisGetResults("SELECT COUNT(*) FROM %s;", (AsIs(scratch_table_1), ))
        num_features = num_features[0][0]
        if num_features == 0: search_table = table
        else: search_table = scratch_table_1

        if num_features == 0: 
            # LogMessage("No features found within bounding box of turbine " + str(turbine_fid) + " for " + table)
            num_outside_bounding_box += 1
        else:
            num_outside_bounding_box -= 1

        postgisExec("""
        INSERT INTO %s 
        SELECT %s AS ogc_fid, %s AS table_name, MIN(ST_Distance(ST_Transform(turbine.geom, 27700), dataset.geom)) AS distance 
        FROM (SELECT ogc_fid, geom FROM %s WHERE ogc_fid=%s) turbine, %s dataset GROUP BY turbine.ogc_fid
        """, (AsIs(DISTANCE_CACHE_TABLE), AsIs(turbine_fid), table, AsIs(windturbines_all_table), AsIs(turbine_fid), AsIs(search_table), ))

        postgisExec("""
        UPDATE %s cache SET distance = 
        (
            SELECT -MIN(ST_Distance(ST_Transform(turbine.geom, 27700), ST_ExteriorRing(dataset.geom))) FROM 
            windturbines_all_projects__uk turbine, %s dataset
            WHERE turbine.ogc_fid = cache.ogc_fid AND ST_Contains(dataset.geom, ST_Transform(turbine.geom, 27700))
        )
        WHERE 
        cache.distance = 0 AND cache.table_name = %s AND cache.ogc_fid = %s;
        """, (AsIs(DISTANCE_CACHE_TABLE), AsIs(search_table), table, AsIs(turbine_fid), ))

        # If bounding box consistently too small then double size (as many times as necessary until excluded numbers drop)
        if num_outside_bounding_box > 50:
            search_bounding_box_size = (search_bounding_box_size * 2)
            LogMessage("Increasing bounding box for " + table + " to " + str(search_bounding_box_size / 1000) + " km")
            num_outside_bounding_box = 0

        if postgisCheckTableExists(scratch_table_1): postgisDropTable(scratch_table_1)

    LogMessage("************ ENDING DISTANCE CACHE CREATION: " + table + " ************")

def createDistanceCache(tables):
    """
    Runs efficient PostGIS queries across entire dataset to save time
    """

    global DISTANCE_CACHE_TABLE, WINDTURBINES_ALLPROJECTS_DATASET

    windturbines_all_table = reformatTableName(WINDTURBINES_ALLPROJECTS_DATASET)

    if not postgisCheckTableExists(DISTANCE_CACHE_TABLE):
        postgisExec("CREATE TABLE %s (ogc_fid INTEGER, table_name VARCHAR(70), distance DOUBLE PRECISION)", (AsIs(DISTANCE_CACHE_TABLE), ))
        postgisExec("CREATE INDEX ON %s (ogc_fid)", (AsIs(DISTANCE_CACHE_TABLE), ))
        postgisExec("CREATE INDEX ON %s (table_name)", (AsIs(DISTANCE_CACHE_TABLE), ))

    all_turbines = postgisGetResults("SELECT ogc_fid FROM %s;", (AsIs(windturbines_all_table), ))
    number_turbines = len(all_turbines)
    table_index = 0

    multiprocessing_tables_to_process = []
    for table in tables:
        table_index += 1
        number_cached_records = postgisGetResults("SELECT COUNT(*) FROM %s WHERE table_name = %s", (AsIs(DISTANCE_CACHE_TABLE), table, ))
        number_cached_records = number_cached_records[0][0]
        if number_cached_records != number_turbines:
            multiprocessing_tables_to_process.append([table, table_index, len(tables)])

    if len(multiprocessing_tables_to_process) != 0:
        LogMessage("************************************************")
        LogMessage("********** STARTING MULTIPROCESSING ************")
        LogMessage("************************************************")

        # Run multiprocessing pool
        with Pool(None) as p:
            p.map(createTableDistanceCache, multiprocessing_tables_to_process)

        LogMessage("************************************************")
        LogMessage("*********** ENDING MULTIPROCESSING *************")
        LogMessage("************************************************")


def createBatchGrid(runtest, batch_grid_spacing):
    """
    Creates batch grid for multiprocessing
    """

    global TEST_POINT

    if batch_grid_spacing is None: return None

    batch_grid_table = buildBatchGridTableName(runtest, batch_grid_spacing)

    if not postgisCheckTableExists(batch_grid_table):

        LogMessage("Creating batch processing grid overlay for multiprocessing")

        postgisExec("CREATE TABLE %s AS SELECT (ST_SquareGrid(%s, ST_Transform(geom, 27700))).geom geom FROM overall_clipping__union;",
                    (AsIs(batch_grid_table), AsIs(batch_grid_spacing), ))
        postgisExec("ALTER TABLE %s ADD COLUMN temp_id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY", (AsIs(batch_grid_table), ))
        postgisExec("DELETE FROM %s WHERE temp_id IN (SELECT grid.temp_id FROM %s grid, overall_clipping__union clipping WHERE ST_Intersects(ST_Transform(grid.geom, 4326), clipping.geom) IS FALSE);", \
                    (AsIs(batch_grid_table), AsIs(batch_grid_table), ))
        postgisExec("CREATE INDEX %s ON %s USING GIST (geom);", (AsIs(batch_grid_table + "_idx"), AsIs(batch_grid_table), ))

        # If running test, only select batch grid square that covers TEST_POINT
        if runtest:
            postgisExec("DELETE FROM %s WHERE ST_Intersects(geom, ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), 27700)) = FALSE", (AsIs(batch_grid_table), TEST_POINT['lng'], TEST_POINT['lat'], ))

        postgisExec("ALTER TABLE %s DROP COLUMN temp_id", (AsIs(batch_grid_table), ))
        postgisExec("ALTER TABLE %s ADD COLUMN id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY", (AsIs(batch_grid_table), ))

    number_batches = postgisGetResults("SELECT COUNT(*) FROM %s;", (AsIs(batch_grid_table), ))
    number_batches = number_batches[0][0]

    LogMessage("Total number of batches: " + str(number_batches))

    return number_batches

def createSamplingGrid(runtest, batch_index, batch_grid_spacing, raster_resolution):
    """
    Creates sampling grid for use in building final result maps
    """

    global SAMPLING_GRID

    if (batch_index is not None) and (batch_grid_spacing is not None):

        batch_sampling_grid = buildBatchSamplingGridTableName(batch_index, batch_grid_spacing)
        batch_grid_table = buildBatchGridTableName(runtest, batch_grid_spacing)
        batch_cell_table = buildBatchCellTableName(batch_index, batch_grid_spacing)
        number_batches = postgisGetResults("SELECT COUNT(*) FROM %s;", (AsIs(batch_grid_table), ))
        number_batches = number_batches[0][0]

        if not postgisCheckTableExists(batch_cell_table):

            # LogMessage("Creating individual batch cell for multiprocessing")

            postgisExec("CREATE TABLE %s AS SELECT geom FROM %s WHERE id = %s", \
                        (AsIs(batch_cell_table), AsIs(batch_grid_table), batch_index, ))
            postgisExec("CREATE INDEX %s ON %s USING GIST (geom);", (AsIs(batch_cell_table + "_idx"), AsIs(batch_cell_table), ))

        if postgisCheckTableExists(batch_sampling_grid): postgisDropTable(batch_sampling_grid)

        LogMessage("Creating batch sampling grid for batch " + str(batch_index) + "/" + str(number_batches) + " with points spaced at " + str(raster_resolution) + " metres")

        # Note: It's important raster_resolution is float when sent to ST_AsRaster
        # otherwise interpreted as number of rows/columns rather than size of rows/columns
        postgisExec("""
        CREATE TABLE %s AS
        (
            SELECT 
                ST_X(ST_Transform(samplepoints.samplepoint, 27700)) easting,
                ST_Y(ST_Transform(samplepoints.samplepoint, 27700)) northing,
                samplepoints.samplepoint geom
            FROM
            (
                SELECT ST_Transform((ST_PixelAsCentroids(ST_AsRaster(ST_Transform(geom, 27700), %s, %s))).geom, 4326) samplepoint FROM %s WHERE id = %s
            ) samplepoints 
        );
        """, (AsIs(batch_sampling_grid), AsIs(float(raster_resolution)), AsIs(float(raster_resolution)), AsIs(batch_grid_table), AsIs(batch_index), ))

        postgisExec("ALTER TABLE %s ADD COLUMN temp_id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY", (AsIs(batch_sampling_grid), ))
        postgisExec("DELETE FROM %s WHERE temp_id IN (SELECT grid.temp_id FROM %s grid, overall_clipping__union clipping WHERE ST_Intersects(grid.geom, clipping.geom) IS FALSE);", \
                    (AsIs(batch_sampling_grid), AsIs(batch_sampling_grid), ))
        postgisExec("ALTER TABLE %s DROP COLUMN temp_id", (AsIs(batch_sampling_grid), ))
        postgisExec("ALTER TABLE %s ADD COLUMN id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY;", (AsIs(batch_sampling_grid), ))

    else:
        if not postgisCheckTableExists(SAMPLING_GRID):

            LogMessage("Creating sampling grid with points spaced at " + str(raster_resolution) + " metres")

            # Note: It's important raster_resolution is float when sent to ST_AsRaster
            # otherwise interpreted as number of rows/columns rather than size of rows/columns

            postgisExec("""
            CREATE TABLE %s AS
            (
                SELECT 
                    ST_X(ST_Transform(samplepoints.samplepoint, 27700)) easting,
                    ST_Y(ST_Transform(samplepoints.samplepoint, 27700)) northing,
                    samplepoints.samplepoint geom
                FROM
                (
                    SELECT ST_Transform((ST_PixelAsCentroids(ST_AsRaster(ST_Transform(geom, 27700), %s, %s))).geom, 4326) samplepoint FROM overall_clipping__union
                ) samplepoints 
            );
            """, (AsIs(SAMPLING_GRID), AsIs(float(raster_resolution)), AsIs(float(raster_resolution)), ))
            postgisExec("ALTER TABLE %s ADD COLUMN id INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY;", (AsIs(SAMPLING_GRID), ))

def runAdditionalDownloads():
    """
    Carry out any additional downloads
    """

    global CENSUS_2011_ZIP_URL, ADDITIONAL_DOWNLOADS, DATASETS_FOLDER, LOCALAUTHORITY_CONVERSIONS

    census_2011_zip = 'census_2011.zip'

    if not isfile(census_2011_zip):

        LogMessage("Downloading and extracting 2011 census data...")

        attemptDownloadUntilSuccess(CENSUS_2011_ZIP_URL, census_2011_zip)
        with ZipFile(census_2011_zip, 'r') as zip_ref: zip_ref.extractall(DATASETS_FOLDER)

        LogMessage("2011 census data downloaded and extracted")

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
                while True:
                    attemptDownloadUntilSuccess(additional_download['url'], additional_download_path)
                    if file_extension != 'gpkg': break
                    # Attempt to get projection from any GPKG - if error, allow retry of download
                    if getGPKGProjection(additional_download_path) is not None: break
                    LogMessage("Retrying download after delay")
                    time.sleep(5)

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

    local_authority_canonical = getJSON(LOCALAUTHORITY_CONVERSIONS)
    for conversion_from in local_authority_canonical.keys():
        conversion_to = local_authority_canonical[conversion_from]
        postgisExec('UPDATE sitepredictor__political__uk SET area = %s WHERE area = %s', (conversion_to, conversion_from, ))
        postgisExec('DELETE FROM sitepredictor__councils__uk WHERE name = %s', (conversion_from, ))

def createDistanceRasters(raster_resolution, tables, batch_index, batch_grid_spacing):
    """
    Creates distance rasters for tables
    """

    global RASTER_OUTPUT_FOLDER

    # Create folder for rasters
    makeFolder(RASTER_OUTPUT_FOLDER)

    for table in tables:

        feature_raster = RASTER_OUTPUT_FOLDER + table + '.tif'
        distance_raster = getDistanceRasterPath(raster_resolution, table)

        if batch_index is None:
            if not isfile(distance_raster):
                createFeaturesRaster(raster_resolution, table, feature_raster)
                createDistanceRaster(raster_resolution, feature_raster, distance_raster, batch_index, batch_grid_spacing)
        else:
            batch_distance_raster = buildBatchRasterFilename(raster_resolution, distance_raster, batch_index, batch_grid_spacing)
            if not isfile(batch_distance_raster):
                createDistanceRaster(raster_resolution, feature_raster, distance_raster, batch_index, batch_grid_spacing)

        if isfile(feature_raster): os.remove(feature_raster)

def deleteDistanceRasters(raster_resolution, tables, batch_index, batch_grid_spacing):
    """
    Deletes distance rasters for tables
    """

    for table in tables:

        distance_raster = getDistanceRasterPath(raster_resolution, table)
        distance_batch_output = buildBatchRasterFilename(raster_resolution, distance_raster, batch_index, batch_grid_spacing)
        if isfile(distance_batch_output): os.remove(distance_batch_output)

def createSpacedGrid(position_start, spacing_metres, num_rows, num_cols):
    """
    Creates grid of points starting at position_start with num_rows and num_cols spaced by spacing_metres
    """

    start_x, start_y = lnglat_to_bngrs(position_start['lng'], position_start['lat'])

    spaced_grid = []
    current_x = start_x
    for x in range(num_cols):
        current_y = start_y
        for y in range(num_rows):
            current_lng, current_lat = bngrs_to_lnglat(current_x, current_y)
            spaced_grid.append({'lng': current_lng, 'lat': current_lat})
            current_y += spacing_metres
        current_x += spacing_metres

    return spaced_grid

def getSampleGrid(batch_index, batch_grid_spacing):
    """
    Gets entire sample grid as array
    """

    global SAMPLING_GRID

    if batch_index is None:
        return postgisGetResultsAsDict("SELECT easting, northing, ST_X(geom) lng, ST_Y(geom) lat FROM %s ORDER BY easting, northing;", (AsIs(SAMPLING_GRID), ))
    else:
        batch_sampling_grid_cell = buildBatchSamplingGridTableName(batch_index, batch_grid_spacing)
        return postgisGetResultsAsDict("SELECT easting, northing, ST_X(geom) lng, ST_Y(geom) lat FROM %s ORDER BY easting, northing;", (AsIs(batch_sampling_grid_cell), ))

def getSamplingGridBatchNumberPoints(batch_parameters):
    """
    Get total number of points for single batch grid square
    """

    runtest, batch_index, batch_grid_spacing, raster_resolution = batch_parameters[0], batch_parameters[1], batch_parameters[2], batch_parameters[3]
    batch_cell_table = buildBatchCellTableName(batch_index, batch_grid_spacing)
    batch_sampling_grid_table = buildBatchSamplingGridTableName(batch_index, batch_grid_spacing)
    createSamplingGrid(runtest, batch_index, batch_grid_spacing, raster_resolution)
    if postgisCheckTableExists(batch_sampling_grid_table): 
        points_in_batch = postgisGetResults("SELECT COUNT(*) FROM %s;", (AsIs(batch_sampling_grid_table), ))
        points_in_batch = points_in_batch[0][0]
        with cnt.get_lock(): cnt.value += points_in_batch
        postgisDropTable(batch_sampling_grid_table)
    if postgisCheckTableExists(batch_cell_table): postgisDropTable(batch_cell_table)

def getSamplingGridNumberPoints(runtest, batch_grid_spacing, batch_number, raster_resolution):
    """
    Get total number of points by adding points within each batch grid square
    """

    multiprocessing_batch_values = [[runtest, batch_index, batch_grid_spacing, raster_resolution] for batch_index in range(1, (batch_number + 1))]

    cnt = Value('i', 0)
    # Run multiprocessing pool
    with Pool(initializer=init_globals, initargs=(cnt,)) as p:
        p.map(getSamplingGridBatchNumberPoints, multiprocessing_batch_values)

    return cnt.value

def createSamplingGridData(batch_values):
    """
    Generates sampling grid data, ie. same features created for all failed/successful wind turbines but for all sampling grid points
    """

    global OUTPUT_DATA_SAMPLEGRID

    batch_index, batch_grid_spacing, raster_resolution = None, None, None
    if (batch_values is not None):
        runtest, batch_index, batch_grid_spacing, raster_resolution = batch_values[0], batch_values[1], batch_values[2], batch_values[3]

    LogMessage("========================================")
    LogMessage("Starting batch: " + str(batch_index))
    LogMessage("========================================")

    # ************************************************************
    # ******************* CREATE SAMPLING GRID *******************
    # ************************************************************
    # Default, below, is to create sampling grid for whole of UK
    # If batch_index/batch_grid_spacing are set:
    # - Cut up UK into grid squares spaced at batch_grid_spacing metres
    # - Select grid square with index 'batch_index'
    createSamplingGrid(runtest, batch_index, batch_grid_spacing, raster_resolution)


    # ************************************************************
    # ***************** CREATE DISTANCE RASTERS ******************
    # ************************************************************

    # Create distance rasters to improve performance
    # - faster than querying PostGIS for every position

    # Get list of tables to run distance testing on
    tables_to_test_unprojected = removeNonEssentialTablesForDistance(postgisGetUKBasicProcessedTables())

    # Creates reprojected version of all testing tables to improve performance
    tables_to_test = []
    for table in tables_to_test_unprojected:
        tables_to_test.append(createTransformedTable(table))

    tables_to_test = removeNonEssentialTablesForDistance(tables_to_test)

    createDistanceRasters(raster_resolution, tables_to_test, batch_index, batch_grid_spacing)

    # ************************************************************
    # ********* LOAD SAMPLED POINTS AND START PROCESSING *********
    # ************************************************************

    LogMessage("Retrieving all points from sample grid with spacing: " + str(raster_resolution) + " metres")

    sample_grid = getSampleGrid(batch_index, batch_grid_spacing)

    LogMessage("Number of points in sample grid: " + str(len(sample_grid)))

    index, features = 0, []
    distance_ranges = [10, 20, 30, 40]
    max_distance_range = 1000 * max(distance_ranges)
    batch_sampling_grid_cell = buildBatchSamplingGridTableName(batch_index, batch_grid_spacing)
    boundingbox = postgisGetTableBounds(batch_sampling_grid_cell)
    boundingbox['left']    -= max_distance_range
    boundingbox['right']   += max_distance_range
    boundingbox['bottom']  -= max_distance_range
    boundingbox['top']     += max_distance_range
    output_data = buildBatchGridOutputData(buildOutputPath(runtest, OUTPUT_DATA_SAMPLEGRID, batch_grid_spacing, raster_resolution), batch_index, batch_grid_spacing)
    
    distances = []
    for index in range(len(sample_grid)): distances.append({})

    # With batching, we add distances one layer at a time after main processing has completed
    # Without batching, we create inmemory array of all distances, below

    if batch_index is None:

        LogMessage("Building array of distances from distance rasters for all points and all rasters...")

        for table in tables_to_test:
            LogMessage("Getting distances for: " + table)
            distance_raster = getDistanceRasterPath(raster_resolution, table)
            raster = rasterio.open(distance_raster)
            table_name_for_output = table.replace('__pro__27700', '')

            for index in range(len(sample_grid)):
                metric_point = (sample_grid[index]['easting'], sample_grid[index]['northing'])
                iterator = raster.sample([metric_point])
                for iterator_item in iterator: distance = iterator_item[0]
                distances[index]['distance__' + table_name_for_output] = float(distance)

            raster.close()

        LogMessage("Finished building array of distances")

    index, firstrowwritten, totalrecords, fieldnames = 0, False, len(sample_grid), None

    if isfile(output_data): os.remove(output_data)

    # Populate Geocode lookup to save time
    populateLookupsWithSamplingGrid(batch_index, batch_grid_spacing)

    with total.get_lock(): total_points = total.value

    added_to_count = 0
    timings = {'step1': 0, "step2": 0, "step3": 0, "step4": 0, "step5": 0, "step6": 0, "step7": 0}
    for index in range(len(sample_grid)):
        turbine = {}

        if index % 1000 == 0:
            with cnt.get_lock():
                LogMessage("Processing hypothetical turbine position: " + str(cnt.value) + "/" + str(total_points))
                # print(json.dumps(timings, indent=4))
                cnt.value += (index - added_to_count)
                added_to_count = index

        turbine['project_date_end'] = datetime.today().strftime('%Y-%m-%d')
        turbine['project_date_operational'] = None
        turbine['project_date_underconstruction'] = None
        turbine['project_date_start'] = datetime.today().strftime('%Y-%m-%d')
        turbine['project_year'] = datetime.today().strftime('%Y')

        # Improve ordering of fields

        LogStage("Step 1")

        # time_start = time.time()
        turbine_lnglat = {'lng': sample_grid[index]['lng'], 'lat': sample_grid[index]['lat']}
        turbine_xy = {'x': sample_grid[index]['easting'], 'y': sample_grid[index]['northing']}
        turbine['turbine_country'] = getCountry(turbine_lnglat)
        # timings['step1'] += (time.time() - time_start)
        if turbine['turbine_country'] is None: 
            LogMissingData("No country found for position: " + str(turbine_lnglat['lng']) + "," + str(turbine_lnglat['lat']))
            continue

        LogStage("Step 2")

        # time_start = time.time()
        turbine['turbine_elevation'] = getElevation(turbine_lnglat)[0]
        # timings['step2'] += (time.time() - time_start)

        LogStage("Step 3")

        turbine['turbine_grid_coordinates_srs'] = 'EPSG:27700'
        turbine['turbine_grid_coordinates_easting'] = sample_grid[index]['easting']
        turbine['turbine_grid_coordinates_northing'] = sample_grid[index]['northing']
        turbine['turbine_lnglat_lng'] = turbine_lnglat['lng']
        turbine['turbine_lnglat_lat'] = turbine_lnglat['lat']
        # time_start = time.time()
        turbine['windspeed'] = getWindSpeed(turbine_lnglat)
        # timings['step3'] += (time.time() - time_start)
        turbine['project_size'] = 1

        LogStage("Step 4")

        # time_start = time.time()
        census = getCensus(turbine_lnglat)
        # timings['step4'] += (time.time() - time_start)
        if census is None:
            LogMissingData("No census data for position: " + str(turbine_lnglat['lng']) + "," + str(turbine_lnglat['lat']))
            continue

        LogStage("Step 5")

        for census_key in census.keys(): turbine[census_key] = census[census_key]

        political = {
            'political_total': None,
            'political_con': None,
            'political_lab': None,
            'political_ld': None,
            'political_other': None,
            'political_nat': None,
            'political_proportion_con': None,
            'political_proportion_lab': None,
            'political_proportion_ld': None,
            'political_proportion_other': None,
            'political_proportion_nat': None,
        }

        year = str(int(datetime.today().strftime('%Y')) - 1)
        # time_start = time.time()
        political = getPolitical(turbine_lnglat, year)
        # timings['step5'] += (time.time() - time_start)

        if political is None:
            LogMissingData("No political data for point: " + str(turbine_lnglat['lng']) + "," + str(turbine_lnglat['lat']) + " so skipping")
            continue

        LogStage("Step 6")

        for political_key in political.keys(): turbine[political_key] = political[political_key]

        # time_start = time.time()
        for distance_range in distance_ranges:
            radiuspoints = runRadiusSearch(turbine_xy, 1000 * distance_range, None, boundingbox)
            if radiuspoints is None:
                turbine['count__operational_within_' + str(distance_range)+'km']    = 0
                turbine['count__approved_within_' + str(distance_range)+'km']       = 0
                turbine['count__applied_within_' + str(distance_range)+'km']        = 0
                turbine['count__rejected_within_' + str(distance_range)+'km']       = 0
            else:
                turbine['count__operational_within_' + str(distance_range)+'km']    = getOperationalBeforeDateWithinDistance(radiuspoints, turbine['project_date_end'])
                turbine['count__approved_within_' + str(distance_range)+'km']       = getApprovedBeforeDateWithinDistance(radiuspoints, turbine['project_date_end'])
                turbine['count__applied_within_' + str(distance_range)+'km']        = getAppliedBeforeDateWithinDistance(radiuspoints, turbine['project_date_end'])
                turbine['count__rejected_within_' + str(distance_range)+'km']       = getRejectedBeforeDateWithinDistance(radiuspoints, turbine['project_date_end'])
        # timings['step6'] += (time.time() - time_start)

        LogStage("Step 7")

        if batch_index is None:
            for distance_key in distances[index].keys(): turbine[distance_key] = distances[index][distance_key]

        # time_start = time.time()
        if not firstrowwritten:
            with open(output_data, 'w', newline='') as csvfile:
                fieldnames = turbine.keys()
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
            firstrowwritten = True

        with open(output_data, 'a', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writerow(turbine)
        # timings['step7'] += (time.time() - time_start)

        index += 1

    # For batched processing, add distances from batch rasters to turbine positions after finishing main processing
    if batch_index is not None:

        if isfile(output_data):
            for table in tables_to_test:
                table_name_for_output = table.replace('__pro__27700', '')
                distance_column = 'distance__' + table_name_for_output

                turbines, firstrowwritten = [], False
                with open(output_data, 'r', newline='', encoding="utf-8") as csvfile:
                    reader = csv.DictReader(csvfile)
                    for row in reader: turbines.append(row)

                if distance_column in turbines[0]:
                    LogMessage("Turbine output data already has distances for: " + table_name_for_output)
                    continue

                LogMessage("Getting distances from distance raster for: " + table)

                distance_raster = getDistanceRasterPath(raster_resolution, table)
                batch_distance_raster = buildBatchRasterFilename(raster_resolution, distance_raster, batch_index, batch_grid_spacing)
                raster = rasterio.open(batch_distance_raster)

                # Output results to temporary file and only copy over once processing has completed
                temp_data = str(batch_index) + '_temp.csv'
                if isfile(temp_data): os.remove(temp_data)
                firstrowwritten = False

                for turbine in turbines:
                    metric_point = (turbine['turbine_grid_coordinates_easting'], turbine['turbine_grid_coordinates_northing'])
                    iterator = raster.sample([metric_point])
                    for iterator_item in iterator: distance = iterator_item[0]
                    turbine[distance_column] = float(distance)

                    if not firstrowwritten:
                        with open(temp_data, 'w', newline='') as csvfile:
                            fieldnames = turbine.keys()
                            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                            writer.writeheader()
                        firstrowwritten = True

                    with open(temp_data, 'a', newline='') as csvfile:
                        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                        writer.writerow(turbine)

                raster.close()
                shutil.copy(temp_data, output_data)
                if isfile(temp_data): os.remove(temp_data)

    if (batch_index is not None) and (batch_grid_spacing is not None):
        batch_sampling_grid = buildBatchSamplingGridTableName(batch_index, batch_grid_spacing)
        if postgisCheckTableExists(batch_sampling_grid):
            LogMessage("Dropping batch sampling grid table: " + batch_sampling_grid)
            postgisDropTable(batch_sampling_grid)

        deleteDistanceRasters(raster_resolution, tables_to_test, batch_index, batch_grid_spacing)

    with cnt.get_lock():
        LogMessage("Processed hypothetical turbine position: " + str(cnt.value))
        cnt.value += (index - added_to_count)
        added_to_count = index

    LogMessage("========================================")
    LogMessage("Ending batch: " + str(batch_index))
    LogMessage("========================================")

def createAllTurbinesData():
    """
    Runs entire site predictor pipeline
    """

    global CENSUS_SEARCH_RADIUS, OUTPUT_DATA_ALLTURBINES, OUTPUT_FOLDER

    # Download all necessary OSM data
    osmDownloadData()

    # Make outputfolder
    makeFolder(OUTPUT_FOLDER)

    # download terrain GeoTIFF
    downloadTerrainGeoTIFF()

    # Download wind speed data
    downloadWindSpeeds()

    # Perform additional downloads
    runAdditionalDownloads()

    # Import all failed and successful projects
    importAllWindProjects()

    # Fill in missing turbine height-to-tip values with average value
    updateMissingTipHeights(getAverageTipHeight())

    # Populate dataframe with all failed and successful wind projects
    initialiseAllLargeWindProjectsDataFrame()

    # Amalgamate location-specific tables that don't cover whole of UK into unified table that covers UK
    amalgamateNonUKtables()

    # Get list of tables to run distance testing on
    tables_to_test_unprojected = removeNonEssentialTablesForDistance(postgisGetUKBasicProcessedTables())

    # Creates reprojected version of all testing tables to improve performance
    tables_to_test = []
    for table in tables_to_test_unprojected:
        tables_to_test.append(createTransformedTable(table))

    # Generate historical footpaths to account for turbine-created footpaths creating misleading data
    generateHistoricalFootpaths()

    # Generate historical minor roads to account for turbine-created service roads creating misleading data
    generateHistoricalMinorRoads()

    tables_to_test = removeNonEssentialTablesForDistance(tables_to_test)

    # Create distance-to-turbine cache
    createDistanceCache(tables_to_test)

    # If file already created, don't do anything else
    if isfile(OUTPUT_DATA_ALLTURBINES): return

    # distance_ranges = [20]
    distance_ranges = [10, 20, 30, 40]

    # Populate Geocode lookup to save time
    populateLookupsWithAllTurbines()

    # Get all large failed and successful wind turbines and iterate through them

    all_turbines = getAllLargeWindProjects()
    index, firstrowwritten, totalrecords, fieldnames = 0, False, len(all_turbines), None

    for turbine in all_turbines:

        if index % 1000 == 0:
            LogMessage("Processing turbine: " + str(index + 1) + "/" + str(totalrecords))

        # Convert dates to text
        # Note: import creates date type fields unprompted
        if turbine['project_date_operational'] is not None:
            turbine['project_date_operational'] = turbine['project_date_operational'].strftime('%Y-%m-%d')
        if turbine['project_date_underconstruction'] is not None:
            turbine['project_date_underconstruction'] = turbine['project_date_underconstruction'].strftime('%Y-%m-%d')
        if turbine['project_date_start'] is None: turbine['project_year'] = None
        else: turbine['project_year'] = str(turbine['project_date_start'])[0:4]

        # Improve ordering of fields
        turbine_lnglat = {'lng': turbine['lng'], 'lat': turbine['lat']}
        turbine_xy = {'x': turbine['x'], 'y': turbine['y']}
        turbine['turbine_country'] = getCountry(turbine_lnglat)
        turbine['turbine_elevation'] = getElevation(turbine_lnglat)[0]
        turbine['turbine_grid_coordinates_srs'] = turbine['turbine_srs']
        turbine['turbine_grid_coordinates_easting'] = turbine['turbine_easting']
        turbine['turbine_grid_coordinates_northing'] = turbine['turbine_northing']
        turbine['turbine_lnglat_lng'] = turbine['lng']
        turbine['turbine_lnglat_lat'] = turbine['lat']
        del turbine['lng']
        del turbine['lat']
        del turbine['x']
        del turbine['y']
        del turbine['turbine_srs']
        del turbine['turbine_easting']
        del turbine['turbine_northing']
        del turbine['geom']
        del turbine['geom_27700']

        turbine['windspeed'] = getWindSpeed(turbine_lnglat)
        turbine['project_size'] = getProjectSize(turbine['project_guid'])

        # Get viewshed visibility overlaps for (subset of) layers
        # *** Currently selects subset of layers using filterRelevantViewshedLayers()
        # *** to save computation time but this is not ideal
        # *** Ideally optimise computation and run on all layers
        # *** in order to avoid prejudging which might be salient

        # viewshedoverlaps = getViewshedOverlaps(turbine_lnglat, turbine['turbine_tipheight'], tables_to_test)
        # for viewshedoverlaps_key in viewshedoverlaps.keys(): turbine[viewshedoverlaps_key] = viewshedoverlaps[viewshedoverlaps_key]

        census = getCensus(turbine_lnglat)
        for census_key in census.keys(): turbine[census_key] = census[census_key]

        # # Get demographics for a number of radius circles
        # for census_radius in [10, 20, 30, 40]:
        #     census = getCensus(turbine_lnglat, census_radius * 1000)
        #     for census_key in census.keys(): turbine[str(census_radius) + 'km_radius_' + census_key] = census[census_key]

        political = {
            'political_total': None,
            'political_con': None,
            'political_lab': None,
            'political_ld': None,
            'political_other': None,
            'political_nat': None,
            'political_proportion_con': None,
            'political_proportion_lab': None,
            'political_proportion_ld': None,
            'political_proportion_other': None,
            'political_proportion_nat': None,
        }

        # If no project_date_end set it to project_date_operational if exists

        if (turbine['project_date_end'] is None) or (turbine['project_date_end'] == ''):
            if (turbine['project_date_operational'] is not None) and (turbine['project_date_operational'] != ''): turbine['project_date_end'] = turbine['project_date_operational']

        # project_date_end represents last date of all planning applications attached to project (or if null, is project_date_operational if available)

        if (turbine['project_date_end'] is not None) and (turbine['project_date_end'] != ''):
            year = str(turbine['project_date_end'])[0:4]
            political = getPolitical(turbine_lnglat, year)
        else:
            LogMessage("No project_date_end for: " + turbine['project_guid'] + ', ' + str(turbine['ogc_fid']))

        for political_key in political.keys(): turbine[political_key] = political[political_key]

        for distance_range in distance_ranges:
            radiuspoints                                                        = runRadiusSearch(turbine_xy, 1000 * distance_range, turbine['project_guid'])
            turbine['count__operational_within_' + str(distance_range)+'km']    = getOperationalBeforeDateWithinDistance(radiuspoints, turbine['project_date_end'])
            turbine['count__approved_within_' + str(distance_range)+'km']       = getApprovedBeforeDateWithinDistance(radiuspoints, turbine['project_date_end'])
            turbine['count__applied_within_' + str(distance_range)+'km']        = getAppliedBeforeDateWithinDistance(radiuspoints, turbine['project_date_end'])
            turbine['count__rejected_within_' + str(distance_range)+'km']       = getRejectedBeforeDateWithinDistance(radiuspoints, turbine['project_date_end'])

        for table_to_test in tables_to_test:
            distance = postgisDistanceToNearestFeature(turbine['ogc_fid'], table_to_test)
            # Remove internal table suffixes to improve readability
            table_to_test = table_to_test.replace('__pro__27700', '')
            # We don't need more precision than 1 decimetre
            if distance is None:
                turbine['distance__' + table_to_test] = 0
            else:
                turbine['distance__' + table_to_test] = round(distance, 1)

        if not firstrowwritten:
            with open(OUTPUT_DATA_ALLTURBINES, 'w', newline='') as csvfile:
                fieldnames = turbine.keys()
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
            firstrowwritten = True

        with open(OUTPUT_DATA_ALLTURBINES, 'a', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writerow(turbine)

        index += 1

def initializeDistanceRasters(raster_resolution, batch_grid_spacing):
    """
    Initializes distance rasters, regardless of whether batching or not
    """

    # Get list of tables to run distance testing on
    tables_to_test_unprojected = removeNonEssentialTablesForDistance(postgisGetUKBasicProcessedTables())

    # Creates reprojected version of all testing tables to improve performance
    tables_to_test = []
    for table in tables_to_test_unprojected:
        tables_to_test.append(createTransformedTable(table))

    tables_to_test = removeNonEssentialTablesForDistance(tables_to_test)

    createDistanceRasters(raster_resolution, tables_to_test, None, batch_grid_spacing)

def runSitePredictor(runtest, batch_grid_spacing, raster_resolution, pass_index):
    """
    Runs entire site predictor application
    """

    # Output machine learning features for all failed and successful turbines including
    # - Distances from each turbine to all GIS features
    # - Political data for council that turbine is in
    # - Census data (age, qualification, occupation, tenure) for LSOA/DZ that turbine is in
    # This approach broadly follows:
    # Michael Harper, Ben Anderson, Patrick A.B. James, AbuBakr S. Bahaj (2019)
    # https://www.sciencedirect.com/science/article/pii/S0301421519300023

    global RASTER_OUTPUT_FOLDER, OUTPUT_DATA_SAMPLEGRID, CLIPPING_FOLDER, DEFAULT_BATCH_GRID_SPACING, OUTPUT_ML_RASTER

    createAllTurbinesData()

    # Build machine learning model using failed/successful wind turbine features
    if not machinelearningModelExists(): machinelearningBuildModel(pass_index)

    # Create batch grid for multiprocessing
    if batch_grid_spacing is None: batch_grid_spacing = DEFAULT_BATCH_GRID_SPACING

    output_data = buildOutputPath(runtest, OUTPUT_DATA_SAMPLEGRID, batch_grid_spacing, raster_resolution)
    
    if not isfile(output_data):

        number_batches = createBatchGrid(runtest, batch_grid_spacing)

        LogMessage("Batch grid spacing set to " + str(batch_grid_spacing) + " metres, will run multiprocessing with " + str(number_batches) + " batches")
        if runtest: LogMessage("NOTE: Using test grid - so only 1 batch")

        LogMessage("Determining total number of points to be processed...")

        total_points = getSamplingGridNumberPoints(runtest, batch_grid_spacing, number_batches, raster_resolution)

        LogMessage("Total number of points to be processed: " + str(total_points))

        # Initialize core distance rasters that will be used by all batches
        initializeDistanceRasters(raster_resolution, batch_grid_spacing)

        multiprocessing_batch_values = [[runtest, batch_index, batch_grid_spacing, raster_resolution] for batch_index in range(1, number_batches + 1)]

        LogMessage("************************************************")
        LogMessage("********** STARTING MULTIPROCESSING ************")
        LogMessage("************************************************")

        cnt, total = Value('i', 0), Value('i', total_points)
        # Run multiprocessing pool
        with Pool(initializer=init_counter_total_globals, initargs=(cnt, total, )) as p:
            # Populates sampling grid (spaced at raster_resolution metres) with same
            # features data - where possible - as all turbines, above.
            # Year used is (CURRENTYEAR - 1), ie. attempting to predict probability-of-success for now
            p.map(createSamplingGridData, multiprocessing_batch_values, chunksize=1)

        LogMessage("************************************************")
        LogMessage("*********** ENDING MULTIPROCESSING *************")
        LogMessage("************************************************")

        LogMessage("Consolidating batch output files...")

        firstrowwritten = False

        for batch_item in multiprocessing_batch_values:
            runtest, batch_index, batch_grid_spacing = batch_item[0], batch_item[1], batch_item[2]
            batch_output_data = buildBatchGridOutputData(buildOutputPath(runtest, OUTPUT_DATA_SAMPLEGRID, batch_grid_spacing, raster_resolution), batch_index, batch_grid_spacing)
            if not isfile(batch_output_data): continue

            LogMessage("Adding batch output file: " + str(batch_index))

            turbines = []
            with open(batch_output_data, 'r', newline='', encoding="utf-8") as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader: 
                    turbines.append(row)

            if len(turbines) == 0: continue

            if not firstrowwritten:
                with open(output_data, 'w', newline='') as csvfile:
                    fieldnames = turbines[0].keys()
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()
                firstrowwritten = True

            with open(output_data, 'a', newline='') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                for turbine in turbines:
                    writer.writerow(turbine)

            os.remove(batch_output_data)

    final_raster_path = buildOutputPath(runtest, OUTPUT_ML_RASTER, batch_grid_spacing, raster_resolution)

    if not isfile(final_raster_path):
        # Run machine learning model on sampling grid
        machinelearningRunModelOnSamplingGrid(runtest, batch_grid_spacing, raster_resolution)

    if isdir(CLIPPING_FOLDER): shutil.rmtree(CLIPPING_FOLDER)

def clearML(runtest, batch_grid_spacing, final_raster_resolution):
    """
    Clears previous ML run
    """

    global OUTPUT_ML_GEOJSON, OUTPUT_ML_RASTER, OUTPUT_ML_CSV

    # Delete ML model and any files derived from applying it
    machinelearningDeleteSavedModels()
    files_to_delete =   [ \
                            buildOutputPath(runtest, OUTPUT_ML_GEOJSON, batch_grid_spacing, final_raster_resolution), \
                            buildOutputPath(runtest, OUTPUT_ML_RASTER, batch_grid_spacing, final_raster_resolution), \
                            buildOutputPath(runtest, OUTPUT_ML_CSV, batch_grid_spacing, final_raster_resolution) \
                        ]

    for file_to_delete in files_to_delete:
        if isfile(file_to_delete): os.remove(file_to_delete)

def generatePercentileVariabilityGeoTIFF(file_paths, output_file_path):
    """
    Generates a GeoTIFF showing (P95 - P5) per pixel across a stack of input GeoTIFFs.
    This percentile range reflects predictive variability or uncertainty.
    """

    stack = []
    for path in file_paths:
        with rasterio.open(path) as src:
            band = src.read(1).astype(np.float32)
            stack.append(band)
            profile = src.profile  # Used to write the output

    raster_stack = np.stack(stack)  # shape: (n_runs, height, width)

    # Compute percentiles along the 0th axis (runs)
    p95 = np.nanpercentile(raster_stack, 95, axis=0)
    p5 = np.nanpercentile(raster_stack, 5, axis=0)

    percentile_range = p95 - p5

    # Optional: set a no-data value
    NODATA_VALUE = -9999
    percentile_range[np.isnan(percentile_range)] = NODATA_VALUE

    # Update raster profile
    profile.update(dtype=rasterio.float32, count=1, nodata=NODATA_VALUE)

    with rasterio.open(output_file_path, 'w', **profile) as dst:
        dst.write(percentile_range.astype(np.float32), 1)

    LogMessage("Saved percentile range GeoTIFF: " + output_file_path)


def generateNormalizedSDGeoTIFF(file_paths, output_file_path):
    """
    Generates a GeoTIFF with a normalized SD for all GeoTIFFs
    Normalized SD => 1 = normal distribution, values essentially random, no-data > 1
    As value -> 0, less random
    """

    stack = []
    for path in file_paths:
        with rasterio.open(path) as src:
            band = src.read(1).astype(np.float32)
            stack.append(band)
            profile = src.profile  # We'll use this for writing output

    raster_stack = np.stack(stack)  # Shape: (n_passes, height, width)

    # 3. Compute stddev along the passes axis
    stddev = np.nanstd(raster_stack, axis=0)

    # 4. Normalize and apply nodata
    normalized = stddev / MAX_RANDOM_STDDEV
    normalized[normalized > 1.0] = NODATA_VALUE

    # 5. Update profile for single-band float GeoTIFF
    profile.update(dtype=rasterio.float32, count=1, nodata=NODATA_VALUE)

    # 6. Write output GeoTIFF
    with rasterio.open(output_file_path, 'w', **profile) as dst:
        dst.write(normalized.astype(np.float32), 1)

    LogMessage("Saved normalized SD GeoTIFF: " + output_file_path)

# ***********************************************************
# ***********************************************************
# ********************* MAIN APPLICATION ********************
# ***********************************************************
# ***********************************************************

def main():
    """
    Main function - put here to allow multiprocessing to work
    """

    global RASTER_RESOLUTION, SAMPLING_GRID, LOG_SINGLE_PASS, RASTER_OUTPUT_FOLDER, WORKING_FOLDER

    final_raster_resolution = RASTER_RESOLUTION
    batch_grid_spacing = None

    if len(sys.argv) > 1:
        batch_grid_spacing_set, resample, rerunml, runtest, passes = False, False, False, False, None

        arg_index = 1
        while True:
            if arg_index >= len(sys.argv): break
            arg = sys.argv[arg_index].strip()

            if isfloat(arg) and (not batch_grid_spacing_set):
                batch_grid_spacing = int(arg)
                batch_grid_spacing_set = True
                LogMessage("Running batch processing with batch_grid_spacing = " + str(batch_grid_spacing))

            if arg == '--resample':
                resample = True
                LogMessage("--resample argument passed: Deleting output files")

            if arg == '--rerunml':
                rerunml = True
                LogMessage("--rerunml argument passed: Deleting ML model and related output files")

            if arg == '--test':
                runtest = True
                LogMessage("--test argument passed: Only sample specific test area")

            if arg == '--resolution':
                if len(sys.argv) > arg_index:
                    resolution = sys.argv[arg_index + 1]
                    if isfloat(resolution):
                        final_raster_resolution = int(resolution)
                        arg_index += 1
                        LogMessage("--resolution argument passed: Using resolution of " + resolution + " metres")

            if arg == '--passes':
                if len(sys.argv) > arg_index:
                    passes = sys.argv[arg_index + 1]
                    if isfloat(passes):
                        passes = int(passes)
                        arg_index += 1
                        LogMessage("--passes argument passed: Number of passes to run: " + str(passes))

            arg_index += 1

        files_to_delete = None

        if resample:
            # Delete RASTER_OUTPUT_FOLDER just to be safe
            shutil.rmtree(RASTER_OUTPUT_FOLDER)
            files_to_delete =   [ \
                                    buildOutputPath(runtest, OUTPUT_DATA_SAMPLEGRID, batch_grid_spacing, final_raster_resolution), \
                                    buildOutputPath(runtest, OUTPUT_ML_GEOJSON, batch_grid_spacing, final_raster_resolution), \
                                    buildOutputPath(runtest, OUTPUT_ML_RASTER, batch_grid_spacing, final_raster_resolution), \
                                    buildOutputPath(runtest, OUTPUT_ML_CSV, batch_grid_spacing, final_raster_resolution) \
                                ]

        if rerunml: clearML(runtest, batch_grid_spacing, final_raster_resolution)

        if files_to_delete is not None:
            for file_to_delete in files_to_delete:
                if isfile(file_to_delete): os.remove(file_to_delete)


    SAMPLING_GRID += str(final_raster_resolution) + "_m__uk"

    if passes is None:
        runSitePredictor(runtest, batch_grid_spacing, final_raster_resolution, 666)
    else:
        makeFolder(PASSES_FOLDER)
        file_paths = []
        for pass_index in range(1, passes + 1):
            LogMessage("Running pass: " + str(pass_index))
            clearML(runtest, batch_grid_spacing, final_raster_resolution)
            output_tif_pass = PASSES_FOLDER + 'pass-' + str(pass_index).zfill(5) + '-' + basename(OUTPUT_ML_RASTER)
            file_paths.append(output_tif_pass)
            if not isfile(output_tif_pass):
                runSitePredictor(runtest, batch_grid_spacing, final_raster_resolution, pass_index)
                shutil.copy(buildOutputPath(runtest, OUTPUT_ML_RASTER, batch_grid_spacing, final_raster_resolution), output_tif_pass)

        normalized_sd_geotiff = PASSES_FOLDER + 'normalized-sd-' + basename(OUTPUT_ML_RASTER)
        # generateNormalizedSDGeoTIFF(file_paths, normalized_sd_geotiff)
        percentile_variability_geotiff = PASSES_FOLDER + 'percentile-variability-' + basename(OUTPUT_ML_RASTER)
        generatePercentileVariabilityGeoTIFF(file_paths, percentile_variability_geotiff)

    # Copy final results as gzipped tar to /usr/src/openwindenergy/ folder
    if WORKING_FOLDER.startswith('/usr/src/openwindenergy/') and isfile(buildOutputPath(runtest, OUTPUT_ML_RASTER, batch_grid_spacing, final_raster_resolution)):
        LogMessage("Bundling final rasters and data as tar.gz archives")
        data_samplegrid = basename(buildOutputPath(runtest, OUTPUT_DATA_SAMPLEGRID, batch_grid_spacing, final_raster_resolution))
        ml_geojson = basename(buildOutputPath(runtest, OUTPUT_ML_GEOJSON, batch_grid_spacing, final_raster_resolution))
        ml_raster = basename(buildOutputPath(runtest, OUTPUT_ML_RASTER, batch_grid_spacing, final_raster_resolution))
        ml_csv = basename(buildOutputPath(runtest, OUTPUT_ML_CSV, batch_grid_spacing, final_raster_resolution))
        subprocess.call("tar -cjf /usr/src/openwindenergy/build-cli/output/sitepredictor__finalraster_data__" + str(final_raster_resolution) + "_m.tar.gz -C /usr/src/openwindenergy/sitepredictor/output/ " + data_samplegrid + " " + ml_geojson + " " + ml_raster + " " + ml_csv, shell=True)
        subprocess.call("tar -cvzf /usr/src/openwindenergy/build-cli/output/sitepredictor__intermediate_rasters__" + str(final_raster_resolution) + "_m.tar.gz /usr/src/openwindenergy/sitepredictor/rasters/distance__" + str(final_raster_resolution) + "*.tif", shell=True)

# Only remove log file on main thread
if __name__ == "__main__":
    if isfile(LOG_SINGLE_PASS): os.remove(LOG_SINGLE_PASS)

# Always initialise logging so multiprocessing threads get logged
initLogging()

if __name__ == "__main__": main()
