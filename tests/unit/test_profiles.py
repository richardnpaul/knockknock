import os
import pytest
from unittest.mock import patch

from knockknock.Profiles import Profiles


class TestProfiles:

    def test_load_profiles_from_directory(self, sample_profiles_dir):
        # Add a regular file to ensure Profiles ignores non-directories
        with open(os.path.join(sample_profiles_dir, "ignore_me.txt"), "w") as f:
            f.write("test")

        profiles = Profiles(sample_profiles_dir)
        assert not profiles.isEmpty()
        assert len(profiles.profiles) == 2

    def test_empty_directory(self, temp_dir):
        profiles = Profiles(temp_dir)
        assert profiles.isEmpty()
        assert profiles.getProfileForPort(7000) is None
        assert profiles.getProfileForName("unknown") is None
        assert profiles.getProfileForIP("127.0.0.1") is None

    def test_get_profile_for_port(self, sample_profiles_dir):
        profiles = Profiles(sample_profiles_dir)

        p1 = profiles.getProfileForPort(7001)
        assert p1 is not None
        assert p1.getName() == "host-a"

        # Test string port argument
        p2 = profiles.getProfileForPort("7002")
        assert p2 is not None
        assert p2.getName() == "host-b"

        assert profiles.getProfileForPort(9999) is None

    def test_get_profile_for_name(self, sample_profiles_dir):
        profiles = Profiles(sample_profiles_dir)

        pa = profiles.getProfileForName("host-a")
        assert pa is not None
        assert int(pa.getKnockPort()) == 7001

        pb = profiles.getProfileForName("host-b")
        assert pb is not None
        assert int(pb.getKnockPort()) == 7002

        assert profiles.getProfileForName("nonexistent") is None

    def test_get_profile_for_ip_and_resolve_names(self, sample_profiles_dir):
        profiles = Profiles(sample_profiles_dir)

        mock_dns = {
            "host-a": ("host-a", [], ["10.0.1.1", "10.0.1.2"]),
            "host-b": ("host-b", [], ["10.0.2.1"]),
        }

        def mock_gethostbyname_ex(name):
            if name in mock_dns:
                return mock_dns[name]
            raise OSError("Host not found")

        with patch("socket.gethostbyname_ex", side_effect=mock_gethostbyname_ex):
            profiles.resolveNames()

        p_found1 = profiles.getProfileForIP("10.0.1.2")
        assert p_found1 is not None
        assert p_found1.getName() == "host-a"

        p_found2 = profiles.getProfileForIP("10.0.2.1")
        assert p_found2 is not None
        assert p_found2.getName() == "host-b"

        assert profiles.getProfileForIP("192.168.99.99") is None
