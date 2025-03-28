# ***********************************************************
# *********************** OPEN WIND *************************
# ***********************************************************
# ***** Script to upload Open Wind datasets to GeoNode ******
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

import logging
import json
import requests
import os
import time
import subprocess
import uuid
from webcolors import name_to_hex
from os.path import isfile, basename, join, dirname
from dotenv import load_dotenv

load_dotenv()

geonode_dotenv_path = join(dirname(__file__), 'geonode', 'openwind-project', '.env')
if isfile(geonode_dotenv_path): load_dotenv(geonode_dotenv_path)

BUILD_FOLDER                    = 'build-cli/'
GEONODE_BASE_URL                = 'http://localhost'
GEOSERVER_BASE_URL              = GEONODE_BASE_URL + '/geoserver'
TILESERVER_URL                  = 'http://localhost:8080'

if os.environ.get("BUILD_FOLDER") is not None: BUILD_FOLDER = os.environ.get('BUILD_FOLDER')
if os.environ.get("GEONODE_BASE_URL") is not None: GEONODE_BASE_URL = os.environ.get('GEONODE_BASE_URL')
if os.environ.get("GEOSERVER_BASE_URL") is not None: GEOSERVER_BASE_URL = os.environ.get('GEOSERVER_BASE_URL')
if os.environ.get("TILESERVER_URL") is not None: TILESERVER_URL = os.environ.get('TILESERVER_URL')

HEIGHT_TO_TIP                   = None
STRUCTURE_LOOKUP                = BUILD_FOLDER + 'datasets-structure.json'
STYLE_LOOKUP                    = BUILD_FOLDER + 'datasets-style.json'
BUFFER_LOOKUP                   = BUILD_FOLDER + 'datasets-buffers.json'
FINALLAYERS_OUTPUT_FOLDER       = BUILD_FOLDER + 'output/'
ADMIN_USERNAME                  = os.environ.get("ADMIN_USERNAME")
ADMIN_PASSWORD                  = os.environ.get("ADMIN_PASSWORD")
FINALLAYERS_CONSOLIDATED        = 'windconstraints'
MAP_ESSENTIAL_BLOB = {
  "map": {
    "center": {
      "x": 2.532466473149996,
      "y": 55.75900447488736,
      "crs": "EPSG:4326"
    },
    "groups": [
                {
                    "id": "Default",
                    "title": "Group_1",
                    "expanded": True
                },
                {
                    "id": 'latest--all',
                    "title": "Group_2",
                    "expanded": True
                }
    ],    
    "backgrounds": []
  }
}

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

    datasettitle = datasettitle.replace('.geojson', '').replace('.gpkg', '')
    reformatted_name = datasettitle.lower().replace(' - ', '--').replace(' ','-').replace('_','-').replace('(', '').replace(')', '')
    reformatted_name = reformatted_name.replace('areas-of-special-scientific-interest', 'sites-of-special-scientific-interest')
    reformatted_name = reformatted_name.replace('conservation-area-boundaries', 'conservation-areas')
    reformatted_name = reformatted_name.replace('scheduled-historic-monument-areas', 'scheduled-ancient-monuments')
    reformatted_name = reformatted_name.replace('priority-habitats--woodland', 'ancient-woodlands')
    reformatted_name = reformatted_name.replace('local-wildlife-reserves', 'local-nature-reserves')
    reformatted_name = reformatted_name.replace('national-scenic-areas-equiv-to-aonb', 'area-of-outstanding-natural-beauty')
    reformatted_name = reformatted_name.replace('explosive-safeguarded-areas,-danger-areas-near-ranges', 'danger-areas')
    reformatted_name = reformatted_name.replace('separation-distance-to-residential-properties', 'separation-distance-from-residential')

    return reformatted_name

def reformatTableName(name):
    """
    Reformats names, eg. dataset names, to be compatible with Postgres
    """

    return name.replace("-", "_")

# ***********************************************************
# ********** Application data structure functions ***********
# ***********************************************************

