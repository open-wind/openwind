
# Use Ubuntu 22.04 as problems building osm-export-tool with newer versions of Ubuntu

FROM ubuntu:22.04


# Ensure noninteractive setup during container creation

ENV DEBIAN_FRONTEND=noninteractive 


# Install general tools and required libraries

RUN apt update
RUN apt install gnupg software-properties-common cmake make g++ dpkg \
                libbz2-dev libpq-dev libboost-all-dev libgeos-dev libtiff-dev libspatialite-dev \
                libsqlite3-dev libcurl4-gnutls-dev liblua5.4-dev rapidjson-dev libshp-dev libgdal-dev gdal-bin \
                zip unzip lua5.4 shapelib ca-certificates curl nano wget pip git nodejs npm proj-bin spatialite-bin sqlite3 \
                qgis qgis-plugin-grass -y
RUN apt update; exit 0


# Install togeojson node library

RUN npm install -g @mapbox/togeojson


# Install Python3.9

RUN add-apt-repository ppa:deadsnakes/ppa
RUN apt update -y; exit 0
RUN apt install python3.9 python3.9-dev python3.9-venv python3-gdal -y


# Install tilemaker

WORKDIR /usr/src/openwind
RUN git clone https://github.com/systemed/tilemaker.git
WORKDIR /usr/src/openwind/tilemaker
RUN make
RUN make install


# Install tippecanoe

WORKDIR /usr/src/openwind
RUN git clone https://github.com/felt/tippecanoe.git
WORKDIR /usr/src/openwind/tippecanoe
RUN make -j
RUN make install


# Create Python virtual environment and install Python libraries

WORKDIR /usr/src/openwind
COPY requirements.txt .
RUN /usr/bin/python3.9 -m venv /usr/src/openwind/venv
ENV PATH="/usr/src/openwind/venv/bin:$PATH"
RUN pip3 install gdal==`gdal-config --version`
RUN pip3 install -r requirements.txt
RUN pip3 install git+https://github.com/hotosm/osm-export-tool-python --no-deps


# Install nvm
# https://github.com/creationix/nvm#install-script
RUN rm /bin/sh && ln -s /bin/bash /bin/sh
ENV NVM_DIR=/usr/local/nvm
ENV NODE_VERSION=10.19.0
RUN curl --silent -o- https://raw.githubusercontent.com/creationix/nvm/v0.31.2/install.sh | bash
RUN source $NVM_DIR/nvm.sh \
    && nvm install $NODE_VERSION \
    && nvm alias default $NODE_VERSION \
    && nvm use default
ENV NODE_PATH=$NVM_DIR/v$NODE_VERSION/lib/node_modules
ENV PATH=$NVM_DIR/versions/node/v$NODE_VERSION/bin:$PATH


# Set working directory and copy essential files into it

WORKDIR /usr/src/openwind
COPY tileserver tileserver
COPY build-cli.sh .
RUN chmod +x build-cli.sh
COPY openwind.py .
COPY build-qgis.py .
COPY uk--clipping.gpkg .
COPY .env-template .

CMD ["/bin/bash"]
