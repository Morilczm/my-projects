# Final Known Limitations

- The current version is local pilot-ready and not production-ready.
- 当前版本不是 production-ready。
- 当前默认适合本地演示和小范围试点。
- SQLite 不适合作为长期生产数据库。
- LocalStorageBackend 不适合作为长期生产文件存储。
- Local worker 不适合高并发任务。
- Mock payment 不是真实支付。
- Mock email 不是真实邮件。
- 没有真实 API key 时 AI 只能使用 none/mock/local。
- 没有真实 Formula OCR provider 时不能承诺高质量公式 OCR。
- LocalJsonVectorIndexBackend 只适合 demo。
- local_hash_embedding 不代表真实语义向量。
- 真实课程资料需要教师确认授权。
- 术语卡片仍需结合 evidence、risk_note 和教师审核状态使用。
