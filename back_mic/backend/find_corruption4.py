"""Find bytes FA 8C B3 A4 (from the original ijson error) in cwwl.json."""
import sys

TARGETS = [0xfa, 0x8c, 0xb3, 0xa4]  # from original error: \xfa3\x8c\xb3\xa4s
# Look for the exact sequence \xfa
CHUNK = 64 * 1024

count = 0
with open(r'E:\12490_with_bib\cwwl.json', 'rb') as f:
    abs_offset = 0
    leftover = b''
    while True:
        raw = f.read(CHUNK)
        if not raw:
            break
        data = leftover + raw
        
        # Search for 0xFA (0xfa is the first corrupted byte in original error)
        idx = 0
        while True:
            pos = data.find(b'\xfa', idx)
            if pos == -1:
                break
            abs_pos = abs_offset - len(leftover) + pos
            ctx = data[max(0, pos-30):pos+30]
            print(f"0xFA at abs offset {abs_pos}")
            print(f"  Context hex: {ctx.hex()}")
            print(f"  Context repr: {ctx!r}")
            count += 1
            if count >= 5:
                print(f"Found 5 occurrences, stopping.")
                sys.exit(0)
            idx = pos + 1
        
        leftover = data[-5:]
        abs_offset += len(raw)

print(f"Total 0xFA bytes found: {count}")
