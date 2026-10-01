from struct import pack

from knockknock.LogEntry import LogEntry


class TestLogEntry:
    def test_parse_valid_iptables_log_line(self, make_log_line):
        line = make_log_line(src="10.20.30.40", dpt=8000, id_field=1111, seq=222222, ack=333333, win=4444)
        entry = LogEntry(line)

        assert entry.getSourceIP() == "10.20.30.40"
        assert entry.getDestinationPort() == 8000

        expected_data = pack("!HIIH", 1111, 222222, 333333, 4444)
        assert entry.getEncryptedData() == expected_data

    def test_token_map_ignores_non_key_value_tokens(self):
        line = "Oct  1 12:00:00 kernel: REJECT PROTO=TCP DPT=9999 SRC=1.2.3.4 ID=1 SEQ=2 ACK=3 WINDOW=4 SYN"
        entry = LogEntry(line)

        assert entry.getDestinationPort() == 9999
        assert entry.getSourceIP() == "1.2.3.4"
        assert "REJECT" not in entry.tokenMap
        assert "SYN" not in entry.tokenMap
