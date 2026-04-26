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
        self.laptop_mic = None
        self.mic_loopback_id = None

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

    def _get_active_profile(self):
        _, cards = self._run("pactl list cards", silent=True)
        in_card = False
        for line in cards.splitlines():
            if self._card in line:
                in_card = True
            if in_card and "Active Profile:" in line:
                return line.split("Active Profile:")[-1].strip()
        return "unknown"

    def setup_hfp(self):
        """ofono modem power on + online karo."""
        print("\n[HFP] ofono modem setup kar raha hun...")

        for prop, val in [("Powered", "true"), ("Online", "true")]:
            ok, out = self._dbus(
                self._ofono_path, "org.ofono.Modem.SetProperty",
                f'string:"{prop}"', f'variant:boolean:{val}'
            )
            label = "ON" if val == "true" else "OFF"
            if ok:
                print(f"  [HFP] ✅ Modem {prop} {label}")
            else:
                print(f"  [HFP] ⚠️  Modem {prop} failed (may already be): {out}")
            time.sleep(0.8)

        # Modem properties print karo
        self._dbus(self._ofono_path, "org.ofono.Modem.GetProperties", silent=False)

        # Bluetooth reconnect — WirePlumber ko sync karne do
        print("  [HFP] Bluetooth reconnect kar raha hun (WirePlumber sync ke liye)...")
        self._run(f"bluetoothctl disconnect {self.phone_mac}", silent=True)
        time.sleep(1.5)
        self._run(f"bluetoothctl connect {self.phone_mac}", silent=True)
        time.sleep(2.0)

        profile = self._get_active_profile()
        print(f"  [HFP] 🎵 Current profile after reconnect: {profile}")

    def dial_via_ofono(self, number: str) -> bool:
        """ofono VoiceCallManager se call karo. Answer pe SCO auto-activate hoga."""
        print(f"\n[ofono] Calling {number} via HFP VoiceCallManager...")
        ok, out = self._dbus(
            self._ofono_path,
            "org.ofono.VoiceCallManager.Dial",
            f'string:"{number}"',
            'string:"default"',
            silent=False
        )
        call_started = "voicecall" in out.lower() or ok
        if call_started:
            call_path = ""
            for line in out.splitlines():
                line = line.strip()
                if line.startswith("object path"):
                    call_path = line.replace("object path", "").strip().strip('"')
                    break
            call_path = call_path or f"{self._ofono_path}/voicecall01"
            print(f"  [ofono] ✅ Call initiated — {call_path}")
            print(f"  [ofono] 📞 Phone ring ho rahi hai... answer hone par audio activate hoga")
            threading.Thread(
                target=self._monitor_call_state,
                args=(call_path,),
                daemon=True
            ).start()
            return True
        else:
            print(f"  [ofono] ⚠️  ofono dial failed: {out}")
            return False

    def _monitor_call_state(self, call_dbus_path: str):
        """Polling se call state monitor karo. active hone pe SCO activate karo."""
        print(f"  [Monitor] Call state monitor shuru — answer hone ka wait kar raha hun...")
        prev_state = "alerting"
        for _ in range(30):  # max 60 sec
            time.sleep(2.0)
            _, out = self._dbus(
                call_dbus_path,
                "org.ofono.VoiceCall.GetProperties",
                silent=True
            )
            state = "unknown"
            if 'string "active"' in out:
                state = "active"
            elif 'string "alerting"' in out:
                state = "alerting"
            elif 'string "disconnected"' in out:
                state = "disconnected"

            if state == "active" and prev_state != "active":
                print(f"\n  [Monitor] ✅ Call ANSWER hua! SCO audio activate kar raha hun...")
                self._activate_sco_now(call_dbus_path)
                return
            elif state == "disconnected":
                print(f"\n  [Monitor] 📵 Call khatam hua")
                return
            prev_state = state

        print(f"\n  [Monitor] ⏱️  Timeout — 60 sec mein answer nahi hua")

    def _activate_sco_now(self, call_dbus_path: str = None):
        """
        Call answer hone ke baad:
        1. ofono AcquireVoice → SCO channel open
        2. WirePlumber khud profile switch karta hai
        3. Agar nahi kiya → pactl force
        4. Laptop mic → BT speaker loopback (caller sun sake)
        5. BT mic → default source (hum sun sake)
        """

        # Laptop mic save karo (call end pe restore ke liye)
        _, src = self._run("pactl get-default-source", silent=True)
        self.laptop_mic = src.strip()

        # Step 1: ofono AcquireVoice — SCO channel explicitly open karo
        if call_dbus_path:
            print("  [SCO] ofono AcquireVoice call kar raha hun...")
            ok, out = self._dbus(
                call_dbus_path,
                "org.ofono.VoiceCall.AcquireVoice",
                silent=False
            )
            acquired = ok or bool(out.strip())
            print(f"  [SCO] AcquireVoice: {'✅ success' if acquired else '⚠️  no response'}")
            time.sleep(2.0)  # SCO establish hone do

        # Step 2: Profile check — WirePlumber ne switch kiya?
        profile = self._get_active_profile()
        print(f"  [SCO] 🎵 Profile after AcquireVoice: {profile}")

        # Step 3: Agar abhi bhi audio-gateway/off → pactl force karo
        if "headset-head-unit" not in profile:
            print("  [SCO] pactl se headset-head-unit force kar raha hun...")
            self._run(f"pactl set-card-profile {self._card} headset-head-unit", silent=True)
            time.sleep(1.0)
            profile = self._get_active_profile()
            print(f"  [SCO] 🎵 Profile after force: {profile}")

        # Step 4: BT sink (speaker) dhundho
        _, sinks = self._run("pactl list short sinks", silent=True)
        bt_sink = None
        for line in sinks.splitlines():
            if "bluez" in line.lower():
                bt_sink = line.split()[1]
                break

        # Step 5: BT source (mic) dhundho
        _, sources = self._run("pactl list short sources", silent=True)
        bt_mic = None
        for line in sources.splitlines():
            if "bluez" in line.lower() and "monitor" not in line.lower():
                bt_mic = line.split()[1]
                break

        # Step 6: Default sink → BT speaker (hum sune)
        if bt_sink:
            self._run(f"pactl set-default-sink {bt_sink}", silent=True)
            print(f"  [SCO] ✅ BT Speaker: {bt_sink}")
        else:
            print("  [SCO] ❌ BT speaker nahi mila")

        # Step 7: Default source → BT mic (caller hume sune via HFP mic)
        if bt_mic:
            self._run(f"pactl set-default-source {bt_mic}", silent=True)
            print(f"  [SCO] ✅ BT Mic: {bt_mic}")
        else:
            # Fallback: laptop mic → BT speaker loopback
            print("  [SCO] ⚠️  BT mic nahi mila — laptop mic loopback try kar raha hun...")
            if self.laptop_mic and bt_sink:
                ok, out = self._run(
                    f"pactl load-module module-loopback "
                    f"source={self.laptop_mic} sink={bt_sink} latency_msec=20",
                    silent=True
                )
                if ok:
                    self.mic_loopback_id = out.strip()
                    print(f"  [SCO] 🎤✅ Laptop mic loopback ON → caller sun sakta hai!")
                else:
                    print(f"  [SCO] ❌ Loopback fail: {out}")

        # Final status
        _, def_src = self._run("pactl get-default-source", silent=True)
        _, def_snk = self._run("pactl get-default-sink", silent=True)
        print(f"\n  [SCO] 🎤 Mic  : {def_src.strip()}")
        print(f"  [SCO] 🔊 Sink : {def_snk.strip()}")

        if (bt_mic or self.mic_loopback_id) and bt_sink:
            print("  [SCO] 🟢 Audio ready — dono taraf awaaz aani chahiye!")
        else:
            print("  [SCO] 🔴 Audio setup incomplete")
        print("PhoneLink> ", end="", flush=True)

    def deactivate_call_audio(self):
        """Call khatam — audio + mic restore karo."""
        print("\n[HFP] Call khatam — audio restore kar raha hun...")
        time.sleep(0.5)

        if self.mic_loopback_id:
            self._run(f"pactl unload-module {self.mic_loopback_id}", silent=True)
            self.mic_loopback_id = None
            print("  [HFP] 🎤❌ Mic loopback OFF")

        self._run(f"pactl set-card-profile {self._card} a2dp-sink", silent=True)

        if self.laptop_mic:
            self._run(f"pactl set-default-source {self.laptop_mic}", silent=True)
            print(f"  [HFP] ✅ Mic wapas laptop pe: {self.laptop_mic}")
        else:
            _, sources = self._run("pactl list short sources", silent=True)
            for line in sources.splitlines():
                if "alsa_input" in line.lower() and "monitor" not in line.lower():
                    self._run(f"pactl set-default-source {line.split()[1]}", silent=True)
                    print(f"  [HFP] ✅ Mic wapas: {line.split()[1]}")
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
        self.hfp.setup_hfp()

        print(f"\nRFCOMM server se connect kar raha hun ({address})...")
        ports_to_try = [13] + list(range(1, 31))

        for port in ports_to_try:
            label = "preferred " if port == 13 else ""
            print(f"Trying {label}RFCOMM port {port}...")
            try:
                s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
                s.settimeout(2.0)
                s.connect((address, port))
                try:
                    data = s.recv(1024).decode('utf-8', errors='ignore')
                    if "PHONELINK_READY" in data:
                        s.settimeout(None)
                        self.sock = s
                        self.connected = True
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

        if not self.connected:
            print("Failed to connect. Make sure PhoneLink app is running on phone.")
            return False

        # RFCOMM connect ke baad profile check
        profile = self.hfp._get_active_profile()
        print(f"[HFP] Profile after RFCOMM connect: {profile}")
        if "audio-gateway" in profile:
            print("[HFP] ℹ️  audio-gateway active — call answer karne par SCO se fix hoga")

        threading.Thread(target=self._receive_loop, daemon=True).start()
        return True

    def _receive_loop(self):
        try:
            while self.connected:
                try:
                    data = self.sock.recv(1024)
                    if not data:
                        self.connected = False
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
                except socket.timeout:
                    continue
                except Exception:
                    self.connected = False
                    break
        finally:
            self.connected = False

    def send_command(self, action, number=""):
        if action == "dial":
            self._in_call = True
            ofono_ok = self.hfp.dial_via_ofono(number)
            if not ofono_ok:
                print("[Dial] ofono fail — Android app fallback...")
                if self.sock and self.connected:
                    try:
                        self.sock.send(json.dumps({"action": action, "number": number}).encode())
                        print(f"Sent to Android: dial {number}")
                    except Exception as e:
                        print(f"Android send failed: {e}")
                else:
                    print("Android app bhi connected nahi hai.")
            return

        if not (self.connected and self.sock):
            print("Not connected to Android App.")
            return

        try:
            self.sock.send(json.dumps({"action": action, "number": number}).encode())
            print(f"Sent command: {action} {number}")
        except Exception as e:
            print(f"Failed to send: {e}")
            self.connected = False

        if action == "hangup" and self._in_call:
            self._in_call = False
            time.sleep(0.5)
            threading.Thread(target=self.hfp.deactivate_call_audio, daemon=True).start()

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
    print("==========================================\n")

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
        while True:
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
