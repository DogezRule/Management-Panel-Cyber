"""Proxmox VE SSH-based API client wrapper (avoids gevent SSL recursion)"""

import paramiko
import json
from typing import Dict, List


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

    def _ssh_command(self, command: str) -> str:
        """Execute command on Proxmox host via SSH"""
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(
                self.ssh_host,
                username=self.ssh_user,
                key_filename=self.ssh_key_path,
                timeout=10
            )
            stdin, stdout, stderr = ssh.exec_command(command)
            out = stdout.read().decode()
            err = stderr.read().decode()
            ssh.close()

            if err.strip() and "warning" not in err.lower():
                raise Exception(err)
            return out
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

    def get_vnc_ticket(self, node: str, vmid: int) -> Dict:
        """Get VNC ticket for console access"""
        result = self._ssh_command(f"pvesh create /nodes/{node}/qemu/{vmid}/vncproxy --output-format=json")
        data = json.loads(result)
        return {
            "ticket": data.get("ticket", ""),
            "port": data.get("port", ""),
            "upid": data.get("upid", ""),
            "user": self.user,
            "session_ticket": data.get("upid")
        }
