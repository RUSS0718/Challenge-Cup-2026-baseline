# Codespace 与成熟工程初始化调研

**日期：2026-10-13**
**范围：GitHub Codespaces、Dev Container、Python 依赖、质量门禁、Secrets 与合并保护**

## 已确认事实

- GitHub Codespaces 使用仓库中的 `.devcontainer/devcontainer.json` 定义统一开发环境；其中可以指定工具、运行时、扩展和端口。GitHub 建议将团队共同需要的工具写入仓库配置，不把个人偏好塞进共享配置。
- Dev Container 生命周期有 `onCreateCommand`、`updateContentCommand`、`postCreateCommand`、`postStartCommand` 和 `postAttachCommand`。需要仓库内容且允许使用用户权限/Secrets 的安装动作应放在 `postCreateCommand`；镜像构建阶段不应依赖个人 Secrets。
- GitHub Codespaces Secrets 以环境变量提供给运行中的 Codespace 和生命周期脚本，不能在 Dockerfile、镜像入口或 Feature 构建阶段使用。
- uv 的项目模式使用 `pyproject.toml`、`.python-version`、`.venv` 和 `uv.lock`；`uv run` 会检查 lockfile 与环境是否和项目声明同步。uv 官方建议将 `uv.lock` 纳入版本控制。
- GitHub Actions 的 Python 指南建议用 `actions/setup-python` 固定 Python，并在 CI 中执行与本地相同的测试命令；setup-python 支持依赖缓存。
- pre-commit 管理不同语言的 hook 环境，开发者通过 `pre-commit install` 安装提交钩子，官方建议在 CI 中再次运行 hook。
- Ruff 官方提供 lint、format 和 `ruff-pre-commit`；Ruff 可以统一本地、pre-commit 和 CI 的格式/静态检查。
- GitHub 保护分支可以要求 Pull Request、审批和 status checks；required status checks 通过后才允许合并。

## 官方来源

- [GitHub: Introduction to dev containers](https://docs.github.com/en/codespaces/setting-up-your-project-for-codespaces/adding-a-dev-container-configuration/introduction-to-dev-containers)
- [Dev Container Specification: lifecycle commands](https://github.com/devcontainers/spec/blob/main/docs/specs/devcontainerjson-reference.md)
- [GitHub: Codespaces secrets](https://docs.github.com/en/codespaces/managing-your-codespaces/managing-your-account-specific-secrets-for-github-codespaces)
- [uv: Working on projects](https://docs.astral.sh/uv/guides/projects/)
- [GitHub: Building and testing Python](https://docs.github.com/en/actions/tutorials/build-and-test-code/python)
- [pre-commit documentation](https://pre-commit.com/)
- [Ruff installation and pre-commit integration](https://github.com/astral-sh/ruff/blob/main/docs/tutorial.md)
- [GitHub: Status checks](https://docs.github.com/en/pull-requests/reference/status-checks)

## 当前工作树的事实

当前 `develop` 工作树已经有：

- 根 `user_agent.py` 和官方评分实现；
- 本地 `main.py`、`demo_server.py` 和测试；
- `requirements.txt` 与 `requirements-local.txt`；
- `pytest.ini`；
- 产品 PRD 和技术架构文档。

当前没有：

- `.devcontainer/`；
- `pyproject.toml`、`.python-version` 和 `uv.lock`；
- `.pre-commit-config.yaml`；
- `.github/workflows/`；
- Codespaces Secrets 推荐字段；
- 分支保护和 required checks 的仓库说明。

## 适用于本分支的结论

1. Dev Container 是团队环境入口，必须保持可重建和幂等；它不应读取答案库，也不应修改官方提交路径。
2. 依赖需要先确定一个权威来源。当前 `requirements.txt` 是官方提交边界，不能直接删除；迁移到 `pyproject.toml/uv.lock` 必须通过生成/比对门禁，避免两套依赖漂移。
3. API Key 通过 Codespaces Secret 或本地未跟踪 `.env` 注入。任何构建镜像、提交日志和 trace 都不应包含凭证。
4. 本地 pre-commit 和 CI 必须运行同一组质量命令；Codespace setup 只负责准备环境，不能代替 CI。
5. 分支保护和 required checks 是仓库成熟化的最后一道门，不能只依赖个人本地测试。
