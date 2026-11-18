"""Transparent desktop selection, independent of the animation window."""
import os
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

# A per-pixel transparent native Qt surface. No backdrop, dimmer or screenshot.
# Kept inline so zipapp and frozen builds don't need extra resource paths.
SNAP_JS = r'''
function magneticPoint(x, y, windows, threshold) {
    var sx=x, sy=y, bestX=threshold+1, bestY=threshold+1;
    for (var i=0; i<windows.length; ++i) {
        var r=windows[i], ex=[r[0],r[0]+r[2]], ey=[r[1],r[1]+r[3]];
        for (var j=0;j<2;++j) {
            var dx=Math.abs(x-ex[j]),dy=Math.abs(y-ey[j]);
            if (y>=r[1]-threshold && y<=r[1]+r[3]+threshold && dx<=threshold && dx<bestX) {sx=ex[j];bestX=dx;}
            if (x>=r[0]-threshold && x<=r[0]+r[2]+threshold && dy<=threshold && dy<bestY) {sy=ey[j];bestY=dy;}
        }
    }
    return {x:sx,y:sy};
}
'''

QML = r'''
import QtQuick
import QtQuick.Window
import QtQml.Models

QtObject {
    id: controller
    property bool dragging: false
    property bool magnetic: false
    property var windows: []
    // SNAP_FUNCTION
    function adjusted(point) { return magnetic ? magneticPoint(point.x, point.y, windows, 14) : point; }
    property real startX: 0
    property real startY: 0
    property real endX: 0
    property real endY: 0
    function finish() {
        var w = Math.round(Math.abs(endX - startX));
        var h = Math.round(Math.abs(endY - startY));
        if (w < 40 || h < 30) { dragging = false; return; }
        console.log("TTHINGS_REGION " + Math.round(Math.min(startX, endX)) + " "
                    + Math.round(Math.min(startY, endY)) + " " + w + " " + h);
        Qt.quit();
    }
    property var surfaces: Instantiator {
        model: Qt.application.screens
        delegate: Window {
            id: overlay
            required property var modelData
            screen: modelData
            x: modelData.virtualX
            y: modelData.virtualY
            width: modelData.width
            height: modelData.height
            visible: true
            color: "transparent"
            title: "tthings · выделение области"
            flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
            Component.onCompleted: { show(); requestActivate(); }
            Item {
                anchors.fill: parent
                focus: true
                Keys.onEscapePressed: Qt.quit()
                Rectangle {
                    x: Math.min(controller.startX, controller.endX) - overlay.x
                    y: Math.min(controller.startY, controller.endY) - overlay.y
                    width: Math.abs(controller.endX - controller.startX)
                    height: Math.abs(controller.endY - controller.startY)
                    visible: controller.dragging
                    color: "transparent"
                    border.color: controller.magnetic ? "#f3c87a" : "#70e1ce"
                    border.width: 2
                }
                MouseArea {
                    id: mouse
                    anchors.fill: parent
                    cursorShape: Qt.CrossCursor
                    acceptedButtons: Qt.LeftButton | Qt.RightButton
                    onPressed: function(event) {
                        if (event.button === Qt.RightButton) { Qt.quit(); return; }
                        var point = controller.adjusted(mapToGlobal(event.x, event.y));
                        controller.startX = controller.endX = point.x;
                        controller.startY = controller.endY = point.y;
                        controller.dragging = true;
                    }
                    onPositionChanged: function(event) {
                        if (!controller.dragging) return;
                        var point = controller.adjusted(mapToGlobal(event.x, event.y));
                        controller.endX = point.x;
                        controller.endY = point.y;
                    }
                    onReleased: function(event) {
                        if (event.button !== Qt.LeftButton || !controller.dragging) return;
                        var point = controller.adjusted(mapToGlobal(event.x, event.y));
                        controller.endX = point.x;
                        controller.endY = point.y;
                        controller.finish();
                    }
                    onCanceled: controller.dragging = false
                }
            }
        }
    }
}
'''.replace('// SNAP_FUNCTION', SNAP_JS)


def qml_runtime():
    override = os.environ.get('TTHINGS_QML')
    if override:
        candidate = Path(override).expanduser()
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
        raise RuntimeError('TTHINGS_QML не указывает на исполняемый Qt QML runtime')
    for command in ('qml6', 'qml', 'qml-qt6'):
        found = shutil.which(command)
        if found:
            return found
    for candidate in ('/usr/lib/qt6/bin/qml', '/usr/lib64/qt6/bin/qml'):
        if Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def parse_rectangle(output):
    match = re.search(r'TTHINGS_REGION\s+(-?\d+)\s+(-?\d+)\s+(\d+)\s+(\d+)', output)
    if match:
        rect = tuple(map(int, match.groups()))
        if rect[2] >= 40 and rect[3] >= 30:
            return rect
    return None


def select_desktop_region(snap=False):
    runtime = qml_runtime()
    if not runtime:
        raise RuntimeError('Для прозрачного выделения на Linux нужен Qt 6 QML runtime. '
                           'На SteamOS он входит в KDE; путь можно указать через TTHINGS_QML. '
                           'Обычные окна и терминальные эффекты доступны без него.')
    from .snapping import window_rectangles
    windows = window_rectangles() if snap else []
    source = QML.replace('property bool magnetic: false', 'property bool magnetic: ' + str(bool(snap)).lower())
    source = source.replace('property var windows: []', 'property var windows: ' + json.dumps(windows))
    env = dict(os.environ)
    if env.get('XDG_SESSION_TYPE') == 'wayland' and env.get('WAYLAND_DISPLAY'):
        env['QT_QPA_PLATFORM'] = 'wayland'
    # KDE may redirect Qt logging to journald. The result is an IPC message,
    # so force it into our captured stderr instead.
    env['QT_FORCE_STDERR_LOGGING'] = '1'
    env['QT_LOGGING_TO_CONSOLE'] = '1'
    env['QT_LOGGING_RULES'] = 'qml.debug=true;qml.warning=true;qml.critical=true'
    env['QT_MESSAGE_PATTERN'] = '%{message}'
    # PyInstaller's bundled Tk libraries must not override the system Qt runtime.
    if 'LD_LIBRARY_PATH_ORIG' in env:
        env['LD_LIBRARY_PATH'] = env['LD_LIBRARY_PATH_ORIG']
    else:
        env.pop('LD_LIBRARY_PATH', None)
    env.pop('QT_PLUGIN_PATH', None)
    env.pop('QT_QPA_PLATFORM_PLUGIN_PATH', None)
    with tempfile.TemporaryDirectory(prefix='tthings-region-') as directory:
        path = Path(directory) / 'region.qml'
        path.write_text(source, encoding='utf-8')
        process = subprocess.Popen([runtime, '--transparent', str(path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        try:
            stdout,stderr=process.communicate()
        except BaseException:
            process.terminate()
            try:process.wait(timeout=2)
            except subprocess.TimeoutExpired:process.kill();process.wait()
            raise
        result = subprocess.CompletedProcess(process.args,process.returncode,stdout,stderr)
    output = result.stdout + '\n' + result.stderr
    if result.returncode:
        raise RuntimeError('Прозрачное выделение Qt не запустилось: ' + output.strip()[-1500:])
    return parse_rectangle(output)
