from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from localizador_falta.fault_analysis import FaultReport


@dataclass
class ProtectionDecision:
    ansi: str
    name: str
    operated: bool
    reason: str


ANSI_TABLE = {
    "21": "Distância",
    "24": "Sobre-excitação",
    "25": "Sincronismo",
    "27": "Subtensão",
    "32": "Direcional de potência",
    "46": "Sequência negativa",
    "47": "Sequência de tensão",
    "49": "Sobrecarga térmica",
    "50": "Sobrecorrente instantânea",
    "50N": "Sobrecorrente neutro instantânea",
    "51": "Sobrecorrente temporizada",
    "51N": "Sobrecorrente neutro temporizada",
    "59": "Sobretensão",
    "59N": "Sobretensão residual",
    "67": "Sobrecorrente direcional",
    "67N": "Sobrecorrente direcional de neutro",
    "79": "Religamento automático",
    "81": "Sub/Sobrefrequência",
    "87": "Diferencial",
}


def evaluate_protections(report: FaultReport, pickups: Dict[str, float] | None = None) -> List[ProtectionDecision]:
    pickups = pickups or {"phase": 1.5, "ground": 0.25, "negative": 0.30}
    i1 = max(abs(report.symmetrical.i1), 1e-6)
    i2_ratio = abs(report.symmetrical.i2) / i1
    i0_ratio = abs(report.symmetrical.i0) / i1

    phase_max = max(report.rms["IA"], report.rms["IB"], report.rms["IC"])
    neutral = report.rms["IN"]

    decisions: List[ProtectionDecision] = []

    decisions.append(
        ProtectionDecision("50", ANSI_TABLE["50"], phase_max > pickups["phase"], f"Imax={phase_max:.2f} pu")
    )
    decisions.append(
        ProtectionDecision("51", ANSI_TABLE["51"], phase_max > 1.1 * pickups["phase"], f"Imax={phase_max:.2f} pu")
    )
    decisions.append(
        ProtectionDecision("50N", ANSI_TABLE["50N"], neutral > pickups["ground"], f"In={neutral:.2f} pu")
    )
    decisions.append(
        ProtectionDecision("51N", ANSI_TABLE["51N"], neutral > 0.8 * pickups["ground"], f"In={neutral:.2f} pu")
    )
    decisions.append(
        ProtectionDecision("46", ANSI_TABLE["46"], i2_ratio > pickups["negative"], f"I2/I1={i2_ratio:.2f}")
    )
    decisions.append(
        ProtectionDecision("67", ANSI_TABLE["67"], "Bifásica" in report.detected_fault, f"Tipo={report.detected_fault}")
    )
    decisions.append(
        ProtectionDecision("67N", ANSI_TABLE["67N"], "terra" in report.detected_fault.lower(), f"I0/I1={i0_ratio:.2f}")
    )
    decisions.append(
        ProtectionDecision("21", ANSI_TABLE["21"], report.confidence > 0.75, f"Confiança={report.confidence:.2f}")
    )

    for code, name in ANSI_TABLE.items():
        if not any(d.ansi == code for d in decisions):
            decisions.append(ProtectionDecision(code, name, False, "Sem critério primário nesta versão"))

    return sorted(decisions, key=lambda d: d.ansi)
