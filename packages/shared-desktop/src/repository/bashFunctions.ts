/**
 * Bash Functions Module
 * Provides interactive bash functions for terminal sessions
 * Ported from desktop/src/cli/core/rediacc-term-config.json
 */

/**
 * Content for ~/.bashrc-rediacc file on remote machines
 * Provides helper functions for Docker container management
 */
export const BASHRC_REDIACC_CONTENT = `# Rediacc Terminal Functions - Auto-generated
# Source this file in your .bashrc for persistent functions:
#   echo 'source ~/.bashrc-rediacc 2>/dev/null' >> ~/.bashrc

# Enter a Docker container interactively
# Usage: enter_container <container_name_or_id>
enter_container() {
  local container="\${1:-}"
  if [ -z "$container" ]; then
    echo "Usage: enter_container <container_name_or_id>"
    echo ""
    echo "Available containers:"
    docker ps --format "table {{.Names}}\\t{{.Image}}\\t{{.Status}}"
    return 1
  fi
  # Try bash first, fall back to sh
  docker exec -it "$container" bash 2>/dev/null || docker exec -it "$container" sh
}
export -f enter_container 2>/dev/null || true

# Follow logs for a container
# Usage: logs <container_name> [lines]
logs() {
  local container="\${1:-}"
  local lines="\${2:-100}"
  if [ -z "$container" ]; then
    echo "Usage: logs <container_name> [lines]"
    echo "  lines: number of lines to show (default: 100)"
    return 1
  fi
  docker logs --tail "$lines" -f "$container"
}
export -f logs 2>/dev/null || true

# Show Docker and repository status
status() {
  echo "=== Docker Containers ==="
  docker ps --format "table {{.Names}}\\t{{.Image}}\\t{{.Status}}\\t{{.Ports}}"
  echo ""
  echo "=== Repository Info ==="
  echo "Team:       \${REDIACC_TEAM:-not set}"
  echo "Machine:    \${REDIACC_MACHINE:-not set}"
  echo "Repository: \${REDIACC_REPOSITORY:-not set}"
  echo "Datastore:  \${REDIACC_DATASTORE:-not set}"
  echo ""
  echo "=== Docker Info ==="
  echo "Socket:     \${DOCKER_SOCKET:-/var/run/docker.sock}"
  echo "Data:       \${DOCKER_DATA:-not set}"
}
export -f status 2>/dev/null || true

# Custom prompt function for rediacc sessions
rediacc_prompt() {
  local repository="\${REDIACC_REPOSITORY:-}"
  local machine="\${REDIACC_MACHINE:-}"
  if [ -n "$repository" ]; then
    echo "[$repository@$machine]"
  elif [ -n "$machine" ]; then
    echo "[$machine]"
  else
    echo ""
  fi
}
export -f rediacc_prompt 2>/dev/null || true

# Set custom prompt showing repo name instead of GUID path
if [ -n "\${REDIACC_REPOSITORY:-}" ]; then
  __rediacc_ps1_dir() {
    local cwd="$PWD"
    # Try REDIACC_WORKING_DIR (mount path) first, then DOCKER_DATA (named path)
    local work_dir="\${REDIACC_WORKING_DIR:-\${DOCKER_DATA:-}}"
    if [ -n "$work_dir" ] && [ "\${cwd#"$work_dir"}" != "$cwd" ]; then
      local rel="\${cwd#"$work_dir"}"
      printf '%s' "\${REDIACC_REPOSITORY}\${rel}"
    else
      printf '%s' "$cwd"
    fi
  }
  PS1='\\u@\\h:$(__rediacc_ps1_dir)\\$ '
fi

# Quick container restart
restart_container() {
  local container="\${1:-}"
  if [ -z "$container" ]; then
    echo "Usage: restart_container <container_name_or_id>"
    return 1
  fi
  echo "Restarting $container..."
  docker restart "$container"
}
export -f restart_container 2>/dev/null || true

# Show container resource usage
container_stats() {
  local container="\${1:-}"
  if [ -z "$container" ]; then
    docker stats --no-stream
  else
    docker stats --no-stream "$container"
  fi
}
export -f container_stats 2>/dev/null || true

# Block 'docker compose' — must use 'renet compose' for network isolation
docker() {
  case "$1" in
    compose)
      echo "Error: Use 'renet compose' instead of 'docker compose'"
      echo "  Example: renet compose -- up -d"
      echo "  Why: renet compose injects network isolation, service IPs, and CRIU capabilities"
      return 1
      ;;
  esac
  command docker "$@"
}
export -f docker 2>/dev/null || true

# Block legacy 'docker-compose' command
docker-compose() {
  echo "Error: Use 'renet compose' instead of 'docker-compose'"
  echo "  Example: renet compose -- up -d"
  return 1
}
export -f docker-compose 2>/dev/null || true
`;

/**
 * Generates the SSH command to set up bash functions on remote
 *
 * @returns Shell command that creates ~/.bashrc-rediacc
 */
export function generateSetupCommand(): string {
  // Using heredoc with 'REDIACC_EOF' prevents variable expansion, so no escaping needed
  return `mkdir -p ~/.config/rediacc && cat > ~/.bashrc-rediacc << 'REDIACC_EOF'
${BASHRC_REDIACC_CONTENT}
REDIACC_EOF
chmod 644 ~/.bashrc-rediacc`;
}

/**
 * Generates the command to source bash functions
 *
 * @returns Shell command to source the bashrc file
 */
export function generateSourceCommand(): string {
  return 'source ~/.bashrc-rediacc 2>/dev/null || true';
}

/**
 * Generates a command that sources functions before running user command
 *
 * @param userCommand - User's command to run
 * @returns Command with sourcing prepended
 */
export function wrapWithBashFunctions(userCommand: string): string {
  return `${generateSourceCommand()} && ${userCommand}`;
}

/**
 * Checks if bash functions are installed on remote
 * Returns a command that outputs 'yes' if installed, 'no' otherwise
 */
export function generateCheckCommand(): string {
  return '[ -f ~/.bashrc-rediacc ] && echo "yes" || echo "no"';
}
