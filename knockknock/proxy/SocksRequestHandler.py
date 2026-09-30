
import asynchat, asyncore
import socket, string
from struct import *

from .EndpointConnection import EndpointConnection
from .KnockingEndpointConnection import KnockingEndpointConnection

class SocksRequestHandler(asynchat.async_chat):

    def __init__(self, sock, profiles):
        asynchat.async_chat.__init__(self, sock=sock)

        self.INITIAL_HEADER_LEN = 2
        self.REQUEST_HEADER_LEN = 4

        self.profiles     = profiles
        self.input        = []
        self.state        = 0
        self.endpoint     = None
        self.stateMachine = {
            0: self.processHeaders,
            1: self.processAuthenticationMethod,
            2: self.processRequestHeader,
            3: self.processAddressHeader,
            4: self.processAddressAndPort,
            }

        self.set_terminator(self.INITIAL_HEADER_LEN)

    def _byte(self, val):
        return val if isinstance(val, int) else ord(val)

    def sendSuccessResponse(self, localIP, localPort):
        response = b"\x05\x00\x00\x01" 
        
        quad = localIP.split(".")
        
        for segment in quad:
            response = response + bytes([int(segment)])
        
        response = response + pack('!H', int(localPort))

        self.push(response)

    def sendCommandNotSupportedResponse(self):
        response = b"\x05\x07\x00\x01\x00\x00\x00\x00\x00\x00"
        self.push(response)

    def sendAddressNotSupportedResponse(self):
        response = b"\x05\x08\x00\x01\x00\x00\x00\x00\x00\x00"
        self.push(response)

    def sendAuthenticationResponse(self, method):
        response = bytes([0x05, method])
        self.push(response)

    def setupEndpoint(self):
        if (self.addressType == 0x01):            
            profile = self.profiles.getProfileForIP(self.address)
        else:
            profile = self.profiles.getProfileForName(self.address)

        if profile == None:
            self.endpoint = EndpointConnection(self, self.address, self.port)
        else:
            self.endpoint = KnockingEndpointConnection(self, profile, self.address, self.port)


    def processAddressAndPort(self):
        self.rawAddressAndPort = self.input

        if (self.addressType == 0x01):
            self.address = str(self._byte(self.input[0])) + "." + str(self._byte(self.input[1])) + "." + str(self._byte(self.input[2])) + "." + str(self._byte(self.input[3]))
        else:
            addr_bytes = self.input[0:-2]
            self.address = addr_bytes.decode('utf-8', errors='replace') if isinstance(addr_bytes, (bytes, bytearray)) else addr_bytes

        self.port = self._byte(self.input[-2]) * 256 + self._byte(self.input[-1]) 

        self.set_terminator(None)
        self.setupEndpoint()

    def processAddressHeader(self):
        addressLength = self._byte(self.input[0]) + 2
        return addressLength

    def processRequestHeader(self):
        command          = self._byte(self.input[1])
        self.addressType = self._byte(self.input[3])

        if (command != 0x01):
            self.sendCommandNotSupportedResponse()
            self.handle_close()
            return

        if (self.addressType == 0x01):
            self.state = self.state + 1 # No Address Header
            return 6
        elif (self.addressType == 0x03):
            return 1
        else:
            self.sendAddressNotSupportedResponse()
            self.handle_close()        

    def processAuthenticationMethod(self):
        for method in self.input:
            if (self._byte(method) == 0):
                self.sendAuthenticationResponse(0x00)
                return self.REQUEST_HEADER_LEN

        self.sendAuthenticationResponse(0xFF)
        self.handle_close()

    def processHeaders(self):
        socksVersion = self._byte(self.input[0])
        methodCount  = self._byte(self.input[1])

        if (socksVersion != 5):
            self.handle_close()
            return

        return methodCount


    def handle_close(self):
        if (self.endpoint != None):
            self.endpoint.handle_close()

        asynchat.async_chat.handle_close(self)
        

    # async_chat impl

    def printHex(self, val):
        for c in val:
            print("%#x" % (ord(c) if isinstance(c, str) else c), end=" ")
            
        print("")

    def collect_incoming_data(self, data):
        if (self.endpoint != None):
            self.endpoint.write(data)
        else:
            self.input.append(data)

    def found_terminator(self):
        self.input = b"".join(self.input)
        terminator = self.stateMachine[self.state]()
        self.input = []
        self.state = self.state + 1
        
        self.set_terminator(terminator)
    
    # Shuttle Methods

    def connectSucceeded(self, localIP, localPort):
        self.sendSuccessResponse(localIP, localPort)
        
    def receivedData(self, data):
        self.push(data)

