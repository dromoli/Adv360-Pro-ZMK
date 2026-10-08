"""Read-only ZMK Studio dump: device info, lock state, behaviors, keymap.

Usage: python3 tools/studio_dump.py /dev/cu.usbmodemXXXX out.json
(close Clique first; unlock the keyboard with Mod+Esc)

Only sends get_* / list_* requests. Never writes, saves, or resets anything.
"""
import json, os, select, sys, termios, time, tty

SOF, ESC, EOF = 0xAB, 0xAC, 0xAD
PORT = sys.argv[1]
OUT = sys.argv[2]


# --- minimal protobuf wire helpers -------------------------------------------
def varint(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def field_varint(num, v):
    return varint(num << 3) + varint(v)


def field_bytes(num, b):
    return varint((num << 3) | 2) + varint(len(b)) + b


def parse(buf):
    """-> {field: [values]}; varints as int, length-delimited as bytes."""
    out, i = {}, 0
    while i < len(buf):
        key, i = read_varint(buf, i)
        num, wt = key >> 3, key & 7
        if wt == 0:
            v, i = read_varint(buf, i)
        elif wt == 2:
            ln, i = read_varint(buf, i)
            v, i = bytes(buf[i:i + ln]), i + ln
        elif wt == 5:
            v, i = int.from_bytes(buf[i:i + 4], "little"), i + 4
        elif wt == 1:
            v, i = int.from_bytes(buf[i:i + 8], "little"), i + 8
        else:
            raise ValueError(f"wire type {wt}")
        out.setdefault(num, []).append(v)
    return out


def read_varint(buf, i):
    n = shift = 0
    while True:
        b = buf[i]
        i += 1
        n |= (b & 0x7F) << shift
        shift += 7
        if not b & 0x80:
            return n, i


def zigzag(n):
    return (n >> 1) ^ -(n & 1)


# --- framing + transport ------------------------------------------------------
def frame(payload):
    body = bytearray([SOF])
    for b in payload:
        if b in (SOF, ESC, EOF):
            body.append(ESC)
        body.append(b)
    body.append(EOF)
    return bytes(body)


class Port:
    def __init__(self, path):
        self.fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        tty.setraw(self.fd)
        attrs = termios.tcgetattr(self.fd)
        attrs[2] |= termios.CLOCAL | termios.CREAD
        termios.tcsetattr(self.fd, termios.TCSANOW, attrs)
        self.buf = bytearray()
        self.next_id = 1

    def frames(self, timeout):
        """Yield decoded frames until timeout passes with no data."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            r, _, _ = select.select([self.fd], [], [], 0.1)
            if r:
                try:
                    self.buf += os.read(self.fd, 65536)
                except BlockingIOError:
                    pass
                deadline = time.time() + timeout
            while True:
                try:
                    s = self.buf.index(SOF)
                except ValueError:
                    self.buf.clear()
                    break
                out, j, done = bytearray(), s + 1, False
                while j < len(self.buf):
                    b = self.buf[j]
                    if b == ESC and j + 1 < len(self.buf):
                        out.append(self.buf[j + 1]); j += 2; continue
                    if b == ESC:
                        break
                    if b == EOF:
                        done = True; j += 1; break
                    out.append(b); j += 1
                if not done:
                    del self.buf[:s]
                    break
                del self.buf[:j]
                yield bytes(out)

    def request(self, subsystem_field, inner, timeout=3.0):
        rid = self.next_id
        self.next_id += 1
        msg = field_varint(1, rid) + field_bytes(subsystem_field, inner)
        os.write(self.fd, frame(msg))
        for f in self.frames(timeout):
            resp = parse(f)
            if 1 not in resp:          # notification, ignore
                continue
            rr = parse(resp[1][0])
            if rr.get(1, [None])[0] != rid:
                continue
            return rr
        raise TimeoutError(f"no response to request {rid}")


def main():
    p = Port(PORT)
    list(p.frames(0.3))  # drain

    result = {}

    rr = p.request(3, field_varint(1, 1))  # core.get_device_info
    info = parse(parse(rr[3][0])[1][0])
    result["device_name"] = info.get(1, [b""])[0].decode()

    rr = p.request(3, field_varint(2, 1))  # core.get_lock_state
    lock = parse(rr[3][0]).get(2, [0])[0]
    result["lock_state"] = "unlocked" if lock == 1 else "locked"
    print(f"device: {result['device_name']}  lock: {result['lock_state']}")

    rr = p.request(4, field_varint(1, 1))  # behaviors.list_all_behaviors
    if 2 in rr:
        print("behaviors: error", parse(rr[2][0])); sys.exit(2)
    ids = []
    lst = parse(parse(rr[4][0])[1][0]).get(1, [])
    for v in lst:  # packed or not
        if isinstance(v, bytes):
            i = 0
            while i < len(v):
                n, i = read_varint(v, i); ids.append(n)
        else:
            ids.append(v)
    behaviors = {}
    for bid in ids:
        rr = p.request(4, field_bytes(2, field_varint(1, bid)))
        d = parse(parse(rr[4][0])[2][0])
        behaviors[bid] = d.get(2, [b""])[0].decode()
    result["behaviors"] = behaviors
    print(f"behaviors: {len(behaviors)}")

    rr = p.request(5, field_varint(1, 1), timeout=5.0)  # keymap.get_keymap
    if 2 in rr:
        print("keymap: error", parse(rr[2][0])); sys.exit(3)
    km = parse(parse(rr[5][0])[1][0])
    layers = []
    for lb in km.get(1, []):
        l = parse(lb)
        binds = []
        for bb in l.get(3, []):
            b = parse(bb)
            bid = zigzag(b.get(1, [0])[0])
            binds.append([behaviors.get(bid, f"#{bid}"), b.get(2, [0])[0], b.get(3, [0])[0]])
        layers.append({"id": l.get(1, [0])[0],
                       "name": l.get(2, [b""])[0].decode(),
                       "bindings": binds})
    result["layers"] = layers
    print(f"layers: {[ (l['name'], len(l['bindings'])) for l in layers ]}")

    with open(OUT, "w") as f:
        json.dump(result, f, indent=1)
    print("wrote", OUT)


main()
