"""A newly delivered observation changes only later published estimates."""
import csv
import io
from pathlib import Path

from fastapi.testclient import TestClient

from app.api import create_app

DATA = Path(__file__).resolve().parents[1]/'data'


def test_rolling_observation_delivery_through_http(tmp_path):
    with TestClient(create_app(tmp_path/'obs.db', DATA, enable_scheduler=False)) as client:
        with (DATA/'events/event2.csv').open(encoding='utf-8-sig', newline='') as original:
            records = list(csv.DictReader(original))
        target = 12
        cutoff = records[target]['时间']
        request = {'event_id':'event2','correction':True,'cutoff':cutoff,'actor':'值班员'}
        initial = client.post('/api/runs',json=request).json()
        def update():
            buffer = io.StringIO(newline='')
            writer = csv.DictWriter(buffer,fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)
            saved = client.post('/api/events/event2/import',json={'csv_text':buffer.getvalue(),'actor':'水文站'})
            assert saved.status_code==200, saved.text
            response = client.post('/api/runs',json=request)
            assert response.status_code==200, response.text
            return response.json()

        # Replace the newest available gauge reading, leaving forcing unchanged.
        flow = '实测流量Q(m3/s)'
        records[target][flow] = str(float(records[target][flow])+80)
        revised = update()
        q1 = initial['result']['forecast']
        q2 = revised['result']['forecast']
        assert q1[:target+1]==q2[:target+1]
        assert q2[target+1]>q1[target+1]
        assert revised['result']['raw']==initial['result']['raw']
        assert revised['snapshot_hash']!=initial['snapshot_hash']

        # A reading received beyond the issuance cutoff cannot affect its forecast.
        records[target+2][flow] = str(float(records[target+2][flow])+200)
        later = update()
        assert later['result']['forecast']==q2
        assert client.post(f"/api/runs/{initial['id']}/replay").json()['match']
        assert client.post(f"/api/runs/{revised['id']}/replay").json()['match']

