# GetNote Sync Skill

## Execution Boundary

唯一合法执行入口：

```
scripts/sync_getnote_to_obsidian.py
```

路径相对于 project root（PROJECT_CONVENTIONS.md 所在目录）。Claude 必须直接调用此脚本。

禁止：

- 动态生成替代 sync 脚本
- inline shell sync workflow
- 临时 python sync logic
- 在 project 中创建新的 sync system
- 修改 sync 脚本
- 绕过 sync 脚本

---

## Scope

本 Skill 被允许：

- 调用得到大脑 API 获取笔记
- 读取同步状态文件（sync_state.json）
- 创建新的 markdown 文件
- 下载 attachments
- 更新同步状态文件

本 Skill 被禁止：

- 修改任何已存在的 markdown 文件
- 删除任何文件
- 重命名任何文件
- 执行 migration 操作
- 重新生成或覆盖已同步内容

---

## Authorization

以下操作默认被禁止，必须收到明确授权后才能执行：

- 修改已存在的 markdown 文件（任何字段）
- 批量重命名
- metadata 修复
- archive 重构

唯一合法授权语句：

```
migration approved
```

未收到此语句，必须拒绝执行上述操作。
