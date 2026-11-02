# Hosting on Hetzner Cloud (about $5 a month)

Runs the same Docker setup as the laptop on a small Hetzner server, with a real HTTPS certificate from
Let's Encrypt (Caddy gets and renews it). The print agent stays on the Windows PC next to the printer and
connects to the server. Your parts, designs and pictures move over from the laptop in step 6.

## 1. Make an SSH key on the laptop (once)

In PowerShell:

```powershell
ssh-keygen -t ed25519
Get-Content $HOME\.ssh\id_ed25519.pub
```

Press Enter at each question. Copy the line it prints (starts with `ssh-ed25519`).

## 2. Create the server

1. Sign up at https://www.hetzner.com/cloud and create a project.
2. **Add Server**:

| Setting | Choose |
| --- | --- |
| Location | The one closest to the shop (Ashburn or Hillsboro in the US) |
| Image | **Ubuntu 24.04** |
| Type | Shared vCPU, x86: **CX22** (2 vCPU, 4 GB) or the cheapest plan with 4 GB |
| Networking | Public IPv4 **on** |
| SSH keys | **Add SSH key**, paste the line from step 1 |
| Backups | Optional, about 20% extra: daily snapshots of the whole server |

3. When it's running, note the **IPv4 address**, e.g. `203.0.113.10`.

Hetzner has no firewall by default, so ports 80 and 443 are already open. If you add a Hetzner firewall later,
allow TCP 22, 80 and 443.

## 3. The web address

No domain needed: `<ip-with-dashes>.sslip.io` always points at that IP, e.g. `203-0-113-10.sslip.io`.
The setup suggests it. (Your own name such as `labels.novoprecision.com` also works: add a DNS A record
pointing at the IP.)

## 4. Put the code on the server

Push your latest commits from the laptop first; the server gets what's on GitHub.

```powershell
ssh root@<ip>
```

On the server, give it read-only access to the private repository with a deploy key:

```bash
ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519
cat ~/.ssh/id_ed25519.pub
```

Copy the printed line into GitHub → the repository → Settings → Deploy keys → Add deploy key (leave write
access off). Then:

```bash
git clone git@github.com:Shrutibrahma/novo-label-studio.git
cd novo-label-studio
bash scripts/server.sh setup
bash scripts/server.sh up
```

`up` asks for the web address (press Enter for the sslip.io one), builds everything (the first build takes
several minutes) and prints `https://<your address>` when it's healthy. **Don't do the first-run setup in the
browser yet** if you're moving the laptop's data over (next step).

## 5. Only answer the shop (recommended)

Find the shop's public IP (search "what is my IP" from a PC there). On the server:

```bash
echo "ALLOWED_CIDRS=198.51.100.7/32" >> deploy/.env
bash scripts/server.sh up
```

Several ranges: comma-separated. Every other address gets 403. Phones on mobile data won't get in; on the
shop Wi-Fi they will.

## 6. Move the laptop's data

On the laptop, take a fresh backup and copy it up (use the stamp it prints, e.g. `20261101-101500`):

```powershell
.\scripts\backup-now.ps1
scp .\backups\label-<stamp>.dump .\backups\assets-<stamp>.tar.gz root@<ip>:novo-label-studio/backups/
```

On the server:

```bash
bash scripts/server.sh restore
```

Type `RESTORE`. Sign in at `https://<your address>` with your usual username and password.

Starting fresh instead? Skip this step and do the first-run setup in the browser (use a strong password;
the sign-in page is on the internet).

## 7. Connect the print agent

Get an agent token: Settings → Printers → **New agent token** (copy it; it shows once).
On the Windows PC with the printer, in the repository folder:

```powershell
.\scripts\agent.ps1 -Mode usb -Token <paste token> -ApiBaseUrl https://<your address>/api
```

Stop the laptop's own copy afterwards (`.\scripts\down.ps1`) so nobody prints to the old one by mistake.

## 8. QR codes that open the part page (optional)

Settings → Label style → QR codes → turn on **QR codes open the part page** and set the address to
`https://<your address>`. Any phone allowed in step 5 can then scan a label and see the part.

## Everyday commands (on the server, in `~/novo-label-studio`)

| Command | Does |
| --- | --- |
| `bash scripts/server.sh update` | Pull the latest code from GitHub and restart |
| `bash scripts/server.sh status` | What's running |
| `bash scripts/server.sh logs api` | Follow a service's logs (`api`, `web`, `db`, `caddy`, `backup`) |
| `bash scripts/server.sh backup` | Take a backup now |
| `bash scripts/server.sh restore [stamp]` | Replace all data with a backup in `backups/` |
| `bash scripts/server.sh reset-password Novo` | Set a new password for a user |
| `bash scripts/server.sh down` | Stop everything (data is kept) |

Nightly backups land in `~/novo-label-studio/backups` on the server. Copy them off now and then:

```powershell
scp -r root@<ip>:novo-label-studio/backups .\server-backups
```
