# 成熟项目的仓库初始化蓝图

这份蓝图是下一步实现 `.devcontainer` 和 CI 前的工作协议。它先固定边界，再配置工具，避免把开发环境、提交环境和官方运行环境混在一起。

## 目标

任何新成员或新 Codespace 完成 setup 后，都能：

1. 使用固定 Python 版本进入可复现环境；
2. 一条命令安装本地/测试依赖；
3. 一条命令运行质量检查；
4. 在没有 API Key 时完成离线导入、结构测试和 Demo 健康检查；
5. 在有授权 Secret 时运行明确标记的联网任务；
6. 从同一份命令得到本地和 CI 一致的结果。

## 推荐仓库文件

```text
.devcontainer/
  devcontainer.json
  post-create.sh
  welcome.sh
pyproject.toml
.python-version
uv.lock
.pre-commit-config.yaml
.github/
  workflows/quality.yml
  CODEOWNERS
  pull_request_template.md
.env.example
docs/engineering/bootstrap.md
```

## 初始化顺序

### 1. 先做基线锁定

记录当前官方入口、生产依赖、最小 `solve()`、默认测试命令和当前提交 SHA。先把官方提交文件和产品侧车列成两份清单。

### 2. 创建最小 Dev Container

`devcontainer.json` 只放全员需要的内容：固定 Python/Node 版本、Git、uv、pytest、Ruff、pre-commit 和常用编辑器扩展。`postCreateCommand` 只做幂等安装与检查，不启动长服务、不调用模型、不写运行产物。

### 3. 选择依赖权威源

短期保留 `requirements.txt` 作为官方提交依赖，新增开发依赖清单和锁定检查。完成一次干净安装比对后，再决定是否迁移到 `pyproject.toml + uv.lock`。迁移后由 CI 检查 `requirements.txt` 是否由锁定配置生成且无未声明包。

### 4. 建立统一质量命令

建议固定以下入口：

```text
make setup       # 安装开发环境，不调用模型
make check       # 格式、lint、导入和单元测试
make test        # pytest
make demo-check  # Demo health/contract checks
make clean       # 清理可重建缓存，不删除 artifacts 证据
```

Windows/PowerShell 和 Codespace 应调用同一 Python 模块或跨平台脚本，避免维护两套命令。

### 5. 本地 hook 与 CI 双重验证

pre-commit 做快速检查：尾随空格、JSON/YAML、Ruff、基础 Secret 扫描。CI 重新执行全部 hook、导入验收、测试、编译和 devcontainer 配置检查。hook 失败可以在本地快速反馈，CI 才是合并门。

### 6. Secrets 分层

`.env.example` 只列变量名和用途；真实值使用 Codespaces Secret、GitHub Actions Secret 或本地未跟踪 `.env`。构建镜像不读取 Secret，离线测试不要求 Secret，联网测试必须显式选择 Profile。

### 7. CI 和分支保护

第一条 workflow 只做质量门：固定 Python、安装锁定依赖、执行 `pre-commit run --all-files`、`pytest`、`py_compile`、入口 smoke、Demo contract check。GitHub 主分支要求 Pull Request、至少一次审查和 quality check 通过后才能合并。

### 8. 运行产物边界

`artifacts/<run_id>/`、模型 raw、答案、报告、临时日志都保持 ignored。源码、测试、fixture、配置和压缩后的结论进入 Git。CI 只上传脱敏测试报告和失败日志，不上传凭证或完整模型响应。

## 对本项目的特殊边界

- `official` Profile 不读取产品数据库、不联网、不加载答案库；
- `showcase_mvp` Profile 才启用 Workbench、持久化、子 Agent、搜索和工具；
- `research_experimental` Profile 才允许沙箱、长期记忆、Debate 或 RSI；
- Codespace setup 可以安装这些开发依赖，但不能让官方 `user_agent.py` 自动导入产品侧车；
- 每次 setup 变更都要记录容器镜像、Python、依赖锁文件和验证命令。

## 完成条件

- 新 Codespace 从创建到 `make check` 成功无需人工补装隐藏依赖；
- 没有 Secret 时 setup 和离线检查仍然成功；
- 有 Secret 时联网能力只通过显式命令启用；
- 本地质量命令和 CI 命令一致；
- 重建容器不会丢失源码、锁文件和可提交配置；
- 官方入口回归结果与 setup 变更前一致。
