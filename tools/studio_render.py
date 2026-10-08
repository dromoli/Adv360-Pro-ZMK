"""Print a studio_dump.py JSON as ZMK bindings per layer, plus Clique custom macros.

Usage: python3 tools/studio_render.py backup/<dump>.json
"""
import json, sys
d = json.load(open(sys.argv[1]))
K = {}
for i, c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"): K[0x04 + i] = c
for i in range(9): K[0x1E + i] = f"N{i+1}"
K[0x27] = "N0"
K.update({0x28: "ENTER", 0x29: "ESC", 0x2A: "BSPC", 0x2B: "TAB", 0x2C: "SPACE", 0x2D: "MINUS",
          0x2E: "EQUAL", 0x2F: "LBKT", 0x30: "RBKT", 0x31: "BSLH", 0x32: "NON_US_HASH", 0x33: "SEMI",
          0x34: "SQT", 0x35: "GRAVE", 0x36: "COMMA", 0x37: "DOT", 0x38: "FSLH", 0x39: "CAPS",
          0x46: "PSCRN", 0x47: "SLCK", 0x48: "PAUSE_BREAK", 0x49: "INS", 0x4A: "HOME", 0x4B: "PG_UP",
          0x4C: "DEL", 0x4D: "END", 0x4E: "PG_DN", 0x4F: "RIGHT", 0x50: "LEFT", 0x51: "DOWN", 0x52: "UP",
          0x53: "KP_NUM", 0x54: "KP_DIVIDE", 0x55: "KP_MULTIPLY", 0x56: "KP_MINUS", 0x57: "KP_PLUS",
          0x58: "KP_ENTER", 0x62: "KP_N0", 0x63: "KP_DOT", 0x64: "NON_US_BSLH", 0x65: "K_APP",
          0x67: "KP_EQUAL", 0xE0: "LCTRL", 0xE1: "LSHFT", 0xE2: "LALT", 0xE3: "LGUI", 0xE4: "RCTRL",
          0xE5: "RSHFT", 0xE6: "RALT", 0xE7: "RGUI"})
for i in range(12): K[0x3A + i] = f"F{i+1}"
for i in range(12): K[0x68 + i] = f"F{i+13}"
for i in range(9): K[0x59 + i] = f"KP_N{i+1}"
C = {0xE9: "C_VOL_UP", 0xEA: "C_VOL_DN", 0xE2: "C_MUTE", 0xCD: "C_PP", 0xB5: "C_NEXT", 0xB6: "C_PREV",
     0x6F: "C_BRI_UP", 0x70: "C_BRI_DN"}
MODS = [(0x01, "LC"), (0x02, "LS"), (0x04, "LA"), (0x08, "LG"), (0x10, "RC"), (0x20, "RS"), (0x40, "RA"), (0x80, "RG")]

def key(v):
    mods, page, u = v >> 24, (v >> 16) & 0xFF, v & 0xFFFF
    name = (K if page == 7 else C if page == 0x0C else {}).get(u, f"0x{v:x}")
    for bit, m in MODS:
        if mods & bit: name = f"{m}({name})"
    return name

BT = {0: "BT_CLR", 1: "BT_NXT", 2: "BT_PRV", 3: "BT_SEL", 4: "BT_CLR_ALL", 5: "BT_DISC"}
BL = {0: "BL_ON", 1: "BL_OFF", 2: "BL_TOG", 3: "BL_INC", 4: "BL_DEC"}

def bind(n, p1, p2):
    if n == "Key Press": return f"&kp {key(p1)}"
    if n == "Momentary Layer": return f"&mo {p1}"
    if n == "Toggle Layer": return f"&tog {p1}"
    if n == "Transparent": return "&trans"
    if n == "None": return "&none"
    if n == "Mod-Tap": return f"&mt {key(p1)} {key(p2)}"
    if n == "Bluetooth": return f"&bt {BT[p1]}" + (f" {p2}" if p1 in (3, 5) else "")
    if n == "Backlight": return f"&bl {BL[p1]}"
    if n == "Underglow": return "&rgb_ug RGB_TOG" if p1 == 0 else f"&rgb_ug {p1}"
    if n == "Bootloader": return "&bootloader"
    if n == "Studio Unlock": return "&studio_unlock"
    if n == "macro_ver": return "&macro_ver"
    if n == "Battery Level": return "&stp STP_BAT"
    if n.startswith("Custom Macro"): return "&CUSTOM_MACRO_" + n.split()[-1]
    return f"<{n} {p1} {p2}>"

ROWS = [14, 14, 18, 14, 16]
for l in d["layers"]:
    print(f"== {l['id']} {l['name']}")
    b = [bind(*x) for x in l["bindings"]]
    i = 0
    for r in ROWS:
        print("  ", " | ".join(f"{j}:{b[j]}" for j in range(i, i + r)))
        i += r
    for m in range(12):
        steps = [bind(*x) for x in l["bindings"][76 + 32 * m: 76 + 32 * (m + 1)]]
        steps = [s for s in steps if s not in ("&none", "&trans")]
        if steps: print(f"   macro {m+1}: {steps}")
