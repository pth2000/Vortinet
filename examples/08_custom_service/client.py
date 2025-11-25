import urllib.request
import time
import sys

print("Client started. Waiting for server...")
time.sleep(3) # 等待服务器启动

target = "http://10.0.0.1:8000"
print(f"Sending request to {target}...")
try:
    resp = urllib.request.urlopen(target)
    content = resp.read().decode()
    print(f"SUCCESS! Server response: {content}")
except Exception as e:
    print(f"FAILURE! Error: {e}")
