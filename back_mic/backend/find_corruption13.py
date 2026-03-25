"""Examine ALL 7 corruption regions after the big blob."""
OFFSETS = [2735737903, 2735739262, 2736788695, 2657096001]  # add more if needed

import re

# Find all non-ASCII bytes after big blob end (2657096001) 
BIG_END = 2657096001
CHUNK = 1 << 20

count = 0
regions = []
with open(r'E:\12490_with_bib\cwwl.json', 'rb') as f:
    f.seek(BIG_END)
    offset = BIG_END
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
            regions.append(abs_pos)
            idx = pos + 1
        offset += len(raw)

print(f"All \\xfa offsets after big blob: {regions}")
print()

# For each region, check context
with open(r'E:\12490_with_bib\cwwl.json', 'rb') as f:
    for abs_pos in regions:
        print(f"=== \\xfa at {abs_pos} ===")
        # Check if inside "embedding": [
        f.seek(max(BIG_END, abs_pos - 2000))
        data = f.read(4000)
        rel = abs_pos - max(BIG_END, abs_pos - 2000)
        
        emb_key = b'"embedding"'
        last_emb = -1
        idx = 0
        while True:
            pos = data.find(emb_key, idx)
            if pos == -1 or pos >= rel:
                break
            last_emb = pos
            idx = pos + 1
        
        if last_emb >= 0:
            abs_emb = abs_pos - rel + last_emb
            ctx = data[last_emb:last_emb+100]
            print(f"  'embedding' at {abs_emb}: {ctx!r}")
        
        # Find ], " pattern after this offset
        f.seek(abs_pos)
        fwd = f.read(500000)
        close_pat = b'], "'
        pos2 = fwd.find(close_pat)
        if pos2 >= 0:
            abs_close = abs_pos + pos2
            print(f"  '], \"' found at {abs_close} (+{pos2} bytes)")
            print(f"  Context: {fwd[pos2:pos2+30]!r}")
        else:
            print("  NO '], \"' found in 500KB after this point!")
        print()
