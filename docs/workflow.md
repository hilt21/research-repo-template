# Agent 工作流与工具

在工具仓库根目录运行。`--root` 指定一个研究实例；默认根目录，也可指定仓库外的实例路径。合成验收用 `--root tests/fixtures/work`，默认只读。目录和 ID 由脚本处理，内容判断由 Agent 完成。

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

新会话先运行 status，再读取 Topic、knowledge/index，并按用户意图确定相关任务或交付目标。目标唯一明确时运行 `status --target 实例内对象路径`，使用返回的导航读取相应文件；有多个合理目标且上下文无法消歧时才询问。不能只按“最近修改”选择另一项工作的 Trace。对工作区修改过的条目，必要时用 Git 读取 HEAD 版本进行对比；不要把本地候选修改当成已接受事实。没有 HEAD 时明确“尚无正式入库基线”。

给用户短摘要：当前问题、已知、关键不确定性、下一步。默认无需另建会过时的研究状态摘要。Query 只读；research/maintain 可以写候选内容，但都遵守集中入库规则。

结构检查不能发现未记录的语义依赖，也不能判定证据是否真的支持命题。即使有来源链接，Agent 仍需阅读定位并判断支持关系。

## 交付与口述反馈

持续投入、有独立用途与验收标准的工作，用 `new Deliverable --title '面向非专业同事的分享'` 创建一份 brief，填写目标、受众、范围和完成标准。单次问答无需创建。用户无需填写表格；Agent 从意图提取内容，仅就会改变下一步的歧义提问。

brief 位于 `deliverables/<id>.md`，通过 `research.claims` 引用共享知识。Task 和 Artifact 可用 `research.deliverable` 关联 brief 的实例内相对路径；各自最多一个交付目标，不反向重复保存任务清单。Task 的输入可用 `research.dependencies` 引用实际所需记录，输出与写入范围可写在正文。目录、ID、引用与检查顺序由 Agent 和工具处理。

先展示提纲或样稿，用户口述反馈后保留原话，提取修改要求、偏好、待核实判断及问题，修订产出并给出简短变更说明。默认修订当前目标；明确要求“两版都保留”时创建另一个目标。无法判断是否保留原目标且影响已有成果时只问一次。不将一次表达、一条建议都变成 Event 或 Task。

Agent 按完成标准复核，展示产出及重要未决事项并提出完成建议；用户接受该交付后才将 `research.deliverable_state` 从 active 改为 done。无需完成整个课题，也不表示其中所有新判断已入库。新判断仍是候选 Claim，沿用原有集中审阅。该状态与文档 status、Artifact 的 review_state 分别表达不同含义。

## Chat → Codex Work 交接

Work 专指 Codex Work 模式。三类材料同时可获得：Project context 与当前仓库状态提供约束，交接摘要提供接续入口，原 Chat 提供按定位回查的历史。导航顺序不等于无条件权威排序；当前用户指令、明确决定、知识证据和历史假设分别判断。文件协议不能控制平台是否已经注入了整个历史。

用户说“生成简短交接”时，Agent 在一份 Trace 中增加可选 `## 交接入口`：当前目标、明确决定及依据、排除事项与重新讨论条件、假设、下一步。以一屏为目标，通过链接指向 brief、Task 与原文，不复制全部状态。Trace 的其他章节照常记录研究过程；不能将精选 Trace 称为完整 Chat。

同时填写 `research.handoff`：

```yaml
handoff:
  target: tasks/task_example.md  # Task 或 Deliverable，实例内相对路径
  source: knowledge/sources/source_chat.md
  locator: 用户第 3、5 轮；原文对应标题或段落
  base: null  # 有 Git HEAD 时使用 status 返回的完整 accepted_base
```

交付级交接省略 `research.task`；任务级交接如填写 task，必须与 target 一致。原 Chat/口述先建立 Source，再用 snapshot 保存实际取得的原文。完整 Chat 不可获取时，只保留实际取得的部分并在来源说明中写明覆盖范围。不要把普通原文直接放入受控对象目录。

`status --target` 接受 Task、Deliverable 或 Trace。它返回相关文件、匹配范围的交接候选和材料状态，不自动选择或宣称已经阅读原文：available 只表示本地字节与记录哈希一致；missing 表示缓存缺失；not_cached 表示无快照；corrupt 表示字节不符。远程链接的可访问性需实际读取核实。

多个 capsule 由 Agent 根据目标、明确更新关系与依赖变化选择；不得恢复已被否定的方案或把助手建议提升为用户授权。关键冲突无法消解且影响下一步时，指出具体位置再问；无依赖工作继续。原文在本地缓存，不随 Git 同步；本轮只保证同目录接续，跨设备全文打包后置。

## 依赖基线与整体复核

`status --target` 的 freshness 和 related_freshness 使用同一套比较逻辑。依赖包括显式 `research.dependencies`、Claim、被阅读的 Source、交付关联和交接原文/目标，并跟随这些记录的必要来源；Task 的历史 traces 不自动成为新鲜度依赖。未声明的语义关系不在机械检查范围。

首次完成语义复核或生成交接后，重新运行 status，把该对象对应的 `fingerprints` 原样写入其 `research.basis`，然后执行 check；这是候选写入，不能把旧摘要配上新指纹来消除提醒。有 missing 时先解决具体缺口或如实保留未复核状态，不写入“已复核”基线。快照 corrupt 时先核对来源，不能仅更新哈希。

unrecorded 表示尚未记录依赖基线；current 只表示记录的依赖字节未变；needs_review 表示依赖新增、移除、变化或不可解析。check 将变化定位为警告，非法/缺失引用仍为错误；未完成复核的候选可带警告进入用户审阅。无关 Git 提交不使所有交付失效。status/check 不更新基线、不改变完成状态；依赖变化后的语义复核由 Agent 完成。

维护交付时，先检查结构与材料，再逐项审阅受众适配、前后矛盾、证据强度、论证缺口、反证和重复。每条实质发现给出文件/段落、问题、依据、对交付的影响与建议动作；将结果写入本轮 Trace 的“整体复核”章节。结构全绿不能省略这一步。完成复核后修订 Artifact 的 review_state 和相应 basis，仍未完成则保持 needs_review。无需为每条提醒新建待办。

最终给用户一份可读的变更与缺口说明，不要求用户逐条操作脚本。涉及知识变化时，复用 prepare/accept 精确审阅范围；“修改一下”“交付完成”都不替代知识接受。
