import importlib.util
from pathlib import Path
import hashlib
import tempfile
import unittest
s=importlib.util.spec_from_file_location('m',Path(__file__).with_name('check-shadow-migrations.py'))
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Tests(unittest.TestCase):
 def test_local_version_collision_is_rejected(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory)
   for name in ('0014_hybrid.sql','0014_origin.sql'):
    (root/name).write_text('SELECT 1;')
   with self.assertRaisesRegex(ValueError, 'Duplicate local'):
    m.compare([],root)
 def test_inventory(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'0001_a.sql').write_text('SELECT 1;');(p/'0015_b.sql').write_text('SELECT 2;')
   row={'version':1,'success':True,'checksum':hashlib.sha384((p/'0001_a.sql').read_bytes()).hexdigest()}
   self.assertEqual(m.compare([row],p)['pending'],['0015_b.sql'])
   for patch in ({'checksum':'bad'},{'success':False},{'version':99}):
    with self.assertRaises(ValueError):m.compare([dict(row,**patch)],p)
   with self.assertRaises(ValueError):m.compare([row,row],p)
if __name__=='__main__':unittest.main()
