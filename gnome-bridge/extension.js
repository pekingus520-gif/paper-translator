import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import St from 'gi://St';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {SelectionTracker} from './selection.js';
import {HotkeyBindings} from './bindings.js';
import {attachScreenshotSignals} from './screenshot-session.js';
import {shouldPresentResult} from './result-presentation.js';

export default class PaperTranslatorBridge extends Extension {
    enable() {
        this._alive = true;
        this._config = null;
        this._status = '';
        this._mainPinned = null;
        this._presentedResult = null;
        this._polling = false;
        this._epoch = 0;
        this._cancellable = new Gio.Cancellable();
        this._tracker = new SelectionTracker();
        this._settings = this.getSettings();
        this._hotkeys = new HotkeyBindings(
            (key, accelerator) => {
                this._settings.set_strv(key, [accelerator]);
                const action = Main.wm.addKeybinding(key, this._settings, Meta.KeyBindingFlags.NONE,
                    Shell.ActionMode.NORMAL, () => {
                        if (key === 'paper-translator-screenshot' && this._config?.translation_enabled)
                            this._startNativeScreenshot();
                        else if (key === 'paper-translator-toggle')
                            this._send({command: 'toggle'});
                    });
                return action !== Meta.KeyBindingAction.NONE;
            },
            key => Main.wm.removeKeybinding(key),
        );
        this._clipboard = St.Clipboard.get_default();
        try {
            this._selection = global.display.get_selection();
            this._ownerSignal = this._selection.connect('owner-changed', (_selection, type) => {
                if (type === Meta.SelectionType?.SELECTION_CLIPBOARD)
                    this._tracker.cancelCurrent();
            });
        } catch (_error) {
            // Text changes and Ctrl+C remain available on older Shell versions.
            this._selection = null;
            this._ownerSignal = null;
        }
        this._lastClipboardText = undefined;
        this._copySignal = global.stage.connect('captured-event', (_stage, event) => {
            if (event.type() === Clutter.EventType.KEY_PRESS &&
                event.get_state() & Clutter.ModifierType.CONTROL_MASK &&
                [Clutter.KEY_c, Clutter.KEY_C, Clutter.KEY_Insert].includes(event.get_key_symbol()))
                this._tracker.cancelCurrent();
            return Clutter.EVENT_PROPAGATE;
        });
        this._file = Gio.File.new_for_path(GLib.build_filenamev([GLib.get_user_config_dir(), 'paper-translator', 'bridge.json']));
        this._readConfig();
        this._configTimer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 500, () => {
            this._readConfig();
            return GLib.SOURCE_CONTINUE;
        });
        this._selectionTimer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 60, () => {
            this._pollSelection();
            return GLib.SOURCE_CONTINUE;
        });
        this._heartbeatTimer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 2000, () => {
            this._send({command: 'bridge', status: this._status});
            return GLib.SOURCE_CONTINUE;
        });
        this._mapSignal = global.window_manager.connect('map', (_manager, actor) => {
            this._positionResult(actor.meta_window);
            this._positionStatus(actor.meta_window);
            this._setMainAbove(actor.meta_window, Boolean(this._config?.pin_main));
        });
    }

    _readConfig() {
        if (!this._alive)
            return;
        try {
            const [ok, contents] = this._file.load_contents(null);
            const value = ok ? JSON.parse(new TextDecoder().decode(contents)) : null;
            if (!value || !value.running || typeof value.socket !== 'string' ||
                Math.abs(Date.now() / 1000 - value.timestamp) > 8) {
                this._deactivate();
                return;
            }
            if (this._config?.enabled !== value.enabled || this._config?.generation !== value.generation) {
                this._epoch++;
                this._tracker.suspend();
            }
            this._config = value;
            if (shouldPresentResult(this._presentedResult, value) && this._presentResult())
                this._presentedResult = {generation: value.generation,
                    result_revision: value.result_revision};
            if (this._mainPinned !== Boolean(value.pin_main)) {
                this._mainPinned = Boolean(value.pin_main);
                for (const actor of global.get_window_actors())
                    this._setMainAbove(actor.meta_window, this._mainPinned);
            }
            const failed = this._hotkeys.sync([
                ['paper-translator-screenshot', value.screenshot],
                ['paper-translator-toggle', value.toggle],
            ]);
            const status = failed.map(accelerator => `快捷键 ${accelerator} 注册失败，请修改设置。`).join(' ');
            if (status !== this._status) {
                this._status = status;
                this._send({command: 'bridge', status: this._status});
            }
        } catch (_error) {
            this._deactivate();
        }
    }

    _deactivate() {
        this._config = null;
        this._mainPinned = null;
        this._presentedResult = null;
        this._epoch++;
        this._tracker.suspend();
        this._hotkeys.clear();
    }

    _pollSelection() {
        if (!this._alive || !this._config?.enabled || Main.sessionMode.isLocked)
            return;
        const focus = global.display.focus_window;
        const id = `${focus?.get_wm_class() ?? ''} ${focus?.get_gtk_application_id() ?? ''}`.toLowerCase();
        if (id.includes('papertranslator')) {
            this._tracker.suspend();
            return;
        }
        const [x, y, modifiers] = global.get_pointer();
        const dragging = Boolean(modifiers & Clutter.ModifierType.BUTTON1_MASK);
        if (dragging) {
            this._tracker.feed('', GLib.get_monotonic_time() / 1000, true, {x, y});
            return;
        }
        if (this._polling)
            return;
        this._polling = true;
        const epoch = this._epoch;
        this._clipboard.get_text(St.ClipboardType.CLIPBOARD, (_clipboard, clipboardText) => {
            const changed = this._lastClipboardText !== undefined && clipboardText !== this._lastClipboardText;
            this._lastClipboardText = clipboardText;
            this._clipboard.get_text(St.ClipboardType.PRIMARY, (_primaryClipboard, text) => {
                this._polling = false;
                if (!this._alive || !this._config?.enabled || epoch !== this._epoch)
                    return;
                if (changed)
                    this._tracker.cancelText(clipboardText || text);
                const [currentX, currentY, currentModifiers] = global.get_pointer();
                const selected = this._tracker.feed(text, GLib.get_monotonic_time() / 1000,
                    Boolean(currentModifiers & Clutter.ModifierType.BUTTON1_MASK),
                    {x: currentX, y: currentY});
                if (selected && selected.length <= 10000)
                    this._send({command: 'selection', text: selected});
            });
        });
    }

    _send(message, onSent = null) {
        if (!this._alive || !this._config)
            return;
        const address = new Gio.UnixSocketAddress({path: this._config.socket});
        const client = new Gio.SocketClient({timeout: 1});
        const epoch = this._epoch;
        const generation = this._config.generation;
        if (message.command === 'selection')
            message.generation = generation;
        const data = new TextEncoder().encode(`${JSON.stringify(message)}\n`);
        client.connect_async(address, this._cancellable, (_client, result) => {
            let connection;
            try {
                connection = client.connect_finish(result);
                if (!this._alive || (message.command === 'selection' &&
                    (!this._config?.enabled || epoch !== this._epoch || generation !== this._config.generation))) {
                    connection.close(null);
                    return;
                }
                const stream = connection.get_output_stream();
                stream.write_all_async(data, GLib.PRIORITY_DEFAULT, this._cancellable, (_stream, written) => {
                    try {
                        stream.write_all_finish(written);
                        onSent?.();
                    } catch (_error) {
                        // App may have exited between connecting and writing.
                    } finally {
                        try { connection.close(null); } catch (_error) { /* already closed */ }
                    }
                });
            } catch (_error) {
                if (connection) {
                    try { connection.close(null); } catch (_ignored) { /* already closed */ }
                }
            }
        });
    }

    _startNativeScreenshot() {
        const ui = Main.screenshotUI;
        if (!ui?.open) {
            this._focusTranslator();
            this._send({command: 'screenshot'});
            return;
        }
        const captureId = GLib.uuid_string_random();
        this._send({command: 'screenshot_native', capture_id: captureId}, () => {
            if (!this._alive)
                return;
            const session = attachScreenshotSignals(ui, captureId,
                message => this._send(message),
                callback => GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
                    callback();
                    return GLib.SOURCE_REMOVE;
                }));
            GLib.timeout_add(GLib.PRIORITY_DEFAULT, 180, () => {
                if (!this._alive) {
                    session.close();
                    return GLib.SOURCE_REMOVE;
                }
                ui.open().then(() => {
                    // Start in area mode regardless of the user's last GNOME
                    // screenshot mode; only the selected region is translated.
                    if (ui._selectionButton)
                        ui._selectionButton.checked = true;
                }).catch(_error => {
                    session.close();
                });
                return GLib.SOURCE_REMOVE;
            });
        });
    }

    _focusTranslator() {
        const window = global.get_window_actors()
            .map(actor => actor.meta_window)
            .find(candidate => candidate?.get_title() === 'Paper Translator');
        if (window)
            Main.activateWindow(window);
    }

    _positionResult(window) {
        if (!this._config || !window || !window.get_title()?.startsWith('Paper Translator · 翻译结果'))
            return;
        try {
            window.make_above();
            const [x, y] = global.get_pointer();
            const frame = window.get_frame_rect();
            const area = window.get_work_area_current_monitor();
            window.move_frame(false,
                Math.max(area.x, Math.min(x + 16, area.x + area.width - frame.width)),
                Math.max(area.y, Math.min(y + 16, area.y + area.height - frame.height)));
        } catch (_error) {
            // Positioning is cosmetic; translation still works if a compositor refuses it.
        }
    }

    _presentResult() {
        const window = global.get_window_actors()
            .map(actor => actor.meta_window)
            .find(candidate => candidate?.get_title()?.startsWith('Paper Translator · 翻译结果'));
        if (!window)
            return false;
        try {
            window.make_above();
            Main.activateWindow(window);
            return true;
        } catch (_error) {
            return false;
        }
    }

    _positionStatus(window) {
        if (!window || window.get_title?.() !== 'Paper Translator · 翻译状态')
            return;
        try {
            window.make_above();
            const frame = window.get_frame_rect();
            const area = window.get_work_area_current_monitor();
            window.move_frame(false, area.x + Math.floor((area.width - frame.width) / 2), area.y + 32);
        } catch (_error) {
            // Qt positioning remains the fallback if Shell refuses the move.
        }
    }

    _setMainAbove(window, pinned) {
        if (!window || window.get_title?.() !== 'Paper Translator')
            return;
        try {
            if (pinned)
                window.make_above();
            else
                window.unmake_above();
        } catch (_error) {
            // Qt's WindowStaysOnTopHint remains the fallback on other desktops.
        }
    }

    disable() {
        this._alive = false;
        this._epoch++;
        this._cancellable?.cancel();
        for (const timer of [this._configTimer, this._selectionTimer, this._heartbeatTimer]) {
            if (timer)
                GLib.Source.remove(timer);
        }
        if (this._mapSignal)
            global.window_manager.disconnect(this._mapSignal);
        if (this._copySignal)
            global.stage.disconnect(this._copySignal);
        if (this._ownerSignal)
            this._selection.disconnect(this._ownerSignal);
        this._hotkeys?.clear();
        this._config = null;
        this._clipboard = null;
        this._settings = null;
    }
}
