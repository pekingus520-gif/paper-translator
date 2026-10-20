export function shouldPresentResult(lastPresented, config) {
    const revision = config?.result_revision;
    if (!Number.isSafeInteger(revision) || revision <= 0)
        return false;
    return !lastPresented || lastPresented.generation !== config.generation ||
        lastPresented.result_revision !== revision;
}
