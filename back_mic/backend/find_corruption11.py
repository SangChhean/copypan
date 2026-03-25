"""Find ALL documents affected by the corruption."""

END_OF_BINARY = 2657096001  # where ] appears before "_id"
CORRUPTION_START = 2649749201  # where "embedding" key starts for the corrupt doc

print(f"Corrupt embedding size: {END_OF_BINARY - CORRUPTION_START:,} bytes ({(END_OF_BINARY - CORRUPTION_START) / 1e6:.1f} MB)")
print(f"Binary blob size: {END_OF_BINARY - 2649751552:,} bytes ({(END_OF_BINARY - 2649751552) / 1e6:.1f} MB)")

# Check what's right before the end of binary section
with open(r'E:\12490_with_bib\cwwl.json', 'rb') as f:
    f.seek(END_OF_BINARY - 200)
    data = f.read(300)
    print(f"\nContext at end of binary: {data!r}")

# Find next occurrence of corruption - any \xfa after the binary ends?
# The binary ends at offset 2,657,096,001 (~2.65 GB)
# File is 3.2 GB, so there's ~550 MB more to check
import re

count_corrupts = 0
CHUNK = 1 << 20
with open(r'E:\12490_with_bib\cwwl.json', 'rb') as f:
    f.seek(END_OF_BINARY)  # skip past known corruption
    offset = END_OF_BINARY
    while True:
        raw = f.read(CHUNK)
        if not raw:
            break
        if b'\xfa' in raw:
            pos = raw.find(b'\xfa')
            abs_pos = offset + pos
            ctx = raw[max(0,pos-20):pos+20]
            count_corrupts += 1
            if count_corrupts <= 3:
                print(f"\n0xFA at {abs_pos}: {ctx!r}")
        offset += len(raw)

print(f"\nTotal additional \\xfa after the big corruption: {count_corrupts}")
