"""Look at the exact embedding key format near offset 2,649,751,552."""
TARGET = 2649751552

with open(r'E:\12490_with_bib\cwwl.json', 'rb') as f:
    # Scan backwards from the \xfa position to find "embedding"
    start = max(0, TARGET - 10000)
    f.seek(start)
    data = f.read(10200)
    rel_pos = TARGET - start
    
    # Search for "embedding" backwards from rel_pos
    emb_key = b'"embedding"'
    last_pos = -1
    idx = 0
    while True:
        pos = data.find(emb_key, idx)
        if pos == -1 or pos >= rel_pos:
            break
        last_pos = pos
        idx = pos + 1
    
    if last_pos >= 0:
        abs_emb_pos = start + last_pos
        print(f"Found 'embedding' key at abs offset {abs_emb_pos}")
        print(f"Key context (50 bytes after key): {data[last_pos:last_pos+50]!r}")
        print(f"Key context hex: {data[last_pos:last_pos+50].hex()}")
        
        # Find the opening [
        j = last_pos + len(emb_key)
        while j < len(data) and data[j] in (ord(':'), ord(' ')):
            j += 1
        print(f"Byte after key+colon+whitespace: {data[j]:02x} = {chr(data[j]) if 32 <= data[j] < 127 else '?'}")
        print(f"Opening sequence (30 bytes): {data[last_pos:j+30]!r}")
    else:
        print("No 'embedding' key found in range!")
    
    # Also check the byte right before the \xfa
    print()
    print(f"Bytes at rel_pos-10 to rel_pos+10: {data[rel_pos-10:rel_pos+10]!r}")
