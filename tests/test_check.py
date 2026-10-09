"""The pre-PR command must propagate browser failures and clean up Chrome."""
from pathlib import Path
import os
import select
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from tests import check


class CheckCommand(unittest.TestCase):
    def test_browser_uses_own_port_and_cleans_up_on_success_or_failure(self):
        for fails in (False, True):
            with self.subTest(fails=fails):
                browser = Mock()
                directories = []

                def launch(args, **kwargs):
                    self.assertEqual(kwargs['start_new_session'], os.name == 'posix')
                    profile = Path(next(a.split('=', 1)[1] for a in args if a.startswith('--user-data-dir=')))
                    profile.mkdir()
                    (profile / 'DevToolsActivePort').write_text('43210\n/devtools/browser/test\n')
                    directories.append(profile.parent)
                    return browser

                failure = subprocess.CalledProcessError(1, 'node') if fails else None
                with patch.object(check.subprocess, 'Popen', side_effect=launch), patch.object(check.subprocess, 'run', side_effect=failure) as run, patch.object(check, 'stop_browser') as stop:
                    if fails:
                        with self.assertRaises(subprocess.CalledProcessError):
                            check.run_browser('chrome')
                    else:
                        check.run_browser('chrome')
                    self.assertEqual(run.call_args.kwargs['env']['QUICKDASH_CHROME_PORT'], '43210')
                    self.assertTrue(run.call_args.kwargs['check'])
                stop.assert_called_once_with(browser)
                self.assertFalse(directories[0].exists())

    @unittest.skipUnless(os.name == 'posix', 'POSIX process-group lifecycle')
    def test_cleanup_stops_a_profile_writer_even_after_browser_parent_exits(self):
        for parent_exits in (False, True):
            for ignores_term in (False, True):
                with self.subTest(parent_exits=parent_exits, ignores_term=ignores_term):
                    self.check_profile_writer_cleanup(parent_exits, ignores_term)

    def check_profile_writer_cleanup(self, parent_exits, ignores_term):
        # A child keeps making files, like a lingering Chrome subprocess.
        # Cover both graceful exit and escalation, including an exited parent.
        writer = """
import os, pathlib, signal, sys, time
if sys.argv[2] == 'True':
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
profile = pathlib.Path(sys.argv[1])
profile.mkdir()
print(os.getpid(), flush=True)
i = 0
while True:
    (profile / str(i)).write_text('background write')
    i += 1
    time.sleep(.01)
"""
        launcher = """
import subprocess, sys
child = subprocess.Popen([sys.executable, '-c', *sys.argv[1:4]])
if sys.argv[4] == 'False':
    child.wait()
"""
        with tempfile.TemporaryDirectory() as temporary:
            profile = Path(temporary) / 'Default'
            browser = subprocess.Popen([sys.executable, '-c', launcher, writer, str(profile),
                                        str(ignores_term), str(parent_exits)],
                                       start_new_session=True, stdout=subprocess.PIPE, text=True)
            try:
                self.assertTrue(select.select([browser.stdout], [], [], 10)[0])
                child = int(browser.stdout.readline())
                if parent_exits:
                    browser.wait(timeout=10)
                os.kill(child, 0)
                self.assertTrue(profile.is_dir())
                check.stop_browser(browser, grace=1)
                # EOF proves the writer exited; a zombie may remain until the
                # OS reaps it, so killpg(..., 0) is not a liveness check.
                self.assertTrue(select.select([browser.stdout], [], [], 10)[0])
                self.assertEqual(browser.stdout.read(), '')
                self.assertIsNotNone(browser.returncode)
            finally:
                try:
                    os.killpg(browser.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
                browser.wait(timeout=10)
                self.assertTrue(select.select([browser.stdout], [], [], 10)[0])
                browser.stdout.close()
        self.assertFalse(profile.exists())

    @unittest.skipUnless(os.name == 'posix', 'POSIX process-group lifecycle')
    def test_cleanup_does_not_wait_for_zombies_or_other_process_groups(self):
        browser = Mock(pid=123)
        for result in ('', '123 Z\n124 S\n'):
            with self.subTest(processes=result), patch.object(check.subprocess, 'check_output', return_value=result), patch.object(check.os, 'killpg') as kill:
                check.stop_browser(browser, grace=.1)
                kill.assert_called_once_with(123, signal.SIGTERM)

    @unittest.skipUnless(os.name == 'posix', 'POSIX process-group lifecycle')
    def test_cleanup_fails_if_a_live_process_cannot_be_stopped(self):
        browser = Mock(pid=123)
        with patch.object(check.subprocess, 'check_output', return_value='123 S\n'), patch.object(check.os, 'killpg') as kill:
            with self.assertRaisesRegex(RuntimeError, 'did not exit'):
                check.stop_browser(browser, grace=0)
            self.assertEqual([call.args[1] for call in kill.call_args_list],
                             [signal.SIGTERM, signal.SIGKILL])

    @unittest.skipUnless(os.name == 'posix', 'POSIX process-group lifecycle')
    def test_signal_races_do_not_hide_permission_errors_for_live_processes(self):
        browser = Mock(pid=123)
        for error in (ProcessLookupError, PermissionError):
            with self.subTest(error=error), patch.object(check.subprocess, 'check_output', return_value=''), patch.object(check.os, 'killpg', side_effect=error):
                check.stop_browser(browser)
        with patch.object(check.subprocess, 'check_output', return_value='123 S\n'), patch.object(check.os, 'killpg', side_effect=PermissionError):
            with self.assertRaises(PermissionError):
                check.stop_browser(browser)

    def test_non_posix_cleanup_waits_and_escalates_if_necessary(self):
        for times_out in (False, True):
            with self.subTest(times_out=times_out), patch.object(check.os, 'name', 'nt'):
                browser = Mock()
                if times_out:
                    browser.wait.side_effect = [subprocess.TimeoutExpired('chrome', 10), 0]
                check.stop_browser(browser)
                browser.terminate.assert_called_once()
                self.assertEqual(browser.kill.call_count, int(times_out))
                self.assertEqual(browser.wait.call_count, 1 + int(times_out))

    def test_missing_browser_is_an_error_not_a_skipped_check(self):
        with patch.object(check.os.path, 'isfile', return_value=False):
            with self.assertRaisesRegex(RuntimeError, 'Chrome is required'):
                check.find_chrome()
