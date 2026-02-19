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
    z_app: complex
    loop_used: str


@dataclass
class NegativeSeqDistanceResult:
    terminal_s: str
    terminal_r: str
    m_pu: float
    km_from_s: float
    km_from_r: float
    z2lt: complex
    z2s: complex
    z2r: complex
    root_1: float
    root_2: float
    method_note: str
    selected_root: str


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


def _polar(mod: float, ang_deg: float) -> complex:
    return mod * np.exp(1j * np.radians(ang_deg))


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


def _fault_phasors(data: ComtradeData) -> dict[str, complex]:
    start_idx, end_idx = _get_fault_window(data)

    va = _find_channel(data.analog, PHASE_ALIASES["VA"])
    vb = _find_channel(data.analog, PHASE_ALIASES["VB"])
    vc = _find_channel(data.analog, PHASE_ALIASES["VC"])
    ia = _find_channel(data.analog, PHASE_ALIASES["A"])
    ib = _find_channel(data.analog, PHASE_ALIASES["B"])
    ic = _find_channel(data.analog, PHASE_ALIASES["C"])

    va_ph = _phasor(va[start_idx:end_idx], data.frequency, data.sample_rate)
    vb_ph = _phasor(vb[start_idx:end_idx], data.frequency, data.sample_rate)
    vc_ph = _phasor(vc[start_idx:end_idx], data.frequency, data.sample_rate)
    ia_ph = _phasor(ia[start_idx:end_idx], data.frequency, data.sample_rate)
    ib_ph = _phasor(ib[start_idx:end_idx], data.frequency, data.sample_rate)
    ic_ph = _phasor(ic[start_idx:end_idx], data.frequency, data.sample_rate)

    i0 = (ia_ph + ib_ph + ic_ph) / 3
    a = np.exp(1j * 2 * np.pi / 3)
    v1 = (va_ph + a * vb_ph + a**2 * vc_ph) / 3
    i1 = (ia_ph + a * ib_ph + a**2 * ic_ph) / 3

    return {
        "VA": va_ph,
        "VB": vb_ph,
        "VC": vc_ph,
        "IA": ia_ph,
        "IB": ib_ph,
        "IC": ic_ph,
        "I0": i0,
        "V1": v1,
        "I1": i1,
    }


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


def _distance_factor(z_app: complex, z1_pos_ohm_per_line: complex) -> float:
    denom = max(abs(z1_pos_ohm_per_line) ** 2, 1e-9)
    return float(np.real(z_app * np.conj(z1_pos_ohm_per_line)) / denom)


def estimate_fault_distance(
    data: ComtradeData,
    report: FaultReport,
    z1_pos_ohm_per_line: complex,
    line_length_km: float,
    z0_ohm_per_line: complex | None = None,
) -> DistanceEstimate:
    if abs(z1_pos_ohm_per_line) < 1e-9:
        raise ValueError("Z1 positiva não pode ser zero.")
    if line_length_km <= 0:
        raise ValueError("Comprimento da LT deve ser maior que zero.")

    z0 = z0_ohm_per_line if z0_ohm_per_line is not None else z1_pos_ohm_per_line
    k0 = (z0 - z1_pos_ohm_per_line) / (3 * z1_pos_ohm_per_line)

    p = _fault_phasors(data)
    fault = report.detected_fault.upper()

    if "FASE-TERRA" in fault:
        ph = report.probable_phase.upper()
        if ph == "A":
            z_app = p["VA"] / (p["IA"] + 3 * k0 * p["I0"])
            loop = "AG"
        elif ph == "B":
            z_app = p["VB"] / (p["IB"] + 3 * k0 * p["I0"])
            loop = "BG"
        else:
            z_app = p["VC"] / (p["IC"] + 3 * k0 * p["I0"])
            loop = "CG"
    elif "BIFÁSICA" in fault:
        pair = report.probable_phase.upper()
        if "AB" in pair:
            z_app = (p["VA"] - p["VB"]) / (p["IA"] - p["IB"])
            loop = "AB"
        elif "BC" in pair:
            z_app = (p["VB"] - p["VC"]) / (p["IB"] - p["IC"])
            loop = "BC"
        else:
            z_app = (p["VC"] - p["VA"]) / (p["IC"] - p["IA"])
            loop = "CA"
    else:
        if abs(p["I1"]) < 1e-9:
            raise ValueError("I1 muito baixa para cálculo de distância.")
        z_app = p["V1"] / p["I1"]
        loop = "SEQ1"

    m = np.clip(_distance_factor(z_app, z1_pos_ohm_per_line), 0.0, 1.2)
    km_a = float(min(max(m, 0.0), 1.0) * line_length_km)
    km_b = float(line_length_km - km_a)

    return DistanceEstimate(m_pu=float(m), km_from_a=km_a, km_from_b=km_b, z_app=z_app, loop_used=loop)


