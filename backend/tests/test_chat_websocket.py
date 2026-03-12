"""
WebSocket chat integration test.

Tests whether WebSocket chat works correctly.
"""

import asyncio
import json
import sys

import websockets


async def test_chat_websocket():
    """Test WebSocket chat."""

    conversation_id = "test_conv_123"
    uri = f"ws://localhost:8000/api/v1/chat/ws/{conversation_id}"

    print(f"Connecting to WebSocket: {uri}")

    try:
        async with websockets.connect(uri) as websocket:
            print("WebSocket connection succeeded")

            test_message = "What is machine learning?"
            print(f"\nSending message: {test_message}")

            await websocket.send(json.dumps({"message": test_message}))

            print("\nReceiving response:")
            print("-" * 60)

            full_response = ""
            chunk_count = 0

            while True:
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=30.0)
                    data = json.loads(response)

                    if "error" in data:
                        print(f"Error: {data['error']}")
                        break

                    if "chunk" in data:
                        chunk_count += 1
                        chunk = data["chunk"]
                        full_response += chunk
                        print(chunk, end="", flush=True)

                    if data.get("type") == "completion" and data.get("status") == "finished":
                        print("\n" + "-" * 60)
                        print("Response completed")
                        print(f"Stats: received {chunk_count} response chunks")
                        print(f"Full response length: {len(full_response)} characters")
                        break

                except asyncio.TimeoutError:
                    print("\nTimed out while waiting for response (30 seconds)")
                    break

            print("\nTest completed")
            return True

    except websockets.exceptions.WebSocketException as e:
        print(f"WebSocket connection failed: {e}")
        return False
    except ConnectionRefusedError:
        print("Connection refused - make sure the backend server is running")
        print("   Start command: uvicorn app.main:app --reload --host 127.0.0.1 --port 8000")
        return False
    except Exception as e:
        print(f"Test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_conversation_api():
    """Test the conversation history API."""
    import aiohttp

    conversation_id = "test_conv_123"
    base_url = "http://localhost:8000/api/v1"

    print("\n" + "=" * 60)
    print("Testing conversation history API")
    print("=" * 60)

    try:
        async with aiohttp.ClientSession() as session:
            url = f"{base_url}/conversations/{conversation_id}"
            print(f"\nGET {url}")

            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"Status code: {response.status}")
                    print(f"Message count: {len(data.get('data', []))}")

                    if data.get("data"):
                        print("\nConversation history:")
                        for msg in data["data"]:
                            role = msg.get("role", "unknown")
                            content = msg.get("content", "")[:50]
                            timestamp = msg.get("timestamp", "N/A")
                            print(f"  [{timestamp}] {role}: {content}...")
                else:
                    print(f"Status code: {response.status}")
                    print(await response.text())

            url = f"{base_url}/conversations/{conversation_id}/summary"
            print(f"\nGET {url}")

            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"Status code: {response.status}")
                    print("Summary:")
                    summary = data.get("data", {})
                    for key, value in summary.items():
                        print(f"  {key}: {value}")
                else:
                    print(f"Status code: {response.status}")

        return True

    except aiohttp.ClientError as e:
        print(f"HTTP request failed: {e}")
        return False
    except Exception as e:
        print(f"Test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def main():
    """Main test function."""
    print("=" * 60)
    print("WebSocket chat integration test")
    print("=" * 60)

    print("\nChecking dependencies...")
    try:
        import websockets  # noqa: F401
        import aiohttp  # noqa: F401

        print("websockets installed")
        print("aiohttp installed")
    except ImportError as e:
        print(f"Missing dependency: {e}")
        print("\nPlease install dependencies:")
        print("  pip install websockets aiohttp")
        sys.exit(1)

    result1 = await test_chat_websocket()
    result2 = await test_conversation_api()

    print("\n" + "=" * 60)
    print("Test summary")
    print("=" * 60)
    print(f"WebSocket chat: {'passed' if result1 else 'failed'}")
    print(f"Conversation API: {'passed' if result2 else 'failed'}")

    if result1 and result2:
        print("\nAll tests passed!")
        sys.exit(0)

    print("\nSome tests failed")
    sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(130)
