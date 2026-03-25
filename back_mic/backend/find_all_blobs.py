"""Find ALL blob regions by scanning for ], " after every embedding key."""
import re

CHUNK = 1 << 20  # 1 MB
emb_key = b'"embedding"'
close_pat = b'], "'

# Strategy: find all "embedding": [ positions, then for each, 
# check if the embedding content has non-ASCII bytes (corrupt blob)

blobs = []
total_emb = 0
corrupt_emb = 0

with open(r'E:\12490_with_bib\cwwl.json', 'rb') as f:
    # Process file in chunks with overlap
    offset = 0
    leftover = b''
    while True:
        raw = f.read(CHUNK)
        if not raw:
            break
        data = leftover + raw
        
        idx = 0
        while True:
            pos = data.find(emb_key, idx)
            if pos == -1:
                break
            abs_pos = offset - len(leftover) + pos
            
            # Find opening [
            j = pos + len(emb_key)
            while j < len(data) and data[j] in (ord(':'), ord(' ')):
                j += 1
            if j < len(data) and data[j] == ord('['):
                total_emb += 1
                # Sample first 100 bytes of array content
                sample = data[j+1:j+200] if j+200 < len(data) else data[j+1:]
                if any(b >= 0x80 for b in sample[:100]):
                    pass  # might be corrupt, but sample too small
                # Check if array content has binary patterns (>40% non-ASCII in 100 bytes)
                non_ascii = sum(1 for b in sample[:100] if b >= 0x80)
                if non_ascii > 10 and total_emb % 1000 == 0:
                    print(f"Progress: {total_emb} embeddings scanned...")
            idx = pos + 1
        
        leftover = data[-len(emb_key)-10:]
        offset += len(raw)

print(f"Total embeddings in file: {total_emb}")

# Now count actual corrupt blobs by finding all non-ASCII bytes clusters
# in non-string context
print("\nSearching for corrupt blob regions...")
with open(r'E:\12490_with_bib\cwwl.json', 'rb') as f:
    blob_start = None
    last_fa_pos = -1
    offset = 0
    blob_count = 0
    while True:
        raw = f.read(CHUNK)
        if not raw:
            break
        
        pos = 0
        while True:
            fa_pos = raw.find(b'\xfa', pos)
            if fa_pos == -1:
                break
            abs_fa = offset + fa_pos
            if blob_start is None:
                blob_start = abs_fa
                blob_count += 1
            elif abs_fa - last_fa_pos > 10000:  # gap > 10KB = new blob
                print(f"Blob {blob_count}: {blob_start} to ~{last_fa_pos} "
                      f"(~{(last_fa_pos-blob_start)/1e6:.1f} MB)")
                blob_start = abs_fa
                blob_count += 1
            last_fa_pos = abs_fa
            pos = fa_pos + 1
        offset += len(raw)
    
    if blob_start is not None:
        print(f"Blob {blob_count}: {blob_start} to ~{last_fa_pos} "
              f"(~{(last_fa_pos-blob_start)/1e6:.1f} MB)")
