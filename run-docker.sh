#! /bin/bash -l

# Start tileserver-gl

. ./.env

echo "Running tileserver-gl..."

if [ -n "${BUILD_FOLDER+1}" ]; then
    docker run --name openwind-tileserver -d --rm -v "$BUILD_FOLDER"tileserver/:/data -p 8080:8080 maptiler/tileserver-gl --config config.json
else
    docker run --name openwind-tileserver -d --rm -v $(pwd)/build-docker/tileserver/:/data -p 8080:8080 maptiler/tileserver-gl --config config.json
fi


# Run simple webserver

echo -e ""
echo -e "\033[1;34m***********************************************************************\033[0m"
echo -e "\033[1;34m****************** OPEN WIND WEB + TILE SERVER RUNNING ****************\033[0m"
echo -e "\033[1;34m***********************************************************************\033[0m"
echo -e ""
echo -e "Open web browser and enter:"
echo -e ""
echo -e "\033[1;94mhttp://localhost:8000/\033[0m"
echo -e ""
echo -e ""

if [ -n "${BUILD_FOLDER+1}" ]; then
    cd "$BUILD_FOLDER"app
else
    cd build-docker/app
fi

python3 -m http.server 
cd ../../

# Stop tileserver-gl

echo "Closing tileserver-gl..."

docker kill openwind-tileserver