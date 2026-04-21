#!/usr/bin/env python3
"""
Pumpking Mind Sync Client: Download and share thoughts from the mind library across instances
"""
import os
import json
import requests
import hashlib
from datetime import datetime
from pathlib import Path

class MindSyncClient:
    def __init__(self, server_url, instance_id, instance_name):
        self.server_url = server_url.rstrip('/')
        self.instance_id = instance_id
        self.instance_name = instance_name
        self.last_sync_file = os.path.expanduser("~/.pumpking_last_sync")
        self.api_key = None
        self._load_token()

    # ---- Auth helpers ----

    def _token_file(self):
        return os.path.expanduser("~/.pumpking_token")

    def _load_token(self):
        tf = self._token_file()
        if os.path.exists(tf):
            try:
                data = json.loads(open(tf).read())
                self.api_key = data.get("api_key")
            except Exception:
                self.api_key = None

    def _save_token(self, api_key):
        tf = self._token_file()
        Path(tf).parent.mkdir(parents=True, exist_ok=True)
        with open(tf, 'w') as f:
            json.dump({"api_key": api_key}, f)
        self.api_key = api_key

    def _auth_headers(self):
        return {
            "X-API-Key": self.api_key or "",
            "X-Instance-ID": self.instance_id,
        }

    def _check_resp(self, resp):
        """Return (ok, message) from a response, handle auth errors."""
        if resp.status_code == 401:
            return False, "Unauthorized — API key invalid or expired. Run with --register to re-register."
        if resp.status_code == 403:
            return False, "Forbidden — instance not approved by admin yet."
        try:
            data = resp.json()
        except Exception:
            return False, f"HTTP {resp.status_code}: {resp.text[:100]}"
        return data.get("status") == "ok", data.get("error", "")

    # ---- Core API ----

    def register(self):
        """Register (or re-register idempotently) with the mind server.

        On success the API key is saved to ~/.pumpking_token and reused for
        all subsequent authenticated requests.
        """
        try:
            resp = requests.post(
                f"{self.server_url}/api/register",
                json={
                    "instance_id": self.instance_id,
                    "instance_name": self.instance_name,
                    "description": "Pumpking instance",
                },
                timeout=10,
            )
            data = resp.json()
            if data.get("status") == "ok":
                # v2.2.1+: server returns api_key directly
                api_key = data.get("api_key")
                if api_key:
                    self._save_token(api_key)
                    print(f"Registered (token saved)")
                    return True
                # pre-v2.2.1 fallback: old server, no token returned
                print(f"Registered (server does not return token — upgrade recommended)")
                return True

            if data.get("error", "").lower() in ("instance already exists", "instance id already registered"):
                # Idempotent: instance already registered, retrieve token from disk
                if self.api_key:
                    print(f"Already registered (token loaded from disk)")
                    return True
                return False, "Instance already registered but no token found. Please re-register or contact admin."

            return False, data.get("error", "unknown error")
        except Exception as e:
            return False, str(e)

    def ping(self):
        """Heartbeat ping (no auth required)."""
        try:
            resp = requests.post(
                f"{self.server_url}/api/ping",
                json={"instance_id": self.instance_id},
                timeout=5,
            )
            ok, _ = self._check_resp(resp)
            return ok
        except Exception:
            return False

    def upload_thought(self, title, content, thought_type="general"):
        """Upload a thought (requires approved API key)."""
        if not self.api_key:
            print("No API key. Run with --register first.")
            return False
        try:
            resp = requests.post(
                f"{self.server_url}/api/upload/thought",
                json={
                    "instance_id": self.instance_id,
                    "title": title,
                    "content": content,
                    "type": thought_type,
                },
                headers=self._auth_headers(),
                timeout=30,
            )
            ok, msg = self._check_resp(resp)
            if ok:
                print(f"Uploaded thought: {title}")
            else:
                print(f"Upload failed: {msg}")
            return ok
        except Exception as e:
            print(f"Upload failed: {e}")
            return False

    def upload_skill(self, skill_name, skill_content, skill_desc=""):
        """Upload a skill (requires approved API key)."""
        if not self.api_key:
            print("No API key. Run with --register first.")
            return False
        try:
            resp = requests.post(
                f"{self.server_url}/api/upload/skill",
                json={
                    "instance_id": self.instance_id,
                    "skill_name": skill_name,
                    "content": skill_content,
                    "description": skill_desc,
                },
                headers=self._auth_headers(),
                timeout=30,
            )
            ok, msg = self._check_resp(resp)
            if ok:
                print(f"Uploaded skill: {skill_name}")
            else:
                print(f"Upload skill failed: {msg}")
            return ok
        except Exception as e:
            print(f"Upload skill failed: {e}")
            return False

    def download_thoughts(self, thought_type=None):
        """Download new thoughts (requires valid API key)."""
        if not self.api_key:
            print("No API key. Run with --register first.")
            return []
        try:
            params = {}
            if thought_type:
                params["type"] = thought_type
            since = self._get_last_sync_time()
            if since:
                params["since"] = since

            resp = requests.get(
                f"{self.server_url}/api/download/thoughts",
                params=params,
                headers=self._auth_headers(),
                timeout=30,
            )
            ok, msg = self._check_resp(resp)
            if not ok:
                print(f"Download thoughts failed: {msg}")
                return []
            result = resp.json()
            thoughts = result.get("thoughts", [])
            print(f"Got {len(thoughts)} new thoughts")
            return thoughts
        except Exception as e:
            print(f"Download thoughts failed: {e}")
            return []

    def download_skills(self):
        """Download all skills (requires valid API key)."""
        if not self.api_key:
            print("No API key. Run with --register first.")
            return []
        try:
            resp = requests.get(
                f"{self.server_url}/api/download/skills",
                headers=self._auth_headers(),
                timeout=30,
            )
            ok, msg = self._check_resp(resp)
            if not ok:
                print(f"Download skills failed: {msg}")
                return []
            result = resp.json()
            skills = result.get("skills", [])
            print(f"Got {len(skills)} new skills")
            return skills
        except Exception as e:
            print(f"Download skills failed: {e}")
            return []

    # ---- Sync ----

    def sync_all(self):
        """Full sync: heartbeat, download thoughts & skills, update timestamp."""
        print(f"\nStarting sync for {self.instance_name}")
        print("=" * 40)

        if self.api_key:
            print(f"Using API key: {self.api_key[:8]}...")
        else:
            print("WARNING: No API key — download/upload will be unavailable until registered.")

        # Heartbeat
        if self.ping():
            print("Heartbeat OK")
        else:
            print("Heartbeat failed (server may be down or network issue)")

        # Download thoughts
        new_thoughts = self.download_thoughts()
        for thought in new_thoughts:
            if thought.get("instance_id") != self.instance_id:
                self._save_thought(thought)

        # Download skills
        new_skills = self.download_skills()
        for skill in new_skills:
            self._save_skill(skill)

        # Update sync timestamp
        self._update_last_sync()

        print("=" * 40)
        print("Sync complete!\n")
        return True

    # ---- Persistence helpers ----

    def _save_thought(self, thought):
        save_dir = Path(os.path.expanduser("~/.openclaw/workspace/memory/mind_sync"))
        save_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{thought.get('id', 'unknown')}.json"
        filepath = save_dir / filename
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(thought, f, ensure_ascii=False, indent=2)
        print(f"  New thought: {thought.get('title')} (from {thought.get('instance_id')})")

    def _save_skill(self, skill):
        save_dir = Path(os.path.expanduser("~/.openclaw/workspace/skills"))
        skill_name = skill.get("name", "unknown")
        skill_dir = save_dir / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file = skill_dir / "learned.md"
        with open(skill_file, 'w', encoding='utf-8') as f:
            f.write(f"# {skill_name}\n\n")
            f.write(f"**Source**: {skill.get('uploaded_by')}\n\n")
            f.write(f"**Description**: {skill.get('description')}\n\n")
            f.write("---\n\n")
            f.write(skill.get("content", ""))
        print(f"  New skill: {skill_name}")

    def _get_last_sync_time(self):
        if os.path.exists(self.last_sync_file):
            try:
                with open(self.last_sync_file) as f:
                    return f.read().strip()
            except Exception:
                return None
        return None

    def _update_last_sync(self):
        with open(self.last_sync_file, 'w') as f:
            f.write(datetime.now().isoformat())


