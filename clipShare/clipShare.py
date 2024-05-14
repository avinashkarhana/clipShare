from time import sleep
import pyclip
import argparse
import socketio as python_socketio
import threading
import socket
import hashlib
import random
from datetime import datetime
import netifaces as ni
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, disconnect
from zeroconf import Zeroconf, ServiceBrowser, ServiceInfo, ServiceListener
import base64
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad,unpad
from Crypto.Random import get_random_bytes
from pyngrok import ngrok
import os
import requests
import logging

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.template_folder = f'{os.path.dirname(os.path.realpath(__file__))}/web-interface/templates'
app.static_folder = f'{os.path.dirname(os.path.realpath(__file__))}/web-interface/static'

sio = python_socketio.Client(ssl_verify=False)
socketio = SocketIO(app)

last_copied_data = ''
shared_text=''
server_port = None
server_ip = None
server_name = 'clipShare'
server_clipboard_thread_started = False
QUITTING = False
DEBUG = False
ADVERTISE_SERVER = False
SERVE_ON_NGROK_TUNNEL = False
passcode = '1234'
client_authenticated_with_server = False
encryption_password = '1234567890123456'
public_url = ''
tcp_over_https = False

# Get Current working directory
current_working_directory = os.getcwd()

USAAGE_STRING = f"""
Usage: newClipShare.py [-h] [-s [SERVER_PORT_NUMER]] [-c SERVER_IP:SERVER_PORT_NUMBER] [-d]

Options:
    -h, --help                     Show this help message and exit
    -s, --server [SERVER_PORT_NUMER], --server [SERVER_PORT_NUMER]
                                   Run as server on the specified port.
    -c, --client SERVER_IP:SERVER_PORT_NUMBER, --client SERVER_IP:SERVER_PORT_NUMBER
                                   Run as client, specify server IP and port.
    -t, --serve-on-ngrok-tunnel    Enable Serve on ngrok tunnel. This option requires ngrok authtoken to be present in {current_working_directory}/ngrok-auth-token.txt
    -a, --advertise                Enable Advertising server on the local network.
    -n, --name                     Name of the server to be advertised.
    -p, --passcode                 Passcode for authentication.
    -ep, --encryption-password     Encryption password for data transfer.
    -toh, --tcp-over-https         Enable TCP over HTTPS for ngrok tunnel.
    -d, --debug                    Enable debug mode.

Examples:
    python newClipShare.py -s 5000
    python newClipShare.py -c 192.168.0.1:8080
    python newClipShare.py -s 5000 -d
    python newClipShare.py -c -d
"""

##############################################################################################################
# Encryption Code
##############################################################################################################

def getMd5(string_data):
    string_data = str(string_data)
    result = hashlib.md5(string_data.encode('utf-8')).hexdigest()
    return result

def encrypt(raw):
    raw = pad(raw.encode(),16)
    iv_bytes = get_random_bytes(16)
    key = getMd5(encryption_password)
    cipher = AES.new(key.encode('utf-8'), AES.MODE_CBC, iv_bytes)
    encrypted_data = cipher.encrypt(raw)
    encrypted_data = base64.b64encode(encrypted_data).decode("utf-8", "ignore")
    iv_base64 = base64.b64encode(iv_bytes).decode("utf-8", "ignore")
    return f"{encrypted_data}${iv_base64}"

def decrypt(encypted_data):
    enc,iv = encypted_data.split('$')
    enc = base64.b64decode(enc)
    iv = base64.b64decode(iv)
    key = getMd5(encryption_password)
    cipher = AES.new(key.encode('utf-8'), AES.MODE_CBC, iv)
    try:
        decrypted_data = unpad(cipher.decrypt(enc),16)
        decrypted_data = decrypted_data.decode("utf-8", "ignore")
        return decrypted_data
    except:
        print('Decryption failed. Please check encryption password.')


##############################################################################################################
# Server Code
##############################################################################################################
authenticated_clients = []

