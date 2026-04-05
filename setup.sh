#!/bin/bash
# =============================================================
# Watson — One-time VM setup script
# Run this once after SSH-ing into your GCP VM:
#   bash setup.sh
# =============================================================
set -e

echo ""
echo "=== Watson VM Setup ==="
echo ""

# ── 1. System packages ─────────────────────────────────────────
echo "[1/6] Installing system packages..."
sudo apt-get update -y -q
sudo apt-get install -y -q python3 python3-pip python3-venv git

# ── 2. App directory ───────────────────────────────────────────
echo "[2/6] Creating app directory at /opt/watson..."
sudo mkdir -p /opt/watson
sudo chown "$USER":"$USER" /opt/watson

# Copy your project files into /opt/watson before running this script,
# or uncomment the git clone line below if you're using a repo:
git clone https://github.com/fivetran-vishnubhargav/watson-test.git /opt/watson

# ── 3. Python virtual environment ─────────────────────────────
echo "[3/6] Setting up Python virtual environment..."
cd /opt/watson
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q

# ── 4. Firewall — open port 8080 ──────────────────────────────
echo "[4/6] Opening port 8080 via GCP firewall..."
# Run this in GCP Cloud Shell or the console if gcloud isn't installed here:
# gcloud compute firewall-rules create watson-http \
#   --allow tcp:8080 \
#   --target-tags watson-server \
#   --description "Allow Watson API traffic"
echo "     (Remember to open port 8080 in your GCP VPC firewall rules)"

# ── 5. Systemd service ─────────────────────────────────────────
echo "[5/6] Installing systemd service..."
CURRENT_USER="$USER"
sudo tee /etc/systemd/system/watson.service > /dev/null <<EOF
[Unit]
Description=Watson Investigation Service
After=network.target

[Service]
Type=simple
User=${CURRENT_USER}
WorkingDirectory=/opt/watson

# 4 workers = handles 4 requests truly in parallel
# --timeout 120 = investigation can take up to 2 min before gunicorn kills it
ExecStart=/opt/watson/venv/bin/gunicorn main:app \\
    -k uvicorn.workers.UvicornWorker \\
    -w 4 \\
    -b 0.0.0.0:8080 \\
    --timeout 120 \\
    --access-logfile - \\
    --error-logfile -

Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# ── 6. Start the service ───────────────────────────────────────
echo "[6/6] Starting Watson..."
sudo systemctl daemon-reload
sudo systemctl enable watson
sudo systemctl start watson

echo ""
echo "=== Done! ==="
echo ""
echo "Check status : sudo systemctl status watson"
echo "View logs    : sudo journalctl -u watson -f"
echo "Test health  : curl http://localhost:8080/health"
echo ""
echo "Your VM's external IP can be found in:"
echo "  GCP Console → Compute Engine → VM instances"
echo ""
