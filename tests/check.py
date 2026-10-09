"""Run the public pre-PR checks used by CI, including an isolated browser."""
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
NODE_TESTS = [
    'test_data.cjs', 'test_yaml.cjs', 'test_suites.cjs', 'test_warning_policy.cjs',
    'test_components.cjs', 'test_view_links.cjs',
]


def find_chrome():
    candidates = [os.environ.get('CHROME_BIN'),
                  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome']
    candidates += [shutil.which(name) for name in
                   ('google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser')]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    raise RuntimeError('Chrome is required for the public browser checks. Install Chrome or set CHROME_BIN to its executable.')


def stop_browser(browser, grace=10):
    """Stop profile writers before TemporaryDirectory removes their files."""
    if os.name != 'posix':
        browser.terminate()
        try:
            browser.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            browser.kill()
            browser.wait(timeout=grace)
        return

    def running():
        browser.poll()  # Reap the parent, even while children are still exiting.
        # killpg(..., 0) also sees zombies. They cannot write to the profile,
        # and orphaned children must be reaped by the OS, not by this process.
        processes = subprocess.check_output(['ps', '-eo', 'pgid=,stat='], text=True)
        return any(int(group) == browser.pid and not state.startswith('Z')
                   for group, state in (line.split() for line in processes.splitlines()))

    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(browser.pid, sig)
        except ProcessLookupError:
            pass
        except PermissionError:
            # macOS can report EPERM for a group whose last member is exiting.
            # A genuinely live, unsignalable group remains a cleanup failure.
            if running():
                raise
        deadline = time.monotonic() + grace
        while running():
            if time.monotonic() >= deadline:
                break
            time.sleep(.05)
        else:
            browser.wait(timeout=grace)
            return
    raise RuntimeError('Chrome subprocesses did not exit after SIGKILL.')


def run_browser(chrome):
    with tempfile.TemporaryDirectory(prefix='quickdash-check-') as temporary:
        directory = Path(temporary)
        profile = directory / 'profile'
        with (directory / 'chrome.log').open('w+') as log:
            browser = subprocess.Popen([
                chrome, '--headless', '--no-sandbox', '--disable-gpu', '--no-first-run',
                '--no-default-browser-check', '--remote-debugging-port=0',
                '--user-data-dir=' + str(profile), 'about:blank',
            ], stdout=log, stderr=subprocess.STDOUT, start_new_session=os.name == 'posix')
            try:
                active_port = profile / 'DevToolsActivePort'
                deadline = time.monotonic() + 30
                while not active_port.exists():
                    if browser.poll() is not None or time.monotonic() >= deadline:
                        raise RuntimeError('Chrome did not start its debugging endpoint within 30 seconds.')
                    time.sleep(.1)
                port = int(active_port.read_text().splitlines()[0])
                env = dict(os.environ, QUICKDASH_CHROME_PORT=str(port))
                subprocess.run(['node', 'tests/test_public_browser.mjs'], cwd=ROOT, env=env, check=True)
            except Exception:
                log.flush()
                log.seek(0)
                print(log.read(), file=sys.stderr)
                raise
            finally:
                stop_browser(browser)


def main():
    chrome = find_chrome()  # Fail before expensive tests if a prerequisite is missing.
    version = subprocess.check_output(['node', '--version'], text=True).strip()
    if int(version.lstrip('v').split('.')[0]) < 22:
        raise RuntimeError('Node.js 22+ is required for the public browser checks.')
    # Browser tests invoke python3; use this command's Python environment for builds.
    os.environ['PATH'] = str(Path(sys.executable).parent) + os.pathsep + os.environ.get('PATH', '')
    subprocess.run([sys.executable, '-m', 'unittest', 'tests.test_check',
                    'tests.test_data', 'tests.test_engines', 'tests.test_pages_preview'], cwd=ROOT, check=True)
    subprocess.run(['node', '--test'] + ['tests/' + name for name in NODE_TESTS], cwd=ROOT, check=True)
    run_browser(chrome)
    print('All public checks passed, including the browser.')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print('Public checks failed: ' + str(error), file=sys.stderr)
        sys.exit(1)
