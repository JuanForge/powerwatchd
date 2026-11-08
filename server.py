import argparse
import json
import secrets
import socket
import sys
import threading
import time
import traceback

from src import prometheus, protocol
from version import __schemaVersion__, __version__


class UPS:
    class backend_ConnectionRefusedError(Exception): pass
    def __init__(self, cacheTime: int, backend: int, ups_name: str, debug: bool = False, simulate: dict|None = None, ups_host: str = "", ups_port: int = 0):
        self.lock = threading.Lock()
        self.cache = {}
        self.timelifecache = cacheTime
        self.debug = debug
        self.simulate = {
                            "__meta__": {"start_time": time.monotonic()},
                            "simulate": simulate
                        }
        
        try:
            if backend == 0:
                from src.ups import backend0
                self.backend = backend0.session(ups_name=ups_name, host=ups_host, port=ups_port)
            elif backend == 1:
                from src.ups import backend1
                self.backend = backend1.session(ups_name=ups_name, host=ups_host, port=ups_port)
            elif backend == 2:
                from src.ups import backend2
                self.backend = backend2.session(ups_name=ups_name, host=ups_host, port=ups_port)
            else:
                raise RuntimeError("Invalid backend number.")
        except ConnectionRefusedError:
            raise self.backend_ConnectionRefusedError(traceback.format_exc())
    
    def setTimeLifeCache(self, x: int | float):
        with self.lock:
            self.timelifecache = x
    
    def status(self) -> dict:
        with self.lock:
            if self.cache.get("time", 0) < time.monotonic() - self.timelifecache:
                start_time = time.monotonic()
                
                self.cache["data"] = self.backend.status()
                if self.cache["data"] == None:
                    raise RuntimeError("UPS data stale ( 53 )")
                
                if self.simulate["simulate"]:
                    self.cache["data"]["battery.charge"] = str(max(
                        0,
                        100 - (time.monotonic() - self.simulate["__meta__"]["start_time"]) * self.simulate["simulate"]["battery_drain_rate_sec"]
                    ))
                
                if self.debug:
                    print(f"time for status ups : {time.monotonic() - start_time}")
                self.cache["time"] = time.monotonic()
            
            return self.cache["data"]

def client(metrics: prometheus.session, sock: socket.socket, addr, ups: UPS):
    LastStatus: str = ""
    timeoutNoPing = 10
    name = ID = None
    start_time_connect = time.monotonic()
    
    try:
        sock.settimeout(0.5)
        sesssion = protocol.network(sock)
        start_time: dict = {
                        "init": time.monotonic(),
                        "ping": time.monotonic()
                    }
        
        data = sesssion.recv()
        if data["type"] != "handshake_name":
            raise ConnectionError("Expected handshake message")
        
        sesssion.send({"type": "handshake_ack"})
        
        name = str(data.get("name", "unknown"))
        ID = secrets.token_hex(20)
        
        while True:
            metrics.addclient(name=name, ID=ID, ip=addr[0], time=int(time.monotonic() - start_time_connect))
            try:
                data = sesssion.recv()
                
                start_time["ping"] = time.monotonic()
                
                if data["type"] == "ping":
                    sesssion.send({"type": "pong"})
                
                data = ups.status()
                
                if data["ups.status"] != LastStatus:
                    LastStatus = data["ups.status"]
                    
                    if "OB" in data["ups.status"]:
                        status = False
                    else:
                        status = True
                    
                    sesssion.send({"type": "UPS",
                                    "status": status,
                                    "battery.charge": int(data["battery.charge"])
                                })
            except socket.timeout:
                if time.monotonic() - start_time["ping"] > timeoutNoPing:
                    return
                else:
                    continue
    except Exception as e:
        print(traceback.format_exc())
    finally:
        if (type(name) == str) and (type(ID) == str):
            metrics.removeclient(name=name, ID=ID, ip=addr[0])
        if sock:
            sock.close()

def prometheus_thread(metrics: prometheus.session, host: str, port: int, ups: UPS):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.listen(20)
    
    print(f"Prometheus listen {host}:{port}")
    while True:
        try:
            conn, addr = sock.accept()
            
            data = b""
            while b"\r\n\r\n" not in data and len(data) < ( 1024 * 1024 * 4):
                chunk = conn.recv(1024)
                if not chunk:
                    break
                data += chunk
            else:
                metrics.update(ups.status())
                conn.sendall(metrics._dumps())
        except Exception as e:
            print(traceback.format_exc())

