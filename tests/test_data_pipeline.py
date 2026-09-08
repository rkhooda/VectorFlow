"""Contract tests for the real data pipeline on the bundled CIC-IDS-2018 sample."""

from pathlib import Path

import pytest

from modules.data_pipeline import process

SAMPLE = Path("data/samples/ssh_bruteforce_2018-02-14.csv")


@pytest.fixture(scope="module")
def states():
    return process(SAMPLE, {})


def test_process_contract(states):
    assert len(states) > 20
    for i, s in enumerate(states):
        assert s.window_index == i
        assert s.window_start < s.window_end
        assert len(s.features) == 75
        assert s.flow_count == s.features["flow_count"] > 0
        assert s.packet_count == s.features["Tot Fwd Pkts_sum"] + s.features["Tot Bwd Pkts_sum"]
    for prev, cur in zip(states, states[1:]):
        assert prev.window_end <= cur.window_start


def test_rejects_wrong_columns(tmp_path):
    bad = tmp_path / "flows.csv"
    bad.write_text("timestamp,src_ip\n1,10.0.0.1\n")
    with pytest.raises(ValueError, match="missing columns"):
        process(bad, {})


def test_rejects_pcap(tmp_path):
    pcap = tmp_path / "capture.pcap"
    pcap.write_bytes(b"\xd4\xc3\xb2\xa1")
    with pytest.raises(ValueError, match="CSV"):
        process(pcap, {})
