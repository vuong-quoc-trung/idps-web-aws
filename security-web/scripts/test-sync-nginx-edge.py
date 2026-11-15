#!/usr/bin/env python3
"""Service lifecycle regression tests; no host changes."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('sync', Path(__file__).with_name('sync-nginx-edge.py'))
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)

class LifecycleTests(unittest.TestCase):
    def test_stopped_service_starts(self):
        installer = Mock()
        with patch.object(sync, 'nginx_active', side_effect=[False, True]):
            sync.activate(installer)
        installer.run.assert_called_once_with(['systemctl', 'start', 'nginx'])

    def test_running_service_reloads(self):
        installer = Mock()
        with patch.object(sync, 'nginx_active', return_value=True):
            sync.activate(installer)
        installer.run.assert_called_once_with(['systemctl', 'reload', 'nginx'])

    def test_unchanged_stopped_service_starts(self):
        installer = Mock()
        with patch.object(sync, 'nginx_active', side_effect=[False, True]):
            sync.activate(installer, changed=False)
        installer.run.assert_called_once_with(['systemctl', 'start', 'nginx'])

    def test_unchanged_running_no_reload(self):
        installer = Mock()
        with patch.object(sync, 'nginx_active', return_value=True):
            sync.activate(installer, changed=False)
        installer.run.assert_not_called()

    def test_inactive_after_start_fails(self):
        with patch.object(sync, 'nginx_active', return_value=False):
            with self.assertRaises(RuntimeError):
                sync.activate(Mock())

    def test_invalid_old_config_reports_separate_warning(self):
        installer = Mock()
        installer.run.side_effect = RuntimeError('old listener missing')
        with patch('sys.stderr') as err:
            sync.recover(installer, [], True)
        installer.restore.assert_called_once_with([])
        self.assertIn('ROLLBACK WARNING', str(err.write.call_args_list))
        installer.run.assert_called_once_with(['/usr/sbin/nginx', '-t'])

    def test_rollback_does_not_start_previously_stopped_service(self):
        installer = Mock()
        sync.recover(installer, [], False)
        installer.run.assert_called_once_with(['/usr/sbin/nginx', '-t'])

if __name__ == '__main__':
    unittest.main(verbosity=2)
