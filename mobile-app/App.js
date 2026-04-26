import React, { useState, useEffect, useCallback } from 'react';
import { StyleSheet, Text, View, TouchableOpacity, ScrollView, NativeModules, NativeEventEmitter, PermissionsAndroid, Platform } from 'react-native';
import * as Network from 'expo-network';

const { HttpServerModule, PhoneCallModule } = NativeModules;
const eventEmitter = new NativeEventEmitter(HttpServerModule);

export default function App() {
  const [ipAddress, setIpAddress] = useState('Loading...');
  const [isServerRunning, setIsServerRunning] = useState(false);
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

    const subscription = eventEmitter.addListener('onCallRequested', (event) => {
      const { number } = event;
      addLog(`Incoming call request for: ${number}`);
      makeCall(number);
    });

    return () => {
      subscription.remove();
    };
  }, [addLog]);

  const requestCallPermission = async () => {
    if (Platform.OS === 'android') {
      try {
        const granted = await PermissionsAndroid.request(
          PermissionsAndroid.PERMISSIONS.CALL_PHONE,
          {
            title: 'Phone Call Permission',
            message: 'This app needs access to make phone calls.',
            buttonNeutral: 'Ask Me Later',
            buttonNegative: 'Cancel',
            buttonPositive: 'OK',
          }
        );
        return granted === PermissionsAndroid.RESULTS.GRANTED;
      } catch (err) {
        console.warn(err);
        return false;
      }
    }
    return true;
  };

  const makeCall = async (number) => {
    const hasPermission = await requestCallPermission();
    if (hasPermission) {
      addLog(`Initiating call to: ${number}`);
      PhoneCallModule.makeCall(number);
    } else {
      addLog('Permission denied to make call.');
    }
  };

  const toggleServer = () => {
    if (isServerRunning) {
      HttpServerModule.stopServer();
      setIsServerRunning(false);
      addLog('Server stopped.');
    } else {
      HttpServerModule.startServer(5000);
      setIsServerRunning(true);
      addLog('Server started on port 5000.');
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
          <Text style={styles.label}>Server Status:</Text>
          <Text style={[styles.value, { color: isServerRunning ? '#4CAF50' : '#F44336' }]}>
            {isServerRunning ? 'RUNNING' : 'STOPPED'}
          </Text>
        </View>
      </View>

      <View style={styles.buttonContainer}>
        <TouchableOpacity 
          style={[styles.button, isServerRunning ? styles.stopButton : styles.startButton]} 
          onPress={toggleServer}
        >
          <Text style={styles.buttonText}>{isServerRunning ? 'Stop Server' : 'Start Server'}</Text>
        </TouchableOpacity>

        <TouchableOpacity style={[styles.button, styles.testButton]} onPress={testCall}>
          <Text style={styles.buttonText}>Test Call (9354785567)</Text>
        </TouchableOpacity>
      </View>

      <View style={styles.logContainer}>
        <Text style={styles.logTitle}>Recent Requests</Text>
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
    marginBottom: 30,
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
    padding: 20,
    marginBottom: 30,
    elevation: 3,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
  },
  infoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 10,
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
    gap: 15,
    marginBottom: 30,
  },
  button: {
    padding: 15,
    borderRadius: 10,
    alignItems: 'center',
    elevation: 2,
  },
  startButton: {
    backgroundColor: '#00B894',
  },
  stopButton: {
    backgroundColor: '#D63031',
  },
  testButton: {
    backgroundColor: '#0984E3',
  },
  buttonText: {
    color: '#FFFFFF',
    fontSize: 18,
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
