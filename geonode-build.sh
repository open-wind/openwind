#!/bin/bash


# Enforce emulation on Docker

export DOCKER_DEFAULT_PLATFORM=linux/amd64


# Clean any existing directories

sudo rm -r geonode
mkdir -p geonode
cd geonode


# Clone geonode 4.4.1

sudo rm -r geonode-project
git clone https://github.com/GeoNode/geonode-project.git
cd geonode-project
git checkout 4.4.1
cd ..


# Setup directory with settings and Django project

sudo rm -r openwind-project
mkdir -p openwind-project
virtualenv -p "$(which python3)" openwind-project/venv
. openwind-project/venv/bin/activate
pip install Django==3.2.13 
django-admin startproject --template=./geonode-project -e py,sh,md,rst,json,yml,ini,env,sample,properties -n monitoring-cron -n Dockerfile openwind openwind-project


# Run docker

cd openwind-project
python create-envfile.py --noinput
docker compose build
docker compose up -d
cd ../../
