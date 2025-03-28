
# Dockerfile to generate tileserver-gl fonts


# Use lite version of Debian to save time

FROM debian:bookworm-slim

# FROM node:6


# Ensure noninteractive setup during container creation

ENV DEBIAN_FRONTEND=noninteractive 


# Install general tools and required libraries

RUN apt update
RUN apt install git nodejs npm -y
RUN apt update; exit 0


# Clone font repo and run font creation script

RUN git clone https://github.com/openmaptiles/fonts
WORKDIR /fonts
RUN npm install
RUN node generate.js


# Copy font-copying script to run on start that copies fonts into docker-build directory

WORKDIR /
COPY fonts-docker.sh .
RUN chmod +x fonts-docker.sh

CMD ["/bin/bash", "fonts-docker.sh"]
