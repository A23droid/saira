import socket

def check_port(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    result = sock.connect_ex(('127.0.0.1', port))
    sock.close()
    return result == 0

print(f"Port 3000 (Frontend): {check_port(3000)}")
print(f"Port 8000 (Backend): {check_port(8000)}")
