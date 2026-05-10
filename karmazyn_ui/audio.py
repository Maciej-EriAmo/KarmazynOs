"""
KarmazynOS — Sakralny Dźwięk (proceduralny, z kolejką zdarzeń)
"""
import numpy as np
import threading
from queue import Queue

SAMPLE_RATE = 44100
try:
    import sounddevice as sd
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False

class AudioEngine:
    def __init__(self, enabled=True):
        self.enabled = enabled and AUDIO_AVAILABLE
        self.queue = Queue()
        if self.enabled:
            threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        while True:
            wave = self.queue.get()
            try:
                sd.play(wave, SAMPLE_RATE)
                sd.wait()
            except Exception:
                pass

    def _enqueue(self, samples):
        if self.enabled:
            self.queue.put(samples)

    def tick(self, atom_T: float = 0.8):
        freq = 800 + (atom_T * 1000)
        duration = 0.04
        t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
        wave = np.sin(2 * np.pi * freq * t) * 0.2
        self._enqueue(wave)

    def warm_threshold(self):
        t = np.linspace(0, 0.3, int(SAMPLE_RATE * 0.3), endpoint=False)
        wave = np.sin(2 * np.pi * 80 * t) * 0.25
        self._enqueue(wave)

    def vacuum_decay(self):
        t = np.linspace(0, 0.8, int(SAMPLE_RATE * 0.8), endpoint=False)
        wave = (np.sin(2 * np.pi * 60 * t) * 0.3 + np.random.normal(0, 0.3, len(t))) * 0.5
        self._enqueue(wave)

    def corruption(self):
        t = np.linspace(0, 0.4, int(SAMPLE_RATE * 0.4), endpoint=False)
        wave = (np.sin(2 * np.pi * 440 * np.sqrt(2) * t) + np.sin(2 * np.pi * 440 * np.sqrt(3) * t)) * 0.15
        self._enqueue(wave)

    def mandala_harmony(self):
        for f in [330, 392, 523, 660]:
            t = np.linspace(0, 0.15, int(SAMPLE_RATE * 0.15), endpoint=False)
            wave = np.sin(2 * np.pi * f * t) * 0.2
            self._enqueue(wave)

    def incense(self):
        t = np.linspace(0, 0.3, int(SAMPLE_RATE * 0.3), endpoint=False)
        wave = np.random.normal(0, 0.3, len(t)) * 0.1
        self._enqueue(wave)

    def archive_seal(self):
        for _ in range(3):
            t = np.linspace(0, 0.02, int(SAMPLE_RATE * 0.02), endpoint=False)
            wave = np.sin(2 * np.pi * 2000 * t) * 0.4
            self._enqueue(wave)