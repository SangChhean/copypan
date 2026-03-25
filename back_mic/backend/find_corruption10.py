"""Scan 10MB to find next valid JSON doc."""
TARGET = 2649751552

with open(r'E:\12490_with_bib\cwwl.json', 'rb') as f:
    f.seek(TARGET)
    data = f.read(10 * 1024 * 1024)  # 10 MB
    
    # Search for the next valid document ID pattern
    import re
    pat = re.compile(rb'"id":\s*"cwwl_\d{4}-')
    m = pat.search(data)
    if m:
        pos = m.start()
        print(f"Next valid doc at: {pos} bytes after corruption start (abs={TARGET+pos})")
        print(f"Context: {data[max(0,pos-50):pos+80]!r}")
    else:
        print("No next doc found in 10 MB!")
    
    # Also find '"_id"'
    pos2 = data.find(b'"_id"')
    print(f'"_id" found at: {pos2} (abs={TARGET+pos2 if pos2>=0 else "not found"})')
    if pos2 >= 0:
        print(f"Context: {data[max(0,pos2-10):pos2+40]!r}")
