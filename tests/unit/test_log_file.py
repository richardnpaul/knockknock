import os
import time
import pytest
from unittest.mock import patch

from knockknock.LogFile import LogFile


class TestLogFile:

    def test_check_for_file_rotate_no_rotation(self, temp_dir):
        log_path = os.path.join(temp_dir, "kern.log")
        with open(log_path, "w") as f:
            f.write("line 1\n")

        log_file = LogFile(log_path)
        fd = open(log_path)
        try:
            fd_after = log_file.checkForFileRotate(fd)
            assert fd_after == fd
            assert not fd.closed
        finally:
            fd.close()

    def test_check_for_file_rotate_with_rotation(self, temp_dir):
        log_path = os.path.join(temp_dir, "kern.log")
        rotated_path = os.path.join(temp_dir, "kern.log.1")

        with open(log_path, "w") as f:
            f.write("old file\n")

        log_file = LogFile(log_path)
        old_fd = open(log_path)

        # Simulate logrotate: rename old file, create new file at original path
        os.rename(log_path, rotated_path)
        with open(log_path, "w") as f:
            f.write("new file\n")

        old_fileno = old_fd.fileno()
        new_fd = log_file.checkForFileRotate(old_fd)
        try:
            assert old_fd.closed
            assert new_fd.fileno() != old_fileno
            assert not new_fd.closed
        finally:
            new_fd.close()


    def test_tail_reads_new_lines_and_handles_sleep(self, temp_dir):
        log_path = os.path.join(temp_dir, "kern.log")
        # Pre-populate with initial line that should be skipped by SEEK_END
        with open(log_path, "w") as f:
            f.write("initial line before tail\n")

        log_file = LogFile(log_path)
        gen = log_file.tail()

        # Step 1: Advance generator into wait loop
        # We patch time.sleep to avoid waiting and to append data on sleep
        appended = False

        def mock_sleep(duration):
            nonlocal appended
            if not appended:
                with open(log_path, "a") as f:
                    f.write("appended line 1\n")
                appended = True

        with patch("time.sleep", side_effect=mock_sleep):
            first_line = next(gen)

        assert first_line == "appended line 1\n"
