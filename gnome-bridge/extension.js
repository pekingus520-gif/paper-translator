import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import St from 'gi://St';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {SelectionTracker} from './selection.js';

export default class PaperTranslatorBridge extends Extension {
    enable() {
        this._alive = true;
        this._config = null;
        this._signature = '';
        this._bound = [];
        this._status = '';
        this._polling = false;
        this._epoch = 0;
        this._cancellable = new Gio.Cancellable();
        this._tracker = new SelectionTracker();
        this._settings = this.getSettings();
        this._clipboard = St.Clipboard.get_default();
        this._file = Gio.File.new_for_path(GLib.build_filenamev([GLib.get_user_config_dir(), 'paper-translator', 'bridge.json']));
        this._readConfig();
        this._configTimer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 500, () => {
            this._readConfig();
            return GLib.SOURCE_CONTINUE;
        });
        this._selectionTimer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 150, () => {
            this._pollSelection();
            return GLib.SOURCE_CONTINUE;
        });
        this._heartbeatTimer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 2000, () => {
            this._send({command: 'bridge', status: this._status});
            return GLib.SOURCE_CONTINUE;
        });
        this._mapSignal = global.window_manager.connect('map', (_manager, actor) => this._positionResult(actor.meta_window));
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
            const signature = JSON.stringify([value.screenshot, value.toggle]);
            if (signature !== this._signature) {
                this._unbind();
                this._signature = signature;
                this._status = '';
                for (const [key, accelerator, command] of [
                    ['paper-translator-screenshot', value.screenshot, 'screenshot'],
                    ['paper-translator-toggle', value.toggle, 'toggle'],
                ]) {
                    if (typeof accelerator !== 'string' || accelerator.length > 100)
                        continue;
                    this._settings.set_strv(key, [accelerator]);
                    const action = Main.wm.addKeybinding(key, this._settings, Meta.KeyBindingFlags.NONE,
                        Shell.ActionMode.NORMAL, () => {
                            if (command === 'toggle' || this._config?.translation_enabled)
                                this._send({command});
                        });
                    if (action === Meta.KeyBindingAction.NONE)
                        this._status += `快捷键 ${accelerator} 注册失败，请修改设置。`;
                    else
                        this._bound.push(key);
                }
                this._send({command: 'bridge', status: this._status});
            }
        } catch (_error) {
            this._deactivate();
        }
    }

    _deactivate() {
        this._config = null;
        this._epoch++;
        this._tracker.suspend();
        this._unbind();
        this._signature = '';
    }

    _unbind() {
        for (const key of this._bound ?? [])
            Main.wm.removeKeybinding(key);
        this._bound = [];
    }

    _pollSelection() {
        if (!this._alive || !this._config?.enabled || this._polling || Main.sessionMode.isLocked)
            return;
        const focus = global.display.focus_window;
        const id = `${focus?.get_wm_class() ?? ''} ${focus?.get_gtk_application_id() ?? ''}`.toLowerCase();
        if (id.includes('papertranslator')) {
            this._tracker.suspend();
            return;
        }
        const [, , modifiers] = global.get_pointer();
        const dragging = Boolean(modifiers & Clutter.ModifierType.BUTTON1_MASK);
        if (dragging) {
            this._tracker.feed('', GLib.get_monotonic_time() / 1000, true);
            return;
        }
        this._polling = true;
        const epoch = this._epoch;
        this._clipboard.get_text(St.ClipboardType.PRIMARY, (_clipboard, text) => {
            this._polling = false;
            if (!this._alive || !this._config?.enabled || epoch !== this._epoch)
                return;
            const [, , currentModifiers] = global.get_pointer();
            const selected = this._tracker.feed(text, GLib.get_monotonic_time() / 1000,
                Boolean(currentModifiers & Clutter.ModifierType.BUTTON1_MASK));
            if (selected && selected.length <= 10000)
                this._send({command: 'selection', text: selected});
        });
    }

    _send(message) {
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
        this._unbind();
        this._config = null;
        this._clipboard = null;
        this._settings = null;
    }
}
