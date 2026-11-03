# Hosting on a server in the office (e.g. the OptiPlex)

Runs the same Docker setup as the laptop on a PC that stays on, reachable only from the plant network at
`https://<server-ip>:8443`. No domain, cloud account or internet-facing ports. The certificate is the same
self-signed one the laptop uses, made for the server's IP. The print agent stays on the Windows PC next to the
printer and connects to the server.

Ports used: 8443 (HTTPS) and 8088 (redirects to HTTPS). They don't clash with the NOVO server stack
(80, 3001, 8080, 9443).

## 1. Before you start

- Ubuntu Server with Docker installed (the NOVO server setup script does this). **Don't run
  `bash scripts/server.sh setup`** here: it's for cloud VMs and replaces the `ufw` firewall.
- A fixed IP for the server: ask IT for a DHCP reservation. The certificate and every agent and bookmark use it.
- You can SSH in from the laptop: `ssh <user>@<server-ip>`.

## 2. Put the code on the server

Push your latest commits from the laptop first; the server gets what's on GitHub. On the server, give it
read-only access to the private repository with a deploy key:

```bash
ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519
cat ~/.ssh/id_ed25519.pub
```

Copy the printed line into GitHub → the repository → Settings → Deploy keys → Add deploy key (leave write
access off). Then:

```bash
git clone git@github.com:Shrutibrahma/novo-label-studio.git
cd novo-label-studio
bash scripts/server.sh lan
```

`lan` uses the server's IP (or give it: `bash scripts/server.sh lan 192.168.1.50`), builds everything (the
first build takes several minutes) and prints `https://<server-ip>:8443` when it's healthy. **Don't do the
first-run setup in the browser yet** if you're moving the laptop's data over (next step).

From now on `up`, `update` and `restore` remember LAN mode.

## 3. Move the laptop's data

On the laptop, take a fresh backup and copy it over (use the stamp it prints, e.g. `20261101-101500`):

```powershell
.\scripts\backup-now.ps1
scp .\backups\label-<stamp>.dump .\backups\assets-<stamp>.tar.gz <user>@<server-ip>:novo-label-studio/backups/
```

On the server:

```bash
bash scripts/server.sh restore
```

Type `RESTORE`. Sign in at `https://<server-ip>:8443` with your usual username and password.

Starting fresh instead? Skip this step and do the first-run setup in the browser.

## 4. Copy the certificate to the printer PC

The agent only talks to a server whose certificate it trusts. On the Windows PC with the printer:

```powershell
scp <user>@<server-ip>:novo-label-studio/deploy/certs/labelstudio.crt $HOME\labelstudio-server.crt
```

Browsers show a warning the first time; accept it once per PC. To stop the warning on a kiosk PC for good:
double-click the `.crt` → Install Certificate → Local Machine → Trusted Root Certification Authorities.

## 5. Connect the print agent

Get an agent token: Settings → Printers → **New agent token** (copy it; it shows once).
On the printer PC, in the repository folder:

```powershell
.\scripts\agent.ps1 -Mode usb -Token <paste token> -ApiBaseUrl https://<server-ip>:8443/api -CaBundle $HOME\labelstudio-server.crt
```

All three are saved, so later runs are just `.\scripts\agent.ps1 -Mode usb`. As a Windows service, pass the
same values to `agent\packaging\install-service.ps1` (`-ApiBaseUrl`, `-CaBundle`).

Stop the laptop's own copy afterwards (`.\scripts\down.ps1`) so nobody prints to the old one by mistake.

## 6. QR codes that open the part page (optional)

Settings → Label style → QR codes → turn on **QR codes open the part page** and set the address to
`https://<server-ip>:8443`. Phones on the plant Wi-Fi can then scan a label and see the part.

## A name instead of the IP, without the port number

Ask IT to add a record on the office DNS server pointing the name at the server, e.g.
`labels.novoprecision.com → 192.168.1.50`. Then, on the server:

```bash
echo "HTTPS_PORT=443" >> deploy/.env
bash scripts/server.sh lan 192.168.1.50 labels.novoprecision.com
```

The app is then at `https://labels.novoprecision.com` (port 443 needs no number in the address), and the IP
address keeps working. It makes a new certificate covering both: repeat step 4, run the agent once with
`-ApiBaseUrl https://labels.novoprecision.com/api`, and update the QR-code address in step 6.

## If the server's IP changes

```bash
bash scripts/server.sh lan <new-ip>
```

It makes a new certificate for the new IP. Repeat step 4 and run the agent once with the new `-ApiBaseUrl`.

## Everyday commands (on the server, in `~/novo-label-studio`)

| Command | Does |
| --- | --- |
| `bash scripts/server.sh update` | Pull the latest code from GitHub and restart |
| `bash scripts/server.sh status` | What's running |
| `bash scripts/server.sh logs api` | Follow a service's logs (`api`, `web`, `db`, `backup`) |
| `bash scripts/server.sh backup` | Take a backup now |
| `bash scripts/server.sh restore [stamp]` | Replace all data with a backup in `backups/` |
| `bash scripts/server.sh reset-password Novo` | Set a new password for a user |
| `bash scripts/server.sh down` | Stop everything (data is kept) |

Nightly backups land in `~/novo-label-studio/backups` on the server. To also copy each one off the machine
(a NAS or network share mounted on the server), set `BACKUP_COPY_TO=<that folder>` in `deploy/.env` and run
`bash scripts/server.sh up`.
