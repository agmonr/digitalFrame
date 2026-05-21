#!/bin/bash
# install.sh: Install the Digital Frame as a systemd service

if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root (use sudo)"
   exit 1
fi

PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
SERVICE_NAME="frame.service"

echo "Setting up Digital Frame service in $PROJECT_DIR..."

# 0. Install system dependencies
echo "Installing system dependencies..."
apt-get update
apt-get install -y python3-venv python3-pip nginx logrotate libopenjp2-7 libtiff6 libcamera-apps-lite

# 1. Setup Virtual Environment
echo "Setting up Python virtual environment..."
if [ ! -d "$PROJECT_DIR/venv" ]; then
    python3 -m venv "$PROJECT_DIR/venv"
fi

source "$PROJECT_DIR/venv/bin/activate"
pip install --upgrade pip
pip install -r "$PROJECT_DIR/requirements.txt"

# 2. Configure Nginx
echo "Configuring Nginx..."
cp "$PROJECT_DIR/digitalframe.nginx" /etc/nginx/sites-available/digitalframe
ln -sf /etc/nginx/sites-available/digitalframe /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx

# 3. Setup Logging
echo "Setting up logging..."
mkdir -p "$PROJECT_DIR/logs"
chmod 777 "$PROJECT_DIR/logs"

# Create logrotate config
cat <<EOF > /etc/logrotate.d/digitalframe
$PROJECT_DIR/logs/*.log {
    daily
    rotate 7
    compress
    missingok
    copytruncate
}
EOF
chmod 644 /etc/logrotate.d/digitalframe

# 4. Make scripts executable
chmod +x "$PROJECT_DIR/run_frame.sh"

# 5. Create the systemd service file
echo "Creating systemd service..."
cat <<EOF > /etc/systemd/system/$SERVICE_NAME
[Unit]
Description=Digital Frame Display Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/run_frame.sh
Restart=always
# Ensure output to the first console
StandardOutput=tty
TTYPath=/dev/tty1

[Install]
WantedBy=multi-user.target
EOF

[[ -f config.ini ]] && cp config.ini.example config.ini 

# 6. Reload systemd, enable and start the service
#
systemctl daemon-reload
systemctl enable $SERVICE_NAME
systemctl restart $SERVICE_NAME

echo "------------------------------------------------"
echo "Installation complete!"
echo "Service '$SERVICE_NAME' is installed and running."
echo "Use 'systemctl status $SERVICE_NAME' to check status."
echo "Use 'journalctl -u $SERVICE_NAME -f' to see live logs."
echo "------------------------------------------------"
