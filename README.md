# Open Wind Energy

The Open Wind Energy toolkit builds and displays onshore wind turbine site constraints in a fully automated way - avoiding the need for manually downloading and processing multiple GIS datasets by hand. 

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

For an overview of how the toolkit works, see ['How it works'](#how-it-works), below.

## Quickstart

Install [Docker](https://docker.com) then run:

```
git clone https://github.com/open-wind/openwindenergy.git
cd openwindenergy
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

This will display the following map:

## Open Wind Energy site constraints map

![Open Wind Energy Site Constraints Map](/openwindenergy-image-map.png)

This map is also available at [https://map.openwind.energy](https://map.openwind.energy). 

The map uses vanilla Javascript, [MapLibre-GL](https://github.com/maplibre/maplibre-gl-js) and [TileServer-GL](https://github.com/maptiler/tileserver-gl) and is straightforward to modify by a developer with basic HTML / Javascript skills. 

Note: the live map has been produced using the Open Wind Energy toolkit with no changes to the underlying source code or HTML.

## Installation 

See [INSTALL.md](INSTALL.md). 

## Turbine-specific wind site constraints

By default the Open Wind Energy toolkit creates onshore wind site constraints for turbines with a height to tip of **124.2 metres** and blade radius of **47.8 metres** - the average height to tip and average blade radius of all large (>= 75 metre to tip height) failed and successful pre-2025 wind turbine planning applications according to Open Wind Energy's research. 

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

To specify the blade radius, add this value after the `[HEIGHT TO TIP]`:

```
./build-docker.sh [HEIGHT TO TIP] [BLADE RADIUS]
```

For example:

```
./build-docker.sh 99.5 30.5
./build-docker.sh 120 40
./build-docker.sh 149.9 45
```

If using a localised (non-Docker) version of toolkit:

```
./build-cli.sh [HEIGHT TO TIP]

./build-cli.sh 99.5 30.5
./build-cli.sh 120 40
./build-cli.sh 149.9 45
```

Note: **[HEIGHT TO TIP]** and **[BLADE RADIUS]** parameters should only be numbers - so remove `m`, `metres`, etc.

## Minimum platform requirements

To run the Open Wind Energy build process, you will need a computer with the following minimum configuration:

- 12Gb memory
- 90Gb hard disk

## Typical timings

To run the entire build process - from generating the necessary Docker instances (if using Docker) to outputting the final files - will take between 10 and 20 hours. Once an initial build is completed, however, it will take considerably less time to generate wind site constraints for turbines with different tip heights. 

To improve performance, PostGIS should be run on an optimized platform, eg. a high-performance cloud-based database service, as much of the time-consuming processing involves PostGIS spatial queries. 

## Build files
Output files will be created in `build-cli/` or `build-docker/` and will be located in the following folders:

### `output`
Contains Open Wind Energy output files for each final data layer. Each layer will have a `GeoJSON`, `ESRI Shapefile` and `GeoPackage` version. 

Files will be called either `tip-...` or `latest-...`: 

- `tip-...` files will be unchangeable over time (assuming source data doesn't change), regardless of number of times toolkit is run.

- `latest-...` files represent *latest* build and are overwritten each time toolkit is run. 

As different `[HEIGHT TO TIP]` or `[BLADE RADIUS]` parameters are run, the `output` folder will fill up with additional height-to-tip- and blade-radius-specific files, eg. `tip-99-5m-bld-35-5m--inland-waters.gpkg`, `tip-120-m-bld-45-m--inland-waters.gpkg`, etc.

### `tileserver`
Contains complete folder required to run [TileServer-GL](https://github.com/maptiler/tileserver-gl) instance. MapBox Tiles (`mbtiles`) files will be created in `tileserver/data/` while style definitions will be created in `tileserver/styles/`. 

You can either run your own [TileServer-GL](https://github.com/maptiler/tileserver-gl) instance to serve up these files (see https://github.com/maptiler/tileserver-gl) or create an account with [MapBox](https://www.mapbox.com/) and upload your `mbtiles` files to this account so MapBox can serve them.

### `app`
Contains simple [MapLibre-GL](https://github.com/maplibre/maplibre-gl-js) map application using vanilla Javascript (`index.html` and `datasets-latest-style.js`). Note: you will need a running [TileServer-GL](https://github.com/maptiler/tileserver-gl) instance to use this map (see `tileserver`, above). The `run-cli.sh` and `run-docker.sh` scripts create a temporary Docker instance of TileServer-GL to allow the `mbtiles` files in `tileserver/data/` to be loaded.

### `datasets-downloads`
Contains all downloaded datasets, converted into either `GeoJSON` or `GeoPackage` files.

### `osm-export-yml`
Contains all downloaded [osm-export-tool](https://github.com/hotosm/osm-export-tool-python) `yml` files. These files are used to generate OpenStreetMap `GeoPackage` files from the OpenStreetMap bulk download (`[build-folder]/united-kingdom-latest.osm.pbf`).

## Custom configuration and custom clipping

The Open Wind Energy data portal provides a full definition of datasets, dataset-specific buffers and related styling. The Open Wind Energy toolkit also uses a default *clipping area* - the coastline of the United Kingdom - to clip all final data layers for UK onshore wind. 

If elements of the default configuration need to be modified - for example, to modify default buffers or closely crop on a specific area - this can be done using custom configuration `YML` files or by supplying a clipping area in the command line. 

Possible customizations include:

- **Country-specific output**: Select only datasets for a specific country. This may be desirable if an organisation's focus is country-specific and/or to reduce overall processing time - processing time is less for country-specific configurations as the number and size of datasets to process is reduced.

- **Custom buffers**: Buffer areas indicate the padding around specific GIS features where a turbine is not appropriate. With a custom configuration file you can override the default buffer values Open Wind Energy uses.

- **Custom datasets**: Select a subset of datasets from those on the Open Wind Energy data portal.

- **Custom styling**: Select specific colours for displaying the final dataset groups. 

- **Custom clipping**: Clip final results on a specific country or council area, eg. `Scotland` or `Essex`, or group of countries / council areas, eg. `Essex` *and* `Suffolk` *and* `Cambridgeshire`. This may be useful to local authorities or energy companies focused on specific areas of the UK.

### Example custom configuration - `scotland`:

![Open Wind Energy Custom Configuration - Scotland](/openwindenergy-image-custom-scotland.png)

This map was generated by entering:

```
./build-cli.sh --custom scotland
```

### Custom configuration files

There are three ways to use a custom configuration file:

- **Local file**: Specify path to local `YML` configuration file.

- **Internet URL**: Specify internet URL of `YML` configuration file.

- **Specify configuration name**: Specify *name* of configuration from list of available configurations on [Open Wind Energy Configuration Area](https://data.openwind.energy/group/custom). The system will then download the configuration file with the same title from the data portal.

To use a local custom configuration file:
```
./build-cli.sh --custom /path/to/custom.yml
./build-docker.sh --custom /path/to/custom.yml

[For example]

./build-cli.sh --custom configuration/custom-openwindenergy.yml
./build-docker.sh --custom configuration/custom-openwindenergy.yml
```

To use a custom configuration file on the internet:
```
./build-cli.sh --custom https://yourdomain.org/custom-openwindenergy.yml
./build-docker.sh --custom https://yourdomain.org/custom-openwindenergy.yml
```

To use a specific configuration from the [Open Wind Energy Configuration Area](https://data.openwind.energy/group/custom):
```
./build-cli.sh --custom [Name of configuration - if spaces, include quotes]
./build-docker.sh --custom [Name of configuration - if spaces, include quotes]

[For example]

./build-cli.sh --custom 'Open Wind Energy'
./build-docker.sh --custom 'Open Wind Energy'
```

To specify a particular country configuration file from the data portal, use `england`, `wales`, `scotland` or `northern-ireland`. For example:

```
./build-cli.sh --custom england
./build-cli.sh --custom wales
./build-cli.sh --custom scotland
./build-cli.sh --custom northern-ireland

[or for Docker-based builds]

./build-docker.sh --custom england
./build-docker.sh --custom wales
./build-docker.sh --custom scotland
./build-docker.sh --custom northern-ireland
```


A number of sample `YML` custom configuration files are provided within the `configuration/` folder:
```
custom-council.yml
custom-england.yml
custom-great-britain.yml
custom-northern-ireland.yml
custom-openwindenergy.yml
custom-scotland.yml
custom-wales.yml
```

### Elements of `YML` custom configuration file:

```
# Wind turbine height-to-tip to use
tip-height:
  124.2

# Wind turbine blade radius to use
blade-radius:
  47.8

# OpenStreetMap download to use
osm:
  https://download.geofabrik.de/europe/united-kingdom-latest.osm.pbf

# Clipping area to use
clipping:
  - england
  - wales
  - scotland
  - northern-ireland

# Countries to use when selecting datasets
# Note: 'uk' is required to download OSM datasets that are not country-specific
areas:
  - england
  - wales
  - scotland
  - northern-ireland
  - uk

# Specific datasets from data.openwind.energy to use
# Note: any datasets must exist on data.openwind.energy to be used
structure:
  aviation-and-exclusion-areas:
    - airspace--uk
    - civilian-airports--uk
    ...

# Specific buffer values (in metres) to use for each dataset
# Note: any datasets must exist on data.openwind.energy to be buffered
buffers: 
  hedgerows--uk: 
    50
  inland-waters--uk:
    1.1 * height-to-tip
  separation-distance-from-residential--uk:
    8 * blade-radius
  ...

# Colours to use for each dataset group when displaying final data layers
style:
  aviation-and-exclusion-areas:
    color:
      purple
  ecology-and-wildlife:
    color:
      darkgreen
  ...
 
```
Note: all elements are entirely optional and do not need to be included in a custom configuration file - if values are omitted, default values from Open Wind Energy data portal will be used.

### Custom clipping area

You can specify a custom clipping area that will be used for clipping all final datasets before they are output. To specify a custom clipping area, add the `--clip` argument:

```
./build-cli.sh --clip [area]
./build-docker.sh --clip [area]
```

For example
```
./build-cli.sh --clip 'Brighton and Hove'
./build-docker.sh --clip Highland
```

If a non-country area is supplied, the data pipeline will determine the country the clipping area is in and will *only* select datasets for that country (excluding OpenStreetMap datasets that are only limited by the value of the `osm` parameter).

To provide multiple values for the clipping area, ie. to create a clipping area that is a composite of several specific areas, use a custom configuration file instead. For example

```
clipping:
  - Suffolk
  - Essex
  - Cambridgeshire
```

This will clip the final dataset layers on `Suffolk` *and* `Essex` *and* `Cambridgeshire`.

## Additional scripts

- `geonode-build.sh`: Creates local copy of [GeoNode](https://geonode.org/) map server.

- `geonode-upload.py`: Uploads post-build datasets to local copy of GeoNode created through `geonode-build.sh`. 

Note: due to raster-based focus of GeoNode / GeoServer together with the complexity of final Open Wind Energy datasets, a high performance computer is recommended to run GeoNode with Open Wind Energy constraint layers.

## Command line parameters
The toolkit accepts the following optional command line arguments:

- `[HEIGHT TO TIP]`: Height to tip in metres of intended wind turbine. This parameter is used to generate turbine-height-specific buffers. Note: enter number only, omitting `m`, `metres`, etc. 

- `--custom [path/URL/name of custom configuration file]`: Specify path, URL or name of `YML` custom configuration file. See [Custom configuration and custom clipping](#custom-configuration-and-custom-clipping).

- `--clip [clipping area to use]`: Specific clipping area to use on final dataset layers. See [Custom configuration and custom clipping](#custom-configuration-and-custom-clipping).

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

- `QGIS_PROJ_DATA`: Absolute path to `PROJ` library directory, eg. `/usr/share/proj`.

There are also **optional** environment variables that can be set in `.env`:

- `BUILD_FOLDER`: Absolute path to build folder where datasets will be downloaded and output files created. This will replace the default `build-cli/` build folder. *Note: only used if local (non-Docker) build.*

- `TILESERVER_URL`: URL of [TileServer GL](https://github.com/maptiler/tileserver-gl) instance where you will host your mbtiles, eg. `https://tiles.openwind.energy`. This variable is used when creating the MapLibre-GL test site in `[build-directory]/app/index.html` and the related TileServer-GL `*.json` style files in `[build-directory]/tileserver/styles/`.

- `GEONODE_BASE_URL`: URL of GeoNode instance to use when uploading data to GeoNode instance through `geonode-upload.sh`. *Note: only used if local (non-Docker) build.*

- `GEOSERVER_BASE_URL`: URL of GeoServer instance to use when uploading data to GeoNode instance through `geonode-upload.sh`. *Note: only used if local (non-Docker) build.*

- `ADMIN_USERNAME`: Username of GeoNode user to use when uploading data to GeoNode instance through `geonode-upload.sh`. *Note: only used if local (non-Docker) build.*

- `ADMIN_PASSWORD`: Password of GeoNode user to use when uploading data to GeoNode instance through `geonode-upload.sh`. *Note: only used if local (non-Docker) build.*

## How it works

### 1. Download latest definition of onshore wind site constraints
The toolkit downloads the latest definition of onshore wind site constraints, including recommended buffers, from the Open Wind Energy [CKAN](https://ckan.org/) open data portal [data.openwind.energy](https://data.openwind.energy). 

The definition contains updated information about where to locate the required datasets as well as higher level information about how to organise, process and amalgamate datasets once they have been downloaded. 

See [Open Data Portal (CKAN) Custom Fields](#open-data-portal-ckan-custom-fields), below, for information about custom fields used in [CKAN](https://ckan.org/) to describe how datasets should be processed. 

### 2. Download and import required datasets
The toolkit downloads open source datasets from third party websites, eg. Historic England or OpenDataNI, and imports them into PostGIS. The range of data formats the toolkit currently supports include:

- `GeoJSON`
- `GeoPackage`
- `ArcGIS`
- `WFS`
- `KML` / `KMZ`
- [osm-export-tool](https://github.com/hotosm/osm-export-tool-python) `yml`

[osm-export-tool](https://github.com/hotosm/osm-export-tool-python) `yml` files are used to define and import specific OpenStreetMap (https://www.openstreetmap.org/) datasets, eg. railways or major roads.

### 3. Process imported datasets
For each imported dataset in PostGIS, the toolkit adds buffers where appropriate, clips each dataset to a predefined clipping path (currently UK coastline) and dissolves overlapping geometries. The toolkit then amalgamates geographically-specifically database tables to create a single unified table for the entire target area. 

For example, the following tables will be amalgamated to create the table `tip_any__national_parks`:

```
national_parks__scotland__pro
national_parks__england__pro
national_parks__wales__pro
national_parks__northern_ireland__pro
```

 The toolkit then amalgamates tables by *group*, as defined in the Open Wind Energy open data portal [data.openwind.energy](https://data.openwind.energy) (see, for example, the group [Landscape and visual impacts](https://data.openwind.energy/group/landscape-and-visual-impacts)). 
 
The following tables, for example, will be amalgamated to create the table `tip_any__landscape_and_visual_impacts`:

```
tip_any__areas_of_outstanding_natural_beauty
tip_any__heritage_coasts
tip_any__national_parks
```

When layers include buffers that are turbine height-to-tip or blade-radius dependent, final layers are amalgamated into a single `tip_[HEIGHT TO TIP]_bld_[BLADE RADIUS]__windconstraints` database table that defines overall site constraints for a turbine with height **[HEIGHT TO TIP]** and blade radius **[BLADE RADIUS]**.

### 4. Export final layers
All PostGIS tables with prefix `tip_` will be exported as `GeoJSON`, `ESRI Shapefile`, `GeoPackage` and MapBox Vector Tiles (`mbtiles`). As the final wind constraint datasets are often highly detailed and interconnected, [Tippecanoe](https://github.com/felt/tippecanoe) is used to create optimized MapBox Vector Tiles that provide the most responsive user experience.

In addition to exporting separate layers, a [QGIS](https://qgis.org/) file is also generated that provides an overview of the latest exported layers. The QGIS file uses `GeoPackage` files in the `[build-folder]/output/` and does not require a tileserver to be running.

### 5. Post-build
Once the build has completed, the final wind site constraint layers can be viewed as follows:

#### Run local tileserver 
Type `./run-docker.sh` (or `./run-cli.sh` if non-Docker build) and enter `http://localhost:8000` into web browser.

#### Run QGIS
Install and run [QGIS](https://qgis.org/) and load exported QGIS file at `[build-folder]/windconstraints--latest.qgs`.

## Generalizing to other use cases

While the Open Wind Energy toolkit was specifically designed for onshore wind, the same codebase can be used to convert any CKAN data portal into final GIS layers for other use cases - for example solar farms, battery storage or green hydrogen. 

To change the source CKAN open data portal the toolkit uses, set the `CKAN_URL` in the `.env` environment file:

```
CKAN_URL=https://data.otherdomain
```

You can also add custom fields to the CKAN instance that modify toolkit processing using the following specification:

### Open Data Portal ([CKAN](https://ckan.org/)) Custom Fields

The following custom fields are used within the [CKAN](https://ckan.org/) [Open Wind Energy Data Portal](https://data.openwind.energy) to describe how datasets should be processed by the Open Wind Energy toolkit:

| Field | Value | Example | Description |
| ----------- | ----------- | ----------- | ----------- |
| `automation` | `exclude` | | Indicates dataset should not be included in automation process. This may be desirable when data portal is used to host non-constraint-related datasets that should not be included in final constraint layers. |
| `automation` | `intersect` | | *To be implemented.* |
| `buffer` | `[float]` | `50` | Absolute value in metres describing size of buffer to add to specific dataset. |
| `buffer` | `[float] * height-to-tip` | `1.1 * height-to-tip` | Fractional value in height-to-tip units describing size of buffer to add to specific dataset. |
| `buffer` | `[float] * blade-radius` | `1.1 * blade-radius` | Fractional value in blade-radius units describing size of buffer to add to specific dataset. |
| `color` | *html-color* | `red` or `#FF3300` | Colour to be used when displaying dataset or dataset group in final user interface. |
| `layer` | *layername* | `HES:Buildings_by_Category` | Specific layer to be downloaded from WFS endpoint. |

## Contact

info@openwind.energy

https://openwind.energy

## Thanks

We are grateful to the following individuals/organisations for their invaluable feedback and suggestions in shaping Open Wind Energy:

- Kayla Ente, [Brighton & Hove Energy Services Co-operative](https://bhesco.co.uk)
- Ben Cannell, [Sharenergy](https://sharenergy.coop)
- [Clive Howard](https://www.linkedin.com/in/clivehoward/)
- John Taylor, [Community Energy England](https://communityenergyengland.org/)
- Mike Childs, Magnus Gallie, Toby Bridgeman, [Friends of the Earth](https://friendsoftheearth.uk/)
- Catriona Cockburn, [Energise South Downs](https://esd.energy/)
- Ben Sharpe, [Energise South Coast](https://www.energisesussexcoast.co.uk/)
- Francis Cram, [MapStand](https://mapstand.com/)

## Copyright

Open Wind Energy Toolkit  
Copyright (c) Open Wind Energy, 2025  
Released under MIT License  

Developed by Stefan Haselwimmer  
