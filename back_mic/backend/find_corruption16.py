"""Check first blob for ALL '], "' occurrences."""
FIRST_BLOB_START = 2649751552  # where binary starts inside embedding
FIRST_BLOB_END = 2657096001    # real closing ], "

with open(r'E:\12490_with_bib\cwwl.json', 'rb') as f:
    f.seek(FIRST_BLOB_START)
    data = f.read(FIRST_BLOB_END - FIRST_BLOB_START + 100)
    
    pat = b'], "'
    idx = 0
    count = 0
    print("All '], \"' in first blob:")
    while True:
        pos = data.find(pat, idx)
        if pos == -1:
            break
        abs_pos = FIRST_BLOB_START + pos
        ctx = data[pos:pos+80]
        count += 1
        print(f"  pos={pos} (abs={abs_pos}): {ctx!r}")
        idx = pos + 1
    
    print(f"\nTotal: {count}")
