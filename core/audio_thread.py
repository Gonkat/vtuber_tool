import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal

try:
    import sounddevice as sd
    HAS_SOUNDDEVICE = True
except ImportError:
    HAS_SOUNDDEVICE = False


def list_input_devices() -> list[tuple[int, str]]:
    """Return list of (index, name) for available microphone input devices."""
    if not HAS_SOUNDDEVICE:
        return []
    devices = []
    try:
        for i, d in enumerate(sd.query_devices()):
            if d['max_input_channels'] > 0:
                name = d['name'][:50]
                devices.append((i, name))
    except Exception:
        pass
    return devices


class AudioThread(QThread):
    """Monitors microphone input and emits normalized volume level (0.0–1.0)."""

    volume_changed = pyqtSignal(float)

    def __init__(self, device_index=None, sensitivity: float = 8.0):
        super().__init__()
        self.device_index = device_index
        self.sensitivity = sensitivity
        self.running = False
        self._smoothed = 0.0
        self._scream_threshold = 0.85  # emitted as raw vol, UI applies

    def run(self):
        if not HAS_SOUNDDEVICE:
            return

        self.running = True

        def callback(indata, frames, time, status):
            rms = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2)))
            raw = min(1.0, rms * self.sensitivity)
            # Exponential smoothing: fast attack, slow decay
            if raw > self._smoothed:
                self._smoothed = raw * 0.7 + self._smoothed * 0.3
            else:
                self._smoothed = raw * 0.15 + self._smoothed * 0.85
            self.volume_changed.emit(self._smoothed)

        try:
            with sd.InputStream(
                device=self.device_index,
                channels=1,
                samplerate=44100,
                blocksize=512,
                dtype='float32',
                callback=callback,
            ):
                while self.running:
                    sd.sleep(20)
        except Exception as e:
            print(f"[Audio] Error: {e}")

    def stop(self):
        self.running = False
        self.wait(3000)

    def set_sensitivity(self, value: float):
        self.sensitivity = float(value)

    def set_scream_threshold(self, value: float):
        self._scream_threshold = value
