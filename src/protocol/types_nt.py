from pydantic import BaseModel, ConfigDict


class pong(BaseModel): pass

class ping(BaseModel): pass

class handshake_ack(BaseModel): pass

class UPS(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    status: bool
    battery_charge: int