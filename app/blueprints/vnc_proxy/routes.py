from flask import session
from flask_login import current_user
from ...models import VirtualMachine
from ...services.proxmox_client import ProxmoxClient
import os
import ssl
import websocket
import threading
import sys
import time
import struct
from Crypto.Cipher import DES

# Simple in-memory cache for VNC tickets (vm_id -> {ticket, port, timestamp})
vnc_ticket_cache = {}

def register_websocket_routes(sock):
    """Register WebSocket routes with flask-sock instance"""
    
    @sock.route('/vnc-proxy/ws/<int:vm_id>')
    def vnc_websocket(ws, vm_id):
        """WebSocket proxy for VNC connections to Proxmox"""
        print(f"[VNC-PROXY] New connection for VM {vm_id}")
        
        # Verify access permissions
        vm = VirtualMachine.query.get_or_404(vm_id)
        
        # Check if user is teacher/admin or student with access
        has_access = False
        if current_user.is_authenticated:
            # Teacher/admin access
            if current_user.is_admin():
                has_access = True
            elif vm.student and vm.student.classroom and vm.student.classroom.teacher_id == current_user.id:
                has_access = True
        elif session.get('student_id'):
            # Student access
            if vm.student_id == session.get('student_id'):
                has_access = True
        
        if not has_access:
            print(f"[VNC-PROXY] Access denied for VM {vm_id}")
            ws.close(message='Access denied')
            return
        
        # Get VNC ticket from Proxmox
        proxmox = ProxmoxClient(
            host=os.getenv('PROXMOX_HOST'),
            user=os.getenv('PROXMOX_USER'),
            token_name=os.getenv('PROXMOX_TOKEN_NAME'),
            token_value=os.getenv('PROXMOX_TOKEN_VALUE'),
            password=os.getenv('PROXMOX_PASSWORD')
        )
        
        proxmox_ws = None
        try:
            vnc_data = proxmox.get_vnc_ticket(vm.proxmox_node, vm.proxmox_vmid)
            
            print(f"[VNC-PROXY] Generated VNC ticket for client to use", flush=True)
            
            # Build Proxmox WebSocket URL with properly URL-encoded ticket
            from urllib.parse import urlencode
            proxmox_host = os.getenv('PROXMOX_HOST').replace('https://', '').replace('http://', '')
            proxmox_ws_url = f"wss://{proxmox_host}/api2/json/nodes/{vm.proxmox_node}/qemu/{vm.proxmox_vmid}/vncwebsocket"
            # URL encode the parameters properly
            params = urlencode({'port': vnc_data['port'], 'vncticket': vnc_data['ticket']})
            proxmox_ws_url += f"?{params}"
            
            print(f"[VNC-PROXY] VM {vm_id}: Connecting to Proxmox...", flush=True)
            print(f"[VNC-PROXY] Port: {vnc_data['port']}, Node: {vm.proxmox_node}, VMID: {vm.proxmox_vmid}", flush=True)
            print(f"[VNC-PROXY] VNC Ticket: {vnc_data['ticket'][:50]}... (len={len(vnc_data['ticket'])})", flush=True)
            print(f"[VNC-PROXY] Session Ticket: {vnc_data.get('session_ticket', 'None')[:50] if vnc_data.get('session_ticket') else 'None'}...", flush=True)
            print(f"[VNC-PROXY] User: {vnc_data.get('user')}", flush=True)
            print(f"[VNC-PROXY] Full URL (first 150 chars): {proxmox_ws_url[:150]}...", flush=True)
            sys.stdout.flush()
            
            # Connect to Proxmox WebSocket with session cookie for authentication
            proxmox_ws = websocket.WebSocket(sslopt={"cert_reqs": ssl.CERT_NONE})
            # Use session ticket as PVEAuthCookie if available
            if vnc_data.get('session_ticket'):
                headers = {"Cookie": f"PVEAuthCookie={vnc_data['session_ticket']}"}
                print(f"[VNC-PROXY] Using session ticket for authentication", flush=True)
                proxmox_ws.connect(proxmox_ws_url, header=headers)
            else:
                print(f"[VNC-PROXY] WARNING: No session ticket available, using VNC ticket only", flush=True)
                proxmox_ws.connect(proxmox_ws_url)
            # Set timeout high enough to not interfere with normal operation
            proxmox_ws.settimeout(30)
            
            print(f"[VNC-PROXY] Connected successfully, starting bidirectional proxy", flush=True)
            print(f"[VNC-PROXY] Flask-Sock ws type: {type(ws)}, has receive: {hasattr(ws, 'receive')}", flush=True)
            print(f"[VNC-PROXY] Proxmox WebSocket status: connected={proxmox_ws.connected}, sock={proxmox_ws.sock is not None}", flush=True)
            
            # VNC authentication helper
            def vnc_encrypt_des(password, challenge):
                """DES encrypt challenge using VNC password (mirror bits)"""
                # VNC password must be exactly 8 bytes, pad or truncate
                key = (password[:8] + b'\x00' * 8)[:8]
                # VNC uses mirrored bits for DES key
                key_mirrored = bytes([int('{:08b}'.format(b)[::-1], 2) for b in key])
                cipher = DES.new(key_mirrored, DES.MODE_ECB)
                return cipher.encrypt(challenge)
            
            # Store VNC ticket for auth
            ticket_bytes = vnc_data['ticket'].encode('latin-1')
            vnc_challenge = None
            vnc_auth_complete = False
            
            # Forward from client to Proxmox
            def client_to_proxmox():
                nonlocal vnc_challenge, vnc_auth_complete
                print(f"[VNC-PROXY] Client->Proxmox thread running, waiting for client data...", flush=True)
                try:
                    msg_count = 0
                    while True:
                        try:
                            data = ws.receive()
                            if data is None:
                                print(f"[VNC-PROXY] Client closed connection (receive returned None)", flush=True)
                                break
                        except Exception as recv_err:
                            print(f"[VNC-PROXY] Error receiving from client: {type(recv_err).__name__}: {recv_err}", flush=True)
                            break
                        
                        msg_count += 1
                        
                        if msg_count <= 20:
                            hex_preview = data[:32].hex() if isinstance(data, bytes) and len(data) <= 64 else (data[:32].hex() + "..." if isinstance(data, bytes) else str(data)[:50])
                            print(f"[VNC-PROXY] C->P msg #{msg_count}: {len(data)} bytes, hex={hex_preview}", flush=True)
                        
                        # Intercept the VNC auth response (16 bytes after challenge)
                        if not vnc_auth_complete and isinstance(data, bytes) and len(data) == 16 and vnc_challenge is not None:
                            print(f"[VNC-PROXY] Intercepting client VNC auth response, sending our encrypted ticket instead", flush=True)
                            # Don't forward client response, send ours
                            our_response = vnc_encrypt_des(ticket_bytes, vnc_challenge)
                            print(f"[VNC-PROXY] Sending encrypted response: {our_response.hex()}", flush=True)
                            proxmox_ws.send(our_response, opcode=websocket.ABNF.OPCODE_BINARY)
                            vnc_challenge = None  # Clear so we don't intercept again
                            continue
                        
                        # Forward everything else normally
                        proxmox_ws.send(data, opcode=websocket.ABNF.OPCODE_BINARY if isinstance(data, bytes) else websocket.ABNF.OPCODE_TEXT)
                except Exception as e:
                    print(f"[VNC-PROXY] Client->Proxmox thread error: {e}", flush=True)
                    import traceback
                    traceback.print_exc()
                finally:
                    try:
                        proxmox_ws.close()
                    except:
                        pass
            
            # Start client->proxmox thread
            thread = threading.Thread(target=client_to_proxmox, daemon=True)
            thread.start()
            print(f"[VNC-PROXY] Client->Proxmox forwarding thread started", flush=True)
            
            # Forward from Proxmox to client (main thread)
            msg_count = 0
            print(f"[VNC-PROXY] Waiting for data from Proxmox...", flush=True)
            while True:
                try:
                    data = proxmox_ws.recv()
                    if not data:
                        print(f"[VNC-PROXY] Proxmox closed connection (recv returned empty)", flush=True)
                        break
                    msg_count += 1
                    
                    if msg_count <= 20:
                        hex_preview = data[:32].hex() if isinstance(data, bytes) and len(data) <= 64 else (data[:32].hex() + "..." if isinstance(data, bytes) else str(data)[:50])
                        print(f"[VNC-PROXY] P->C msg #{msg_count}: {len(data)} bytes, hex={hex_preview}", flush=True)
                    
                    # Detect VNC auth challenge (16 bytes, typically message #4)
                    if not vnc_auth_complete and isinstance(data, bytes) and len(data) == 16 and msg_count >= 3:
                        print(f"[VNC-PROXY] Detected VNC auth challenge, storing it", flush=True)
                        vnc_challenge = data
                        # Forward to client so it can attempt auth
                        ws.send(data)
                        continue
                    
                    # Detect auth result (4 bytes)
                    if not vnc_auth_complete and isinstance(data, bytes) and len(data) == 4:
                        result = struct.unpack('>I', data)[0]
                        if result == 0:
                            print(f"[VNC-PROXY] ✓ VNC authentication successful!", flush=True)
                            vnc_auth_complete = True
                        else:
                            print(f"[VNC-PROXY] ✗ VNC authentication failed: {result}", flush=True)
                    
                    # Forward everything to client
                    ws.send(data)
                except Exception as e:
                    if "timed out" not in str(e).lower():
                        print(f"[VNC-PROXY] Proxmox->Client error: {e}", flush=True)
                        break
            
        except Exception as e:
            print(f"[VNC-PROXY] Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            print(f"[VNC-PROXY] Closing connection for VM {vm_id}")
            if proxmox_ws:
                try:
                    proxmox_ws.close()
                except:
                    pass
