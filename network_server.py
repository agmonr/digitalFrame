from flask import Flask, jsonify, request, render_template
import subprocess
import json
import os
import configparser
import time

app = Flask(__name__, template_folder='templates')

def get_config_network():
    config = configparser.ConfigParser()
    ap_name = "dframe"
    ap_password = "DigitalFrame"
    try:
        config.read('config.ini')
        if 'NETWORK' in config:
            if 'ap_name' in config['NETWORK']:
                ap_name = config['NETWORK']['ap_name']
            if 'ap_password' in config['NETWORK']:
                ap_password = config['NETWORK']['ap_password']
    except Exception as e:
        pass
    return ap_name, ap_password

@app.route('/network')
def network_page():
    return render_template('network.html')

@app.route('/api/network/status', methods=['GET'])
def get_status():
    try:
        ap_name, _ = get_config_network()
        # Check active connections directly
        con_res = subprocess.run(['nmcli', '-t', '-f', 'TYPE,NAME', 'con', 'show', '--active'], capture_output=True, text=True)
        
        is_ap_active = False
        actual_ssid = None
        
        for line in con_res.stdout.strip().split('\n'):
            parts = line.split(':')
            if len(parts) >= 2:
                con_type = parts[0].strip()
                con_name = parts[1].strip()
                
                if con_type in ['802-11-wireless', 'wifi']:
                    if con_name in [ap_name, 'DigitalFrame_Setup']:
                        is_ap_active = True
                    else:
                        actual_ssid = con_name
                        break
        
        if actual_ssid:
            return jsonify({"ssid": actual_ssid})
        if is_ap_active:
            return jsonify({"ssid": "Access Point"})
            
        return jsonify({"ssid": "Not connected"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/network/scan', methods=['GET'])
def scan_networks():
    try:
        ap_name, _ = get_config_network()
        # Run nmcli scan
        result = subprocess.run(['nmcli', '-t', '-f', 'SSID,SIGNAL,SECURITY', 'dev', 'wifi', 'list'], capture_output=True, text=True, check=True)
        networks = []
        for line in result.stdout.strip().split('\n'):
            parts = line.split(':')
            if len(parts) >= 3:
                ssid = parts[0]
                # Filter out empty SSIDs and the setup AP name
                if ssid and ssid not in [ap_name, 'DigitalFrame_Setup']:
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

    log_file = "logs/network_debug.log"
    def log(msg):
        with open(log_file, "a") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {msg}\n")
        print(msg)

    log(f"--- Starting connection attempt to SSID: {ssid} ---")

    try:
        ap_name, _ = get_config_network()
        
        # 1. Kill DHCP and other setup processes
        log("Stopping DHCP server...")
        subprocess.run(['sudo', 'pkill', '-9', '-f', 'dnsmasq'], capture_output=True)
        
        # 2. Delete setup connections
        log(f"Deleting setup connections ({ap_name}, DigitalFrame_Setup)...")
        subprocess.run(['sudo', 'nmcli', 'con', 'delete', ap_name], capture_output=True)
        subprocess.run(['sudo', 'nmcli', 'con', 'delete', 'DigitalFrame_Setup'], capture_output=True)
        
        # 3. Clear ANY existing connection with this SSID to prevent secret conflicts
        log(f"Clearing existing profiles for {ssid}...")
        subprocess.run(['sudo', 'nmcli', 'con', 'delete', 'id', ssid], capture_output=True)
        
        # 4. Wait for hardware to transition
        log("Waiting 3 seconds for hardware to settle...")
        time.sleep(3)

        # 5. Attempt connection using a more explicit method
        log(f"Attempting to connect to {ssid}...")
        # We use 'nmcli dev wifi connect' as it handles profile creation and activation in one go
        # but we capture both stdout and stderr for the log
        result = subprocess.run(['sudo', 'nmcli', 'dev', 'wifi', 'connect', ssid, 'password', password], 
                                capture_output=True, text=True)
        
        log(f"nmcli exit code: {result.returncode}")
        log(f"nmcli stdout: {result.stdout.strip()}")
        log(f"nmcli stderr: {result.stderr.strip()}")

        if result.returncode != 0:
            # Check if secrets were the problem and try an alternative if needed
            if "Secrets were required" in result.stderr or "secrets are required" in result.stderr:
                log("Secrets error detected. Attempting alternative profile-first connection...")
                # Delete and try manual add
                subprocess.run(['sudo', 'nmcli', 'con', 'delete', 'id', ssid], capture_output=True)
                add_res = subprocess.run([
                    'sudo', 'nmcli', 'con', 'add', 'type', 'wifi', 'con-name', ssid, 'ifname', '*', 'ssid', ssid
                ], capture_output=True, text=True)
                log(f"Profile add result: {add_res.stdout.strip()}")
                
                subprocess.run(['sudo', 'nmcli', 'con', 'modify', ssid, 
                               'wifi-security.key-mgmt', 'wpa-psk', 
                               'wifi-security.psk', password], capture_output=True)
                
                log("Activating manually created profile...")
                up_res = subprocess.run(['sudo', 'nmcli', 'con', 'up', ssid], capture_output=True, text=True)
                log(f"Manual up exit code: {up_res.returncode}")
                log(f"Manual up stdout: {up_res.stdout.strip()}")
                log(f"Manual up stderr: {up_res.stderr.strip()}")
                
                if up_res.returncode == 0:
                    log("Manual connection successful.")
                    return jsonify({"status": "success", "message": f"Connected to {ssid}"})
            
            return jsonify({"error": f"Failed to connect: {result.stderr or result.stdout}"}), 500

        log("Connection successful.")
        return jsonify({"status": "success", "message": f"Connected to {ssid}"})
    except Exception as e:
        log(f"CRITICAL ERROR: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5003)
