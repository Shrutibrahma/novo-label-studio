#!/usr/bin/env bash
# Runs Novo Smart Labels on an internet-facing Linux server (Ubuntu: Hetzner Cloud, Oracle Cloud Always Free, ...),
# with a free Let's Encrypt certificate from Caddy. See deploy/HETZNER.md or deploy/ORACLE.md for the full walkthrough.
#   bash scripts/server.sh setup                    install Docker and open ports 80/443 in the VM firewall (once)
#   bash scripts/server.sh up [domain]              build + start everything, wait until healthy, print the URL
#   bash scripts/server.sh lan [ip] [name]          office-network server instead (deploy/LAN.md): https://<ip>:8443
#   bash scripts/server.sh down                     stop everything (data is kept)
#   bash scripts/server.sh update                   git pull, then up
#   bash scripts/server.sh status | logs [service]  what's running / follow the logs
#   bash scripts/server.sh backup                   take a backup now (into backups/)
#   bash scripts/server.sh demo                     load the demo parts
#   bash scripts/server.sh reset-password <user>    set a new password for a user (asked twice, hidden)
#   bash scripts/server.sh restore [stamp]          replace all data with a backup in backups/ (newest by default)
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
    # LAN mode has no Caddy: the web container's own HTTPS port faces the office network.
    local files=(-f "$DEPLOY_DIR/docker-compose.yml")
    [ "$(env_value MODE)" = "lan" ] || files+=(-f "$DEPLOY_DIR/docker-compose.server.yml")
    docker_cmd compose --project-directory "$DEPLOY_DIR" "${files[@]}" "$@"
}

# Empty (not an error) when the setting or the file is missing: set -e would otherwise stop the script.
env_value() { grep -E "^$1=" "$ENV_FILE" 2>/dev/null | tail -n1 | cut -d= -f2- || true; }

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

create_env_file() {
    if [ ! -f "$ENV_FILE" ]; then
        cat > "$ENV_FILE" <<EOF
DB_PASSWORD=$(openssl rand -hex 24)
SESSION_TTL_HOURS=12
BACKUP_AT=02:00
EOF
        chmod 600 "$ENV_FILE"
        echo "Created deploy/.env with a random database password."
    fi
}

init_env() {
    local domain="${1:-}"
    create_env_file
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
            fail "https://$domain didn't answer in time. Check that the domain points at this server, that ports 80 and 443 are open in the cloud firewall (Hetzner firewall / Oracle security list), and the logs:  bash scripts/server.sh logs caddy"
        fi
        sleep 3
    done
    echo
    echo "Novo Smart Labels is running at https://$domain"
}