@socketio.on('disconnect', namespace='/')
def on_disconnect():
    global authenticated_clients
    found_client = False
    for client in authenticated_clients:
        if client['clientId'] == request.sid:
            found_client = True
            authenticated_clients.remove(client)
            print(f'#> Client {request.sid} disconnected.')
            break
    if not found_client:
        print(f'#> Client {request.sid} disconnected without authentication.')

@socketio.on('authentication_from_client', namespace='/')
def auth_request_from_client(data):
    global authenticated_clients
    if str(data.get('passcode')) == str(passcode):
        md5_hash = hashlib.md5(str(random.randint(0, 100000000)).encode()).hexdigest()
        emit('authentication_to_client', {'success': True, 'token': md5_hash, 'msg': 'Pass this token along all further requests'}, broadcast=False)
        for client in authenticated_clients:
            if client['clientId'] == request.sid:
                authenticated_clients.remove(client)
        now_time = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        authenticated_clients.append({ "clientId": request.sid, "hash": md5_hash, "ip": request.remote_addr, "connection_time": now_time })
        print(f'#> Client {request.sid} from {request.remote_addr} authenticated successfully at {now_time}.')
    else:
        print(f'#> Client {request.sid} authentication failed. Disconnecting...')
        emit('authentication_to_client', {'success': False, 'msg': 'Authentication Failed due to inavlid passcode!'}, broadcast=False)
        disconnect(request.sid)

@socketio.on('connect', namespace='/')
def on_connect():
    print(f'#> Client Connection {request.sid}')
    for client in authenticated_clients:
        if client['clientId'] == request.sid:
            socketio.emit('clipboard_data_to_clients', {'clipboard_data': ''}, room=client['clientId'], namespace='/')
            authenticated_clients.remove(client)
    global server_clipboard_thread_started
    if not server_clipboard_thread_started:
        start_server_clipboard_thread()
    socketio.emit('authenticate', {'action': 'initiate_auth', 'msg': 'Initiate Authentication!'}, room=request.sid, namespace='/')
    print(f'#> Asked Client {request.sid} to start authentication.')

@socketio.on('clipboard_data_to_server', namespace='/')
def on_clipboard_data(data):
    if not is_client_authenticated(request.sid, data.get('token')):
        for client in authenticated_clients:
            if client['clientId'] != request.sid:
                emit('authenticate', {'success': False, 'msg': 'Authentication Failed! Authenticate again.'}, room=client['clientId'])
        disconnect(request.sid)
        return
    global last_copied_data
    global shared_text
    received_clipboard_data = data.get('clipboard_data')
    received_clipboard_data = decrypt(received_clipboard_data)
    if received_clipboard_data:
        if last_copied_data != received_clipboard_data:
            pyclip.copy(received_clipboard_data)
            if DEBUG:
                print(f'Copied data received from client {request.sid}: {received_clipboard_data}')
            shared_text = received_clipboard_data
            received_clipboard_data = encrypt(received_clipboard_data)
            emit('clipboard_data_to_clients', {'clipboard_data': received_clipboard_data}, broadcast=True)

def advertise_server():
    # Get the IP address of the local machine
    for interface in ni.interfaces():
        try:
            server_ip = ni.ifaddresses(interface)[ni.AF_INET][0]['addr']
            if server_ip != '' and server_ip != '127.0.0.1':
                break
        except:
            pass
    if server_ip == '':
        print("\n# Couldn't find a valid IP address for the server.")
        exit()
    
    service_name = f'_{server_name}._clipShare._tcp.local.'
    # Set up the service info
    service_info = ServiceInfo(
        "_clipShare._tcp.local.",  # Service type
        service_name,  # Service name
        addresses=[socket.inet_aton(server_ip)],
        port=server_port,
        properties={
            "port": str(server_port),
            "name": server_name,
            "server_ip": server_ip
        },
    )

    # Create and register the Zeroconf object
    zeroconf = Zeroconf()
    zeroconf.register_service(service_info)
    print(f"# Server advertised at {server_ip}:{server_port} as {service_name}")
    while True:
        if not ADVERTISE_SERVER or QUITTING:
            print("\n# Server unadvertised.")
            break
    zeroconf.unregister_service(service_info)
    zeroconf.close()

