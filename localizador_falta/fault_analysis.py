from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import numpy as np

from localizador_falta.comtrade_service import ComtradeData


PHASE_ALIASES = {
    "A": ("IA", "I_A", "CURRENTA", "I1"),
    "B": ("IB", "I_B", "CURRENTB", "I2"),
    "C": ("IC", "I_C", "CURRENTC", "I3"),
    "N": ("IN", "I0", "NEUTRAL", "RESIDUAL"),
    "VA": ("VA", "V_A", "V1"),
    "VB": ("VB", "V_B", "V2"),
    "VC": ("VC", "V_C", "V3"),
}


@dataclass
class SymmetricalComponents:
    i0: complex
    i1: complex
    i2: complex


@dataclass
class FaultReport:
    detected_fault: str
    probable_phase: str
    fault_start_s: float
    rms: Dict[str, float]
    symmetrical: SymmetricalComponents
    confidence: float


@dataclass
class DistanceEstimate:
    m_pu: float
    km_from_a: float
    km_from_b: float
    z1_app: complex


def _find_channel(analog: Dict[str, np.ndarray], aliases: tuple[str, ...]) -> np.ndarray:
    for alias in aliases:
        for key, value in analog.items():
            if alias in key:
                return value
    raise KeyError(f"Canal não encontrado para aliases={aliases}")


def _phasor(signal: np.ndarray, base_frequency: float, sample_rate: float) -> complex:
    n = len(signal)
    if n < 8:
        return 0 + 0j
    t = np.arange(n) / sample_rate
    kernel = np.exp(-1j * 2 * np.pi * base_frequency * t)
    return (2.0 / n) * np.dot(signal, kernel)


def _rms(signal: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(signal))))


def _classify_fault(rms: Dict[str, float], s: SymmetricalComponents) -> tuple[str, str, float]:
    ia, ib, ic = rms["IA"], rms["IB"], rms["IC"]
    in_ = rms.get("IN", 0.0)
    mags = np.array([ia, ib, ic])
    max_idx = int(np.argmax(mags))
    phase = ["A", "B", "C"][max_idx]

    neg = abs(s.i2)
    zero = abs(s.i0)
    pos = max(abs(s.i1), 1e-6)
    unbalance = neg / pos
    ground_factor = zero / pos

    if ground_factor > 0.35 and mags[max_idx] > 1.2 * np.mean(mags):
        return f"Fase-terra ({phase}-G)", phase, min(0.99, 0.70 + ground_factor)
    if unbalance > 0.40:
        two = np.argsort(mags)[-2:]
        pair = "".join(sorted(["A", "B", "C"][i] for i in two))
        if in_ > 0.15 * mags[max_idx]:
            return f"Bifásica-terra ({pair}-G)", pair, min(0.99, 0.65 + unbalance)
        return f"Bifásica ({pair})", pair, min(0.95, 0.60 + unbalance)
    if np.min(mags) > 0.8 * np.max(mags):
        return "Trifásica (ABC)", "ABC", 0.85
    return "Indeterminada", phase, 0.35


def _get_fault_window(data: ComtradeData) -> tuple[int, int]:
    ia = _find_channel(data.analog, PHASE_ALIASES["A"])
    ia_abs = np.abs(ia)
    threshold = np.mean(ia_abs) + 3 * np.std(ia_abs)
    starts = np.where(ia_abs > threshold)[0]
    start_idx = int(starts[0]) if len(starts) else 0

    cycle = int(max(16, round(data.sample_rate / data.frequency)))
    end_idx = min(len(ia), start_idx + cycle)
    return start_idx, end_idx


def analyze_fault(data: ComtradeData) -> FaultReport:
    ia = _find_channel(data.analog, PHASE_ALIASES["A"])
    ib = _find_channel(data.analog, PHASE_ALIASES["B"])
    ic = _find_channel(data.analog, PHASE_ALIASES["C"])

    try:
        in_ = _find_channel(data.analog, PHASE_ALIASES["N"])
    except KeyError:
        in_ = ia + ib + ic

    start_idx, end_idx = _get_fault_window(data)

    ia_w, ib_w, ic_w, in_w = ia[start_idx:end_idx], ib[start_idx:end_idx], ic[start_idx:end_idx], in_[start_idx:end_idx]

    ia_ph = _phasor(ia_w, data.frequency, data.sample_rate)
    ib_ph = _phasor(ib_w, data.frequency, data.sample_rate)
    ic_ph = _phasor(ic_w, data.frequency, data.sample_rate)

    a = np.exp(1j * 2 * np.pi / 3)
    i0 = (ia_ph + ib_ph + ic_ph) / 3
    i1 = (ia_ph + a * ib_ph + a**2 * ic_ph) / 3
    i2 = (ia_ph + a**2 * ib_ph + a * ic_ph) / 3

    rms = {"IA": _rms(ia_w), "IB": _rms(ib_w), "IC": _rms(ic_w), "IN": _rms(in_w)}

    detected, phase, confidence = _classify_fault(rms, SymmetricalComponents(i0=i0, i1=i1, i2=i2))

    return FaultReport(
        detected_fault=detected,
        probable_phase=phase,
        fault_start_s=float(data.time[start_idx]),
        rms=rms,
        symmetrical=SymmetricalComponents(i0=i0, i1=i1, i2=i2),
        confidence=confidence,
    )


def estimate_fault_distance(data: ComtradeData, z1_pos_ohm: complex, line_length_km: float) -> DistanceEstimate:
    if abs(z1_pos_ohm) < 1e-9:
        raise ValueError("Z1 positiva não pode ser zero.")
    if line_length_km <= 0:
        raise ValueError("Comprimento da LT deve ser maior que zero.")

    va = _find_channel(data.analog, PHASE_ALIASES["VA"])
    vb = _find_channel(data.analog, PHASE_ALIASES["VB"])
    vc = _find_channel(data.analog, PHASE_ALIASES["VC"])
    ia = _find_channel(data.analog, PHASE_ALIASES["A"])
    ib = _find_channel(data.analog, PHASE_ALIASES["B"])
    ic = _find_channel(data.analog, PHASE_ALIASES["C"])

    start_idx, end_idx = _get_fault_window(data)

    va_ph = _phasor(va[start_idx:end_idx], data.frequency, data.sample_rate)
    vb_ph = _phasor(vb[start_idx:end_idx], data.frequency, data.sample_rate)
    vc_ph = _phasor(vc[start_idx:end_idx], data.frequency, data.sample_rate)
    ia_ph = _phasor(ia[start_idx:end_idx], data.frequency, data.sample_rate)
    ib_ph = _phasor(ib[start_idx:end_idx], data.frequency, data.sample_rate)
    ic_ph = _phasor(ic[start_idx:end_idx], data.frequency, data.sample_rate)

    a = np.exp(1j * 2 * np.pi / 3)
    v1 = (va_ph + a * vb_ph + a**2 * vc_ph) / 3
    i1 = (ia_ph + a * ib_ph + a**2 * ic_ph) / 3

    if abs(i1) < 1e-9:
        raise ValueError("I1 muito baixa para cálculo de distância.")

    z1_app = v1 / i1
    m = np.clip(abs(z1_app) / abs(z1_pos_ohm), 0.0, 1.0)

    km_a = float(m * line_length_km)
    km_b = float((1.0 - m) * line_length_km)

    return DistanceEstimate(m_pu=float(m), km_from_a=km_a, km_from_b=km_b, z1_app=z1_app)


def get_available_channels(data: ComtradeData) -> List[str]:
    return sorted(data.analog.keys())
