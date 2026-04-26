# PhoneLink

A system that lets your laptop trigger phone calls on your Android device over WiFi.

## Project Structure

```
phoneLinkLinux/
├── mobile-app/               # React Native Expo app (Development Build)
│   ├── App.js                # Main UI + server logic
│   ├── app.json              # Expo config (permissions, package name)
│   ├── index.js              # App entry point
│   └── android/
│       └── app/src/main/java/com/phonelink/
│           ├── MainApplication.kt    # Registers PhoneLinkPackage
│           ├── PhoneCallModule.kt    # Native module: makes phone calls
│           ├── HttpServerModule.kt   # Native module: HTTP server on port 5000
│           └── PhoneLinkPackage.kt   # Registers both modules with React Native
└── python-server/            # Python laptop-side script
    ├── server.py             # CLI script to send call requests
    ├── requirements.txt      # Python dependencies
    └── .venv/                # Python virtual environment
```

## Architecture

```
[Laptop - Python]  →  GET http://PHONE_IP:5000/9354785567  →  [Android App]
                                                                    ↓
                                                           Intent.ACTION_CALL
                                                                    ↓
                                                            📞 Phone Call Initiated
```

---

## Setup & Usage

### Step 1: Build & Run the Android App

> **Requirements:** Android device with USB debugging enabled, Android SDK installed.

```bash
cd mobile-app

# Install dependencies (if not done)
npm install

# Build and run on Android device
npx expo run:android
```

On first launch:
1. **Grant the `CALL_PHONE` permission** when prompted.
2. Note the **Device IP** shown on screen.
3. Tap **"Start Server"** to begin listening on port 5000.

---

### Step 2: Run the Python Server (Laptop)

```bash
cd python-server

# Activate the virtual environment
source .venv/bin/activate

# Run the script
python server.py
```

**Interactive mode:**
```
Enter Phone IP: 192.168.1.42
Enter phone number to call (or 'exit' to quit): 9354785567
Sending request to http://192.168.1.42:5000/9354785567...
Successfully sent call request.
```

**CLI one-liner:**
```bash
python server.py call 9354785567
# (will prompt for phone IP)
```

---

## Network Requirements

- Both laptop and phone must be on the **same WiFi network**
- OR use ADB port forwarding for USB debugging:

```bash
adb reverse tcp:5000 tcp:5000
# Then use 127.0.0.1 as the phone IP
```

---

## Permissions Used

| Permission | Purpose |
|---|---|
| `CALL_PHONE` | Directly initiate calls without user confirmation |
| `INTERNET` | Allow the in-app HTTP server to receive connections |

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `Connection refused` | Make sure the server is started in the app, and both devices are on the same WiFi |
| `Permission denied` | Go to Android Settings → Apps → PhoneLink → Permissions → Phone → Allow |
| Call opens dialer instead of calling | Grant `CALL_PHONE` permission |
| Port 5000 already in use | Restart the app |

---

## How It Works

1. The **Android app** runs a native Java `ServerSocket` on port 5000.
2. When a GET request arrives at `http://PHONE_IP:5000/NUMBER`, it extracts the number from the URL path.
3. It fires an event to React Native via `RCTDeviceEventEmitter`.
4. React Native calls the `PhoneCallModule.makeCall(number)` native method.
5. The native module fires an `Intent.ACTION_CALL` intent, directly initiating the call.
