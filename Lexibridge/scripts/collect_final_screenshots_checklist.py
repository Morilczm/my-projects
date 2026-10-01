#!/usr/bin/env python3
"""Generate final screenshot checklist and count existing screenshot files."""

from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CHECKLIST = """# Final Screenshot Checklist

## Login / Role
- [ ] 登录页面
- [ ] 教师工作台
- [ ] 学生工作台
- [ ] 管理员工作台

## Teacher Workflow
- [ ] 课程管理
- [ ] 资料上传
- [ ] Job 状态
- [ ] AlignmentRun 统计
- [ ] Quality Control 列表
- [ ] 术语卡详情
- [ ] Evidence score breakdown
- [ ] 学生反馈处理

## Student Workflow
- [ ] 术语搜索
- [ ] 术语卡详情
- [ ] 收藏 / 掌握
- [ ] 提交反馈
- [ ] 个人资料上传
- [ ] 导出复习资料

## Admin Workflow
- [ ] 全局任务
- [ ] EvaluationRun
- [ ] AI Provider Governance
- [ ] KnowledgeBaseVersion
- [ ] Retrieval Experiment
- [ ] Pilot Report

## Technical Evidence
- [ ] OCR 状态
- [ ] FormulaBlock
- [ ] Knowledge Health
- [ ] Retrieval Regression
- [ ] Production Readiness NOT READY
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    screenshots = ROOT / "screenshots"
    count = 0
    if screenshots.exists():
        count = len([path for path in screenshots.rglob("*") if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}])
    content = CHECKLIST + f"\n## Existing Screenshot Inventory\n\n- screenshots directory: {'present' if screenshots.exists() else 'missing'}\n- screenshot files found: {count}\n- Missing screenshots are warnings only; final screenshots may be captured manually.\n"
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    print(f"Final screenshot checklist written: {output}")
    print(f"Existing screenshots: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