def is_client_authenticated(sid, token):
    global authenticated_clients
    for client in authenticated_clients:
        if client['clientId'] == sid and client['hash'] == token:
            return True
    return False

def start_server_clipboard_thread():
    global server_clipboard_thread_started
    def server_clipboard_thread():
        global last_copied_data
        global shared_text
        print("\n# Server Clipboard thread started.")
        while True:
            if QUITTING:
                print("\n# Server Clipboard thread stopped.")
                break
            data = pyclip.paste().decode('utf-8')
            data = data.strip()
            if data != last_copied_data and len(data)>0:
                if DEBUG:
                    print("Sending data to clients:", data)
                shared_text = data
                last_copied_data = data
                data = encrypt(data)
                for client in authenticated_clients:
                    socketio.emit('clipboard_data_to_clients', {'clipboard_data': data}, room=client['clientId'], namespace='/')
            sio.sleep(1)
    try:
        thread = threading.Thread(target=server_clipboard_thread, daemon=True)
        thread.start()
        server_clipboard_thread_started = True
    except (KeyboardInterrupt, SystemExit):
        global QUITTING
        QUITTING = True
        print('\n# Received keyboard interrupt, quitting...')
        exit()

def get_shortened_url(url):
    # Make a request to bitly.ws to shorten the URL
    shortne_service_url = f"https://shorter.me/page/shorten"
    response = requests.post(shortne_service_url, data={'url': url})
    if response.status_code == 200:
        shortened_url = response.json()['data']
        print(f' * Shortened URL: {shortened_url}')

def run_server():
    global ADVERTISE_SERVER
    global QUITTING
    global server_port
    global server_name
    global public_url
    global SERVE_ON_NGROK_TUNNEL
    print('\n# Starting server...')
    if ADVERTISE_SERVER:
        threading.Thread(target=advertise_server, daemon=True).start()
    if SERVE_ON_NGROK_TUNNEL:
        ngrok_public = ngrok.connect(server_port)
        public_url = ngrok_public.public_url
        print(' * NGROK tunnel "{}" -> "http://127.0.0.1:{}/"'.format(public_url, server_port))
        app.config['BASE_URL'] = public_url
        get_shortened_url(public_url)

    socketio.run(app, host='0.0.0.0', port=server_port)
    ADVERTISE_SERVER = False
    QUITTING = True
    print("\n# Server stopped.")
    if SERVE_ON_NGROK_TUNNEL:
        ngrok.disconnect(public_url)
        ngrok.kill()

def act_as_server():
    run_server()


##############################################################################################################
# Web Client Code
##############################################################################################################
@app.route('/')
def index():
    return render_template('index.html', server_ip=server_ip, server_port=server_port, server_name=server_name)


##############################################################################################################
# Client Code
##############################################################################################################
authenticated_server_info = {
    'token': '',
    'server_ip': '',
    'server_port': '',
    'passcode': '',
    'server_name': ''
}

@sio.on('authenticate', namespace='/')
def on_authenticate_with_server(data):
    global client_authenticated_with_server
    if data.get('action') == 'initiate_auth':
        client_authenticated_with_server = False
        print('\n# Server asked to initiate authentication')
        sleep(3)
        start_authentication_to_server()
    elif data.get('success') == False:
        client_authenticated_with_server = False
        print('Halting client')
        print(data.get('msg'))
        # ask if user wants to try again or quit
        user_option = input('Try again? (y/n): ')
        if QUITTING:
            exit()
        if user_option.lower() == 'y':
            start_authentication_to_server(data.get('msg'))
        else:
            exit()

@sio.on('clipboard_data_to_clients', namespace='/')
def on_clipboard_data(data):
    global last_copied_data
    global shared_text
    last_copied_data = data.get('clipboard_data')
    last_copied_data = decrypt(last_copied_data)
    if last_copied_data:
        if DEBUG:
            print(f'Copied data received from server: {last_copied_data}')
        shared_text=last_copied_data
        pyclip.copy(last_copied_data)

