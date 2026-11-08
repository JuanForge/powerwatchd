from typing import Union

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Gauge,
    Info,
    generate_latest,
)


class session:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.metrics: dict[str, Union[Gauge, Info]] = {"clients": Gauge(
                                                        "clients",
                                                        "connected clients",
                                                        ["name", "ip", "ID"], registry=self.registry
                                                    )
        }
    
    def _set_value(self, key: str, value: str|int|float) -> None:
        name = key.replace(".", "_")
        m = self.metrics.get(name, None)
        try:
            value = float(value)
            
            if m == None:
                m = Gauge(name, key, registry=self.registry)
                self.metrics[name] = m
            
            if isinstance(m, Gauge): m.set(value)
            
        except ValueError:
            if name == "ups_status":
                if "OL" in str(value):
                    online = 1
                elif "OB" in str(value):
                    online = 0
                else:
                    online = 2
                if m == None:
                    m = Gauge(name, key, registry=self.registry)
                    self.metrics[name] = m
                if isinstance(m, Gauge): m.set(online)
            else:
                if m == None:
                    m = Info(name, key, registry=self.registry)
                    self.metrics[name] = m
                if isinstance(m, Info): m.info({"value": str(value)})
    
    def update(self, dico: dict[str, str | int | float]) -> dict:
        for key, value in dico.items():
            self._set_value(key, value)
        return self.metrics
    
    def _dumps(self) -> bytes:
        data = generate_latest(self.registry)
        return (
            b"HTTP/1.1 200 OK\r\n"
            + f"Content-Type: {CONTENT_TYPE_LATEST}\r\n".encode()
            + f"Content-Length: {len(data)}\r\n".encode()
            + b"Connection: close\r\n"
            + b"\r\n"
            + data
        )
    
    def addclient(self, name: str, ID: str, ip: str|None = None, time: int = 1) -> None:
        self.metrics["clients"].labels(name=name, ip=str(ip), ID=ID).set(time) # type: ignore
    def removeclient(self, name: str, ID: str, ip: str|None = None) -> None:
        self.metrics["clients"].remove_by_labels({"name": name, "ip": str(ip), "ID": ID})

if __name__ == "__main__":
    s = session()
    data = { # example
            'battery.charge': '100', 'battery.charge.low': '20', 'battery.runtime': '1612',
            'battery.type': 'PbAc', 'device.mfr': 'EATON', 'device.model': 'Ellipse ECO 1200',
            'device.serial': '000000000', 'device.type': 'ups', 'driver.name': 'usbhid-ups',
            'driver.parameter.pollfreq': '30', 'driver.parameter.pollinterval': '2',
            'driver.parameter.port': 'auto', 'driver.parameter.productid': '----',
            'driver.parameter.synchronous': 'auto', 'driver.parameter.vendorid': '----', 'driver.version': '2.8.0',
            'driver.version.data': 'MGE HID 1.46', 'driver.version.internal': '0.47', 'driver.version.usb': 'libusb-1.0.26 (API: 0x1000109)',
            'input.transfer.high': '264', 'input.transfer.low': '184', 'outlet.1.desc': 'PowerShare Outlet 1', 'outlet.1.id': '2', 'outlet.1.status': 'on',
            'outlet.1.switchable': 'no', 'outlet.2.desc': 'PowerShare Outlet 2', 'outlet.2.id': '3', 'outlet.2.status': 'on', 'outlet.2.switchable': 'no', 'outlet.desc':
            'Main Outlet', 'outlet.id': '1', 'outlet.power': '25', 'outlet.switchable': 'no', 'output.frequency.nominal': '50', 'output.voltage': '230.0', 'output.voltage.nominal': '230',
            'ups.beeper.status': 'enabled', 'ups.delay.shutdown': '20', 'ups.delay.start': '30', 'ups.firmware': '02', 'ups.load': '18', 'ups.mfr': 'EATON', 'ups.model': 'Ellipse ECO 1200',
            'ups.power.nominal': '1200', 'ups.productid': '----', 'ups.realpower': '173', 'ups.serial': '000000000', 'ups.status': 'OL', 'ups.timer.shutdown': '-1', 'ups.timer.start': '-1', 'ups.vendorid': '----'
    }
    s.update(data) # type: ignore
    print(s._dumps())