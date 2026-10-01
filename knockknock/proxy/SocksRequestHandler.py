import asyncio
from struct import pack
from typing import Any, Callable, Dict, List, Optional, Union

from knockknock.Profiles import Profiles
from .EndpointConnection import EndpointConnection
from .KnockingEndpointConnection import KnockingEndpointConnection


class SocksRequestHandler:

    INITIAL_HEADER_LEN = 2
    REQUEST_HEADER_LEN = 4

    def __init__(
        self,
        reader_or_sock: Any = None,
        writer_or_profiles: Any = None,
        profiles: Optional[Profiles] = None,
    ) -> None:
        if profiles is not None:
            self.reader: Optional[asyncio.StreamReader] = reader_or_sock
            self.writer: Optional[asyncio.StreamWriter] = writer_or_profiles
            self.profiles: Profiles = profiles
        else:
            self.reader = None
            self.writer = None
            self.profiles = writer_or_profiles

        self.input: Any = []
        self.state = 0
        self.addressType = 0
        self.address = ""
        self.port = 0
        self.rawAddressAndPort: Any = None
        self.endpoint: Optional[EndpointConnection] = None
        self.closed = False
        self.terminator: Optional[int] = self.INITIAL_HEADER_LEN

        self.stateMachine: Dict[int, Callable[[], Optional[int]]] = {
            0: self.processHeaders,
            1: self.processAuthenticationMethod,
            2: self.processRequestHeader,
            3: self.processAddressHeader,
            4: self._state_processAddressAndPort,
        }

    def _state_processAddressAndPort(self) -> Optional[int]:
        self.processAddressAndPort()
        return None

    def set_terminator(self, terminator: Optional[int]) -> None:
        self.terminator = terminator

    def _byte(self, val: Union[int, str, bytes, bytearray]) -> int:
        if isinstance(val, int):
            return val
        if isinstance(val, (bytes, bytearray)):
            return val[0]
        return ord(val)

    def sendSuccessResponse(self, localIP: str, localPort: int) -> None:
        response = b"\x05\x00\x00\x01"
        quad = localIP.split(".")
        for segment in quad:
            response = response + bytes([int(segment)])
        response = response + pack('!H', int(localPort))
        self.push(response)

    def sendCommandNotSupportedResponse(self) -> None:
        response = b"\x05\x07\x00\x01\x00\x00\x00\x00\x00\x00"
        self.push(response)

    def sendAddressNotSupportedResponse(self) -> None:
        response = b"\x05\x08\x00\x01\x00\x00\x00\x00\x00\x00"
        self.push(response)

    def sendAuthenticationResponse(self, method: int) -> None:
        response = bytes([0x05, method])
        self.push(response)

    def setupEndpoint(self) -> None:
        if self.addressType == 0x01:
            profile = self.profiles.getProfileForIP(self.address)
        elif self.addressType == 0x03:
            profile = self.profiles.getProfileForName(self.address)
        else:
            profile = None

        if profile is None:
            self.endpoint = EndpointConnection(self, self.address, self.port)
        else:
            self.endpoint = KnockingEndpointConnection(self, profile, self.address, self.port)

    def processAddressAndPort(self) -> None:
        self.rawAddressAndPort = self.input

        if self.addressType == 0x01:
            self.address = (
                f"{self._byte(self.input[0])}.{self._byte(self.input[1])}."
                f"{self._byte(self.input[2])}.{self._byte(self.input[3])}"
            )
        else:
            addr_bytes = self.input[0:-2]
            self.address = (
                addr_bytes.decode('utf-8', errors='replace')
                if isinstance(addr_bytes, (bytes, bytearray))
                else str(addr_bytes)
            )

        self.port = (self._byte(self.input[-2]) << 8) | self._byte(self.input[-1])

        self.set_terminator(None)
        self.setupEndpoint()

    def processAddressHeader(self) -> int:
        addressLength = self._byte(self.input[0]) + 2
        return addressLength

    def processRequestHeader(self) -> Optional[int]:
        command = self._byte(self.input[1])
        self.addressType = self._byte(self.input[3])

        if command != 0x01:
            self.sendCommandNotSupportedResponse()
            self.handle_close()
            return None

        if self.addressType == 0x01:
            self.state = self.state + 1  # No Address Header
            return 6
        elif self.addressType == 0x03:
            return 1
        else:
            self.sendAddressNotSupportedResponse()
            self.handle_close()
            return None

    def processAuthenticationMethod(self) -> Optional[int]:
        for method in self.input:
            if self._byte(method) == 0:
                self.sendAuthenticationResponse(0x00)
                return self.REQUEST_HEADER_LEN

        self.sendAuthenticationResponse(0xFF)
        self.handle_close()
        return None

    def processHeaders(self) -> Optional[int]:
        socksVersion = self._byte(self.input[0])
        methodCount = self._byte(self.input[1])

        if socksVersion != 5:
            self.handle_close()
            return None

        return methodCount

    def handle_close(self) -> None:
        if not self.closed:
            self.closed = True
            if self.endpoint is not None:
                self.endpoint.handle_close()
            if self.writer is not None:
                try:
                    self.writer.close()
                except OSError:
                    pass
                self.writer = None
                self.reader = None

    def printHex(self, val: Union[bytes, bytearray, str]) -> None:
        for c in val:
            print("%#x" % (ord(c) if isinstance(c, str) else c), end=" ")
        print("")

    def collect_incoming_data(self, data: bytes) -> None:
        if self.endpoint is not None:
            self.endpoint.write(data)
        else:
            if isinstance(self.input, list):
                self.input.append(data)
            else:
                self.input = [self.input, data]

    def found_terminator(self) -> None:
        if isinstance(self.input, list):
            self.input = b"".join(self.input)
        handler_fn = self.stateMachine[self.state]
        terminator = handler_fn()
        self.input = []
        self.state = self.state + 1
        self.set_terminator(terminator)

    def connectSucceeded(self, localIP: str, localPort: int) -> None:
        self.sendSuccessResponse(localIP, localPort)

    def receivedData(self, data: bytes) -> None:
        self.push(data)

    def push(self, data: bytes) -> None:
        if not self.closed and self.writer is not None:
            self.writer.write(data)

    async def _drain_writer(self) -> None:
        if self.writer is not None:
            try:
                await self.writer.drain()
            except OSError:
                pass

    async def _endpoint_drain(self) -> None:
        if self.endpoint is not None and self.endpoint.writer is not None:
            try:
                await self.endpoint.writer.drain()
            except OSError:
                pass

    async def _copy_stream(
        self,
        reader: asyncio.StreamReader,
        write_fn: Callable[[bytes], None],
        drain_coro: Callable[[], Any],
    ) -> None:
        while True:
            data = await reader.read(4096)
            if not data:
                break
            write_fn(data)
            try:
                await drain_coro()
            except OSError:
                break

    async def _stream_bidirectional(self) -> None:
        assert self.reader is not None
        assert self.endpoint is not None
        assert self.endpoint.reader is not None

        c2e = asyncio.create_task(
            self._copy_stream(self.reader, self.endpoint.write, self._endpoint_drain)
        )
        e2c = asyncio.create_task(
            self._copy_stream(self.endpoint.reader, self.push, self._drain_writer)
        )

        _, pending = await asyncio.wait(
            [c2e, e2c], return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

    async def handle(self) -> None:
        if self.reader is None or self.writer is None:
            return

        try:
            # 1. Initial greeting
            header = await self.reader.readexactly(self.INITIAL_HEADER_LEN)
            self.input = header
            method_count = self.processHeaders()
            if method_count is None:
                return

            # 2. Authentication methods
            methods = await self.reader.readexactly(method_count)
            self.input = methods
            req_header_len = self.processAuthenticationMethod()
            if req_header_len is None:
                return
            await self._drain_writer()

            # 3. Request header
            req_header = await self.reader.readexactly(req_header_len)
            self.input = req_header
            remaining_len = self.processRequestHeader()
            if remaining_len is None:
                return

            # 4. If domain name, read length and domain
            if self.addressType == 0x03:
                domain_len_byte = await self.reader.readexactly(remaining_len)
                self.input = domain_len_byte
                remaining_len = self.processAddressHeader()

            # 5. Read address and port
            addr_and_port = await self.reader.readexactly(remaining_len)
            self.input = addr_and_port
            self.processAddressAndPort()

            if self.endpoint is None:
                self.handle_close()
                return

            # 6. Connect endpoint
            connected = await self.endpoint.connect()
            if not connected:
                self.handle_close()
                return
            await self._drain_writer()

            # 7. Stream bidirectional data
            await self._stream_bidirectional()

        except (asyncio.IncompleteReadError, ConnectionResetError, BrokenPipeError, OSError):
            self.handle_close()
        finally:
            self.handle_close()
