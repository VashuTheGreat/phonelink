import React, { useState, useEffect, useCallback } from 'react';
import { StyleSheet, Text, View, TouchableOpacity, ScrollView, NativeModules, NativeEventEmitter, PermissionsAndroid, Platform } from 'react-native';
import * as Network from 'expo-network';

const { HttpServerModule, PhoneCallModule, BluetoothServerModule } = NativeModules;
const httpEventEmitter = new NativeEventEmitter(HttpServerModule);
const btEventEmitter = new NativeEventEmitter(BluetoothServerModule);

export default function App() {
  const [ipAddress, setIpAddress] = useState('Loading...');
  const [isHttpServerRunning, setIsHttpServerRunning] = useState(false);
  const [isBTServerRunning, setIsBTServerRunning] = useState(false);
  const [btStatus, setBtStatus] = useState('disconnected');
  const [logs, setLogs] = useState([]);

  const addLog = useCallback((message) => {
    const timestamp = new Date().toLocaleTimeString();
    setLogs((prevLogs) => [`[${timestamp}] ${message}`, ...prevLogs].slice(0, 50));
  }, []);

  useEffect(() => {
    (async () => {
      const ip = await Network.getIpAddressAsync();
      setIpAddress(ip);
    })();

    // HTTP Events
    const httpSub = httpEventEmitter.addListener('onCallRequested', (event) => {
      const { number } = event;
      addLog(`[HTTP] Incoming call request for: ${number}`);
      makeCall(number);
    });

    // Bluetooth Events
    const btCmdSub = btEventEmitter.addListener('onBTCommandReceived', (event) => {
      const { action, number } = event;
      addLog(`[BT] Command received: ${action} ${number ? number : ''}`);
      if (action === 'dial' && number) {
        makeCall(number);
      } else if (action === 'answer') {
        answerCall();
      } else if (action === 'hangup') {
        hangupCall();
      }
    });

    const btStatusSub = btEventEmitter.addListener('onBTStatusChanged', (event) => {
      const { data } = event;
      setBtStatus(data);
    });

    const btLogSub = btEventEmitter.addListener('onBTLog', (event) => {
      const { data } = event;
      addLog(`[BT] ${data}`);
    });

    return () => {
      httpSub.remove();
      btCmdSub.remove();
      btStatusSub.remove();
      btLogSub.remove();
    };
  }, [addLog]);

  const requestPermissions = async () => {
    if (Platform.OS === 'android') {
      try {
        const granted = await PermissionsAndroid.requestMultiple([
          PermissionsAndroid.PERMISSIONS.CALL_PHONE,
          PermissionsAndroid.PERMISSIONS.ANSWER_PHONE_CALLS,
          PermissionsAndroid.PERMISSIONS.READ_PHONE_STATE,
          PermissionsAndroid.PERMISSIONS.BLUETOOTH_CONNECT,
          PermissionsAndroid.PERMISSIONS.BLUETOOTH_SCAN,
        ]);
        return granted['android.permission.CALL_PHONE'] === PermissionsAndroid.RESULTS.GRANTED;
      } catch (err) {
        console.warn(err);
        return false;
      }
    }
    return true;
  };

  const makeCall = async (number) => {
    const hasPermission = await requestPermissions();
    if (hasPermission) {
      addLog(`Initiating call to: ${number}`);
      PhoneCallModule.makeCall(number);
    } else {
      addLog('Permission denied to make call.');
    }
  };

  const answerCall = async () => {
    const hasPermission = await requestPermissions();
    if (hasPermission) {
      addLog('Answering incoming call');
      PhoneCallModule.answerCall();
    } else {
      addLog('Permission denied to answer call.');
    }
  };

  const hangupCall = async () => {
    const hasPermission = await requestPermissions();
    if (hasPermission) {
      addLog('Hanging up call');
      PhoneCallModule.hangupCall();
    } else {
      addLog('Permission denied to hangup call.');
    }
  };

  const toggleHttpServer = () => {
    if (isHttpServerRunning) {
      HttpServerModule.stopServer();
      setIsHttpServerRunning(false);
      addLog('HTTP Server stopped.');
    } else {
      HttpServerModule.startServer(5000);
      setIsHttpServerRunning(true);
      addLog('HTTP Server started on port 5000.');
    }
  };

  const toggleBTServer = async () => {
    await requestPermissions();
    if (isBTServerRunning) {
      BluetoothServerModule.stopServer();
      setIsBTServerRunning(false);
    } else {
      BluetoothServerModule.startServer();
      setIsBTServerRunning(true);
    }
  };

  const testCall = () => {
    makeCall('9354785567'); // Default test number
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>PhoneLink</Text>
        <Text style={styles.subtitle}>Direct Call Link</Text>
      </View>

      <View style={styles.statusCard}>
        <View style={styles.infoRow}>
          <Text style={styles.label}>Device IP:</Text>
          <Text style={styles.value}>{ipAddress}</Text>
        </View>
        <View style={styles.infoRow}>
          <Text style={styles.label}>HTTP Status:</Text>
          <Text style={[styles.value, { color: isHttpServerRunning ? '#4CAF50' : '#F44336' }]}>
            {isHttpServerRunning ? 'RUNNING' : 'STOPPED'}
          </Text>
        </View>
        <View style={styles.infoRow}>
          <Text style={styles.label}>BT Status:</Text>
          <Text style={[styles.value, { color: btStatus === 'connected' ? '#4CAF50' : btStatus === 'listening' ? '#FF9800' : '#F44336' }]}>
            {btStatus.toUpperCase()}
          </Text>
        </View>
      </View>

      <View style={styles.buttonContainer}>
        <TouchableOpacity 
          style={[styles.button, isHttpServerRunning ? styles.stopButton : styles.startButton]} 
          onPress={toggleHttpServer}
        >
          <Text style={styles.buttonText}>{isHttpServerRunning ? 'Stop HTTP Server' : 'Start HTTP Server'}</Text>
        </TouchableOpacity>

        <TouchableOpacity 
          style={[styles.button, isBTServerRunning ? styles.stopButton : styles.btButton]} 
          onPress={toggleBTServer}
        >
          <Text style={styles.buttonText}>{isBTServerRunning ? 'Stop BT Server' : 'Start BT Server'}</Text>
        </TouchableOpacity>

        <TouchableOpacity style={[styles.button, styles.testButton]} onPress={testCall}>
          <Text style={styles.buttonText}>Test Call (9354785567)</Text>
        </TouchableOpacity>
      </View>

      <View style={styles.logContainer}>
        <Text style={styles.logTitle}>Logs & Requests</Text>
        <ScrollView style={styles.scrollView}>
          {logs.length === 0 ? (
            <Text style={styles.noLogs}>No logs yet...</Text>
          ) : (
            logs.map((log, index) => (
              <Text key={index} style={styles.logEntry}>{log}</Text>
            ))
          )}
        </ScrollView>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F5F7FA',
    padding: 20,
    paddingTop: 60,
  },
  header: {
    marginBottom: 20,
    alignItems: 'center',
  },
  title: {
    fontSize: 32,
    fontWeight: 'bold',
    color: '#2D3436',
  },
  subtitle: {
    fontSize: 16,
    color: '#636E72',
    marginTop: 5,
  },
  statusCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: 15,
    padding: 15,
    marginBottom: 20,
    elevation: 3,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
  },
  infoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#F0F0F0',
  },
  label: {
    fontSize: 16,
    color: '#636E72',
    fontWeight: '600',
  },
  value: {
    fontSize: 16,
    color: '#2D3436',
    fontWeight: 'bold',
  },
  buttonContainer: {
    flexDirection: 'column',
    gap: 10,
    marginBottom: 20,
  },
  button: {
    padding: 12,
    borderRadius: 10,
    alignItems: 'center',
    elevation: 2,
  },
  startButton: {
    backgroundColor: '#00B894',
  },
  btButton: {
    backgroundColor: '#6C5CE7',
  },
  stopButton: {
    backgroundColor: '#D63031',
  },
  testButton: {
    backgroundColor: '#0984E3',
  },
  buttonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: 'bold',
  },
  logContainer: {
    flex: 1,
    backgroundColor: '#FFFFFF',
    borderRadius: 15,
    padding: 15,
    elevation: 2,
  },
  logTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#2D3436',
    marginBottom: 10,
    borderBottomWidth: 2,
    borderBottomColor: '#F0F0F0',
    paddingBottom: 5,
  },
  scrollView: {
    flex: 1,
  },
  logEntry: {
    fontSize: 14,
    color: '#2D3436',
    paddingVertical: 5,
    borderBottomWidth: 1,
    borderBottomColor: '#F9F9F9',
  },
  noLogs: {
    textAlign: 'center',
    color: '#B2BEC3',
    marginTop: 20,
  }
});
