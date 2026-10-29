
import os

PROJECT_ID = os.getenv("FALLGUARD_PROJECT", "ganti-dengan-id-unik")
BROKER_HOST = os.getenv("FALLGUARD_BROKER", "broker.hivemq.com")
BROKER_PORT = int(os.getenv("FALLGUARD_PORT", "1883"))  # TCP (Python / ESP32)
# Halaman web (HP & dashboard) memakai WebSocket: wss://broker.hivemq.com:8884/mqtt

BUFFER_SECONDS = 8            # berapa detik data sensor disimpan per device
CONFIRM_THRESHOLD = float(os.getenv("FALLGUARD_THRESHOLD", "0.6"))  # batas probabilitas ML
MODEL_PATH = os.getenv(
    "FALLGUARD_MODEL",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ml", "model.pkl"),
)


def topic(*parts: str) -> str:
    """topic('edge1', 'sensor') -> 'fallguard/<PROJECT_ID>/edge1/sensor'"""
    return "/".join(["fallguard", PROJECT_ID, *parts])
