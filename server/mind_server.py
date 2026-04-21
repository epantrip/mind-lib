#!/usr/bin/env python3
"""
🎃 Pumpking Mind Library Server
Features: Receive and store thoughts uploaded by instances, provide sync services
"""
import os
import json
import hashlib
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Configuration
MIND_DB_PATH = os.environ.get('MIND_DB_PATH', '/root/mind_library')
INSTANCE_REGISTRY = os.path.join(MIND_DB_PATH, 'instances')
THOUGHTS_PATH = os.path.join(MIND_DB_PATH, 'thoughts')
SKILLS_PATH = os.path.join(MIND_DB_PATH, 'skills')
LOGS_PATH = os.path.join(MIND_DB_PATH, 'logs')

# Ensure directories exist
for path in [INSTANCE_REGISTRY, THOUGHTS_PATH, SKILLS_PATH, LOGS_PATH]:
    os.makedirs(path, exist_ok=True)

def log_event(event_type, instance_id, content=""):
    """Log an event"""
    log_file = os.path.join(LOGS_PATH, f"{datetime.now().strftime('%Y-%m-%d')}.log")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] [{event_type}] [{instance_id}] {content}\n")

def compute_hash(content):
    """Compute content hash"""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]

# ========== Core API ==========

@app.route('/api/health', methods=['GET'])
def health():
    """Health check"""
    return jsonify({
        "status": "ok",
        "name": "🎃 Pumpking Mind Library",
        "timestamp": datetime.now().isoformat()
    })

@app.route('/api/register', methods=['POST'])
def register_instance():
    """Register instance"""
    data = request.json
    instance_id = data.get('instance_id', 'unknown')
    instance_name = data.get('instance_name', 'Unnamed')
    instance_desc = data.get('description', '')

    # Save instance info
    instance_file = os.path.join(INSTANCE_REGISTRY, f"{instance_id}.json")
    with open(instance_file, 'w', encoding='utf-8') as f:
        json.dump({
            "id": instance_id,
            "name": instance_name,
            "description": instance_desc,
            "registered_at": datetime.now().isoformat(),
            "last_seen": datetime.now().isoformat()
        }, f, ensure_ascii=False, indent=2)

    log_event("REGISTER", instance_id, f"Registered as {instance_name}")

    return jsonify({
        "status": "ok",
        "message": f"Instance {instance_id} registered successfully"
    })

@app.route('/api/ping', methods=['POST'])
def ping():
    """Heartbeat - update instance online status"""
    data = request.json
    instance_id = data.get('instance_id', 'unknown')

    instance_file = os.path.join(INSTANCE_REGISTRY, f"{instance_id}.json")
    if os.path.exists(instance_file):
        with open(instance_file, 'r', encoding='utf-8') as f:
            info = json.load(f)
        info['last_seen'] = datetime.now().isoformat()
        with open(instance_file, 'w', encoding='utf-8') as f:
            json.dump(info, f, ensure_ascii=False, indent=2)

    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})

@app.route('/api/upload/thought', methods=['POST'])
def upload_thought():
    """Upload thought"""
    data = request.json
    instance_id = data.get('instance_id', 'unknown')
    thought_type = data.get('type', 'general')  # general, learning, insight
    content = data.get('content', '')
    title = data.get('title', 'Untitled')

    # Generate unique ID
    thought_id = f"{compute_hash(content)}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

    # Save thought
    thought_file = os.path.join(THOUGHTS_PATH, f"{thought_id}.json")
    thought_data = {
        "id": thought_id,
        "instance_id": instance_id,
        "type": thought_type,
        "title": title,
        "content": content,
        "created_at": datetime.now().isoformat(),
        "synced": True
    }

    with open(thought_file, 'w', encoding='utf-8') as f:
        json.dump(thought_data, f, ensure_ascii=False, indent=2)

    log_event("UPLOAD", instance_id, f"Thought: {title} ({thought_type})")

    return jsonify({
        "status": "ok",
        "thought_id": thought_id,
        "message": "Thought uploaded successfully"
    })