def isSpecificDatasetHeightDependent(dataset_name):
    """
    Returns True or False, depending on whether specific dataset (ignoring children) is turbine-height dependent
    """

    buffer_lookup = getBufferLookup()
    if dataset_name in buffer_lookup:
        buffer_value = buffer_lookup[dataset_name]
        if 'height-to-tip' in buffer_value: return True
    return False

def isTurbineHeightDependent(dataset_name):
    """
    Returns True or False, depending on whether dataset is turbine-height dependent
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

def getCoreDatasetName(file_path):
    """
    Gets core dataset name from file path
    Core dataset = 'description--location', eg 'national-parks--scotland'
    """

    file_basename = basename(file_path).split(".")[0]
    elements = file_basename.split("--")
    if elements[0] == 'latest': return "--".join(elements[1:2])
    return "--".join(elements[0:2])

def getDatasetBuffer(datasetname):
    """
    Gets buffer for dataset 'datasetname'
    """

    global HEIGHT_TO_TIP

    datasetname = getCoreDatasetName(datasetname)
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

def formatValue(value):
    """
    Formats float value to be short and readable
    """

    return str(round(value, 1)).replace('.0', '')

def getDatasetRelativePath(dataset_core_path):
    """
    Builds relative path of dataset
    """

    global FINALLAYERS_OUTPUT_FOLDER

    if FINALLAYERS_OUTPUT_FOLDER not in dataset_core_path: return os.path.join(FINALLAYERS_OUTPUT_FOLDER, dataset_core_path)

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

def runSubprocess(subprocess_array):
    """
    Runs subprocess
    """

    output = subprocess.run(subprocess_array)

    # print("\n" + " ".join(subprocess_array) + "\n")

    if output.returncode != 0:
        LogError("subprocess.run failed with error code: " + str(output.returncode) + '\n' + " ".join(subprocess_array))
    return " ".join(subprocess_array)

# ***********************************************************
# ***************** Application functions *******************
# ***********************************************************

def waitForGeoNode():
    """
    Wait for GeoNode to be active
    """

    global GEONODE_BASE_URL

    LogMessage("Waiting for GeoNode to become active...")

    url = GEONODE_BASE_URL + "/api/v2/resources"

    while True:
        response = requests.request('GET', url)
        if response.status_code == 200: 
            LogMessage("GeoNode now active")
            break

        time.sleep(5)

def createSLD(style):
    """
    Creates style definition text
    """

    if (style['fill'].strip() != '') and ('#' not in style['fill']): style['fill'] = name_to_hex(style['fill'])
    if (style['stroke'].strip() != '') and ('#' not in style['stroke']): style['stroke'] = name_to_hex(style['stroke'])

    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<StyledLayerDescriptor version="1.0.0" xsi:schemaLocation="http://www.opengis.net/sld StyledLayerDescriptor.xsd" xmlns="http://www.opengis.net/sld" xmlns:ogc="http://www.opengis.net/ogc" xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <NamedLayer>
    <Name>Default Polygon</Name>
    <UserStyle>
      <Name>Default Polygon</Name>
      <Title>Default Polygon</Title>
      <FeatureTypeStyle>
        <Rule>
          <Name>""" + str(style['name']) + """</Name>
          <PolygonSymbolizer>
            <Fill>
              <CssParameter name="fill">""" + str(style['fill']) + """</CssParameter>
              <CssParameter name="fill-opacity">""" + str(style['fill-opacity']) + """</CssParameter>
            </Fill>
            <Stroke>
              <CssParameter name="stroke">""" + str(style['stroke']) + """</CssParameter>
              <CssParameter name="stroke-width">""" + str(style['stroke-width']) + """</CssParameter>
              <CssParameter name="stroke-opacity">""" + str(style['stroke-opacity']) + """</CssParameter>
            </Stroke>
          </PolygonSymbolizer>
        </Rule>
      </FeatureTypeStyle>
    </UserStyle>
  </NamedLayer>
</StyledLayerDescriptor>
"""

