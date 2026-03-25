"""Find the FIRST actual invalid UTF-8 byte in cwwl.json."""
import sys

CHUNK = 64 * 1024  # 64 KB

with open(r'E:\12490_with_bib\cwwl.json', 'rb') as f:
    abs_offset = 0
    leftover = b''
    while True:
        raw = f.read(CHUNK)
        if not raw:
            break
        data = leftover + raw
        
        # Try to decode in UTF-8 strict; find exact failure position
        try:
            data[:-3].decode('utf-8')  # leave last 3 bytes as potential continuation
            leftover = data[-3:]
            abs_offset += len(raw)
        except UnicodeDecodeError as e:
            # Found the bad byte
            bad_pos_in_data = e.start
            abs_bad = abs_offset - len(leftover) + bad_pos_in_data
            ctx = data[max(0, bad_pos_in_data-50):bad_pos_in_data+50]
            print(f"First bad UTF-8 byte at absolute offset: {abs_bad}")
            print(f"Error: {e}")
            print(f"Context (hex): {ctx.hex()}")
            print(f"Context (repr): {ctx!r}")
            break
