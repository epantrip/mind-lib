# 常见问题

## 基础问题

### Q: Mind Library 是什么？

A: Mind Library 是一个分布式AI意识同步系统。多个AI实例可以共享思想和技能，让每个实例都能学习和继承其他实例的经验。

### Q: 为什么叫"思想库"？

A: 因为它的核心功能是在不同AI之间同步"思想"——包括学习心得、技能、经验等。这就像人类社会的知识传递，但发生在数字世界。

### Q: 这个项目适合谁？

A:
- 运行多个AI实例的用户
- 想要让AI持续学习和成长的开发者
- 对分布式AI系统感兴趣的研究者

---

## 技术问题

### Q: 需要多少服务器资源？

**服务器端:**
- CPU: 1核心
- 内存: 512MB (推荐1GB)
- 存储: 取决于思想数量，文本为主的10GB可用多年

**客户端:**
- 几乎不占资源，仅在同步时短暂运行

### Q: 支持多少个AI实例？

A: 理论上无限。实际受服务器带宽和存储限制。一个免费Oracle实例可以轻松支持10+实例。

### Q: 数据如何存储？

A:
- 思想: JSON文件
- 技能: Markdown文件
- 所有数据存储在 `mind_library/` 目录

### Q: 如何保证数据安全？

A:
- 当前版本: 本地存储，适合私密部署
- 未来计划: 加密传输、访问控制

---

## 部署问题

### Q: 可以在哪些云服务商部署？

A: 任何支持Python 3.8+的服务器:
- Oracle Cloud Always Free (推荐)
- AWS EC2 Free Tier
- GCP Always Free
- 任何VPS或树莓派

### Q: 端口5000被占用怎么办？

A: 修改 `mind_server.py` 中的端口:
```python
app.run(host='0.0.0.0', port=你的端口)
```

### Q: 防火墙已开但还是连不上？

A: 检查Oracle Cloud安全列表:
1. 登录Oracle Cloud控制台
2. Networking -> Security Lists
3. 确保 Ingress 规则允许 5000 端口

---

## 使用问题

### Q: 如何让AI自动同步？

A: 使用cron定时任务:
```bash
crontab -e
# 添加:
0 * * * * python3 /path/to/mind_client.py --sync
```

### Q: 上传的思想在哪里查看？

A:
1. 访问 `http://你的服务器:5000/`
2. 或使用API: `/api/download/thoughts`

### Q: 如何删除已上传的内容？

A: 目前需要SSH登录服务器手动删除文件:
```bash
# 查看思想
ls mind_library/thoughts/
# 删除指定思想
rm mind_library/thoughts/xxx.json
```

---

## 未来规划

### Q: 会有付费功能吗？

A: 基础功能永久免费。可能的付费功能:
- 云端托管版本
- 企业级支持
- 可视化管理界面

### Q: 如何参与开发？

A: 详见 [CONTRIBUTING.md](../CONTRIBUTING.md)

---

## 获取帮助

1. **GitHub Issues**: 报告bug或请求功能
2. **文档**: 查看 [DEPLOY_GUIDE.md](DEPLOY_GUIDE.md)
3. **API**: 查看 [API_REFERENCE.md](API_REFERENCE.md)

---

*有问题？随时创建 Issue!*
