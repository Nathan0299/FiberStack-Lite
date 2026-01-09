# Safe Reset (Scoped to Sandbox)
cd "$(dirname "$0")/../simulation" && docker compose -f cluster-simulation.yml down -v --remove-orphans
