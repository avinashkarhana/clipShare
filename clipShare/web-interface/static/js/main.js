var encryption_password = prompt("Enter your Encryption Password:")

function decrypt_data(cipher_text_and_iv) {
    // split cipher_text at $ to get cipher_text and iv
    let cipher_text_and_iv_array = cipher_text_and_iv.split('$');
    let cipher_text = cipher_text_and_iv_array[0];
    let iv_base64 = cipher_text_and_iv_array[1];
    let iv_bytes = CryptoJS.enc.Base64.parse(iv_base64);
    let key = CryptoJS.MD5(encryption_password)
    key = CryptoJS.enc.Utf8.parse(key);
    let decrypted = CryptoJS.AES.decrypt(cipher_text, key, { mode: CryptoJS.mode.CBC, iv: iv_bytes });
    let decrypted_data = decrypted.toString(CryptoJS.enc.Utf8);
    // treat last two decrypted data as a queue
    last_two_decrypted_data.push(decrypted_data);
    if (last_two_decrypted_data.length > 2) {
        last_two_decrypted_data.shift();
    }
    // check if last two decrypted data are all "" (empty string)
    if (last_two_decrypted_data.every(function (val) { return val === ""; })) {
        alert("Last two decryptions resulted in empty string!\nIf it is not intentional; then possibly, the decryption is not working properly.\nPlease recheck your Encryption Password, and reload the page.");
    }
    return decrypted_data;
}

function encrypt_data(plain_text) {
    let key = CryptoJS.MD5(encryption_password)
    let iv_bytes = CryptoJS.lib.WordArray.random(16);
    key = CryptoJS.enc.Utf8.parse(key);
    let encrypted_data = CryptoJS.AES.encrypt(plain_text, key, { mode: CryptoJS.mode.CBC, iv: iv_bytes });
    encrypted_data = encrypted_data.toString();
    iv_bytes = CryptoJS.enc.Base64.stringify(iv_bytes);
    return `${encrypted_data}` + '$' + `${iv_bytes}`;
}

const socket = io();
let lastText = '';
let client_authenticated_with_server = false;
let passcode;
let server_ip = window.location.hostname;
let clipboard_available = true;
let dom_out_of_focus = false;
let clipboard_read_available = true;
let clipboard_monitor_interval;
let last_two_decrypted_data = [];

// Check if the browser supports the Clipboard API
if (!navigator.clipboard) {
    console.log('Clipboard API not available');
    clipboard_available = false;
}

// Define the authenticated_server_info object
const authenticated_server_info = {
    token: '',
    server_ip: '',
    server_port: '',
    passcode: '',
    server_name: ''
};

// Send the updated text to the server
function updateText() {
    let text = document.getElementById('textbox').value;
    text = encrypt_data(text);
    socket.emit('clipboard_data_to_server', { 'clipboard_data': text, 'token': authenticated_server_info.token });
}

// Update the textbox content when receiving updates from the server
socket.on('clipboard_data_to_clients', function (data) {
    let clipboard_data = data.clipboard_data;
    clipboard_data = decrypt_data(clipboard_data);
    if (clipboard_data === lastText) {
        return;
    }
    lastText = document.getElementById('textbox').value;
    document.getElementById('textbox').value = clipboard_data;
    // copy data.clipboard_data to clipboard if available
    if (!clipboard_available) {
        return;
    }
    navigator.clipboard.writeText(clipboard_data).then(function () {
        console.log('Async: Copying to clipboard was successful!');
    }, function (err) {
        console.error('Async: Could not copy text: ', err);
    });
});

// Define the socket event listeners
socket.on('authenticate', function (data) {
    if (data.action === 'initiate_auth') {
        start_authentication_to_server(data.msg);
    } else if (data.success === false) {
        client_authenticated_with_server = false;
        console.log('Halting client');
        console.log(data.msg);
        start_authentication_to_server(data.msg);
    }
});

socket.on('authentication_to_client', function (data) {
    if (data.success === true) {
        authenticated_server_info.token = data.token;
        authenticated_server_info.server_ip = server_ip;
        authenticated_server_info.server_port = server_port;
        authenticated_server_info.passcode = passcode;
        authenticated_server_info.server_name = server_name;
        console.log(`#> Authentication with Server ${authenticated_server_info.server_name} (${authenticated_server_info.server_ip}:${authenticated_server_info.server_port}) successful.`);
        client_authenticated_with_server = true;
    } else if (data.success === false) {
        client_authenticated_with_server = false;
        console.log('#> Server authentication failed.');
        start_authentication_to_server(data.msg);
    }
});

// Function to start authentication to the server
function start_authentication_to_server(msg) {
    if (!passcode || passcode === '' || passcode === '1234') {
        let promtMsg = '';
        if (msg) {
            promtMsg = msg + '\n';
        }
        const userInp = prompt(promtMsg + 'Do you want to continue with default passcode (1234)? (y/n): ');
        if (userInp.toLowerCase() != 'y') {
            passcode = prompt('Enter passcode: ');
        } else {
            passcode = '1234';
        }
    }
    else {
        passcode = prompt(msg + '\nEnter passcode: ');
    }
    socket.emit('authentication_from_client', { passcode: passcode });
}

// Add an event listener to the textbox to call updateText() when the text changes
document.getElementById('textbox').addEventListener('input', updateText);

// read the clipboard every 1 second
clipboard_monitor_interval = setInterval(async function () {
    if (!clipboard_available) {
        clearInterval(clipboard_monitor_interval);
        return;
    }
    let clipboard_read_permission = await navigator.permissions.query({ name: 'clipboard-read' });
    if (clipboard_read_permission.state !== 'granted') {
        if (clipboard_read_permission.state === 'prompt') {
            try {
                // try to read the clipboard once to trigger the prompt
                await navigator.clipboard.readText();
            }
            catch { }
        }
        if (clipboard_read_available) {
            console.log('Clipboard read permission not granted');
            clipboard_read_available = false;
        }
        return;
    }
    else {
        if (!clipboard_read_available) {
            console.log('Clipboard read permission granted');
            clipboard_read_available = true;
        }
    }
    navigator.clipboard.readText().then(function (clipboard_data) {
        document.getElementById('textbox').value = clipboard_data;
        dom_out_of_focus = false;
    }, function (err) {
        if (err.name === 'NotAllowedError' && err.message === 'Document is not focused.') {
            if (dom_out_of_focus) {
                return;
            }
            dom_out_of_focus = true;
        }
        console.error('Failed to read clipboard contents: ', err);
    });
}, 1000);
