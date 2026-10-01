import os
import pytest

from knockknock.DaemonConfiguration import DaemonConfiguration


class TestDaemonConfiguration:

    def test_load_valid_config(self, temp_dir):
        config_path = os.path.join(temp_dir, "config")
        with open(config_path, "w") as f:
            f.write("[main]\ndelay=30\nerror_window=50\n")

        config = DaemonConfiguration(config_path)
        assert config.getDelay() == 30
        assert config.getWindow() == 50

    def test_missing_config_uses_defaults(self, temp_dir, capsys):
        config_path = os.path.join(temp_dir, "nonexistent.ini")
        config = DaemonConfiguration(config_path)

        assert config.getDelay() == 15
        assert config.getWindow() == 20

        captured = capsys.readouterr()
        assert "knockknock-daemon: config file not found, assuming defaults." in captured.out

    def test_config_missing_section_uses_defaults(self, temp_dir, capsys):
        config_path = os.path.join(temp_dir, "bad_section.ini")
        with open(config_path, "w") as f:
            f.write("[other_section]\nfoo=bar\n")

        config = DaemonConfiguration(config_path)
        assert config.getDelay() == 15
        assert config.getWindow() == 20

        captured = capsys.readouterr()
        assert "knockknock-daemon: config file not found, assuming defaults." in captured.out
