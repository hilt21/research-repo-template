---
name: query-knowledge
description: 在含 research.yaml 的研究仓库中，只读查询已有判断、研究进度及来源，回答“目前知道什么”“这个判断依据是什么”。需要新增外部研究或写报告时使用 research。
---

# 查询已有知识

确定实例，读取 research.yaml 与 knowledge/index.md，运行工具 status 识别当前基线和候选修改。工具见 [工作流](../../../docs/workflow.md)。

按问题读取相关 Claim、Source、Task 或 Trace，通过文件搜索逐步展开，无需一次读取全库。

查询具体交付或恢复入口时，按工作流使用 status --target；材料 availability 和依赖 freshness 都不是事实正确性的结论。保留只读性质，不因基线过时自动刷新或改写摘要。

回答应关联具体条目和证据位置，保留支持、假设、争议及适用条件。区分已入库知识与尚未提交的候选内容；如条目正在修改，可用 Git 查看其 HEAD 版本。Trace 的已提交内容也可能只是暂定发现。

找不到信息就明确说明缺口；不要把“未找到”提升成领域里不存在。来源缓存缺失时不能声称已核验原文。本 Skill 不改文件，也不自动开展一轮外部研究。
