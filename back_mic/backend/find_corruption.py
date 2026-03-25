"""Find corrupt regions in cwwl.json near the failing offset."""
import re, sys

CHUNK = 1 << 20  # 1 MB

embedding_key = b'"embedding"'
found = 0

with open(r'E:\12490_with_bib\cwwl.json', 'rb') as f:
    offset = 0
    leftover = b''
    while True:
        raw = f.read(CHUNK)
        if not raw:
            break
        data = leftover + raw
        
        # Find embedding arrays and check for non-ASCII bytes
        idx = 0
        while True:
            pos = data.find(embedding_key, idx)
            if pos == -1:
                break
            # Find the opening [
            j = pos + len(embedding_key)
            while j < len(data) and data[j] in (ord(':'), ord(' ')):
                j += 1
            if j >= len(data) or data[j] != ord('['):
                idx = pos + 1
                continue
            # Scan the array
            arr_start = j
            arr_end = data.find(b']', j)
            if arr_end == -1:
                break
            arr_content = data[j:arr_end+1]
            
            # Check for non-ASCII and non-float chars
            bad_bytes = [b for b in arr_content if b > 127 or (b < 32 and b not in (9, 10, 13))]
            if bad_bytes:
                abs_off = offset - len(leftover) + pos
                bad_ascii = [b for b in arr_content if b <= 127 and chr(b) not in '0123456789.-+eE, \t\n\r[]']
                print(f"Corrupt at offset {abs_off} (doc starting nearby)")
                print(f"  Non-ASCII count: {len(bad_bytes)}, bad ASCII: {bad_ascii[:10]}")
                print(f"  Raw sample: {arr_content[max(0,arr_content.find(bytes([bad_bytes[0]]))-5):arr_content.find(bytes([bad_bytes[0]]))+10]}")
                found += 1
                if found >= 5:
                    print("Found 5 corrupt regions, stopping.")
                    sys.exit(0)
            idx = arr_end + 1
        
        leftover = data[-len(embedding_key)-10:]
        offset += len(raw)

print(f"Total corrupt embedding arrays: {found}")
