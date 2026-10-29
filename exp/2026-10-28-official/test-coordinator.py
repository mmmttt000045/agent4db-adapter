"""A supervisor restart must never silently rerun a paid cell."""
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import threading
import time
import unittest
from unittest.mock import patch
import uuid

spec=importlib.util.spec_from_file_location('coordinator',Path(__file__).with_name('coordinator.py'))
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)


class ExistingCells(unittest.TestCase):
    def setUp(self):
        self.parent=Path(__file__).resolve().parents[2]/'tmp'
        self.parent.mkdir(exist_ok=True)
        self.root=self.parent/('coordinator-fixture-'+uuid.uuid4().hex)
        self.root.mkdir();(self.root/'cell').mkdir()
    def tearDown(self):
        assert self.root.resolve().parent==self.parent.resolve()
        assert self.root.name.startswith('coordinator-fixture-')
        shutil.rmtree(self.root)
    def launch(self,record):
        (self.root/'cell/run.json').write_text(json.dumps(record))
        with patch.object(mod,'OUT',self.root),patch.object(mod.subprocess,'Popen') as start:
            result=mod.launch('cell','none','rel-stack')
            start.assert_not_called()
        self.assertEqual(json.loads((self.root/'cell/run.json').read_text()),record)
        return result
    def test_finished_cell_is_adopted_without_another_run(self):
        self.assertEqual(self.launch({'finished':'fixture'})['status'],'finished')
    def test_failed_attempt_is_preserved_without_another_run(self):
        self.assertEqual(self.launch({'error':'fixture failure'})['status'],'failed')

    def test_freeze_record_is_immutable_on_restart(self):
        record={'candidate':'compact-reuse','frozen_utc':'fixture original time'}
        p=self.root/'selection.json';p.write_text(json.dumps(record))
        before=p.read_bytes()
        with patch.object(mod,'OUT',self.root):
            self.assertEqual(mod.select(),'compact-reuse')
        self.assertEqual(p.read_bytes(),before)

    @unittest.skipIf(sys.platform=='win32','The production file lock uses Linux fcntl')
    def test_fixed_queue_runs_every_cell_once_with_configured_slots(self):
        seen=[];active=peak=0;guard=threading.Lock()
        def launch(name,*args):
            nonlocal active,peak
            with guard:
                active+=1;peak=max(peak,active);seen.append(name)
            time.sleep(.01)
            with guard: active-=1
            return {'name':name,'status':'finished'}
        with patch.object(mod,'OUT',self.root),patch.object(mod,'launch',side_effect=launch),patch.object(mod,'select',return_value='compact-reuse'):
            mod.main()
        expected={'dev-original','dev-compact-reuse'}|{f'{a}-{d}-r1' for a in mod.CONFIG['evaluation']['arms'] for d in mod.CONFIG['evaluation']['datasets']}
        self.assertEqual(set(seen),expected)
        self.assertEqual(len(seen),len(expected))
        self.assertEqual(peak,mod.CONFIG['evaluation']['parallel_cells'])
        self.assertEqual(json.loads((self.root/'status.json').read_text())['status'],'completed')


if __name__=='__main__': unittest.main()
