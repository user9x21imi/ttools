"""python-telegram 2.0 transport adapter for the native cross-platform tdjson wheel."""
import json,time
import tdjson
class TDJson:
    def __init__(self,library_path=None,verbosity=0):
        tdjson.td_execute(json.dumps({'@type':'setLogVerbosityLevel','new_verbosity_level':verbosity}).encode())
        self.td_json_client=tdjson.td_create_client_id();self.closed=False
    def send(self,query):
        if self.td_json_client is None:raise RuntimeError('TDLib client is stopped')
        tdjson.td_send(self.td_json_client,json.dumps(query,ensure_ascii=False).encode('utf-8'))
    def receive(self):
        if self.td_json_client is None:return None
        deadline=time.monotonic()+1
        while time.monotonic()<deadline:
            result=tdjson.td_receive(max(.01,deadline-time.monotonic()))
            if not result:return None
            value=json.loads(result)
            if value.get('@client_id',self.td_json_client)!=self.td_json_client:continue
            if value.get('@type')=='updateAuthorizationState' and value.get('authorization_state',{}).get('@type')=='authorizationStateClosed':self.closed=True
            return value
        return None
    def td_execute(self,query):
        result=tdjson.td_execute(json.dumps(query,ensure_ascii=False).encode('utf-8'))
        return json.loads(result) if result else None
    def stop(self):
        if self.td_json_client is not None:
            if not self.closed:self.send({'@type':'close'})
            self.td_json_client=None
