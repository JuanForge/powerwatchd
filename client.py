import argparse
import os
import socket
import sys
import threading
import time
import traceback
from pathlib import Path

from pydbus import SystemBus

from src import config_client as config
from src import systemd
from src.protocol import client as nt_client
from src.protocol import types_nt as types
from version import __schemaVersion__, __version__

ifbuzzer = True

if ifbuzzer:
    from src import buzzer

def keepalive(session: nt_client.client):
    try:
        while True:
            session.ping()
            time.sleep(4)
    except:  # noqa: E722
        print(f"KEEP ALIVE : {traceback.format_exc()}")

def AntiBoucle(tasks: list[config.StopTask]):
    seen = set()
    
    def visit(task_name: str, path: list[str]):
        if task_name in path:
            print(f"Loop detected : {' -> '.join(path + [task_name])}")
            return False
        if task_name in seen:
            return True
        seen.add(task_name)
        task = next((t for t in tasks if t.name == task_name), None)
        if not task:
            return True
        for dep in task.dependency:
            result = visit(dep, path + [task_name])
            if result is False:
                return False
        return True
    
    for task in tasks:
        result = visit(task.name, [])
        if result is False:
            return False
    
    return True

def audio(STOP: threading.Event):
    while not STOP.wait(2):
        buzzer.beep(2000, 500)

def shutdown():
    time.sleep(2)
    login1 = SystemBus().get(".login1")
    login1.PowerOff(False)

def unit(percent: int, task: config.StopTask, tasks: list[config.StopTask]):
    bus = SystemBus()
    for tache in tasks:
        if task.name in tache.dependency:
            status = systemd.status(tache.name, bus=bus)
            if isinstance(status, dict):  # noqa: SIM102
                if not status['status'] in ('inactive', 'failed', 'deactivating'):
                    print(f"[WARNING] : {task.name} ask by {tache.name}")
    
    if percent <= task.percent:
        print(f"[WARNING] : STOP : {task.name}")
        systemd.service.stop(task.name, bus=bus)
        return True
    else:
        return False

class main:
    def __init__(self, JSON: config.Config, beep: bool = True):
        self.JSON = JSON
        self.bus = SystemBus()
        self.threadbeep: None|threading.Thread = None
        self.threadbeepSTOP = threading.Event()
        self.oldstatus: bool|None = None
        #self.threads = None
        self.service_table: list[dict[str, str|list[str]]] = []
        self.beep = beep
        self.tasks = self.JSON.OnBattery.StopTask
    
    def update(self, status: bool, charge: int):
        if status == False:
            print("Battery-powered server.")
            if self.beep == True and self.threadbeep == None:
                self.threadbeep = threading.Thread(target=audio, args=(self.threadbeepSTOP,), daemon=True)
                self.threadbeep.start()
            
            if self.oldstatus == True:
                for task in self.tasks:
                    _status = systemd.status(task.name, bus=self.bus)
                    if isinstance(_status, dict):  # noqa: SIM102
                        if _status['status'] in ('active',):
                            self.service_table.append(
                                {
                                    "name": task.name,
                                    "status": _status['status'],
                                    "dependency": task.dependency
                                }
                            )
            
            for task in self.tasks:
                unit(charge, task, tasks=self.tasks)
            
            if charge <= JSON.OnBattery.shutdown.percent:
                print("SHUTDOWN")
                shutdown()
        
        elif status == True:
            if self.oldstatus == False:
                print("Server on mains power.")
            
            if self.beep == True and self.threadbeep != None:
                self.threadbeepSTOP.set()
                self.threadbeep.join()
                self.threadbeep = None
                self.threadbeepSTOP.clear()
                
                for task in self.service_table:
                    def __load__(tache: str) -> None:
                        current = next((t for t in self.service_table if t['name'] == tache), None)
                        if not current:
                            print(f"[WARNING] : Unknown task : {tache}")
                            return
                        for dep in current.get('dependency', []):
                            __load__(dep)
                        
                        print(f"[DEBUG] : Start : {tache}")
                        
                        systemd.service.start(tache, bus=self.bus)
                    if task['status'] == 'active':
                        __load__(str(task['name']))
                self.service_table = []
        self.oldstatus = status

if __name__ == "__main__":
    if True == ifbuzzer:
        buzzer.beep(2000, 500) # type: ignore
    
    os.chdir(Path(__file__).resolve().parent)
    
    with open('config.client.json', 'r') as file:
        JSON = config.Config.model_validate_json(file.read())
    
    if JSON.schemaVersion != __schemaVersion__:
        sys.exit(158)
    
    if not AntiBoucle(JSON.OnBattery.StopTask):
        sys.exit(157)
    
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
        "--no-beep",
        action="store_false",
        help="disable the beep sound for debug"
    )
    parser.add_argument(
        "--name",
        type=str,
        help="Client name displayed on server side"
    )
    
    args = parser.parse_args()
    
    if args.version:
        print(f"version : {__version__}")
        sys.exit(0)
    
    if not args.no_beep_lib:
        from src import buzzer
    
    JSON.beep = args.no_beep
    name = args.name
    
    app = main(JSON, beep=JSON.beep)
    sock = None
    try:
        i = 0
        while i != JSON.offlineServer.retry:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(JSON.offlineServer.tcpTimeoutSec)
                print(f"Connect ( try: {i+1})...")
                sock.connect((args.host, args.port))
                
                session = nt_client.client(sock)
                
                print(f"name client : {name}")
                
                session.handshake(name)
                d = session.recv()
                if isinstance(d, types.handshake_ack):
                    print("Connect : OK")
                    break
                else:
                    raise ConnectionError(f"Handshake failed: {d}")
            except Exception as e:  # noqa: BLE001
                print(str(e))
                i += 1
                buzzer.beep(3000, 500)
                time.sleep(JSON.offlineServer.retryIntervalSec)
        else:
            if JSON.offlineServer.shutdown == True:
                shutdown()
                sys.exit(178)
            else:
                sys.exit(180)
        
        session._sock.settimeout(1)
        
        keepalive_thread = threading.Thread(target=keepalive, args=(session,), daemon=True)
        keepalive_thread.start()
        
        while True:
            try:
                data = session.recv()
                
                if isinstance(data, types.UPS):
                    app.update(data.status, data.battery_charge)
                
                elif isinstance(data, types.pong):
                    pass
                
                if not keepalive_thread.is_alive():
                    raise RuntimeError("keepalive thread is dead")
            except TimeoutError:
                continue
    except KeyboardInterrupt:
        pass
    except Exception:  # noqa: BLE001
        print(traceback.format_exc())
    finally:
        # with open("session.client.json", "w", encoding="utf-8") as file:
        #     file.write(json.dumps(app.save(), indent=4))
        
        if sock:
            sock.close()