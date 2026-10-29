# Hosting on Oracle Cloud (Always Free)

Runs the same Docker setup as the laptop on a free Oracle VM, with a real HTTPS certificate from Let's Encrypt
(Caddy gets and renews it). The print agent stays on the Windows PC next to the printer and connects to the server.

What's added for this: `deploy/docker-compose.server.yml`, `deploy/Caddyfile`, `scripts/server.sh`.

## 1. Create the Oracle account

1. Sign up at https://signup.cloud.oracle.com (a card is needed for identity checks; Always Free resources aren't charged).
2. The **home region** can't be changed later — pick the one closest to the shop.
3. Recommended: once signed in, upgrade to **Pay As You Go** (Billing → Upgrade). Always Free resources stay free,
   and Oracle no longer reclaims the VM for being idle, which it may do on free-only accounts.

## 2. Create the VM

Menu → Compute → Instances → **Create instance**:

| Setting | Choose |
| --- | --- |
| Image | Canonical **Ubuntu 24.04** |
| Shape | Ampere → **VM.Standard.A1.Flex**, 2 OCPU, 12 GB memory (free up to 4 OCPU / 24 GB) |
| Networking | Create new virtual cloud network + public subnet, **Assign a public IPv4 address** |
| SSH keys | **Generate a key pair** → download the private key (keep it safe) |

"Out of capacity" for A1 is common: try another availability domain, or try again later.
When it's running, note the **Public IP address**.

## 3. Open ports 80 and 443

Instance page → the subnet link → **Default Security List** → **Add Ingress Rules**:
source CIDR `0.0.0.0/0`, IP protocol TCP, destination port range `80,443`.
(`server.sh setup` opens the same ports inside the VM's own firewall.)

## 4. Pick the web address

- Your own name, e.g. `labels.novoprecision.com`: add a DNS **A record** pointing at the public IP (ask whoever runs the domain).
- No domain: use `<ip-with-dashes>.sslip.io`, e.g. `129-146-10-20.sslip.io` for IP 129.146.10.20 — works with no setup.

## 5. Put the code on the server

Commit and push your latest changes from the laptop first — the server gets what's on GitHub.

From PowerShell on the laptop (the key file must be readable only by you, or ssh refuses it):

```powershell
icacls C:\path\to\ssh-key.key /inheritance:r /grant:r "$($env:USERNAME):R"
ssh -i C:\path\to\ssh-key.key ubuntu@<public-ip>
```

On the server, give it read-only access to the private repository with a deploy key:

```bash
ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519
cat ~/.ssh/id_ed25519.pub
```

Copy the printed line into GitHub → the repository → Settings → Deploy keys → Add deploy key (leave write access off). Then:

```bash
git clone git@github.com:Shrutibrahma/novo-label-studio.git
cd novo-label-studio
```

## 6. Start it

```bash
bash scripts/server.sh setup
exit
```

Log back in (so Docker works without sudo), then:

```bash
cd novo-label-studio
bash scripts/server.sh up
```

It asks for the web address (and suggests the sslip.io one), builds everything — the first build takes several
minutes — and prints `https://<your address>` when it's healthy.

Open that address → first-run setup: create the admin (use a strong password; the sign-in page is on the internet),
company and serial settings. Step 3 shows the **agent token once** — copy it.

## 7. Connect the print agent

On the Windows PC with the printer, in the repository folder:

```powershell
.\scripts\agent.ps1 -Mode usb -Token <paste token> -ApiBaseUrl https://<your address>/api
```

Both the token and the address are saved in `agent/.env`, so later just `.\scripts\agent.ps1 -Mode usb`.
Leave out `-Mode usb` to try it with the simulated printer first.

## Everyday commands (on the server, in `~/novo-label-studio`)

| Command | Does |
| --- | --- |
| `bash scripts/server.sh update` | Pull the latest code from GitHub and restart |
| `bash scripts/server.sh status` | What's running |
| `bash scripts/server.sh logs api` | Follow a service's logs (`api`, `web`, `db`, `caddy`, `backup`) |
| `bash scripts/server.sh backup` | Take a backup now |
| `bash scripts/server.sh reset-password Novo` | Set a new password for a user |
| `bash scripts/server.sh down` | Stop everything (data is kept) |

Nightly backups land in `~/novo-label-studio/backups` **on the same VM**. Copy them off now and then, e.g. from the laptop:

```powershell
scp -i C:\path\to\ssh-key.key -r ubuntu@<public-ip>:novo-label-studio/backups .\server-backups
```

The data on the laptop isn't moved over; the server starts empty.
