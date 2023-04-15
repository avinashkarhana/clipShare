# clipboardSync

A single TCP server/client bundle that allows you to sync your clipboard between systems.

# Features
1. Sync clipboard between systems.
2. Has a Web UI.
    - To view clipboard on mobile devices.
    - To sync clipboard if not using the python client.
2. Advertise server on the local network.
3. Authentication using passcode.
5. Scan for servers on the local network.
6. Same script can be used as server or client.

## Usage

    Usage: 
        python newClipShare.py [-h] [-s [SERVER_PORT_NUMER]] [-c SERVER_IP:SERVER_PORT_NUMBER] [-d]

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