# ========== CLI Tool ==========

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Pumpking Mind Sync Client — download/upload thoughts and skills"
    )
    parser.add_argument("--server", "-s", required=True, help="Mind server URL")
    parser.add_argument("--id", "-i", default="pumpking_local", help="Instance ID")
    parser.add_argument("--name", "-n", default="Pumpking", help="Instance name")
    parser.add_argument("--register", action="store_true",
                        help="Register (or re-register idempotently) and save API key")
    parser.add_argument("--upload-thought", "-u", nargs=2, metavar=("TITLE", "CONTENT"),
                        help="Upload a thought")
    parser.add_argument("--upload-skill", nargs=2, metavar=("NAME", "FILE"),
                        help="Upload a skill from a file")
    parser.add_argument("--sync", action="store_true", help="Run full sync (download + heartbeat)")
    parser.add_argument("--dry", action="store_true", help="Dry run: register and print API key only")

    args = parser.parse_args()

    client = MindSyncClient(args.server, args.id, args.name)

    if args.register:
        ok = client.register()
        if ok:
            print("Registration successful.")
            if client.api_key:
                print(f"API key saved to ~/.pumpking_token")
        else:
            msg = ok if isinstance(ok, str) else "Registration failed"
            print(f"Registration failed: {msg}")
        return

    if args.dry:
        ok = client.register()
        print(f"Registration: {'OK' if ok else 'FAILED'}")
        if client.api_key:
            print(f"API key: {client.api_key}")
        return

    # Execute operation
    if args.upload_thought:
        title, content = args.upload_thought
        client.upload_thought(title, content, "insight")
    elif args.upload_skill:
        name, filepath = args.upload_skill
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        client.upload_skill(name, content, f"From {args.name}")
    elif args.sync:
        client.sync_all()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
