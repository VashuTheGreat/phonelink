import sys
import json
import threading
import socket
import subprocess
import time

SPP_UUID = "00001101-0000-1000-8000-00805F9B34FB"


# ─────────────────────────────────────────────────────────────
#  HFP Audio Manager
# ─────────────────────────────────────────────────────────────

class HFPAudioManager:
    def __init__(self, phone_mac: str):
        self.phone_mac = phone_mac
        self._card = f"bluez_card.{phone_mac.replace(':', '_')}"
        self._ofono_path = f"/hfp/org/bluez/hci0/dev_{phone_mac.replace(':', '_')}"

    def _run(self, cmd, silent=False):
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if not silent and r.stdout.strip():
                print(f"  [HFP] {r.stdout.strip()}")
            return r.returncode == 0, r.stdout.strip()
        except Exception as e:
            return False, str(e)

    def _dbus(self, path, iface_method, *args, silent=True):
        args_str = " ".join(args)
        cmd = (
            f"dbus-send --system --print-reply --dest=org.ofono "
            f"{path} {iface_method} {args_str}"
        )
        return self._run(cmd, silent=silent)

    def setup_hfp(self):
        """
        ofono modem power on + online karo.
        WirePlumber iske baad properly headset-head-unit profile create karta hai.
        """
        print("\n[HFP] ofono modem setup kar raha hun...")

        # Powered = true
        ok, out = self._dbus(
            self._ofono_path,
            "org.ofono.Modem.SetProperty",
            'string:"Powered"', 'variant:boolean:true'
        )
        if ok:
            print("  [HFP] ✅ Modem Powered ON")
        else:
            print(f"  [HFP] ⚠️  Modem power on failed: {out}")

        time.sleep(1.0)

        # Online = true
        ok, out = self._dbus(
            self._ofono_path,
            "org.ofono.Modem.SetProperty",
            'string:"Online"', 'variant:boolean:true'
        )
        if ok:
            print("  [HFP] ✅ Modem Online")
        else:
            print(f"  [HFP] ⚠️  Modem online failed (may already be): {out}")

        time.sleep(0.5)

        # Check karo modem sahi hai
        ok, out = self._dbus(
            self._ofono_path,
            "org.ofono.Modem.GetProperties",
            silent=False
        )

        # WirePlumber ko profile update karne ka mauka do
        # Bluetooth reconnect karo taaki PipeWire naya state pakde
        print("  [HFP] Bluetooth reconnect kar raha hun (WirePlumber sync ke liye)...")
        self._run(f"bluetoothctl disconnect {self.phone_mac}", silent=True)
        time.sleep(1.5)
        self._run(f"bluetoothctl connect {self.phone_mac}", silent=True)
        time.sleep(2.0)

        # Profile check
        ok2, profiles = self._run(f"pactl list cards", silent=True)
        if "headset-head-unit" in profiles:
            print("  [HFP] ✅ headset-head-unit profile available hai!")
            self._run(
                f"pactl set-card-profile {self._card} headset-head-unit",
                silent=True
            )
            print("  [HFP] ✅ headset-head-unit profile set kiya")
        else:
            print("  [HFP] ⚠️  headset-head-unit profile abhi nahi mili")
            print("  [HFP] Workaround: audio-gateway mode mein call hogi")
            print("  [HFP] Phone ki call screen pe manually Bluetooth select karna hoga")

    def activate_call_audio(self):
        """Dial se pehle call audio + mic dono Bluetooth pe set karo"""
        print("\n[HFP] Call audio activate kar raha hun...")

        # headset-head-unit profile set karo
        ok, _ = self._run(
            f"pactl set-card-profile {self._card} headset-head-unit",
            silent=True
        )
        if ok:
            print("  [HFP] ✅ headset-head-unit profile set hua")
        else:
            print("  [HFP] ⚠️  Profile set nahi hua")

        time.sleep(0.5)

        # Default SINK (speaker/output) — Bluetooth pe set karo
        ok2, sinks = self._run("pactl list short sinks", silent=True)
        if ok2:
            for line in sinks.splitlines():
                if "bluez" in line.lower():
                    sink_name = line.split()[1]
                    self._run(f"pactl set-default-sink {sink_name}", silent=True)
                    print(f"  [HFP] ✅ Default sink (output): {sink_name}")
                    break

        # Default SOURCE (mic/input) — Bluetooth HFP mic pe set karo
        ok3, sources = self._run("pactl list short sources", silent=True)
        if ok3:
            for line in sources.splitlines():
                if "bluez" in line.lower() and "monitor" not in line.lower():
                    source_name = line.split()[1]
                    self._run(f"pactl set-default-source {source_name}", silent=True)
                    print(f"  [HFP] ✅ Default source (mic): {source_name}")
                    break
            else:
                print("  [HFP] ⚠️  Bluetooth mic source nahi mila — ofono se SCO try karunga")

        print("  [HFP] 📞 Ready — mic aur speaker dono laptop se\n")

    def dial_via_ofono(self, number: str) -> bool:
        """
        ofono VoiceCallManager se seedha call karo.
        Yeh SCO audio automatically establish karta hai — mic + speaker dono kaam karte hain.
        """
        print(f"\n[ofono] Calling {number} via HFP VoiceCallManager...")
        ok, out = self._dbus(
            self._ofono_path,
            "org.ofono.VoiceCallManager.Dial",
            f'string:"{number}"',
            'string:"default"',
            silent=False
        )
        # dbus-send --print-reply success pe "object path" return karta hai stdout mein
        # returncode pe depend mat karo — output mein voicecall check karo
        call_started = "voicecall" in out.lower() or ok
        if call_started:
            # Sirf object path nikalo output se
            call_path = ""
            for line in out.splitlines():
                line = line.strip()
                if line.startswith("object path"):
                    call_path = line.replace("object path", "").strip().strip('"')
                    break
            print(f"  [ofono] ✅ Call initiated via ofono — SCO audio automatic hoga")
            print(f"  [ofono] 📞 Call object: {call_path or 'voicecall01'}")
            # SCO establish hone ka wait karo phir audio status check karo
            threading.Thread(target=self._check_sco_audio, daemon=True).start()
            return True
        else:
            print(f"  [ofono] ⚠️  ofono dial failed: {out}")
            print(f"  [ofono] Fallback: Android app ko command bhej raha hun")
            return False

    def _check_sco_audio(self):
        """Call dial ke 3 second baad SCO + audio status print karo"""
        time.sleep(3.0)
        print("\n[SCO Check] Call audio status check kar raha hun...")

        # 1. Active bluetooth card profile
        ok, cards = self._run("pactl list cards", silent=True)
        profile_active = "unknown"
        if ok:
            in_our_card = False
            for line in cards.splitlines():
                if self._card in line:
                    in_our_card = True
                if in_our_card and "Active Profile:" in line:
                    profile_active = line.split("Active Profile:")[-1].strip()
                    break
        print(f"  [SCO] 🎵 Active profile: {profile_active}")
        if "headset-head-unit" in profile_active:
            print("  [SCO] ✅ headset-head-unit ACTIVE — SCO link hai!")
        elif "audio-gateway" in profile_active:
            print("  [SCO] ⚠️  audio-gateway active — SCO link NAHI bana")
        else:
            print("  [SCO] ❓ Profile unknown/off")

        # 2. Bluetooth mic (bluez_input) available hai?
        ok2, sources = self._run("pactl list short sources", silent=True)
        bt_mic = None
        if ok2:
            for line in sources.splitlines():
                if "bluez" in line.lower() and "monitor" not in line.lower():
                    bt_mic = line.split()[1]
                    break
        if bt_mic:
            print(f"  [SCO] ✅ Bluetooth mic source: {bt_mic}")
        else:
            print("  [SCO] ❌ Bluetooth mic source (bluez_input) NAHI mila — mic kaam nahi karega")

        # 3. Bluetooth speaker (bluez sink) available hai?
        ok3, sinks = self._run("pactl list short sinks", silent=True)
        bt_sink = None
        if ok3:
            for line in sinks.splitlines():
                if "bluez" in line.lower():
                    bt_sink = line.split()[1]
                    break
        if bt_sink:
            print(f"  [SCO] ✅ Bluetooth speaker sink: {bt_sink}")
        else:
            print("  [SCO] ❌ Bluetooth speaker sink NAHI mila")

        # 4. Default source/sink kya hai?
        ok4, def_source = self._run("pactl get-default-source", silent=True)
        ok5, def_sink = self._run("pactl get-default-sink", silent=True)
        print(f"  [SCO] 🎤 Default mic (source): {def_source.strip()}")
        print(f"  [SCO] 🔊 Default speaker (sink): {def_sink.strip()}")

        # 5. Summary
        print()
        if "headset-head-unit" in profile_active and bt_mic:
            print("  [SCO] 🟢 RESULT: Mic + Speaker dono kaam karenge via Bluetooth HFP!")
        elif bt_mic:
            print("  [SCO] 🟡 RESULT: Mic mil gaya lekin profile galat hai — awaaz aa sakti hai")
        else:
            print("  [SCO] 🔴 RESULT: SCO link nahi bana — mic kaam nahi karega")
            print("  [SCO]    Fix: Phone screen pe call answer karo aur 'Bluetooth' select karo")
        print("PhoneLink> ", end="", flush=True)

    def deactivate_call_audio(self):
        """Call khatam hone par audio + mic wapas normal karo"""
        print("\n[HFP] Call khatam — audio restore kar raha hun...")
        time.sleep(0.5)

        # A2DP profile wapas
        self._run(
            f"pactl set-card-profile {self._card} a2dp-sink",
            silent=True
        )

        # Default source wapas laptop internal mic pe
        ok, sources = self._run("pactl list short sources", silent=True)
        if ok:
            for line in sources.splitlines():
                if "alsa_input" in line.lower() and "monitor" not in line.lower():
                    source_name = line.split()[1]
                    self._run(f"pactl set-default-source {source_name}", silent=True)
                    print(f"  [HFP] ✅ Mic wapas laptop pe: {source_name}")
                    break

        print("  [HFP] ✅ A2DP (music) mode restore hua\n")


