#!/usr/bin/env python3
"""Two isolated app instances, over the Mac's actual LAN interface, with disposable PTYs."""
import argparse
import importlib.util
import json
import pathlib
import secrets
import socket
import time
import uuid

parser=argparse.ArgumentParser()
parser.add_argument('--host-socket',required=True)
parser.add_argument('--client-socket',required=True)
parser.add_argument('--address',required=True)
parser.add_argument('--output',required=True,type=pathlib.Path)
args=parser.parse_args()

def rpc(path,method,params=None):
    with socket.socket(socket.AF_UNIX) as stream:
        stream.settimeout(15); stream.connect(path)
        stream.sendall((json.dumps({'id':str(uuid.uuid4()),'method':method,'params':params or {}})+'\n').encode())
        data=b''
        while b'\n' not in data:
            chunk=stream.recv(65536)
            if not chunk or len(data)>4*1024*1024: raise AssertionError('No bounded RPC response')
            data+=chunk
        line=data.split(b'\n')[0]
        if not line.startswith(b'{'):
            raise AssertionError('Run this test from a local terminal inside the client app; its socket correctly rejects unrelated processes')
        result=json.loads(line)
        if not result.get('ok'): raise AssertionError(result.get('error',{}).get('code','rpc_failed'))
        return result['result']
def host(method,params=None): return rpc(args.host_socket,method,params)
def client(method,params=None): return rpc(args.client_socket,method,params)
def until(check,seconds=30):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        result=check()
        if result: return result
        time.sleep(.3)
    raise AssertionError('Native condition not satisfied')
def rows(call): return call('mobile.workspace.list')['workspaces']
def title_matches(workspace,title):
    value=workspace['title']
    return value==title or value.startswith(title+' · ') or value.endswith(' · '+title)
def find(call,title): return next((w for w in rows(call) if title_matches(w,title)),None)
def replay(call,w):
    return call('mobile.terminal.replay',{'workspace_id':w['id'],'surface_id':w['terminals'][0]['id'],'anchor':'screen','max_scrollback_rows':0})
def input_to(call,w,value):
    return call('mobile.terminal.input',{'workspace_id':w['id'],'surface_id':w['terminals'][0]['id'],'text':value})

