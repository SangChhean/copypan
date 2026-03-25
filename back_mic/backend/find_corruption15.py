"""Check ALL ], " occurrences in second blob to find false positives."""
SECOND_START = 2735737903  
SECOND_END = 2739931932  # confirmed real end

with open(r'E:\12490_with_bib\cwwl.json', 'rb') as f:
    f.seek(SECOND_START)
    data = f.read(SECOND_END - SECOND_START + 100)
    
    pat = b'], "'
    print(f"All '], \"' occurrences within second blob:")
    idx = 0
    count = 0
    while True:
        pos = data.find(pat, idx)
        if pos == -1:
            break
        abs_pos = SECOND_START + pos
        ctx = data[pos:pos+60]
        count += 1
        print(f"  pos={pos} (abs={abs_pos}): {ctx!r}")
        idx = pos + 1
    
    print(f"\nTotal '], \"' in second blob: {count}")
    
    # Also check all blobs for any remaining corruption after second
    print("\n=== Checking for more blobs after second end ===")
    f.seek(SECOND_END)
    data2 = f.read(10 * 1024 * 1024)  # 10 MB  
    
    # Any non-ASCII bytes?
    has_fa = b'\xfa' in data2
    print(f"\\xfa in 10MB after second blob: {has_fa}")
    if has_fa:
        pos = data2.find(b'\xfa')
        abs_pos = SECOND_END + pos
        ctx = data2[max(0,pos-20):pos+30]
        print(f"  First at abs {abs_pos}: {ctx!r}")
