"""Own an asyncio application loop in one QThread, separate from the GUI thread.

Only Qt signals cross into widgets. Long inference/download tasks stay cancellable
and no web server, browser, Electron, or WebEngine is used by this application.
"""
from __future__ import annotations
import asyncio
import threading
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from aletheia_core.service import Service


class Backend(QThread):
    state = Signal(object)
    result = Signal(str, object)
    error = Signal(str, str)
    ready = Signal()

    def __init__(self, home: Path, service_factory=Service, parent=None):
        super().__init__(parent)
        self.home, self.service_factory = home, service_factory
        self.loop, self.service, self.stopping = None, None, None
        self.jobs = set()
        self.stop_requested = threading.Event()

    def run(self):
        try:
            asyncio.run(self.serve())
        except Exception as error:
            self.error.emit("startup", str(error))

    async def serve(self):
        self.loop = asyncio.get_running_loop()
        self.stopping = asyncio.Event()
        if self.stop_requested.is_set():
            self.stopping.set()
        self.service = self.service_factory(self.home)
        self.ready.emit()
        initialization = asyncio.create_task(self.service.initialize())
        async def poll():
            while True:
                self.state.emit(self.service.snapshot())
                await asyncio.sleep(.5)
        polling = asyncio.create_task(poll())
        try:
            await self.stopping.wait()
        finally:
            tasks = [initialization, polling, *self.jobs]
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await self.service.close()

    def submit(self, identifier, name, args):
        if self.loop is None or self.stopping is None or self.stopping.is_set():
            self.error.emit(identifier, "The library is not ready or is closing.")
            return
        def schedule():
            task = asyncio.create_task(self.dispatch(identifier, name, args))
            self.jobs.add(task)
            task.add_done_callback(self.jobs.discard)
        self.loop.call_soon_threadsafe(schedule)

    async def dispatch(self, identifier, name, args):
        try:
            if name == "importPaths":
                def read_files():
                    values = []
                    for raw in args[0]:
                        path = Path(raw)
                        candidates = sorted(path.rglob("*")) if path.is_dir() else [path]
                        for file in candidates:
                            if not file.is_file() or file.is_symlink() or file.suffix.lower() != ".md":
                                continue
                            if len(values) >= 2000 or file.stat().st_size > 2 * 1024 * 1024:
                                raise ValueError("Import at most 2,000 Markdown files, each up to 2 MiB.")
                            values.append(dict(name=file.name, content=file.read_bytes().decode("utf-8")))
                    return values
                values = await asyncio.to_thread(read_files)
                value = await self.service.import_contents(values)
            else:
                value = await self.service.execute(name, args)
            self.result.emit(identifier, value)
        except asyncio.CancelledError:
            self.error.emit(identifier, "Stopped.")
        except Exception as error:
            self.error.emit(identifier, str(error))
        finally:
            self.state.emit(self.service.snapshot())

    def stop(self):
        self.stop_requested.set()
        if self.loop and self.stopping:
            self.loop.call_soon_threadsafe(self.stopping.set)
