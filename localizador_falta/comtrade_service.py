from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict

import numpy as np

from comtrade import Comtrade


@dataclass
class ComtradeData:
    cfg_path: Path
    dat_path: Path
    station_name: str
    frequency: float
    sample_rate: float
    time: np.ndarray
    analog: Dict[str, np.ndarray]
    status: Dict[str, np.ndarray]


def _normalize_channel_name(name: str) -> str:
    return "".join(ch for ch in name.upper().strip() if ch.isalnum() or ch in {"_", "-"})


def load_comtrade(cfg_path: str | Path, dat_path: str | Path) -> ComtradeData:
    cfg = Path(cfg_path)
    dat = Path(dat_path)

    if not cfg.exists() or not dat.exists():
        raise FileNotFoundError("Arquivo CFG ou DAT não encontrado.")

    recorder = Comtrade()
    recorder.load(str(cfg), str(dat))

    analog = {
        _normalize_channel_name(channel): np.asarray(values, dtype=float)
        for channel, values in zip(recorder.analog_channel_ids, recorder.analog)
    }
    status = {
        _normalize_channel_name(channel): np.asarray(values, dtype=int)
        for channel, values in zip(recorder.status_channel_ids, recorder.status)
    }

    time = np.asarray(recorder.time, dtype=float)
    if len(time) < 2:
        raise ValueError("Série temporal inválida no COMTRADE.")

    dt = float(np.mean(np.diff(time)))
    sample_rate = 1.0 / dt

    return ComtradeData(
        cfg_path=cfg,
        dat_path=dat,
        station_name=getattr(recorder, "station_name", "Sem nome") or "Sem nome",
        frequency=float(getattr(recorder, "frequency", 60.0) or 60.0),
        sample_rate=sample_rate,
        time=time,
        analog=analog,
        status=status,
    )
