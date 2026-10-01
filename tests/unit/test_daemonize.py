import os
from unittest.mock import patch

import pytest

import knockknock.daemonize as daemonize


class TestDaemonize:
    def test_create_daemon_success(self):
        with (
            patch("os.fork", side_effect=[0, 0]),
            patch("os._exit") as mock_exit,
            patch("os.setsid") as mock_setsid,
            patch("os.chdir") as mock_chdir,
            patch("os.umask") as mock_umask,
            patch("os.open", return_value=0) as mock_open,
            patch("os.dup2") as mock_dup2,
        ):
            ret = daemonize.createDaemon()

            assert ret == 0
            mock_exit.assert_not_called()
            mock_setsid.assert_called_once()
            mock_chdir.assert_called_once_with("/")
            mock_umask.assert_called_once_with(0)
            mock_open.assert_called_once_with(daemonize.REDIRECT_TO, os.O_RDWR)
            assert mock_dup2.call_count == 2
            mock_dup2.assert_any_call(0, 1)
            mock_dup2.assert_any_call(0, 2)

    def test_first_fork_parent_exits(self):
        with patch("os.fork", return_value=1), patch("os._exit") as mock_exit, patch("os.setsid") as mock_setsid:
            daemonize.createDaemon()
            mock_exit.assert_called_once_with(0)
            mock_setsid.assert_not_called()

    def test_first_fork_error_raises_exception(self):
        err = OSError(17, "File exists")
        with patch("os.fork", side_effect=err):
            with pytest.raises(Exception, match=r"File exists \[17\]"):
                daemonize.createDaemon()

    def test_second_fork_parent_exits(self):
        with (
            patch("os.fork", side_effect=[0, 1]),
            patch("os.setsid") as mock_setsid,
            patch("os.chdir") as mock_chdir,
            patch("os._exit") as mock_exit,
        ):
            daemonize.createDaemon()
            mock_setsid.assert_called_once()
            mock_exit.assert_called_once_with(0)
            mock_chdir.assert_not_called()

    def test_second_fork_error_raises_exception(self):
        err = OSError(12, "Cannot allocate memory")
        with patch("os.fork", side_effect=[0, err]), patch("os.setsid"):
            with pytest.raises(Exception, match=r"Cannot allocate memory \[12\]"):
                daemonize.createDaemon()

    def test_first_fork_negative_pid_exits(self) -> None:
        """Fork returning -1 takes the parent/else path (kills boundary -1 shift on pid == 0)."""
        with patch("os.fork", return_value=-1), patch("os._exit") as mock_exit, patch("os.setsid") as mock_setsid:
            daemonize.createDaemon()
            mock_exit.assert_called_once_with(0)
            mock_setsid.assert_not_called()

    def test_first_fork_large_pid_exits(self) -> None:
        """Fork returning 2 takes the parent/else path (kills boundary +1 shift on pid == 0)."""
        with patch("os.fork", return_value=2), patch("os._exit") as mock_exit, patch("os.setsid") as mock_setsid:
            daemonize.createDaemon()
            mock_exit.assert_called_once_with(0)
            mock_setsid.assert_not_called()

    def test_devnull_fallback(self) -> None:
        import importlib

        original_devnull = getattr(os, "devnull", None)
        try:
            if hasattr(os, "devnull"):
                delattr(os, "devnull")
            importlib.reload(daemonize)
            assert daemonize.REDIRECT_TO == "/dev/null"
        finally:
            if original_devnull is not None:
                os.devnull = original_devnull
            importlib.reload(daemonize)
