# BYR Docs 复现记录

这是 BYR Docs 主站复现项目的文档和关键源码归档。主站使用 Cloudflare Workers + D1，资料和公开数据使用阿里云 OSS；本项目记录了用 OSS 替代原指南 Cloudflare R2 的具体改动。

## 内容

- `docs/`：复现步骤、R2 到 OSS 的改造说明、更新与恢复流程、配置清单。
- `oss-adaptation/`：Worker OSS 签名读写、分片上传、路由和 Wrangler 配置的关键文件。
- `source/`：主站和 Archive 的 Git 源码快照。
- `data/byrdocs-data-2026-10-03/`：已发布到 OSS 数据桶的 `metadata.json`、三个 YAML schema。
- `reports/`：本地资料与 Archive 元信息的对照报告。
- `tools/`：数据生成和对照脚本、ossutil 版本记录。

完整的 3372 个 PDF、ZIP、JPG、WEBP（约 27 GiB）保留在部署电脑的 `E:\byrdocs-reproduction\resources`，没有上传 GitHub；GitHub 仓库只保存复现所需的小型文本和代码文件。AccessKey、Cloudflare Token、JWT 密钥和 `.env` 也没有上传。

从 [docs/复现过程.md](docs/复现过程.md) 开始阅读。OSS 的核心改动见 [docs/R2替换为OSS.md](docs/R2替换为OSS.md)。
