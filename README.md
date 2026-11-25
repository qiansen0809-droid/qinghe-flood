# 青河流域洪水预报系统
钱森 · 软件工程课程实践二期

值班员可以在浏览器中导入洪水过程、选择参数版本、一键或定时起报、复核过程线并签发产品。系统使用一期新安江模型和冻结参数，带四场教学数据及全部 15 个降雨情景。

## 启动工作台

在安装 Docker Engine 和 Compose v2 的环境克隆本项目，进入仓库目录运行：

```sh
docker compose up --build -d --wait
```

打开 [本地预报工作台](http://127.0.0.1:8000/)、[交互接口](http://127.0.0.1:8000/docs) 或 [健康检查](http://127.0.0.1:8000/health)。首次启动自动导入四场黄金数据。默认端口仅绑定本机，数据持久化到 Compose 命名卷。

**演示**　在“预报工作台”选择 event2，启用集合预报并起报。在结果中核对基线洪峰和警戒消息，签发后下载产品公报，再执行历史回放。第二场基线洪峰约 868.59 m³/s。选择 event4 并分别关闭、打开滚动校正，可比较留出场的 40 个时段。若要看调度，请在“定时起报”登记短周期任务，确认生成产品后停用。

## 本机 Python 运行

使用 Python 3.13。创建虚拟环境并激活后执行：

```sh
python -m pip install -r requirements-dev.txt
python -m uvicorn app.api:app --host 127.0.0.1 --port 8000 --workers 1
```

模型步长 6 h。工作台、定时器和领域服务运行在同一进程。一个数据库只启动一个调度进程。Python 默认使用 `var/qinghe.sqlite3`；容器使用 `/srv/state/qinghe.sqlite3`。配置项见运维手册。

## 验证与复现

```sh
python -m pytest -q
python -m scripts.collect_evidence
python -m scripts.export_openapi
# 以下需先启动服务，会新建验收预报及站内通知
python scripts/smoke.py
```

重启后运行 `python scripts/smoke.py --check-persistence` 校验原产品、签发状态与回放摘要。CI 对每次推送及拉取请求运行测试、Docker Compose 构建、端到端验收及重启复验。运行记录见 [GitHub Actions](https://github.com/qiansen0809-droid/qinghe-flood/actions)。

## 文档和数据

| 文件 | 内容 |
|---|---|
| [项目总结报告](docs/report.pdf) | 系统架构、全流程实例、滚动校正与集合结果 |
| [需求规格说明 SRS](docs/srs.pdf) | UC1–UC5、M1–M5、O1–O4 与验收条件 |
| [接口契约](docs/openapi.json) | OpenAPI 3.1，可导入接口工具 |
| [运维与演示手册](docs/operations.pdf) | 部署、备份恢复、常见问题与现场演示 |
| [测试报告](docs/testing.pdf) | 黄金基准、验收覆盖和运行证据 |
| [数值证据](docs/evidence) | 实际运行的逐时段分位数、成员洪峰、校正对照与黄金回归结果 |
| [黄金数据](data/golden) | 一期存档的四场出口流量，共 160 点 |

各 PDF 的 LaTeX 源文件同名放在 `docs/`。在该目录使用 XeLaTeX 分别编译 report、srs、operations、testing 两遍。图件数据先由 `scripts/collect_evidence.py` 保存，再用 `scripts/plot_evidence.py` 绘制（绘图另需 matplotlib）。

本项目使用虚拟教学流域资料。操作员署名用于课程工作台的操作留痕；签发流程产生可下载的电子公报。