if __name__ == "__main__":
    with open('config.server.json', 'r') as file:
        JSON:dict = json.load(file)
    
    if JSON["schemaVersion"] != __schemaVersion__:
        sys.exit(109)
    
    with open('simulate.profiles.json', 'r') as file:
        profile_simulate:dict = json.load(file)
        del profile_simulate["index"]
    
    parser = argparse.ArgumentParser(
        description="Configuration CLI",
        allow_abbrev=False
    )
    
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1"
    )
    
    parser.add_argument(
        "--port",
        type=int,
        default=2152
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="display the version and exit."
    )
    parser.add_argument(
        "--ups-cache-time",
        type=int,
        default=JSON["cacheUPStime"],
        help=f"Cache uptime (seconds), default : {JSON['cacheUPStime']}"
    )
    
    parser.add_argument(
        "--ups-name",
        help=f"Name of the UPS used by the backend, default : {JSON['UPSname']}"
    )
    
    parser.add_argument(
        "--ups-backend",
        type=int,
        default=JSON["backend"],
        help=f"UPS backend ID, default : {JSON['backend']}",
        choices=[0, 1, 2]
    )
    
    parser.add_argument(
        "--debug",
        action="store_true",
        help="enable debugging output for the program"
    )
    parser.add_argument(
        "--prometheus",
        action="store_true",
        help="Expose UPS information in Prometheus format."
    )
    parser.add_argument(
        "--prometheus-port",
        type=int,
        default=2162
    )
    parser.add_argument(
        "--simulate-profile",
        type=str,
        default=False,
        help=f"Use a predefined simulation profile to inject synthetic UPS states for testing purposes.",
        choices=profile_simulate.keys()
    )
    parser.add_argument(
        "--max-clients",
        type=int,
        help="Maximum number of clients connected to the server.",
        default=-1
    )
    parser.add_argument(
        "--ups-backend-host",
        type=str,
        help="Backend IP address to connect to.",
        default="127.0.0.1"
    )
    parser.add_argument(
        "--ups-backend-port",
        type=int,
        help="Port of the backend to connect to.",
        default=3493
    )
    # parser.add_argument(
    #     "--simulate-power-outage",
    #     action="store_true",
    #     help=("Injects a simulated UPS state transition from online (OL) ")
    #     + ("to on-battery (OB) by overriding exported metrics for testing and monitoring purposes.")
    # )
    # parser.add_argument(
    #     "--battery-drain-rate",
    #     type=int,
    #     default=False,
    #     help="Battery percentage decrease per second during simulation."
    # )
    
    args, unknown = parser.parse_known_args()
    
    if unknown:
        print(f"Error: Unrecognized arguments: {', '.join(unknown)}")
        sys.exit(139)
    print("\033[38;5;208m[WARNING]\033[0m Use CLI arguments instead. File-based configuration will be deprecated.\033[0m")
    
    if args.version:
        print(f"version : {__version__}")
        sys.exit(0)
    if any([args.simulate_profile]): # args.simulate_power_outage, args.battery_drain_rate
        print("\033[38;5;208m[WARNING]\033[0m [TEST MODE] Application started in simulation mode. This instance is NOT intended for production use.\033[0m")
    
    simulate_profile = None
    
    if args.simulate_profile:
        if not str(args.simulate_profile) in profile_simulate.keys():
            print("The requested profile does not exist.")
            sys.exit(234)
        else:
            simulate_profile: dict|None = profile_simulate[args.simulate_profile]
    
    metrics = prometheus.session()
    threads: list[threading.Thread] = []
    
    try:
        ups = UPS(cacheTime=args.ups_cache_time or JSON.get("cacheUPStime", 0),
                    backend=args.ups_backend    or JSON.get("backend", 2),
                    ups_name=args.ups_name      or JSON.get("UPSname", "ecoEaton"),
                    debug=args.debug, simulate=simulate_profile,
                    ups_host=args.ups_backend_host,
                    ups_port=args.ups_backend_port)
        
        if args.prometheus:
            threading.Thread(target=prometheus_thread, args=(metrics, args.host, args.prometheus_port, ups), daemon=True).start()
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((args.host, args.port))
        sock.listen(20)
        
        while True:
            try:
                conn, addr = sock.accept()
                if int(args.max_clients) == -1 or len(threads) <= int(args.max_clients):
                    thread = threading.Thread(target=client, args=(metrics, conn, addr, ups), daemon=True)
                    thread.start()
                    threads.append(thread)
                    
                    for unit in threads.copy():
                        if not unit.is_alive():
                            unit.join()
                            threads.remove(unit)
                else:
                    try: conn.close()
                    except: pass
            except Exception as e:
                print(traceback.format_exc())
    except KeyboardInterrupt:
        pass
    except UPS.backend_ConnectionRefusedError as e:
        print(f"{e}\nError connecting to the UPS backend.")
    except Exception as e:
        print(traceback.format_exc())