import asyncio
from typing import Any


class EndpointConnection:
    def __init__(self, shuttle: Any, host: str, port: int) -> None:
        self.shuttle = shuttle
        self.buffer = b""
        self.destination = (host, port)
        self.closed = False
        self.connectAttempts = 0
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None

    async def connect(self) -> bool:
        for _ in range(3):
            self.connectAttempts += 1
            try:
                self.reader, self.writer = await asyncio.open_connection(self.destination[0], self.destination[1])
                self.handle_connect()
                return True
            except (OSError, asyncio.TimeoutError):
                if self.connectAttempts < 3:
                    self.reconnect_hook()
                else:
                    self.handle_close()
        return False

    def reconnect_hook(self) -> None:
        pass

    def reconnect(self) -> None:
        if self.connectAttempts < 3:
            self.connectAttempts += 1
            self.close()

    def getsockname(self) -> tuple[str, int]:
        if self.writer is not None:
            sock = self.writer.get_extra_info("socket")
            if sock is not None:
                name = sock.getsockname()
                return (str(name[0]), int(name[1]))
        return ("127.0.0.1", 0)

    def handle_connect(self) -> None:
        local_ip, local_port = self.getsockname()
        self.shuttle.connectSucceeded(local_ip, local_port)

    def handle_close(self) -> None:
        if not self.closed:
            self.closed = True
            self.shuttle.handle_close()
            self.close()

    def close(self) -> None:
        if self.writer is not None:
            try:
                self.writer.close()
            except OSError:
                pass
            self.writer = None
            self.reader = None

    def handle_error(self) -> None:
        self.reconnect()

    def handle_read(self, data: bytes | None = None) -> None:
        if data is None:
            data = b""
        self.shuttle.receivedData(data)

    def write(self, data: bytes) -> None:
        if not self.closed and self.writer is not None:
            self.writer.write(data)
