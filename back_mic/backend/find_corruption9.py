"""Scan farther to find where binary ends."""
TARGET = 2649751552

with open(r'E:\12490_with_bib\cwwl.json', 'rb') as f:
    f.seek(TARGET)
    data = f.read(100000)  # read 100 KB
    
    # Search for ], "_id" with up to 5 bytes gap after ]
    pat = b'"_id"'
    pos = data.find(pat)
    print(f"Pattern '\"_id\"': position={pos} (abs={TARGET+pos if pos>=0 else 'not found'})")
    if pos >= 0:
        print(f"  Context around it: {data[max(0,pos-20):pos+30]!r}")
    
    # Also search for }, { which marks end of one doc and start of next
    pat2 = b'}, {'
    pos2 = data.find(pat2)
    print(f"Pattern '}} {{': position={pos2} (abs={TARGET+pos2 if pos2>=0 else 'not found'})")
    if pos2 >= 0:
        print(f"  Context: {data[max(0,pos2-10):pos2+30]!r}")
    
    # Look for "id": "cwwl_ which marks start of next document
    pat3 = b'"id": "cwwl_'
    pos3 = data.find(pat3)
    print(f"Pattern next doc id: position={pos3} (abs={TARGET+pos3 if pos3>=0 else 'not found'})")
    if pos3 >= 0:
        print(f"  Context: {data[max(0,pos3-30):pos3+40]!r}")
    
    print()
    print(f"Total size of binary section appears to be at least: {min(pos, pos2, pos3) if min(pos,pos2,pos3)>=0 else '>100KB'}")
