# sync_getnote_to_Obsidian

将「得到大脑」笔记增量同步到 Obsidian 的自动化工具。

## 功能概述

- 调用得到大脑 OpenAPI，拉取笔记列表
- 通过 `sync_state.json` 记录同步游标，支持**增量同步**（只处理新笔记）
- 无标题笔记自动调用 **DeepSeek** 生成语义标题
- 按固定格式写入 Obsidian vault，生成带 YAML frontmatter 的 markdown 文件
- 遵循 **create once, never mutate** 原则，已同步文件永不覆盖

## 架构

系统分为两层，严格隔离：

| 层级 | 说明 | 操作权限 |
|------|------|----------|
| **Raw Layer** | 真实历史档案，source of truth | 只允许 create，禁止修改/删除 |
| **Interpretation Layer** | AI 派生认知层（Obsidian 其他目录） | 允许演化 |

## 前置条件

- Python 3.9+（无第三方依赖，仅使用标准库）
- 得到大脑 OpenAPI 的 `API Key` 和 `Client ID`
- （可选）DeepSeek API Key，用于为无标题笔记自动生成语义标题

## 配置

通过环境变量配置，运行前需设置：

```bash
export GETNOTE_API_KEY="your_api_key"
export GETNOTE_CLIENT_ID="your_client_id"
export DEEPSEEK_API_KEY="your_deepseek_api_key"   # 可选
```

脚本内的硬编码配置（如需调整请直接修改脚本）：

| 常量 | 默认值 | 说明 |
|------|--------|------|
| `SYNC_START_DATE` | `2026-03-21` | 只同步该日期之后的笔记 |
| `OBSIDIAN_OUTPUT_DIR` | `/Users/leoclaw/LeoObisidian_Macmini/00 Sources/GetNote` | 输出目标目录 |

## 使用方法

```bash
python3 scripts/sync_getnote_to_obsidian.py
```

**唯一合法执行入口**为 `scripts/sync_getnote_to_obsidian.py`，禁止通过其他方式触发同步。

运行完成后输出统计信息：

```
同步完成。created=4  skipped=12  failed=0
```

若有笔记写入失败，脚本以退出码 `2` 结束。

## 输出文件格式

### 文件名

```
YYYY-MM-DD HH-MM Title.md
```

示例：`2026-05-26 19-17 AI认知架构.md`

### YAML Frontmatter

```yaml
---
source: get
created: 2026-05-26 19:17:00
get_note_id: 1912158461031155008
noteType: RawGet
tags:
  - AI_Strategy
  - 认知架构
---
```

字段说明：

| 字段 | 说明 |
|------|------|
| `source` | 固定为 `get` |
| `created` | 笔记原始创建时间 |
| `get_note_id` | 得到大脑笔记 ID（用于去重检测） |
| `noteType` | 固定为 `RawGet` |
| `tags` | 来自笔记标签 + 内容中的 hashtag，自动规范化 |

### 标签规范化

- 空格替换为下划线：`AI Strategy` → `AI_Strategy`
- 去除非法字符：`/ \ : * ? " < > |`

## 项目结构

```
sync_getnote_to_Obsidian/
├── scripts/
│   └── sync_getnote_to_obsidian.py   # 唯一同步脚本
├── logs/
│   ├── sync.log                       # 运行日志
│   └── sync_error.log                 # 错误日志
├── sync_state.json                    # 增量同步游标（git 忽略）
├── PROJECT_CONVENTIONS.md             # 治理规范（必读）
└── README.md
```

## 治理原则

详见 [PROJECT_CONVENTIONS.md](./PROJECT_CONVENTIONS.md)，核心要点：

- **不可变原则**：Raw markdown 创建后永久 immutable，禁止修改已有文件的任何内容
- **仅追加**：同步脚本只能创建新文件，文件已存在则跳过
- **单一入口**：禁止创建其他同步系统或脚本副本
- **迁移授权**：批量修改/重命名等高风险操作需明确人工授权（`migration approved`），未获授权前 AI 必须拒绝执行

## API 限流处理

遇到 `429 Too Many Requests` 时，脚本自动等待 60 秒后重试，最多重试 5 次。
