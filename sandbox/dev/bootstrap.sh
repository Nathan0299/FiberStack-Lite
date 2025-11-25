#!/bin/bash
echo "Starting FiberStack Sandbox..."
docker compose -f docker-compose.sandbox.yml up --build
