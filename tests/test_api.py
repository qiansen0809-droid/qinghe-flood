"""Exercise the public HTTP routes with a real temporary SQLite database."""
from pathlib import Path
import time

from fastapi.testclient import TestClient
import pytest

from app.api import create_app

DATA = Path(__file__).resolve().parents[1]/'data'


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path/'app.db', DATA, enable_scheduler=False)) as http:
        yield http


def test_full_issue_and_replay(client):
    assert client.get('/health').json()['status']=='ok'
    assert len(client.get('/api/events').json())==4
    result = client.post('/api/runs', json={'event_id':'event2','ensemble':True,'correction':True})
    assert result.status_code==200, result.text
    product = result.json()
    rid = product['id']
    assert product['status']=='draft'
    assert len(product['result']['members'])==15
    assert len(product['result']['forecast'])==40
    assert client.post(f'/api/runs/{rid}/issue', json={'actor':'forecaster'}).json()['issued_by']=='forecaster'
    alert = client.get('/api/alerts').json()[0]
    assert alert['run_id']==rid
    assert client.post(f"/api/alerts/{alert['id']}/read").json()['read_at']
    assert client.post(f'/api/runs/{rid}/replay').json()['match'] is True
    assert client.get('/api/runs',params={'status':'issued','event_id':'event2'}).json()[0]['id']==rid
    assert {row['action'] for row in client.get('/api/audit').json()} >= {'issue','replay'}


def test_version_selection_is_pinned(client):
    base = client.get('/api/schemes').json()[0]
    new = client.post('/api/schemes',json={'name':'comparison','parameters':base['parameters']}).json()
    amended = dict(new['parameters'], K=0.8)
    latest = client.post(f"/api/schemes/{new['id']}/versions", json={'parameters':amended}).json()
    assert latest['version']==2 and latest['id']!=new['id']
    assert client.post(f"/api/schemes/{latest['id']}/activate").json()['active']
    product = client.post('/api/runs',json={'event_id':'event1'}).json()
    assert product['plan_id']==latest['id']
    assert client.delete(f"/api/schemes/{new['id']}").status_code==200
    assert client.post(f"/api/runs/{product['id']}/replay").json()['match']


def test_import_records_missing_values_and_blocks_invalid_forcing(client):
    event = client.get('/api/events/event1').json()
    text = (DATA/'events/event1.csv').read_text(encoding='utf-8-sig')
    lines = text.splitlines()
    fields = lines[1].split(',')
    fields[1]='-1'
    lines[1]=','.join(fields)
    result=client.post('/api/events/custom/import',json={'csv_text':'\n'.join(lines),'state':event['state']})
    assert result.status_code==200
    assert result.json()['quality']=='blocked'
    assert client.get('/api/events/custom').json()['issues'][0]['row']==2
    assert client.post('/api/runs',json={'event_id':'custom'}).status_code==422


def test_periodic_dispatch_survives_restart_and_can_be_cancelled(tmp_path):
    database = tmp_path/'persist.db'
    with TestClient(create_app(database, DATA, enable_scheduler=False)) as first:
        schedule = first.post('/api/schedules',json={'event_id':'event4','interval_seconds':60}).json()
        assert first.app.state.scheduler.tick(schedule['next_run_at'] - .1)==[]
    with TestClient(create_app(database, DATA, enable_scheduler=False)) as second:
        outcomes = second.app.state.scheduler.tick(schedule['next_run_at'] + .1)
        assert len(outcomes)==1 and outcomes[0]['error'] is None
        assert second.app.state.scheduler.tick(schedule['next_run_at'] + 1)==[]
        product = second.get(f"/api/runs/{outcomes[0]['run_id']}").json()
        assert product['event_id']=='event4' and product['status']=='draft'
        assert second.delete(f"/api/schedules/{schedule['id']}").json()['active'] is False
        assert second.app.state.scheduler.tick(schedule['next_run_at']+200)==[]


def test_actual_timer_creates_forecast(tmp_path, monkeypatch):
    monkeypatch.setenv('QINGHE_POLL_SECONDS','0.03')
    with TestClient(create_app(tmp_path/'timer.db',DATA)) as http:
        job = http.post('/api/schedules',json={'event_id':'event1','interval_seconds':1}).json()
        deadline = time.monotonic()+8
        while time.monotonic()<deadline:
            rows=http.get('/api/schedules').json()
            if rows[0]['last_run_id']:
                break
            time.sleep(.05)
        assert rows[0]['last_run_id']
        assert http.delete(f"/api/schedules/{job['id']}").status_code==200


def test_api_errors_are_machine_readable(client):
    assert client.get('/api/runs/9999').status_code==404
    assert client.post('/api/runs',json={'event_id':'event1','ensemble':True}).status_code==422
    assert client.post('/api/schedules',json={'event_id':'event1','interval_seconds':0}).status_code==422
    assert client.post('/api/events/new/import',json={'csv_text':'x'}).status_code==422
    assert client.get('/openapi.json').json()['info']['version']=='2.0.0'

