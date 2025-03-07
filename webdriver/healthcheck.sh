curl --fail-with-body "http://0.0.0.0:$WEBDRIVERPORT/status" | jq '.value.ready == true'
