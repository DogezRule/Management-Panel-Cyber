"""Proxmox VE API and SSH client wrapper"""

import requests
import paramiko
import json
import urllib3
from typing import Dict, List, Optional

# Disable SSL warnings for self-signed certs (use properly in production)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class ProxmoxClient:
    """Client for interacting with Proxmox VE via API or SSH"""
    
    def __init__(self, host: str, user: str = None, token_name: str = None, 
                 token_value: str = None, ssh_host: str = None, ssh_user: str = None,
                 ssh_key_path: str = None, password: str = None):
        self.host = host
        self.user = user
        self.token_name = token_name
        self.token_value = token_value
        self.password = password
        self.ssh_host = ssh_host
        self.ssh_user = ssh_user
        self.ssh_key_path = ssh_key_path
        self.use_ssh = bool(ssh_key_path)
        self.session_ticket = None
        self.csrf_token = None
        
        if not self.use_ssh:
            self.api_token = f"{user}!{token_name}={token_value}"
            self.headers = {
                'Authorization': f'PVEAPIToken={self.api_token}'
            }
    
    def _api_request(self, method: str, endpoint: str, data: Dict = None) -> Dict:
        """Make API request to Proxmox"""
        url = f"{self.host}/api2/json/{endpoint}"
        print(f"[PROXMOX] {method} {url}")
        print(f"[PROXMOX] Data: {data}")
        try:
            if method == 'GET':
                response = requests.get(url, headers=self.headers, verify=False)
            elif method == 'POST':
                response = requests.post(url, headers=self.headers, data=data, verify=False)
            elif method == 'DELETE':
                response = requests.delete(url, headers=self.headers, verify=False)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            print(f"[PROXMOX] Response status: {response.status_code}")
            print(f"[PROXMOX] Response text: {response.text[:500]}")
            response.raise_for_status()
            return response.json().get('data', {})
        except requests.exceptions.HTTPError as e:
            # Try to get detailed error message from response
            try:
                error_detail = response.json()
                print(f"[PROXMOX] Error detail: {error_detail}")
                raise Exception(f"Proxmox API error: {e} - Details: {error_detail}")
            except:
                raise Exception(f"Proxmox API error: {e}")
        except Exception as e:
            raise Exception(f"Proxmox API error: {str(e)}")
    
    def _ssh_command(self, command: str) -> str:
        """Execute command via SSH"""
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(
                self.ssh_host,
                username=self.ssh_user,
                key_filename=self.ssh_key_path
            )
            stdin, stdout, stderr = ssh.exec_command(command)
            result = stdout.read().decode()
            error = stderr.read().decode()
            ssh.close()
            
            if error:
                raise Exception(f"SSH command error: {error}")
            return result
        except Exception as e:
            raise Exception(f"SSH error: {str(e)}")
    
    def get_nodes(self) -> List[str]:
        """Get list of Proxmox nodes"""
        if self.use_ssh:
            result = self._ssh_command("pvesh get /nodes --output-format=json")
            nodes = json.loads(result)
            return [node['node'] for node in nodes]
        else:
            data = self._api_request('GET', 'nodes')
            return [node['node'] for node in data]
    
    def get_next_vmid(self) -> int:
        """Get next available VM ID"""
        if self.use_ssh:
            result = self._ssh_command("pvesh get /cluster/nextid")
            return int(result.strip())
        else:
            data = self._api_request('GET', 'cluster/nextid')
            return int(data)
    
    def clone_vm(self, node: str, template_id: int, new_vmid: int, name: str, storage: str = None, linked: bool = True) -> Dict:
        """Clone a VM from template with support for linked clones"""
        if self.use_ssh:
            cmd = f"qm clone {template_id} {new_vmid} --name {name}"
            if linked:
                cmd += " --snapname __base__"
            if storage:
                cmd += f" --storage {storage}"
            self._ssh_command(cmd)
            return {'vmid': new_vmid, 'node': node}
        else:
            endpoint = f"nodes/{node}/qemu/{template_id}/clone"
            data = {
                'newid': new_vmid,
                'name': name
            }
            # For linked clones, use snapname parameter
            if linked:
                data['snapname'] = '__base__'
            # Add storage parameter if provided
            if storage:
                data['storage'] = storage
            return self._api_request('POST', endpoint, data)
    
    def create_linked_clone(self, source_node: str, template_id: int, target_node: str, new_vmid: int, name: str, storage: str = None) -> Dict:
        """Create a linked clone, optimized for performance"""
        return self.clone_vm(target_node, template_id, new_vmid, name, storage, linked=True)
    
    def replicate_template(self, source_node: str, source_template_id: int, target_node: str, target_template_id: int = None) -> Dict:
        """Replicate a template from one node to another"""
        if target_template_id is None:
            target_template_id = self.get_next_vmid()
        
        # Get source template info
        source_config = self.get_vm_config(source_node, source_template_id)
        template_name = source_config.get('name', f'template-{source_template_id}')
        
        if self.use_ssh:
            # Use pvesh for cross-node replication
            cmd = f"qm migrate {source_template_id} {target_node} --online --with-local-disks"
            self._ssh_command(cmd)
        else:
            # Use API to migrate/copy template
            endpoint = f"nodes/{source_node}/qemu/{source_template_id}/migrate"
            data = {
                'target': target_node,
                'targetstorage': 'local-lvm',  # Default storage
                'with-local-disks': 1
            }
            self._api_request('POST', endpoint, data)
        
        return {'vmid': target_template_id, 'node': target_node}
    
    def get_node_vm_count(self, node: str) -> int:
        """Get count of VMs currently on a node"""
        if self.use_ssh:
            result = self._ssh_command(f"qm list | grep -c '^[ ]*[0-9]' || true")
            return int(result.strip()) if result.strip().isdigit() else 0
        else:
            data = self._api_request('GET', f'nodes/{node}/qemu')
            return len(data) if data else 0
    
    def get_node_resources(self, node: str) -> Dict:
        """Get node resource usage information"""
        if self.use_ssh:
            result = self._ssh_command(f"pvesh get /nodes/{node}/status --output-format=json")
            return json.loads(result)
        else:
            return self._api_request('GET', f'nodes/{node}/status')

    def get_node_storages(self, node: str) -> List[Dict]:
        """Get list of storages available on a node"""
        if self.use_ssh:
            result = self._ssh_command("pvesh get /storage --output-format=json")
            data = json.loads(result)
            return data
        else:
            return self._api_request('GET', f'nodes/{node}/storage')
    
    def optimize_vm_for_performance(self, node: str, vmid: int) -> None:
        """Apply performance optimizations to a VM"""
        # Get current config
        config = self.get_vm_config(node, vmid)
        
        # Performance optimizations
        optimizations = {}
        
        # Enable QEMU Guest Agent for better performance monitoring
        if 'agent' not in config:
            optimizations['agent'] = 'enabled=1'
        
        # Set CPU type for better performance
        if 'cpu' not in config or config.get('cpu') == 'qemu64':
            optimizations['cpu'] = 'host'
        
        # Enable virtio for better I/O performance
        if 'balloon' not in config:
            optimizations['balloon'] = 0  # Disable memory ballooning for consistent performance
        
        # Apply optimizations if any
        if optimizations:
            if self.use_ssh:
                for key, value in optimizations.items():
                    self._ssh_command(f"qm set {vmid} --{key} {value}")
            else:
                endpoint = f"nodes/{node}/qemu/{vmid}/config"
                self._api_request('PUT', endpoint, optimizations)
    
    def create_template_snapshot(self, node: str, vmid: int, snapname: str = '__base__') -> Dict:
        """Create a snapshot for linked clones"""
        if self.use_ssh:
            self._ssh_command(f"qm snapshot {vmid} {snapname}")
            return {'snapname': snapname}
        else:
            endpoint = f"nodes/{node}/qemu/{vmid}/snapshot"
            data = {'snapname': snapname}
            return self._api_request('POST', endpoint, data)
    
    def start_vm(self, node: str, vmid: int) -> Dict:
        """Start a VM"""
        if self.use_ssh:
            self._ssh_command(f"qm start {vmid}")
            return {'status': 'started'}
        else:
            endpoint = f"nodes/{node}/qemu/{vmid}/status/start"
            return self._api_request('POST', endpoint)
    
    def stop_vm(self, node: str, vmid: int) -> Dict:
        """Stop a VM"""
        if self.use_ssh:
            self._ssh_command(f"qm stop {vmid}")
            return {'status': 'stopped'}
        else:
            endpoint = f"nodes/{node}/qemu/{vmid}/status/stop"
            return self._api_request('POST', endpoint)
    
    def reset_vm(self, node: str, vmid: int) -> Dict:
        """Reset a VM"""
        if self.use_ssh:
            self._ssh_command(f"qm reset {vmid}")
            return {'status': 'reset'}
        else:
            endpoint = f"nodes/{node}/qemu/{vmid}/status/reset"
            return self._api_request('POST', endpoint)
    
    def suspend_vm(self, node: str, vmid: int) -> Dict:
        """Suspend a VM"""
        if self.use_ssh:
            self._ssh_command(f"qm suspend {vmid}")
            return {'status': 'suspended'}
        else:
            endpoint = f"nodes/{node}/qemu/{vmid}/status/suspend"
            return self._api_request('POST', endpoint)
    
    def resume_vm(self, node: str, vmid: int) -> Dict:
        """Resume a VM"""
        if self.use_ssh:
            self._ssh_command(f"qm resume {vmid}")
            return {'status': 'running'}
        else:
            endpoint = f"nodes/{node}/qemu/{vmid}/status/resume"
            return self._api_request('POST', endpoint)
    
    def delete_vm(self, node: str, vmid: int) -> Dict:
        """Delete a VM"""
        if self.use_ssh:
            self._ssh_command(f"qm destroy {vmid}")
            return {'status': 'deleted'}
        else:
            endpoint = f"nodes/{node}/qemu/{vmid}"
            return self._api_request('DELETE', endpoint)
    
    def get_vm_status(self, node: str, vmid: int) -> Dict:
        """Get VM status"""
        if self.use_ssh:
            result = self._ssh_command(f"qm status {vmid}")
            # Parse output like "status: running"
            status = result.split(':')[1].strip() if ':' in result else 'unknown'
            return {'status': status, 'vmid': vmid}
        else:
            endpoint = f"nodes/{node}/qemu/{vmid}/status/current"
            return self._api_request('GET', endpoint)
    
    def get_vm_config(self, node: str, vmid: int) -> Dict:
        """Get VM configuration"""
        if self.use_ssh:
            result = self._ssh_command(f"qm config {vmid}")
            # Parse config output
            config = {}
            for line in result.split('\n'):
                if ':' in line:
                    key, value = line.split(':', 1)
                    config[key.strip()] = value.strip()
            return config
        else:
            endpoint = f"nodes/{node}/qemu/{vmid}/config"
            return self._api_request('GET', endpoint)
    
    def get_console_url(self, node: str, vmid: int) -> str:
        """Get URL for Proxmox noVNC console (for isolated VMs with no network)"""
        return f"{self.host}/?console=kvm&novnc=1&vmid={vmid}&node={node}"
    
    def get_vm_config(self, node: str, vmid: int) -> Dict:
        """Get VM configuration"""
        endpoint = f"nodes/{node}/qemu/{vmid}/config"
        return self._api_request('GET', endpoint)
    
    def create_session_ticket(self) -> Dict:
        """Create a session ticket using password authentication (required for VNC WebSocket)"""
        if not self.password:
            raise Exception("Password is required for VNC WebSocket authentication")
        
        url = f"{self.host}/api2/json/access/ticket"
        data = {
            'username': self.user,
            'password': self.password
        }
        print(f"[PROXMOX] Creating session ticket for user: {self.user}")
        response = requests.post(url, data=data, verify=False)
        response.raise_for_status()
        result = response.json().get('data', {})
        
        self.session_ticket = result.get('ticket')
        self.csrf_token = result.get('CSRFPreventionToken')
        print(f"[PROXMOX] Session ticket created successfully")
        
        return {
            'ticket': self.session_ticket,
            'csrf': self.csrf_token
        }
    
    def get_vnc_ticket(self, node: str, vmid: int) -> Dict:
        """Get VNC websocket ticket for console access"""
        # First check VM config
        config = self.get_vm_config(node, vmid)
        print(f"[PROXMOX] VM {vmid} config - vga: {config.get('vga')}, args: {config.get('args')}")
        
        # If password is available, create session and use session-based auth for VNC
        session_data = None
        if self.password:
            try:
                session_data = self.create_session_ticket()
                # Get VNC ticket using session auth instead of API token
                url = f"{self.host}/api2/json/nodes/{node}/qemu/{vmid}/vncproxy"
                headers_with_session = {
                    'Cookie': f'PVEAuthCookie={self.session_ticket}',
                    'CSRFPreventionToken': self.csrf_token
                }
                data = {'websocket': 1}
                print(f"[PROXMOX] POST {url} (using session auth)")
                response = requests.post(url, headers=headers_with_session, data=data, verify=False)
                response.raise_for_status()
                result = response.json().get('data', {})
                print(f"[PROXMOX] VNC Ticket (from session): port={result.get('port')}, user={result.get('user')}")
                
                return {
                    'ticket': result.get('ticket'),
                    'port': result.get('port'),
                    'user': result.get('user'),
                    'cert': result.get('cert'),
                    'session_ticket': self.session_ticket
                }
            except Exception as e:
                print(f"[PROXMOX] Error with session-based VNC ticket: {e}")
                print(f"[PROXMOX] Falling back to API token method")
        
        # Fallback to API token method
        endpoint = f"nodes/{node}/qemu/{vmid}/vncproxy"
        data = {'websocket': 1}
        result = self._api_request('POST', endpoint, data=data)
        print(f"[PROXMOX] VNC Ticket response: port={result.get('port')}, user={result.get('user')}")
        
        return {
            'ticket': result.get('ticket'),
            'port': result.get('port'),
            'user': result.get('user'),
            'cert': result.get('cert'),
            'session_ticket': None
        }
