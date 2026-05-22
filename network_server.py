from flask import Flask, jsonify, request, render_template
import subprocess
import json
import os

app = Flask(__name__, template_folder='templates')

@app.route('/network')
def network_page():
    return render_template('network.html')

@app.route('/api/network/status', methods=['GET'])
def get_status():
    try:
        # Get current SSID
        result = subprocess.run(['nmcli', '-t', '-f', 'ACTIVE,SSID', 'dev', 'wifi'], capture_output=True, text=True)
        # Filter for active connections that are NOT the setup AP
        active = []
        for line in result.stdout.split('\n'):
            if line.startswith('yes:'):
                ssid = line.split(':')[1]
                if ssid not in ['dframe', 'DigitalFrame_Setup']:
                    active.append(ssid)
        
        ssid = active[0] if active else "Not connected"
        return jsonify({"ssid": ssid})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/network/scan', methods=['GET'])
def scan_networks():
    try:
        # Run nmcli scan
        result = subprocess.run(['nmcli', '-t', '-f', 'SSID,SIGNAL,SECURITY', 'dev', 'wifi', 'list'], capture_output=True, text=True, check=True)
        networks = []
        for line in result.stdout.strip().split('\n'):
            parts = line.split(':')
            if len(parts) >= 3:
                ssid = parts[0]
                if ssid: # Filter out empty SSIDs
                    networks.append({"ssid": ssid, "signal": parts[1], "security": parts[2]})
        # Remove duplicates
        unique_networks = {n['ssid']: n for n in networks}.values()
        return jsonify({"status": "success", "networks": list(unique_networks)})
    except subprocess.CalledProcessError as e:
        return jsonify({"error": f"Failed to scan: {e.stderr}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/network/wifi', methods=['POST'])
def configure_wifi():
    data = request.json
    ssid = data.get('ssid')
    password = data.get('password')
    
    if not ssid:
        return jsonify({"error": "Missing SSID"}), 400

    try:
        # Kill dnsmasq if it was running for ad-hoc/AP setup
        subprocess.run(['sudo', 'pkill', '-f', 'dnsmasq.*dframe'], capture_output=True)
        subprocess.run(['sudo', 'pkill', '-f', 'dnsmasq.*DigitalFrame_Setup'], capture_output=True)
        # Delete setup connections if they exist
        subprocess.run(['sudo', 'nmcli', 'con', 'delete', 'dframe'], capture_output=True)
        subprocess.run(['sudo', 'nmcli', 'con', 'delete', 'DigitalFrame_Setup'], capture_output=True)
        
        subprocess.run(['sudo', 'nmcli', 'dev', 'wifi', 'connect', ssid, 'password', password], check=True)
        return jsonify({"status": "success", "message": f"Connected to {ssid}"})
    except subprocess.CalledProcessError as e:
        return jsonify({"error": f"Failed to connect: {e.stderr}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5003)
