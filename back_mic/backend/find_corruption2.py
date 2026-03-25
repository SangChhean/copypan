"""Find all non-ASCII bytes in cwwl.json and their context."""
import sys

CHUNK = 1 << 20  # 1 MB

count = 0
with open(r'E:\12490_with_bib\cwwl.json', 'rb') as f:
    offset = 0
    leftover = b''
    while True:
        raw = f.read(CHUNK)
        if not raw:
            break
        data = leftover + raw
        for i in range(len(leftover), len(data)):
            b = data[i]
            if b > 127:
                # Check if this is inside a UTF-8 sequence (continuation bytes)
                # UTF-8 continuation bytes: 0x80-0xBF
                # Starting bytes: 0xC0-0xFF
                abs_off = offset - len(leftover) + i
                ctx_start = max(0, i - 20)
                ctx_end = min(len(data), i + 20)
                ctx = data[ctx_start:ctx_end]
                # Try to decode context as utf-8 to see if it's valid
                try:
                    ctx.decode('utf-8')
                    # Valid UTF-8 - skip
                except UnicodeDecodeError:
                    # Invalid UTF-8 byte
                    count += 1
                    if count <= 10:
                        print(f"Invalid UTF-8 at abs offset {abs_off}:")
                        print(f"  Context (hex): {ctx.hex()}")
                        print(f"  Context (repr): {ctx!r}")
                        print()
        leftover = data[-50:]
        offset += len(raw)
        if count > 20:
            break

print(f"Total invalid UTF-8 regions found: {count}")
