#!/usr/bin/env bash
set -euo pipefail
APP=/opt/igtracker

sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip git

sudo mkdir -p $APP && sudo chown $USER:$USER $APP
# ここでローカルから転送: scp -r ./igtracker/* ubuntu@<EIP>:$APP/

cd $APP
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

mkdir -p data data/media

sudo tee /etc/systemd/system/igtracker.service >/dev/null <<EOF
[Unit]
Description=IG Uraaka Tracker
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=$APP
Environment=PYTHONUNBUFFERED=1
ExecStart=$APP/venv/bin/python run.py
Restart=always
RestartSec=10
User=$USER

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now igtracker
echo "起動完了: http://$(curl -s ifconfig.me):8000"