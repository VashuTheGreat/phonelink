import sys
import json
import threading
import socket
import subprocess

# The same UUID used in the Android App (Not strictly needed for native sockets if we just iterate ports, but good for reference)
SPP_UUID = "00001101-0000-1000-8000-00805F9B34FB"

def get_paired_devices():
    try:
        # Run bluetoothctl to get paired devices
        result = subprocess.run(['bluetoothctl', 'devices'], capture_output=True, text=True, check=True)
        devices = []
        for line in result.stdout.split('\n'):
            if line.startswith('Device'):
                parts = line.split(' ', 2)
                if len(parts) >= 3:
                    devices.append({'mac': parts[1], 'name': parts[2]})
        return devices
    except Exception as e:
        print(f"Failed to run bluetoothctl: {e}")
        return []

class PhoneLinkBTClient:
    def __init__(self):
        self.sock = None
        self.connected = False
        self.receive_thread = None

    def connect(self, address=None):
        if not address:
            devices = get_paired_devices()
            if not devices:
                print("Could not find any paired Bluetooth devices. Please pair your phone first.")
                return False
                
            print("\nPaired Bluetooth Devices:")
            for i, dev in enumerate(devices):
                print(f"[{i+1}] {dev['name']} ({dev['mac']})")
                
            try:
                choice = int(input("\nSelect your phone (number): ")) - 1
                if 0 <= choice < len(devices):
                    address = devices[choice]['mac']
                else:
                    print("Invalid selection.")
                    return False
            except ValueError:
                print("Invalid input.")
                return False

        print(f"\nAttempting to connect to {address}...")
        
        # We don't have SDP via native sockets easily, so we try RFCOMM ports 1 to 30
        connected = False
        for port in range(1, 15): # Usually Android SPP is between 1 and 10
            try:
                print(f"Trying RFCOMM port {port}...")
                s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
                s.settimeout(3.0) # 3 seconds timeout per port
                s.connect((address, port))
                
                # Check for handshake
                try:
                    data = s.recv(1024).decode('utf-8', errors='ignore')
                    if "PHONELINK_READY" in data:
                        s.settimeout(None) # Reset timeout for blocking operations
                        self.sock = s
                        self.connected = True
                        connected = True
                        print(f"Connected successfully to PhoneLink App on port {port}!\n")
                        break
                    else:
                        print(f"Port {port} is active but it is not the PhoneLink App (likely Headset/HFP). Skipping...")
                        s.close()
                except socket.timeout:
                    print(f"Port {port} connected but did not send handshake. Skipping...")
                    s.close()
            except Exception as e:
                s.close()
                
        if not connected:
            print("Failed to connect. Make sure the PhoneLink Android App is running the BT Server.")
            return False

        # Start a thread to listen for incoming data from the phone
        self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self.receive_thread.start()
        return True

    def _receive_loop(self):
        try:
            while self.connected:
                data = self.sock.recv(1024)
                if not data:
                    break
                print(f"\n[Phone -> PC]: {data.decode('utf-8')}")
                print("PhoneLink> ", end="", flush=True)
        except Exception:
            pass
        finally:
            print("\nConnection lost.")
            self.connected = False

    def send_command(self, action, number=""):
        if not self.connected:
            print("Not connected to phone.")
            return
            
        payload = {
            "action": action,
            "number": number
        }
        
        try:
            self.sock.send(json.dumps(payload).encode('utf-8'))
            print(f"Sent command: {action} {number}")
        except Exception as e:
            print(f"Failed to send command: {e}")
            self.connected = False

    def disconnect(self):
        self.connected = False
        if self.sock:
            self.sock.close()
            self.sock = None
        print("Disconnected.")


def main():
    print("=== PhoneLink Bluetooth Desktop Client ===")
    print("Make sure you have paired your phone with your PC via Bluetooth.")
    print("If you want call voice to route to your PC, ensure it's connected as a 'Headset' (HFP).")
    print("==========================================")
        
    client = PhoneLinkBTClient()
    
    address = None
    if len(sys.argv) > 1:
        address = sys.argv[1]
        
    if not client.connect(address):
        sys.exit(1)
        
    print("\nCommands:")
    print("  dial <number>  - Initiate a call")
    print("  answer         - Answer incoming call")
    print("  hangup         - End current call")
    print("  exit           - Disconnect and quit")
    
    try:
        while client.connected:
            cmd_input = input("\nPhoneLink> ").strip().split()
            if not cmd_input:
                continue
                
            cmd = cmd_input[0].lower()
            
            if cmd == "exit" or cmd == "quit":
                break
            elif cmd == "dial":
                if len(cmd_input) > 1:
                    client.send_command("dial", cmd_input[1])
                else:
                    print("Please specify a number. Usage: dial <number>")
            elif cmd == "answer":
                client.send_command("answer")
            elif cmd == "hangup":
                client.send_command("hangup")
            else:
                print("Unknown command.")
                
    except KeyboardInterrupt:
        pass
    finally:
        client.disconnect()

if __name__ == "__main__":
    main()
