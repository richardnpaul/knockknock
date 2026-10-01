import importlib.util
from pathlib import Path
import struct
from unittest.mock import MagicMock, patch
import pytest

cli_path = Path(__file__).resolve().parent.parent.parent / "knockknock.py"
spec = importlib.util.spec_from_file_location("knockknock_cli", str(cli_path))
assert spec is not None and spec.loader is not None
knockknock_cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(knockknock_cli)


class TestKnockKnockMain:

    def test_exists_in_path_removed(self) -> None:
        assert not hasattr(knockknock_cli, "existsInPath")

    def test_main_calls_send_syn(self, capsys: pytest.CaptureFixture[str]) -> None:
        mock_profile = MagicMock()
        mock_profile.getKnockPort.return_value = 12345
        mock_profile.encrypt.return_value = struct.pack("!HIIH", 111, 222, 333, 444)

        with patch.object(knockknock_cli, "verifyPermissions"), \
             patch.object(knockknock_cli, "getProfile", return_value=mock_profile), \
             patch.object(knockknock_cli, "send_syn") as mock_send_syn:

            knockknock_cli.main(["-p", "22", "target.example.com"])

            mock_send_syn.assert_called_once_with(
                "target.example.com", 12345, 111, 222, 333, 444
            )
            captured = capsys.readouterr()
            assert "Knock sent." in captured.out

    def test_main_send_syn_handles_permission_error(self, capsys: pytest.CaptureFixture[str]) -> None:
        mock_profile = MagicMock()
        mock_profile.getKnockPort.return_value = 12345
        mock_profile.encrypt.return_value = struct.pack("!HIIH", 111, 222, 333, 444)

        with patch.object(knockknock_cli, "verifyPermissions"), \
             patch.object(knockknock_cli, "getProfile", return_value=mock_profile), \
             patch.object(knockknock_cli, "send_syn", side_effect=PermissionError("Need CAP_NET_RAW")):

            with pytest.raises(SystemExit) as exc_info:
                knockknock_cli.main(["-p", "22", "target.example.com"])

            assert exc_info.value.code == 2
            captured = capsys.readouterr()
            assert "Error sending knock packet" in captured.out

    def test_main_send_syn_handles_os_error(self, capsys: pytest.CaptureFixture[str]) -> None:
        mock_profile = MagicMock()
        mock_profile.getKnockPort.return_value = 12345
        mock_profile.encrypt.return_value = struct.pack("!HIIH", 111, 222, 333, 444)

        with patch.object(knockknock_cli, "verifyPermissions"), \
             patch.object(knockknock_cli, "getProfile", return_value=mock_profile), \
             patch.object(knockknock_cli, "send_syn", side_effect=OSError("Network unreachable")):

            with pytest.raises(SystemExit) as exc_info:
                knockknock_cli.main(["-p", "22", "target.example.com"])

            assert exc_info.value.code == 2
            captured = capsys.readouterr()
            assert "Error sending knock packet" in captured.out

    def test_usage_exits_with_code_2(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            knockknock_cli.usage()
        assert exc_info.value.code == 2

    def test_parse_arguments_invalid_exits(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            knockknock_cli.parseArguments(["-p", "-1", "host"])
        assert exc_info.value.code == 2

    def test_verify_permissions_non_root(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("os.getuid", return_value=1000):
            with pytest.raises(SystemExit) as exc_info:
                knockknock_cli.verifyPermissions()
            assert exc_info.value.code == 2
            captured = capsys.readouterr()
            assert "must be root" in captured.out

    def test_verify_permissions_root(self) -> None:
        with patch("os.getuid", return_value=0):
            knockknock_cli.verifyPermissions()

    def test_get_profile_missing_knock_dir(self, tmp_path: Path) -> None:
        with patch("pathlib.Path.home", return_value=tmp_path):
            with pytest.raises(SystemExit) as exc_info:
                knockknock_cli.getProfile("somehost")
            assert exc_info.value.code == 2

    def test_get_profile_missing_host_dir(self, tmp_path: Path) -> None:
        knock_dir = tmp_path / ".knockknock"
        knock_dir.mkdir()
        with patch("pathlib.Path.home", return_value=tmp_path):
            with pytest.raises(SystemExit) as exc_info:
                knockknock_cli.getProfile("somehost")
            assert exc_info.value.code == 2

    def test_get_profile_success(self, tmp_path: Path) -> None:
        knock_dir = tmp_path / ".knockknock"
        knock_dir.mkdir()
        host_dir = knock_dir / "somehost"
        host_dir.mkdir()
        import binascii
        b64_key = binascii.b2a_base64(b"0" * 32)
        (host_dir / "cipher.key").write_bytes(b64_key)
        (host_dir / "mac.key").write_bytes(b64_key)
        (host_dir / "counter").write_text("0\n")
        (host_dir / "config").write_text("[main]\nknock_port = 1234\n")
        with patch("pathlib.Path.home", return_value=tmp_path):
            profile = knockknock_cli.getProfile("somehost")
            assert profile.getKnockPort() == "1234"
