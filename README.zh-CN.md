# lifeline — Claude Code 的自主 Harness 工程

[English](./README.md) | 简体中文

一个独立的 Claude Code [插件市场](https://docs.claude.com/en/docs/claude-code/plugins)，提供端到端的 **代理工作流**，用于自主 Harness 工程实践。该工作流把多个专职代理串成单一流水线 —— 初始化代理、coder、本地 reviewer、云端 reviewer、PR 创建器、PR 合并器 —— 接收一段功能描述、最终以一个 clean 的 PR 交付：

> 需求 → 头脑风暴产品规格 → 分阶段功能列表 → coder + 跨厂商 reviewer 循环 → 云端评审修复循环 → 合并 PR

七个 Skills 端到端覆盖整个流水线（设计 → 构建 → 评审 → PR），外加一个独立的目标驱动循环（改编自 OpenAI Codex 的 `/goal`）。

## Skills

按一个功能从设计到合并的全生命周期顺序排列 —— 设计 → 自主构建 → 本地评审 → 创建 PR → 修复 PR 评审结果 → 合并。`/lifeline:deliver` 是例外：独立的目标驱动 Skill，不属于 PR 流水线。

| Skill | 功能 |
| --- | --- |
| `/lifeline:planner` | 自包含的设计规格撰写器：引导你完成头脑风暴方法论，将规格写入 `docs/superpowers/specs/`，然后自动在结果上运行 Codex 评审并应用你选择的修改。v1 仅生成规格 —— 实施计划请单独运行 `/superpowers:writing-plans`。 |
| `/lifeline:loop` | 启动自主开发 Harness —— 收集需求、头脑风暴产品规格、生成 `app_spec.md`、启动代理循环。语言无关、项目无关；自动读取项目根目录的 `CLAUDE.md` / `AGENTS.md` 来获取项目特定的构建/测试/lint 命令。 |
| `/lifeline:deliver` | 目标驱动的会话内循环。两种模式：`/lifeline:deliver <objective>`（纯模式 —— Claude 在每次迭代中根据改编自 Codex `/goal` continuation 提示词自我审计）和 `/lifeline:deliver pair [N] <objective>`（配对模式 —— 完成判定委托给 `codex exec` 作为独立评判员，对其屏蔽 Claude 对话历史）。独立 Skill —— 不属于 PR 流水线。改编自 openai/codex `/goal` 模板（Apache-2.0；见 `NOTICE`）。 |
| `/lifeline:review` | 在已暂存的 diff 上运行本地 Codex 代码评审 (`codex exec review --base main`)，结果保存到 `.codex-reviews/latest.md`。 |
| `/lifeline:request-pr` | 从当前分支打开 PR，自动生成标题与正文（Summary 来自 commit list，Test plan 占位）。与 `/lifeline:approve-pr` 配对使用。 |
| `/lifeline:upsource-review` | 自驱动循环 —— 从 GitHub 拉取 PR 评审结果（Claude Code Review + chatgpt-codex-connector），按周期原子化批量修复，在已暂存的 diff 上运行 `codex verify`，提交、推送、回复并解决 connector 评审线程，然后轮询下一轮评审。 |
| `/lifeline:approve-pr` | 端到端完成一个 PR —— squash + 删除远程分支、同步本地 main、删除本地 feature 分支，并安全地清理关联的 git worktrees。 |

## 安装

Lifeline 以 Claude Code 插件市场的形式发布。在任意 Claude Code 会话中运行：

```
/plugin marketplace add winoooops/lifeline       # 1. 注册市场目录
/plugin install lifeline@lifeline                # 2. 从市场安装插件 (plugin@marketplace)
/reload-plugins                                  # 3. 在当前会话中激活新的斜杠命令
```

两步都必需 —— `marketplace add` 仅注册目录，`plugin install` 才会激活 Skills。简写形式 `winoooops/lifeline` 会解析为 `https://github.com/winoooops/lifeline`，你也可以传完整的 Git URL。

从本地 clone 安装（用于开发）：

```
/plugin marketplace add /absolute/path/to/lifeline
/plugin install lifeline@lifeline
/reload-plugins
```

卸载：

```
/plugin uninstall lifeline@lifeline
/plugin marketplace remove lifeline
```

升级到 `main` 上的最新 commit：

```
/plugin marketplace update lifeline
/plugin install lifeline@lifeline
```

### 安装内容

`/plugin install` 会把整个仓库同步到 `~/.claude/plugins/cache/lifeline/lifeline/<version>/`，包含：

- `skills/` 下的 7 个 Skills（执行 `/reload-plugins` 后会被自动补全为 `/lifeline:<skill>`）。
- `harness/` Python orchestrator —— `/lifeline:loop` 调用此目录。在启动循环前确保 `python3` 与 `harness/requirements.txt` 中的依赖在 `$PATH` 下可用。一次性安装依赖：`pip3 install -r ~/.claude/plugins/cache/lifeline/lifeline/<version>/harness/requirements.txt`。
- Claude Code 用以注册 Skills 的 `.claude-plugin/marketplace.json` 与 `plugin.json` 清单文件。

### 自动补全变通方案

由于 [Claude Code 的一个已知问题](https://github.com/anthropics/claude-code/issues/18949)，插件 Skills 当前不会出现在 `/` 自动补全里。修复方法是在 `~/.claude/commands/` 下为每个 Skill 创建一个轻量包装文件。一次性运行：

```bash
mkdir -p ~/.claude/commands
while IFS='|' read -r slug desc; do
  cat > ~/.claude/commands/lifeline-${slug}.md <<EOF
---
description: ${desc}
---
Use the Skill tool to invoke \`lifeline:${slug}\` with these arguments: \$ARGUMENTS
EOF
done <<'SKILLS'
planner|头脑风暴设计规格并自动运行 Codex 评审
loop|启动自主开发 Harness
deliver|目标驱动的会话内循环（纯模式或与 Codex 配对）
review|在已暂存的 diff 上运行本地 Codex 代码评审
request-pr|从当前分支打开 PR，自动生成正文
upsource-review|自驱动循环修复 PR 评审结果（Claude + Codex）
approve-pr|端到端完成 PR（squash、删分支、清理 worktrees）
SKILLS
```

执行 `/reload-plugins` 后，`/lifeline-*` 别名会出现在自动补全里。直接输入 `/lifeline:*` 始终有效。

## 配套 GitHub Action —— `Claude PR Review`

`/lifeline:upsource-review` 轮询的是 **由 `github-actions[bot]` 创建的真实 PR 评审 comment**。要产出该 comment，需要在每个 PR 上运行 [Claude PR Review workflow](.github/workflows/claude-review.yml)。Lifeline 自带一个可工作的副本，可以直接拷贝到任意项目：

| 文件 | 用途 |
| --- | --- |
| `.github/workflows/claude-review.yml` | PR open/sync 时运行 [`anthropics/claude-code-action@v1`](https://github.com/anthropics/claude-code-action)，返回结构化 JSON，并发布一条聚合的 `## Claude Code Review` comment（带严重级别 + IDEA 块）。 |
| `.github/codex/codex-output-schema.json` | Action 用以约束模型输出的 JSON schema（severity、title、文件、行号范围、IDEA 字段）。 |

**单仓库设置：**

```bash
# 从 lifeline 插件缓存（执行 /plugin install lifeline@lifeline 之后）
LIFELINE=~/.claude/plugins/cache/lifeline/lifeline/<version>
mkdir -p .github/workflows .github/codex
cp "$LIFELINE/.github/workflows/claude-review.yml" .github/workflows/
cp "$LIFELINE/.github/codex/codex-output-schema.json" .github/codex/
```

然后在仓库里添加一个 `CLAUDE_CODE_OAUTH_TOKEN` secret（Settings → Secrets and variables → Actions）。token 通过 `claude login --print-token` 生成，或参考 [Claude Code GitHub Actions 文档](https://docs.claude.com/en/docs/claude-code/github-actions)。

如果存在 `CLAUDE.md` / `AGENTS.md` / `docs/code-review.md`，workflow 会读取它们作为项目特定的评审标准 —— 把其中之一放在仓库根目录可以让评审输出更稳定。

**与 lifeline 的协作流程：**

1. PR 打开 → workflow 运行 → bot 发布 `## Claude Code Review` comment。
2. 你运行 `/lifeline:upsource-review` → 拉取该 comment 加上来自 `chatgpt-codex-connector` 的内联评论，按周期原子化批量修复，运行 `codex verify`，用带水印的 trailer 提交、推送、然后轮询下一轮评审。
3. 循环持续直到两个 reviewer 都报告 clean。

## 从 harness-plugin 迁移

如果你之前用过 [`harness-plugin`](https://github.com/winoooops/vimeflow/tree/main/plugins/harness)（lifeline 的内嵌前身），自动迁移不会影响你 —— 两者可以并存以便验证。验证完成后从你的项目市场移除 `harness-plugin`。

注意：scratch 目录从 `.harness-github-review/` 改名为 `.lifeline-upsource-review/`。如果你的 `.harness-github-review/` 留有 harness-plugin 时代的工件（特别是 `cycle-*-aborted/` 取证目录），lifeline 不会自动恢复。删除前请手动检查。

## 系统要求

- [Claude Code](https://docs.claude.com/en/docs/claude-code/overview) ≥ 1.0
- [Codex CLI](https://github.com/openai/codex) 在 `$PATH` 下（`review`、`upsource-review`、`planner` 使用）。Lifeline **不** 强制指定 Codex 模型 —— 默认情况下 `codex` 会按当前的 auth 模式选择正确的默认模型（例如 ChatGPT-account auth 与 API-key auth 可用的模型列表不同）。如果你确实想固定一个模型，在启动 `/lifeline:loop` 之前 `export LIFELINE_CODEX_MODEL=<name>`（例如 `gpt-5.4`）。
- [GitHub CLI](https://cli.github.com/) (`gh`) 已认证（`upsource-review`、`request-pr`、`approve-pr` 使用）
- `git`、GNU coreutils、可选 `timeout`（缺失时 Skills 会优雅降级）

## 贡献

clone 之后启用 verifier pre-commit hook（拒绝重新引入 `harness-plugin` 引用 —— 见 `.githooks/pre-commit`）：

```bash
git config core.hooksPath .githooks
```

## 致谢

驱动 `/lifeline:loop` 的 `harness/` Python orchestrator 改编自 Anthropic 的 [autonomous-coding quickstart](https://github.com/anthropics/claude-quickstarts/tree/main/autonomous-coding)。最初的双代理（initializer + coder）模式、`feature_list.json` 调度和 settings-isolation 安全模型来源于该 demo。

Lifeline 在原版基础上扩展：

- **用 `claude -p` 子进程替换原 Python SDK 来启动 subagent** —— 原 quickstart 通过 Anthropic Python SDK 启动每个 subagent（initializer、coder），需要 `ANTHROPIC_API_KEY`。`/lifeline:loop` 改为通过 `claude -p` 命令行子进程来驱动 subagent，直接继承操作员现有的 Claude Code CLI 认证。**结果：一个 Claude Code "Coding agent" 订阅就足以运行完整的代理团队 —— 不需要 API key，也不需要单独的计费通道。** SDK 后端保留为可选 fallback（`--client sdk`），供需要自定义 `ANTHROPIC_BASE_URL`（代理、自建 gateway）或在 CLI 不可达环境运行的操作员使用。
- 在 coder 迭代之上叠加了本地 + 云端 Codex 评审循环。
- 通过 `gh` 实现 PR 创建与合并（`/lifeline:request-pr`、`/lifeline:approve-pr`）。
- 自驱动的 `upsource-review` 修复循环，同时轮询 Claude Code Review 和 `chatgpt-codex-connector`。
- LLM 兜底的 bash 命令策略评审器。
- **`/lifeline:deliver`** —— 目标驱动的会话内循环，改编自 OpenAI Codex 的 [`/goal` 命令](https://github.com/openai/codex/tree/main/codex-rs/core/templates/goals)（Apache-2.0）。`skills/deliver/references/` 下的 `continuation.md` 与 `budget_limit.md` 是上游模板的衍生作品，完整归属信息见 `NOTICE`。配对模式将完成判定委托给 `codex exec` 作为独立评判员 —— 这种 Outcomes 风格的隔离能减少自审中的确认偏差。

## 许可

MIT —— 见 [LICENSE](./LICENSE)。
