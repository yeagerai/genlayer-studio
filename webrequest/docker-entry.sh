#!/usr/bin/env bash

set -ex

/usr/lib/jvm/java-17-openjdk-amd64/bin/java \
    -jar "$base/$selpath/selenium-server-4.24.0.jar" \
    standalone \
    -I chrome \
    --port "$WEBREQUESTSELENIUMPORT" --host 0.0.0.0 \
    &

python3 server.py