def uploadDataset2GeoNode(dataset_title, dataset_core_path, style, wmtsonly=False):
    """
    Uploads single dataset to GeoNode
    """

    global GEONODE_BASE_URL, HEIGHT_TO_TIP, ADMIN_USERNAME, ADMIN_PASSWORD

    LogMessage("Uploading to GeoNode: " + dataset_title)

    # Initiate authenticated session

    session = requests.Session()
    session.auth = (ADMIN_USERNAME, ADMIN_PASSWORD)
    
    url = GEONODE_BASE_URL + "/api/v2/uploads/upload"

    core_dataset = getCoreDatasetName(dataset_core_path)
    if isTurbineHeightDependent(core_dataset): dataset_title += ' - Tip height ' + formatValue(HEIGHT_TO_TIP) + 'm'

    dataset_core_path = getDatasetRelativePath(dataset_core_path)
    dataset_basename = basename(dataset_core_path)
    style['name'] = dataset_title
    style_sld = createSLD(style)
    style_sld_file = dataset_core_path + '.sld'
    with open(style_sld_file, "w") as sld_file: sld_file.write(style_sld)

    files= [
        ('sld_file',(basename(style_sld_file), open(style_sld_file,'rb'), 'application/octet-stream')),  
        ('base_file',(dataset_basename + '.shp', open(dataset_core_path + '.shp','rb'), 'application/octet-stream')),  
        ('dbf_file',(dataset_basename + '.dbf', open(dataset_core_path + '.dbf','rb'), 'application/octet-stream')),  
        ('shx_file',(dataset_basename + '.shx', open(dataset_core_path + '.shx','rb'), 'application/octet-stream')),
        ('prj_file',(dataset_basename + '.prj', open(dataset_core_path + '.prj','rb'), 'application/octet-stream'))
    ]
    payload = {
        'overwrite_existing_layer': 'True'
    }
    response = session.post(url, data=payload, files=files)
    # os.remove(style_sld_file)

    try:
        response_json = json.loads(response.text)
    except:
        LogError("Problem with response from Geonode: " + response.text)
        exit()

    if 'execution_id' in response_json:
        execution_id = response_json['execution_id']
        LogMessage("Waiting for upload to finish...")
        while True:
            execution_url = GEONODE_BASE_URL + '/api/v2/executionrequest/' + execution_id
            response = session.get(execution_url)
            response_json = json.loads(response.text)
            upload_status = response_json['request']['status']
            if upload_status == 'finished': 
                dataset_id = response_json['request']['output_params']['resources'][0]['id']
                url = GEONODE_BASE_URL + "/api/v2/datasets/" + str(dataset_id)
                response = session.patch(url, json={'title': dataset_title})
                LogMessage("Upload finished")
                return dataset_id
            if upload_status == 'failed':
                LogError("Upload failed, aborting upload process")
                # break
                exit()
            time.sleep(5)


def uploadDatasets2GeoNode():
    """
    Uploads datasets and groups to GeoNode
    """

    global HEIGHT_TO_TIP, STYLE_LOOKUP, FINALLAYERS_OUTPUT_FOLDER, GEONODE_BASE_URL, ADMIN_USERNAME, ADMIN_PASSWORD

    # Start off by checking GeoNode is active

    waitForGeoNode()

    # Get style-specific version of dataset hierarchy

    style_lookup = getStyleLookup()

    # Set height to tip from first element in style lookup

    HEIGHT_TO_TIP = float(style_lookup[0]['height-to-tip'])

    # Iterate through all groups and children of groups

    dataset_ids = []
    style = {
        'fill': '',
        'fill-opacity': '',
        'stroke': '#FFFFFF',
        'stroke-width': 0,
        'stroke-opacity': 0
    }
    
    dataset_ids_lookup = {}
    for group in style_lookup:
        style['fill'] = group['color']
        style['fill-opacity'] = 0.8
        dataset_ids_lookup[group['dataset']] = uploadDataset2GeoNode(group['title'], group['dataset'], style)
        if 'children' not in group: continue
        for child in group['children']:
            style['fill-opacity'] = 0.4
            dataset_ids_lookup[child['dataset']] = uploadDataset2GeoNode(child['title'], child['dataset'], style)

    return dataset_ids_lookup 

