# Hamops 
Implementation of a FastAPI and an MCP Server for Ham Operations

## Features


## Installation

'''
gcloud run deploy hamops \
  --source . \
  --region us-central1 \
  --allow-unauthenticated

'''


docker build -t hamops .



gcloud run services describe hamops \
  --region us-central1 \
  --format="value(status.url)"