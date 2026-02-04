from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk
import json
from pathlib import Path

es = Elasticsearch(hosts=['http://localhost:9200'])

# 原始数据目录
source_dir = Path(r'C:\Users\Administrator\Desktop\Pan最新备份\backup\data_complete\home\stv\data\backup')

print("=" * 70)
print("开始导入所有JSON数据到Elasticsearch")
print("=" * 70)

# 打开所有关闭的索引
print("\n检查并打开关闭的索引...")
closed_indices = ['bib', 'cwwl', 'cwwn', 'feasts', 'foo', 'hymn', 'life', 'others', 
                  'pano', 'pano_msg', 'pano_outlines', 'pano_booknames', 'pano_titles', 
                  'pano_headings', 'pano_ot1', 'cwwl_headings', 'cwwl_titles', 'cwwl_booknames',
                  'cwwn_headings', 'cwwn_titles', 'cwwn_booknames', 'feasts_titles', 'feasts_ot1',
                  'feasts_booknames', 'life_titles', 'life_headings', 'others_titles', 
                  'others_headings', 'others_booknames']

for idx in closed_indices:
    try:
        es.indices.open(index=idx, ignore_unavailable=True)
        print(f"  ✓ 已打开: {idx}")
    except Exception as e:
        if 'index_not_found' not in str(e).lower():
            print(f"  ⚠ {idx}: {str(e)[:50]}")

print("\n等待索引就绪...")
import time
time.sleep(3)

# 获取当前索引状态
existing_indices = {}
try:
    indices_info = es.cat.indices(format='json', h='index,docs.count')
    for idx in indices_info:
        existing_indices[idx['index']] = int(idx.get('docs.count', 0) or 0)
except:
    pass

print(f"\n当前ES中的索引状态：")
for idx, count in sorted(existing_indices.items()):
    if count > 0:
        print(f"  {idx:30} {count:>10} 条")

# 获取所有索引文件夹
index_dirs = [d for d in source_dir.iterdir() if d.is_dir()]
print(f"\n找到 {len(index_dirs)} 个索引文件夹")

total_imported = 0
total_skipped = 0
errors = []

for index_dir in sorted(index_dirs):
    index_name = index_dir.name
    
    # 获取该索引下所有JSON文件
    json_files = list(index_dir.glob('*.json'))
    
    if not json_files:
        print(f"\n{index_name}: 没有JSON文件，跳过")
        continue
    
    print(f"\n处理索引: {index_name}")
    print(f"  JSON文件数: {len(json_files)}")
    
    # 检查是否已有数据
    current_count = existing_indices.get(index_name, 0)
    print(f"  当前已有: {current_count} 条")
    
    # 统计总文档数
    total_docs = 0
    for json_file in json_files:
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    total_docs += len(data)
                else:
                    total_docs += 1
        except:
            pass
    
    print(f"  源数据共: {total_docs} 条")
    
    # 决定是否导入
    if current_count >= total_docs:
        print(f"  ✓ 数据已完整，跳过")
        total_skipped += current_count
        continue
    
    print(f"  → 开始导入...")
    
    imported = 0
    failed = 0
    
    # 逐个JSON文件导入
    for i, json_file in enumerate(json_files, 1):
        try:
            print(f"    [{i}/{len(json_files)}] {json_file.name}...", end=' ', flush=True)
            
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 转换为列表
            if not isinstance(data, list):
                data = [data]
            
            if not data:
                print("空文件")
                continue
            
            # 准备批量导入
            actions = []
            for doc in data:
                action = {
                    '_index': index_name,
                    '_source': doc
                }
                
                # 使用文档中的ID
                if 'id' in doc:
                    action['_id'] = str(doc['id'])
                elif 'refid' in doc:
                    action['_id'] = str(doc['refid'])
                elif '_id' in doc:
                    action['_id'] = str(doc['_id'])
                
                actions.append(action)
            
            # 批量导入
            if actions:
                success, failed_list = bulk(es, actions, raise_on_error=False, chunk_size=500)
                imported += success
                
                # 显示详细错误（仅第一个文件的第一个错误）
                if failed_list:
                    failed += len(failed_list)
                    if i == 1 and len(failed_list) > 0:
                        first_error = failed_list[0]
                        print(f"\n      错误详情: {first_error}")
                
                print(f"✓ {success}条")
            else:
                print("无数据")
                    
        except Exception as e:
            error_msg = f"{index_name}/{json_file.name}: {str(e)[:100]}"
            errors.append(error_msg)
            print(f"✗ {str(e)[:30]}")
    
    if imported > 0:
        print(f"  ✓ 索引 {index_name} 成功导入: {imported} 条")
        total_imported += imported
    if failed > 0:
        print(f"  ✗ 失败: {failed} 条")

print("\n" + "=" * 70)
print(f"导入完成！")
print(f"  新导入: {total_imported:,} 条")
print(f"  已存在: {total_skipped:,} 条")
print(f"  总计: {(total_imported + total_skipped):,} 条")
print("=" * 70)

if errors:
    print(f"\n遇到 {len(errors)} 个错误:")
    for err in errors[:10]:
        print(f"  {err}")

# 显示最终状态
print("\n最终索引状态:")
final_indices = es.cat.indices(format='json', h='index,docs.count,store.size')
sorted_indices = sorted(final_indices, key=lambda x: int(x.get('docs.count', 0) or 0), reverse=True)
for idx in sorted_indices:
    count = idx.get('docs.count', '0')
    if count and int(count) > 0:
        size = idx.get('store.size', '')
        is_new = idx['index'] not in existing_indices or existing_indices[idx['index']] == 0
        emoji = '🆕' if is_new else '✓'
        print(f"  {emoji} {idx['index']:30} {count:>10} 条  {size:>10}")

print("\n✅ 全部完成！现在可以测试搜索功能了。")