"""Examine the second corruption region at 2735737903."""
TARGET2 = 2735737903

with open(r'E:\12490_with_bib\cwwl.json', 'rb') as f:
    # Look back to find the "embedding" key
    f.seek(max(0, TARGET2 - 5000))
    data = f.read(6000)
    rel_pos = min(5000, TARGET2)
    
    # Find last "embedding" key before rel_pos
    emb_key = b'"embedding"'
    last_emb = -1
    idx = 0
    while True:
        pos = data.find(emb_key, idx)
        if pos == -1 or pos >= rel_pos:
            break
        last_emb = pos
        idx = pos + 1
    
    if last_emb >= 0:
        abs_emb = TARGET2 - rel_pos + last_emb  
        print(f"'embedding' key before 0xFA at abs offset: {abs_emb}")
        print(f"Embedding key context: {data[last_emb:last_emb+60]!r}")
        print()
    
    # Check if there are other corrupted regions  
    # Look forward from TARGET2 to find next valid doc
    f.seek(TARGET2)
    data2 = f.read(1024 * 1024)  # 1 MB
    pat = b'"id": "cwwl_'
    pos = data2.find(pat)
    if pos >= 0:
        print(f"Next cwwl doc at offset {TARGET2 + pos}")
        print(f"Context: {data2[max(0,pos-20):pos+60]!r}")
    else:
        print("No next cwwl doc found in 1MB after second corruption")
    
    # Check if ], pattern appears near the second corruption
    close_pat = b'],'
    pos2 = data2.find(close_pat)
    print(f"First ], pattern at {TARGET2 + pos2 if pos2 >= 0 else 'not found'}")
    if pos2 >= 0:
        print(f"Context: {data2[max(0,pos2-5):pos2+20]!r}")