@sio.on('authentication_to_client', namespace='/')
def on_authentication_from_server(data):
    global authenticated_server_info
    global client_authenticated_with_server
    if data.get('success') == True:
        authenticated_server_info['token'] = data.get('token')
        authenticated_server_info['server_ip'] = server_ip
        authenticated_server_info['server_port'] = server_port
        authenticated_server_info['passcode'] = passcode
        authenticated_server_info['server_name'] = server_name
        server_address = ''
        if authenticated_server_info.get('server_port'):
            server_address = f'{authenticated_server_info.get("server_ip")}:{authenticated_server_info.get("server_port")}'
        else:
            server_address = f'{authenticated_server_info.get("server_ip")}'
        print(f'#> Authentication with Server {authenticated_server_info.get("server_name")} ({server_address}) successful.')
        client_authenticated_with_server = True
    else:
        client_authenticated_with_server = False
        print('\n#> Server authentication failed.')
        user_option = input('Try again? (y/n): ')
        if QUITTING:
            exit()
        if user_option.lower() == 'y':
            start_authentication_to_server(data.get('msg'))
        else:
            exit()

def start_authentication_to_server(msg=None):
    global passcode
    if not passcode or passcode == '' or passcode == '1234':
        if msg:
            print(f'Server: {msg}')
        userInp = input('\nDo you want to continue with default passcode (1234)? (y/n): ')
        if QUITTING:
            exit()
        if userInp.lower() == 'n':
            passcode = input('Enter passcode: ')
            if QUITTING:
                exit()
        else:
            passcode = '1234'
    if msg:
        passcode = input(f'Server: {msg}\nEnter passcode: ')
        if QUITTING:
            exit()
    try:
        sio.emit('authentication_from_client', {'passcode': passcode}, namespace='/')
    except:
        if tcp_over_https:
            server_url = f'https://{server_ip}:{server_port}' if server_port else f'https://{server_ip}'
        else:
            server_url = f'http://{server_ip}:{server_port}' if server_port else f'http://{server_ip}'
        connect_to_server(server_url)
        sio.emit('authentication_from_client', {'passcode': passcode}, namespace='/')
        print("# Sent Authentication passcode")

def connect_to_server(server_url):
    try:
        sio.connect(server_url, namespaces=['/'])
    except python_socketio.exceptions.ConnectionError as e:
        if 'Connection refused'in str(e):
            print(f'#> Connection to server {server_ip}:{server_port} refused. Retrying...')
            sleep(3)
            connect_to_server(server_url)
        elif str(e) == 'Already connected':
            return
    except Exception as e:
            if 'Client is not in a disconnected state' in str(e):
                sio.disconnect()
                sleep(3)
                print("Reconnecting to server...")
                connect_to_server(server_url)
                sleep(3)
            else:
                print(f'Exception:\n {e}')

def run_client():
    global QUITTING
    global tcp_over_https
    server_url = ''
    if tcp_over_https:
        server_url = f'https://{server_ip}:{server_port}' if server_port else f'https://{server_ip}'
    else:
        server_url = f'http://{server_ip}:{server_port}' if server_port else f'http://{server_ip}'
    print(f'\n# Connecting to server {server_url}.')
    connect_to_server(server_url)

    def client_clipboard_thread():
        global last_copied_data
        while True:
            if QUITTING:
                sio.disconnect()
                print('\n# Client disconnected from server.')
                print('\n# Stopped client clipboard thread...')
                break
            data = pyclip.paste().decode('utf-8')
            if data != last_copied_data and client_authenticated_with_server:
                connect_to_server(server_url)
                last_copied_data = data
                data = encrypt(data)
                sio.emit('clipboard_data_to_server', {'token': authenticated_server_info.get('token'), 'clipboard_data': data }, namespace='/')
            sio.sleep(1)
        return

    try:
        thread = threading.Thread(target=client_clipboard_thread, daemon=True)
        thread.start()
        while True:
            if QUITTING:
                break
            thread.join(1)
    except (KeyboardInterrupt, SystemExit):
        sio.disconnect()
        QUITTING = True
        print('\n# Received keyboard interrupt')
        print('\n# Client disconnected from server.')
        print('\n# Quitting...')
        exit()

