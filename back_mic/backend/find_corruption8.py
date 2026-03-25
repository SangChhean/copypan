"""Find where the binary section ends and normal JSON resumes."""
TARGET = 2649751552  # where \xfa starts

with open(r'E:\12490_with_bib\cwwl.json', 'rb') as f:
    f.seek(TARGET)
    data = f.read(8192)  # read 8 KB after the corruption start
    
    # Look for patterns that indicate return to JSON text
    # After embedding ], we expect: ], "_id": "
    pat1 = b'], "_id"'
    pat2 = b'],"_id"'
    pat3 = b'], "_id": "'
    
    for pat in [pat1, pat2, pat3]:
        pos = data.find(pat)
        print(f"Pattern {pat!r}: position={pos} (abs={TARGET+pos if pos>=0 else 'not found'})")
    
    # Also look for the plain "]" followed by printable JSON
    print()
    print("All ']' positions in the 8KB region:")
    idx = 0
    while True:
        pos = data.find(b']', idx)
        if pos == -1:
            break
        ctx_after = data[pos:pos+20]
        print(f"  pos={pos} (abs={TARGET+pos}): after=  {ctx_after!r}")
        idx = pos + 1
