#! /bin/bash -l


# Copies fonts from local server to shared build-docker space

mkdir -p /build-docker/tileserver/

if [ -f "/build-docker/tileserver/fonts" ]; then
    rmdir -p /build-docker/tileserver/fonts
fi

cp -r /fonts/_output/. /build-docker/tileserver/fonts

