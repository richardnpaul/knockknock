import os
import shutil
import sys
from setuptools import setup

if len(sys.argv) > 1 and sys.argv[1] != "sdist":
    shutil.copyfile("knockknock-daemon.py", "knockknock/knockknock-daemon")
    shutil.copyfile("knockknock-genprofile.py", "knockknock/knockknock-genprofile")
    shutil.copyfile("knockknock-proxy.py", "knockknock/knockknock-proxy")
    shutil.copyfile("knockknock.py", "knockknock/knockknock")

setup(
    scripts=[
        'knockknock/knockknock-daemon',
        'knockknock/knockknock-genprofile',
        'knockknock/knockknock-proxy',
        'knockknock/knockknock',
    ],
)

if os.path.exists("build/"):
    shutil.rmtree("build/")

try:
    os.remove("knockknock/knockknock-proxy")
    os.remove("knockknock/knockknock-daemon")
    os.remove("knockknock/knockknock-genprofile")
    os.remove("knockknock/knockknock")
except OSError:
    pass
