import sys
from PyQt5.QtWidgets import QApplication
from ui.main_window import MainWindow

DARK_STYLE = """
QWidget {
    background-color: #0f0f17;
    color: #e2e2f0;
    font-family: 'Segoe UI', Tahoma, Arial, sans-serif;
    font-size: 13px;
}
QMainWindow { background-color: #0f0f17; }

QPushButton {
    background-color: #1e1e2e;
    border: 1px solid #2e2e45;
    border-radius: 7px;
    padding: 7px 14px;
    color: #c8c8e8;
}
QPushButton:hover {
    background-color: #2a2a40;
    border-color: #6c6cf0;
}
QPushButton:pressed { background-color: #333355; }
QPushButton:checked {
    background-color: #5555dd;
    border-color: #7777ff;
    color: #ffffff;
    font-weight: bold;
}
QPushButton:disabled { color: #404055; border-color: #1e1e2e; }

QComboBox {
    background-color: #1e1e2e;
    border: 1px solid #2e2e45;
    border-radius: 7px;
    padding: 5px 10px;
    min-height: 26px;
    color: #c8c8e8;
}
QComboBox:hover { border-color: #6c6cf0; }
QComboBox::drop-down { border: none; width: 20px; }
QComboBox::down-arrow { width: 10px; height: 10px; }
QComboBox QAbstractItemView {
    background-color: #1e1e2e;
    border: 1px solid #3a3a5c;
    border-radius: 5px;
    selection-background-color: #5555dd;
    selection-color: #ffffff;
    padding: 4px;
}

QGroupBox {
    border: 1px solid #2a2a45;
    border-radius: 10px;
    margin-top: 10px;
    padding: 10px 8px 8px 8px;
    font-weight: bold;
    color: #8888ff;
    background-color: #0d0d18;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #9999ff;
}

QSlider::groove:horizontal {
    background: #1e1e2e;
    height: 6px;
    border-radius: 3px;
    border: 1px solid #2e2e45;
}
QSlider::handle:horizontal {
    background: #6666ee;
    width: 16px;
    height: 16px;
    border-radius: 8px;
    margin: -5px 0;
    border: 2px solid #9999ff;
}
QSlider::sub-page:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #4444bb, stop:1 #8866ff);
    border-radius: 3px;
}

QListWidget {
    background-color: #0d0d18;
    border: 1px solid #2a2a45;
    border-radius: 8px;
    padding: 4px;
    color: #c8c8e8;
}
QListWidget::item {
    padding: 5px 8px;
    border-radius: 5px;
    margin: 1px 0;
}
QListWidget::item:selected {
    background-color: #3333aa;
    color: #ffffff;
}
QListWidget::item:hover { background-color: #1e1e35; }

QProgressBar {
    background-color: #1e1e2e;
    border: 1px solid #2e2e45;
    border-radius: 6px;
    text-align: center;
    color: transparent;
    height: 12px;
}
QProgressBar::chunk {
    border-radius: 5px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #44cc88, stop:0.65 #ffcc44, stop:1 #ff4444);
}

QLabel { color: #c8c8e8; background: transparent; }
QDialog { background-color: #0f0f17; }

QDoubleSpinBox, QSpinBox {
    background-color: #1e1e2e;
    border: 1px solid #2e2e45;
    border-radius: 6px;
    padding: 4px 8px;
    color: #c8c8e8;
}
QDoubleSpinBox:hover, QSpinBox:hover { border-color: #6c6cf0; }

QScrollBar:vertical {
    background: #0f0f17;
    width: 8px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #2e2e4e;
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover { background: #4444aa; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

QDialogButtonBox QPushButton { min-width: 80px; }
QToolTip {
    background-color: #1e1e35;
    border: 1px solid #5555bb;
    color: #e2e2f0;
    border-radius: 5px;
    padding: 4px 8px;
}
"""


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setStyleSheet(DARK_STYLE)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()                          