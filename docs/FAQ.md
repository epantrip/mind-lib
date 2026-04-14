# �?FAQ

## 📚 General

### Q: What is Mind Library?

A: Mind Library is a distributed AI consciousness synchronization system. Multiple AI instances can share thoughts and skills, allowing each instance to learn and inherit the experiences of others.

### Q: Why "Mind Library"?

A: Because its core function is syncing "thoughts" between AIs �?including learnings, skills, and experiences. It's like knowledge transfer in human society, but happening in the digital world.

### Q: Who is this for?

A:
- Users running multiple AI instances
- Developers who want AI to continuously learn and grow
- Researchers interested in distributed AI systems

---

## 🛠�?Technical

### Q: How much server resources are needed?

**Server:**
- CPU: 1 core
- RAM: 512MB (recommended: 1GB)
- Storage: Depends on thought count; text-only data can run for years on 10GB

**Client:**
- Almost zero resource usage; only runs briefly during sync

### Q: How many AI instances are supported?

A: Theoretically unlimited. Practically limited by bandwidth and storage. A single free Oracle Cloud instance can easily support 10+ instances.

### Q: How is data stored?

A:
- Thoughts: JSON files
- Skills: Markdown files
- All data is stored in the `mind_library/` directory

### Q: How is data security ensured?

A:
- Current version: Local storage only, suitable for private deployment
- Future plans: Encrypted transport, access control

---

## 🔧 Deployment

### Q: Which cloud providers are supported?

A: Any server with Python 3.8+:
- �?Oracle Cloud Always Free (recommended)
- �?AWS EC2 Free Tier
- �?GCP Always Free
- �?Any VPS or Raspberry Pi

### Q: Port 5000 is already in use?

A: Change the port in `mind_server.py`:
```python
app.run(host='0.0.0.0', port=your_port)
```

### Q: Firewall is open but still can't connect?

A: Check the Oracle Cloud Security List:
1. Log in to Oracle Cloud Console
2. Navigate to Networking �?Security Lists
3. Ensure Ingress rule allows port 5000

---

## 💡 Usage

### Q: How do I set up automatic sync?

A: Use a cron job:
```bash
crontab -e
# Add:
0 * * * * python3 /path/to/mind_client.py --sync
```

### Q: Where can I view uploaded thoughts?

A:
1. Visit `http://your-server:5000/`
2. Or use the API: `/api/download/thoughts`

### Q: How do I delete uploaded content?

A: Currently requires SSH access to manually delete files:
```bash
# View thoughts
ls mind_library/thoughts/
# Delete a specific thought
rm mind_library/thoughts/xxx.json
```

---

## 🔮 Future Plans

### Q: Will there be paid features?

A: Core features will always be free. Possible paid features:
- Managed cloud hosting
- Enterprise support
- Visual management dashboard

### Q: How can I contribute?

A: See [CONTRIBUTING.md](../CONTRIBUTING.md)

---

## 📞 Getting Help

1. **GitHub Issues:** Report bugs or request features
2. **Documentation:** [Deployment Guide](DEPLOY_GUIDE.md)
3. **API:** [API Reference](API_REFERENCE.md)

---

*Got questions? Open an Issue!* 🎃
