"""Examine blob 100 at 2774532253."""
TARGET = 2774532253
END_APPROX = 2775580397

with open(r'E:\12490_with_bib\cwwl.json', 'rb') as f:
    # Find context before blob
    f.seek(max(0, TARGET - 20000))
    data = f.read(25000)
    rel = min(20000, TARGET)
    
    # Find last "embedding" key
    emb_matches = []
    idx = 0
    while True:
        pos = data.find(b'"embedding"', idx)
        if pos == -1 or pos >= rel:
            break
        emb_matches.append(pos)
        idx = pos + 1
    
    if emb_matches:
        last_emb = emb_matches[-1]
        abs_emb = TARGET - rel + last_emb
        print(f"Last 'embedding' key at abs {abs_emb}")
        print(f"Context: {repr(data[last_emb:last_emb+80])}")
    else:
        print("No 'embedding' found in 20KB before blob!")
    
    # Find ], " in 2MB after blob start
    f.seek(TARGET)
    fwd = f.read(2 * 1024 * 1024)
    
    pat = b'], "'
    pos = fwd.find(pat)
    if pos >= 0:
        abs_close = TARGET + pos
        print(f"\n'], \"' at abs {abs_close} (+{pos:,} bytes from blob start)")
        print(f"Context: {repr(fwd[pos:pos+80])}")
    else:
        print("\nNO '], \"' in 2MB!")
    
    # Check how many ], " patterns are in the blob
    idx2 = 0
    count = 0
    while True:
        pos2 = fwd.find(pat, idx2)
        if pos2 == -1:
            break
        count += 1
        if count <= 3:
            print(f"  '], \"' at +{pos2}: {repr(fwd[pos2:pos2+40])}")
        idx2 = pos2 + 1
    print(f"Total '], \"' in 2MB: {count}")
