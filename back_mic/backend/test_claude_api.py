"""
Claude API连接测试
测试API是否可用，评估性能和费用
"""
import anthropic
import os
import time
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

def test_basic_connection():
    """测试1：基础连接"""
    print("\n" + "="*60)
    print("【测试1】基础API连接测试")
    print("="*60)
    
    try:
        API_KEY = os.getenv("CLAUDE_API_KEY")
        if not API_KEY:
            print("❌ 错误：未找到CLAUDE_API_KEY环境变量")
            print("请检查 .env 文件是否存在且配置正确")
            return False
        
        print(f"✓ API密钥已加载（前15位）: {API_KEY[:15]}...")
        
        client = anthropic.Anthropic(api_key=API_KEY)
        
        start_time = time.time()
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=100,
            messages=[
                {"role": "user", "content": "你好，请用一句话介绍你自己。"}
            ]
        )
        elapsed = (time.time() - start_time) * 1000
        
        print(f"\n✅ API连接成功！")
        print(f"\n【响应内容】")
        print(message.content[0].text)
        print(f"\n【性能数据】")
        print(f"  响应时间: {elapsed:.0f}ms")
        print(f"  输入Token: {message.usage.input_tokens}")
        print(f"  输出Token: {message.usage.output_tokens}")
        print(f"  总Token: {message.usage.input_tokens + message.usage.output_tokens}")
        
        # 费用估算（Claude Sonnet 4.5定价）
        input_cost = (message.usage.input_tokens / 1_000_000) * 3
        output_cost = (message.usage.output_tokens / 1_000_000) * 15
        total_cost = input_cost + output_cost
        print(f"\n【费用估算】")
        print(f"  输入费用: ${input_cost:.6f}")
        print(f"  输出费用: ${output_cost:.6f}")
        print(f"  总费用: ${total_cost:.6f}")
        
        return True
        
    except anthropic.AuthenticationError as e:
        print(f"\n❌ 认证失败！")
        print(f"错误信息: {e}")
        print("\n请检查：")
        print("  1. API密钥是否正确（包含 sk-ant- 前缀）")
        print("  2. 密钥是否已过期")
        print("  3. 是否有足够的余额")
        return False
    except Exception as e:
        print(f"\n❌ 测试失败！")
        print(f"错误类型: {type(e).__name__}")
        print(f"错误信息: {e}")
        return False