def estimate_negative_sequence_distance_two_terminal(
    terminal_s: str,
    terminal_r: str,
    z2lt_mod: float,
    z2lt_ang_deg: float,
    line_length_km: float,
    v2s_mod: float,
    v2s_ang_deg: float,
    i2s_mod: float,
    i2s_ang_deg: float,
    v2r_mod: float,
    v2r_ang_deg: float,
    i2r_mod: float,
    i2r_ang_deg: float,
) -> NegativeSeqDistanceResult:
    if line_length_km <= 0:
        raise ValueError("Comprimento da LT deve ser maior que zero.")
    if z2lt_mod <= 0:
        raise ValueError("Impedância total da LT deve ser maior que zero.")

    z2lt = _polar(z2lt_mod, z2lt_ang_deg)
    v2s = _polar(v2s_mod, v2s_ang_deg)
    i2s = _polar(i2s_mod, i2s_ang_deg)
    v2r = _polar(v2r_mod, v2r_ang_deg)
    i2r = _polar(i2r_mod, i2r_ang_deg)

    if abs(i2s) < 1e-9 or abs(i2r) < 1e-9:
        raise ValueError("I2 das extremidades deve ser diferente de zero.")

    z2s = v2s / i2s
    z2r = v2r / i2r

    # Forma equivalente à planilha: A*m² + B*m + C = 0
    # com parâmetros complexos a..h derivados de I2S*Z2S, I2S*Z2LT, Z2R+Z2LT, Z2LT
    k = abs(i2r) ** 2
    x = i2s * z2s
    y = i2s * z2lt
    u = z2r + z2lt
    w = z2lt

    a, b = np.real(x), np.imag(x)
    c, d = np.real(y), np.imag(y)
    e, f = np.real(u), np.imag(u)
    g, h = np.real(w), np.imag(w)

    A = k * (g * g + h * h) - (c * c + d * d)
    B = -2 * (k * (e * g + f * h) + (a * c + b * d))
    C = k * (e * e + f * f) - (a * a + b * b)

    if abs(A) < 1e-12:
        raise ValueError("Coeficiente A inválido para solução da equação de 2º grau.")

    minus_b = -B
    b_sq = B * B
    four_a_c = 4 * A * C
    disc = b_sq - four_a_c

    if disc >= 0:
        sqrt_disc = float(np.sqrt(disc))
        note = "modo planilha: Δ real"
    else:
        sqrt_disc = float(np.sqrt(abs(disc)))
        note = "modo planilha: Δ<0, usando |Δ| para raiz"

    two_a = 2 * A
    # Reproduz exatamente a lógica da planilha de referência enviada
    first_numerator = b_sq
    second_numerator = minus_b - sqrt_disc

    m1 = float(first_numerator / two_a)
    m2 = float(second_numerator / two_a)

    m = m1
    selected_root = "m1"
    km_s = m * line_length_km
    km_r = line_length_km - km_s

    return NegativeSeqDistanceResult(
        terminal_s=terminal_s or "S",
        terminal_r=terminal_r or "R",
        m_pu=float(m),
        km_from_s=float(km_s),
        km_from_r=float(km_r),
        z2lt=z2lt,
        z2s=z2s,
        z2r=z2r,
        root_1=m1,
        root_2=m2,
        method_note=note,
        selected_root=selected_root,
    )


def get_available_channels(data: ComtradeData) -> List[str]:
    return sorted(data.analog.keys())