def getLayerItem(group_id, geonode_name, title, dataset_pk, visibility):
    """
    Gets JSON for layer item for use in API
    """

    global GEOSERVER_BASE_URL

    if GEOSERVER_BASE_URL.endswith('/'): GEOSERVER_BASE_URL = GEOSERVER_BASE_URL[:-1]

    uniqueid = str(uuid.uuid4())

    layer_item = {
        "id": uniqueid,
        "format": "image/png",
        "group": group_id,
        "search": {
            "type": "wfs",
            "url": GEOSERVER_BASE_URL + "/ows"
        },
        "fields": [
            {
                "name": "ogc_fid",
                "alias": None,
                "type": "xsd:int"
            }
        ],
        "name": geonode_name,
        "style": geonode_name,
        "title": title,
        "type": "wms",
        "url": GEOSERVER_BASE_URL + "/ows",
        "bbox": {
            "crs": "EPSG:4326",
            "bounds": {
                "minx": -8.6500072,
                "miny": 49.89003787553913,
                "maxx": 1.62997920879999,
                "maxy": 60.86077150000001
            }
        },
        "visibility": visibility,
        "singleTile": False,
        "dimensions": [],
        "hideLoading": False,
        "handleClickOnLayer": False,
        "featureInfo": {
            "format": "TEMPLATE",
            "template": "<div style=\"overflow-x:hidden\"><div class=\"row\"><div class=\"col-xs-6\" style=\"font-weight: bold; word-wrap: break-word;\">ogc_fid:</div>                             <div class=\"col-xs-6\" style=\"word-wrap: break-word;\">${properties['ogc_fid']}</div></div></div>"
        },
        "useForElevation": False,
        "hidden": False,
        "tileSize": 512,
        "expanded": False,
        "params": {},
        "extendedParams": {
            "pk": str(dataset_pk),
            "mapLayer": {
                "dataset": {
                    "pk": str(dataset_pk),

                }
            }
        }
    }

    return layer_item

def getGroupItem(group_id, title, visibility):
    """
    Gets JSON for group item for use in API
    """

    return {
        "id": group_id,
        "title": title,
        "expanded": False,
        "visibility": visibility
    }

def getGeoNodeName(resource_pk):
    """
    Gets GeoNode name using resource pk
    """

    global GEONODE_BASE_URL, ADMIN_USERNAME, ADMIN_PASSWORD

    LogMessage("Getting GeoNode name for resource pk: " + str(resource_pk))

    session = requests.Session()
    session.auth = (ADMIN_USERNAME, ADMIN_PASSWORD)
    url = GEONODE_BASE_URL + "/api/v2/resources/" + str(int(resource_pk))
    response = session.get(url)
    response_json = json.loads(response.text)
    return response_json['resource']['alternate']

def getMapLayerItem(layer_id, geonode_name):
    """
    Gets JSON for group item for use in API
    """

    return {
        "extra_params": {
            "msId": layer_id
        },
        "current_style": geonode_name,
        "name": geonode_name,
        "order": 0,
        "opacity": 1,
        "visibility": True
    }

