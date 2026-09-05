# Agent 工作流与工具

在工具仓库根目录运行。`--root` 指定一个研究实例；默认根目录，示例用 `--root examples/emb`。目录和 ID 由脚本处理，内容判断由 Agent 完成。

```sh
uv sync
uv run python scripts/repo.py --root . init --title '课题标题' --question '研究问题' --scope '研究范围' --done '完成标准'
uv run python scripts/repo.py --root . new ResearchTrace --title '本轮研究'
uv run python scripts/repo.py --root . new Claim --title '一个关键判断'
uv run python scripts/repo.py --root . check
uv run python scripts/repo.py --root . index
uv run python scripts/repo.py --root . status
```

`new` 仅生成不完整草稿，不声称已通过检查。填写正文和元数据后运行 check。字段及必需二级标题由 `schemas/objects.yaml` 定义。

## 来源与引用

Source 位于 `knowledge/sources/`，`resource` 是原始 URL，`research.publisher` 可明确写“未知（原因）”。获取时间来自实际读取，不把网页日期当获取时间。

本地原文使用 `snapshot /绝对路径/材料.pdf` 保存内容寻址快照，返回 path、sha256；将结果填入 Source 的 `research.snapshot`。该操作不抓网页，网页获取由 Agent 使用已有工具完成。重复获取不同内容产生不同缓存路径，不能覆盖旧内容。

知识文件的 OKF `sources` 条目使用稳定来源 ID 和包内相对路径，例如 `resource: /sources/source_x.md`。Claim 的 `research.evidence` 通过同一 source_id 指向该来源，并带 locator 和 supports/challenges/context。正文可使用标准 Markdown 链接；逐来源脚注标签与 sources.id 一致。

项目元数据中的 traces、task、proposed_changes 以研究实例根目录为路径基准。Artifact 的 claims、Relation 两端和 Trace 的 inspected_sources 使用稳定对象 ID。Knowledge 包内以 `/` 开头的链接相对于 knowledge；其他工作文件的 `/` 相对于实例根目录。

## 一次入库

1. Agent 在对应 Trace 的“本轮知识变化”中写出语义摘要，指出判断变化、依据、争议、输出影响与下一步。
2. Claim 变化时用 `impact CLAIM_ID ...` 将显式关联报告标为待复核。必要时复核并修订报告，保留仍未完成的 needs_review。
3. 重建索引，执行 check，修复结构错误。研究不确定性保留并解释。
4. `prepare FILE ...`：逐个指定本轮相关文件，包含新来源、索引、Trace、Task 等所需引用。返回本地 ticket、文件内容摘要值和候选 Git tree。脚本针对实际候选提交校验，不会偷偷包含其他暂存文件。
5. 展示语义摘要与 prepare 范围，获得用户对这批具体内容的确认。
6. `accept TICKET --message '本轮知识变化' --confirmed`：将返回的 ticket 原样传入。任何实质修改后重新 prepare 并审阅，不能复用旧确认。

accepted_base 是当前 Git HEAD 中知识的版本基线。Git 历史仅证明文件版本，不能独立证明事实正确或用户身份。脚本的 --confirmed 是 Agent 已取得确认的声明，不是身份认证。受控提交使用独立 Git index 和 commit-tree，不运行用户的 commit hooks；它运行本项目校验，保留无关暂存项，直接操作 Git 仍可绕过本协议。

## 恢复与维护

新会话先运行 status，再读取 Topic、knowledge/index、相关 Task 和最近 Trace。对工作区修改过的条目，必要时用 Git 读取 HEAD 版本进行对比；不要把本地候选修改当成已接受事实。没有 HEAD 时明确“尚无正式入库基线”。

给用户短摘要：当前问题、已知、关键不确定性、下一步。默认无需另建会过时的研究状态摘要。Query 只读；research/maintain 可以写候选内容，但都遵守集中入库规则。

结构检查不能发现未记录的语义依赖，也不能判定证据是否真的支持命题。即使有来源链接，Agent 仍需阅读定位并判断支持关系。
