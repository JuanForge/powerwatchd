import socket


class session:
    def __init__(self, ups_name: str, host: str = "127.0.0.1", port: int = 3493, timeout: float = 1.5):
        self.sock = socket.create_connection((host, port))
        self.sock.settimeout(timeout)
        self.ups_name = ups_name
    
    def _decoder(self, data: str):
        d = {}
        for line in data.splitlines():
            if line.startswith("VAR "):
                parts = line.split(" ", 3)
                d[parts[2]] = parts[3][1:-1]
        return d
    
    def status(self) -> dict:
        self.sock.sendall(f"LIST VAR {self.ups_name}\n".encode("utf-8"))  # noqa: UP012
        data = b""
        while True:
            chunk = self.sock.recv(2048)
            data += chunk
            if f"END LIST VAR {self.ups_name}".encode("utf-8") in data:  # noqa: UP012
                return self._decoder(data.decode().replace(f"BEGIN LIST VAR {self.ups_name}", "", 1).replace(f"END LIST VAR {self.ups_name}", "", 1))
    
    def close(self):
        self.sock.close()