def createMapGeoNode(dataset_pks):
    """
    Creates GeoNode map with hierarchy according to groups
    """

    global GEONODE_BASE_URL, HEIGHT_TO_TIP, ADMIN_USERNAME, ADMIN_PASSWORD

    LogMessage("Creating GeoNode map...")

    session = requests.Session()
    session.auth = (ADMIN_USERNAME, ADMIN_PASSWORD)

    # Delete any maps with same name

    name = 'Wind Constraints Map - Tip Height ' + formatValue(HEIGHT_TO_TIP) + 'm'

    url = GEONODE_BASE_URL + "/api/v2/resources/?filter{resource_type}=map"
    response = session.get(url)

    response_json = json.loads(response.text)
    for resource in response_json['resources']:
        if resource['title'].strip() == name.strip():
            LogMessage("Deleting existing map with same name - id: " + str(resource['pk']))
            delete_url = GEONODE_BASE_URL + '/api/v2/resources/' + str(resource['pk'])
            session.delete(delete_url)

    # Generate map

    url = GEONODE_BASE_URL + "/api/v2/maps"

    group_structure = getStyleLookup()
    layers, output_groups, maplayers = [], [], []
    index = 0
    for group in group_structure:
        group_id = str(uuid.uuid4())
        dataset_name = group['dataset']
        geonode_name = getGeoNodeName(dataset_pks[dataset_name])
        group_title = group['title']
        visibility = True
        if index == 0: visibility = False
        layers_item = getLayerItem(group_id, geonode_name, group_title, dataset_pks[dataset_name], visibility)
        layer_id = layers_item['id']
        layers.append(layers_item)
        output_groups.append(getGroupItem(group_id, group_title, visibility))
        maplayer_item = getMapLayerItem(layer_id, geonode_name)
        maplayers.append(maplayer_item)
        index += 1
        if 'children' not in group: continue
        for child in group['children']:
            dataset_name = child['dataset']
            child_title = child['title']
            geonode_name = getGeoNodeName(dataset_pks[dataset_name])
            visibility = False
            layers_item = getLayerItem(group_id, geonode_name, child_title, dataset_pks[dataset_name], visibility)
            layer_id = layers_item['id']
            layers.append(layers_item)
            maplayer_item = getMapLayerItem(layer_id, geonode_name)
            maplayers.append(maplayer_item)

    FINAL_PAYLOAD = {
        'title': name,
        "data": {
            "map": {
                "center": {
                    "x": 8.574946941899997,
                    "y": 55.75900447488736,
                    "crs": "EPSG:4326"
                },
                "layers": layers[::-1],
                "groups": output_groups,
                "backgrounds": []
            }
        },
        "maplayers": maplayers
    }

    LogMessage("Submitting create map request")

    session = requests.Session()
    session.auth = (ADMIN_USERNAME, ADMIN_PASSWORD)

    url = GEONODE_BASE_URL + "/api/v2/maps"

    response = session.post(url, json=FINAL_PAYLOAD)
    if response.status_code == 201: 
        LogMessage("Map request finished submitting successfully", )
    else:
        LogError("Problem creating map - error code:")
        print(response)

def getWMTSLayerItem(group_id, title, dataset_name, visibility, opacity):
    """
    Gets JSON for WMTS layer item for use in API
    """

    global TILESERVER_URL

    # dataset_name = 'basic'
    
    if TILESERVER_URL.endswith('/'): TILESERVER_URL = TILESERVER_URL[:-1]

    uniqueid = str(uuid.uuid4())

    layer_item = {
        "id": uniqueid,
        "format": "image/png",
        "group": group_id,
        "name": title,
        "description": title,
        "style": "default",
        "title": title,
        "type": "wmts",
        "opacity": opacity,
        "url": TILESERVER_URL + "/styles/" + dataset_name + "/256/{TileMatrix}/{TileCol}/{TileRow}.png",
        "bbox": {
          "crs": "EPSG:4326",
            "bounds": {
                "minx": -8.6500072,
                "miny": 49.89003787553913,
                "maxx": 1.62997920879999,
                "maxy": 60.86077150000001
            }
        },
        "visibility": visibility,
        "singleTile": False,
        "allowedSRS": {
          "EPSG:3857": True
        },
        "requestEncoding": "RESTful",
        "dimensions": [],
        "hideLoading": False,
        "handleClickOnLayer": False,
        "queryable": False,
        "catalogURL": None,
        "capabilitiesURL": TILESERVER_URL + "/styles/" + dataset_name + "/wmts.xml",
        "useForElevation": False,
        "hidden": False,
        "expanded": False,
        "params": {},
        "availableTileMatrixSets": {
          "GoogleMapsCompatible_256": {
            "crs": "EPSG:3857",
            "tileMatrixSetLink": "sources['" + TILESERVER_URL + "/styles/" + dataset_name + "/wmts.xml'].tileMatrixSet['GoogleMapsCompatible_256']"
          }
        }
    }

    return layer_item

