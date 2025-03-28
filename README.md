# Open Wind

The Open Wind toolkit builds and displays onshore wind turbine site constraints in a fully automated way - avoiding the need for manually downloading and processing multiple GIS datasets by hand. 

It is designed to save time and lower the barrier to entry for onshore wind site identification for the following users:

- Community energy groups
- Net Zero and fuel poverty organisations
- Local authorities
- Electricity companies

The toolkit also provides a streamlined process for generating different turbine-specific constraint layers and may be of interest to:

- Wind farm developers
- GIS analysts and data scientists

The toolkit outputs data in a number of industry-standard GIS formats:

- `GeoJSON`
- `ESRI Shapefile`
- `GeoPackage`
- Mapbox Vector Tiles (`mbtiles`)
- QGIS file

The toolkit also provides local versions of several popular GIS viewing clients for viewing the final wind site constraints:

- [MapLibre-GL](https://github.com/maplibre/maplibre-gl-js)
- [TileServer-GL](https://github.com/maptiler/tileserver-gl)
- [GeoNode](https://geonode.org/)

For an overview of how the toolkit works, see the [How it works](#how-it-works) section, below.

## Quickstart

Install [Docker](https://docker.com) then run:

```
git clone https://github.com/open-wind/openwind.git
cd openwind
./build-docker.sh
```

The process will take 10 to 20 hours to complete, depending on computer specification (see [Minimum platform requirements](#minimum-platform-requirements), below). 

Once the data build has completed, set up a temporary map tileserver by typing:

```
./run-docker.sh
```

Then view a simple map showing the final datasets by opening a web browser and entering:
```
http://localhost:8000
```

To see this map on the internet, go to [https://map.openwind.energy](https://map.openwind.energy). 

Note: the live map has been produced using the Open Wind toolkit with no changes to the underlying source code or HTML.

In the event of build issues or to install Open Wind toolkit on your computer without Docker, see [INSTALL.md](INSTALL.md).

## Turbine-specific wind site constraints

By default the Open Wind toolkit creates onshore wind site constraints for turbines with a height to tip of **124.2 metres** - the average height to tip of all failed and successful pre-2025 wind turbine planning applications according to Open Wind's research. 

To create wind site constraints for different turbines, add the height to tip value to the `build-docker.sh` prompt:

```
./build-docker.sh [HEIGHT TO TIP]
```

For example:

```
./build-docker.sh 99.5
./build-docker.sh 120
./build-docker.sh 149.9
```

If using a localised (non-Docker) version of toolkit:

```
./build-cli.sh [HEIGHT TO TIP]

./build-cli.sh 99.5
./build-cli.sh 120
./build-cli.sh 149.9
```

Note: **[HEIGHT TO TIP]** parameter should only be a number - so remove `m`, `metres`, etc.

## Minimum platform requirements

To run the Open Wind build process, you will need a computer with the following minimum configuration:

- 16Gb memory
- 80Gb hard disk

## Typical timings

To run the entire build process - from generating the necessary Docker instances (if using Docker) to outputting the final files - will take between 10 and 20 hours. Once an initial build is completed, however, it will take considerably less time to generate wind site constraints for turbines with different tip heights. 

To improve performance, PostGIS should be run on an optimized platform, eg. a high-performance cloud-based database service, as much of the time-consuming processing involves PostGIS spatial queries. 

## Build files
Output files will be created in `build-cli/` or `build-docker/` and will be located in the following folders:

### `output`
Contains Open Wind output files for each final data layer. Each layer will have a `GeoJSON`, `ESRI Shapefile` and `GeoPackage` version. 

Files will be called either `tipheight-...` or `latest-...`: 

- `tipheight-...` files will be unchangeable over time (assuming source data doesn't change), regardless of number of times toolkit is run. 

- `latest-...` files represent *latest* build and are overwritten each time toolkit is run. 

As different `[HEIGHT TO TIP]` parameters are run, the `output` folder will fill up with additional height-to-tip-specific files, eg. `tipheight-99-5m--inland-waters.gpkg`, `tipheight-120-m--inland-waters.gpkg`, etc.

### `tileserver`
Contains complete folder required to run [TileServer-GL](https://github.com/maptiler/tileserver-gl) instance. MapBox Tiles (`mbtiles`) files will be created in `tileserver/data/` while style definitions will be created in `tileserver/styles/`. 

You can either run your own [TileServer-GL](https://github.com/maptiler/tileserver-gl) instance to serve up these files (see https://github.com/maptiler/tileserver-gl) or create an account with [MapBox](https://www.mapbox.com/) and upload your `mbtiles` files to this account so MapBox can serve them.

### `app`
Contains simple [MapLibre-GL](https://github.com/maplibre/maplibre-gl-js) map application using vanilla Javascript (`index.html` and `datasets-latest-style.js`). Note: you will need a running [TileServer-GL](https://github.com/maptiler/tileserver-gl) instance to use this map (see `tileserver`, above). The `run-cli.sh` and `run-docker.sh` scripts create a temporary Docker instance of TileServer-GL to allow the `mbtiles` files in `tileserver/data/` to be loaded.

### `datasets-downloads`
Contains all downloaded datasets, converted into either `GeoJSON` or `GeoPackage` files.

### `osm-export-yml`
Contains all downloaded [osm-export-tool](https://github.com/hotosm/osm-export-tool-python) `yml` files. These files are used to generate OpenStreetMap `GeoPackage` files from the OpenStreetMap bulk download (`[build-folder]/united-kingdom-latest.osm.pbf`).

## Additional scripts

- `geonode-build.sh`: Creates local copy of [GeoNode](https://geonode.org/) map server.

- `geonode-upload.py`: Uploads post-build datasets to local copy of GeoNode created through `geonode-build.sh`. 

Note: due to raster-based focus of GeoNode / GeoServer together with the complexity of final Open Wind datasets, a high performance computer is recommended to run GeoNode with Open Wind constraint layers.

## Command line parameters
The toolkit accepts the following optional command line arguments:

- `[HEIGHT TO TIP]`: Height to tip in metres of intended wind turbine. This parameter is used to generate turbine-height-specific buffers. Note: enter number only, omitting `m`, `metres`, etc. 

- `--purgeall`: Clears all downloads, exports and database tables as if starting fresh.

- `--purgedb`: Clears all PostGIS tables and reexports final layer files.

- `--purgederived`: Clears all derived (ie. non-core data) PostGIS tables and reexports final layer files.

- `--purgeamalgamated`: Clears all amalgamated PostGIS tables and reexports final layer files.

- `--skipdownload`: Skips download stage and just does PostGIS processing.

- `--skipfonts`: Skips font installation stage and uses hosted version of openmaptiles fonts instead.

- `--regenerate` *dataset*: Regenerates specific *dataset* by redownloading and recreating all tables relating to *dataset*.

- `--buildtileserver`: Rebuilds files for tileserver.

### Environment variables
The toolkit uses environment variables from `.env` and automatically copies `.env-template` (containing default values) to `.env` if `.env` has not been created. 

If you need to modify the environment variables in `.env` script - for example to use a different PostGIS database or to resolve installation issues - the **mandatory** environment variables in `.env` are described below:

- `POSTGRES_HOST`: Hostname of PostGIS database server to use.

- `POSTGRES_DB`: PostGIS database to use.

- `POSTGRES_USER`: Username of user who will access `POSTGRES_DB`. The user needs full access permissions to `POSTGRES_DB`. 

- `POSTGRES_PASSWORD`: Password of user who will access `POSTGRES_DB`.

- `CKAN_URL`: URL of CKAN Open Data Portal to use to define wind (or other asset) site constraints.

- `QGIS_PREFIX_PATH`: Filesystem prefix to QGIS (see [Using PyQGIS in standalone scripts](https://docs.qgis.org/3.40/en/docs/pyqgis_developer_cookbook/intro.html#using-pyqgis-in-standalone-scripts)).

- `QGIS_PYTHON_PATH`: Absolute path to specific version of Python3 that QGIS uses, eg. `/usr/bin/python3`.

- `PROJ_DATA`: Absolute path to `PROJ` library directory, eg. `/usr/share/proj`.

There are also **optional** environment variables that can be set in `.env`:

- `BUILD_FOLDER`: Absolute path to build folder where datasets will be downloaded and output files created. This will replace the default `build-cli/` or `build-docker/` build folder.

- `TILESERVER_URL`: URL of [TileServer GL](https://github.com/maptiler/tileserver-gl) instance where you will host your mbtiles, eg. `https://tiles.openwind.energy`. This variable is used when creating the MapLibre-GL test site in `[build-directory]/app/index.html` and the related TileServer-GL `*.json` style files in `[build-directory]/tileserver/styles/`.

- `GEONODE_BASE_URL`: URL of GeoNode instance to use when uploading data to GeoNode instance through `geonode-upload.sh`.

- `GEOSERVER_BASE_URL`: URL of GeoServer instance to use when uploading data to GeoNode instance through `geonode-upload.sh`.

- `ADMIN_USERNAME`: Username of GeoNode user to use when uploading data to GeoNode instance through `geonode-upload.sh`.

- `ADMIN_PASSWORD`: Password of GeoNode user to use when uploading data to GeoNode instance through `geonode-upload.sh`.

## How it works

### 1. Download latest definition of onshore wind site constraints
The toolkit downloads the latest definition of onshore wind site constraints, including recommended buffers, from the Open Wind [CKAN](https://ckan.org/) open data portal [data.openwind.energy](https://data.openwind.energy). 

The definition contains updated information about where to locate the required datasets as well as higher level information about how to organise, process and amalgamate datasets once they have been downloaded. 

See [Open Data Portal (CKAN) Custom Fields](#open-data-portal-ckan-custom-fields), below, for information about custom fields used in [CKAN](https://ckan.org/) to describe how datasets should be processed. 

### 2. Download and import required datasets
The toolkit downloads open source datasets from third party websites, eg. Historic England or OpenDataNI, and imports them into PostGIS. The range of data formats the toolkit currently supports include:

- `GeoJSON`
- `ESRI Shapefile`
- `GeoPackage`
- `ArcGIS`
- `WFS`
- `KML` / `KMZ`
- [osm-export-tool](https://github.com/hotosm/osm-export-tool-python) `yml`

[osm-export-tool](https://github.com/hotosm/osm-export-tool-python) `yml` files are used to define and import specific OpenStreetMap (https://www.openstreetmap.org/) datasets, eg. railways or major roads.

### 3. Process imported datasets
For each imported dataset in PostGIS, the toolkit adds buffers where appropriate, clips each dataset to a predefined clipping path (currently UK coastline) and dissolves overlapping geometries. The toolkit then amalgamates geographically-specifically database tables to create a single unified table for the entire target area. 

For example, the following tables will be amalgamated to create the table `tipheight_any__national_parks`:

```
national_parks__scotland__pro
national_parks__england__pro
national_parks__wales__pro
national_parks__northern_ireland__pro
```

 The toolkit then amalgamates tables by *group*, as defined in the Open Wind open data portal [data.openwind.energy](https://data.openwind.energy) (see, for example, the group [Landscape and visual impacts](https://data.openwind.energy/group/landscape-and-visual-impacts)). 
 
The following tables, for example, will be amalgamated to create the table `tipheight_any__landscape_and_visual_impacts`:

```
tipheight_any__areas_of_outstanding_natural_beauty
tipheight_any__heritage_coasts
tipheight_any__national_parks
```

Final layers are then amalgamated into a single `tipheight_[HEIGHT TO TIP]__windconstraints` database table that defines overall site constraints for a turbine with height **[HEIGHT TO TIP]**.

### 4. Export final layers
All PostGIS tables with prefix `tipheight_` will be exported as `GeoJSON`, `ESRI Shapefile`, `GeoPackage` and MapBox Vector Tiles (`mbtiles`). As the final wind constraint datasets are often highly detailed and interconnected, [Tippecanoe](https://github.com/felt/tippecanoe) is used to create optimized MapBox Vector Tiles that provide the most responsive user experience.

In addition to exporting separate layers, a [QGIS](https://qgis.org/) file is also generated that provides an overview of the latest exported layers. The QGIS file uses `GeoPackage` files in the `[build-folder]/output/` and does not require a tileserver to be running.

### 5. Post-build
Once the build has completed, the final wind site constraint layers can be viewed as follows:

#### Run local tileserver 
Type `./run-docker.sh` (or `./run-cli.sh` if non-Docker build) and enter `http://localhost:8000` into web browser.

#### Run QGIS
Install and run [QGIS](https://qgis.org/) and load exported QGIS file at `[build-folder]/windconstraints--latest.qgs`.

## Generalizing to other use cases

While the Open Wind toolkit was specifically designed for onshore wind, the same codebase can be used to convert any CKAN data portal into final GIS layers for other use cases - for example solar farms, battery storage or green hydrogen. 

To change the source CKAN open data portal the toolkit uses, set the `CKAN_URL` in the `.env` environment file:

```
CKAN_URL=https://data.otherdomain
```

You can also add custom fields to the CKAN instance that modify toolkit processing using the following specification:

### Open Data Portal ([CKAN](https://ckan.org/)) Custom Fields

The following custom fields are used within the [CKAN](https://ckan.org/) [Open Wind Data Portal](https://data.openwind.energy) to describe how datasets should be processed by the Open Wind toolkit:

| Field | Value | Example | Description |
| ----------- | ----------- | ----------- | ----------- |
| `automation` | `exclude` | | Indicates dataset should not be included in automation process. This may be desirable when data portal is used to host non-constraint-related datasets that should not be included in final constraint layers. |
| `automation` | `intersect` | | *To be implemented.* |
| `buffer` | `[float]` | `50` | Absolute value in metres describing size of buffer to add to specific dataset. |
| `buffer` | `[float] * height_to_tip` | `1.1 * height_to_tip` | Fractional value in height-to-tip units describing size of buffer to add to specific dataset. |
| `color` | *html-color* | `red` or `#FF3300` | Colour to be used when displaying dataset or dataset group in final user interface. |
| `layer` | *layername* | `HES:Buildings_by_Category` | Specific layer to be downloaded from WFS endpoint. |

## Contact

info@openwind.energy

https://openwind.energy

## Copyright

Open Wind Toolkit  
Copyright (c) Open Wind, 2025  
Released under MIT License  

Developed by Stefan Haselwimmer  
