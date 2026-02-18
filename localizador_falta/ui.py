from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from localizador_falta.ansi_protection import evaluate_protections
from localizador_falta.comtrade_service import ComtradeData, load_comtrade
from localizador_falta.fault_analysis import analyze_fault


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Localizador de Falta - Engenharia de Proteção")
        self.resize(1400, 900)

        self.current_data: ComtradeData | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        grid = QGridLayout(root)

        header = QGroupBox("Projeto COMTRADE")
        h = QHBoxLayout(header)
        self.cfg_label = QLabel("CFG: não selecionado")
        self.dat_label = QLabel("DAT: não selecionado")
        load_btn = QPushButton("Selecionar Arquivos")
        load_btn.clicked.connect(self.select_files)
        analyze_btn = QPushButton("Analisar Falta")
        analyze_btn.clicked.connect(self.run_analysis)
        h.addWidget(self.cfg_label)
        h.addWidget(self.dat_label)
        h.addWidget(load_btn)
        h.addWidget(analyze_btn)

        self.wave_plot = pg.PlotWidget(title="Curvas de Onda")
        self.wave_plot.addLegend()
        self.wave_plot.showGrid(x=True, y=True)

        self.info_box = QTextEdit()
        self.info_box.setReadOnly(True)

        self.sym_plot = pg.PlotWidget(title="Componentes Simétricas (magnitude)")
        self.sym_plot.showGrid(x=True, y=True)

        self.prot_table = QTableWidget(0, 4)
        self.prot_table.setHorizontalHeaderLabels(["ANSI", "Função", "Atuou", "Motivo"])
        self.prot_table.horizontalHeader().setStretchLastSection(True)

        grid.addWidget(header, 0, 0, 1, 2)
        grid.addWidget(self.wave_plot, 1, 0)
        grid.addWidget(self.sym_plot, 1, 1)
        grid.addWidget(self.info_box, 2, 0)
        grid.addWidget(self.prot_table, 2, 1)

    def select_files(self) -> None:
        cfg, _ = QFileDialog.getOpenFileName(self, "Selecione o arquivo CFG", str(Path.home()), "CFG Files (*.cfg)")
        if not cfg:
            return

        dat, _ = QFileDialog.getOpenFileName(self, "Selecione o arquivo DAT", str(Path(cfg).parent), "DAT Files (*.dat)")
        if not dat:
            return

        self.cfg_label.setText(f"CFG: {cfg}")
        self.dat_label.setText(f"DAT: {dat}")

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
            self.current_data = data
        except Exception as exc:
            QMessageBox.critical(self, "Erro na análise", str(exc))
            return

        self._draw_waveforms(data)
        self._draw_symmetrical(report)
        self._update_report(data, report)
        self._update_protections(protections)

    def _draw_waveforms(self, data: ComtradeData) -> None:
        self.wave_plot.clear()
        colors = [("IA", "r"), ("IB", "g"), ("IC", "b")]
        for key, color in colors:
            signal = next((v for k, v in data.analog.items() if key in k), None)
            if signal is not None:
                self.wave_plot.plot(data.time, signal, pen=pg.mkPen(color=color, width=1.4), name=key)

    def _draw_symmetrical(self, report) -> None:
        self.sym_plot.clear()
        labels = ["I0", "I1", "I2"]
        values = [abs(report.symmetrical.i0), abs(report.symmetrical.i1), abs(report.symmetrical.i2)]
        bars = pg.BarGraphItem(x=np.arange(3), height=values, width=0.6)
        self.sym_plot.addItem(bars)
        ax = self.sym_plot.getAxis("bottom")
        ax.setTicks([list(enumerate(labels))])

    def _update_report(self, data: ComtradeData, report) -> None:
        text = [
            "=== Resumo Técnico da Falta ===",
            f"Subestação: {data.station_name}",
            f"Frequência nominal: {data.frequency:.2f} Hz",
            f"Taxa de amostragem: {data.sample_rate:.2f} amostras/s",
            f"Tipo de falta: {report.detected_fault}",
            f"Fase provável: {report.probable_phase}",
            f"Início estimado: {report.fault_start_s:.4f} s",
            f"Confiança: {report.confidence:.2%}",
            "",
            "RMS por fase (pu aproximado):",
            f"IA={report.rms['IA']:.3f} | IB={report.rms['IB']:.3f} | IC={report.rms['IC']:.3f} | IN={report.rms['IN']:.3f}",
            "",
            "Componentes simétricas:",
            f"I0={abs(report.symmetrical.i0):.4f} ∠{np.degrees(np.angle(report.symmetrical.i0)):.1f}°",
            f"I1={abs(report.symmetrical.i1):.4f} ∠{np.degrees(np.angle(report.symmetrical.i1)):.1f}°",
            f"I2={abs(report.symmetrical.i2):.4f} ∠{np.degrees(np.angle(report.symmetrical.i2)):.1f}°",
        ]
        self.info_box.setText("\n".join(text))

    def _update_protections(self, protections) -> None:
        self.prot_table.setRowCount(len(protections))
        for row, p in enumerate(protections):
            state = "SIM" if p.operated else "NÃO"
            items = [p.ansi, p.name, state, p.reason]
            for col, value in enumerate(items):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignCenter if col != 3 else Qt.AlignLeft)
                if col == 2 and p.operated:
                    item.setBackground(Qt.darkGreen)
                    item.setForeground(Qt.white)
                self.prot_table.setItem(row, col, item)


def run_app() -> None:
    app = QApplication(sys.argv)
    pg.setConfigOptions(antialias=True)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
