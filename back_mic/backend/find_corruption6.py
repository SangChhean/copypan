"""Count all 0xFA occurrences and check context (0xFA is rare in valid UTF-8)."""
import sys

# Find all \xfa bytes and see if they're all in embedding arrays
# (0xFA is not a valid UTF-8 start or continuation byte in modern UTF-8)
count = 0
CHUNK = 1 << 20  # 1 MB

with open(r'E:\12490_with_bib\cwwl.json', 'rb') as f:
    offset = 0
    while True:
        raw = f.read(CHUNK)
        if not raw:
            break
        idx = 0
        while True:
            pos = raw.find(b'\xfa', idx)
            if pos == -1:
                break
            abs_pos = offset + pos
            count += 1
            idx = pos + 1
        offset += len(raw)

print(f"Total 0xFA bytes in file: {count}")

# Also find how many documents have binary embedding (looking for \xfa near embedding key)
# Search for "embedding": [...\xfa (the specific pattern)
count2 = 0
SEARCH = b'"embedding": ['
with open(r'E:\12490_with_bib\cwwl.json', 'rb') as f:
    offset = 0
    leftover = b''
    while True:
        raw = f.read(CHUNK)
        if not raw:
            break
        data = leftover + raw
        idx = 0
        while True:
            pos = data.find(SEARCH, idx)
            if pos == -1:
                break
            abs_pos = offset - len(leftover) + pos
            # Check if there's a 0xFA within next 2048 bytes
            sample = data[pos:pos+2048]
            if b'\xfa' in sample:
                count2 += 1
            idx = pos + 1
        leftover = data[-len(SEARCH):]
        offset += len(raw)

print(f"Documents with binary embedding (\\xfa in embedding): {count2}")
