import redis

r = redis.Redis(host="localhost", port=6379, db=0)

r.set("test_key", "hello redis")
val = r.get("test_key").decode()

print(f"✅ Redis connected successfully, value = {val}")
