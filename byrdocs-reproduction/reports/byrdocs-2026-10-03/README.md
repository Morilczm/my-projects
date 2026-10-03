# BYR Docs 资料对照与处理决定

## 本次对照的用途

第二步把 Archive 的每一条 YAML 与本地 PDF、ZIP、JPG、WEBP 按 MD5 文件名逐项对应，避免网站索引指向不存在的文件，也避免已存储的文件因为缺元信息而无法搜索。

第三步根据对照结果为每个 MD5 确定后续动作。此阶段只做决策和整理；没有修改 Archive、原始资料或 OSS。

## 固定来源

- Archive：`E:\byrdocs-archive`，提交 `25df77900b0c46084d7f81cf9e5275a7427042b7`。
- 资源目录：`E:\byrdocs`。
- 对照脚本：`C:\Users\Lenovo\Documents\ChatGPT\byrteam\scripts\compare_byrdocs_archive.py`。
- 结果 CSV 为 UTF-8（带 BOM），可直接用 Excel 打开。

## 结果与决定

| 状态 | 数量 | 处理决定 |
| --- | ---: | --- |
| `ready` | 1092 | 元信息与原文件对应；先列入待上线集合。完成 OSS 上传和线上读取核验后，才视为真正可用。 |
| `missing_source` | 110 | Archive 有记录，本地缺 PDF。保留原 YAML；寻找原件或备份。在文件补齐前，从本站生成的搜索数据中暂时排除这些记录，避免失效链接。 |
| `missing_metadata` | 32 | 本地有 PDF，但 Archive 无记录。逐份查看内容、分类、重名/重复和授权，再按 Archive 的元信息规则补写 YAML；审核前不加入搜索索引。 |
| `preview_only` | 1 | 只有 JPG 和 WEBP，没有 PDF/ZIP 或 YAML。先找原文件；找不到则暂不上传这组预览图，也不加入索引。 |
| `extension_mismatch` | 0 | 当前无此问题。 |

110 条缺原文件的分类：试题 66、书籍 37、资料 7，均指向 PDF。对原站文件 URL 抽样执行未登录 HEAD 请求，返回 `302 /login`；不能把原站 URL 当作自动补齐途径。

32 份未收录 PDF 的文件名 MD5 已逐份与实际文件内容核验，全部一致。32 份中有 31 份具备 JPG 和 WEBP；`5aaedeaa9eda35607f0c3c2b6e2ab5de.pdf` 没有预览图。PDF 内部标题仅作为人工识别线索，不能直接据此生成元信息。

唯一只剩预览图的 MD5：`71c1698db0a1bd3dcdbdac36a83c6d17`。

## 文件说明

- `all_resources.csv`：全部 1235 个 MD5 的统一对照表，是后续处理的主清单。
- `ready.csv`：1092 条本地资源和 YAML 匹配记录。
- `missing_source.csv`：需要寻找原件的 110 条元信息。
- `missing_metadata.csv`：需要人工审核并补 YAML 的 32 份 PDF，附文件大小、页数和可获取的 PDF 标题线索。
- `preview_only.csv`：仅有预览图的 1 组文件。
- `extension_mismatch.csv`：当前只有表头，供以后重跑时发现后缀不一致的问题。
- `summary.json`：机器可读的汇总统计。

## 后续操作顺序

1. 优先寻找 `missing_source.csv` 中的 110 份 PDF；每找到一份，核对内容 MD5 是否等于文件名。找不到的维持“暂缓展示”。
2. 查看 `missing_metadata.csv` 中的 32 份 PDF。按 `E:\byrdocs-archive\docs\文件规则.md` 和 `元信息规则.md` 判断是否收录及类别；不合格或重复的文件记录为不收录。
3. 寻找 `preview_only.csv` 对应的原文件。补到原件之后才考虑预览图。
4. 重新运行对照脚本，确认状态变化。然后基于可用记录生成本站专属 `metadata.json`，将文件 URL 指向本站域名，上传资料和数据到 OSS，并核验线上访问。

注意：`ready` 只表示本地资料与元信息对应，尚未确认其已上传 OSS，也尚未对 1092 份原文件逐个计算内容 MD5。
