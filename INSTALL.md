# Installation

## Software Required

- [PostGIS](https://postgis.net/): For storing and processing GIS data.

- `Python3.9`: For compatibility with [osm-export-tool](https://github.com/hotosm/osm-export-tool-python).

- [GDAL](https://gdal.org): For transferring data in and out of PostGIS.

- [QGIS](https://qgis.org/): For generating QGIS files.

- [tilemaker](https://github.com/systemed/tilemaker): For generating mbtiles version of OpenStreetMap for use as background map within MapLibre-GL.

- [tippecanoe](https://github.com/felt/tippecanoe): For generating optimized mbtiles versions of data layers for MapLibre-GL.

- [Docker](https://www.docker.com/): For previewing final data in TileServer-GL - *desirable but not mandatory*.

## Docker and Local (non-Docker) installs

The Open Wind toolkit has two flavours of build process:

- **1. Docker-based**: The entire build is run within Docker instances. This is the recommended option as it helps avoid installation issues.

- **2. Local (non-Docker) based**: All of the build runs without Docker. This may be desirable for performance reasons or when there is a need to quickly modify the codebase and / or resolve technical issues. There may, however, be a need to run Docker after the build has completed in order to view results through a Dockerized tileserver. 

## Software Platforms

We have covered installations for Ubuntu and Mac OS below but the broad installation process should work for other platforms, especially when using a **Docker-based install**. 

If you have specific success or issues running the Open Wind toolkit on other platforms, please drop us an email at support@openwind.org

Next steps:

- For Ubuntu, go to [1a. Ubuntu - All Installs](#1a-ubuntu---all-installs)

- For Mac, go to [1b. Mac - All Installs](#1b-mac---all-installs)

## 1a. Ubuntu - All Installs

Install [QEMU](https://www.qemu.org/download/):

```
sudo apt-get update
sudo apt install qemu-user-static binfmt-support
```

Install Docker using [these official instructions](https://docs.docker.com/engine/install/ubuntu/) or with:
```
sudo apt-get update
sudo apt-get install ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin -y
```

### Next steps:

- If you want to create a **Docker-based Install**, go to section [2. All Platforms - Docker-based Install -> Build -> View](#2-all-platforms---docker-based-install---build---view).

- If you want to create a **Local (non-Docker) Install**, go to section [3a. Ubuntu - Local (non-Docker) install](#3a-ubuntu---local-non-docker-install).

## 1b. Mac - All Installs

Install [QEMU](https://www.qemu.org/download/):

```
brew install qemu
```

Install Docker using [these official instructions](https://docs.docker.com/desktop/setup/install/mac-install/) or with:
```
brew install docker
```
### Next steps:

- If you want to create a **Docker-based Install**, go to section [2. All Platforms - Docker-based Install -> Build -> View](#2-all-platforms---docker-based-install---build---view).

- If you want to create a **Local (non-Docker) Install**, go to section [3b. Mac - Local (non-Docker) install](#3b-mac---local-non-docker-install).

## 2. All Platforms - Docker-based Install -> Build -> View

If you're running the Open Wind toolkit in the **Docker-based** mode, run the Open Wind build stage by typing:
```
./build-docker.sh
```
This will use a default value (124.2 metres) for the turbine height to tip. 

Alternatively, specify the turbine height to tip by adding it to the prompt:
```
./build-docker.sh [HEIGHT TO TIP]
```
For example:
```
./build-docker.sh 99.5
./build-docker.sh 129
./build-docker.sh 149.9
``` 
Once the build has completed (10-20 hours), view the final Open Wind constraint layers by running:
```
./run-docker.sh
```
Or alternatively open the QGIS file located at `build-docker/windconstraints--latest.qgs`.

### Next steps:

- Your installation is complete!

## 3a. Ubuntu - Local (non-Docker) Install

Install `PostGIS`, `Python3.9`, `GDAL`, `QGIS`, general software and libraries required to compile `tilemaker` and `tippecanoe`:

```
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install  gnupg software-properties-common cmake make g++ dpkg ca-certificates \
                  libbz2-dev libpq-dev libboost-all-dev libgeos-dev libtiff-dev libspatialite-dev \
                  liblua5.4-dev rapidjson-dev libshp-dev libgdal-dev shapelib \
                  spatialite-bin sqlite3 lua5.4 gdal-bin virtualenv \
                  zip unzip curl nano wget pip git nodejs npm proj-bin \
                  postgresql-postgis qgis qgis-plugin-grass \
                  python3.9 python3.9-dev python3.9-venv python3-gdal -y
```
Install `tippecanoe` with:

```
git clone https://github.com/felt/tippecanoe
cd tippecanoe
make -j
sudo make install
cd ..
```
Check `tippecanoe` has installed correctly by typing:
```
tippecanoe --help
```

Install `tilemaker` with:

```
git clone https://github.com/systemed/tilemaker.git
cd tilemaker
make
sudo make install
cd ..
```
Check `tilemaker` has installed correctly by typing:
```
tilemaker --help
```

### Next steps:
- Move to section [4. All Platforms - Local (non-Docker) Install](#4-all-platforms---local-non-docker-install).

## 3b. Mac - Local (non-Docker) Install

Install `PostGIS`, `Python3.9`, `GDAL`, `tippecanoe`, general software and libraries required to compile `tilemaker`:

```
brew install postgis python@3.9 gdal tippecanoe cmake make geos rapidjson gqis \
libpq libtiff libspatialite lua shapelib sqlite curl proj node npm virtualenv
```
Install `tilemaker` with:

```
git clone https://github.com/systemed/tilemaker.git
cd tilemaker
make
sudo make install
cd ..
```
Check `tilemaker` has installed correctly by typing:
```
tilemaker --help
```

### Next steps:

- Move to section [4. All Platforms - Local (non-Docker) Install](#4-all-platforms---local-non-docker-install).

# 4. All Platforms - Local (non-Docker) Install

### Install Node Version Manager (`nvm`) and `togeojson`:
```
curl --silent -o- https://raw.githubusercontent.com/creationix/nvm/v0.31.2/install.sh | bash
source ~/.bashrc

nvm install v10.19.0
nvm use v10.19.0
npm install -g @mapbox/togeojson
```
Check `togeosjon` has installed correctly by typing:
```
togeojson
```

### Clone Open Wind project repository:

```
git clone https://github.com/open-wind/openwind.git
cd openwind
```

Copy environment file template `.env-template` to `.env` and activate a Python 3.9 virtual environment:
```
cp .env-template .env

which python3.9
[PATH TO PYTHON 3.9]

virtualenv -p [PATH TO PYTHON 3.9 - FROM ABOVE] venv

source venv/bin/activate
```

### Install correct version of `GDAL`
Install correct version of `GDAL` Python module so it exactly matches installed (non-Python) version of `GDAL`:
```
pip3 install gdal==`gdal-config --version`
```

### Install Python modules required for Open Wind
```
pip3 install -r requirements.txt
pip3 install git+https://github.com/hotosm/osm-export-tool-python --no-deps
```

### Set QGIS environment variables
Edit `.env` file and set `QGIS_PREFIX_PATH` and `QGIS_PYTHON_PATH` environment variables for QGIS:
```
QGIS_PREFIX_PATH=[ABSOLUTE PATH TO FOLDER CONTAINING QGIS]
QGIS_PYTHON_PATH=[ABSOLUTE PATH TO QGIS VERSION OF PYTHON3]
```
Typical values for these variables are:
```
[Ubuntu]

QGIS_PREFIX_PATH=/usr/
QGIS_PYTHON_PATH=/usr/bin/python3


[Mac]

QGIS_PREFIX_PATH=/Applications/QGIS.app/Contents/MacOS/
QGIS_PYTHON_PATH=/Applications/QGIS.app/Contents/MacOS/bin/python3
```
To ensure you have the correct `QGIS_PYTHON_PATH` value, enter it into the command line. For example:
```
/usr/bin/python3

or

/Applications/QGIS.app/Contents/MacOS/bin/python3
```
This should load QGIS's version of Python:
```
Python 3.9.5 (default, Sep 10 2021, 16:18:19) 
[Clang 12.0.5 (clang-1205.0.22.11)] on darwin
Type "help", "copyright", "credits" or "license" for more information.
>>> 
```
Enter the following to atempt to load the QGIS Python module:
```
from qgis.core import (QgsProject)
```
If you are running the correct QGIS version of Python, this should return without generating a `ModuleNotFoundError` message like:
```
ModuleNotFoundError: No module named 'qgis' <-- **** ERROR IF INCORRECT QGIS_PYTHON_PATH
```
If you see a "Cannot find proj.db" error message, you will need to set the `QGIS_PROJ_DATA` environment variable in `.env` to the folder of your `PROJ` library containing `proj.db`:
```
PROJ_DATA=/path/to/proj/
```
To find potential values for `QGIS_PROJ_DATA`, type:
```
sudo find / -name proj.db
```
Once you have set the value of `QGIS_PROJ_DATA` in `.env`, reload environment variables in `.env` and attempt to run QGIS Python again:
```
source ./.env


/usr/bin/python3

[or] 

/Applications/QGIS.app/Contents/MacOS/bin/python3

[or]

/your/path/to/QGIS/python


[When Python loads, enter:]

from qgis.core import (QgsProject)
```
This should load the `qgis.core` Python module without generating errors. If so, press `CTRL-D` to quit QGIS Python and continue with the installation process.

### Set up PostGIS
Enter the commands below to set up a new PostGIS database for Open Wind:
```
sudo -u postgres createuser -P openwind
sudo -u postgres createdb -O openwind openwind
sudo -u postgres psql -d openwind -c 'CREATE EXTENSION postgis;'
sudo -u postgres psql -d openwind -c 'GRANT ALL PRIVILEGES ON DATABASE openwind TO openwind;'
```
When prompted, use password `password` - or enter a different password and edit the `POSTGRES_PASSWORD` variable in the `.env` file accordingly.

### Install openmaptiles fonts
Install folder of openmaptiles fonts:
```
git clone https://github.com/openmaptiles/fonts
cd fonts
npm install
node ./generate.js
```
If you experience problems compiling openmaptiles fonts, you will need to add the `--skipfonts` argument to all build commands:
```
./build-cli.sh 149.9 --skipfonts
```
This will instruct the build process to avoid attempting an install of openmaptiles fonts and will use a CDN version of the necessary fonts instead.

### Next steps:

- Go to [All Platforms - Local (non-Docker) Install](#5-all-platforms---local-non-docker-install---build---view)

## 5. All Platforms - Local (non-Docker) Install -> Build -> View

To run the Open Wind build stage in **Local (non-Docker)** mode, type:
```
./build-cli.sh
```
This will use a default value (124.2 metres) for the turbine height to tip. 

Alternatively, explicitly specify the turbine height to tip by adding it to the prompt:
```
./build-cli.sh [HEIGHT TO TIP]
```
For example:
```
./build-cli.sh 99.5
./build-cli.sh 129
./build-cli.sh 149.9
``` 
Once the build has completed (10-20 hours), view the final Open Wind constraint layers by running:
```
./run-cli.sh
```
This runs a Docker-containerized version of the TileServer-GL tileserver to serve up `mbtiles` layers to a simple web map. 

Alternatively, you can view the final layers without using Docker by opening the QGIS file located at `build-cli/windconstraints--latest.qgs`.
