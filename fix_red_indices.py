"""
修复 Elasticsearch 红色索引（关闭后重新打开）。

失败原因说明：
  若报错 "analyzer [ik_max_word] has not been conf"，说明索引的 mapping 使用了
  IK 中文分词器，但当前集群未安装 IK 插件。必须先安装插件再重试本脚本。

  安装 IK 插件（版本需与 Elasticsearch 一致，例如 ES 8.11）：
    cd <ES安装目录>
    bin/elasticsearch-plugin install https://github.com/medcl/elasticsearch-analysis-ik/releases/download/v8.11.0/elasticsearch-analysis-ik-8.11.0.zip
  安装后需重启 Elasticsearch，再运行本脚本。
"""
from elasticsearch import Elasticsearch
from elasticsearch.exceptions import ApiError
import time

es = Elasticsearch(hosts=['http://localhost:9200'])

print("=" * 50)
print("开始修复红色索引")
print("=" * 50)

# 获取所有红色索引
indices_info = es.cat.indices(format='json', h='index,health')
red_indices = [idx['index'] for idx in indices_info if idx['health'] == 'red']

print(f"\n发现 {len(red_indices)} 个红色索引:")
for idx in red_indices:
    print(f"  - {idx}")

if not red_indices:
    print("\n没有红色索引，无需修复！")
    exit(0)

print(f"\n开始修复...")
success_count = 0
failed_indices = []

for i, index in enumerate(red_indices, 1):
    print(f"\n[{i}/{len(red_indices)}] 修复索引: {index}")
    try:
        # 关闭索引
        print(f"  关闭中...")
        es.indices.close(index=index, ignore_unavailable=True)
        time.sleep(2)
        
        # 重新打开
        print(f"  打开中...")
        es.indices.open(index=index, ignore_unavailable=True)
        time.sleep(3)
        
        # 检查状态
        status = es.cat.indices(index=index, format='json', h='index,health')[0]
        new_health = status['health']
        
        if new_health in ['yellow', 'green']:
            print(f"  ✅ 成功! 状态: {new_health}")
            success_count += 1
        else:
            print(f"  ⚠️  仍然是: {new_health}")
            failed_indices.append(index)
            
    except ApiError as e:
        err_msg = str(e)
        print(f"  ❌ 错误: {err_msg[:200]}")
        if "ik_max_word" in err_msg or "analyzer" in err_msg.lower():
            print("  → 原因: 索引使用了 IK 分词器，但集群未安装 IK 插件。")
            print("  → 解决: 安装与 ES 版本匹配的 analysis-ik 插件并重启 ES，再重试。")
        failed_indices.append(index)
    except Exception as e:
        print(f"  ❌ 错误: {str(e)[:200]}")
        failed_indices.append(index)

print("\n" + "=" * 50)
print("修复完成!")
print("=" * 50)
print(f"成功: {success_count}/{len(red_indices)}")
if failed_indices:
    print(f"失败: {len(failed_indices)} 个")
    print("失败的索引:")
    for idx in failed_indices:
        print(f"  - {idx}")
else:
    print("🎉 所有红色索引都已修复!")

# 显示最终状态
print("\n最终索引状态:")
final_indices = es.cat.indices(format='json', h='index,health,docs.count')
for idx in sorted(final_indices, key=lambda x: x['health']):
    health_emoji = '🟢' if idx['health'] == 'green' else '🟡' if idx['health'] == 'yellow' else '🔴'
    print(f"  {health_emoji} {idx['health']:6} {idx['index']:30} {idx.get('docs.count', '0'):>10} 条")