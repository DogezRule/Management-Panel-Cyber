#!/usr/bin/env python3
"""
Simple status check - no subprocess calls
"""

import os
import socket

print("CyberLab Admin - Service Status Check")
print("=" * 50)

# Check if service file exists
service_file = "/etc/systemd/system/cyberlab-admin.service"
if os.path.exists(service_file):
    print(f"✅ Service file exists: {service_file}")
else:
    print(f"❌ Service file missing: {service_file}")

# Check if port 8000 is open
print("\nChecking if Flask is listening on 8000...")
try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    result = sock.connect_ex(('127.0.0.1', 8000))
    sock.close()
    if result == 0:
        print("✅ Port 8000 is open (Flask likely running)")
    else:
        print("❌ Port 8000 is closed (Flask not listening)")
except Exception as e:
    print(f"⚠️  Could not check port 8000: {e}")

# Check if Caddy is listening
print("\nChecking if Caddy is listening on 443...")
try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    result = sock.connect_ex(('127.0.0.1', 443))
    sock.close()
    if result == 0:
        print("✅ Port 443 is open (Caddy likely running)")
    else:
        print("❌ Port 443 is closed (Caddy not listening)")
except Exception as e:
    print(f"⚠️  Could not check port 443: {e}")

# Check key files
print("\nChecking key files...")
key_files = [
    "/home/admin/Admin-Panel/cyberlab-admin/.env",
    "/home/admin/Admin-Panel/cyberlab-admin/id_rsa",
    "/home/admin/Admin-Panel/cyberlab-admin/deploy/caddy/root.crt",
    "/home/admin/Admin-Panel/cyberlab-admin/deploy/gunicorn.service"
]

for f in key_files:
    if os.path.exists(f):
        print(f"✅ {os.path.basename(f)} exists")
    else:
        print(f"❌ {os.path.basename(f)} missing")

print("\n" + "=" * 50)
print("Status check complete")
