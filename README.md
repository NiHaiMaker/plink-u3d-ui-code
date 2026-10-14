# U3D UI 编码技能

面向 Unity UGUI 的 Codex 技能：根据策划案和已生成的 Prefab，先拆解任务、实现方式与资源 / 数据缺口，确认后逐项实现和验证 UI。

适用于新界面编码、已有界面迭代，以及实际使用 PLink / XUGUI 的项目。纯 PSD 整理与切图应使用对应美术技能。

## 安装

首次安装，在 PowerShell 中执行（目标目录须不存在）：

```powershell
git clone https://github.com/NiHaiMaker/u3d-ui-code.git "$env:USERPROFILE\.codex\skills\u3d-ui-code"
```

如果已通过 Git 安装，可在技能目录执行 `git pull --ff-only` 更新。已有手工安装目录时，先保留本地改动，再用仓库中的 `SKILL.md`、`agents/` 和 `references/` 同步更新。

## 使用

提供策划案和已生成的 Prefab 路径，并在请求中指定 `$u3d-ui-code`：

```text
使用 $u3d-ui-code，这是策划案和已生成的 Prefab。
先列出任务、实现方式及缺少的资源和数据，等我确认。
```

技能会先进行只读调查，形成 `T01`、`T02` 等任务清单和 `G01` 等缺口清单。确认具体任务后继续：

```text
确认这份清单，先做 T01、T02；缺图标的 T03 暂缓。
```

已确认范围内逐项推进，分别报告静态检查、Unity 编译、Editor 资产检查与 PlayMode 的实际结果；未执行的验证会明确标注。

## 主要约定

- 复用已生成的 Prefab、绑定、布局和 GUID，遵守目标项目规范与 Unity 工具约定。
- 运行时不补挂 Unity 组件，不覆盖 Prefab 的字号、字体、布局等固定配置；允许按需求更新文本和展示状态。
- 动态条目使用项目已有的 `_@` 完整模板克隆 / 回收入口。
- UI 调用既有业务接口；默认只修改业务，不擅自修改框架或拆出职责代码文件。
- UI 特效使用非缩放时间；按钮射线接收、点击监听与点击动画作用于同一按钮对象。
- 已确认的数据契约直接消费，不仅出于防御性习惯添加兜底分支。

完整规则以 [SKILL.md](SKILL.md) 为准。PLink / XUGUI 项目还需按其中的路由读取项目自身规范。

## 仓库内容

| 文件 | 用途 |
| --- | --- |
| [SKILL.md](SKILL.md) | 技能入口、核心约定与三阶段工作流 |
| [agents/openai.yaml](agents/openai.yaml) | 技能显示名称与默认提示 |
| [references/plink-xugui.md](references/plink-xugui.md) | PLink / XUGUI 项目接入说明 |

## 许可证

本仓库采用 [MIT License](LICENSE)。
