# Oracle Cloud "Always Free" VPS Setup

Deploys the read-only FastAPI app (`api.py`) to a free-forever Oracle Cloud VM.
Scraping (`scraper.py`, `franchise_discovery.py`, `franchise_enrichment.py`) still
runs locally — this VPS only serves the synced `apparel_aggregator.db`.

## 1. Create the instance
- Sign up for Oracle Cloud (requires a credit card for verification, not charged
  unless you explicitly switch to Pay-As-You-Go).
- **Compute → Instances → Create Instance**
- Image: **Ubuntu 22.04 or 24.04**
- Shape: **VM.Standard.A1.Flex** (Arm, Always Free — 1-2 OCPU / 6-12 GB RAM is
  plenty) or the free `VM.Standard.E2.1.Micro` (AMD) if A1 capacity isn't
  available in your region.
  - Gotcha: the free A1 shape is popular and can show "Out of capacity" —
    retry, try a different Availability Domain, or fall back to the AMD micro
    shape.
- Add your SSH public key during creation.
- Leave boot volume at default (Always Free includes up to 200GB block storage).

## 2. Open network access (Oracle's VCN firewall)
- **Networking → Virtual Cloud Networks → (your VCN) → Security Lists →
  Default Security List**
- Add ingress rules for **TCP 80** and **TCP 443** (source `0.0.0.0/0`).
  SSH (22) is usually already open by default.

## 3. Initial server setup
SSH in first:
```bash
ssh ubuntu@<your-instance-public-ip>

sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-venv python3-pip nginx ufw

# OS-level firewall (Ubuntu ships with ufw)
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

## 4. Deploy the app
No need for Playwright or scraper dependencies here — this instance only
serves reads. A trimmed dependency set is enough.

```bash
sudo mkdir -p /opt/aggregate_apparel
sudo chown ubuntu:ubuntu /opt/aggregate_apparel
cd /opt/aggregate_apparel

# Copy api.py, models.py, database.py, templates/, static/ here
# (e.g. via git clone, or scp from your local machine)

python3 -m venv venv
source venv/bin/activate
pip install fastapi uvicorn jinja2 apscheduler
```

Set the cloud-only environment variable so the scheduler never runs there:
```bash
echo 'ENABLE_SCRAPER_SCHEDULER=false' | sudo tee /etc/aggregate_apparel.env
```

## 5. Run it as a systemd service (auto-restart, starts on boot)
Create `/etc/systemd/system/aggregate-apparel.service`:
```ini
[Unit]
Description=Aggregate Apparel FastAPI app
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/opt/aggregate_apparel
EnvironmentFile=/etc/aggregate_apparel.env
ExecStart=/opt/aggregate_apparel/venv/bin/uvicorn api:app --host 127.0.0.1 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now aggregate-apparel
sudo systemctl status aggregate-apparel   # verify it's running
```

## 6. Nginx reverse proxy + HTTPS
Create `/etc/nginx/sites-available/aggregate_apparel`:
```nginx
server {
    listen 80;
    server_name gamingapparel.gg www.gamingapparel.gg;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/aggregate_apparel /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# Free TLS cert (point your domain's DNS A record at the instance's public IP first)
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d gamingapparel.gg -d www.gamingapparel.gg
```

## 7. Sync the database from your local machine
Add your local machine's SSH public key to the VPS's `~/.ssh/authorized_keys`
(or reuse the same keypair from step 1). After each local `python scraper.py`
run, push the updated DB:

```bash
rsync -avz --progress apparel_aggregator.db ubuntu@<instance-ip>:/opt/aggregate_apparel/apparel_aggregator.db
```

Uvicorn opens a new SQLite connection per request rather than holding one
persistent connection, so an `rsync` overwrite while the service is running is
safe for this read-mostly workload — no restart needed. If you ever see odd
read errors right after a sync, run `sudo systemctl restart aggregate-apparel`
as a safety net.

## Summary checklist for each deploy/update
1. Point domain DNS A record at the instance's public IP (one-time).
2. `rsync` the local `apparel_aggregator.db` up to the VPS after each local
   scraper run.
3. `ENABLE_SCRAPER_SCHEDULER=false` stays set on the VPS permanently — the
   heavy scrape/discovery job only ever runs locally.