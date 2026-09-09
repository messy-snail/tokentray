"""Tray-accessible setup for one outbound notification destination."""

from __future__ import annotations

import threading
from typing import Callable

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
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
from . import icons

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

        root = QVBoxLayout(self)
        intro = QLabel(t("integration.intro"), self)
        intro.setWordWrap(True)
        root.addWidget(intro)

        form = QFormLayout()
        self.enabled = QCheckBox(t("integration.enabled"), self)
        self.enabled.setObjectName("webhook-enabled")
        self.enabled.setChecked(self._initial.enabled)
        form.addRow("", self.enabled)

        self.kind = QComboBox(self)
        self.kind.setObjectName("webhook-kind")
        for key in ("slack", "discord", "ntfy", "generic"):
            self.kind.addItem(_LABELS[key], key)
        self.kind.setCurrentIndex(max(0, self.kind.findData(self._initial.kind)))
        form.addRow(t("integration.service"), self.kind)

        self.url = QLineEdit(self)
        self.url.setObjectName("webhook-url")
        self.url.setEchoMode(QLineEdit.EchoMode.Password)
        self.url.setPlaceholderText(
            t("integration.saved_url") if self._initial.configured else "https://…"
        )
        form.addRow(t("integration.url"), self.url)
        root.addLayout(form)

        self.help = QLabel(self)
        self.help.setObjectName("webhook-steps")
        self.help.setOpenExternalLinks(True)
        self.help.setWordWrap(True)
        root.addWidget(self.help)

        self.url_shape = QLabel(self)
        self.url_shape.setObjectName("webhook-url-shape")
        self.url_shape.setWordWrap(True)
        # Plain, not auto: the placeholders read as <id> and <topic>, and only
        # Qt's guess that those are not HTML tags keeps them on screen.
        self.url_shape.setTextFormat(Qt.TextFormat.PlainText)
        self.url_shape.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        root.addWidget(self.url_shape)

        self.status = QLabel("", self)
        self.status.setObjectName("webhook-status")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

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
        self.buttons.accepted.connect(self._save)
        self.buttons.rejected.connect(self.reject)
        controls.addWidget(self.buttons)
        root.addLayout(controls)

        self.kind.currentIndexChanged.connect(self._kind_changed)
        self.operation_finished.connect(self._operation_done)
        self._update_help()

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
        self.help.setText(t(f"integration.steps.{kind}", url=_DOCS.get(kind, "")))
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
        self.status.setText(t("integration.testing"))
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
        self.status.setText(t("integration.saving"))
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
                self.status.setText(t("integration.test_ok"))
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
        self.status.setText(t("integration.error", reason=message))
