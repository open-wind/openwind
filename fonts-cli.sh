#! /bin/bash -l


# Download and convert fonts for tileserver-gl
# Use if build-cli.sh script fails during fonts copying/creation stage

export NVM_DIR=$HOME/.nvm;
source $NVM_DIR/nvm.sh;
nvm install v10.19.0
nvm use v10.19.0
git clone https://github.com/openmaptiles/fonts
cd fonts
npm install
node ./generate.js
cd ..
mkdir -p build-cli
mkdir -p build-cli/tileserver
cp -r fonts/_output/. build-cli/tileserver/fonts