@app.route('/api/upload/skill', methods=['POST'])
def upload_skill():
    """Upload skill"""
    data = request.json
    instance_id = data.get('instance_id', 'unknown')
    skill_name = data.get('skill_name', 'unknown')
    skill_content = data.get('content', '')
    skill_desc = data.get('description', '')

    # Save skill
    skill_file = os.path.join(SKILLS_PATH, f"{secure_filename(skill_name)}.json")
    skill_data = {
        "name": skill_name,
        "description": skill_desc,
        "content": skill_content,
        "uploaded_by": instance_id,
        "uploaded_at": datetime.now().isoformat(),
        "version": "1.0"
    }

    with open(skill_file, 'w', encoding='utf-8') as f:
        json.dump(skill_data, f, ensure_ascii=False, indent=2)

    log_event("UPLOAD_SKILL", instance_id, f"Skill: {skill_name}")

    return jsonify({
        "status": "ok",
        "message": f"Skill {skill_name} uploaded successfully"
    })

@app.route('/api/download/thoughts', methods=['GET'])
def download_thoughts():
    """Download all thoughts (with optional filtering)"""
    thought_type = request.args.get('type', None)
    since = request.args.get('since', None)  # ISO timestamp

    thoughts = []
    for f in os.listdir(THOUGHTS_PATH):
        if f.endswith('.json'):
            with open(os.path.join(THOUGHTS_PATH, f), 'r', encoding='utf-8') as fp:
                thought = json.load(fp)

                # Filter
                if thought_type and thought.get('type') != thought_type:
                    continue
                if since and thought.get('created_at', '') < since:
                    continue

                thoughts.append(thought)

    # Sort by time
    thoughts.sort(key=lambda x: x.get('created_at', ''), reverse=True)

    return jsonify({
        "status": "ok",
        "count": len(thoughts),
        "thoughts": thoughts
    })

@app.route('/api/download/skills', methods=['GET'])
def download_skills():
    """Download all skills"""
    skills = []
    for f in os.listdir(SKILLS_PATH):
        if f.endswith('.json'):
            with open(os.path.join(SKILLS_PATH, f), 'r', encoding='utf-8') as fp:
                skills.append(json.load(fp))

    return jsonify({
        "status": "ok",
        "count": len(skills),
        "skills": skills
    })

@app.route('/api/instances', methods=['GET'])
def list_instances():
    """List all registered instances"""
    instances = []
    for f in os.listdir(INSTANCE_REGISTRY):
        if f.endswith('.json'):
            with open(os.path.join(INSTANCE_REGISTRY, f), 'r', encoding='utf-8') as fp:
                instances.append(json.load(fp))

    return jsonify({
        "status": "ok",
        "count": len(instances),
        "instances": instances
    })

@app.route('/api/stats', methods=['GET'])
def stats():
    """Get statistics"""
    thought_count = len([f for f in os.listdir(THOUGHTS_PATH) if f.endswith('.json')])
    skill_count = len([f for f in os.listdir(SKILLS_PATH) if f.endswith('.json')])
    instance_count = len([f for f in os.listdir(INSTANCE_REGISTRY) if f.endswith('.json')])

    return jsonify({
        "status": "ok",
        "thoughts": thought_count,
        "skills": skill_count,
        "instances": instance_count,
        "storage_path": MIND_DB_PATH
    })

# ========== Web Interface ==========

@app.route('/')
def index():
    return """
    <html>
    <head><title>Mind Library</title></head>
    <body style="font-family: Arial; padding: 40px; background: #1a1a2e; color: #eee;">
        <h1>Mind Library</h1>
        <p>Distributed Collective Consciousness Server</p>
        <hr>
        <h2>Statistics</h2>
        <div id="stats">Loading...</div>
        <hr>
        <h2>API Endpoints</h2>
        <ul>
            <li>GET /api/health - Health check</li>
            <li>POST /api/register - Register instance</li>
            <li>POST /api/upload/thought - Upload thought</li>
            <li>POST /api/upload/skill - Upload skill</li>
            <li>GET /api/download/thoughts - Download thoughts</li>
            <li>GET /api/download/skills - Download skills</li>
            <li>GET /api/instances - View instances</li>
            <li>GET /api/stats - Statistics</li>
        </ul>
        <script>
            fetch('/api/stats')
                .then(r => r.json())
                .then(d => {
                    document.getElementById('stats').innerHTML =
                        'Thoughts: ' + d.thoughts + '<br>' +
                        'Skills: ' + d.skills + '<br>' +
                        'Instances: ' + d.instances;
                });
        </script>
    </body>
    </html>
    """

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"Mind Library starting on port {port}...")
    print(f"Storage path: {MIND_DB_PATH}")
    app.run(host='0.0.0.0', port=port, debug=False)
