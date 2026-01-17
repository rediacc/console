#!/bin/bash

# Docker Mailserver Management Tool
# Simple wrapper for docker exec mailserver setup commands

CONTAINER_NAME="mailserver"

# Check if container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
  echo "Error: Container '${CONTAINER_NAME}' is not running."
  echo "Start the mail server with: source Rediaccfile && up"
  exit 1
fi

# Show help if no arguments provided
if [ $# -eq 0 ]; then
  echo "Docker Mailserver Management Tool"
  echo ""
  echo "Usage: ./tool.sh <command> [arguments...]"
  echo ""
  echo "Common commands:"
  echo "  email add <email> [password]       - Create new mail account"
  echo "  email update <email> [password]    - Update account password"
  echo "  email del <email>                  - Delete mail account"
  echo "  email list                         - List all mail accounts"
  echo ""
  echo "  alias add <alias> <target>         - Create email alias"
  echo "  alias del <alias> <target>         - Delete email alias"
  echo "  alias list                         - List all aliases"
  echo ""
  echo "  quota set <email> <quota>          - Set mailbox quota (e.g., 1G, 500M)"
  echo "  quota del <email>                  - Remove quota limit"
  echo ""
  echo "  config dkim [keysize N]            - Generate DKIM keys"
  echo ""
  echo "  help                               - Show all available commands"
  echo ""
  echo "Examples:"
  echo "  ./tool.sh email add user@example.com secretpass123"
  echo "  ./tool.sh email list"
  echo "  ./tool.sh alias add info@example.com admin@example.com"
  echo "  ./tool.sh quota set user@example.com 2G"
  echo "  ./tool.sh config dkim"
  echo ""
  exit 0
fi

# Execute setup command with all arguments
docker exec "${CONTAINER_NAME}" setup "$@"
