// Keeps each GNOME keybinding in sync with the current user setting.
export class HotkeyBindings {
    constructor(register, remove) {
        this.register = register;
        this.remove = remove;
        this.active = new Map();
    }

    sync(desired) {
        const failed = [];
        for (const [key, accelerator] of desired) {
            if (this.active.get(key) === accelerator)
                continue;
            if (this.active.has(key)) {
                this.remove(key);
                this.active.delete(key);
            }
            if (typeof accelerator !== 'string' || !accelerator || accelerator.length > 100) {
                failed.push(String(accelerator));
                continue;
            }
            try {
                if (this.register(key, accelerator))
                    this.active.set(key, accelerator);
                else
                    failed.push(accelerator);
            } catch (_error) {
                failed.push(accelerator);
            }
        }
        return failed;
    }

    clear() {
        for (const key of this.active.keys())
            this.remove(key);
        this.active.clear();
    }
}
