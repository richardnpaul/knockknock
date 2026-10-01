import os
from pathlib import Path
import time
from typing import IO, Iterator, Union


class LogFile:

    def __init__(self, file: Union[str, Path]) -> None:
        self.file: str = str(file)

    def checkForFileRotate(self, fd: IO[str]) -> IO[str]:
        freshFile = open(self.file)

        if os.path.sameopenfile(freshFile.fileno(), fd.fileno()):
            freshFile.close()
            return fd
        else:
            fd.close()
            return freshFile

    def tail(self) -> Iterator[str]:
        fd: IO[str] = open(self.file)
        fd.seek(0, os.SEEK_END)

        while True:
            fd = self.checkForFileRotate(fd)
            where = fd.tell()
            line = fd.readline()

            if not line:
                time.sleep(.25)
                fd.seek(where)
            else:
                yield line