class MyListener(ServiceListener):
    def __init__(self):
        self.services = {}

    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name)
        self.services[name] = info

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name)
        self.services[name] = info

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name)
        self.services[name] = info

def get_list_of_local_servers(scan_time=25):
    listener = MyListener()
    zeroconf = Zeroconf()
    # Start browsing for services
    browser = ServiceBrowser(zeroconf, '_clipShare._tcp.local.', listener)

    # Wait for 25 seconds (you can adjust the time if needed)
    try:
        for i in range(scan_time):
            if i % 5 == 0:
                print(f"Scanning for local servers for {scan_time-i}... ")
            sleep(1)
    except KeyboardInterrupt:
        print('\n# Stopped scanning for local servers.')
    # Stop browsing after 25 seconds
    zeroconf.close()

    # Print the IP:Port of services found
    serviceList = []
    for name, info in listener.services.items():
        ip = info.properties[b'server_ip'].decode('utf-8')
        port = info.port
        serviceList.append({'name': name, 'ip': ip, 'port': port})
    return serviceList

def scan_for_local_servers():
    global server_ip
    global server_port
    localServerList = []
    localServerList = get_list_of_local_servers()
    if len(localServerList) == 0:
        print("#No local servers found.\n")
        user_option = input('Try again later? y/n: ')
        if QUITTING:
            exit()
        if user_option.lower() == 'y':
            scan_for_local_servers()
        else:
            print('Quitting...')
            exit()
    else:
        print('#Choose a server to connect to:')
        for i in range(len(localServerList)):
            print(f'{i+1}. {localServerList[i].get("name")} {localServerList[i].get("ip")}:{localServerList[i].get("port")}')
        user_option = input('\nEnter option: ')
        if QUITTING:
            exit()
        if user_option.isdigit():
            user_option = int(user_option)
            if user_option >= len(localServerList):
                server_ip = localServerList[user_option-1].get('ip')
                server_port = localServerList[user_option-1].get('port')
            else:
                print('Invalid option. Quitting...')
                exit()

def act_as_client():
    global server_ip
    global server_port
    global passcode
    global encryption_password
    global tcp_over_https

    if not server_ip or not server_port:
        if not server_ip:
            print('Client Mode requires server IP.')
            # ask user if they want to enter server IP or scan for local servers using option 1,2
            user_option = input('Choose an option:\n1. Enter server IP\n2. Scan for local servers\nEnter option: ')
            if QUITTING:
                exit()
            if user_option == '1':
                server_ip = input('Enter server IP: ')
                if QUITTING:
                    exit()
                server_port = input('Enter server port: ')
                if QUITTING:
                    exit()
                if server_port.isdigit():
                    server_port = int(server_port)
                else:
                    print('Invalid port number.\n Quitting...')
            elif user_option == '2':
                    scan_for_local_servers()
                    
        if not server_port and not tcp_over_https:
            server_port = input('Enter server port: ')
            if QUITTING:
                exit()
            if server_port.isdigit():
                server_port = int(server_port)
            else:
                print('Invalid port number.\n Quitting...')
    if not passcode or passcode == '' or passcode == '1234':
        passcode = input('Enter passcode: ')
        if QUITTING:
            exit()
    if not encryption_password or encryption_password == '' or encryption_password == '1234567890123456':
        encryption_password = input('Enter encryption password: ')
        if QUITTING:
            exit()

    print("\nRunning as a client")
    run_client()

