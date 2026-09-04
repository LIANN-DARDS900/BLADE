from __future__ import annotations

from datetime import datetime
import html
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QEasingCurve, QRectF, Qt, QTimer, QPropertyAnimation
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .audit import AuditLogger
from .constants import APP_AUTHOR, APP_NAME, APP_VERSION, POWERSHELL_SCRIPT
from .models import OperationResult
from .powershell import PowerShellRunner
from .responsive import should_use_compact_layout
from .worker import WorkflowWorker


COLORS = {
    # Neutral, ChatGPT-inspired dark palette. Status colors are intentionally
    # reserved for health and warning meaning rather than decoration.
    "bg": "#111111",
    "surface": "#1B1B1B",
    "surface_alt": "#232323",
    "surface_hover": "#292929",
    "border": "#343434",
    "text": "#F2F2F2",
    "muted": "#A3A3A3",
    "blue": "#D7D7D7",
    "cyan": "#D7D7D7",
    "green": "#5ED6A0",
    "amber": "#E8B96A",
    "red": "#F17A86",
    "violet": "#BDBDBD",
}

STATUS_COLORS = {
    "ready": COLORS["green"],
    "success": COLORS["green"],
    "ok": COLORS["green"],
    "running": COLORS["blue"],
    "step": COLORS["violet"],
    "waiting": COLORS["amber"],
    "warning": COLORS["amber"],
    "blocked": COLORS["red"],
    "failed": COLORS["red"],
    "error": COLORS["red"],
    "unknown": COLORS["muted"],
    "cancelled": COLORS["muted"],
    "info": "#C9D6E8",
}