run=secrets.token_hex(4)
titles=['LAN '+run+' · '+str(n).zfill(2) for n in range(1,7)]
report={'network':'LAN IPv4 '+args.address,'physical_macs':1,'isolated_native_apps':2,'checks':[]}
host_ids=[]
try:
    host('developer.peer.stop')
    # Each fixture is newly created. Never send text to an existing user's agent.
    for title in titles:
        host('workspace.create',{'title':title,'working_directory':str(pathlib.Path(__file__).resolve().parents[1]),'focus':False})
        workspace=until(lambda:find(host,title))
        host_ids.append(workspace['id'])
        # Visiting starts the default shell in this upstream's deferred workspace model.
        host('workspace.select',{'workspace_id':workspace['id']})
        until(lambda:find(host,title)['terminals'][0]['is_ready'])
        input_to(host,workspace,"clear; printf '\\033[38;5;110mMac origen · misma PTY\\033[0m\\n'\r")
    host('developer.peer.share',{'address':args.address,'port':0})
    status=until(lambda:host('developer.peer.status') if host('developer.peer.status').get('invitation') else None)
    invitation=status['invitation']
    # Pairing secret stays inside this process and private app pipes; never print or save it.
    client('developer.peer.connect',{'invitation':invitation})
    remote=until(lambda:[w for w in rows(client) if w.get('peer_projection') and any(title_matches(w,t) for t in titles)]
        if sum(w.get('peer_projection',False) and any(title_matches(w,t) for t in titles) for w in rows(client))==6 else None)
    host_id=until(lambda:client('developer.peer.status').get('clients'))[0]
    report['checks'].append('Native pairing and six existing owner PTYs appear alongside local workspaces')
    local=next(w for w in rows(client) if not w.get('peer_projection'))
    client('workspace.rename',{'workspace_id':local['id'],'title':'Este Mac · trabajo local'})
    target=find(client,titles[0]); owner=find(host,titles[0])
    client('workspace.select',{'workspace_id':target['id']})
    time.sleep(1)
    marker='REMOTE_INPUT_'+run
    input_to(client,target,"printf '"+marker+"\\n'\r")
    until(lambda:marker in json.dumps(replay(host,owner),ensure_ascii=False))
    report['checks'].append('Input through client Ghostty arrives in the original owner PTY')
    marker2='OWNER_INPUT_'+run
    input_to(host,owner,"printf '"+marker2+"\\n'\r")
    until(lambda:marker2 in json.dumps(replay(client,target),ensure_ascii=False))
    report['checks'].append('Owner input is visible in the native remote mirror')
    root=pathlib.Path(__file__).resolve().parents[1]
    directory=str(root/'Sources/LocalPeers')
    input_to(host,owner,"cd '"+directory+"'\r")
    until(lambda:find(host,titles[0])['terminals'][0].get('current_directory')==directory)
    until(lambda:find(client,titles[0])['terminals'][0].get('current_directory')==directory)
    input_to(host,owner,"cd '"+str(root)+"'\r")
    until(lambda:find(client,titles[0])['terminals'][0].get('current_directory')==str(root))
    report['checks'].append('Remote CWD metadata follows the owner and retains remote filesystem authority')
    second=find(client,titles[1]); second_owner=find(host,titles[1])
    client('workspace.select',{'workspace_id':second['id']})
    time.sleep(2)
    second_marker='REVEALED_SESSION_'+run
    input_to(client,second,"printf '"+second_marker+"\\n'\r")
    until(lambda:second_marker in json.dumps(replay(host,second_owner)))
    until(lambda:second_marker in json.dumps(replay(client,second)))
    client('workspace.select',{'workspace_id':target['id']})
    report['checks'].append('A previously hidden session becomes interactive when selected, without polling hidden views')
    started=time.monotonic()
    client('surface.split',{'workspace_id':target['id'],'surface_id':target['terminals'][0]['id'],'direction':'right','focus':False})
    until(lambda:len(find(host,titles[0])['terminals'])==2)
    until(lambda:len(find(client,titles[0])['terminals'])==2)
    report['split_observed_seconds']=round(time.monotonic()-started,3)
    report['checks'].append('Native split routes to the owner and projects its new terminal')
    # All app actions must execute in the owner, not in the client.
    created_title='Created remotely '+run
    client('developer.peer.action',{'host_id':host_id,'action':{'action':'workspace.new','title':created_title}})
    created=until(lambda:find(host,created_title))
    until(lambda:find(client,created_title))
    renamed='Renamed remotely '+run
    client('developer.peer.action',{'host_id':host_id,'action':{'action':'workspace.rename','workspace_id':created['id'],'title':renamed}})
    until(lambda:find(host,renamed)); until(lambda:find(client,renamed))
    client('developer.peer.action',{'host_id':host_id,'action':{'action':'workspace.close','workspace_id':created['id'],'confirmed':True}})
    until(lambda:not find(host,renamed)); until(lambda:not find(client,renamed))
    report['checks'].append('Remote create, rename and confirmed close control the original app')
    # Forbidden launch override cannot silently spawn a local shell in a peer workspace.
    try:
        client('surface.split',{'workspace_id':target['id'],'surface_id':target['terminals'][0]['id'],
            'direction':'right','initial_command':'printf DO_NOT_RUN'})
    except AssertionError: report['checks'].append('Local spawn override denied in a remote projection')
    else: raise AssertionError('Remote override was admitted')
    before={w['id'] for w in rows(host)}
    client('developer.peer.disconnect',{'host_id':host_id,'forget':True})
    until(lambda:not any(w.get('peer_projection') for w in rows(client)))
    assert before=={w['id'] for w in rows(host)},'Disconnect closed owner sessions'
    input_to(host,owner,"printf 'OWNER_STILL_ALIVE\\n'\r")
    until(lambda:'OWNER_STILL_ALIVE' in json.dumps(replay(host,owner)))
    report['checks'].append('Disconnect preserves all owner workspaces and the original PTY remains interactive')
    # Reconnect for the visual demo; only the same private, isolated app receives this grant.
    host('developer.peer.stop')
    host('developer.peer.share',{'address':args.address,'port':0})
    status=until(lambda:host('developer.peer.status') if host('developer.peer.status').get('invitation') else None)
    client('developer.peer.connect',{'invitation':status['invitation']})
    until(lambda:find(client,titles[0]))
    client('workspace.select',{'workspace_id':find(client,titles[0])['id']})
    report['checks'].append('New invitation reconnects to the same original sessions')
    # Re-pairing a live host replaces all old transport bindings, without closing any PTY.
    host('developer.peer.share',{'address':args.address,'port':0})
    fresh=until(lambda:host('developer.peer.status') if host('developer.peer.status').get('invitation') else None)
    client('developer.peer.connect',{'invitation':fresh['invitation']})
    time.sleep(2)
    target=until(lambda:find(client,titles[0]))
    client('workspace.select',{'workspace_id':target['id']})
    marker3='REPAIRED_INPUT_'+run
    # The newly projected second tab can be selected by Bonsplit. Focus the
    # specific original terminal and await its real frame before typing.
    client('surface.focus',{'workspace_id':target['id'],'surface_id':target['terminals'][0]['id']})
    until(lambda:'OWNER_STILL_ALIVE' in json.dumps(replay(client,target)))
    input_to(client,target,"printf '"+marker3+"\\n'\r")
    until(lambda:marker3 in json.dumps(replay(host,owner)))
    report['checks'].append('Re-pairing an already connected host replaces stale credentials and preserves its PTYs')
    report['fixture_workspace_ids']=host_ids
    report['fixture_titles']=titles
    report['status']='passed'
finally:
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('fixture_workspace_ids',)},ensure_ascii=False,indent=2))
