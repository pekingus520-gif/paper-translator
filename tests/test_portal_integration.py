"""Exercise real Qt D-Bus marshalling on a private bus, no desktop permission UI."""
import os
from pathlib import Path
import shutil
import subprocess
import uuid

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtDBus import QDBusConnection

from paper_translator.capture import PortalCapture


SERVICE = r'''
import sys
from gi.repository import Gio, GLib
uri = sys.argv[1]
connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
xml = '<node><interface name="org.freedesktop.portal.Screenshot"><method name="Screenshot"><arg type="s" direction="in"/><arg type="a{sv}" direction="in"/><arg type="o" direction="out"/></method></interface></node>'
info = Gio.DBusNodeInfo.new_for_xml(xml)
def call(conn, sender, path, interface, method, parameters, invocation):
    parent, options = parameters.unpack()
    assert options['interactive'] is True
    token = options['handle_token']
    request = '/org/freedesktop/portal/desktop/request/' + sender[1:].replace('.', '_') + '/' + token
    invocation.return_value(GLib.Variant('(o)', (request,)))
    def respond():
        conn.emit_signal(sender, request, 'org.freedesktop.portal.Request', 'Response',
                         GLib.Variant('(ua{sv})', (0, {'uri': GLib.Variant('s', uri)})))
        return False
    GLib.timeout_add(50, respond)
connection.register_object('/org/freedesktop/portal/desktop', info.interfaces[0], call, None, None)
def ready(*args):
    print('READY', flush=True)
Gio.bus_own_name_on_connection(connection, 'org.freedesktop.portal.Desktop', Gio.BusNameOwnerFlags.NONE, ready, None)
GLib.MainLoop().run()
'''


def test_real_portal_call_receives_uri(qapp, spin, tmp_path):
    if os.name == 'nt' or not shutil.which('dbus-daemon'):
        pytest.skip('Linux D-Bus integration')
    system_python = '/usr/bin/python3'
    if subprocess.run([system_python, '-c', 'import gi'], capture_output=True).returncode:
        pytest.skip('System PyGObject needed for fake portal')
    bus_config = tmp_path / 'bus.conf'
    bus_config.write_text('<busconfig><type>session</type><listen>unix:tmpdir=/tmp</listen>'
        '<auth>EXTERNAL</auth><apparmor mode="disabled"/><policy context="default">'
        '<allow send_destination="*"/><allow eavesdrop="true"/><allow own="*"/></policy></busconfig>')
    daemon = subprocess.Popen(['dbus-daemon', '--config-file=' + str(bus_config), '--nofork', '--print-address', '--nopidfile'],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    service = None
    name = 'test-portal-' + uuid.uuid4().hex
    try:
        address = daemon.stdout.readline().strip()
        assert address.startswith('unix:')
        script = tmp_path / 'portal_service.py'
        script.write_text(SERVICE)
        expected = tmp_path / 'shot with spaces.png'
        environment = os.environ.copy()
        environment['DBUS_SESSION_BUS_ADDRESS'] = address
        service = subprocess.Popen([system_python, str(script), QUrl.fromLocalFile(str(expected)).toString()],
                    env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        ready = service.stdout.readline().strip()
        assert ready == 'READY', service.stderr.read() if not ready else ready
        capture = PortalCapture()
        capture.bus = QDBusConnection.connectToBus(address, name)
        paths, errors = [], []
        capture.path_ready.connect(paths.append)
        capture.error.connect(errors.append)
        capture.start()
        spin(lambda: bool(paths or errors), timeout=5)
        assert not errors
        assert paths == [str(expected)]
        assert not capture.waiting
    finally:
        QDBusConnection.disconnectFromBus(name)
        if service:
            service.terminate()
            service.wait(3)
        daemon.terminate()
        daemon.wait(3)