##############################################################################################################
# Main
##############################################################################################################
def set_ngrok_auth_token():
    global SERVE_ON_NGROK_TUNNEL
    # Read ngrok auth token from file and set it if SERVE_ON_NGROK_TUNNEL is True
    if SERVE_ON_NGROK_TUNNEL:
        try:
            with open(f'{current_working_directory}/ngrok-auth-token.txt', 'r') as f:
                ngrok_auth_token = f.read()
            ngrok.set_auth_token(ngrok_auth_token)
        except:
            if __name__ == '__main__':
                print(f'# Ngrok auth token not found!\n\t* Please add it to {current_working_directory}/ngrok-auth-token.txt and restart the server.')
                print('\n> For now, disabling ngrok tunnel.')
                SERVE_ON_NGROK_TUNNEL = False
            else:
                ngrok_auth_token = input('You enabled Ngrok Tunnel Option!\nEnter ngrok auth token: ')
                ngrok.set_auth_token(ngrok_auth_token)

def main():
    global server_port
    global server_ip
    global server_name
    global passcode
    global ADVERTISE_SERVER
    global SERVE_ON_NGROK_TUNNEL
    global DEBUG
    global encryption_password
    global tcp_over_https

    ALREADY_RAN = False

    parser = argparse.ArgumentParser(description="Clipboard Sync App", add_help=False)
    parser.add_argument('-s', '--server', type=str, nargs='?', const=5000, help='Run as server on the specified port.')
    parser.add_argument('-c', '--client', type=str, nargs='?', const=-1, help='Run as client, specify server IP and port (e.g., -c 192.169.1.1:8080).')
    parser.add_argument('-d', '--debug', action='store_true', help='Enable debug mode.')
    parser.add_argument('-a', '--advertise', action='store_true', help='Advertise server on the local network.')
    parser.add_argument('-n', '--name', type=str, nargs=1, help='Name of the server to advertise.')
    parser.add_argument('-p', '--passcode', type=str, nargs=1, help='Passcode to authenticate clients.')
    parser.add_argument('-ep', '--encryption-password', type=str, nargs=1, help='Encryption password.')
    parser.add_argument('-h', '--help', action='store_true', help='Show this help message and exit.')
    parser.add_argument('-t', '--serve-on-ngrok-tunnel', action='store_true', help='Serve on ngrok tunnel.')
    parser.add_argument('-toh', '--tcp-over-https', action='store_true', help='Serve on ngrok tunnel.')

    args = parser.parse_args()

    if args.tcp_over_https:
        tcp_over_https = True

    if args.name:
        server_name = args.name[0]
    
    if args.passcode:
        passcode = args.passcode[0]

    if args.encryption_password:
        encryption_password = args.encryption_password[0]

    if args.serve_on_ngrok_tunnel:
        SERVE_ON_NGROK_TUNNEL = True
        set_ngrok_auth_token()

    if args.advertise:
        ADVERTISE_SERVER = True

    if args.debug:
        DEBUG = True
        app.logger.setLevel(logging.DEBUG)
    else:
        app.logger.setLevel(logging.ERROR)
    
    if args.help:
        print(USAAGE_STRING)
        exit()
    
    if not args.server and not args.client:
        print("No command-line arguments provided.")
        role = input("Do you want to act as a server or client? (Type 'server' or 'client'): ")
        if role.lower() == 'server':
            server_port = input("Enter the port to run the server: ")
            if not server_port.isdigit():
                print("Invalid port number. Please enter a valid port number.")
                exit()
            server_port = int(server_port)
            if not args.passcode:
                server_connection_passcode = input("Enter the passcode to authenticate clients: ")
                if server_connection_passcode != '':
                    passcode = server_connection_passcode
            if not args.encryption_password:
                server_data_transfer_encryption_password = input("Enter the encryption password to encrypt data transfer: ")
                if server_data_transfer_encryption_password != '':
                    encryption_password = server_data_transfer_encryption_password
            if not args.advertise:
                enable_server_advertisement = input("Do you want to advertise the server on the local network? (y/n): ")
                if enable_server_advertisement.lower() == 'y':
                    ADVERTISE_SERVER = True
                else:
                    ADVERTISE_SERVER = False
            if not args.serve_on_ngrok_tunnel:
                enable_ngrok_tunnel = input("Do you want to serve on ngrok tunnel? (y/n): ")
                if enable_ngrok_tunnel.lower() == 'y':
                    SERVE_ON_NGROK_TUNNEL = True
                    set_ngrok_auth_token()
                else:
                    SERVE_ON_NGROK_TUNNEL = False
            ALREADY_RAN = True
            if DEBUG:
                print('\nGoing to use encryption password:', encryption_password)
                print('\nGoing to use passcode:', passcode)
            print('\nGoing to use server name:', server_name)
            act_as_server()
        elif role.lower() == 'client':
            server_info = input("Enter the server IP and port (e.g., 192.169.1.1:8080): ").split(':')
            server_ip = server_info[0]
            if server_info[1].isdigit():
                server_port = int(server_info[1])
            else:
                print("Invalid port number. Please enter a valid port number.")
                exit()
            server_connection_passcode = input("Enter the passcode to authenticate clients: ")
            if server_connection_passcode != '':
                passcode = server_connection_passcode
            server_data_transfer_encryption_password = input("Enter the encryption password to encrypt data transfer: ")
            if server_data_transfer_encryption_password != '':
                encryption_password = server_data_transfer_encryption_password
            ALREADY_RAN = True
            if DEBUG:
                print('\nGoing to use encryption password:', encryption_password)
                print('\nGoing to use passcode:', passcode)
            print('\nGoing to use server name:', server_name)
            print('\nGoing to connect to server:', server_ip, server_port)
            act_as_client()
        else:
            print("Invalid role choice. Please type 'server' or 'client'.")
    
    if args.server:
        #if args.server if is number
        if not str(args.server).isdigit():
            print("Invalid port number. Please enter a valid port number.")
            exit()
        server_port = int(args.server)
        if not args.passcode:
            server_connection_passcode = input("Enter the passcode to authenticate clients: ")
            if server_connection_passcode != '':
                passcode = server_connection_passcode
        if not args.encryption_password:
            server_data_transfer_encryption_password = input("Enter the encryption password to encrypt data transfer: ")
            if server_data_transfer_encryption_password != '':
                encryption_password = server_data_transfer_encryption_password
        if not args.advertise:
            enable_server_advertisement = input("Do you want to advertise the server on the local network? (y/n): ")
            if enable_server_advertisement.lower() == 'y':
                ADVERTISE_SERVER = True
            else:
                ADVERTISE_SERVER = False
        if not args.serve_on_ngrok_tunnel:
            enable_ngrok_tunnel = input("Do you want to serve on ngrok tunnel? (y/n): ")
            if enable_ngrok_tunnel.lower() == 'y':
                SERVE_ON_NGROK_TUNNEL = True
                set_ngrok_auth_token()
            else:
                SERVE_ON_NGROK_TUNNEL = False
        if DEBUG:
            print('\nGoing to use encryption password:', encryption_password)
            print('\nGoing to use passcode:', passcode)
        print('\nGoing to use server name:', server_name)
        act_as_server()
    
    elif args.client:
        client_present = False
        if args.client != -1 and len(args.client) > 0:
            server_ip = args.client.split(':')[0]
            client_present = True
            try:
                server_port = args.client.split(':')[1]
            except IndexError:
                if args.tcp_over_https:
                    server_port = None
                else:
                    # riase cumstom exception saying port not specified
                    print('Port not specified. Please specify port number for the server, then only the client can connect to the server.')
                    exit()

        if not args.passcode and client_present:
            server_connection_passcode = input("Enter the passcode to authenticate clients: ")
            if server_connection_passcode != '':
                passcode = server_connection_passcode
        if not args.encryption_password and client_present:
            server_data_transfer_encryption_password = input("Enter the encryption password to encrypt data transfer: ")
            if server_data_transfer_encryption_password != '':
                encryption_password = server_data_transfer_encryption_password
        if DEBUG:
            print('\nGoing to use encryption password:', encryption_password)
            print('\nGoing to use passcode:', passcode)
        print('\nGoing to use server name:', server_name)
        act_as_client()
    
    else:
        if not ALREADY_RAN:
            print("Invalid arguments. Use '-h' or '--help' for usage information.")

if __name__ == '__main__':
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        print('\n# Keyboard Interrupt received. Quitting...')