cmd_lan() {
    # A server on the office network (e.g. a spare PC): no domain or internet access needed. The web container
    # serves HTTPS itself with the self-signed certificate it makes on first start for this machine's IP.
    command -v docker >/dev/null || fail "Docker isn't installed. Run: bash scripts/server.sh setup"
    create_env_file
    local ip="${1:-$(env_value LAN_IP)}"
    [ -n "$ip" ] || ip="$(hostname -I | awk '{print $1}')"
    [ -n "$ip" ] || fail "Couldn't find this machine's IP address. Run: bash scripts/server.sh lan <ip>"
    # Optional name from the office DNS (e.g. labels.example.com): the certificate covers it and links use it.
    local name="${2:-$(env_value LAN_NAME)}"
    local port; port="$(env_value HTTPS_PORT)"; port="${port:-8443}"
    local host="${name:-$ip}" suffix=":$port" san="IP:$ip"
    [ "$port" != "443" ] || suffix=""
    if [ -n "$name" ]; then san="$san,DNS:$name"; fi
    set_env_value MODE lan
    set_env_value LAN_IP "$ip"
    set_env_value LAN_NAME "$name"
    set_env_value EXTRA_SAN "$san"
    set_env_value PUBLIC_BASE_URL "https://$host$suffix"
    set_env_value BACKUP_TZ "$(timedatectl show -p Timezone --value 2>/dev/null || echo UTC)"

    # The certificate only covers the addresses it was made for: after an IP or name change, make a new one.
    local cert="$DEPLOY_DIR/certs/labelstudio.crt"
    if [ -f "$cert" ] && ! cert_covers "$cert" "$ip" "$name"; then
        echo "The certificate doesn't cover $host; making a new one (copy it to the print agent PC again)."
        sudo rm -f "$cert" "$DEPLOY_DIR/certs/labelstudio.key"
    fi

    echo "Building and starting Novo Smart Labels (db, api, web, backup) for the office network..."
    compose up -d --build --remove-orphans

    echo "Waiting for the app to come up at https://$host$suffix..."
    local deadline=$((SECONDS + 300))
    until [ "$(curl -sk -o /dev/null -w '%{http_code}' "https://127.0.0.1:$port/api/v1/health" || true)" = "200" ]; do
        if [ $SECONDS -ge $deadline ]; then
            compose ps
            fail "The app didn't come up in time. Check the logs:  bash scripts/server.sh logs api"
        fi
        sleep 3
    done
    echo
    echo "Novo Smart Labels is running at https://$host$suffix"
    if [ -n "$name" ]; then echo "(also https://$ip$suffix, until the office DNS knows $name)"; fi
    echo "The certificate is self-signed: each browser asks to accept it once. The print agent PC needs a copy of"
    echo "  $cert"
}

# True when the certificate lists the IP and, if given, the name.
cert_covers() {
    local text; text="$(openssl x509 -in "$1" -noout -text)"
    grep -qE "IP Address:${2//./\\.}(,|$)" <<<"$text" || return 1
    [ -z "$3" ] || grep -qE "DNS:${3//./\\.}(,|$)" <<<"$text"
}

# Starts the app the way it was set up: LAN mode once 'lan' has been run, the internet server otherwise.
start_app() {
    if [ "$(env_value MODE)" = "lan" ]; then cmd_lan "$@"; else cmd_up "$@"; fi
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

cmd_restore() {
    # Same steps as scripts/restore.ps1: used to move the laptop's data here (copy label-*.dump and
    # assets-*.tar.gz into backups/ first) or to roll back.
    local backups="$REPO_ROOT/backups" stamp="${1:-}"
    if [ -z "$stamp" ]; then
        local latest; latest="$(ls "$backups"/label-*.dump 2>/dev/null | sort | tail -n1 || true)"
        [ -n "$latest" ] || fail "No backups found in $backups."
        stamp="$(basename "$latest" .dump)"; stamp="${stamp#label-}"
    fi
    [ -f "$backups/label-$stamp.dump" ] || fail "Missing $backups/label-$stamp.dump"
    [ -f "$backups/assets-$stamp.tar.gz" ] || fail "Missing $backups/assets-$stamp.tar.gz"
    echo "This replaces ALL current data with the backup from $stamp."
    local answer; read -r -p "Type RESTORE to continue: " answer
    [ "$answer" = "RESTORE" ] || { echo "Cancelled. Nothing was changed."; exit 0; }

    echo "Stopping the API and web..."
    compose stop api web caddy
    compose up -d db
    echo "Restoring the database from label-$stamp.dump..."
    compose run --rm --no-deps -e "STAMP=$stamp" --entrypoint sh backup -c         'PGPASSWORD="$DB_PASSWORD" pg_restore -h db -U label -d label --clean --if-exists --no-owner --exit-on-error "/backups/label-$STAMP.dump"'
    echo "Restoring part images from assets-$stamp.tar.gz..."
    compose run --rm --no-deps -e "STAMP=$stamp" --user root --entrypoint sh backup -c         'find /data/assets -mindepth 1 -delete; tar -xzf "/backups/assets-$STAMP.tar.gz" -C /data && chown -R 10001 /data/assets'
    echo "Starting the app..."
    start_app
}

command="${1:-}"; shift || true
case "$command" in
    setup) cmd_setup ;;
    up) start_app "$@" ;;
    lan) cmd_lan "$@" ;;
    down) compose down ;;
    update) git -C "$REPO_ROOT" pull --ff-only && start_app ;;
    status) compose ps ;;
    logs) compose logs -f --tail 100 "$@" ;;
    backup) compose run --rm backup once ;;
    demo) compose exec -T api python -m app.demo ;;
    reset-password) cmd_reset_password "$@" ;;
    restore) cmd_restore "$@" ;;
    *) sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
