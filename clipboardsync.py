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

app = Flask(__name__)
sio = python_socketio.Client(ssl_verify=False)
socketio = SocketIO(app)

last_copied_data = ''
shared_text=''
server_port = None
server_ip = None
server_name = 'clipboardSync'
server_clipboard_thread_started = False
QUITTING = False
DEBUG = False
ADVERTISE_SERVER = False
passcode = '1234'
client_authenticated_with_server = False

USAAGE_STRING = """
Usage: newClipShare.py [-h] [-s [SERVER_PORT_NUMER]] [-c SERVER_IP:SERVER_PORT_NUMBER] [-d]

Options:
    -h, --help            show this help message and exit
    -s, --server [SERVER_PORT_NUMER], --server [SERVER_PORT_NUMER]
                            Run as server on the specified port.
    -c, --client SERVER_IP:SERVER_PORT_NUMBER, --client SERVER_IP:SERVER_PORT_NUMBER
                            Run as client, specify server IP and port.
    -a, --advertise       Advertise server on the local network.
    -n, --name            Name of the server to be advertised.
    -p, --passcode        Passcode for authentication.
    -d, --debug           Enable debug mode.

Examples:
    python newClipShare.py -s 5000
    python newClipShare.py -c 192.168.0.1:8080
    python newClipShare.py -s 5000 -d
    python newClipShare.py -c -d
"""

##############################################################################################################
# Server Code
##############################################################################################################
authenticated_clients = []

@socketio.on('authentication_from_client')
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

@socketio.on('connect')
def on_connect():
    print(f'#> Client Connection {request.sid}')
    for client in authenticated_clients:
        if client['clientId'] == request.sid:
            socketio.emit('clipboard_data_to_clients', {'clipboard_data': ''}, room=client['clientId'])
            authenticated_clients.remove(client)
    socketio.emit('authenticate', {'action': 'initiate_auth', 'msg': 'Initiate Authentication!'}, room=request.sid)
    global server_clipboard_thread_started
    if not server_clipboard_thread_started:
        start_server_clipboard_thread()

@socketio.on('clipboard_data_to_server')
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
    if last_copied_data != received_clipboard_data:
        pyclip.copy(received_clipboard_data)
        if DEBUG:
            print(f'Copied data received from client {request.sid}: {received_clipboard_data}')
        shared_text=received_clipboard_data
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
    
    service_name = f'_{server_name}._clipboardsync._tcp.local.'
    # Set up the service info
    service_info = ServiceInfo(
        "_clipboardsync._tcp.local.",  # Service type
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
                for client in authenticated_clients:
                    socketio.emit('clipboard_data_to_clients', {'clipboard_data': data}, room=client['clientId'])
                shared_text = data
                last_copied_data = data
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

def run_server():
    global ADVERTISE_SERVER
    global QUITTING
    global server_port
    global server_name
    if ADVERTISE_SERVER:
        threading.Thread(target=advertise_server, daemon=True).start()
    socketio.run(app, host='0.0.0.0', port=server_port)
    ADVERTISE_SERVER = False
    QUITTING = True
    print("\n# Server stopped.")

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

@sio.on('authenticate')
def on_authenticate_with_server(data):
    global client_authenticated_with_server
    if data.get('action') == 'initiate_auth':
        client_authenticated_with_server = False
        print('\n# Server asked to initiate authentication')
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

@sio.on('clipboard_data_to_clients')
def on_clipboard_data(data):
    global last_copied_data
    global shared_text
    last_copied_data = data.get('clipboard_data')
    if DEBUG:
        print(f'Copied data received from server: {last_copied_data}')
    shared_text=last_copied_data
    pyclip.copy(last_copied_data)

@sio.on('authentication_to_client')
def on_authentication_from_server(data):
    global authenticated_server_info
    global client_authenticated_with_server
    if data.get('success') == True:
        authenticated_server_info['token'] = data.get('token')
        authenticated_server_info['server_ip'] = server_ip
        authenticated_server_info['server_port'] = server_port
        authenticated_server_info['passcode'] = passcode
        authenticated_server_info['server_name'] = server_name
        print(f'#> Authentication with Server {authenticated_server_info.get("server_ip")}:{authenticated_server_info.get("server_port")} successful.')
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
        sio.emit('authentication_from_client', {'passcode': passcode})
    except:
        connect_to_server(f'http://{server_ip}:{server_port}')
        sio.emit('authentication_from_client', {'passcode': passcode})

def connect_to_server(server_url):
    try:
        sio.connect(server_url)
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
                sio.connect(server_url)
            else:
                print(f'Exception:\n {e}')

def run_client():
    global QUITTING
    server_url = f'http://{server_ip}:{server_port}'
    print(f'# Connecting to server {server_ip}:{server_port}.')
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
                sio.emit('clipboard_data_to_server', {'token': authenticated_server_info.get('token'), 'clipboard_data': data })
                last_copied_data = data
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
    browser = ServiceBrowser(zeroconf, '_clipboardsync._tcp.local.', listener)

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
                    
        if not server_port:
            server_port = input('Enter server port: ')
            if QUITTING:
                exit()
            if server_port.isdigit():
                server_port = int(server_port)
            else:
                print('Invalid port number.\n Quitting...')

    run_client()

##############################################################################################################
# Main
##############################################################################################################
def main():
    global server_port
    global server_ip
    global server_name
    global passcode
    global ADVERTISE_SERVER
    global DEBUG


    parser = argparse.ArgumentParser(description="Clipboard Sync App", add_help=False)
    parser.add_argument('-s', '--server', type=str, nargs='?', const=5000, help='Run as server on the specified port.')
    parser.add_argument('-c', '--client', type=str, nargs='?', const=-1, help='Run as client, specify server IP and port (e.g., -c 192.169.1.1:8080).')
    parser.add_argument('-d', '--debug', action='store_true', help='Enable debug mode.')
    parser.add_argument('-a', '--advertise', action='store_true', help='Advertise server on the local network.')
    parser.add_argument('-n', '--name', type=str, nargs=1, help='Name of the server to advertise.')
    parser.add_argument('-p', '--passcode', type=str, nargs=1, help='Passcode to authenticate clients.')
    parser.add_argument('-h', '--help', action='store_true', help='Show this help message and exit.')

    args = parser.parse_args()

    if args.name:
        server_name = args.name[0]
    
    if args.passcode:
        passcode = args.passcode[0]

    if args.advertise:
        ADVERTISE_SERVER = True

    if args.debug:
        DEBUG = True
    
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
            act_as_server()
        elif role.lower() == 'client':
            server_info = input("Enter the server IP and port (e.g., 192.169.1.1:8080): ").split(':')
            server_ip = server_info[0]
            if server_info[1].isdigit():
                server_port = int(server_info[1])
            else:
                print("Invalid port number. Please enter a valid port number.")
                exit()
            act_as_client()
        else:
            print("Invalid role choice. Please type 'server' or 'client'.")
    
    if args.server:
        #if args.server if is number
        if not str(args.server).isdigit():
            print("Invalid port number. Please enter a valid port number.")
            exit()
        server_port = int(args.server)
        act_as_server()
    
    elif args.client:
        if args.client != -1 and len(args.client) > 0:
                server_ip = args.client[0].split(':')[0]
                server_port = args.client[0].split(':')[1]
        act_as_client()
    
    else:
        print("Invalid arguments. Use '-h' or '--help' for usage information.")

if __name__ == '__main__':
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        print('\n# Keyboard Interrupt received. Quitting...')
