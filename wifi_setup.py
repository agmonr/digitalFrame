import subprocess
import os
import time
import sys
import configparser

def run_command(cmd, check=False):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=check)
        return result
    except subprocess.CalledProcessError as e:
        print(f"Command failed: {' '.join(cmd)}\nError: {e.stderr}")
        return e

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
        print(f"Error reading config.ini: {e}")
    return ap_name, ap_password

def get_wifi_interface():
    res = run_command(['nmcli', '-t', '-f', 'DEVICE,TYPE', 'dev'])
    if isinstance(res, Exception): return None
    for line in res.stdout.strip().split('\n'):
        parts = line.split(':')
        if len(parts) == 2 and parts[1] == 'wifi':
            return parts[0]
    return None

def is_wifi_connected(ap_name):
    res = run_command(['nmcli', '-t', '-f', 'DEVICE,ACTIVE,SSID', 'dev', 'wifi'])
    if isinstance(res, Exception): return False
    for line in res.stdout.strip().split('\n'):
        parts = line.split(':')
        if len(parts) >= 3 and parts[1].lower() == 'yes':
            ssid = parts[2]
            if ssid not in [ap_name, 'DigitalFrame_Setup']:
                return True
    return False

def setup_adhoc():
    iface = get_wifi_interface()
    if not iface:
        print("No wifi interface found.")
        return

    ap_name, ap_password = get_config_network()
    
    if is_wifi_connected(ap_name):
        print("Wifi already connected. Skipping AP setup.")
        return

    print(f"No active wifi connection. Setting up Access Point on {iface}...")
    
    # Remove old connections if they exist
    run_command(['sudo', 'nmcli', 'con', 'delete', ap_name])
    run_command(['sudo', 'nmcli', 'con', 'delete', 'DigitalFrame_Setup'])
    
    # Create AP connection
    # AP mode is much more compatible with modern devices than ad-hoc.
    res = run_command([
        'sudo', 'nmcli', 'con', 'add', 'type', 'wifi', 'ifname', iface, 'con-name', ap_name, 
        'autoconnect', 'yes', 'ssid', ap_name, 'mode', 'ap'
    ])
    
    if isinstance(res, subprocess.CalledProcessError) or res.returncode != 0:
        print("Failed to create AP connection. The hardware might not support it.")
        return

    # Configure with WPA2 security and password from config
    run_command(['sudo', 'nmcli', 'con', 'modify', ap_name, 
                 '802-11-wireless-security.key-mgmt', 'wpa-psk',
                 '802-11-wireless-security.psk', ap_password,
                 'ipv4.method', 'manual', 
                 'ipv4.addresses', '192.168.4.1/24',
                 'ipv6.method', 'ignore'])
    
    print(f"Bringing up {ap_name} (AP Mode) with password '{ap_password}'...")
    # Try to bring up with retries
    success = False
    for i in range(3):
        res = run_command(['sudo', 'nmcli', 'con', 'up', ap_name])
        if not isinstance(res, subprocess.CalledProcessError) and res.returncode == 0:
            success = True
            break
        print(f"Retry {i+1} to bring up AP...")
        time.sleep(2)

    if not success:
        print("Failed to bring up AP connection.")
        # Try a simpler way as last resort
        run_command(['sudo', 'nmcli', 'dev', 'wifi', 'hotspot', 'ifname', iface, 'ssid', ap_name, 'password', ap_password])
        return

    # Start dnsmasq
    print("Starting dnsmasq for DHCP...")
    # Kill any existing dnsmasq for this setup
    run_command(['sudo', 'pkill', '-9', '-f', f'dnsmasq.*{ap_name}'])
    run_command(['sudo', 'pkill', '-9', '-f', 'dnsmasq.*DigitalFrame_Setup'])
    
    dnsmasq_cmd = [
        'sudo', '/usr/sbin/dnsmasq', 
        '--interface=' + iface, 
        '--dhcp-range=192.168.4.10,192.168.4.100,255.255.255.0', 
        '--keep-in-foreground', 
        '--bind-interfaces',
        '--conf-file=' # No config file
    ]
    
    try:
        # Run in background
        subprocess.Popen(dnsmasq_cmd)
        print(f"Access Point '{ap_name}' is active. Password: {ap_password}, IP: 192.168.4.1")
    except Exception as e:
        print(f"Failed to start dnsmasq: {e}")
    except Exception as e:
        print(f"Failed to start dnsmasq: {e}")

if __name__ == "__main__":
    setup_adhoc()
