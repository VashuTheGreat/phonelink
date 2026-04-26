import requests
import sys

def make_call(phone_ip, number):
    url = f"http://{phone_ip}:5000/{number}"
    try:
        print(f"Sending request to {url}...")
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            print("Successfully sent call request.")
        else:
            print(f"Error: Phone returned status code {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"Error: Could not reach the phone. Make sure it's on the same network and the server is running.")
        print(f"Details: {e}")

def main():
    if len(sys.argv) > 1:
        # CLI Mode: call <number>
        if sys.argv[1] == "call" and len(sys.argv) > 2:
            phone_ip = input("Enter Phone IP: ").strip()
            make_call(phone_ip, sys.argv[2])
            return
        elif len(sys.argv) == 2:
            # Maybe just the number was passed
            phone_ip = input("Enter Phone IP: ").strip()
            make_call(phone_ip, sys.argv[1])
            return

    # Interactive Mode
    phone_ip = input("Enter Phone IP: ").strip()
    while True:
        number = input("\nEnter phone number to call (or 'exit' to quit): ").strip()
        if number.lower() == 'exit':
            break
        if number:
            make_call(phone_ip, number)

if __name__ == "__main__":
    main()
