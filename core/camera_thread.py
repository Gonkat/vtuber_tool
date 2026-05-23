import cv2
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap


def list_cameras(max_test: int = 8) -> list[tuple[int, str]]:
    """Detect available cameras. Returns list of (index, label)."""
    cameras = []
    for i in range(max_test):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW if hasattr(cv2, 'CAP_DSHOW') else 0)
        if cap.isOpened():
            ret, _ = cap.read()
            if ret:
                cameras.append((i, f"Camera {i}"))
            cap.release()
    return cameras if cameras else [(0, "Default Camera")]


class CameraThread(QThread):
    """Captures frames from a webcam and emits them as QPixmap."""

    frame_ready = pyqtSignal(QPixmap)
    error = pyqtSignal(str)

    def __init__(self, camera_index: int = 0, fps: int = 30):
        super().__init__()
        self.camera_index = camera_index
        self.fps = fps
        self.running = False
        self._cap = None

    def run(self):
        self._cap = cv2.VideoCapture(self.camera_index)
        if not self._cap.isOpened():
            self.error.emit(f"Cannot open camera {self.camera_index}")
            return

        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        delay_ms = max(1, int(1000 / self.fps))
        self.running = True

        while self.running:
            ret, frame = self._cap.read()
            if ret:
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = frame_rgb.shape
                img = QImage(frame_rgb.data, w, h, ch * w, QImage.Format_RGB888)
                self.frame_ready.emit(QPixmap.fromImage(img))
            self.msleep(delay_ms)

        if self._cap:
            self._cap.release()
            self._cap = None

    def stop(self):
        self.running = False
        self.wait(3000)
