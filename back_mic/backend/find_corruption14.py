"""Find end of second binary blob and all blob regions."""
SECOND_START = 2735737903

with open(r'E:\12490_with_bib\cwwl.json', 'rb') as f:
    f.seek(SECOND_START)
    # Search up to 20MB for ], " pattern
    data = f.read(20 * 1024 * 1024)
    
    close_pat = b'], "'
    pos = data.find(close_pat)
    if pos >= 0:
        abs_end = SECOND_START + pos
        print(f"End of second blob at {abs_end} (offset +{pos:,})")
        print(f"Context: {data[pos:pos+60]!r}")
    else:
        print(f"No '], \"' in 20MB! Second blob > 20MB")
    
    # Also check for next cwwl doc ID
    pat2 = b'"id": "cwwl_'
    pos2 = data.find(pat2)
    if pos2 >= 0:
        print(f"\nNext cwwl doc at {SECOND_START + pos2}")
        print(f"Context: {data[pos2:pos2+60]!r}")
    else:
        print(f"No next cwwl doc in 20MB!")
