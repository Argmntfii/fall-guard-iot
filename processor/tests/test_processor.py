"""Uji alur processor dengan MQTT client palsu (tanpa broker)."""
import json

import processor
from test_detector import DT, fall, walking


class FakeClient:
    def __init__(self):
        self.published = []

    def publish(self, topic, payload, qos=0, retain=False):
        self.published.append((topic, json.loads(payload)))


def _feed(device="edge1"):
    processor.buffers.clear()
    seq = walking(0, 2) + fall(2000)
    for x in seq:
        processor.handle_sensor(device, x)
    return 2000 + 6 * DT  # t_impact


def test_event_confirmed_by_rule_publishes_alert():
    t_imp = _feed()
    c = FakeClient()
    alert = processor.handle_event(c, "edge1", {"type": "POSSIBLE_FALL", "t_impact": t_imp})
    assert alert and alert["type"] == "FALL" and alert["source"] == "rule"
    topics = [t for t, _ in c.published]
    assert any(t.endswith("/alert") for t in topics)
    assert any(t.endswith("/processor/log") for t in topics)


def test_event_rejected_when_data_shows_walking():
    processor.buffers.clear()
    for x in walking(0, 8):
        processor.handle_sensor("edge1", x)
    c = FakeClient()
    alert = processor.handle_event(c, "edge1", {"type": "POSSIBLE_FALL", "t_impact": 4000})
    assert alert is None
    assert not any(t.endswith("/alert") for t, _ in c.published)
    log = [p for t, p in c.published if t.endswith("/processor/log")][0]
    assert log["decision"] == "REJECTED"


def test_event_without_enough_data_trusts_edge():
    processor.buffers.clear()
    c = FakeClient()
    alert = processor.handle_event(c, "edge1", {"type": "POSSIBLE_FALL", "t_impact": 5000})
    assert alert and alert["source"] == "edge-only"


def test_buffer_is_trimmed():
    processor.buffers.clear()
    for x in walking(0, 30):
        processor.handle_sensor("edge1", x)
    buf = processor.buffers["edge1"]
    assert buf[-1]["t"] - buf[0]["t"] <= 8000
