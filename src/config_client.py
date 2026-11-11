from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
    )


class OfflineServer(StrictModel):
    retry: int = Field(ge=0)
    retryIntervalSec: int = Field(gt=0)
    tcpTimeoutSec: int = Field(gt=0)
    shutdown: bool


class Shutdown(StrictModel):
    percent: int = Field(default=100, ge=0, le=100)


class StopTask(StrictModel):
    name: str
    dependency: list[str] = Field(default_factory=list)
    percent: int = Field(ge=0, le=100)


class OnBattery(StrictModel):
    shutdown: Shutdown
    StopTask: list[StopTask]


class Config(StrictModel):
    schemaVersion: Literal["schema:0.0.1"]
    beep: bool
    offlineServer: OfflineServer
    OnBattery: OnBattery