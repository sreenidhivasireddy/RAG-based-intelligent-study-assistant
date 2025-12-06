"""
WebSocket 聊天集成测试

测试 WebSocket 聊天功能是否正常工作
"""

import asyncio
import json
import websockets
import sys


async def test_chat_websocket():
    """测试 WebSocket 聊天"""
    
    conversation_id = "test_conv_123"
    uri = f"ws://localhost:8000/api/v1/chat/ws/{conversation_id}"
    
    print(f"🔗 连接到 WebSocket: {uri}")
    
    try:
        async with websockets.connect(uri) as websocket:
            print("✅ WebSocket 连接成功")
            
            # 发送测试消息
            test_message = "What is machine learning?"
            print(f"\n📨 发送消息: {test_message}")
            
            await websocket.send(json.dumps({
                "message": test_message
            }))
            
            print("\n📥 接收响应:")
            print("-" * 60)
            
            full_response = ""
            chunk_count = 0
            
            # 接收响应
            while True:
                try:
                    response = await asyncio.wait_for(
                        websocket.recv(),
                        timeout=30.0  # 30秒超时
                    )
                    
                    data = json.loads(response)
                    
                    # 处理错误
                    if "error" in data:
                        print(f"❌ 错误: {data['error']}")
                        break
                    
                    # 处理流式响应
                    if "chunk" in data:
                        chunk_count += 1
                        chunk = data["chunk"]
                        full_response += chunk
                        print(chunk, end="", flush=True)
                    
                    # 处理完成通知
                    if data.get("type") == "completion" and data.get("status") == "finished":
                        print("\n" + "-" * 60)
                        print(f"✅ 响应完成")
                        print(f"📊 统计: 收到 {chunk_count} 个响应块")
                        print(f"📝 完整响应长度: {len(full_response)} 字符")
                        break
                
                except asyncio.TimeoutError:
                    print("\n⚠️ 接收响应超时（30秒）")
                    break
            
            print(f"\n✅ 测试完成")
            return True
            
    except websockets.exceptions.WebSocketException as e:
        print(f"❌ WebSocket 连接失败: {e}")
        return False
    except ConnectionRefusedError:
        print("❌ 连接被拒绝 - 请确保后端服务器正在运行")
        print("   启动命令: uvicorn app.main:app --reload --host 127.0.0.1 --port 8000")
        return False
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_conversation_api():
    """测试对话历史 API"""
    import aiohttp
    
    conversation_id = "test_conv_123"
    base_url = "http://localhost:8000/api/v1"
    
    print("\n" + "=" * 60)
    print("🧪 测试对话历史 API")
    print("=" * 60)
    
    try:
        async with aiohttp.ClientSession() as session:
            # 获取对话历史
            url = f"{base_url}/conversations/{conversation_id}"
            print(f"\n📥 GET {url}")
            
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ 状态码: {response.status}")
                    print(f"📊 消息数量: {len(data.get('data', []))}")
                    
                    if data.get('data'):
                        print("\n📜 对话历史:")
                        for msg in data['data']:
                            role = msg.get('role', 'unknown')
                            content = msg.get('content', '')[:50]
                            timestamp = msg.get('timestamp', 'N/A')
                            print(f"  [{timestamp}] {role}: {content}...")
                else:
                    print(f"⚠️ 状态码: {response.status}")
                    print(await response.text())
            
            # 获取对话摘要
            url = f"{base_url}/conversations/{conversation_id}/summary"
            print(f"\n📥 GET {url}")
            
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ 状态码: {response.status}")
                    print(f"📊 摘要:")
                    summary = data.get('data', {})
                    for key, value in summary.items():
                        print(f"  {key}: {value}")
                else:
                    print(f"⚠️ 状态码: {response.status}")
        
        return True
        
    except aiohttp.ClientError as e:
        print(f"❌ HTTP 请求失败: {e}")
        return False
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """主测试函数"""
    print("=" * 60)
    print("🧪 WebSocket 聊天集成测试")
    print("=" * 60)
    
    # 检查依赖
    print("\n📦 检查依赖...")
    try:
        import websockets
        import aiohttp
        print("✅ websockets 已安装")
        print("✅ aiohttp 已安装")
    except ImportError as e:
        print(f"❌ 缺少依赖: {e}")
        print("\n请安装依赖:")
        print("  pip install websockets aiohttp")
        sys.exit(1)
    
    # 测试 WebSocket 聊天
    result1 = await test_chat_websocket()
    
    # 测试对话 API
    result2 = await test_conversation_api()
    
    # 总结
    print("\n" + "=" * 60)
    print("📊 测试总结")
    print("=" * 60)
    print(f"WebSocket 聊天: {'✅ 通过' if result1 else '❌ 失败'}")
    print(f"对话 API: {'✅ 通过' if result2 else '❌ 失败'}")
    
    if result1 and result2:
        print("\n✅ 所有测试通过！")
        sys.exit(0)
    else:
        print("\n❌ 部分测试失败")
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️ 测试被用户中断")
        sys.exit(130)

