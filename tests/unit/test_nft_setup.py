from unittest.mock import call, patch

import pytest

from knockknock.NftSetup import NftSetup


class TestNftSetup:
    def test_init_raises_system_exit_if_nft_missing(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("shutil.which", return_value=None):
            with pytest.raises(SystemExit) as exc_info:
                NftSetup()
            assert exc_info.value.code == 3
            captured = capsys.readouterr()
            assert "nft executable not found" in captured.err

    def test_init_stores_nft_path_when_found(self) -> None:
        with patch("shutil.which", return_value="/usr/sbin/nft"):
            setup = NftSetup()
            assert setup.nft_path == "/usr/sbin/nft"

    def test_initialise_issues_idempotent_nft_calls(self) -> None:
        with patch("shutil.which", return_value="/usr/sbin/nft"), patch("subprocess.call", return_value=0) as mock_call:
            setup = NftSetup()
            setup.initialise()

            expected_calls = [
                call(
                    ["/usr/sbin/nft", "add", "table", "inet", "knockknock"],
                    shell=False,
                ),
                call(
                    [
                        "/usr/sbin/nft",
                        "add",
                        "set",
                        "inet",
                        "knockknock",
                        "open_ports",
                        "{ type ipv4_addr . inet_service; flags timeout; }",
                    ],
                    shell=False,
                ),
                call(
                    [
                        "/usr/sbin/nft",
                        "add",
                        "chain",
                        "inet",
                        "knockknock",
                        "input",
                        "{ type filter hook input priority filter - 1; policy accept; }",
                    ],
                    shell=False,
                ),
                call(
                    [
                        "/usr/sbin/nft",
                        "add",
                        "rule",
                        "inet",
                        "knockknock",
                        "input",
                        "ct",
                        "state",
                        "new",
                        "ip",
                        "saddr",
                        ".",
                        "tcp",
                        "dport",
                        "@open_ports",
                        "meter",
                        "open_limit",
                        "{ ip saddr limit rate 1/minute burst 1 packets }",
                        "meta",
                        "mark",
                        "set",
                        "0x4b4b",
                        "accept",
                    ],
                    shell=False,
                ),
            ]
            assert mock_call.call_args_list == expected_calls

    def test_teardown_issues_delete_table(self) -> None:
        with patch("shutil.which", return_value="/usr/sbin/nft"), patch("subprocess.call", return_value=0) as mock_call:
            setup = NftSetup()
            setup.teardown()

            mock_call.assert_called_once_with(
                ["/usr/sbin/nft", "delete", "table", "inet", "knockknock"],
                shell=False,
            )
