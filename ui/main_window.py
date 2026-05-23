import os
from typing import Optional
from pathlib import Path

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPixmap, QFont, QIcon
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QLabel, QPushButton, QComboBox,
    QSlider, QListWidget, QListWidgetItem, QFileDialog,
    QDialog, QDoubleSpinBox, QFormLayout, QDialogButtonBox,
    QMessageBox, QProgressBar, QFrame, QSizePolicy, QSpacerItem,
    QCheckBox,
)

from core.camera_thread import CameraThread, list_cameras
from core.audio_thread import AudioThread, list_input_devices
from core.config import ConfigManager, VTuberConfig
from ui.output_window import OutputWindow
from ui.character_overlay import LayerConfig


# ─── Layer edit dialog ────────────────────────────────────────────────────────

class LayerEditDialog(QDialog):
    """Dialog for configuring volume thresholds of a character layer."""

    def __init__(self, config: Optional[LayerConfig] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Layer")
        self.setModal(True)
        self.setFixedSize(320, 200)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Info
        info = QLabel("Set the volume range when this layer is visible.\n"
                      "0 = silence  ·  1 = maximum volume")
        info.setStyleSheet("color: #8888cc; font-size: 11px;")
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()
        form.setSpacing(8)

        self.min_spin = QDoubleSpinBox()
        self.min_spin.setRange(0.0, 1.0)
        self.min_spin.setSingleStep(0.05)
        self.min_spin.setDecimals(2)
        self.min_spin.setSuffix("  (0–1)")

        self.max_spin = QDoubleSpinBox()
        self.max_spin.setRange(0.0, 1.0)
        self.max_spin.setSingleStep(0.05)
        self.max_spin.setDecimals(2)
        self.max_spin.setSuffix("  (0–1)")

        if config:
            self.min_spin.setValue(config.min_vol)
            self.max_spin.setValue(config.max_vol)
        else:
            self.min_spin.setValue(0.0)
            self.max_spin.setValue(1.0)

        form.addRow("Min volume:", self.min_spin)
        form.addRow("Max volume:", self.max_spin)
        layout.addLayout(form)

        # Preset buttons
        presets_label = QLabel("Presets:")
        presets_label.setStyleSheet("color: #8888cc; font-size: 11px;")
        layout.addWidget(presets_label)
        presets_layout = QHBoxLayout()
        for label, mn, mx in [("Always", 0.0, 1.0), ("Silent", 0.0, 0.2),
                               ("Speaking", 0.2, 0.7), ("Loud", 0.7, 1.0)]:
            btn = QPushButton(label)
            btn.setFixedHeight(26)
            btn.setStyleSheet("font-size: 11px; padding: 2px 6px;")
            _mn, _mx = mn, mx
            btn.clicked.connect(lambda _, a=_mn, b=_mx: (
                self.min_spin.setValue(a), self.max_spin.setValue(b)
            ))
            presets_layout.addWidget(btn)
        layout.addLayout(presets_layout)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_values(self) -> tuple[float, float]:
        return self.min_spin.value(), self.max_spin.value()


# ─── Main window ─────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🎭 VTuber Overlay Tool")
        self.setMinimumWidth(400)
        self.setMaximumWidth(480)

        self._camera_thread: Optional[CameraThread] = None
        self._audio_thread: Optional[AudioThread] = None
        self._output_window: Optional[OutputWindow] = None
        self._layer_configs: list[LayerConfig] = []
        self._current_vol: float = 0.0
        self._is_vtuber_mode: bool = False
        self._config_manager = ConfigManager()
        self._current_config_path: Optional[str] = None
        self._background_path: str = ""  # Full path to background image

        self._setup_ui()
        self._refresh_devices()
        self._load_recent_config()

        # Volume meter refresh timer
        self._vol_timer = QTimer()
        self._vol_timer.setInterval(40)   # 25 fps meter
        self._vol_timer.timeout.connect(self._refresh_vol_meter)

    # ─── UI Setup ────────────────────────────────────────────────────────────

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(8)
        root.setContentsMargins(12, 12, 12, 12)

        # ── Title ──
        title_row = QHBoxLayout()
        title = QLabel("🎭  VTuber Overlay Tool")
        title.setStyleSheet(
            "font-size: 17px; font-weight: bold; color: #aaaaff; padding: 2px 0 6px 0;"
        )
        title_row.addWidget(title)
        root.addLayout(title_row)

        # ── Output window group ──
        out_grp = QGroupBox("Output Window")
        out_lay = QVBoxLayout(out_grp)
        out_lay.setSpacing(6)

        self._open_btn = QPushButton("📺  Open Output Window")
        self._open_btn.setToolTip(
            "Opens a window you can capture in OBS or share in Discord"
        )
        self._open_btn.setFixedHeight(36)
        self._open_btn.clicked.connect(self._open_output)
        out_lay.addWidget(self._open_btn)

        res_row = QHBoxLayout()
        res_row.addWidget(QLabel("Resolution:"))
        self._res_combo = QComboBox()
        self._res_combo.addItems([
            "1280 × 720  (720p)",
            "1920 × 1080  (1080p)",
            "854 × 480  (480p)",
            "2560 × 1440  (1440p)",
        ])
        self._res_combo.setToolTip("Output window size")
        self._res_combo.currentIndexChanged.connect(self._apply_resolution)
        res_row.addWidget(self._res_combo, 1)
        out_lay.addLayout(res_row)
        root.addWidget(out_grp)

        # ── Mode switcher ──
        mode_grp = QGroupBox("Mode")
        mode_lay = QHBoxLayout(mode_grp)
        mode_lay.setSpacing(8)

        self._cam_mode_btn = QPushButton("📷  Camera")
        self._cam_mode_btn.setCheckable(True)
        self._cam_mode_btn.setChecked(True)
        self._cam_mode_btn.setFixedHeight(36)
        self._cam_mode_btn.setToolTip("Show raw camera feed in output")
        self._cam_mode_btn.clicked.connect(lambda: self._set_vtuber_mode(False))

        self._vt_mode_btn = QPushButton("🎭  VTuber")
        self._vt_mode_btn.setCheckable(True)
        self._vt_mode_btn.setFixedHeight(36)
        self._vt_mode_btn.setToolTip(
            "Show background image + animated character overlay"
        )
        self._vt_mode_btn.clicked.connect(lambda: self._set_vtuber_mode(True))

        mode_lay.addWidget(self._cam_mode_btn)
        mode_lay.addWidget(self._vt_mode_btn)
        root.addWidget(mode_grp)

        # ── Camera group ──
        cam_grp = QGroupBox("Camera")
        cam_lay = QVBoxLayout(cam_grp)
        cam_lay.setSpacing(6)

        cam_row = QHBoxLayout()
        self._cam_combo = QComboBox()
        self._cam_refresh_btn = QPushButton("🔄")
        self._cam_refresh_btn.setFixedSize(34, 30)
        self._cam_refresh_btn.setToolTip("Scan for cameras again")
        self._cam_refresh_btn.clicked.connect(self._refresh_devices)
        cam_row.addWidget(self._cam_combo, 1)
        cam_row.addWidget(self._cam_refresh_btn)
        cam_lay.addLayout(cam_row)

        self._cam_toggle_btn = QPushButton("▶  Start Camera")
        self._cam_toggle_btn.setFixedHeight(32)
        self._cam_toggle_btn.clicked.connect(self._toggle_camera)
        cam_lay.addWidget(self._cam_toggle_btn)
        root.addWidget(cam_grp)

        # ── Microphone group ──
        mic_grp = QGroupBox("Microphone")
        mic_lay = QVBoxLayout(mic_grp)
        mic_lay.setSpacing(6)

        self._mic_combo = QComboBox()
        mic_lay.addWidget(self._mic_combo)

        # Sensitivity
        sens_row = QHBoxLayout()
        sens_icon = QLabel("🎚")
        sens_row.addWidget(sens_icon)
        sens_row.addWidget(QLabel("Sensitivity:"))
        self._sens_slider = QSlider(Qt.Horizontal)
        self._sens_slider.setRange(1, 40)
        self._sens_slider.setValue(8)
        self._sens_slider.setToolTip(
            "Increase if the character barely reacts; decrease if it's too twitchy"
        )
        self._sens_slider.valueChanged.connect(self._on_sensitivity_change)
        self._sens_val_label = QLabel("8")
        self._sens_val_label.setFixedWidth(26)
        self._sens_val_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        sens_row.addWidget(self._sens_slider, 1)
        sens_row.addWidget(self._sens_val_label)
        mic_lay.addLayout(sens_row)

        # Volume meter
        vol_row = QHBoxLayout()
        vol_icon = QLabel("🔊")
        vol_row.addWidget(vol_icon)
        vol_row.addWidget(QLabel("Volume:"))
        self._vol_bar = QProgressBar()
        self._vol_bar.setRange(0, 100)
        self._vol_bar.setValue(0)
        self._vol_bar.setFixedHeight(14)
        self._vol_bar.setTextVisible(False)
        vol_row.addWidget(self._vol_bar, 1)
        mic_lay.addLayout(vol_row)

        self._mic_toggle_btn = QPushButton("🎙  Start Microphone")
        self._mic_toggle_btn.setFixedHeight(32)
        self._mic_toggle_btn.clicked.connect(self._toggle_mic)
        mic_lay.addWidget(self._mic_toggle_btn)
        root.addWidget(mic_grp)

        # ── VTuber settings group ──
        vt_grp = QGroupBox("VTuber Settings")
        vt_lay = QVBoxLayout(vt_grp)
        vt_lay.setSpacing(6)

        # Background
        bg_row = QHBoxLayout()
        bg_icon = QLabel("🖼")
        bg_row.addWidget(bg_icon)
        self._bg_path_label = QLabel("No background set")
        self._bg_path_label.setStyleSheet("color: #555577; font-style: italic;")
        self._bg_path_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._bg_path_label.setMaximumWidth(200)
        bg_row.addWidget(self._bg_path_label, 1)
        self._bg_btn = QPushButton("Choose…")
        self._bg_btn.setFixedHeight(28)
        self._bg_btn.clicked.connect(self._choose_background)
        bg_row.addWidget(self._bg_btn)
        vt_lay.addLayout(bg_row)

        # Divider
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #2a2a45;")
        vt_lay.addWidget(sep)

        # Character layers header
        layers_header = QHBoxLayout()
        layers_lbl = QLabel("Character Layers")
        layers_lbl.setStyleSheet("font-weight: bold; color: #9999ee;")
        layers_header.addWidget(layers_lbl)
        layers_tip = QLabel("  ↑ = rendered on top")
        layers_tip.setStyleSheet("color: #444466; font-size: 11px;")
        layers_header.addWidget(layers_tip)
        layers_header.addStretch()
        vt_lay.addLayout(layers_header)

        self._layers_list = QListWidget()
        self._layers_list.setMaximumHeight(140)
        self._layers_list.setToolTip("Double-click to edit volume range")
        self._layers_list.doubleClicked.connect(self._edit_layer)
        vt_lay.addWidget(self._layers_list)

        # Layer buttons
        lbtn_row = QHBoxLayout()
        lbtn_row.setSpacing(5)
        for text, tip, slot in [
            ("➕ Add", "Add image layer(s)", self._add_layer),
            ("➖ Remove", "Remove selected layer", self._remove_layer),
            ("✏ Edit", "Edit volume thresholds", self._edit_layer),
            ("▲", "Move layer up (render on top)", self._move_layer_up),
        ]:
            btn = QPushButton(text)
            btn.setToolTip(tip)
            btn.setFixedHeight(28)
            btn.clicked.connect(slot)
            lbtn_row.addWidget(btn)
        vt_lay.addLayout(lbtn_row)

        # Divider
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet("color: #2a2a45;")
        vt_lay.addWidget(sep2)

        # Scream threshold
        scream_row = QHBoxLayout()
        scream_row.addWidget(QLabel("😱 Scream at:"))
        self._scream_slider = QSlider(Qt.Horizontal)
        self._scream_slider.setRange(50, 99)
        self._scream_slider.setValue(85)
        self._scream_slider.setToolTip(
            "Volume level (%) above which the red scream overlay appears"
        )
        self._scream_val_lbl = QLabel("85%")
        self._scream_val_lbl.setFixedWidth(36)
        self._scream_val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._scream_slider.valueChanged.connect(self._on_scream_threshold_change)
        scream_row.addWidget(self._scream_slider, 1)
        scream_row.addWidget(self._scream_val_lbl)
        vt_lay.addLayout(scream_row)

        # Red glow smoothness
        smooth_row = QHBoxLayout()
        smooth_row.addWidget(QLabel("🎨 Glow smooth:"))
        self._smooth_slider = QSlider(Qt.Horizontal)
        self._smooth_slider.setRange(10, 500)
        self._smooth_slider.setValue(100)
        self._smooth_slider.setToolTip(
            "How smoothly the red glow fades in/out (lower = faster, higher = smoother)"
        )
        self._smooth_val_lbl = QLabel("100ms")
        self._smooth_val_lbl.setFixedWidth(50)
        self._smooth_val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._smooth_slider.valueChanged.connect(self._on_smoothness_change)
        smooth_row.addWidget(self._smooth_slider, 1)
        smooth_row.addWidget(self._smooth_val_lbl)
        vt_lay.addLayout(smooth_row)

        # Divider
        sep3 = QFrame()
        sep3.setFrameShape(QFrame.HLine)
        sep3.setStyleSheet("color: #2a2a45;")
        vt_lay.addWidget(sep3)

        # Config buttons
        cfg_row = QHBoxLayout()
        cfg_row.setSpacing(5)
        for text, tip, slot in [
            ("💾 Save Config", "Save current settings", self._save_config),
            ("📂 Load Config", "Load saved settings", self._load_config),
            ("🔄 Reset", "Restore defaults", self._reset_config),
        ]:
            btn = QPushButton(text)
            btn.setToolTip(tip)
            btn.setFixedHeight(28)
            btn.clicked.connect(slot)
            cfg_row.addWidget(btn)
        vt_lay.addLayout(cfg_row)

        root.addWidget(vt_grp)

        # ── Status bar ──
        root.addStretch()
        self._status_lbl = QLabel("Ready  ·  Open the output window to start")
        self._status_lbl.setStyleSheet(
            "color: #444466; font-size: 11px; padding: 2px 0;"
        )
        self._status_lbl.setWordWrap(True)
        root.addWidget(self._status_lbl)

    # ─── Device management ────────────────────────────────────────────────────

    def _refresh_devices(self):
        # Cameras
        prev_cam = self._cam_combo.currentData()
        self._cam_combo.clear()
        for idx, name in list_cameras():
            self._cam_combo.addItem(name, idx)
        if not self._cam_combo.count():
            self._cam_combo.addItem("No cameras found", -1)
        # Restore previous selection if possible
        for i in range(self._cam_combo.count()):
            if self._cam_combo.itemData(i) == prev_cam:
                self._cam_combo.setCurrentIndex(i)
                break

        # Mics
        prev_mic = self._mic_combo.currentData()
        self._mic_combo.clear()
        for idx, name in list_input_devices():
            self._mic_combo.addItem(name, idx)
        if not self._mic_combo.count():
            self._mic_combo.addItem("No microphones found", -1)
        for i in range(self._mic_combo.count()):
            if self._mic_combo.itemData(i) == prev_mic:
                self._mic_combo.setCurrentIndex(i)
                break

        self._status("Devices refreshed")

    # ─── Output window ───────────────────────────────────────────────────────

    def _open_output(self):
        if self._output_window is None:
            self._output_window = OutputWindow()
            self._output_window.character.set_scream_threshold(
                self._scream_slider.value() / 100
            )
            self._output_window.character.set_red_smoothness(
                self._smooth_slider.value()
            )
        self._apply_resolution()
        self._output_window.show()
        self._output_window.raise_()
        self._output_window.set_vtuber_mode(self._is_vtuber_mode)
        self._status(
            "Output window open  ·  Capture it in OBS or share it in Discord"
        )

    def _apply_resolution(self):
        if not self._output_window:
            return
        resolutions = {
            0: (1280, 720),
            1: (1920, 1080),
            2: (854, 480),
            3: (2560, 1440),
        }
        w, h = resolutions.get(self._res_combo.currentIndex(), (1280, 720))
        self._output_window.resize(w, h)

    # ─── Mode switching ──────────────────────────────────────────────────────

    def _set_vtuber_mode(self, vtuber: bool):
        self._is_vtuber_mode = vtuber
        self._cam_mode_btn.setChecked(not vtuber)
        self._vt_mode_btn.setChecked(vtuber)
        if self._output_window:
            self._output_window.set_vtuber_mode(vtuber)
        self._status("Mode: " + ("🎭 VTuber" if vtuber else "📷 Camera"))

    # ─── Camera ─────────────────────────────────────────────────────────────

    def _toggle_camera(self):
        if self._camera_thread and self._camera_thread.isRunning():
            self._camera_thread.stop()
            self._camera_thread = None
            self._cam_toggle_btn.setText("▶  Start Camera")
            self._cam_toggle_btn.setChecked(False)
            self._status("Camera stopped")
        else:
            idx = self._cam_combo.currentData()
            if idx is None or idx < 0:
                self._status("⚠  No camera selected")
                return
            self._camera_thread = CameraThread(idx)
            self._camera_thread.frame_ready.connect(self._on_frame)
            self._camera_thread.error.connect(
                lambda e: self._status(f"⚠  Camera: {e}")
            )
            self._camera_thread.start()
            self._cam_toggle_btn.setText("⏹  Stop Camera")
            self._status(f"Camera {idx} started")

    def _on_frame(self, pixmap: QPixmap):
        if self._output_window:
            self._output_window.set_camera_frame(pixmap)

    # ─── Microphone ──────────────────────────────────────────────────────────

    def _toggle_mic(self):
        if self._audio_thread and self._audio_thread.isRunning():
            self._audio_thread.stop()
            self._audio_thread = None
            self._mic_toggle_btn.setText("🎙  Start Microphone")
            self._vol_timer.stop()
            self._current_vol = 0.0
            self._vol_bar.setValue(0)
            self._status("Microphone stopped")
        else:
            idx = self._mic_combo.currentData()
            if idx is None:
                self._status("⚠  No microphone selected")
                return
            sensitivity = float(self._sens_slider.value())
            self._audio_thread = AudioThread(
                device_index=idx, sensitivity=sensitivity
            )
            self._audio_thread.volume_changed.connect(self._on_volume)
            self._audio_thread.start()
            self._mic_toggle_btn.setText("⏹  Stop Microphone")
            self._vol_timer.start()
            self._status("Microphone active  ·  Speak to test volume")

    def _on_volume(self, volume: float):
        self._current_vol = volume
        if self._output_window:
            self._output_window.update_volume(volume)

    def _refresh_vol_meter(self):
        pct = int(self._current_vol * 100)
        self._vol_bar.setValue(pct)
        # Color feedback via stylesheet
        if pct < 60:
            chunk_color = "qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #33cc77,stop:1 #44dd88)"
        elif pct < 85:
            chunk_color = "qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #ddaa22,stop:1 #ffcc44)"
        else:
            chunk_color = "qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #cc3333,stop:1 #ff5555)"
        self._vol_bar.setStyleSheet(
            f"QProgressBar::chunk {{ border-radius: 5px; background: {chunk_color}; }}"
        )

    def _on_sensitivity_change(self, val: int):
        self._sens_val_label.setText(str(val))
        if self._audio_thread:
            self._audio_thread.set_sensitivity(float(val))

    # ─── VTuber settings ─────────────────────────────────────────────────────

    def _choose_background(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose Background Image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if not path:
            return
        pixmap = QPixmap(path)
        if pixmap.isNull():
            QMessageBox.warning(self, "Error", "Could not load that image.")
            return
        if self._output_window:
            self._output_window.set_background_image(pixmap)
        self._background_path = path
        name = os.path.basename(path)
        self._bg_path_label.setText(name)
        self._bg_path_label.setStyleSheet("color: #aaaaff;")
        self._status(f"Background: {name}")

    def _add_layer(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add Character Layer(s)", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.svg)"
        )
        for path in paths:
            config = LayerConfig(path=path)
            dlg = LayerEditDialog(config, self)
            if dlg.exec_() == QDialog.Accepted:
                mn, mx = dlg.get_values()
                config.min_vol = mn
                config.max_vol = mx
            self._layer_configs.append(config)
            self._layers_list.addItem(self._layer_item_text(config))
            if self._output_window:
                self._output_window.character.add_layer(config)
        self._status(f"Added {len(paths)} layer(s)")

    def _remove_layer(self):
        row = self._layers_list.currentRow()
        if row < 0:
            return
        self._layers_list.takeItem(row)
        self._layer_configs.pop(row)
        if self._output_window:
            self._output_window.character.remove_layer(row)
        self._status("Layer removed")

    def _edit_layer(self):
        row = self._layers_list.currentRow()
        if row < 0:
            return
        config = self._layer_configs[row]
        dlg = LayerEditDialog(config, self)
        if dlg.exec_() == QDialog.Accepted:
            mn, mx = dlg.get_values()
            config.min_vol = mn
            config.max_vol = mx
            self._layers_list.item(row).setText(self._layer_item_text(config))
            if self._output_window:
                self._output_window.character.update_layer_config(row, config)
        self._status("Layer updated")

    def _move_layer_up(self):
        row = self._layers_list.currentRow()
        if row <= 0:
            return
        self._layer_configs[row], self._layer_configs[row - 1] = \
            self._layer_configs[row - 1], self._layer_configs[row]
        item = self._layers_list.takeItem(row)
        self._layers_list.insertItem(row - 1, item)
        self._layers_list.setCurrentRow(row - 1)
        if self._output_window:
            self._output_window.character.move_layer_up(row)

    def _update_layers_list(self):
        """Refresh the layers list UI from _layer_configs."""
        self._layers_list.clear()
        for config in self._layer_configs:
            self._layers_list.addItem(self._layer_item_text(config))

    def _on_scream_threshold_change(self, val: int):
        self._scream_val_lbl.setText(f"{val}%")
        if self._output_window:
            self._output_window.character.set_scream_threshold(val / 100)

    def _on_smoothness_change(self, val: int):
        self._smooth_val_lbl.setText(f"{val}ms")
        if self._output_window:
            self._output_window.character.set_red_smoothness(val)

    @staticmethod
    def _layer_item_text(config: LayerConfig) -> str:
        return f"{config.name}  [{config.min_vol:.2f} – {config.max_vol:.2f}]"

    # ─── Configuration Management ────────────────────────────────────────────

    def _get_current_config(self) -> VTuberConfig:
        """Create a VTuberConfig from current UI state."""
        return VTuberConfig(
            background_path=self._background_path,
            layers=VTuberConfig.from_layer_configs(self._layer_configs),
            scream_threshold=self._scream_slider.value() / 100.0,
            red_smoothness_ms=self._smooth_slider.value(),
            sensitivity=self._sens_slider.value(),
            resolution=self._res_combo.currentIndex(),
            camera_index=self._cam_combo.currentIndex(),
            microphone_index=self._mic_combo.currentIndex(),
        )

    def _apply_config(self, config: VTuberConfig):
        """Apply a VTuberConfig to the UI."""
        # Background
        if config.background_path and os.path.exists(config.background_path):
            self._background_path = config.background_path
            self._bg_path_label.setText(os.path.basename(config.background_path))
            self._bg_path_label.setStyleSheet("color: #88ff88; font-style: normal;")
            pixmap = QPixmap(config.background_path)
            if self._output_window:
                self._output_window.set_background_image(pixmap)
        else:
            self._background_path = ""
            self._bg_path_label.setText("No background set")
            self._bg_path_label.setStyleSheet("color: #555577; font-style: italic;")

        # Layers
        self._layer_configs = config.to_layer_configs()
        self._update_layers_list()
        if self._output_window:
            char = self._output_window.character
            char.clear_layers()
            for layer_cfg in self._layer_configs:
                char.add_layer(layer_cfg)

        # Settings
        self._scream_slider.setValue(int(config.scream_threshold * 100))
        self._smooth_slider.setValue(config.red_smoothness_ms)
        self._sens_slider.setValue(config.sensitivity)
        self._res_combo.setCurrentIndex(min(config.resolution, self._res_combo.count() - 1))

        if self._output_window:
            self._output_window.character.set_scream_threshold(config.scream_threshold)
            self._output_window.character.set_red_smoothness(config.red_smoothness_ms)

    def _save_config(self):
        """Save current configuration to file."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Configuration",
            str(self._config_manager.CONFIG_DIR),
            "JSON Config (*.json);;All Files (*)",
        )
        if not file_path:
            return

        config = self._get_current_config()

        if self._config_manager.save_config(config, file_path):
            self._current_config_path = file_path
            self._status(f"✓ Config saved to {os.path.basename(file_path)}")
        else:
            QMessageBox.warning(self, "Error", "Failed to save configuration")

    def _load_config(self):
        """Load configuration from file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Configuration",
            str(self._config_manager.CONFIG_DIR),
            "JSON Config (*.json);;All Files (*)",
        )
        if not file_path:
            return

        config = self._config_manager.load_config(file_path)
        if config:
            self._current_config_path = file_path
            self._apply_config(config)
            self._status(f"✓ Config loaded from {os.path.basename(file_path)}")
        else:
            QMessageBox.warning(self, "Error", "Failed to load configuration")

    def _reset_config(self):
        """Reset to default configuration."""
        reply = QMessageBox.question(
            self,
            "Reset Configuration",
            "Are you sure you want to reset to default settings?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            config = self._config_manager.get_default_config()
            self._apply_config(config)
            self._current_config_path = None
            self._status("✓ Reset to default settings")

    def _load_recent_config(self):
        """Automatically load recent configuration on startup."""
        if self._config_manager.has_recent_config():
            config = self._config_manager.load_config()
            if config:
                self._apply_config(config)

    # ─── Helpers ─────────────────────────────────────────────────────────────────

    def _status(self, msg: str):
        self._status_lbl.setText(msg)

    def closeEvent(self, event):
        # Save recent config before closing
        config = self._get_current_config()
        self._config_manager.save_config(config)

        if self._camera_thread:
            self._camera_thread.stop()
        if self._audio_thread:
            self._audio_thread.stop()
        if self._output_window:
            self._output_window.deleteLater()
        event.accept()
