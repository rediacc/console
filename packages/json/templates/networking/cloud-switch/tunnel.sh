#!/bin/bash

CLOUDFLARE_TUNNEL_HOST="${CLOUDFLARE_TUNNEL_HOST:-"demo.rediacc.com"}"

CLOUDFLARE_DOCKER_IMAGE="cloudflare/cloudflared:2024.12.2"
CLOUDFLARE_TUNNEL_DOCKER="rediacc-template-cloudflared-docker"
CLOUDFLARE_TUNNEL_NAME="rediacc-template-cloudflared-tunnel-$(hostname)"
CLOUDFLARE_TUNNELED_SERVICE="http://localhost:5000"

FOLDER_HOST_CONFIG="./data/tunnel-config"
FOLDER_DOCKER_CONFIG="/home/nonroot/.cloudflared"

function _tunnel() {
    docker run \
      --name $CLOUDFLARE_TUNNEL_DOCKER \
      --network host                   \
      --rm                             \
      --volume $FOLDER_HOST_CONFIG:$FOLDER_DOCKER_CONFIG \
      $CLOUDFLARE_DOCKER_IMAGE tunnel --no-autoupdate $@
}

function _tunnel_detach() {
    docker run                         \
      --detach                         \
      --name $CLOUDFLARE_TUNNEL_DOCKER \
      --network host                   \
      --rm                             \
      --volume $FOLDER_HOST_CONFIG:$FOLDER_DOCKER_CONFIG \
      $CLOUDFLARE_DOCKER_IMAGE tunnel --no-autoupdate $@
}

function setup() {
    down &> /dev/null

    sudo rm -rf    $FOLDER_HOST_CONFIG && \
    sudo mkdir -p  $FOLDER_HOST_CONFIG && \
    sudo chmod 777 $FOLDER_HOST_CONFIG && \
    _tunnel login                      && \
    sudo chown --reference=$(find $FOLDER_HOST_CONFIG -type f | head -n 1) $FOLDER_HOST_CONFIG && \
    sudo chmod 700 $FOLDER_HOST_CONFIG
}

function get_tunnel_id() {
    _tunnel list --output json | jq -r ".[] | select(.name == \"$CLOUDFLARE_TUNNEL_NAME\") | .id"
}

function up() {
    docker stop $CLOUDFLARE_TUNNEL_DOCKER    &> /dev/null
    docker rm   $CLOUDFLARE_TUNNEL_DOCKER -f &> /dev/null

    local tunnel_id=$(get_tunnel_id)

    if [[ -z "$tunnel_id" ]]; then
        _tunnel create $CLOUDFLARE_TUNNEL_NAME || return $?
        tunnel_id=$(get_tunnel_id)
        local tunnel_config_yaml="$FOLDER_HOST_CONFIG/$tunnel_id.yaml"
        cat <<EOF | sudo tee "$tunnel_config_yaml" > /dev/null
tunnel: $tunnel_id
credentials-file: $FOLDER_DOCKER_CONFIG/$tunnel_id.json
ingress:
    - hostname: $CLOUDFLARE_TUNNEL_HOST
      service: $CLOUDFLARE_TUNNELED_SERVICE
    - service: http_status:404
EOF
        sudo chown --reference=$(sudo find $FOLDER_HOST_CONFIG -type f | head -n 1) $tunnel_config_yaml && \
        sudo chmod --reference=$(sudo find $FOLDER_HOST_CONFIG -type f | head -n 1) $tunnel_config_yaml
    fi

    _tunnel route dns --overwrite-dns $tunnel_id $CLOUDFLARE_TUNNEL_HOST
    _tunnel_detach --config "$FOLDER_DOCKER_CONFIG/$tunnel_id.yaml" run $tunnel_id
}

function down() {
    docker stop $CLOUDFLARE_TUNNEL_DOCKER    &> /dev/null
    docker rm   $CLOUDFLARE_TUNNEL_DOCKER -f &> /dev/null

    local tunnel_id=$(get_tunnel_id) && \
    [[ -z "$tunnel_id" ]]            && return

    _tunnel delete $tunnel_id                   && \
    sudo rm $FOLDER_HOST_CONFIG/$tunnel_id.yaml && \
    echo $tunnel_id is deleted
}

