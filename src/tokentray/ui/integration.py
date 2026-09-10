"""Tray-accessible setup for one outbound notification destination."""

from __future__ import annotations

import re
import threading
from typing import Callable

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..core.config import Config
from ..core.i18n import t
from ..core.secrets import SecretStore, default_store
from ..notify.configuration import DestinationSettings, current_settings, save_destination
from ..notify.webhook import (
    DeliveryResult,
    Webhook,
    destination_hint,
    validate_destination,
)
from . import icons, theme
from .wrapping import WrappingLabel

_LABELS = {"slack": "Slack", "discord": "Discord", "ntfy": "ntfy", "generic": "Generic"}
_DOCS = {
    "slack": "https://api.slack.com/messaging/webhooks",
    "discord": "https://support.discord.com/hc/articles/228383668",
    "ntfy": "https://docs.ntfy.sh/publish/",
}


class IntegrationDialog(QDialog):
    operation_finished = Signal(str, object)

    def __init__(
        self,
        config: Config,
        *,
        on_saved: Callable[[DestinationSettings], None],
        store: SecretStore | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._store = store or default_store()
        self._on_saved = on_saved
        self._initial = current_settings(config)
        self._test_webhook: Webhook | None = None

        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setWindowTitle(t("integration.title"))
        self.setWindowIcon(icons.app_icon())
        self.setMinimumWidth(440)

        font = self.font()
        font.setPointSize(11)
        self.setFont(font)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)

        self.scroll = QScrollArea(self)
        self.scroll.setObjectName("webhook-scroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        content = QVBoxLayout(body)
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(16)
        content.addWidget(WrappingLabel(t("integration.intro")))

        self.enabled = QCheckBox(t("integration.enabled"))
        self.enabled.setObjectName("webhook-enabled")
        self.enabled.setChecked(self._initial.enabled)
        content.addWidget(self.enabled)

        self.kind = QComboBox()
        self.kind.setObjectName("webhook-kind")
        for key in ("slack", "discord", "ntfy", "generic"):
            self.kind.addItem(_LABELS[key], key)
        self.kind.setCurrentIndex(max(0, self.kind.findData(self._initial.kind)))
        service = QVBoxLayout()
        service.setSpacing(6)
        service_label = QLabel(t("integration.service"))
        service_label.setBuddy(self.kind)
        service.addWidget(service_label)
        service.addWidget(self.kind)
        content.addLayout(service)

        self.url = QLineEdit()
        self.url.setObjectName("webhook-url")
        self.url.setEchoMode(QLineEdit.EchoMode.Password)
        self.url.setPlaceholderText(
            t("integration.saved_url") if self._initial.configured else "https://…"
        )
        destination = QVBoxLayout()
        destination.setSpacing(6)
        url_label = QLabel(t("integration.url"))
        url_label.setBuddy(self.url)
        destination.addWidget(url_label)
        destination.addWidget(self.url)
        self.url_shape = WrappingLabel()
        self.url_shape.setObjectName("webhook-url-shape")
        self.url_shape.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        destination.addWidget(self.url_shape)
        content.addLayout(destination)

        guide = QVBoxLayout()
        guide.setSpacing(8)
        self.help_toggle = QToolButton()
        self.help_toggle.setText(t("integration.help"))
        self.help_toggle.setCheckable(True)
        self.help_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.help_toggle.setArrowType(Qt.ArrowType.RightArrow)
        guide.addWidget(self.help_toggle, 0, Qt.AlignmentFlag.AlignLeft)
        self.help = QWidget()
        self.help.setObjectName("webhook-steps")
        self.steps_layout = QVBoxLayout(self.help)
        self.steps_layout.setContentsMargins(0, 0, 0, 0)
        self.steps_layout.setSpacing(8)
        self.help.hide()
        guide.addWidget(self.help)
        self.help_toggle.toggled.connect(self._toggle_help)
        content.addLayout(guide)

        notice = QFrame()
        notice.setObjectName("webhook-notice-card")
        notice_layout = QVBoxLayout(notice)
        notice_layout.setContentsMargins(12, 12, 12, 12)
        notice_layout.setSpacing(6)
        notice_title = WrappingLabel(t("integration.notice_title"))
        title_font = notice_title.font()
        title_font.setBold(True)
        notice_title.setFont(title_font)
        notice_layout.addWidget(notice_title)
        notice_body = WrappingLabel(t("integration.notice_body"))
        notice_body.setObjectName("webhook-notice")
        notice_layout.addWidget(notice_body)
        content.addWidget(notice)
        content.addStretch(1)
        self.scroll.setWidget(body)
        root.addWidget(self.scroll, 1)

        self.status = WrappingLabel()
        self.status.setObjectName("webhook-status")
        self.status_scroll = QScrollArea()
        self.status_scroll.setWidgetResizable(True)
        self.status_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.status_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.status_scroll.setWidget(self.status)
        self.status_scroll.hide()
        root.addWidget(self.status_scroll)

        palette = theme.current()
        self.setStyleSheet(f"""
            QDialog {{ background: {palette.surface.name()}; color: {palette.text.name()}; }}
            QScrollArea, QScrollArea > QWidget > QWidget {{ background: {palette.surface.name()}; }}
            QLabel {{ color: {palette.text.name()}; }}
            QLabel#webhook-url-shape {{ color: {palette.text_muted.name()}; }}
            QFrame#webhook-notice-card {{ background: {palette.surface_alt.name()}; border-radius: 6px; }}
            QLineEdit, QComboBox {{ min-height: 28px; }}
            QPushButton {{ min-height: 28px; padding: 0 12px; }}
            QToolButton {{ border: none; padding: 4px 0; color: {palette.text.name()}; }}
        """)

        controls = QHBoxLayout()
        self.test_button = QPushButton(t("integration.test"), self)
        self.test_button.setObjectName("webhook-test")
        self.test_button.clicked.connect(self._test)
        controls.addWidget(self.test_button)
        controls.addStretch(1)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText(t("integration.save"))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(t("integration.cancel"))
        self.buttons.accepted.connect(self._save)
        self.buttons.rejected.connect(self.reject)
        controls.addWidget(self.buttons)
        root.addLayout(controls)

        self.kind.currentIndexChanged.connect(self._kind_changed)
        self.operation_finished.connect(self._operation_done)
        self._update_help()
        available_height = self.screen().availableGeometry().height()
        self.resize(560, min(540, max(280, available_height - 80)))

    def _toggle_help(self, expanded: bool) -> None:
        self.help.setVisible(expanded)
        self.help_toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)

    def _selected_kind(self) -> str:
        return str(self.kind.currentData())

    def _kind_changed(self) -> None:
        if self._selected_kind() != self._initial.kind:
            self.url.clear()
            self.url.setPlaceholderText("https://…")
        else:
            self.url.setPlaceholderText(
                t("integration.saved_url") if self._initial.configured else "https://…"
            )
        self._update_help()

    def _update_help(self) -> None:
        kind = self._selected_kind()
        # Only the services with a vendor page take a {url}; a generic webhook
        # has nobody's documentation to link to.
        while self.steps_layout.count():
            item = self.steps_layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        steps = re.findall(r"<li>(.*?)</li>", t(f"integration.steps.{kind}", url=_DOCS.get(kind, "")))
        for number, text in enumerate(steps, 1):
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(8)
            label = QLabel(f"{number}.")
            label.setFixedWidth(20)
            layout.addWidget(label, 0, Qt.AlignmentFlag.AlignTop)
            step = WrappingLabel()
            step.setObjectName("webhook-step")
            step.setTextFormat(Qt.TextFormat.RichText)
            step.setText(text)
            step.setOpenExternalLinks(True)
            layout.addWidget(step, 1)
            self.steps_layout.addWidget(row)
        shape = destination_hint(kind)
        self.url_shape.setText(t("integration.url_shape", shape=shape) if shape else "")
        self.url_shape.setVisible(bool(shape))

    def _test(self) -> None:
        kind = self._selected_kind()
        url = self.url.text().strip()
        if url:
            error = validate_destination(kind, url)
            if error:
                self._show_error(error)
                return
        elif not (self._initial.configured and kind == self._initial.kind):
            self._show_error(t("integration.url_required"))
            return

        self._set_busy(True)
        self._set_status(t("integration.testing"))
        hook = Webhook(
            enabled=True,
            kind=kind,
            url=url or self._initial.url,
            store=self._store,
            configured=True,
        )
        self._test_webhook = hook
        hook.test(lambda result: self.operation_finished.emit("test", result))

    def _save(self) -> None:
        self._set_busy(True)
        self._set_status(t("integration.saving"))
        values = (self.enabled.isChecked(), self._selected_kind(), self.url.text())

        def work() -> None:
            try:
                result: object = save_destination(
                    self._config,
                    enabled=values[0],
                    kind=values[1],
                    url=values[2],
                    store=self._store,
                )
            except Exception as exc:
                result = exc
            self.operation_finished.emit("save", result)

        threading.Thread(target=work, name="tokentray-webhook-save", daemon=True).start()

    @Slot(str, object)
    def _operation_done(self, operation: str, result: object) -> None:
        self._set_busy(False)
        if isinstance(result, Exception):
            self._show_error(str(result))
            return
        if operation == "test":
            delivery = result
            if isinstance(delivery, DeliveryResult) and delivery.ok:
                self._set_status(t("integration.test_ok"))
            else:
                reason = delivery.error if isinstance(delivery, DeliveryResult) else "unknown error"
                self._show_error(t("integration.test_failed", reason=reason))
            return
        if isinstance(result, DestinationSettings):
            self._on_saved(result)
            self.accept()

    def _set_busy(self, busy: bool) -> None:
        self.test_button.setEnabled(not busy)
        self.buttons.setEnabled(not busy)
        self.enabled.setEnabled(not busy)
        self.kind.setEnabled(not busy)
        self.url.setEnabled(not busy)

    def _show_error(self, message: str) -> None:
        self._set_status(t("integration.error", reason=message))

    def _set_status(self, message: str) -> None:
        self.status.setText(message)
        self.status_scroll.setVisible(bool(message))
        self.status_scroll.setFixedHeight(min(80, max(24, self.status.heightForWidth(self.width() - 56))))
