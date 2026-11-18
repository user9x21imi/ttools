import os,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from tthings.system_preview import SystemPreview
from tthings.catalog import SYSTEM_TOOLS
class PreviewTests(unittest.TestCase):
    def test_tools_preview_without_journals_or_scans(self):
        with tempfile.TemporaryDirectory() as td,patch.dict(os.environ,{'HOME':td,'XDG_STATE_HOME':td+'/state','XDG_CONFIG_HOME':td+'/config'}):
            preview=SystemPreview()
            try:
                for tool in SYSTEM_TOOLS:
                    for width,height in [(33,16),(60,32),(100,42)]:
                        frame=preview.render(tool.id,width,height)
                        self.assertEqual((frame.w,frame.h),(width,height))
                self.assertFalse((Path(td)/'state').exists())
                self.assertFalse((Path(td)/'config').exists())
            finally:preview.close()