def getWMTSDefaultSource():
    """
    Gets default source for WMTS layer
    """

    return {
        "tileMatrixSet": {
            "GoogleMapsCompatible_256": {
                "ows:Title": "GoogleMapsCompatible_256",
                "TileMatrix": [
                    {
                        "TileWidth": "256",
                        "TileHeight": "256",
                        "MatrixWidth": "1",
                        "MatrixHeight": "1",
                        "TopLeftCorner": "-20037508.34 20037508.34",
                        "ows:Identifier": "0",
                        "ScaleDenominator": "559082264.02872"
                    },
                    {
                        "TileWidth": "256",
                        "TileHeight": "256",
                        "MatrixWidth": "2",
                        "MatrixHeight": "2",
                        "TopLeftCorner": "-20037508.34 20037508.34",
                        "ows:Identifier": "1",
                        "ScaleDenominator": "279541132.01436"
                    },
                    {
                        "TileWidth": "256",
                        "TileHeight": "256",
                        "MatrixWidth": "4",
                        "MatrixHeight": "4",
                        "TopLeftCorner": "-20037508.34 20037508.34",
                        "ows:Identifier": "2",
                        "ScaleDenominator": "139770566.00718"
                    },
                    {
                        "TileWidth": "256",
                        "TileHeight": "256",
                        "MatrixWidth": "8",
                        "MatrixHeight": "8",
                        "TopLeftCorner": "-20037508.34 20037508.34",
                        "ows:Identifier": "3",
                        "ScaleDenominator": "69885283.00359"
                    },
                    {
                        "TileWidth": "256",
                        "TileHeight": "256",
                        "MatrixWidth": "16",
                        "MatrixHeight": "16",
                        "TopLeftCorner": "-20037508.34 20037508.34",
                        "ows:Identifier": "4",
                        "ScaleDenominator": "34942641.501795"
                    },
                    {
                        "TileWidth": "256",
                        "TileHeight": "256",
                        "MatrixWidth": "32",
                        "MatrixHeight": "32",
                        "TopLeftCorner": "-20037508.34 20037508.34",
                        "ows:Identifier": "5",
                        "ScaleDenominator": "17471320.750897"
                    },
                    {
                        "TileWidth": "256",
                        "TileHeight": "256",
                        "MatrixWidth": "64",
                        "MatrixHeight": "64",
                        "TopLeftCorner": "-20037508.34 20037508.34",
                        "ows:Identifier": "6",
                        "ScaleDenominator": "8735660.3754487"
                    },
                    {
                        "TileWidth": "256",
                        "TileHeight": "256",
                        "MatrixWidth": "128",
                        "MatrixHeight": "128",
                        "TopLeftCorner": "-20037508.34 20037508.34",
                        "ows:Identifier": "7",
                        "ScaleDenominator": "4367830.1877244"
                    },
                    {
                        "TileWidth": "256",
                        "TileHeight": "256",
                        "MatrixWidth": "256",
                        "MatrixHeight": "256",
                        "TopLeftCorner": "-20037508.34 20037508.34",
                        "ows:Identifier": "8",
                        "ScaleDenominator": "2183915.0938622"
                    },
                    {
                        "TileWidth": "256",
                        "TileHeight": "256",
                        "MatrixWidth": "512",
                        "MatrixHeight": "512",
                        "TopLeftCorner": "-20037508.34 20037508.34",
                        "ows:Identifier": "9",
                        "ScaleDenominator": "1091957.5469311"
                    },
                    {
                        "TileWidth": "256",
                        "TileHeight": "256",
                        "MatrixWidth": "1024",
                        "MatrixHeight": "1024",
                        "TopLeftCorner": "-20037508.34 20037508.34",
                        "ows:Identifier": "10",
                        "ScaleDenominator": "545978.77346554"
                    },
                    {
                        "TileWidth": "256",
                        "TileHeight": "256",
                        "MatrixWidth": "2048",
                        "MatrixHeight": "2048",
                        "TopLeftCorner": "-20037508.34 20037508.34",
                        "ows:Identifier": "11",
                        "ScaleDenominator": "272989.38673277"
                    },
                    {
                        "TileWidth": "256",
                        "TileHeight": "256",
                        "MatrixWidth": "4096",
                        "MatrixHeight": "4096",
                        "TopLeftCorner": "-20037508.34 20037508.34",
                        "ows:Identifier": "12",
                        "ScaleDenominator": "136494.69336639"
                    },
                    {
                        "TileWidth": "256",
                        "TileHeight": "256",
                        "MatrixWidth": "8192",
                        "MatrixHeight": "8192",
                        "TopLeftCorner": "-20037508.34 20037508.34",
                        "ows:Identifier": "13",
                        "ScaleDenominator": "68247.346683193"
                    },
                    {
                        "TileWidth": "256",
                        "TileHeight": "256",
                        "MatrixWidth": "16384",
                        "MatrixHeight": "16384",
                        "TopLeftCorner": "-20037508.34 20037508.34",
                        "ows:Identifier": "14",
                        "ScaleDenominator": "34123.673341597"
                    },
                    {
                        "TileWidth": "256",
                        "TileHeight": "256",
                        "MatrixWidth": "32768",
                        "MatrixHeight": "32768",
                        "TopLeftCorner": "-20037508.34 20037508.34",
                        "ows:Identifier": "15",
                        "ScaleDenominator": "17061.836670798"
                    },
                    {
                        "TileWidth": "256",
                        "TileHeight": "256",
                        "MatrixWidth": "65536",
                        "MatrixHeight": "65536",
                        "TopLeftCorner": "-20037508.34 20037508.34",
                        "ows:Identifier": "16",
                        "ScaleDenominator": "8530.9183353991"
                    },
                    {
                        "TileWidth": "256",
                        "TileHeight": "256",
                        "MatrixWidth": "131072",
                        "MatrixHeight": "131072",
                        "TopLeftCorner": "-20037508.34 20037508.34",
                        "ows:Identifier": "17",
                        "ScaleDenominator": "4265.4591676996"
                    },
                    {
                        "TileWidth": "256",
                        "TileHeight": "256",
                        "MatrixWidth": "262144",
                        "MatrixHeight": "262144",
                        "TopLeftCorner": "-20037508.34 20037508.34",
                        "ows:Identifier": "18",
                        "ScaleDenominator": "2132.7295838498"
                    }
                ],
                "ows:Abstract": "GoogleMapsCompatible_256 EPSG:3857",
                "ows:Identifier": "GoogleMapsCompatible_256",
                "ows:SupportedCRS": "urn:ogc:def:crs:EPSG::3857"
            }
        }
    }

