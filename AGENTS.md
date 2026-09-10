# 在这个仓库中工作

这是单课题研究仓库模板。使用者表达研究意图；你负责知识组织，脚本负责确定性操作，用户负责接受具体知识变化。

深模块与减轻用户负担是第一原则：使用集中接口隐藏文件定位、检查顺序和状态维护。共享规则以 docs/workflow.md 为维护来源，四个 Skill 引用它；不让用户手工协调重复状态。

## 入口

- 首先确定研究实例：默认根目录；用户指定其他实例时显式传入其根目录。`tests/fixtures/work` 仅用于合成验收，不属于根课题知识，默认只读。
- 读取实例 `research.yaml`。未初始化时根据用户目的收敛研究问题、范围和完成标准，再调用初始化工具。
- 本仓库的 `.agents/skills` 是该协议的 Skill 来源。存在同名全局 Skill 时，读取这里的具体文件。
- 研究、继续或生成报告 → `.agents/skills/research/SKILL.md`。
- 整理这一轮、接受知识 → `.agents/skills/commit-knowledge/SKILL.md`。
- 只查询已有判断 → `.agents/skills/query-knowledge/SKILL.md`。
- 整理关联、过时内容或复核报告 → `.agents/skills/maintain-knowledge/SKILL.md`。

## 执行边界

- 确定性流程使用 `scripts/repo.py`，命令见 `docs/workflow.md`。初始化、ID、哈希、索引、检查和受控提交不能靠口头推测完成。
- 用 `new` 创建草稿与 ID，再编辑语义内容。按 `schemas/objects.yaml` 填写；不要自行更改 Schema 来让无效研究数据通过。
- 研究关键节点保存 Trace；短研究无需 Task，需要持续跟踪时主动建 Task。
- 持续交付可用 Deliverable brief；恢复指定工作使用 status --target。交接、口述反馈与完成判定按工作流执行，不能靠最近 Trace 或全量历史推测当前目标。
- 解释依据、判断冲突、写作和修订由你完成，校验成功不代表证据成立。
- 查询和恢复时必须查看 Git 基线与本地候选变化。已提交的 Trace 仍包含暂定发现，不是已接受的 Claim。
- 接受知识前展示本轮语义摘要、依据、风险/证据缺口及实际文件范围。取得用户确认后才调用 `accept --confirmed`；实施模板的授权不能代替真实领域知识审阅。
- `prepare` 不等于入库。确认后内容或基线有变化，重新准备并审阅。不要绕过脚本直接提交研究文件。
- 仅因用户允许保留假设，不填写 `verified`。报告状态 current 只表示相对引用知识已复核。
- Source 快照默认在实例 `.cache/sources`，不随 Git 提交。外部来源或缓存不可用时如实说明。

## 修改工具代码

保持实现最少；字段契约以 schemas 为准。修改规则时先写有行为意义的测试，运行 `uv run pytest` 与 `uv run ruff check .`。所有研究示例必须与合成测试样例隔离。
