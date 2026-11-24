import pytest
from devcore.projects import Registry
from devcore.tasks import TaskQueue

def test_registry(tmp_path):
    r=Registry(tmp_path/'state.db')
    r.add('a',str(tmp_path),'repo')
    assert Registry(r.db).list()[0][0]=='a'
    with pytest.raises(ValueError):
        r.add('b','relative','repo')

def test_queue(tmp_path):
    db=tmp_path/'state.db'
    q=TaskQueue(db)
    t=q.create('a','test')
    assert q.claim('b') is None
    assert q.claim('a')==(t,'test')
    assert TaskQueue(db).running('a')==[(t,'test')]
    with pytest.raises(ValueError):
        q.complete('b',t,'passed')
    with pytest.raises(ValueError):
        q.complete('a',t,'')
    q.complete('a',t,'test passed')
    assert q.running('a')==[]
