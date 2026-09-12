import os
import re
from dataclasses import dataclass
from typing import Mapping

_OZON_PATTERN = re.compile(r"^OZON_CABINET_(\d+)_(NAME|CLIENT_ID|API_KEY)$")
_WB_PATTERN = re.compile(r"^WB_CABINET_(\d+)_(NAME|TOKEN)$")


@dataclass(frozen=True)
class OzonCabinet:
    cabinet_id: int
    name: str
    client_id: str
    api_key: str


@dataclass(frozen=True)
class WbCabinet:
    cabinet_id: int
    name: str
    token: str


def _group_by_cabinet(env: Mapping[str, str], pattern: re.Pattern) -> dict[int, dict[str, str]]:
    grouped: dict[int, dict[str, str]] = {}
    for key, value in env.items():
        match = pattern.match(key)
        if not match:
            continue
        cabinet_id = int(match.group(1))
        grouped.setdefault(cabinet_id, {})[match.group(2)] = value
    return grouped


def load_ozon_cabinets(env: Mapping[str, str] | None = None) -> list[OzonCabinet]:
    env = env if env is not None else os.environ
    grouped = _group_by_cabinet(env, _OZON_PATTERN)

    cabinets = []
    for cabinet_id, values in sorted(grouped.items()):
        if not {"NAME", "CLIENT_ID", "API_KEY"} <= values.keys():
            raise ValueError(f"OZON_CABINET_{cabinet_id} is missing required fields")
        cabinets.append(
            OzonCabinet(
                cabinet_id=cabinet_id,
                name=values["NAME"],
                client_id=values["CLIENT_ID"],
                api_key=values["API_KEY"],
            )
        )
    return cabinets


def load_wb_cabinets(env: Mapping[str, str] | None = None) -> list[WbCabinet]:
    env = env if env is not None else os.environ
    grouped = _group_by_cabinet(env, _WB_PATTERN)

    cabinets = []
    for cabinet_id, values in sorted(grouped.items()):
        if not {"NAME", "TOKEN"} <= values.keys():
            raise ValueError(f"WB_CABINET_{cabinet_id} is missing required fields")
        cabinets.append(WbCabinet(cabinet_id=cabinet_id, name=values["NAME"], token=values["TOKEN"]))
    return cabinets
