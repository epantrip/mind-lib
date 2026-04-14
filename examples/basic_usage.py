#!/usr/bin/env python3
"""
Mind Library Usage Example
"""
import sys
sys.path.insert(0, '..')

from client.mind_client import MindSyncClient

# Configuration
SERVER = "http://localhost:5000"
INSTANCE_ID = "demo_instance"
INSTANCE_NAME = "Demo Instance"

# Create client
client = MindSyncClient(SERVER, INSTANCE_ID, INSTANCE_NAME)

# Register
if client.register():
    print("�?Registration successful")
else:
    print("⚠️ Registration failed (may already exist)")

# Example 1: Upload a thought
print("\n📤 Uploading thought...")
client.upload_thought(
    title="Learned something new today",
    content="Through Mind Library, different AI instances can share thoughts and experiences. This is amazing!",
    thought_type="learning"
)

# Example 2: Full sync
print("\n🔄 Syncing...")
client.sync_all()

# Example 3: View stats
print("\n📊 Statistics")
import requests
stats = requests.get(f"{SERVER}/api/stats").json()
print(f"  Thoughts: {stats['thoughts']}")
print(f"  Skills: {stats['skills']}")
print(f"  Instances: {stats['instances']}")

print("\n🎉 Example complete!")
