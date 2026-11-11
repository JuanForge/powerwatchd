import argparse
import socket
import sys
import threading
import time
import traceback

from src import prometheus
from src.protocol import client as nt_client
from src.protocol import types_nt as types
from version import __version__


class UPS:
    class backend_ConnectionRefusedError(Exception): pass
    def __init__(
        self,
        cacheTime: float,
        backend: int,
        ups_name: str,
        ups_host: str = "",
        ups_port: int|None = None,
        debug: bool = False
    ) -> None:
        self.lock = threading.Lock()
        self.cache = {}
        self.timelifecache: float = cacheTime
        self.debug = debug
        # self.simulate = {
        #                     "__meta__": {"start_time": time.monotonic()},
        #                     "simulate": simulate
        #                 }
        
        try:
            kwargs: dict[str, str|int] = {
                "ups_name": ups_name,
                "host": ups_host
            }
            if not ups_port is None:
                kwargs["port"] = ups_port
            
            if backend == 0:
                from src.ups import backend0
                # pyrefly: ignore[bad-argument-type]
                self.backend = backend0.session(**kwargs)
            elif backend == 1:
                from src.ups import backend1
                # pyrefly: ignore[bad-argument-type]
                self.backend = backend1.session(**kwargs)
            elif backend == 2:
                from src.ups import backend2
                # pyrefly: ignore[bad-argument-type]
                self.backend = backend2.session(**kwargs)
            else:
                raise RuntimeError("Invalid backend number.")
        except ConnectionRefusedError:
            raise self.backend_ConnectionRefusedError(traceback.format_exc())
    
    def setTimeLifeCache(self, x: float):
        with self.lock:
            self.timelifecache = x
    
    def status(self) -> dict[str, str|int]:
        with self.lock:
            if self.cache.get("time", 0) < time.monotonic() - self.timelifecache:
                start_time = time.monotonic()
                
                self.cache["data"] = self.backend.status()
                if self.cache["data"] == None:
                    raise RuntimeError("UPS data stale ( 53 )")
                
                # if self.simulate["simulate"]:
                #     self.cache["data"]["battery.charge"] = str(max(
                #         0,
                #         100 - (time.monotonic() - self.simulate["__meta__"]["start_time"]) * self.simulate["simulate"]["battery_drain_rate_sec"]
                #     ))
                
                if self.debug:
                    print(f"time for status ups : {time.monotonic() - start_time}")
                self.cache["time"] = time.monotonic()
            
            return self.cache["data"]

def client(
    sock: socket.socket,
    addr: tuple[str, int]|tuple[str, int, int, int],
    metrics: prometheus.session,
    ups: UPS
) -> None:
    LastStatus: str = ""
    timeoutNoPing = 10
    start_time_connect = time.monotonic()
    
    name = None
    try:
        sock.settimeout(0.5)
        session = nt_client.server(sock)
        
        # start_time_init = time.monotonic()
        start_time_ping = time.monotonic()
        
        data = session._session.recv()
        if data["type"] != "handshake_name":
            raise ConnectionError("Expected handshake message")
        
        name = str(data.get("name", "unknown"))
        session._session.send({"type": "handshake_ack"})
        
        # ID = secrets.token_hex(20)
        
        while True:
            metrics.addclient(name=name, ip=addr[0], time=int(time.monotonic() - start_time_connect))
            try:
                data = session.recv()
                
                start_time_ping = time.monotonic()
                
                if isinstance(data, types.ping):
                    session.pong()
                
                data = ups.status()
                
                if data["ups.status"] != LastStatus:
                    # pyrefly: ignore[bad-assignment]
                    LastStatus = data["ups.status"]
                    
                    # pyrefly: ignore[not-iterable]
                    if "OB" in data["ups.status"]:
                        status = False
                    else:
                        status = True
                    
                    session.UPS(
                        status=status,
                        # pyrefly: ignore[bad-argument-type]
                        battery_charge=data["battery.charge"]
                    )
            except TimeoutError:
                if time.monotonic() - start_time_ping > timeoutNoPing:
                    return
                else:
                    continue
    except:  # noqa: E722
        print(traceback.format_exc())
    finally:
        if (type(name) == str):
            metrics.removeclient(name=name, ip=addr[0])
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
            conn = sock.accept()[0]
            
            data = b""
            while b"\r\n\r\n" not in data and len(data) < ( 1024 * 1024 * 4):
                chunk = conn.recv(1024)
                if not chunk:
                    break
                data += chunk
            else:
                # pyrefly: ignore[bad-argument-type]
                metrics.update(ups.status())
                conn.sendall(metrics._dumps())
        except Exception:  # noqa: BLE001
            print(traceback.format_exc())

if __name__ == "__main__":
    # with open('simulate.profiles.json', 'r') as file:
    #     profile_simulate = json.load(file)
    #     del profile_simulate["index"]
    
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
        default=1,
        help="Cache uptime (seconds)"
    )
    
    parser.add_argument(
        "--ups-name",
        help="Name of the UPS used by the backend.",
        default="ecoEaton"
    )
    
    parser.add_argument(
        "--ups-backend",
        type=int,
        help="UPS backend ID.",
        choices=[0, 1, 2],
        default=2
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
    # parser.add_argument(
    #     "--simulate-profile",
    #     type=str,
    #     default=False,
    #     help="Use a predefined simulation profile to inject synthetic UPS states for testing purposes.",
    #     choices=profile_simulate.keys()
    # )
    parser.add_argument(
        "--max-clients",
        type=int,
        help="Maximum number of clients connected to the server.",
        default=None
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
    
    args = parser.parse_args()
    
    if args.version:
        print(f"version : {__version__}")
        sys.exit(0)
    
    # if any([args.simulate_profile]): # args.simulate_power_outage, args.battery_drain_rate
    #     print("\033[38;5;208m[WARNING]\033[0m [TEST MODE] Application started in simulation mode. This instance is NOT intended for production use.\033[0m")
    
    simulate_profile = None
    
    # if args.simulate_profile:
    #     if not str(args.simulate_profile) in profile_simulate:
    #         print("The requested profile does not exist.")
    #         sys.exit(234)
    #     else:
    #         simulate_profile: dict|None = profile_simulate[args.simulate_profile]
    
    metrics = prometheus.session()
    threads: list[threading.Thread] = []
    
    try:
        ups = UPS(
            cacheTime=args.ups_cache_time,
            backend=args.ups_backend,
            ups_name=args.ups_name,
            debug=args.debug,
            # simulate=simulate_profile,
            ups_host=args.ups_backend_host,
            ups_port=args.ups_backend_port
        )
        
        if args.prometheus:
            threading.Thread(target=prometheus_thread, args=(metrics, args.host, args.prometheus_port, ups), daemon=True).start()
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((args.host, args.port))
        sock.listen(20)
        
        while True:
            try:
                conn, addr = sock.accept()
                if args.max_clients is None or len(threads) <= args.max_clients:
                    thread = threading.Thread(target=client, args=(metrics, conn, addr, ups), daemon=True)
                    thread.start()
                    threads.append(thread)
                    
                    for unit in threads.copy():
                        if not unit.is_alive():
                            unit.join()
                            threads.remove(unit)
                else:
                    try: conn.close()
                    except: pass  # noqa: E722, S110
            except Exception:  # noqa: BLE001
                print(traceback.format_exc())
    except KeyboardInterrupt:
        pass
    except UPS.backend_ConnectionRefusedError as e:
        print(f"{e}\nError connecting to the UPS backend.")
    except Exception:  # noqa: BLE001
        print(traceback.format_exc())