import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "frontend" / "js" / "formal-workflow.js"


def _node_binary():
    bundled = (
        Path.home()
        / ".cache"
        / "codex-runtimes"
        / "codex-primary-runtime"
        / "dependencies"
        / "node"
        / "bin"
        / "node"
    )
    return str(bundled) if bundled.exists() else shutil.which("node")


def _run_node(script):
    node = _node_binary()
    if not node:
        pytest.skip("node is not available")
    completed = subprocess.run(
        [node, "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_formal_module_uses_crypto_bounded_polling_and_allowlisted_storage():
    source = MODULE.read_text(encoding="utf-8")

    assert "cryptoApi.randomUUID" in source
    assert "cryptoApi.getRandomValues" in source
    assert "Math.random" not in source
    assert "MAX_NETWORK_FAILURES = 3" in source
    assert "MIN_POLL_INTERVAL_SECONDS = 1" in source
    assert "MAX_POLL_INTERVAL_SECONDS = 10" in source
    assert 'const STORAGE_KEY = "lexibridge.formalAlignment.activeRun.v1"' in source
    for forbidden in (
        "auth_token",
        "lease_token",
        "execution_key",
        "safe_input_fingerprint",
        "event_identity",
        "raw_output",
        "evidence_body",
    ):
        assert forbidden not in source


def test_start_reuses_pending_key_stops_at_terminal_and_loads_first_page():
    module_path = json.dumps(str(MODULE))
    result = _run_node(
        f"""
        const formal = require({module_path});
        const values = new Map();
        const storage = {{
          getItem: key => values.has(key) ? values.get(key) : null,
          setItem: (key, value) => values.set(key, value),
          removeItem: key => values.delete(key)
        }};
        const calls = [];
        const responses = [
          {{status: 202, headers: {{Location: '/api/document-alignment-runs/run-1', 'Retry-After': '2', 'X-Request-ID': 'request-1'}}, body: {{data: {{run_uid: 'run-1', status: 'queued', status_url: '/api/document-alignment-runs/run-1', items_url: '/api/document-alignment-runs/run-1/items'}}}}}},
          {{status: 200, headers: {{}}, body: {{data: {{run_uid: 'run-1', status: 'ready_for_review', progress_percent: 100, total_items: 2}}}}}},
          {{status: 200, headers: {{}}, body: {{data: {{items: [{{item_uid: 'item-1'}}], pagination: {{page: 1, page_size: 20, total_items: 1, total_pages: 1, has_next: false, has_previous: false}}}}}}}}
        ];
        const fetchImpl = async (url, options) => {{
          calls.push({{url, method: options.method || 'GET', key: options.headers['Idempotency-Key'] || ''}});
          const next = responses.shift();
          return {{
            ok: next.status >= 200 && next.status < 300,
            status: next.status,
            statusText: 'test',
            headers: {{get: name => next.headers[name] || null}},
            json: async () => next.body
          }};
        }};
        const controller = formal.createController({{
          fetchImpl,
          storage,
          cryptoApi: {{randomUUID: () => '11111111-1111-4111-8111-111111111111'}},
          getToken: () => 'teacher-token',
          sleep: async () => {{}},
          nowIso: () => '2026-07-20T00:00:00Z',
          nowMs: (() => {{ let value = 0; return () => value++; }})()
        }});
        Promise.all([controller.start('source-1'), controller.start('source-1')]).then(() => {{
          const persisted = JSON.parse(storage.getItem(formal.STORAGE_KEY));
          console.log(JSON.stringify({{calls, persisted, snapshot: controller.getState()}}));
        }}).catch(error => {{ console.error(error); process.exit(1); }});
        """
    )

    assert [call["method"] for call in result["calls"]] == ["POST", "GET", "GET"]
    assert result["calls"][0]["key"] == "ui-formal-alignment-v1-11111111-1111-4111-8111-111111111111"
    assert result["persisted"] == {
        "source_uid": "source-1",
        "idempotency_key": "ui-formal-alignment-v1-11111111-1111-4111-8111-111111111111",
        "run_uid": "run-1",
        "location": "/api/document-alignment-runs/run-1",
        "items_url": "/api/document-alignment-runs/run-1/items",
        "started_at": "2026-07-20T00:00:00Z",
        "last_status": "ready_for_review",
        "poll_interval_seconds": 2,
        "page": 1,
        "page_size": 20,
    }
    assert result["snapshot"]["mode"] == "terminal"
    assert result["snapshot"]["items"][0]["item_uid"] == "item-1"


def test_resume_gets_existing_run_without_posting_and_clears_forbidden_state():
    module_path = json.dumps(str(MODULE))
    result = _run_node(
        f"""
        const formal = require({module_path});
        const persisted = {{source_uid:'source-2', idempotency_key:'ui-formal-alignment-v1-key', run_uid:'run-2', location:'/api/document-alignment-runs/run-2', items_url:'/api/document-alignment-runs/run-2/items', started_at:'2026-07-20T00:00:00Z', last_status:'processing', poll_interval_seconds:2, page:1, page_size:20, token:'must-drop'}};
        const values = new Map([[formal.STORAGE_KEY, JSON.stringify(persisted)]]);
        const storage = {{getItem:key=>values.get(key)||null,setItem:(key,value)=>values.set(key,value),removeItem:key=>values.delete(key)}};
        const calls = [];
        const responses = [
          {{data: {{run_uid:'run-2', status:'ready_for_review', progress_percent:100}}}},
          {{data: {{items:[], pagination:{{page:1,page_size:20,total_items:0,total_pages:0,has_next:false,has_previous:false}}}}}}
        ];
        const fetchImpl = async (url, options) => {{
          calls.push({{url,method:options.method||'GET'}});
          return {{ok:true,status:200,statusText:'ok',headers:{{get:()=>null}},json:async()=>responses.shift()}};
        }};
        const controller = formal.createController({{fetchImpl,storage,getToken:()=> 'teacher-token',sleep:async()=>{{}},nowMs:()=>0}});
        controller.resume().then(() => console.log(JSON.stringify({{calls,persisted:JSON.parse(storage.getItem(formal.STORAGE_KEY))}}))).catch(error => {{console.error(error);process.exit(1);}});
        """
    )

    assert [call["method"] for call in result["calls"]] == ["GET", "GET"]
    assert all(call["url"].endswith(("/run-2", "/run-2/items?page=1&page_size=20")) for call in result["calls"])
    assert "token" not in result["persisted"]


def test_three_network_failures_preserve_active_run_as_connection_error():
    module_path = json.dumps(str(MODULE))
    result = _run_node(
        f"""
        const formal = require({module_path});
        const values = new Map([[formal.STORAGE_KEY, JSON.stringify({{source_uid:'source-3',idempotency_key:'key',run_uid:'run-3',location:'/api/document-alignment-runs/run-3',items_url:'/api/document-alignment-runs/run-3/items',started_at:'2026-07-20T00:00:00Z',last_status:'processing',poll_interval_seconds:2,page:1,page_size:20}})]]);
        const storage = {{getItem:key=>values.get(key)||null,setItem:(key,value)=>values.set(key,value),removeItem:key=>values.delete(key)}};
        let calls = 0;
        const controller = formal.createController({{fetchImpl:async()=>{{calls++;throw new TypeError('offline');}},storage,getToken:()=> 'teacher-token',sleep:async()=>{{}},nowMs:(()=>{{let n=0;return()=>n++;}})()}});
        controller.resume().then(() => console.log(JSON.stringify({{calls,state:controller.getState(),stored:JSON.parse(storage.getItem(formal.STORAGE_KEY))}}))).catch(error => {{console.error(error);process.exit(1);}});
        """
    )

    assert result["calls"] == 3
    assert result["state"]["mode"] == "connection_error"
    assert result["state"]["last_status"] == "processing"
    assert result["stored"]["run_uid"] == "run-3"


def test_ambiguous_start_retry_reuses_the_same_crypto_key():
    module_path = json.dumps(str(MODULE))
    result = _run_node(
        f"""
        const formal = require({module_path});
        const values = new Map();
        const storage = {{getItem:key=>values.get(key)||null,setItem:(key,value)=>values.set(key,value),removeItem:key=>values.delete(key)}};
        const keys = [];
        let call = 0;
        const fetchImpl = async (url, options) => {{
          call++;
          if ((options.method || 'GET') === 'POST') keys.push(options.headers['Idempotency-Key']);
          if (call === 1) throw new TypeError('response lost');
          const bodies = [
            {{data:{{run_uid:'run-4',status:'ready_for_review',status_url:'/api/document-alignment-runs/run-4',items_url:'/api/document-alignment-runs/run-4/items'}}}},
            {{data:{{items:[],pagination:{{page:1,page_size:20,total_items:0,total_pages:0,has_next:false,has_previous:false}}}}}}
          ];
          const body = bodies[call - 2];
          return {{ok:true,status:call===2?202:200,statusText:'ok',headers:{{get:name=>name==='Location'?'/api/document-alignment-runs/run-4':name==='Retry-After'?'2':null}},json:async()=>body}};
        }};
        const controller = formal.createController({{fetchImpl,storage,cryptoApi:{{randomUUID:()=> '44444444-4444-4444-8444-444444444444'}},getToken:()=> 'teacher-token',sleep:async()=>{{}},nowMs:()=>0}});
        controller.start('source-4').then(() => controller.resumeSubmission()).then(() => console.log(JSON.stringify({{keys,state:controller.getState()}}))).catch(error=>{{console.error(error);process.exit(1);}});
        """
    )

    assert result["keys"] == [
        "ui-formal-alignment-v1-44444444-4444-4444-8444-444444444444",
        "ui-formal-alignment-v1-44444444-4444-4444-8444-444444444444",
    ]
    assert result["state"]["mode"] == "terminal"


def test_forbidden_resume_clears_active_storage():
    module_path = json.dumps(str(MODULE))
    result = _run_node(
        f"""
        const formal = require({module_path});
        const values = new Map([[formal.STORAGE_KEY, JSON.stringify({{source_uid:'source-5',idempotency_key:'key',run_uid:'run-5',location:'/api/document-alignment-runs/run-5',items_url:'/api/document-alignment-runs/run-5/items',started_at:'',last_status:'processing',poll_interval_seconds:2,page:1,page_size:20}})]]);
        const storage = {{getItem:key=>values.get(key)||null,setItem:(key,value)=>values.set(key,value),removeItem:key=>values.delete(key)}};
        const controller = formal.createController({{fetchImpl:async()=>({{ok:false,status:403,statusText:'forbidden',headers:{{get:()=>null}},json:async()=>({{error_code:'PERMISSION_DENIED',message:'Not allowed'}})}}),storage,getToken:()=> 'teacher-token',sleep:async()=>{{}},nowMs:()=>0}});
        controller.resume().then(() => console.log(JSON.stringify({{stored:storage.getItem(formal.STORAGE_KEY),state:controller.getState()}}))).catch(error=>{{console.error(error);process.exit(1);}});
        """
    )

    assert result["stored"] is None
    assert result["state"]["mode"] == "forbidden"
    assert result["state"]["run_uid"] == ""
