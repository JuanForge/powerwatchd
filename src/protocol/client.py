from socket import socket

from src.protocol import network
from src.protocol import types_nt as types


class client:
    def __init__(self, sock: socket) -> None:
        self._sock = sock
        self._session = network.network(sock)
    
    def handshake(self, name: str) -> None:
        self._session.send(
            {"type": "handshake_name", "name": name}
        )
    
    def ping(self) -> None:
        self._session.send(
            {"type": "ping"}
        )
    
    def recv(self):
        data = self._session.recv()
        
        if data["type"] == "handshake_ack":
            return types.handshake_ack()
        
        elif data["type"] == "pong":
            return types.pong()
        
        elif data["type"] == "UPS":
            return types.UPS(
                status=data["status"],
                battery_charge=data["battery.charge"]
            )
        
        else:
            raise RuntimeError("not found key")

class server:
    def __init__(self, sock: socket) -> None:
        self._sock = sock
        self._session = network.network(sock)
    
    def UPS(
        self,
        status: bool,
        battery_charge: int
    ) -> None:
        self._session.send(
            {
                "type": "UPS",
                "status": status,
                "battery.charge": battery_charge
            }
        )
    
    def pong(self):
        self._session.send({"type": "pong"})
    
    def recv(self):
        data = self._session.recv()
        if data["type"] == "ping":
            return types.ping()
        else:
            raise RuntimeError("not found key")