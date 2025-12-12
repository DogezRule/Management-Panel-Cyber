"""Proxmox VE SSH-based API client wrapper (avoids gevent SSL recursion)"""

import paramiko
import json
import threading
import time
from typing import Dict, List


# Global SSH connection pool to avoid resource exhaustion
_ssh_pool_lock = threading.Lock()
_ssh_connections = {}  # Key: (host, user, key_path) -> SSHClient
_ssh_timestamps = {}   # Track when connections were created


class ProxmoxClient:
    """Client for interacting with Proxmox VE via SSH commands."""

    def __init__(
        self,
        host: str,
        user: str = None,
        token_name: str = None,
        token_value: str = None,
        ssh_host: str = None,
        ssh_user: str = None,
        ssh_key_path: str = None,
        password: str = None
    ):
        self.host = host
        self.user = user
        self.token_name = token_name
        self.token_value = token_value
        self.password = password

        self.ssh_host = ssh_host
        self.ssh_user = ssh_user
        self.ssh_key_path = ssh_key_path

        self.use_ssh = bool(ssh_key_path and ssh_host)

        if not self.use_ssh:
            raise Exception("SSH configuration required (ssh_host and ssh_key_path)")

        self.session_ticket = None
        self.csrf_token = None
        
        # Auth cookie and CSRF token cache (per instance)
        self._auth_cookie = None
        self._csrf_token = None
        self._auth_cookie_time = 0

    def _get_ssh_connection(self):
        """Get or create an SSH connection from the pool"""
        global _ssh_connections, _ssh_timestamps, _ssh_pool_lock
        
        key = (self.ssh_host, self.ssh_user, self.ssh_key_path)
        
        with _ssh_pool_lock:
            # Check if we have a reusable connection
            if key in _ssh_connections:
                ssh = _ssh_connections[key]
                # Verify it's still alive with gevent timeout
                try:
                    import gevent
                    with gevent.Timeout(2):
                        transport = ssh.get_transport()
                        if transport and transport.is_active():
                            return ssh
                        else:
                            raise Exception("Transport inactive")
                except:
                    # Connection dead, remove it
                    try:
                        ssh.close()
                    except:
                        pass
                    del _ssh_connections[key]
                    if key in _ssh_timestamps:
                        del _ssh_timestamps[key]
            
            # Create new connection
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(
                self.ssh_host,
                username=self.ssh_user,
                key_filename=self.ssh_key_path,
                timeout=10
            )
            _ssh_connections[key] = ssh
            _ssh_timestamps[key] = time.time()
            return ssh

    def _ssh_command(self, command: str) -> str:
        """Execute command on Proxmox host via SSH"""
        import gevent
        try:
            with gevent.Timeout(15):
                ssh = self._get_ssh_connection()
                stdin, stdout, stderr = ssh.exec_command(command)
                out = stdout.read().decode()
                err = stderr.read().decode()

                if err.strip() and "warning" not in err.lower():
                    raise Exception(err)
                return out
        except gevent.Timeout:
            raise Exception(f"SSH command timed out after 15s: {command[:50]}...")
        except Exception as e:
            raise Exception(f"SSH error: {e}")

    def get_nodes(self) -> List[str]:
        """Get list of cluster nodes"""
        result = self._ssh_command("pvesh get /nodes --output-format=json")
        nodes = json.loads(result)
        return [n["node"] for n in nodes]

    def get_next_vmid(self) -> int:
        """Get next available VMID"""
        result = self._ssh_command("pvesh get /cluster/nextid")
        return int(result.strip())

    def get_vm_config(self, node: str, vmid: int) -> Dict:
        """Get VM configuration"""
        result = self._ssh_command(f"pvesh get /nodes/{node}/qemu/{vmid}/config --output-format=json")
        return json.loads(result)

    def get_vm_status(self, node: str, vmid: int) -> Dict:
        """Get VM status"""
        result = self._ssh_command(f"pvesh get /nodes/{node}/qemu/{vmid}/status/current --output-format=json")
        return json.loads(result)

    def start_vm(self, node: str, vmid: int):
        """Start a VM"""
        self._ssh_command(f"pvesh create /nodes/{node}/qemu/{vmid}/status/start")

    def stop_vm(self, node: str, vmid: int):
        """Stop a VM"""
        self._ssh_command(f"pvesh create /nodes/{node}/qemu/{vmid}/status/stop")

    def reset_vm(self, node: str, vmid: int):
        """Reset a VM"""
        self._ssh_command(f"pvesh create /nodes/{node}/qemu/{vmid}/status/reset")

    def suspend_vm(self, node: str, vmid: int):
        """Suspend a VM"""
        self._ssh_command(f"pvesh create /nodes/{node}/qemu/{vmid}/status/suspend")

    def resume_vm(self, node: str, vmid: int):
        """Resume a VM"""
        self._ssh_command(f"pvesh create /nodes/{node}/qemu/{vmid}/status/resume")

    def delete_vm(self, node: str, vmid: int):
        """Delete a VM"""
        self._ssh_command(f"pvesh delete /nodes/{node}/qemu/{vmid}")

    def get_auth_cookie(self) -> str:
        """Get PVEAuthCookie using password authentication via API with caching"""
        if not self.password:
            raise Exception("Password required for WebSocket VNC authentication")
        
        # Return cached cookie if valid (good for ~2 hours, but cache for 30 mins)
        if self._auth_cookie and (time.time() - self._auth_cookie_time) < 1800:
            return self._auth_cookie
        
        # Use API to create access ticket (no SSH)
        import requests
        url = f"{self.host}/api2/json/access/ticket"
        data = {
            "username": self.user,
            "password": self.password
        }
        
        response = requests.post(url, data=data, verify=False, timeout=10)
        response.raise_for_status()
        result = response.json()['data']
        
        self._auth_cookie = result.get("ticket", "")
        self._csrf_token = result.get("CSRFPreventionToken", "")
        self._auth_cookie_time = time.time()
        return self._auth_cookie
    
    def get_csrf_token(self) -> str:
        """Get CSRF token (call get_auth_cookie first to populate it)"""
        if not self._csrf_token:
            # Refresh auth which also gets CSRF token
            self.get_auth_cookie()
        return self._csrf_token
    
    def get_vnc_ticket(self, node: str, vmid: int) -> Dict:
        """Get VNC ticket for console access via API (preferring Token over Password)"""
        import requests
        url = f"{self.host}/api2/json/nodes/{node}/qemu/{vmid}/vncproxy"
        
        headers = {}
        
        # Use API Token if available
        if self.token_name and self.token_value:
            headers['Authorization'] = f"PVEAPIToken={self.user}!{self.token_name}={self.token_value}"
        else:
            # Fallback to Password/Cookie auth
            auth_cookie = self.get_auth_cookie()
            csrf_token = self.get_csrf_token()
            headers['Cookie'] = f'PVEAuthCookie={auth_cookie}'
            headers['CSRFPreventionToken'] = csrf_token
        
        # Request a WebSocket-compatible ticket
        response = requests.post(url, headers=headers, data={'websocket': 1}, verify=False, timeout=10)
        response.raise_for_status()
        data = response.json()['data']
        
        return {
            "ticket": data.get("ticket", ""),
            "port": data.get("port", ""),
            "upid": data.get("upid", ""),
            "user": data.get("user", self.user), # Proxmox might return the user now
            "auth_cookie": None
        }
