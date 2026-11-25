"""HTTP interface for teaching flood forecasts, products, alerts and replay."""
from __future__ import annotations

from contextlib import asynccontextmanager
import csv
import math
import os
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from .domain import Service
from .scheduler import Scheduler

ROOT = Path(__file__).resolve().parents[1]
Nonempty = Annotated[str, Field(min_length=1, max_length=100, pattern=r'\S')]


class Command(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    actor: Nonempty = 'operator'


class Forecast(Command):
    event_id: Nonempty
    plan_id: int | None = Field(default=None, ge=1, validation_alias=AliasChoices('plan_id','scheme_id'),
                                description='版本 ID；省略时读取当前启用版本')
    correction: bool = Field(False, description='使用先前观测修正下一时段流量状态')
    ensemble: bool = Field(False, description='为 event2 并行计算十五组情景')
    cutoff: str | None = Field(default=None, description='最后允许同化的观测时刻，例如 2023-07-18 00:00')


class Schedule(Forecast):
    interval_seconds: int = Field(ge=1, le=31_536_000, description='启动后首个周期到期时起报，单位秒')


class Version(Command):
    parameters: dict[str,float] = Field(description='16 个新安江参数的完整集合')


class Scheme(Version):
    name: Nonempty


class InitialState(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    WU: float = Field(ge=0)
    WL: float = Field(ge=0)
    WD: float = Field(ge=0)
    S: float = Field(ge=0)
    QS: float = Field(ge=0)
    QI: float = Field(ge=0)
    QG: float = Field(ge=0)


class ImportCSV(Command):
    csv_text: str = Field(min_length=1,max_length=1_000_000,description='带表头的 UTF-8 CSV 文本，格式与 data/events 一致')
    state: InitialState | None = Field(default=None,description='新场次必须给出七个初始状态量；示例场次默认使用索引中的状态')


class Extensible(BaseModel):
    model_config = ConfigDict(extra='allow')


class EventSummary(Extensible):
    event_id: str


class PlanVersion(Extensible):
    id: int
    name: str
    version: int
    parameters: dict[str,float]
    active: bool


class Process(Extensible):
    times: list[str]
    observed: list[float | None]
    forecast: list[float]
    raw: list[float]


class Product(Extensible):
    id: int
    event_id: str
    plan_id: int
    status: str
    result: Process


class Replay(Extensible):
    run_id: int
    match: bool


class Timer(Extensible):
    id: int
    event_id: str
    interval_seconds: int
    next_run_at: float
    last_run_id: int | None
    last_error: str | None
    status: str
    active: bool


def sample_state(folder: Path, event_id: str):
    with (folder/'events_index.csv').open(encoding='utf-8-sig', newline='') as stream:
        for row in csv.DictReader(stream):
            if row['场次编号'] == event_id:
                return {key:float(next(value for col,value in row.items() if col.startswith(f'初始{key}(')))
                        for key in ('WU','WL','WD','S','QS','QI','QG')}
    raise ValueError('导入自定义场次须提供 WU、WL、WD、S、QS、QI、QG 初始状态')


def create_app(db_path=None, data_dir=None, *, enable_scheduler=True):
    folder = Path(data_dir or os.environ.get('QINGHE_DATA_DIR', ROOT/'data'))
    database = Path(db_path or os.environ.get('QINGHE_DB', ROOT/'var'/'qinghe.sqlite3'))

    @asynccontextmanager
    async def lifespan(app):
        database.parent.mkdir(parents=True, exist_ok=True)
        service = Service(database, folder)
        service.seed()
        poll = float(os.environ.get('QINGHE_POLL_SECONDS', '2'))
        if not math.isfinite(poll) or poll <= 0:
            raise ValueError('QINGHE_POLL_SECONDS 必须为正数')
        scheduler = Scheduler(database, service, poll)
        app.state.service = service
        app.state.scheduler = scheduler
        if enable_scheduler:
            scheduler.start()
        try:
            yield
        finally:
            scheduler.close()

    app = FastAPI(title='青河流域洪水预报系统', version='2.0.0',
                  description='青河教学流域的入库、起报、签发、预警、回放与调度接口。时间序列采用数据包当地时刻，调度时刻为 Unix 秒。',
                  lifespan=lifespan)
    for exception, status in [(KeyError,404),(ValueError,422)]:
        def handler(request: Request, exc: Exception, code=status):
            message = str(exc.args[0]) if exc.args else str(exc)
            return JSONResponse(status_code=code, content={'detail':message})
        app.add_exception_handler(exception, handler)

    def service(): return app.state.service

    @app.get('/health', tags=['运行状态'], summary='服务健康检查')
    @app.get('/api/health', include_in_schema=False)
    def health():
        return {'status':'ok','version':'2.0.0'}

    @app.get('/api/events', tags=['入库质控'], response_model=list[EventSummary], summary='列出已入库场次')
    def events():
        return service().events()

    @app.post('/api/events/demo', tags=['入库质控'], summary='幂等导入示例场次与初始方案')
    def demo():
        service().seed()
        return {'events':service().events()}

    @app.get('/api/events/{event_id}', tags=['入库质控'], summary='查看场次观测、输入和逐条质控记录')
    def event(event_id: str):
        return service().event_detail(event_id)

    @app.post('/api/events/{event_id}/import', tags=['入库质控'], response_model=EventSummary, summary='入库 CSV 并记录质控结果')
    def ingest(event_id: str, body: ImportCSV):
        if len(event_id)>100 or not event_id.strip():
            raise ValueError('场次名称长度须为1到100字符')
        state = body.state.model_dump() if body.state else sample_state(folder, event_id)
        return service().ingest(event_id, body.csv_text.lstrip('\ufeff'), state, actor=body.actor)

    @app.get('/api/schemes', tags=['参数方案'], response_model=list[PlanVersion], summary='列出参数方案和版本')
    def schemes():
        return service().plans()

    @app.get('/api/schemes/{plan_id}', tags=['参数方案'], response_model=PlanVersion, summary='读取指定版本')
    def scheme(plan_id: int):
        for plan in service().plans():
            if plan['id']==plan_id:
                return plan
        raise KeyError('找不到参数版本')

    @app.post('/api/schemes', tags=['参数方案'], response_model=PlanVersion, summary='保存具名参数方案版本')
    def save_scheme(body: Scheme):
        return service().save_plan(body.name, body.parameters, actor=body.actor)

    @app.post('/api/schemes/{plan_id}/versions', tags=['参数方案'], response_model=PlanVersion, summary='基于已有方案保存新版本')
    def version(plan_id: int, body: Version):
        return service().save_plan(scheme(plan_id)['name'], body.parameters, actor=body.actor)

    @app.post('/api/schemes/{plan_id}/activate', tags=['参数方案'], summary='切换当前版本')
    def activate(plan_id: int, body: Command=Command()):
        return service().activate(plan_id, actor=body.actor)

    @app.delete('/api/schemes/{plan_id}', tags=['参数方案'], summary='归档指定方案版本')
    def delete_scheme(plan_id: int, actor: Nonempty=Query('operator')):
        return service().delete_plan(plan_id, actor=actor)

    @app.post('/api/runs', tags=['预报产品'], response_model=Product, summary='执行预报并生成产品草稿')
    def run(body: Forecast):
        return service().run(**body.model_dump())

    @app.get('/api/runs', tags=['预报产品'], summary='查询历史预报，可按场次及签发状态筛选')
    def runs(event_id: str | None=None,status: str | None=None):
        return [r for r in service().runs() if (not event_id or r['event_id']==event_id)
                and (not status or r['status']==status)]

    @app.get('/api/runs/{run_id}', tags=['预报产品'], response_model=Product, summary='获取过程线、结果及快照')
    def detail(run_id: int):
        return service().detail(run_id)

    @app.post('/api/runs/{run_id}/issue', tags=['预报产品'], response_model=Product, summary='签发预报产品')
    def issue(run_id: int, body: Command=Command()):
        return service().issue(run_id, actor=body.actor)

    @app.post('/api/runs/{run_id}/replay', tags=['留痕回放'], response_model=Replay, summary='从冻结快照重算并比对')
    def replay(run_id: int, body: Command=Command()):
        return service().replay(run_id, actor=body.actor)

    @app.get('/api/alerts', tags=['预警消息'], summary='查询持久化预警消息')
    def alerts():
        return service().notifications()

    @app.post('/api/alerts/{message_id}/read', tags=['预警消息'], summary='确认已读消息')
    def read(message_id: int, body: Command=Command()):
        return service().read_notification(message_id, actor=body.actor)

    @app.get('/api/audit', tags=['留痕回放'], summary='查询操作日志')
    def audit():
        return service().audit()

    @app.get('/api/schedules', tags=['起报调度'], response_model=list[Timer], summary='列出定时起报任务')
    def schedules():
        return app.state.scheduler.list()

    @app.post('/api/schedules', tags=['起报调度'], response_model=Timer, summary='新增周期起报任务')
    def add_schedule(body: Schedule):
        return app.state.scheduler.add(body.model_dump(exclude={'interval_seconds'}),body.interval_seconds)

    @app.delete('/api/schedules/{job_id}', tags=['起报调度'], response_model=Timer, summary='停用周期起报')
    def cancel(job_id: int):
        return app.state.scheduler.cancel(job_id)

    static = ROOT/'app'/'static'
    app.mount('/static', StaticFiles(directory=str(static), check_dir=False), name='static')

    @app.get('/', include_in_schema=False)
    def workbench():
        if not (static/'index.html').is_file():
            raise HTTPException(status_code=503, detail='工作台静态资源缺失')
        return FileResponse(static/'index.html')
    return app


app = create_app()

