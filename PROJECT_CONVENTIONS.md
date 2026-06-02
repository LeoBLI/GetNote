# GetNote Project Conventions

## Project Philosophy

本项目是长期认知档案系统。

最高优先级：

- authenticity
- immutability
- historical integrity
- rollback safety
- low mutation risk

系统核心目标：不是 AI 优化，而是长期稳定。

---

## Core Architecture

系统严格分为两层：

1. **Raw Layer** — 真实历史档案层，immutable，append-only，source of truth
2. **Interpretation Layer** — AI 派生认知层，允许演化

两层必须严格隔离。

Raw Layer 允许：create new files
Raw Layer 禁止：rewrite、regenerate、rename、semantic reinterpretation、metadata restructuring

---

## Immutable Raw Archive Principle

原则：create once, never mutate。

Raw markdown 创建后永久 immutable。

对于任何已存在 markdown，禁止修改：frontmatter、title、body、tags、filename、attachment embeds。

---

## Create-Time Exception

以下行为只允许在首次文件创建阶段执行一次：

- semantic title generation
- filename normalization
- metadata initialization
- tag normalization
- attachment embed generation

创建完成后永久 immutable。

---

## Filename Format

```
YYYY-MM-DD HH-MM Title.md
```

示例：`2026-05-26 19-17 AI认知架构.md`

要求：包含时间戳、human-readable、使用空格分隔、不使用下划线。

---

## Frontmatter Schema

固定格式，字段顺序固定：

```yaml
---
source: get
created:
get_note_id:
noteType: RawGet
tags:
---
```

禁止：schema drift、YAML restructuring、自动 metadata 扩展。

---

## Tag Normalization Rules

所有 tags 必须转换为 Obsidian-compatible format：

- spaces → underscores
- 删除非法字符：`/ \ : * ? " < > |`

示例：`AI Strategy` → `AI_Strategy`

---

## Attachment Rules

所有 attachment 统一保存在 `get_attachment/` 目录。

图片必须使用 Obsidian wiki embed：

```markdown
![[get_attachment/filename.jpg]]
```

禁止：markdown relative paths、external image urls、attachment relocation。

---

## Sync Governance

sync 脚本只能 create new files。

如果文件已存在：必须 SKIP。

禁止：overwrite、rewrite、rename、patch existing files。

同步状态通过 `sync_state.json` 持久化，记录最后同步游标，支持增量同步。

---

## Human Authorization Boundary

AI 默认不拥有 historical mutation authority。

以下属于 high-risk mutation operation，执行前必须获得明确人工授权：

- migration
- rewrite existing markdown
- metadata repair
- bulk rename
- historical tag normalization
- attachment relocation
- archive restructuring

唯一合法授权语句：

```
migration approved
```

未收到此语句，AI 必须拒绝执行。

---

## Migration Governance

Migration 不是 sync，属于高风险操作。

必须：使用独立 migration script、patch-only editing、migration 前 git checkpoint。

禁止：full markdown regeneration、AI rewriting complete files、semantic restructuring。

所有 repair 必须 minimal patch。AI 必须像 surgical patch tool，不是 document generator。

---

## AI Governance

AI 最大风险不是错误，而是 semantic overreach。

AI 禁止：自由重构 archive、自动优化历史记录、redesign metadata structure、reinterpret history、auto-normalize historical files。

---

## Architecture Constraints

唯一执行入口：`scripts/sync_getnote_to_obsidian.py`（相对于 project root）

禁止：duplicate sync systems、multiple competing pipelines、hidden mutation flows、AI self-expanding architecture。

临时脚本（fix_*.py、migrate_*.py 等）执行完成后必须删除，保持环境纯净。

---

## Git Governance

Git 是 cognition rollback system。

任何 migration 前必须：

```bash
git add .
git commit -m "checkpoint before migration"
```

---

## Vault Structure

```
LeoObisidian_Macmini/
├── 00 Sources/
│   ├── GetNote/       ← Raw Layer 同步目标
│   ├── Flomo/
│   ├── ChatGPT/
├── Distilled/
├── Methodology/
├── Journey/
├── Philosophy/
├── ContentSeeds/
├── Conversations/
```

---

## Long-Term Goal

最终目标不是 markdown 管理，而是构建长期稳定的 Human-AI Cognitive Infrastructure。
