"""Closed application-control policy. Not a general local-RPC or shell relay."""
import ipaddress
import os
import stat
import time
import uuid

class PeerError(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code, self.status = code, status

def private_address(address, internet=False):
    try:
        parsed=ipaddress.ip_address(address)
    except ValueError:
        return False
    if parsed.version!=4: return False
    allowed=('127.0.0.0/8','10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')
    if internet: allowed+=('100.64.0.0/10',)
    return any(parsed in ipaddress.ip_network(network) for network in allowed) and not parsed.is_unspecified

def private_folder(path):
    path=os.path.abspath(os.path.expanduser(path))
    if os.path.realpath(path)!=path: raise PeerError('unsafe_state','State directory must not contain symlinks')
    os.makedirs(path,mode=0o700,exist_ok=True)
    info=os.lstat(path)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid(): raise PeerError('unsafe_state','State directory is not owned by this user')
    os.chmod(path,0o700)
    return path

def identifier(value):
    if not isinstance(value,str): raise PeerError('invalid_target','A UUID target is required')
    try: return str(uuid.UUID(value)).upper()
    except ValueError: raise PeerError('invalid_target','A UUID target is required')

def fields(value,allowed):
    if not isinstance(value,dict) or set(value)-set(allowed): raise PeerError('invalid_fields','Unsupported request fields')

def text(value,maximum=256):
    if not isinstance(value,str) or not value.strip() or len(value.encode())>maximum or '\0' in value:
        raise PeerError('invalid_text','Text is missing or too long')
    return value

class OwnerBroker:
    def __init__(self,socket_path):
        # Reuse the proven local socket admission/size/deadline implementation.
        import importlib.util, pathlib
        path=pathlib.Path(__file__).resolve().parents[1]/'cmux-mobile-menu.py'
        spec=importlib.util.spec_from_file_location('cmux_peer_local_rpc',path)
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        self.local=module.NativeSessionMenu(socket_path,expires_at=float("inf"))
        self.cache=None; self.cached_at=0
    def catalog(self,fresh=False):
        if fresh or self.cache is None or time.monotonic()-self.cached_at>0.35:
            self.cache=self.local.rpc('mobile.workspace.list',{})
            self.cached_at=time.monotonic()
        # Full app grant includes future windows; no captured-session allowlist.
        return dict(self.cache,workspaces=[w for w in self.cache.get('workspaces',[]) if not w.get('peer_projection',False)])
    def target(self,request,surface=False):
        workspace=identifier(request.get('workspace_id'))
        item=next((w for w in self.catalog(True).get('workspaces',[]) if w.get('id','').upper()==workspace),None)
        if item is None: raise PeerError('target_closed','Workspace is no longer available',404)
        if surface:
            sid=identifier(request.get('surface_id'))
            if not any(t.get('id','').upper()==sid for t in item.get('terminals',[])):
                raise PeerError('invalid_target','Terminal does not belong to this workspace',404)
            return {'workspace_id':workspace,'surface_id':sid}
        return {'workspace_id':workspace}
    def replay(self,request):
        fields(request,{'workspace_id','surface_id'})
        return self.local.rpc('mobile.terminal.replay',dict(self.target(request,True),anchor='screen',max_scrollback_rows=0))
    def mutation_rpc(self,method,params,admission=None):
        if admission: return self.local.rpc(method,params,admission=admission)
        return self.local.rpc(method,params)
    def input(self,request,admission=None):
        fields(request,{'workspace_id','surface_id','text','expected_render_epoch'})
        params=self.target(request,True)
        epoch=request.get('expected_render_epoch')
        if self.catalog().get('peer_input_epoch_guard') is not True or not isinstance(epoch,str) or not epoch:
            raise PeerError('producer_guard_required','Update the host app before controlling its terminals',403)
        value=request.get('text')
        if not isinstance(value,str) or not value or len(value.encode())>8192 or '\0' in value:
            raise PeerError('invalid_input','Invalid terminal input')
        return self.mutation_rpc('mobile.terminal.input',dict(params,text=value,expected_render_epoch=epoch),admission)
    def action(self,request,admission=None):
        fields(request,{'action','workspace_id','surface_id','title','direction','confirmed'})
        action=request.get('action')
        if action=='workspace.new':
            fields(request,{'action','title'})
            result=self.mutation_rpc('workspace.create',{'title':text(request.get('title','Remote workspace')),'focus':False,'eager_load_terminal':True},admission)
            # This upstream defers new PTYs until their first visit. Creating a
            # remote session is an explicit app action, so visit it on its owner.
            if result.get('created_workspace_id'):
                self.mutation_rpc('workspace.select',{'workspace_id':identifier(result['created_workspace_id'])},admission)
            return result
        if action=='workspace.rename':
            fields(request,{'action','workspace_id','title'})
            return self.mutation_rpc('workspace.rename',dict(self.target(request),title=text(request.get('title'))),admission)
        if action=='workspace.close':
            fields(request,{'action','workspace_id','confirmed'})
            if request.get('confirmed') is not True: raise PeerError('confirmation_required','Closing a workspace needs explicit confirmation')
            return self.mutation_rpc('workspace.close',dict(self.target(request),force=True),admission)
        if action=='terminal.split':
            fields(request,{'action','workspace_id','surface_id','direction'})
            direction=request.get('direction')
            if direction not in ('left','right','up','down'): raise PeerError('invalid_direction','Invalid split direction')
            return self.mutation_rpc('surface.split',dict(self.target(request,True),direction=direction,focus=False),admission)
        if action=='workspace.select':
            fields(request,{'action','workspace_id'})
            return self.mutation_rpc('workspace.select',self.target(request),admission)
        raise PeerError('denied_action','This application action is not exported',403)

    def files(self,request):
        import base64
        fields(request,{'workspace_id','surface_id','path','operation','show_hidden'})
        target=self.target(request,True)
        workspace=next(w for w in self.catalog(True)['workspaces'] if w['id'].upper()==target['workspace_id'])
        terminal=next(t for t in workspace['terminals'] if t['id'].upper()==target['surface_id'])
        root=terminal.get('current_directory') or workspace.get('current_directory')
        path=request.get('path')
        if not isinstance(root,str) or not root.startswith('/') or not isinstance(path,str) or '\0' in path:
            raise PeerError('invalid_path','No source directory is available')
        root=os.path.realpath(root); path=os.path.abspath(path)
        if os.path.commonpath([root,path])!=root: raise PeerError('path_outside_workspace','Path is outside the terminal directory',403)
        relative=os.path.relpath(path,root)
        # Anchor every component to a descriptor. Never follow a swapped ancestor or leaf symlink.
        fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            components=[] if relative=='.' else relative.split(os.sep)
            for index,component in enumerate(components):
                flags=os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK
                if index<len(components)-1 or request.get('operation')=='list': flags|=os.O_DIRECTORY
                next_fd=os.open(component,flags,dir_fd=fd)
                os.close(fd); fd=next_fd
            return self._files_at_descriptor(fd,path,request)
        except OSError:
            raise PeerError('unsafe_path','The path is unavailable or contains a symlink',403)
        finally: os.close(fd)

    def _files_at_descriptor(self,fd,path,request):
        import base64
        operation=request.get('operation')
        if operation=='list':
            entries=[]
            with os.scandir(fd) as listing:
                for entry in listing:
                    if not request.get('show_hidden',True) and entry.name.startswith('.'): continue
                    if len(entries)>=4096: raise PeerError('directory_limit','Directory is too large for this first version',413)
                    entries.append({'name':entry.name,'path':os.path.join(path,entry.name),'is_directory':entry.is_dir(follow_symlinks=False)})
            return {'entries':entries}
        if operation=='read':
            info=os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size>2*1024*1024: raise PeerError('file_limit','Only files up to 2 MiB are supported',413)
            with os.fdopen(fd,'rb',closefd=False) as handle: data=handle.read(2*1024*1024+1)
            if len(data)>2*1024*1024: raise PeerError('file_limit','File is too large',413)
            return {'data_b64':base64.b64encode(data).decode()}
        raise PeerError('denied_operation','Filesystem writes are not exported',403)
