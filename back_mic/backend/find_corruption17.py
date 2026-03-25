"""Examine the second corruption region - find its JSON context."""
TARGET2 = 2735737903

with open(r'E:\12490_with_bib\cwwl.json', 'rb') as f:
    f.seek(max(0, TARGET2 - 50000))
    data = f.read(60000)
    rel_pos = min(50000, TARGET2)
    
    # Find last "embedding" key before corruption
    emb_matches = []
    idx = 0
    while True:
        pos = data.find(b'"embedding"', idx)
        if pos == -1 or pos >= rel_pos:
            break
        emb_matches.append(pos)
        idx = pos + 1
    
    if emb_matches:
        last_emb = emb_matches[-1]
        abs_emb = TARGET2 - rel_pos + last_emb
        print(f"Last 'embedding' key at abs {abs_emb}")
        print(f"Context: {repr(data[last_emb:last_emb+80])}")
    else:
        print("No 'embedding' key found in 50KB before corruption!")
    
    # Show bytes around the corruption
    print(f"\nContext -50 to +50 bytes around corruption:")
    print(repr(data[rel_pos-50:rel_pos+50]))
    
    # Find last } before the corruption (marks end of previous doc)
    last_close = data[:rel_pos].rfind(b'},')
    if last_close >= 0:
        print(f"\nLast '}},' before corruption at rel offset {last_close}")
        print(f"Context: {repr(data[last_close-20:last_close+30])}")
