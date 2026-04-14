# 参与贡献

感谢你对 Mind Library 的关注！以下是贡献指南。

## 🚀 如何贡献

### 报告Bug

1. 检查 [Issues](https://github.com/epantrip/mind-lib/issues) 是否已有相同问题
2. 如果没有，创建新 Issue，包含：
   - 问题描述
   - 复现步骤
   - 预期行为
   - 实际行为
   - 环境信息（OS、Python版本等）

### 提交代码

1. Fork 本仓库
2. 创建功能分支：`git checkout -b feature/amazing-feature`
3. 提交更改：`git commit -m 'feat: add amazing feature'`
4. 推送分支：`git push origin feature/amazing-feature`
5. 提交 Pull Request

### 代码规范

- 遵循 PEP 8
- 添加适当的注释
- 确保所有测试通过
- 新功能请添加对应的测试

## 📋 提交信息格式

使用约定式提交（Conventional Commits）：

```
feat: 新功能
fix: 修复bug
docs: 文档更新
style: 代码格式（不影响逻辑）
refactor: 重构
test: 测试
chore: 构建/工具变更
```

## 🎯 开发环境设置

```bash
git clone https://github.com/epantrip/mind-lib.git
cd mind-lib

# 安装服务端依赖
cd server && pip3 install -r requirements.txt

# 安装客户端依赖
cd ../client && pip3 install -r requirements.txt

# 运行测试
cd ../tests && python3 -m pytest
```

## 💡 建议

- 保持更改最小化，聚焦于一个功能
- 编写清晰的提交信息
- 更新相关文档

感谢你的贡献！🎃