def rgba(hex_color: str, alpha: float) -> str:
    value = hex_color.lstrip("#")
    if len(value) != 6:
        return hex_color
    red, green, blue = (int(value[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({red}, {green}, {blue}, {alpha:.3f})"


PIPELINE_STAGES = [
    ("PREFLIGHT", "Pre-flight"),
    ("SCCM_HEALTH", "SCCM"),
    ("POLICY_SYNC", "Policy sync"),
    ("GROUP_POLICY", "Group policy"),
    ("POLICY_WAIT", "Policy arrival"),
    ("BITLOCKER_MONITOR", "Encryption"),
    ("SUCCESS", "Complete"),
]


class StatusBadge(QLabel):
    def __init__(self, text: str = "CHECKING", status: str = "unknown") -> None:
        super().__init__(text)
        self.setAlignment(Qt.AlignCenter)
        self.set_status(text, status)

    def set_status(self, text: str, status: str) -> None:
        color = STATUS_COLORS.get(status, STATUS_COLORS["unknown"])
        self.setText(text.upper())
        self.setStyleSheet(
            f"background: {rgba(color, 0.13)}; color: {color}; border: 1px solid {rgba(color, 0.40)}; "
            "border-radius: 10px; padding: 3px 8px; font-size: 10px; font-weight: 800;"
        )


class MetricCard(QFrame):
    def __init__(self, symbol: str, title: str, value: str = "Checking…") -> None:
        super().__init__()
        self.setObjectName("metricCard")
        self.setMinimumHeight(126)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 13, 15, 13)
        layout.setSpacing(7)

        top = QHBoxLayout()
        top.setSpacing(9)
        self.symbol = QLabel(symbol)
        self.symbol.setObjectName("metricSymbol")
        self.symbol.setAlignment(Qt.AlignCenter)
        self.symbol.setFixedSize(34, 34)

        title_label = QLabel(title.upper())
        title_label.setObjectName("eyebrow")
        title_label.setWordWrap(False)

        self.badge = StatusBadge()
        self.badge.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        top.addWidget(self.symbol)
        top.addWidget(title_label, 1)
        top.addWidget(self.badge, 0, Qt.AlignTop)

        self.value_label = QLabel(value)
        self.value_label.setObjectName("metricValue")
        self.value_label.setWordWrap(False)
        self.value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.detail_label = QLabel("")
        self.detail_label.setObjectName("metricDetail")
        self.detail_label.setWordWrap(True)
        self.detail_label.setMinimumHeight(30)

        layout.addLayout(top)
        layout.addWidget(self.value_label)
        layout.addWidget(self.detail_label)

    def set_status(self, value: str, detail: str = "", status: str = "unknown", badge: str | None = None) -> None:
        self.value_label.setText(value)
        self.value_label.setToolTip(value)
        self.detail_label.setText(detail)
        self.detail_label.setToolTip(detail)
        self.value_label.setStyleSheet(f"color: {STATUS_COLORS.get(status, COLORS['text'])}; background: transparent;")
        self.badge.set_status(badge or status, status)


class CircularProgress(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._value = 0
        self._caption = "Readiness"
        self.setMinimumSize(190, 190)
        self.setMaximumSize(225, 225)
        self.animation = QPropertyAnimation(self, b"value", self)
        self.animation.setDuration(650)
        self.animation.setEasingCurve(QEasingCurve.OutCubic)

    def get_value(self) -> int:
        return self._value

    def set_value(self, value: int) -> None:
        self._value = max(0, min(100, int(value)))
        self.update()

    value = Property(int, get_value, set_value)

    def animate_to(self, value: int) -> None:
        self.animation.stop()
        self.animation.setStartValue(self._value)
        self.animation.setEndValue(max(0, min(100, int(value))))
        self.animation.start()

    def set_caption(self, caption: str) -> None:
        self._caption = caption
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        side = min(self.width(), self.height())
        margin = 18
        rect = QRectF(
            (self.width() - side) / 2 + margin,
            (self.height() - side) / 2 + margin,
            side - margin * 2,
            side - margin * 2,
        )
        painter.setPen(QPen(QColor("#303030"), 12, Qt.SolidLine, Qt.RoundCap))
        painter.drawArc(rect, 0, 360 * 16)
        accent = COLORS["green"] if self._value == 100 else "#D0D0D0"
        painter.setPen(QPen(QColor(accent), 12, Qt.SolidLine, Qt.RoundCap))
        painter.drawArc(rect, 90 * 16, -int(360 * 16 * self._value / 100))
        painter.setPen(QColor(COLORS["text"]))
        value_font = QFont("Segoe UI", 27, QFont.Bold)
        painter.setFont(value_font)
        painter.drawText(rect.adjusted(0, 18, 0, -10), Qt.AlignCenter, f"{self._value}%")
        painter.setPen(QColor(COLORS["muted"]))
        painter.setFont(QFont("Segoe UI", 9, QFont.DemiBold))
        painter.drawText(rect.adjusted(0, 62, 0, 0), Qt.AlignCenter, self._caption.upper())


class PipelineStep(QFrame):
    def __init__(self, number: int, title: str) -> None:
        super().__init__()
        self.setObjectName("pipelineStep")
        self.key = ""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(5)
        self.dot = QLabel(str(number))
        self.dot.setAlignment(Qt.AlignCenter)
        self.dot.setFixedSize(28, 28)
        self.label = QLabel(title)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setWordWrap(True)
        self.label.setObjectName("pipelineLabel")
        layout.addWidget(self.dot, 0, Qt.AlignCenter)
        layout.addWidget(self.label)
        self.set_state("pending")

    def set_state(self, state: str) -> None:
        if state == "complete":
            color = COLORS["green"]
            text = "✓"
            border = color
        elif state == "active":
            color = COLORS["blue"]
            text = "●"
            border = COLORS["cyan"]
        elif state == "blocked":
            color = COLORS["red"]
            text = "!"
            border = color
        else:
            color = COLORS["muted"]
            text = self.dot.text() if self.dot.text().isdigit() else "·"
            border = COLORS["border"]
        self.dot.setText(text)
        self.dot.setStyleSheet(
            f"background:{rgba(color, 0.13)};color:{color};border:1px solid {border};"
            "border-radius:14px;font-weight:900;"
        )
        self.label.setStyleSheet(f"color:{color if state != 'pending' else COLORS['muted']};")
        self.setStyleSheet(
            f"QFrame#pipelineStep{{background:{COLORS['surface_alt'] if state == 'active' else 'transparent'};"
            f"border:1px solid {border if state == 'active' else 'transparent'};border-radius:10px;}}"
        )


class PipelineWidget(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("pipelinePanel")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(2)
        self.steps: dict[str, PipelineStep] = {}
        for index, (key, label) in enumerate(PIPELINE_STAGES, start=1):
            step = PipelineStep(index, label)
            step.key = key
            self.steps[key] = step
            layout.addWidget(step, 1)
            if index < len(PIPELINE_STAGES):
                connector = QFrame()
                connector.setFixedHeight(1)
                connector.setStyleSheet(f"background:{COLORS['border']};")
                connector.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                layout.addWidget(connector)
        self.set_stage("PREFLIGHT")

    def set_stage(self, stage: str, terminal_state: str | None = None) -> None:
        keys = [key for key, _ in PIPELINE_STAGES]
        normalized = stage.upper()
        if normalized == "PAUSED":
            return
        aliases = {
            "SCCM_REPAIR": "SCCM_HEALTH",
            "CCMEVAL_RUNNING": "SCCM_HEALTH",
            "SCCM_REPAIR_RUNNING": "SCCM_HEALTH",
            "BITLOCKER_WAITING": "POLICY_WAIT",
            "ENCRYPTING": "BITLOCKER_MONITOR",
            "READY": "PREFLIGHT",
        }
        normalized = aliases.get(normalized, normalized)
        active_index = keys.index(normalized) if normalized in keys else 0
        for index, key in enumerate(keys):
            if terminal_state == "success":
                state = "complete"
            elif terminal_state in {"blocked", "failed"} and index == active_index:
                state = "blocked"
            elif index < active_index:
                state = "complete"
            elif index == active_index:
                state = "active"
            else:
                state = "pending"
            self.steps[key].set_state(state)


class ReadinessRow(QFrame):
    def __init__(self, name: str, state: str, detail: str, status: str) -> None:
        super().__init__()
        self.setObjectName("readinessRow")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(10)
        color = STATUS_COLORS.get(status, COLORS["muted"])
        icon = QLabel("✓" if status in {"ready", "success", "ok"} else "!" if status in {"warning", "waiting"} else "×")
        icon.setAlignment(Qt.AlignCenter)
        icon.setFixedSize(26, 26)
        icon.setStyleSheet(
            f"background:{rgba(color, 0.13)};color:{color};border:1px solid {rgba(color, 0.33)};border-radius:13px;font-weight:900;"
        )
        labels = QVBoxLayout()
        labels.setSpacing(1)
        title = QLabel(name)
        title.setObjectName("readinessName")
        detail_label = QLabel(detail)
        detail_label.setObjectName("readinessDetail")
        detail_label.setWordWrap(True)
        labels.addWidget(title)
        labels.addWidget(detail_label)
        badge = StatusBadge(state, status)
        layout.addWidget(icon)
        layout.addLayout(labels, 1)
        layout.addWidget(badge)


class ReadinessList(QScrollArea):
    def __init__(self) -> None:
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.container = QWidget()
        self.layout_box = QVBoxLayout(self.container)
        self.layout_box.setContentsMargins(0, 0, 4, 0)
        self.layout_box.setSpacing(7)
        self.layout_box.addStretch()
        self.setWidget(self.container)

    def populate(self, checks: list[dict[str, Any]]) -> None:
        while self.layout_box.count():
            item = self.layout_box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for check in checks:
            self.layout_box.addWidget(
                ReadinessRow(
                    str(check.get("name", "Check")),
                    str(check.get("state", "Unknown")),
                    str(check.get("detail", "")),
                    str(check.get("status", "unknown")),
                )
            )
        self.layout_box.addStretch()


class SectionCard(QFrame):
    def __init__(self, title: str, subtitle: str = "") -> None:
        super().__init__()
        self.setObjectName("sectionCard")
        self.layout_box = QVBoxLayout(self)
        self.layout_box.setContentsMargins(17, 16, 17, 16)
        self.layout_box.setSpacing(10)
        header = QVBoxLayout()
        header.setSpacing(2)
        title_label = QLabel(title.upper())
        title_label.setObjectName("sectionTitle")
        header.addWidget(title_label)
        if subtitle:
            subtitle_label = QLabel(subtitle)
            subtitle_label.setObjectName("sectionSubtitle")
            subtitle_label.setWordWrap(True)
            header.addWidget(subtitle_label)
        self.layout_box.addLayout(header)


class MainWindow(QMainWindow):
    def __init__(self, config: dict[str, Any], is_admin: bool) -> None:
        super().__init__()
        self.config = config
        self.is_admin = is_admin
        self.runner = PowerShellRunner(POWERSHELL_SCRIPT)
        self.worker: WorkflowWorker | None = None
        self.paused = False
        self.last_results: dict[str, OperationResult] = {}
        self.minimum_ready = False
        self.sccm_installed = False
        self.current_workflow = ""
        self.current_stage_key = "PREFLIGHT"
        self.compact_mode: bool | None = None
        self.last_corporate_network_likely = False
        self.last_ac_connected = True
        self.audit = AuditLogger()
        self.setWindowTitle(f"{APP_NAME} — {APP_VERSION}")
        self.setMinimumSize(980, 680)
        self.resize(1480, 900)
        self._build_ui()
        self._apply_style()
        self.audit.write_event("Application launched.", "info", version=APP_VERSION, administrator=self.is_admin)
        QTimer.singleShot(0, self._apply_responsive_layout)
        QTimer.singleShot(250, self.run_preflight)

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(212)
        side = QVBoxLayout(self.sidebar)
        self.sidebar_layout = side
        side.setContentsMargins(18, 20, 18, 16)
        side.setSpacing(8)
        self.product_label = QLabel("BITLOCKER\nASSISTANT")
        self.product_label.setObjectName("productName")
        self.brand_name_label = QLabel("CONTROLLED INTERNAL TOOL")
        self.brand_name_label.setObjectName("brandName")
        side.addWidget(self.product_label)
        side.addWidget(self.brand_name_label)
        side.addSpacing(18)
        self.nav_buttons: dict[str, QPushButton] = {}
        self.nav_labels: dict[str, str] = {}
        nav_items = [("dashboard", "01   Dashboard"), ("diagnostics", "02   Diagnostics"), ("activity", "03   Activity"), ("about", "04   About")]
        for key, label in nav_items:
            button = QPushButton(label)
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, page=key: self._switch_page(page))
            side.addWidget(button)
            self.nav_buttons[key] = button
            self.nav_labels[key] = label
        side.addStretch()
        self.safety_label = QLabel("SAFE MODE\nNo direct BitLocker modification")
        self.safety_label.setObjectName("safetyBadge")
        self.safety_label.setWordWrap(True)
        side.addWidget(self.safety_label)
        self.author_label = QLabel(f"Designed & engineered by\n{APP_AUTHOR}")
        self.author_label.setObjectName("signature")
        self.author_label.setWordWrap(True)
        side.addWidget(self.author_label)
        root_layout.addWidget(self.sidebar)
        shell = QWidget()
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)
        header = QFrame()
        header.setObjectName("header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(24, 14, 24, 14)
        header_text = QVBoxLayout()
        header_text.setSpacing(1)
        self.page_title = QLabel("Deployment dashboard")
        self.page_title.setObjectName("pageTitle")
        self.page_subtitle = QLabel("Prepare SCCM, request enterprise policy and monitor encryption safely.")
        self.page_subtitle.setObjectName("pageSubtitle")
        header_text.addWidget(self.page_title)
        header_text.addWidget(self.page_subtitle)
        header_layout.addLayout(header_text)
        header_layout.addStretch()
        version = QLabel(APP_VERSION.upper())
        version.setObjectName("versionBadge")
        self.admin_badge = StatusBadge("ADMINISTRATOR" if self.is_admin else "NOT ELEVATED", "ready" if self.is_admin else "blocked")
        header_layout.addWidget(version)
        header_layout.addSpacing(8)
        header_layout.addWidget(self.admin_badge)
        shell_layout.addWidget(header)
        self.pages = QStackedWidget()
        self.pages.setObjectName("pages")
        self.page_map: dict[str, int] = {}
        self.page_map["dashboard"] = self.pages.addWidget(self._build_dashboard_page())
        self.page_map["diagnostics"] = self.pages.addWidget(self._build_diagnostics_page())
        self.page_map["activity"] = self.pages.addWidget(self._build_activity_page())
        self.page_map["about"] = self.pages.addWidget(self._build_about_page())
        shell_layout.addWidget(self.pages, 1)
        footer = QFrame()
        footer.setObjectName("footer")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(24, 7, 24, 7)
        self.footer_status = QLabel("Detection starting…")
        self.footer_status.setObjectName("footerStatus")
        footer_signature = QLabel(f"Controlled internal IT tooling • {APP_AUTHOR}")
        footer_signature.setObjectName("footerSignature")
        footer_layout.addWidget(self.footer_status)
        footer_layout.addStretch()
        footer_layout.addWidget(footer_signature)
        shell_layout.addWidget(footer)
        root_layout.addWidget(shell, 1)
        self.setCentralWidget(root)
        self._switch_page("dashboard")

    def _build_dashboard_page(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setObjectName("dashboardScroll")
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(14)
        self.cards_layout = QGridLayout()
        self.cards_layout.setSpacing(11)
        self.machine_card = MetricCard("PC", "Machine")
        self.network_card = MetricCard("LAN", "Ethernet / network")
        self.sccm_card = MetricCard("CM", "SCCM client")
        self.bitlocker_card = MetricCard("BL", "BitLocker")
        self.metric_cards = [self.machine_card, self.network_card, self.sccm_card, self.bitlocker_card]
        for index, card in enumerate(self.metric_cards):
            self.cards_layout.addWidget(card, 0, index)
            self.cards_layout.setColumnStretch(index, 1)
        layout.addLayout(self.cards_layout)
        self.dashboard_main_layout = QGridLayout()
        self.dashboard_main_layout.setSpacing(14)
        self.journey_card = SectionCard("Deployment journey", "Focused policy delivery with safe pause and cancellation boundaries.")
        journey_body = QHBoxLayout()
        journey_body.setSpacing(18)
        self.progress_ring = CircularProgress()
        journey_body.addWidget(self.progress_ring, 0, Qt.AlignCenter)
        stage_box = QVBoxLayout()
        stage_box.setSpacing(8)
        self.stage_badge = StatusBadge("DETECTING", "running")
        self.stage_badge.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.stage_label = QLabel("Starting pre-flight detection")
        self.stage_label.setObjectName("heroStage")
        self.stage_detail = QLabel("Nothing changes during the initial detection.")
        self.stage_detail.setObjectName("heroDetail")
        self.stage_detail.setWordWrap(True)
        self.pipeline = PipelineWidget()
        stage_box.addWidget(self.stage_badge, 0, Qt.AlignLeft)
        stage_box.addWidget(self.stage_label)
        stage_box.addWidget(self.stage_detail)
        stage_box.addSpacing(5)
        stage_box.addWidget(self.pipeline)
        stage_box.addStretch()
        journey_body.addLayout(stage_box, 1)
        self.journey_card.layout_box.addLayout(journey_body)
        controls_line = QHBoxLayout()
        controls_line.setSpacing(8)
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Dry run / evidence only", "dry_run")
        self.mode_combo.addItem("Fast deployment", "fast")
        self.mode_combo.addItem("Adaptive SCCM refresh", "full")
        self.mode_combo.setToolTip("Dry run is read-only. Fast deployment uses focused policy actions. Adaptive refresh runs broader SCCM actions and skips only schedules the client reports as unsupported.")
        self.mode_combo.currentIndexChanged.connect(self._mode_changed)
        self.start_button = QPushButton("Run dry check")
        self.start_button.setObjectName("primaryButton")
        self.start_button.setEnabled(False)
        self.start_button.clicked.connect(self.start_deployment)
        self.pause_button = QPushButton("Pause")
        self.pause_button.setEnabled(False)
        self.pause_button.clicked.connect(self.toggle_pause)
        self.cancel_button = QPushButton("Cancel safely")
        self.cancel_button.setObjectName("dangerButton")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_workflow)
        controls_line.addWidget(self.mode_combo, 2)
        controls_line.addWidget(self.start_button, 2)
        controls_line.addWidget(self.pause_button, 1)
        controls_line.addWidget(self.cancel_button, 1)
        self.journey_card.layout_box.addLayout(controls_line)
        self.readiness_card = SectionCard("Readiness", "Minimum requirements are checked before any action begins.")
        self.readiness_list = ReadinessList()
        self.readiness_list.setMinimumHeight(260)
        self.readiness_card.layout_box.addWidget(self.readiness_list, 1)
        quick_actions = QHBoxLayout()
        self.recheck_button = QPushButton("Recheck")
        self.recheck_button.clicked.connect(self.run_preflight)
        self.repair_button = QPushButton("Repair SCCM")
        self.repair_button.clicked.connect(self.repair_sccm)
        quick_actions.addWidget(self.recheck_button)
        quick_actions.addWidget(self.repair_button)
        self.readiness_card.layout_box.addLayout(quick_actions)
        self.dashboard_main_layout.addWidget(self.journey_card, 0, 0)
        self.dashboard_main_layout.addWidget(self.readiness_card, 0, 1)
        self.dashboard_main_layout.setColumnStretch(0, 7)
        self.dashboard_main_layout.setColumnStretch(1, 4)
        layout.addLayout(self.dashboard_main_layout)
        self.activity_card = SectionCard("Live activity", "Latest events from the controlled workflow.")
        activity_head = QHBoxLayout()
        self.activity_preview_status = QLabel("Waiting for events")
        self.activity_preview_status.setObjectName("activityHint")
        view_all = QPushButton("Open activity")
        view_all.clicked.connect(lambda: self._switch_page("activity"))
        activity_head.addWidget(self.activity_preview_status)
        activity_head.addStretch()
        activity_head.addWidget(view_all)
        self.activity_card.layout_box.addLayout(activity_head)
        self.activity_preview = QListWidget()
        self.activity_preview.setObjectName("activityPreview")
        self.activity_preview.setMaximumHeight(132)
        self.activity_card.layout_box.addWidget(self.activity_preview)
        layout.addWidget(self.activity_card)
        layout.addStretch(1)
        scroll.setWidget(page)
        return scroll

    def _build_diagnostics_page(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(14)
        self.diagnostics_top_layout = QGridLayout()
        self.diagnostics_top_layout.setSpacing(14)
        self.diagnostic_summary_card = SectionCard("Diagnostic summary", "Read-only machine health and recommended technician actions.")
        self.diagnostic_state = QLabel("Detection has not completed yet.")
        self.diagnostic_state.setObjectName("diagnosticHero")
        self.diagnostic_advice = QLabel("Run a readiness check to generate a machine-specific diagnosis.")
        self.diagnostic_advice.setObjectName("heroDetail")
        self.diagnostic_advice.setWordWrap(True)
        self.diagnostic_summary_card.layout_box.addWidget(self.diagnostic_state)
        self.diagnostic_summary_card.layout_box.addWidget(self.diagnostic_advice)
        self.diagnostic_summary_card.layout_box.addStretch()
        diag_actions = QHBoxLayout()
        self.diag_recheck_button = QPushButton("Run diagnosis")
        self.diag_recheck_button.clicked.connect(self.run_preflight)
        self.diag_dry_button = QPushButton("Collect dry-run evidence")
        self.diag_dry_button.clicked.connect(self._start_dry_run_from_diagnostics)
        self.diag_repair_button = QPushButton("Safe SCCM repair")
        self.diag_repair_button.setEnabled(False)
        self.diag_repair_button.clicked.connect(self.repair_sccm)
        diag_actions.addWidget(self.diag_recheck_button)
        diag_actions.addWidget(self.diag_dry_button)
        diag_actions.addWidget(self.diag_repair_button)
        self.diagnostic_summary_card.layout_box.addLayout(diag_actions)
        self.diagnostics_top_layout.addWidget(self.diagnostic_summary_card, 0, 0)
        self.safety_card = SectionCard("Safety guardrails", "The assistant accelerates policy delivery without taking ownership of corporate encryption.")
        rules = [
            "No Enable-BitLocker, decrypt, suspend or protector modification commands.",
            "No reboot because encryption is incomplete.",
            "No automatic deep ccmrepair without technician review.",
            "PowerShell bypass is process-scoped only.",
            "Cancel stops new assistant actions; Windows services remain enabled.",
        ]
        for rule in rules:
            row = QLabel(f"✓  {rule}")
            row.setObjectName("safetyRule")
            row.setWordWrap(True)
            self.safety_card.layout_box.addWidget(row)
        self.safety_card.layout_box.addStretch()
        self.diagnostics_top_layout.addWidget(self.safety_card, 0, 1)
        self.diagnostics_top_layout.setColumnStretch(0, 4)
        self.diagnostics_top_layout.setColumnStretch(1, 5)
        layout.addLayout(self.diagnostics_top_layout)
        full = SectionCard("Complete readiness inspection", "Detailed evidence used by the deployment decision engine.")
        self.diagnostics_readiness = ReadinessList()
        self.diagnostics_readiness.setMinimumHeight(300)
        full.layout_box.addWidget(self.diagnostics_readiness, 1)
        layout.addWidget(full)
        evidence = SectionCard("SCCM evidence", "Sanitized log and ccmcache findings collected by dry run or policy-timeout diagnostics.")
        self.evidence_view = QPlainTextEdit()
        self.evidence_view.setReadOnly(True)
        self.evidence_view.setMinimumHeight(260)
        self.evidence_view.setPlaceholderText("Run Dry run / evidence only to inspect SCCM logs and cached deployment content without starting policy or repair actions.")
        evidence.layout_box.addWidget(self.evidence_view, 1)
        layout.addWidget(evidence)
        layout.addStretch(1)
        scroll.setWidget(page)
        return scroll

    def _build_activity_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(14)
        card = SectionCard("Activity and evidence", "Timestamped operations are retained locally for technician review.")
        buttons = QHBoxLayout()
        buttons.addStretch()
        export_activity = QPushButton("Export activity")
        export_activity.clicked.connect(self.export_activity)
        export_report = QPushButton("Export HTML report")
        export_report.setObjectName("primaryButton")
        export_report.clicked.connect(self.export_report)
        buttons.addWidget(export_activity)
        buttons.addWidget(export_report)
        card.layout_box.addLayout(buttons)
        self.activity = QPlainTextEdit()
        self.activity.setReadOnly(True)
        self.activity.setMaximumBlockCount(4000)
        card.layout_box.addWidget(self.activity, 1)
        layout.addWidget(card, 1)
        return page

    def _build_about_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(14)
        hero = QFrame()
        hero.setObjectName("aboutHero")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(30, 28, 30, 28)
        hero_layout.setSpacing(8)
        badge = StatusBadge("CONTROLLED BUILD", "running")
        badge.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        title = QLabel("BitLocker deployment without blind waiting")
        title.setObjectName("aboutTitle")
        description = QLabel("A technician-first Windows assistant that verifies readiness, repairs SCCM safely, accelerates policy delivery and monitors BitLocker without overriding enterprise security policy.")
        description.setObjectName("aboutDescription")
        description.setWordWrap(True)
        hero_layout.addWidget(badge, 0, Qt.AlignLeft)
        hero_layout.addWidget(title)
        hero_layout.addWidget(description)
        layout.addWidget(hero)
        grid = QHBoxLayout()
        grid.setSpacing(14)
        identity = SectionCard("Product identity")
        identity_items = [("Product", APP_NAME), ("Version", APP_VERSION), ("Author", APP_AUTHOR), ("Positioning", "Internal IT automation & deployment tool"), ("Target", "Windows 10/11 x64 enterprise-managed devices")]
        for label, value in identity_items:
            row = QHBoxLayout()
            key = QLabel(label)
            key.setObjectName("aboutKey")
            val = QLabel(value)
            val.setObjectName("aboutValue")
            val.setWordWrap(True)
            row.addWidget(key)
            row.addStretch()
            row.addWidget(val)
            identity.layout_box.addLayout(row)
        identity.layout_box.addStretch()
        grid.addWidget(identity, 1)
        signature = SectionCard("Engineering credit")
        sign_kicker = QLabel("DESIGNED & ENGINEERED BY")
        sign_kicker.setObjectName("signatureKicker")
        sign = QLabel("Ilyas Nazih")
        sign.setObjectName("authorName")
        sign_note = QLabel("Internal IT automation initiative")
        sign_note.setObjectName("aboutDescription")
        sign_note.setWordWrap(True)
        signature.layout_box.addStretch()
        signature.layout_box.addWidget(sign_kicker)
        signature.layout_box.addWidget(sign)
        signature.layout_box.addWidget(sign_note)
        signature.layout_box.addStretch()
        grid.addWidget(signature, 1)
        layout.addLayout(grid, 1)
        return page

    def _apply_style(self) -> None:
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{ background: {COLORS['bg']}; color: {COLORS['text']}; font-family: 'Segoe UI'; font-size: 13px; }}
            QLabel {{ background: transparent; }}
            #sidebar {{ background: #151515; border-right: 1px solid {COLORS['border']}; }}
            #brandName {{ color: {COLORS['muted']}; font-size: 9px; font-weight: 700; letter-spacing: 1.4px; }}
            #productName {{ color: {COLORS['text']}; font-size: 18px; font-weight: 750; letter-spacing: .2px; }}
            #navButton {{ background: transparent; color: {COLORS['muted']}; border: 1px solid transparent; border-radius: 10px; padding: 11px 12px; text-align: left; font-weight: 650; }}
            #navButton:hover {{ background: {COLORS['surface_alt']}; color: {COLORS['text']}; }}
            #navButton:checked {{ background: #2A2A2A; color: {COLORS['text']}; border-color: #444444; }}
            #safetyBadge {{ background: #1D1D1D; color: #CFCFCF; border: 1px solid #343434; border-radius: 10px; padding: 10px; font-size: 10px; font-weight: 700; }}
            #signature {{ color: {COLORS['muted']}; font-size: 10px; padding-top: 8px; }}
            #header {{ background: #151515; border-bottom: 1px solid {COLORS['border']}; }}
            #pageTitle {{ font-size: 19px; font-weight: 750; color: {COLORS['text']}; }}
            #pageSubtitle {{ color: {COLORS['muted']}; font-size: 11px; }}
            #versionBadge {{ color: {COLORS['muted']}; border: 1px solid {COLORS['border']}; border-radius: 10px; padding: 4px 8px; font-size: 10px; font-weight: 750; }}
            #footer {{ background: #151515; border-top: 1px solid {COLORS['border']}; }}
            #footerStatus, #footerSignature {{ color: {COLORS['muted']}; font-size: 10px; }}
            #metricCard, #sectionCard, #pipelinePanel {{ background: {COLORS['surface']}; border: 1px solid {COLORS['border']}; border-radius: 14px; }}
            #metricCard:hover {{ background: {COLORS['surface_alt']}; border-color: #484848; }}
            #metricSymbol {{ background: #252525; color: #D8D8D8; border: 1px solid #3A3A3A; border-radius: 9px; font-size: 10px; font-weight: 800; }}
            #eyebrow, #sectionTitle {{ color: {COLORS['muted']}; font-size: 10px; font-weight: 800; letter-spacing: 1.15px; }}
            #metricValue {{ color: {COLORS['text']}; font-size: 17px; font-weight: 750; }}
            #metricDetail, #sectionSubtitle, #heroDetail, #activityHint {{ color: {COLORS['muted']}; font-size: 11px; }}
            #heroStage {{ color: {COLORS['text']}; font-size: 22px; font-weight: 750; }}
            #pipelineLabel {{ font-size: 9px; font-weight: 650; }}
            #readinessRow {{ background: #181818; border: 1px solid #303030; border-radius: 10px; }}
            #readinessRow:hover {{ border-color: #484848; background: {COLORS['surface_alt']}; }}
            #readinessName {{ color: {COLORS['text']}; font-size: 12px; font-weight: 700; }}
            #readinessDetail {{ color: {COLORS['muted']}; font-size: 10px; }}
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{ background: transparent; width: 8px; margin: 1px; }}
            QScrollBar::handle:vertical {{ background: #444444; border-radius: 4px; min-height: 28px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
            QListWidget, QPlainTextEdit, QComboBox {{ background: #171717; color: #E7E7E7; border: 1px solid {COLORS['border']}; border-radius: 10px; }}
            QListWidget::item {{ padding: 7px; border-bottom: 1px solid #2B2B2B; }}
            QPlainTextEdit {{ font-family: 'Cascadia Mono', 'Consolas'; font-size: 11px; padding: 10px; selection-background-color: #444444; }}
            QComboBox {{ padding: 9px 10px; min-height: 18px; }}
            QComboBox::drop-down {{ border: none; width: 24px; }}
            QPushButton {{ background: #252525; color: #E7E7E7; border: 1px solid #3B3B3B; border-radius: 10px; padding: 9px 12px; font-weight: 650; }}
            QPushButton:hover {{ background: #303030; border-color: #505050; }}
            QPushButton:pressed {{ background: #1E1E1E; }}
            QPushButton:disabled {{ color: #666666; background: #191919; border-color: #2A2A2A; }}
            #primaryButton {{ background: #E7E7E7; color: #111111; border-color: #E7E7E7; padding: 10px 14px; }}
            #primaryButton:hover {{ background: #FFFFFF; }}
            #primaryButton:disabled {{ color: #666666; background: #191919; border-color: #2A2A2A; }}
            #dangerButton {{ color: #D0D0D0; border-color: #444444; background: #252525; }}
            #dangerButton:hover {{ color: {COLORS['red']}; background: #2D2224; border-color: #604044; }}
            #dangerButton:disabled {{ color: #666666; background: #191919; border-color: #2A2A2A; }}
            #activityPreview {{ min-height: 90px; }}
            #diagnosticHero {{ color: {COLORS['text']}; font-size: 22px; font-weight: 750; }}
            #safetyRule {{ color: #D0D0D0; background: #181818; border: 1px solid #303030; border-radius: 8px; padding: 8px; }}
            #aboutHero {{ background: #1B1B1B; border: 1px solid #343434; border-radius: 14px; }}
            #aboutTitle {{ color: white; font-size: 28px; font-weight: 800; }}
            #aboutDescription {{ color: #B8B8B8; font-size: 13px; }}
            #aboutKey {{ color: {COLORS['muted']}; font-weight: 700; }}
            #aboutValue {{ color: {COLORS['text']}; font-weight: 700; }}
            #signatureKicker {{ color: {COLORS['muted']}; font-size: 10px; font-weight: 800; letter-spacing: 1.5px; }}
            #authorName {{ color: {COLORS['text']}; font-family: 'Segoe UI'; font-size: 28px; font-weight: 750; }}
            """)

    def _switch_page(self, page: str) -> None:
        if page not in self.page_map:
            return
        self.pages.setCurrentIndex(self.page_map[page])
        for key, button in self.nav_buttons.items():
            button.setChecked(key == page)
        titles = {
            "dashboard": ("Deployment dashboard", "Prepare SCCM, request enterprise policy and monitor encryption safely."),
            "diagnostics": ("Diagnostics", "Machine-specific readiness evidence and safe remediation guidance."),
            "activity": ("Activity", "Full execution history, evidence and technician report export."),
            "about": ("About this tool", "Product identity, safety model and author signature."),
        }
        self.page_title.setText(titles[page][0])
        self.page_subtitle.setText(titles[page][1])

    def run_preflight(self) -> None:
        if self._worker_busy():
            return
        self._prepare_worker("preflight")
        self.update_stage("PREFLIGHT", "Checking only. No SCCM repair, policy action, or reboot is started.")
        self.update_progress(0)
        self._set_running_controls(True, allow_pause=False)
        self.worker.start()

    def _start_dry_run_from_diagnostics(self) -> None:
        if self._worker_busy():
            return
        index = self.mode_combo.findData("dry_run")
        if index >= 0:
            self.mode_combo.setCurrentIndex(index)
        self._switch_page("diagnostics")
        self.start_deployment()

    def start_deployment(self) -> None:
        if self._worker_busy():
            return
        workflow = str(self.mode_combo.currentData())
        if workflow == "dry_run":
            self.audit.write_event("Technician started dry-run evidence collection.", "info", workflow=workflow)
        else:
            label = "Fast deployment" if workflow == "fast" else "Adaptive SCCM refresh"
            actions = (
                "This controlled workflow may restart CcmExec if unhealthy, run CcmEval once, trigger SCCM client schedules, "
                "and run computer gpupdate. It will not directly enable, disable, suspend, resume, decrypt, or change BitLocker protectors. "
                "It will not reboot automatically or launch deep ccmrepair."
            )
            if workflow == "full":
                actions += "\n\nAdaptive SCCM refresh also requests broader inventory, discovery, update, and application evaluation cycles. Optional schedules reported as unsupported with HRESULT 0x80041002 are skipped; other failures remain blocking."
            if not self.last_corporate_network_likely:
                actions += "\n\nWarning: corporate-network evidence is unconfirmed. Verify that this is an authorized enterprise-managed test device connected by Ethernet."
            if not self.last_ac_connected:
                actions += "\n\nWarning: The laptop is running on battery. Connect the AC adapter before starting for reliability and best disk performance."
            answer = QMessageBox.question(self, f"Confirm {label}", f"Start {label} on {self.machine_card.value_label.text()}?\n\n{actions}", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                self.audit.write_event("Technician declined deployment confirmation.", "warning", workflow=workflow)
                return
            self.audit.write_event("Technician confirmed controlled deployment.", "warning", workflow=workflow)
        self._prepare_worker(workflow)
        self.update_progress(0)
        self._set_running_controls(True, allow_pause=True)
        self.worker.start()

    def repair_sccm(self) -> None:
        if self._worker_busy():
            return
        answer = QMessageBox.question(self, "Safe SCCM repair", "Run basic SCCM remediation and CcmEval if required?\n\nDeep ccmrepair remains disabled in this version.")
        if answer != QMessageBox.Yes:
            return
        self._prepare_worker("repair")
        self.update_progress(0)
        self._set_running_controls(True, allow_pause=True)
        self.worker.start()

    def _prepare_worker(self, workflow: str) -> None:
        self.current_workflow = workflow
        self.worker = WorkflowWorker(self.runner, self.config, workflow)
        self.worker.log.connect(self.append_log)
        self.worker.stage.connect(self.update_stage)
        self.worker.result.connect(self.handle_result)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished_state.connect(self.workflow_finished)
        self.worker.finished.connect(self._thread_finished)

    def _set_running_controls(self, running: bool, allow_pause: bool = True) -> None:
        self.start_button.setEnabled(not running and self._can_start_selected_mode())
        self.recheck_button.setEnabled(not running)
        self.repair_button.setEnabled(not running and self.is_admin and self.sccm_installed)
        if hasattr(self, "diag_recheck_button"):
            self.diag_recheck_button.setEnabled(not running)
            self.diag_dry_button.setEnabled(not running and self.is_admin)
            self.diag_repair_button.setEnabled(not running and self.is_admin and self.sccm_installed)
        self.mode_combo.setEnabled(not running)
        self.pause_button.setEnabled(running and allow_pause)
        self.cancel_button.setEnabled(running)
        if not running:
            self.paused = False
            self.pause_button.setText("Pause")

    def toggle_pause(self) -> None:
        if not self.worker:
            return
        self.paused = not self.paused
        self.worker.request_pause(self.paused)
        self.pause_button.setText("Resume" if self.paused else "Pause")
        if self.paused:
            self.stage_badge.set_status("PAUSED", "warning")

    def cancel_workflow(self) -> None:
        if self.worker:
            self.worker.request_cancel()
            self.cancel_button.setEnabled(False)

    def update_progress(self, value: int) -> None:
        self.progress_ring.animate_to(value)
        caption = "Dry run" if self.current_workflow == "dry_run" else "Deployment" if self.current_workflow not in {"", "preflight"} else "Readiness"
        self.progress_ring.set_caption(caption)

    def update_stage(self, stage: str, detail: str) -> None:
        self.current_stage_key = stage.upper()
        display = stage.replace("_", " ").title()
        self.stage_label.setText(display)
        self.stage_detail.setText(detail)
        self.stage_badge.set_status("RUNNING" if stage.upper() != "PAUSED" else "PAUSED", "running" if stage.upper() != "PAUSED" else "warning")
        self.pipeline.set_stage(stage)
        self.footer_status.setText(f"{display} • {detail}")

    def handle_result(self, result: OperationResult) -> None:
        self.last_results[result.operation] = result
        self.audit.write_result(result.operation, result)
        if result.operation == "preflight": self._apply_preflight(result)
        elif result.operation == "sccm_health": self._apply_sccm(result)
        elif result.operation == "bitlocker_status": self._apply_bitlocker(result)
        elif result.operation == "policy_evidence" and result.data.get("bitlocker"): self._apply_bitlocker_payload(result.data["bitlocker"])
        elif result.operation in {"ccmcache_discovery", "sccm_log_evidence"}: self._append_evidence(result)

    def _apply_preflight(self, result: OperationResult) -> None:
        data = result.data
        machine, network, sccm, bitlocker, power = data.get("machine", {}), data.get("network", {}), data.get("sccm", {}), data.get("bitlocker", {}), data.get("power", {})
        self.last_ac_connected = bool(power.get("acConnected", True))
        self.machine_card.set_status(machine.get("computerName", "Unknown"), f"{machine.get('manufacturer', '')} {machine.get('model', '')} • Serial {machine.get('serialNumber', 'N/A')}", "ready" if result.data else "warning", "detected" if result.data else "unknown")
        net_ready = bool(network.get("ethernetConnected"))
        self.last_corporate_network_likely = bool(network.get("corporateNetworkLikely"))
        self.network_card.set_status("Connected" if net_ready else "Disconnected", network.get("summary", "No Ethernet information"), "ready" if net_ready else "blocked")
        self._apply_sccm_payload(sccm)
        self._apply_bitlocker_payload(bitlocker)
        checks = data.get("checks", [])
        self.readiness_list.populate(checks)
        self.diagnostics_readiness.populate(checks)
        self.minimum_ready = bool(data.get("minimumReady"))
        self.start_button.setEnabled(self._can_start_selected_mode() and not self._worker_busy())
        self._update_diagnostic_summary(checks, bitlocker)

    def _apply_sccm(self, result: OperationResult) -> None:
        self._apply_sccm_payload(result.data)

    def _apply_sccm_payload(self, data: dict[str, Any]) -> None:
        healthy = bool(data.get("healthy"))
        installed = bool(data.get("executableExists") or data.get("serviceExists"))
        self.sccm_installed = installed
        if hasattr(self, "repair_button") and not self._worker_busy():
            self.repair_button.setEnabled(self.is_admin and installed)
            if hasattr(self, "diag_repair_button"): self.diag_repair_button.setEnabled(self.is_admin and installed)
        if healthy: value, status, badge = "Healthy", "ready", "ready"
        elif not installed: value, status, badge = "Client not installed", "blocked", "missing"
        else: value, status, badge = data.get("healthSummary", "Needs attention"), "warning", "review"
        detail = f"Service {data.get('serviceStatus', 'Unknown')} • Site {data.get('siteCode', 'N/A')} • MP {data.get('managementPoint', 'N/A')}"
        self.sccm_card.set_status(value, detail, status, badge)

    def _apply_bitlocker(self, result: OperationResult) -> None:
        self._apply_bitlocker_payload(result.data)

    def _apply_bitlocker_payload(self, data: dict[str, Any]) -> None:
        pct = int(data.get("encryptionPercentage") or 0)
        protection = data.get("protectionStatus", "Unknown")
        volume = data.get("volumeStatus", "Unknown")
        complete = bool(data.get("fullyEncrypted") and data.get("protectionOn"))
        status = "ready" if complete else "waiting"
        self.bitlocker_card.set_status(f"{pct}% encrypted", f"Protection {protection} • Volume {volume}", status, "protected" if complete else "monitoring")

    def _update_diagnostic_summary(self, checks: list[dict[str, Any]], bitlocker: dict[str, Any]) -> None:
        blockers = [c for c in checks if str(c.get("status")) in {"blocked", "failed", "error"}]
        warnings = [c for c in checks if str(c.get("status")) in {"warning", "waiting"}]
        already_protected = bool(bitlocker.get("fullyEncrypted") and bitlocker.get("protectionOn"))
        if already_protected:
            self.diagnostic_state.setText("This device is already protected")
            self.diagnostic_advice.setText("BitLocker reports full encryption with protection on. SCCM readiness can still be inspected for device-management health.")
        elif blockers:
            names = ", ".join(str(item.get("name")) for item in blockers[:3])
            self.diagnostic_state.setText(f"{len(blockers)} blocking condition(s)")
            self.diagnostic_advice.setText(f"Resolve: {names}. Deployment remains disabled until the minimum prerequisites are ready.")
        elif warnings:
            self.diagnostic_state.setText("Ready with warnings")
            self.diagnostic_advice.setText("Minimum requirements are available. Review pending reboot or corporate-network evidence before starting.")
        else:
            self.diagnostic_state.setText("Ready for focused deployment")
            self.diagnostic_advice.setText("The machine passed the minimum pre-flight checks. Fast deployment is the recommended first mode.")

    def workflow_finished(self, state: str, message: str) -> None:
        self.append_log(message, state)
        display_state = state.upper()
        self.stage_label.setText(display_state.replace("_", " ").title())
        self.stage_detail.setText(message)
        badge_status = "success" if state in {"success", "ready"} else "warning" if state in {"waiting", "cancelled"} else "blocked"
        self.stage_badge.set_status(display_state, badge_status)
        self.pipeline.set_stage(self.current_stage_key, terminal_state="success" if state == "success" else state if state in {"blocked", "failed"} else None)
        self.footer_status.setText(message)
        self._set_running_controls(False)
        if state == "success": self.update_progress(100)
        if self.current_workflow == "preflight": return
        if state == "success": QMessageBox.information(self, "Completed", message)
        elif state == "blocked": QMessageBox.warning(self, "Manual action required", message)
        elif state == "cancelled": QMessageBox.information(self, "Assistant stopped", message)

    def _thread_finished(self) -> None:
        completed_workflow = self.current_workflow
        self.worker = None
        if completed_workflow != "preflight": QTimer.singleShot(900, self.run_preflight)

    def append_log(self, message: str, level: str = "info") -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        tag = level.upper().ljust(7)
        line = f"[{timestamp}] [{tag}] {message}"
        self.audit.write_event(message, level, workflow=self.current_workflow, stage=self.current_stage_key)
        self.activity.appendPlainText(line)
        self.activity.moveCursor(QTextCursor.End)
        item = QListWidgetItem(f"{timestamp}   {message}")
        item.setForeground(QColor(STATUS_COLORS.get(level, STATUS_COLORS["info"])))
        self.activity_preview.insertItem(0, item)
        while self.activity_preview.count() > 4: self.activity_preview.takeItem(self.activity_preview.count() - 1)
        self.activity_preview_status.setText(f"Latest event • {timestamp}")

    def export_activity(self) -> None:
        default = Path.home() / f"BLADE_Activity_{datetime.now():%Y%m%d_%H%M%S}.txt"
        target, _ = QFileDialog.getSaveFileName(self, "Export activity", str(default), "Text files (*.txt)")
        if not target: return
        try:
            header = f"{APP_NAME} {APP_VERSION}\nDesigned & engineered by {APP_AUTHOR}\nExported {datetime.now():%Y-%m-%d %H:%M:%S}\n" + "=" * 72 + "\n"
            Path(target).write_text(header + self.activity.toPlainText(), encoding="utf-8")
            QMessageBox.information(self, "Export complete", f"Activity exported to:\n{target}")
        except OSError as exc: QMessageBox.critical(self, "Export failed", str(exc))

    def export_report(self) -> None:
        default = Path.home() / f"BLADE_Report_{datetime.now():%Y%m%d_%H%M%S}.html"
        target, _ = QFileDialog.getSaveFileName(self, "Export HTML report", str(default), "HTML files (*.html)")
        if not target: return
        rows = []
        for operation, result in self.last_results.items():
            rows.append("<tr>" f"<td>{html.escape(operation)}</td>" f"<td><span class='status {html.escape(result.status)}'>{html.escape(result.status.upper())}</span></td>" f"<td>{html.escape(result.message)}</td>" f"<td>{html.escape(result.timestamp)}</td>" "</tr>")
        report = f"""<!doctype html>
<html lang='en'><head><meta charset='utf-8'><title>{html.escape(APP_NAME)} report</title>
<style>
body{{font-family:Segoe UI,Arial;background:#111111;color:#f2f2f2;margin:0;padding:32px}}
.wrap{{max-width:1100px;margin:auto}} .hero{{background:#1b1b1b;padding:28px;border:1px solid #343434;border-radius:16px}}
h1{{margin:0 0 8px}} .muted{{color:#a3a3a3}} table{{width:100%;border-collapse:collapse;margin-top:24px;background:#1b1b1b;border:1px solid #343434}}
th,td{{padding:12px;border-bottom:1px solid #343434;text-align:left;vertical-align:top}} th{{color:#a3a3a3;font-size:12px;text-transform:uppercase}}
.status{{font-weight:700}} .ready,.success,.ok{{color:#2ccb91}} .blocked,.failed,.error{{color:#ff5d6c}} .warning,.waiting{{color:#ffb547}}
pre{{white-space:pre-wrap;background:#171717;padding:16px;border:1px solid #343434;border-radius:10px}} footer{{margin-top:28px;color:#a3a3a3}}
.signature{{color:#f2f2f2;font-size:22px;font-weight:700}}
</style></head><body><div class='wrap'>
<div class='hero'><div class='muted'>CONTROLLED INTERNAL IT TOOLING</div><h1>{html.escape(APP_NAME)}</h1>
<p>Deployment evidence and technician activity report.</p><p class='muted'>Generated {datetime.now():%Y-%m-%d %H:%M:%S}</p></div>
<table><thead><tr><th>Operation</th><th>Status</th><th>Result</th><th>Timestamp</th></tr></thead><tbody>{''.join(rows) or '<tr><td colspan="4">No structured operations recorded.</td></tr>'}</tbody></table>
<h2>Activity log</h2><pre>{html.escape(self.activity.toPlainText())}</pre>
<h2>Sanitized SCCM evidence</h2><pre>{html.escape(self.evidence_view.toPlainText() if hasattr(self, 'evidence_view') else '')}</pre>
<footer><div class='signature'>{html.escape(APP_AUTHOR)}</div><div>Designed & engineered by {html.escape(APP_AUTHOR)}.</div></footer>
</div></body></html>"""
        try:
            Path(target).write_text(report, encoding="utf-8")
            QMessageBox.information(self, "Report exported", f"HTML report saved to:\n{target}")
        except OSError as exc: QMessageBox.critical(self, "Export failed", str(exc))

    def _mode_changed(self) -> None:
        workflow = str(self.mode_combo.currentData())
        labels = {"dry_run": "Run dry check", "fast": "Start deployment", "full": "Start adaptive refresh"}
        self.start_button.setText(labels.get(workflow, "Start"))
        if not self._worker_busy(): self.start_button.setEnabled(self._can_start_selected_mode())

    def _can_start_selected_mode(self) -> bool:
        workflow = str(self.mode_combo.currentData()) if hasattr(self, "mode_combo") else "dry_run"
        return bool(self.is_admin) if workflow == "dry_run" else bool(self.is_admin and self.minimum_ready)

    def _append_evidence(self, result: OperationResult) -> None:
        if not hasattr(self, "evidence_view"): return
        lines = [f"[{result.timestamp}] {result.operation.upper()}: {result.message}"]
        if result.operation == "ccmcache_discovery":
            for item in list(result.data.get("relevantFiles") or [])[:80]:
                matches = ",".join(item.get("matchTypes") or [])
                lines.append(f"CACHE {item.get('relativePath', item.get('fileName','?'))} | {item.get('lastWriteTime','')} | matches={matches}")
        elif result.operation == "sccm_log_evidence":
            for item in list(result.data.get("evidence") or [])[:80]: lines.append(f"LOG {item.get('log','?')} | {item.get('line','')}")
        self.evidence_view.appendPlainText("\n".join(lines) + "\n")

    def _apply_responsive_layout(self) -> None:
        if not hasattr(self, "cards_layout") or not self.screen(): return
        geometry = self.screen().availableGeometry()
        dpi = float(self.screen().logicalDotsPerInch())
        compact = should_use_compact_layout(self.width(), geometry.height(), dpi)
        if compact == self.compact_mode: return
        self.compact_mode = compact
        if compact:
            self.sidebar.setFixedWidth(78)
            self.sidebar_layout.setContentsMargins(12, 16, 12, 12)
            self.brand_name_label.hide(); self.product_label.hide(); self.safety_label.hide(); self.author_label.hide()
            for key, button in self.nav_buttons.items():
                button.setText(self.nav_labels[key].split()[0]); button.setToolTip(self.nav_labels[key].split(None, 1)[1]); button.setStyleSheet("text-align:center;")
            positions = [(0,0),(0,1),(1,0),(1,1)]
            for card, (row, col) in zip(self.metric_cards, positions):
                self.cards_layout.addWidget(card, row, col); card.setMinimumHeight(118); card.value_label.setWordWrap(True)
            for col in range(4): self.cards_layout.setColumnMinimumWidth(col, 0); self.cards_layout.setColumnStretch(col, 1 if col < 2 else 0)
            self.dashboard_main_layout.addWidget(self.journey_card, 0, 0, 1, 1); self.dashboard_main_layout.addWidget(self.readiness_card, 1, 0, 1, 1)
            self.dashboard_main_layout.setColumnStretch(0, 1); self.dashboard_main_layout.setColumnStretch(1, 0)
            if hasattr(self, "diagnostics_top_layout"):
                self.diagnostics_top_layout.addWidget(self.diagnostic_summary_card, 0, 0); self.diagnostics_top_layout.addWidget(self.safety_card, 1, 0)
                self.diagnostics_top_layout.setColumnStretch(0, 1); self.diagnostics_top_layout.setColumnStretch(1, 0)
            self.progress_ring.setMinimumSize(165, 165); self.progress_ring.setMaximumSize(185, 185); self.page_subtitle.hide()
        else:
            self.sidebar.setFixedWidth(212)
            self.sidebar_layout.setContentsMargins(18, 20, 18, 16)
            self.brand_name_label.show(); self.product_label.show(); self.safety_label.show(); self.author_label.show()
            for key, button in self.nav_buttons.items(): button.setText(self.nav_labels[key]); button.setToolTip(""); button.setStyleSheet("")
            for index, card in enumerate(self.metric_cards):
                self.cards_layout.addWidget(card, 0, index); self.cards_layout.setColumnStretch(index, 1); self.cards_layout.setColumnMinimumWidth(index, 225); card.setMinimumHeight(126); card.value_label.setWordWrap(False)
            self.dashboard_main_layout.addWidget(self.journey_card, 0, 0, 1, 1); self.dashboard_main_layout.addWidget(self.readiness_card, 0, 1, 1, 1)
            self.dashboard_main_layout.setColumnStretch(0, 7); self.dashboard_main_layout.setColumnStretch(1, 4)
            if hasattr(self, "diagnostics_top_layout"):
                self.diagnostics_top_layout.addWidget(self.diagnostic_summary_card, 0, 0); self.diagnostics_top_layout.addWidget(self.safety_card, 0, 1)
                self.diagnostics_top_layout.setColumnStretch(0, 4); self.diagnostics_top_layout.setColumnStretch(1, 5)
            self.progress_ring.setMinimumSize(190, 190); self.progress_ring.setMaximumSize(225, 225); self.page_subtitle.show()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        QTimer.singleShot(0, self._apply_responsive_layout)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self._apply_responsive_layout)
        handle = self.windowHandle()
        if handle and not getattr(self, "_screen_signal_connected", False):
            handle.screenChanged.connect(lambda _screen: QTimer.singleShot(0, self._apply_responsive_layout))
            self._screen_signal_connected = True

    def _worker_busy(self) -> bool:
        return bool(self.worker and self.worker.isRunning())

    def closeEvent(self, event) -> None:
        if not self._worker_busy():
            event.accept(); return
        box = QMessageBox(self)
        box.setWindowTitle("Deployment is active")
        box.setText("A controlled workflow is still active.")
        box.setInformativeText("Stopping the assistant will not disable BitLocker or SCCM.")
        stop_button = box.addButton("Stop assistant safely", QMessageBox.DestructiveRole)
        box.addButton("Return to application", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() == stop_button: self.cancel_workflow()
        event.ignore()
