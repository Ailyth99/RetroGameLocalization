"""Read-only PINE memory access; used when the local PCSX2 lacks GDB RSP."""
import argparse
from pathlib import Path
import socket
import struct


class PineReader:
    def __init__(self, port=28011):
        self.connection = socket.create_connection(("127.0.0.1", port), timeout=10)

    def close(self):
        self.connection.close()

    def _receive(self, size):
        result = bytearray()
        while len(result) < size:
            part = self.connection.recv(size - len(result))
            if not part:
                raise RuntimeError("PINE connection closed")
            result.extend(part)
        return bytes(result)

    def read(self, address, length):
        if address < 0 or length < 0:
            raise ValueError("Address and length must be non-negative")
        result = bytearray()
        while len(result) < length:
            remaining = min(length - len(result), 32768)
            words = (remaining + 7) // 8
            # PINE opcode 3 = Read64. This client sends no write commands.
            payload = b"".join(struct.pack("<BI", 3, address + len(result) + i * 8)
                               for i in range(words))
            self.connection.sendall(struct.pack("<I", len(payload) + 4) + payload)
            reply_length = struct.unpack("<I", self._receive(4))[0]
            if not 5 <= reply_length <= 1 + words * 8 + 4:
                raise RuntimeError(f"Unexpected PINE response size: {reply_length}")
            reply = self._receive(reply_length - 4)
            if reply[0] != 0 or len(reply) != 1 + words * 8:
                raise RuntimeError(f"PINE read failed: {reply[:16].hex()}")
            result.extend(reply[1:1 + remaining])
        return bytes(result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("address", type=lambda value: int(value, 0))
    parser.add_argument("length", type=lambda value: int(value, 0))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    reader = PineReader()
    try:
        data = reader.read(args.address, args.length)
    finally:
        reader.close()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(data)
        print(f"Read {len(data)} bytes at {args.address:#x} -> {args.output}")
    else:
        print(data.hex(" "))
