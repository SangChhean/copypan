import io, json, sys
sys.path.insert(0, r'E:\copypan\back_mic\backend')
from kg_rag.scripts.chunking_full import _EmbeddingByteFixer

# Simulate the actual corrupt bytes from cwwl.json
text_part = b'[{"id": "cwwl_test", "text": "hello", "embedding": [0.1, -0.2'
corrupt = bytes([0xfa, 0x33, 0x8c, 0xb3, 0xa4, 0x73])  # FA 33 8C B3 A4 73 ('s')
end_part = b', 0.3], "_id": "x"}]'
test_json = text_part + corrupt + end_part
print('Input:', test_json)

fixer = _EmbeddingByteFixer(io.BytesIO(test_json))
result = fixer.read(len(test_json) + 50)
print('Output:', result)
print('Parsing as JSON...')
parsed = json.loads(result)
print('OK! id =', parsed[0]['id'])
print('embedding =', parsed[0]['embedding'])
