def stop_process(process, connection, timeout=0.5):
    """Cross-process accessibility providers may hang; never hang the GUI on exit."""
    if process is None:
        return
    try:
        connection.send({'stop': True})
    except (OSError, EOFError):
        pass
    process.join(timeout)
    if process.is_alive():
        process.terminate()
        process.join(2)
    if process.is_alive():
        process.kill()
        process.join()
    connection.close()
