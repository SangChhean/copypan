"""Examine the context around the first 0xFA byte."""
TARGET_OFFSET = 2649751552

with open(r'E:\12490_with_bib\cwwl.json', 'rb') as f:
    f.seek(max(0, TARGET_OFFSET - 200))
    data = f.read(500)
    
    print("=== Context around 0xFA ===")
    rel_pos = min(200, TARGET_OFFSET)
    print(f"Bytes before (hex): {data[:rel_pos].hex()}")
    print(f"Bytes before (repr): {data[:rel_pos]!r}")
    print()
    print(f"Bytes after (hex): {data[rel_pos:].hex()}")
    print(f"Bytes after (repr): {data[rel_pos:]!r}")
