#!/usr/bin/env bash
# Runs Novo Smart Labels on an internet-facing Linux server (Ubuntu, e.g. an Oracle Cloud Always Free VM),
# with a free Let's Encrypt certificate from Caddy. See deploy/ORACLE.md for the full walkthrough.
#   bash scripts/server.sh setup                    install Docker and open ports 80/443 in the VM firewall (once)
#   bash scripts/server.sh up [domain]              build + start everything, wait until healthy, print the URL
#   bash scripts/server.sh down                     stop everything (data is kept)
#   bash scripts/server.sh update                   git pull, then up
#   bash scripts/server.sh status | logs [service]  what's running / follow the logs
#   bash scripts/server.sh backup                   take a backup now (into backups/)
#   bash scripts/server.sh demo                     load the demo parts
#   bash scripts/server.sh reset-password <user>    set a new password for a user (asked twice, hidden)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY_DIR="$REPO_ROOT/deploy"
ENV_FILE="$DEPLOY_DIR/.env"

fail() { echo; echo "ERROR: $*" >&2; exit 1; }

docker_cmd() {
    # Right after setup the user isn't in the docker group until they log in again; use sudo meanwhile.
    if docker info >/dev/null 2>&1; then docker "$@"; else sudo docker "$@"; fi
}

compose() {
    docker_cmd compose --project-directory "$DEPLOY_DIR" \
        -f "$DEPLOY_DIR/docker-compose.yml" -f "$DEPLOY_DIR/docker-compose.server.yml" "$@"
}

env_value() { grep -E "^$1=" "$ENV_FILE" 2>/dev/null | tail -n1 | cut -d= -f2-; }

set_env_value() {
    if grep -qE "^$1=" "$ENV_FILE"; then
        sed -i "s|^$1=.*|$1=$2|" "$ENV_FILE"
    else
        echo "$1=$2" >> "$ENV_FILE"
    fi
}

cmd_setup() {
    command -v apt-get >/dev/null || fail "This setup is for Ubuntu. Install Docker yourself, then run: bash scripts/server.sh up"
    if ! command -v docker >/dev/null; then
        echo "Installing Docker..."
        curl -fsSL https://get.docker.com | sudo sh
    fi
    sudo usermod -aG docker "$USER"

    # Oracle's Ubuntu images ship iptables rules that reject everything except SSH, even when the cloud
    # firewall (security list) allows it. Let web traffic in and keep the rule across reboots.
    echo "Opening ports 80 and 443 in the VM firewall..."
    for port in 80 443; do
        sudo iptables -C INPUT -p tcp --dport "$port" -m conntrack --ctstate NEW -j ACCEPT 2>/dev/null \
            || sudo iptables -I INPUT -p tcp --dport "$port" -m conntrack --ctstate NEW -j ACCEPT
    done
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y iptables-persistent >/dev/null
    sudo netfilter-persistent save >/dev/null

    echo
    echo "Setup done. Next:  bash scripts/server.sh up"
}

init_env() {
    local domain="${1:-}"
    if [ ! -f "$ENV_FILE" ]; then
        cat > "$ENV_FILE" <<EOF
DB_PASSWORD=$(openssl rand -hex 24)
SESSION_TTL_HOURS=12
BACKUP_AT=02:00
EOF
        chmod 600 "$ENV_FILE"
        echo "Created deploy/.env with a random database password."
    fi
    [ -n "$domain" ] || domain="$(env_value SITE_DOMAIN)"
    if [ -z "$domain" ]; then
        local ip suggestion
        ip="$(curl -fsS --max-time 5 https://api.ipify.org || true)"
        [ -n "$ip" ] && suggestion="${ip//./-}.sslip.io"
        echo "Which web address should the app use? Its DNS must point at this server's public IP${ip:+ ($ip)}."
        [ -n "${suggestion:-}" ] && echo "No domain of your own? $suggestion works with no setup."
        read -r -p "Domain${suggestion:+ [$suggestion]}: " domain
        domain="${domain:-${suggestion:-}}"
    fi
    domain="${domain#https://}"; domain="${domain#http://}"; domain="${domain%%/*}"
    [ -n "$domain" ] || fail "A domain is needed for the HTTPS certificate."
    set_env_value SITE_DOMAIN "$domain"
    set_env_value PUBLIC_BASE_URL "https://$domain"
}

cmd_up() {
    command -v docker >/dev/null || fail "Docker isn't installed. Run: bash scripts/server.sh setup"
    init_env "${1:-}"
    local domain; domain="$(env_value SITE_DOMAIN)"

    echo "Building and starting Novo Smart Labels (db, api, web, backup, caddy)..."
    compose up -d --build --remove-orphans

    echo "Waiting for the app to come up at https://$domain (the first certificate can take a minute)..."
    local deadline=$((SECONDS + 300))
    until [ "$(curl -s -o /dev/null -w '%{http_code}' "https://$domain/api/v1/health" || true)" = "200" ]; do
        if [ $SECONDS -ge $deadline ]; then
            compose ps
            fail "https://$domain didn't answer in time. Check that the domain points at this server, that ports 80 and 443 are open in the Oracle security list, and the logs:  bash scripts/server.sh logs caddy"
        fi
        sleep 3
    done
    echo
    echo "Novo Smart Labels is running at https://$domain"
}

cmd_reset_password() {
    local user="${1:-}"
    [ -n "$user" ] || fail "Usage: bash scripts/server.sh reset-password <username>"
    local first second
    read -r -s -p "New password for $user: " first; echo
    read -r -s -p "Again: " second; echo
    [ "$first" = "$second" ] || fail "The passwords don't match."
    printf '%s\n' "$first" | compose exec -T api python -m app.reset_password "$user"
}

command="${1:-}"; shift || true
case "$command" in
    setup) cmd_setup ;;
    up) cmd_up "$@" ;;
    down) compose down ;;
    update) git -C "$REPO_ROOT" pull --ff-only && cmd_up ;;
    status) compose ps ;;
    logs) compose logs -f --tail 100 "$@" ;;
    backup) compose run --rm backup once ;;
    demo) compose exec -T api python -m app.demo ;;
    reset-password) cmd_reset_password "$@" ;;
    *) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