def createWMTSMapGeoNode():
    """
    Creates GeoNode map using only WMTS layers (no data uploads)
    """

    global HEIGHT_TO_TIP, STYLE_LOOKUP, FINALLAYERS_OUTPUT_FOLDER, GEONODE_BASE_URL, ADMIN_USERNAME, ADMIN_PASSWORD, TILESERVER_URL

    # Start off by checking GeoNode is active

    waitForGeoNode()

    # Get style-specific version of dataset hierarchy

    style_lookup = getStyleLookup()

    # Set height to tip from first element in style lookup

    HEIGHT_TO_TIP = float(style_lookup[0]['height-to-tip'])

    LogMessage("Creating GeoNode map...")

    session = requests.Session()
    session.auth = (ADMIN_USERNAME, ADMIN_PASSWORD)

    # Delete any maps with same name

    name = 'Wind Constraints Map - Tip Height ' + formatValue(HEIGHT_TO_TIP) + 'm'

    url = GEONODE_BASE_URL + "/api/v2/resources/?filter{resource_type}=map"
    response = session.get(url)

    response_json = json.loads(response.text)
    for resource in response_json['resources']:
        if resource['title'].strip() == name.strip():
            LogMessage("Deleting existing map with same name - id: " + str(resource['pk']))
            delete_url = GEONODE_BASE_URL + '/api/v2/resources/' + str(resource['pk'])
            session.delete(delete_url)

    # Generate map

    url = GEONODE_BASE_URL + "/api/v2/maps"

    group_structure = getStyleLookup()
    layers, output_groups, sources = [], [], {}
    index = 0
    for group in group_structure:
        group_id = str(uuid.uuid4())
        dataset_name = group['dataset']
        group_title = group['title']
        visibility = True
        if index == 0: visibility = False
        opacity = 1
        layers_item = getWMTSLayerItem(group_id, group_title, dataset_name, visibility, opacity)
        source_id = TILESERVER_URL + "/styles/" + dataset_name + "/wmts.xml"
        sources[source_id] = getWMTSDefaultSource()
        layers.append(layers_item)
        output_groups.append(getGroupItem(group_id, group_title, visibility))
        index += 1
        if 'children' not in group: continue
        for child in group['children']:
            dataset_name = child['dataset']
            child_title = child['title']
            visibility = False
            opacity = 0.8
            layers_item = getWMTSLayerItem(group_id, child_title, dataset_name, visibility, opacity)
            layers.append(layers_item)
            source_id = TILESERVER_URL + "/styles/" + dataset_name + "/wmts.xml"
            sources[source_id] = getWMTSDefaultSource()

    FINAL_PAYLOAD = {
        'abstract': name,
        'title': name,
        "data": {
            "version": 2,
            "toc": {},
            "widgetsConfig": {
                "widgets": [],
                "layouts": {
                    "md": [],
                    "xxs": []
                }
            },
            "mapInfoConfiguration": {},
            "featureGrid": {},
            "dimensionData": {},
            "timelineData": {
                "snapRadioButtonEnabled": False
            },
            "playback": {
                "settings": {
                    "timeStep": 1,
                    "stepUnit": "days",
                    "frameDuration": 2,
                    "following": True
                }
            },
            "catalogServices": {
                "services": {},
                "selectedService": ""
            },
            "map": {
                "center": {
                    "x": -3.289375305175791,
                    "y": 55.21478183186432,
                    "crs": "EPSG:4326"
                },                
                "layers": layers[::-1],
                "groups": output_groups,
                "backgrounds": [],
                "mapOptions": {},
                "projection": "EPSG:3857",
                "units": "m",
                "zoom": 6,
                "maxExtent": [
                    -20037508.34,
                    -20037508.34,
                    20037508.34,
                    20037508.34
                ],
                "sources": sources                
            }
        },
        "maplayers": []
    }

    LogMessage("Submitting create WMTS-only map request")

    session = requests.Session()
    session.auth = (ADMIN_USERNAME, ADMIN_PASSWORD)

    url = GEONODE_BASE_URL + "/api/v2/maps"

    response = session.post(url, json=FINAL_PAYLOAD)
    if response.status_code == 201: 
        LogMessage("Map request finished submitting successfully", )
    else:
        LogError("Problem creating map - error code:")
        print(response)


WMTS_ONLY = False

if WMTS_ONLY:
    createWMTSMapGeoNode()
else:
    datasets_info = uploadDatasets2GeoNode()
    createMapGeoNode(datasets_info)

print("""
\033[1;34m***********************************************************************
******************* OPEN WIND GEONODE UPLOAD COMPLETE *****************
***********************************************************************\033[0m

To view the layers/map in GeoNode, enter:

\033[1;94m""" + GEONODE_BASE_URL + """\033[0m

Username: \033[1;94m""" + ADMIN_USERNAME + """\033[0m
Password: \033[1;94m""" + ADMIN_PASSWORD + """\033[0m


""")
