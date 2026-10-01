import os
import shutil
import tempfile
import pytest
from struct import pack

from knockknock.Profile import Profile
from knockknock.Profiles import Profiles


@pytest.fixture
def sample_keys():
    """Return a pair of 16-byte cryptographically secure random keys."""
    return os.urandom(16), os.urandom(16)


@pytest.fixture
def temp_dir():
    """Provide a clean temporary directory that is automatically removed."""
    path = tempfile.mkdtemp(prefix="kk_test_")
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def sample_profile(temp_dir, sample_keys):
    """Provide a serialized Profile instance in a temporary directory."""
    cipher_key, mac_key = sample_keys
    profile = Profile(
        directory=temp_dir,
        cipherKey=cipher_key,
        macKey=mac_key,
        counter=0,
        knockPort=7000
    )
    profile.serialize()
    return profile


@pytest.fixture
def sample_profiles_dir(temp_dir, sample_keys):
    """Create a parent directory containing multiple sub-profiles."""
    cipher_key, mac_key = sample_keys
    for name, port in [("host-a", 7001), ("host-b", 7002)]:
        profile_path = os.path.join(temp_dir, name)
        os.makedirs(profile_path, exist_ok=True)
        p = Profile(
            directory=profile_path,
            cipherKey=cipher_key,
            macKey=mac_key,
            counter=0,
            knockPort=port
        )
        p.serialize()
    return temp_dir


@pytest.fixture
def make_log_line():
    """Factory fixture to generate synthetic iptables log lines."""
    def _generator(src="192.168.1.100", dpt=7000, id_field=1234, seq=5678, ack=9101, win=4096):
        return (
            f"Oct  1 12:00:00 server kernel: REJECT IN=eth0 OUT= "
            f"SRC={src} DST=192.168.1.1 LEN=40 TOS=0x00 PREC=0x00 "
            f"TTL=64 ID={id_field} PROTO=TCP SPT=43210 DPT={dpt} "
            f"SEQ={seq} ACK={ack} WINDOW={win} RES=0x00 SYN URGP=0"
        )
    return _generator
