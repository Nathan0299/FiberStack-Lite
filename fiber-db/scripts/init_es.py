import os
import time
import requests
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("init_es")

ES_URL = os.getenv("ELASTIC_URL", "http://localhost:9200")

def wait_for_es():
    """Wait for Elasticsearch to be ready."""
    logger.info(f"Waiting for Elasticsearch at {ES_URL}...")
    for i in range(30):
        try:
            response = requests.get(f"{ES_URL}/_cluster/health")
            if response.status_code == 200:
                logger.info("Elasticsearch is ready!")
                return True
        except requests.exceptions.ConnectionError:
            pass
        time.sleep(2)
    logger.error("Elasticsearch failed to start.")
    return False

def create_index_templates():
    """Create index templates for logs and events."""
    
    # Logs Template
    logs_template = {
        "index_patterns": ["fiber-logs-*"],
        "template": {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
                "index.lifecycle.name": "fiber-logs-policy",
                "index.lifecycle.rollover_alias": "fiber-logs"
            },
            "mappings": {
                "properties": {
                    "@timestamp": { "type": "date" },
                    "service": { "type": "keyword" },
                    "level": { "type": "keyword" },
                    "message": { "type": "text" },
                    "logger": { "type": "keyword" },
                    "request_id": { "type": "keyword" },
                    "node_id": { "type": "keyword" },
                    "context": { "type": "object" }
                }
            }
        }
    }
    
    # Events Template
    events_template = {
        "index_patterns": ["fiber-events-*"],
        "template": {
            "mappings": {
                "properties": {
                    "@timestamp": { "type": "date" },
                    "event_type": { "type": "keyword" },
                    "node_id": { "type": "keyword" },
                    "severity": { "type": "keyword" },
                    "message": { "type": "text" },
                    "metadata": { "type": "object" }
                }
            }
        }
    }

    # Apply templates
    try:
        resp = requests.put(f"{ES_URL}/_index_template/fiber-logs-template", json=logs_template)
        resp.raise_for_status()
        logger.info("Created fiber-logs-template")
        
        resp = requests.put(f"{ES_URL}/_index_template/fiber-events-template", json=events_template)
        resp.raise_for_status()
        logger.info("Created fiber-events-template")
        
    except Exception as e:
        logger.error(f"Failed to create templates: {e}")

if __name__ == "__main__":
    if wait_for_es():
        create_index_templates()
