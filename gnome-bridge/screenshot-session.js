// Keep Shell signal handlers alive until the current signal emission finishes.
export function attachScreenshotSignals(ui, captureId, send, defer) {
    let taken = false;
    let closing = false;
    const takenId = ui.connect('screenshot-taken', (_ui, file) => {
        if (closing)
            return;
        const path = file?.get_path?.();
        if (typeof path !== 'string' || !path)
            return;
        taken = true;
        send({command: 'screenshot_file', capture_id: captureId, path});
    });
    const closedId = ui.connect('closed', close);

    function close() {
        if (closing)
            return;
        closing = true;
        defer(() => {
            ui.disconnect(takenId);
            ui.disconnect(closedId);
            if (!taken)
                send({command: 'screenshot_cancel', capture_id: captureId});
        });
    }

    return {close};
}
