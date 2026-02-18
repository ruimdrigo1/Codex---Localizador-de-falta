from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from localizador_falta.ansi_protection import ProtectionDecision, evaluate_protections
from localizador_falta.comtrade_service import ComtradeData, load_comtrade
from localizador_falta.fault_analysis import DistanceEstimate, FaultReport, analyze_fault, estimate_fault_distance


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Localizador de Falta - Proteção ANSI")
        self.resize(1650, 980)

        self.current_data: ComtradeData | None = None
        self._apply_theme()
        self._build_ui()

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background-color: #11151c; color: #d8e1ea; font-family: 'Segoe UI'; font-size: 10pt; }
            QGroupBox { border: 1px solid #2f3c4a; border-radius: 6px; margin-top: 12px; padding-top: 10px; font-weight: 600; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #8fc6ff; }
            QPushButton { background-color: #223245; border: 1px solid #2f5674; border-radius: 4px; padding: 7px 12px; color: #ecf4ff; font-weight: 600; }
            QPushButton:hover { background-color: #2c435c; }
            QPushButton:pressed { background-color: #1b2b3c; }
            QTextEdit, QListWidget, QTableWidget, QLineEdit { background-color: #0e131a; border: 1px solid #293645; border-radius: 4px; color: #d8e1ea; }
            QHeaderView::section { background-color: #1f2a36; color: #d8e1ea; border: 1px solid #33495f; padding: 5px; font-weight: 600; }
            QLabel#statusOk { color: #35d07f; font-weight: 700; }
            QLabel#statusWarn { color: #f4c95d; font-weight: 700; }
            """
        )

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        main_layout = QVBoxLayout(root)

        toolbar_box = QGroupBox("Aquisição COMTRADE")
        toolbar_layout = QHBoxLayout(toolbar_box)
        self.cfg_label = QLabel("CFG: não selecionado")
        self.dat_label = QLabel("DAT: não selecionado")
        load_btn = QPushButton("Selecionar Arquivos")
        load_btn.clicked.connect(self.select_files)
        analyze_btn = QPushButton("Analisar Falta")
        analyze_btn.clicked.connect(self.run_analysis)
        toolbar_layout.addWidget(self.cfg_label, 3)
        toolbar_layout.addWidget(self.dat_label, 3)
        toolbar_layout.addWidget(load_btn, 1)
        toolbar_layout.addWidget(analyze_btn, 1)

        distance_box = QGroupBox("Localização da Falta por Impedância Positiva")
        distance_layout = QHBoxLayout(distance_box)
        self.z1_mag_input = QLineEdit("12.0")
        self.z1_ang_input = QLineEdit("75.0")
        self.lt_len_input = QLineEdit("100.0")
        self.dist_result_label = QLabel("Distância: aguardando cálculo")
        self.dist_result_label.setObjectName("statusWarn")
        distance_layout.addWidget(QLabel("|Z1| (ohm):"))
        distance_layout.addWidget(self.z1_mag_input)
        distance_layout.addWidget(QLabel("∠Z1 (graus):"))
        distance_layout.addWidget(self.z1_ang_input)
        distance_layout.addWidget(QLabel("LT total (km):"))
        distance_layout.addWidget(self.lt_len_input)
        distance_layout.addWidget(self.dist_result_label, 3)

        main_splitter = QSplitter(Qt.Horizontal)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)

        plots_box = QGroupBox("Oscilografia")
        plots_layout = QVBoxLayout(plots_box)
        self.wave_plot = pg.PlotWidget(title="Curvas de Onda (IA/IB/IC)")
        self.wave_plot.addLegend(offset=(10, 10))
        self.wave_plot.showGrid(x=True, y=True, alpha=0.25)
        self.wave_plot.setBackground("#0b1016")
        self.wave_plot.setLabel("bottom", "Tempo", units="s")
        self.wave_plot.setLabel("left", "Corrente", units="A")

        self.digital_plot = pg.PlotWidget(title="Estados Digitais")
        self.digital_plot.showGrid(x=True, y=True, alpha=0.20)
        self.digital_plot.setBackground("#0b1016")
        self.digital_plot.setLabel("bottom", "Tempo", units="s")
        self.digital_plot.setLabel("left", "Estado")
        self.digital_plot.setYRange(-0.2, 3.2)

        plots_layout.addWidget(self.wave_plot, 3)
        plots_layout.addWidget(self.digital_plot, 2)

        lower_box = QGroupBox("Diagnóstico")
        lower_layout = QGridLayout(lower_box)
        self.sym_plot = pg.PlotWidget(title="Componentes Simétricas")
        self.sym_plot.showGrid(x=True, y=True, alpha=0.2)
        self.sym_plot.setBackground("#0b1016")
        self.gauge_box = QTextEdit()
        self.gauge_box.setReadOnly(True)
        lower_layout.addWidget(self.sym_plot, 0, 0)
        lower_layout.addWidget(self.gauge_box, 0, 1)

        left_layout.addWidget(plots_box, 3)
        left_layout.addWidget(lower_box, 2)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        events_box = QGroupBox("Eventos")
        events_layout = QVBoxLayout(events_box)
        self.events_list = QListWidget()
        events_layout.addWidget(self.events_list)

        summary_box = QGroupBox("Resumo de Engenharia")
        summary_layout = QVBoxLayout(summary_box)
        self.status_label = QLabel("Aguardando análise...")
        self.status_label.setObjectName("statusWarn")
        self.info_box = QTextEdit()
        self.info_box.setReadOnly(True)
        summary_layout.addWidget(self.status_label)
        summary_layout.addWidget(self.info_box)

        prot_box = QGroupBox("Proteções ANSI")
        prot_layout = QVBoxLayout(prot_box)
        self.prot_table = QTableWidget(0, 4)
        self.prot_table.setHorizontalHeaderLabels(["ANSI", "Função", "Atuou", "Motivo"])
        self.prot_table.horizontalHeader().setStretchLastSection(True)
        prot_layout.addWidget(self.prot_table)

        right_layout.addWidget(events_box, 2)
        right_layout.addWidget(summary_box, 3)
        right_layout.addWidget(prot_box, 3)

        main_splitter.addWidget(left_panel)
        main_splitter.addWidget(right_panel)
        main_splitter.setSizes([1150, 500])

        footer = QFrame()
        footer_layout = QHBoxLayout(footer)
        footer_layout.addWidget(QLabel("Modo: Engenharia de Proteção | ANSI Completo"))
        footer_layout.addStretch()
        footer_layout.addWidget(QLabel("Versão UX Profissional"))

        main_layout.addWidget(toolbar_box)
        main_layout.addWidget(distance_box)
        main_layout.addWidget(main_splitter, 1)
        main_layout.addWidget(footer)

    def select_files(self) -> None:
        cfg, _ = QFileDialog.getOpenFileName(self, "Selecione o arquivo CFG", str(Path.home()), "CFG Files (*.cfg)")
        if not cfg:
            return

        dat, _ = QFileDialog.getOpenFileName(self, "Selecione o arquivo DAT", str(Path(cfg).parent), "DAT Files (*.dat)")
        if not dat:
            return

        self.cfg_label.setText(f"CFG: {cfg}")
        self.dat_label.setText(f"DAT: {dat}")

    def _read_distance_inputs(self) -> tuple[complex, float]:
        try:
            z1_mag = float(self.z1_mag_input.text().replace(",", "."))
            z1_ang_deg = float(self.z1_ang_input.text().replace(",", "."))
            lt_len = float(self.lt_len_input.text().replace(",", "."))
        except ValueError as exc:
            raise ValueError("Campos de distância inválidos. Use números para |Z1|, ângulo e LT.") from exc

        z1 = z1_mag * np.exp(1j * np.radians(z1_ang_deg))
        return z1, lt_len

    def _update_distance_panel(self, result: DistanceEstimate) -> None:
        self.dist_result_label.setObjectName("statusOk")
        self.dist_result_label.setText(
            f"A: {result.km_from_a:.2f} km | B: {result.km_from_b:.2f} km | m={result.m_pu:.3f} pu | Zapp={abs(result.z1_app):.2f}∠{np.degrees(np.angle(result.z1_app)):.1f}°"
        )
        self.dist_result_label.style().unpolish(self.dist_result_label)
        self.dist_result_label.style().polish(self.dist_result_label)

    def run_analysis(self) -> None:
        cfg_text = self.cfg_label.text().replace("CFG: ", "")
        dat_text = self.dat_label.text().replace("DAT: ", "")
        if "não selecionado" in cfg_text or "não selecionado" in dat_text:
            QMessageBox.warning(self, "Atenção", "Selecione os arquivos CFG e DAT.")
            return

        try:
            data = load_comtrade(cfg_text, dat_text)
            report = analyze_fault(data)
            protections = evaluate_protections(report)
            z1, lt_len = self._read_distance_inputs()
            distance = estimate_fault_distance(data, z1, lt_len)
            self.current_data = data
        except Exception as exc:
            QMessageBox.critical(self, "Erro na análise", str(exc))
            self.status_label.setText("Falha na análise")
            self.status_label.setObjectName("statusWarn")
            self.status_label.style().unpolish(self.status_label)
            self.status_label.style().polish(self.status_label)
            self.dist_result_label.setObjectName("statusWarn")
            self.dist_result_label.setText("Distância: não calculada")
            self.dist_result_label.style().unpolish(self.dist_result_label)
            self.dist_result_label.style().polish(self.dist_result_label)
            return

        self._draw_waveforms(data)
        self._draw_digital(data)
        self._draw_symmetrical(report)
        self._update_report(data, report)
        self._update_protections(protections)
        self._update_events(data, report, protections, distance)
        self._update_distance_panel(distance)

    def _draw_waveforms(self, data: ComtradeData) -> None:
        self.wave_plot.clear()
        colors = [("IA", "#ff4d4d"), ("IB", "#77dd77"), ("IC", "#62a8ff")]
        for key, color in colors:
            signal = next((v for k, v in data.analog.items() if key in k), None)
            if signal is not None:
                self.wave_plot.plot(data.time, signal, pen=pg.mkPen(color=color, width=1.6), name=key)

    def _draw_digital(self, data: ComtradeData) -> None:
        self.digital_plot.clear()
        if not data.status:
            self.digital_plot.plot([0], [0], pen=pg.mkPen(color="#5b6875", width=1))
            return

        for idx, (name, states) in enumerate(list(data.status.items())[:3]):
            y = states.astype(float) + idx
            self.digital_plot.plot(
                data.time,
                y,
                pen=pg.mkPen(color=["#8ab4f8", "#f9ab00", "#34a853"][idx], width=1.3),
                stepMode="left",
                name=name,
            )

    def _draw_symmetrical(self, report: FaultReport) -> None:
        self.sym_plot.clear()
        labels = ["I0", "I1", "I2"]
        values = [abs(report.symmetrical.i0), abs(report.symmetrical.i1), abs(report.symmetrical.i2)]
        brushes = [pg.mkBrush("#00bcd4"), pg.mkBrush("#4caf50"), pg.mkBrush("#ff9800")]
        bars = pg.BarGraphItem(x=np.arange(3), height=values, width=0.6, brushes=brushes)
        self.sym_plot.addItem(bars)
        self.sym_plot.getAxis("bottom").setTicks([list(enumerate(labels))])

    def _update_report(self, data: ComtradeData, report: FaultReport) -> None:
        self.status_label.setText(f"FALTA DETECTADA: {report.detected_fault} | Fase: {report.probable_phase}")
        self.status_label.setObjectName("statusOk")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

        text = [
            "=== Resumo Técnico ===",
            f"Subestação: {data.station_name}",
            f"Frequência nominal: {data.frequency:.2f} Hz",
            f"Taxa de amostragem: {data.sample_rate:.2f} amostras/s",
            f"Tipo de falta: {report.detected_fault}",
            f"Fase provável: {report.probable_phase}",
            f"Início estimado: {report.fault_start_s:.4f} s",
            f"Confiança da classificação: {report.confidence:.2%}",
            "",
            "RMS (pu aproximado):",
            f"IA={report.rms['IA']:.3f} | IB={report.rms['IB']:.3f} | IC={report.rms['IC']:.3f} | IN={report.rms['IN']:.3f}",
            "",
            "Componentes simétricas:",
            f"I0={abs(report.symmetrical.i0):.4f} ∠{np.degrees(np.angle(report.symmetrical.i0)):.1f}°",
            f"I1={abs(report.symmetrical.i1):.4f} ∠{np.degrees(np.angle(report.symmetrical.i1)):.1f}°",
            f"I2={abs(report.symmetrical.i2):.4f} ∠{np.degrees(np.angle(report.symmetrical.i2)):.1f}°",
        ]
        self.info_box.setText("\n".join(text))

        i1 = max(abs(report.symmetrical.i1), 1e-6)
        i2_ratio = abs(report.symmetrical.i2) / i1
        i0_ratio = abs(report.symmetrical.i0) / i1
        self.gauge_box.setText(
            "\n".join(
                [
                    "=== Indicadores Vetoriais ===",
                    f"Desequilíbrio (I2/I1): {i2_ratio:.3f}",
                    f"Componente Homopolar (I0/I1): {i0_ratio:.3f}",
                    f"Ângulo I1: {np.degrees(np.angle(report.symmetrical.i1)):.2f}°",
                    f"Ângulo I2: {np.degrees(np.angle(report.symmetrical.i2)):.2f}°",
                ]
            )
        )

    def _update_protections(self, protections: list[ProtectionDecision]) -> None:
        self.prot_table.setRowCount(len(protections))
        for row, p in enumerate(protections):
            state = "SIM" if p.operated else "NÃO"
            items = [p.ansi, p.name, state, p.reason]
            for col, value in enumerate(items):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignCenter if col != 3 else Qt.AlignLeft)
                if col == 2:
                    if p.operated:
                        item.setBackground(QColor("#1f6f43"))
                        item.setForeground(QColor("#e7ffe7"))
                    else:
                        item.setBackground(QColor("#4a2020"))
                        item.setForeground(QColor("#ffdede"))
                self.prot_table.setItem(row, col, item)

    def _update_events(
        self,
        data: ComtradeData,
        report: FaultReport,
        protections: list[ProtectionDecision],
        distance: DistanceEstimate,
    ) -> None:
        self.events_list.clear()
        events = [
            f"[T={report.fault_start_s:.4f}s] Início de distúrbio detectado",
            f"Tipo de falta identificado: {report.detected_fault}",
            f"Fase provável: {report.probable_phase}",
            f"Distância estimada: A={distance.km_from_a:.2f} km | B={distance.km_from_b:.2f} km",
            f"Canal digital monitorado: {len(data.status)}",
        ]

        acted = [p for p in protections if p.operated]
        if acted:
            events.extend(f"Atuação {p.ansi} - {p.name} ({p.reason})" for p in acted)
        else:
            events.append("Nenhuma proteção acima dos critérios configurados")

        for event in events:
            self.events_list.addItem(QListWidgetItem(event))


def run_app() -> None:
    app = QApplication(sys.argv)
    pg.setConfigOptions(antialias=True)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
