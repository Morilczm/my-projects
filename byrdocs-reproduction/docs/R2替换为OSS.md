# Cloudflare R2 替换为阿里云 OSS

原指南假定 Worker 直接绑定 R2，并用 Minio/R2 API 上传两个桶。本次保留 Cloudflare Workers、D1、Durable Objects 和前端，把对象存储换为阿里云 OSS 华北 2（北京）。这不是仅换桶名：Worker 的读取、删除及分片上传请求都要由服务端签名后通过 OSS S3 兼容接口发送。

## 对照表

| 原指南/原项目 | 本次实现 |
| --- | --- |
| `[[r2_buckets]]` 与 `env.R2` | `wrangler.toml` 的 `OSS_ENDPOINT`、`OSS_REGION`、两个桶名；不再绑定 R2。 |
| R2 对象读取 | `worker/oss.ts` 的 `getObject()`，使用 AWS Signature V4 请求 OSS。 |
| R2 对象查询/删除 | `worker/oss.ts` 的 `headFile()`、`deleteFile()`。 |
| R2 分片上传 | `startMultipart()`、`uploadPart()`、`completeMultipart()`、`abortMultipart()` 调 OSS S3 接口。 |
| R2 Access Key | 阿里云 RAM AccessKey；Worker Secrets 为 `OSS_ACCESS_KEY_ID`、`OSS_ACCESS_KEY_SECRET`。 |
| `mcli cp ... r2/byrdocs-file` | `ossutil cp ... oss://byrdocs-file/`，仅上传四种资料扩展名。 |
| `r2/byrdocs-data` | `oss://byrdocs-data/`，公开文件经 Worker `/data/*` 路由读取。 |

## 对应源码

- `oss-adaptation/wrangler.toml`：公开 OSS Endpoint、Region 和桶名。数据库 ID 也在此文件中；换账号需要重填。
- `oss-adaptation/worker/oss.ts`：构造 OSS 对象 URL，计算 SHA-256/HMAC、AWS Signature V4 请求，提供 HEAD/GET/DELETE 和 multipart API。OSS 桶保持私有，浏览器不持有 AccessKey。
- `oss-adaptation/worker/index.ts`：`/data/*` 与 `/schema/*` 映射到数据桶，`/files/*` 映射到文件桶；还保留 `/sitemap.xml` 路由。
- `oss-adaptation/worker/utils.ts` 和 `worker/ssr.ts`：文件访问及详情页读取改用 `getObject()`。
- `oss-adaptation/worker/api/r2.ts`：文件名沿用旧的 `r2.ts`，但内部已调用 OSS 封装；仅凭文件名不能判断仍使用 R2。
- `oss-adaptation/worker/env.d.ts`、`.dev.vars.example`：OSS 凭据的类型和本地开发占位值。实际凭据必须使用 Worker Secrets/本地忽略文件。
- `oss-adaptation/src/search.tsx`：搜索从 `/data/metadata.json` 读取聚合数据，不直接解析三份 YAML schema。

`source/byrdocs-main-c90f42d.zip` 是完整主站源码快照，以上路径为单独提取的阅读副本。需要修改代码时以完整仓库为准。

## OSS 配置要点

1. 两个桶必须位于与 `OSS_ENDPOINT`、`OSS_REGION` 一致的区域。本次 Endpoint 为 `https://oss-cn-beijing.aliyuncs.com`，签名 Region 为 `cn-beijing`，ossutil Region 为 `oss-cn-beijing`。
2. RAM 用户需要两个桶相应的对象访问权限；主站的运行时密钥在 Cloudflare Worker Secrets 中，不能写到 `wrangler.toml` 或 GitHub 仓库。
3. 资料对象的 key 是 `<MD5>.pdf`、`<MD5>.zip`、`<MD5>.jpg`、`<MD5>.webp`，直接位于 `byrdocs-file` 桶根目录。不能多一层 `byrdocs/` 前缀。
4. 数据对象 key 是 `metadata.json`、`book.yaml`、`test.yaml`、`doc.yaml`，直接位于 `byrdocs-data` 桶根目录；上传时可设 JSON/YAML Content-Type。
5. 桶内对象不需要直接公网可读。Worker 持有 RAM 凭据并代理读取，主站 URL 是统一入口。

## 尚未适配的部分

Archive 快照中的 `.github/workflows/upload-metadata.yml` 与 `upload-schema.yml` 仍包含 `R2_*` Secrets、R2 上传动作和上游 `byrdocs-check/upload-metadata` 工具。这个工具/工作流不能仅把 Secret 名称改为 `OSS_*` 就保证兼容。当前四份数据文件是本地生成后用 ossutil 手动发布的。未来要实现 Archive 推送后自动更新，需要修改这些 Actions 与生成/上传逻辑，并验证 OSS 路径、URL 和权限。

原指南的 R2 自定义域名、R2 备份桶步骤也没有在本次复现中建立对应设施；不要把它们标记为已完成。
