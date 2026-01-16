#!/bin/bash
set -e

# Load environment variables from .env file
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Set THREADS to CPU core count but cap at 8
if [ -z "$THREADS" ]; then
    THREADS=$(($(nproc) > 8 ? 8 : $(nproc)))
fi

# Detect container name from docker compose
CONTAINER_NAME=$(docker inspect $(docker compose ps -q db) --format '{{.Name}}' 2>/dev/null | sed 's/^\/*//')

# Extract the Docker-assigned port
PGPORT=$(docker port "$CONTAINER_NAME" 5432 2>/dev/null | cut -d: -f2)

# Fallback to default port if container is not running
: "${PGPORT:=5432}"

export PGHOST PGPORT PGUSER PGPASSWORD

# Function to install required packages for PostgreSQL sysbench testing
host_setup() {
    echo "Installing required packages for PostgreSQL sysbench testing..."

    # Update package list
    sudo apt-get update

    # Install PostgreSQL client tools
    sudo apt-get install -y postgresql-client

    # Install sysbench
    sudo apt-get install -y sysbench

    # Verify installations
    echo "Checking installed versions:"
    psql --version
    sysbench --version

    echo "Host setup completed successfully!"
    return $?
}

# Function to execute PostgreSQL commands using psql
pg_exec() {
    psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$DBNAME" -c "$1"
}

# Function to check and create database if it does not exist
create_database() {
    if ! pg_exec "SELECT 1 FROM pg_database WHERE datname = '$DBNAME'" | grep -q 1; then
        echo "Database $DBNAME does not exist. Creating..."
        psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -c "CREATE DATABASE $DBNAME"
    else
        echo "Database $DBNAME already exists, not creating."
    fi
}

# Function to prepare the database for sysbench
initialize_sysbench() {
    sysbench /usr/share/sysbench/oltp_write_only.lua --db-driver=pgsql \
        --pgsql-host=$PGHOST --pgsql-port=$PGPORT --pgsql-user=$PGUSER --pgsql-password=$PGPASSWORD \
        --pgsql-db=$DBNAME --threads=$THREADS --tables=$TABLES --table-size=$TABLE_SIZE prepare
}

# Benchmark Query Per Second (QPS)
benchmark_qps() {
    echo "Starting Query Per Second (QPS) benchmark..."
    sysbench /usr/share/sysbench/oltp_point_select.lua --db-driver=pgsql \
        --pgsql-host="$PGHOST" --pgsql-port=$PGPORT --pgsql-user="$PGUSER" --pgsql-password="$PGPASSWORD" \
        --pgsql-db="$DBNAME" --threads="$THREADS" --tables="$TABLES" --table-size="$TABLE_SIZE" \
        --time=60 --report-interval=10 run
}

# Cleanup the database from sysbench
cleanup_sysbench() {
    sysbench /usr/share/sysbench/oltp_write_only.lua --db-driver=pgsql \
        --pgsql-host=$PGHOST --pgsql-port=$PGPORT --pgsql-user=$PGUSER --pgsql-password=$PGPASSWORD \
        --pgsql-db=$DBNAME --threads=$THREADS --tables=$TABLES --table-size=$TABLE_SIZE cleanup
}

