# clipboardSync

A single TCP server/client bundle that allows you to sync your clipboard between systems.

# Features
1. Sync clipboard between systems.
2. Has a Web UI.
    - To view clipboard on mobile devices.
    - To sync clipboard if not using the python client.
2. Advertise the server on the local network.
3. Authentication using passcode. (Passcode should be shared via some external safe channel)
5. Scan for servers on the local network.
6. The same script can be used as a server or client.
7. Encrypted communication for clipboard sharing with AES Encryption (Key should be shared via some external safe channel)

## Usage

    Usage: 
        python newClipShare.py [-h] [-s [SERVER_PORT_NUMER]] [-c SERVER_IP:SERVER_PORT_NUMBER] [-d]

    Options:
        -h, --help                      Show this help message and exit
        -s, --server [SERVER_PORT_NUMER], --server [SERVER_PORT_NUMER]
                                        Run as server on the specified port.
        -c, --client SERVER_IP:SERVER_PORT_NUMBER, --client SERVER_IP:SERVER_PORT_NUMBER
                                        Run as a client, that connects to specified server IP and port.
        -t, --serve-on-ngrok-tunnel     Enable Serve on ngrok tunnel. This option requires ngrok authtoken to be present in {current_dir}/ngrok-auth-token.txt
        -a, --advertise                 Enable Advertising server on the local network.
        -n, --name                      Name of the server to be advertised.
        -p, --passcode                  Passcode for authentication.
        -ep, --encryption-password      Encryption password for data transfer.
        -d, --debug                     Enable debug mode.

    Examples:
        python newClipShare.py -s 5000
        python newClipShare.py -s 5000 -d
        python newClipShare.py -s 5000 -a
        python newClipShare.py -s 5000 -p RandomPasscode -ep 5up3rS3cu3_3ncrY9t1on_P45sw0rd
        python newClipShare.py -s 5000 -p RandomPasscode -ep 5up3rS3cu3_3ncrY9t1on_P45sw0rd -t -a -d
        python newClipShare.py -c 192.168.0.1:8080
        python newClipShare.py -c -d
        python newClipShare.py -c -d -p RandomPasscode -ep 5up3rS3cu3_3ncrY9t1on_P45sw0rd