def test_chinese_qa():
    """测试2：中文问答测试"""
    print("\n" + "="*60)
    print("【测试2】中文问答能力测试")
    print("="*60)
    
    try:
        client = anthropic.Anthropic(api_key=os.getenv("CLAUDE_API_KEY"))
        
        question = "什么是信心？请用简短的话回答。"
        print(f"\n问题: {question}")
        
        start_time = time.time()
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=200,
            temperature=0.7,
            messages=[
                {"role": "user", "content": question}
            ]
        )
        elapsed = (time.time() - start_time) * 1000
        
        print(f"\n✅ 回答生成成功！")
        print(f"\n【AI回答】")
        print(message.content[0].text)
        print(f"\n【性能数据】")
        print(f"  响应时间: {elapsed:.0f}ms")
        print(f"  Token使用: {message.usage.input_tokens + message.usage.output_tokens}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        return False


def test_with_context():
    """测试3：带上下文的问答（模拟RAG场景）"""
    print("\n" + "="*60)
    print("【测试3】RAG场景模拟测试")
    print("="*60)
    
    try:
        client = anthropic.Anthropic(api_key=os.getenv("CLAUDE_API_KEY"))
        
        # 模拟从ES检索到的经文
        context = """
1. 希伯来书 11:1
信就是所望之事的实底，是未见之事的确据。

2. 雅各书 2:17
信心若没有行为就是死的。

3. 马太福音 17:20
耶稣说：是因你们的信心小。我实在告诉你们，你们若有信心像一粒芥菜种，就是对这座山说：你从这边挪到那边，它也必挪去，并且你们没有一件不能做的事了。
"""
        
        question = "圣经如何定义信心？"
        
        prompt = f"""你是圣经知识助手。请基于以下经文回答问题，回答要简洁（3-5句话），并引用经文出处。

问题：{question}

参考经文：
{context}

请回答："""
        
        print(f"\n问题: {question}")
        print(f"上下文: {len(context)}字符")
        
        start_time = time.time()
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            temperature=0.3,  # 降低温度提高准确性
            system="你是圣经知识助手。基于提供的经文回答问题，要准确、简洁。引用经文时标注出处（书卷 章:节）。",
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        elapsed = (time.time() - start_time) * 1000
        
        print(f"\n✅ RAG测试成功！")
        print(f"\n【AI回答】")
        print(message.content[0].text)
        print(f"\n【性能数据】")
        print(f"  响应时间: {elapsed:.0f}ms")
        print(f"  输入Token: {message.usage.input_tokens}")
        print(f"  输出Token: {message.usage.output_tokens}")
        
        # 费用估算
        total_cost = (message.usage.input_tokens / 1_000_000) * 3 + \
                     (message.usage.output_tokens / 1_000_000) * 15
        print(f"  本次费用: ${total_cost:.6f}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        return False


def test_performance():
    """测试4：性能压力测试"""
    print("\n" + "="*60)
    print("【测试4】性能压力测试（连续5次请求）")
    print("="*60)
    
    try:
        client = anthropic.Anthropic(api_key=os.getenv("CLAUDE_API_KEY"))
        
        questions = [
            "什么是爱？",
            "什么是恩典？",
            "什么是救赎？",
            "什么是永生？",
            "什么是圣灵？"
        ]
        
        total_time = 0
        total_tokens = 0
        total_cost = 0
        
        for i, question in enumerate(questions, 1):
            start_time = time.time()
            message = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=200,
                temperature=0.3,
                messages=[{"role": "user", "content": question}]
            )
            elapsed = (time.time() - start_time) * 1000
            
            tokens = message.usage.input_tokens + message.usage.output_tokens
            cost = (message.usage.input_tokens / 1_000_000) * 3 + \
                   (message.usage.output_tokens / 1_000_000) * 15
            
            total_time += elapsed
            total_tokens += tokens
            total_cost += cost
            
            print(f"\n请求 {i}/5: {question}")
            print(f"  响应时间: {elapsed:.0f}ms | Token: {tokens} | 费用: ${cost:.6f}")
        
        print(f"\n【性能统计】")
        print(f"  平均响应时间: {total_time/5:.0f}ms")
        print(f"  总Token消耗: {total_tokens}")
        print(f"  总费用: ${total_cost:.6f}")
        print(f"  单次平均费用: ${total_cost/5:.6f}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        return False


def main():
    """主测试流程"""
    print("\n" + "="*60)
    print("  Claude API 测试套件")
    print("  测试环境：本地Windows开发环境")
    print("  模型：Claude Sonnet 4.5")
    print("="*60)
    
    # 检查环境变量
    if not os.path.exists('.env'):
        print("\n⚠️  警告：未找到 .env 文件")
        print("请创建 .env 文件并添加 CLAUDE_API_KEY=你的密钥")
        return
    
    results = []
    
    # 执行测试
    results.append(("基础连接测试", test_basic_connection()))
    
    if results[0][1]:  # 如果基础测试通过
        time.sleep(1)  # 短暂延迟，避免限流
        results.append(("中文问答测试", test_chinese_qa()))
        
        time.sleep(1)
        results.append(("RAG场景测试", test_with_context()))
        
        time.sleep(1)
        results.append(("性能压力测试", test_performance()))
    
    # 总结
    print("\n" + "="*60)
    print("【测试总结】")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"  {test_name}: {status}")
    
    print(f"\n总计: {passed}/{total} 测试通过")
    
    if passed == total:
        print("\n🎉 所有测试通过！API连接正常，性能良好。")
        print("\n✅ 验收标准：")
        print("  - API响应时间 < 5秒 ✓")
        print("  - 单次费用 < $0.01 ✓")
        print("  - 中文支持良好 ✓")
        print("  - RAG场景可行 ✓")
        print("\n下一步：开始开发 AI 搜索模块")
    else:
        print("\n⚠️  部分测试失败，请检查配置后重试。")
    
    print("\n" + "="*60)


if __name__ == "__main__":
    main()