# ─────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────

def get_paired_devices():
    try:
        result = subprocess.run(
            ['bluetoothctl', 'devices'], capture_output=True, text=True, check=True
        )
        devices = []
        for line in result.stdout.split('\n'):
            if line.startswith('Device'):
                parts = line.split(' ', 2)
                if len(parts) >= 3:
                    devices.append({'mac': parts[1], 'name': parts[2]})
        return devices
    except Exception as e:
        print(f"bluetoothctl error: {e}")
        return []


# ─────────────────────────────────────────────────────────────
#  BT Client
# ─────────────────────────────────────────────────────────────

class PhoneLinkBTClient:
    def __init__(self):
        self.sock = None
        self.connected = False
        self.receive_thread = None
        self.phone_mac = None
        self.hfp = None
        self._in_call = False

    def connect(self, address=None):
        if not address:
            devices = get_paired_devices()
            if not devices:
                print("No paired Bluetooth devices found.")
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

        self.phone_mac = address
        self.hfp = HFPAudioManager(address)

        # ── HFP modem setup PEHLE karo, RFCOMM baad mein ────────────
        self.hfp.setup_hfp()

        print(f"\nRFCOMM server se connect kar raha hun ({address})...")
        ports_to_try = [13] + list(range(1, 31))
        connected = False

        for port in ports_to_try:
            label = "preferred " if port == 13 else ""
            print(f"Trying {label}RFCOMM port {port}...")
            try:
                s = socket.socket(
                    socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM
                )
                s.settimeout(2.0)
                s.connect((address, port))
                try:
                    data = s.recv(1024).decode('utf-8', errors='ignore')
                    if "PHONELINK_READY" in data:
                        s.settimeout(None)
                        self.sock = s
                        self.connected = True
                        connected = True
                        print(f"Connected on port {port}!\n")
                        break
                    else:
                        print(f"Port {port}: active but not PhoneLink (likely HFP). Skipping...")
                        s.close()
                except socket.timeout:
                    print(f"Port {port}: no handshake. Skipping...")
                    s.close()
            except Exception:
                try:
                    s.close()
                except Exception:
                    pass

        if not connected:
            print("Failed to connect. Make sure PhoneLink app is running on phone.")
            return False

        self.receive_thread = threading.Thread(
            target=self._receive_loop, daemon=True
        )
        self.receive_thread.start()
        return True

    def _receive_loop(self):
        try:
            while self.connected:
                data = self.sock.recv(1024)
                if not data:
                    break
                msg = data.decode('utf-8')
                print(f"\n[Phone -> PC]: {msg}")
                try:
                    j = json.loads(msg)
                    if j.get("event") in ("call_ended", "hangup") and self._in_call:
                        self._in_call = False
                        threading.Thread(
                            target=self.hfp.deactivate_call_audio, daemon=True
                        ).start()
                except Exception:
                    pass
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

        if action == "dial":
            self._in_call = True

            # Pehle ofono se dial karo — SCO audio automatic hoga
            ofono_ok = self.hfp.dial_via_ofono(number)

            if not ofono_ok:
                # ofono fail hua — manual audio activate karo aur Android app ko bhejo
                print("[Dial] ofono fail — Android app ko dial command bhej raha hun...")
                threading.Thread(
                    target=self.hfp.activate_call_audio, daemon=True
                ).start()
                time.sleep(0.8)
                payload = {"action": action, "number": number}
                try:
                    self.sock.send(json.dumps(payload).encode('utf-8'))
                    print(f"Sent command: {action} {number}")
                except Exception as e:
                    print(f"Failed to send: {e}")
                    self.connected = False
            # ofono success: Android app ko sirf "call started" notify karo (optional)
            return

        payload = {"action": action, "number": number}
        try:
            self.sock.send(json.dumps(payload).encode('utf-8'))
            print(f"Sent command: {action} {number}")
        except Exception as e:
            print(f"Failed to send: {e}")
            self.connected = False

        if action == "hangup" and self._in_call:
            self._in_call = False
            time.sleep(0.5)
            threading.Thread(
                target=self.hfp.deactivate_call_audio, daemon=True
            ).start()

    def disconnect(self):
        self.connected = False
        if self.sock:
            self.sock.close()
            self.sock = None
        print("Disconnected.")


# ─────────────────────────────────────────────────────────────
#  Entry Point
# ─────────────────────────────────────────────────────────────

def main():
    print("=== PhoneLink Bluetooth Desktop Client ===")
    print("Call audio automatically routes to your PC via HFP.")
    print("==========================================")

    client = PhoneLinkBTClient()
    address = sys.argv[1] if len(sys.argv) > 1 else None

    if not client.connect(address):
        sys.exit(1)

    print("Commands:")
    print("  dial <number>  - Call karo (audio auto PC pe aayega)")
    print("  answer         - Incoming call receive karo")
    print("  hangup         - Call band karo")
    print("  exit           - Disconnect")

    try:
        while client.connected:
            cmd_input = input("\nPhoneLink> ").strip().split()
            if not cmd_input:
                continue
            cmd = cmd_input[0].lower()
            if cmd in ("exit", "quit"):
                break
            elif cmd == "dial":
                if len(cmd_input) > 1:
                    client.send_command("dial", cmd_input[1])
                else:
                    print("Usage: dial <number>")
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
