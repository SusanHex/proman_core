import asyncio
from concurrent.futures import process
import logging
from asyncio import create_subprocess_exec, create_subprocess_shell, create_task
from asyncio.subprocess import Process, PIPE
from asyncio.queues import Queue, QueueFull
from multiprocessing.connection import wait

logging.basicConfig(level=logging.DEBUG, format='%(message)s')
logger = logging.getLogger(__name__)
class Manager(object):
    def __init__(self, cmd) -> None:
        self._cmd = cmd

    async def start(self) -> None:
        self._process = await create_subprocess_shell(
            self._cmd, stdin=PIPE, stderr=PIPE, stdout=PIPE
        )
        logger.info(f'Created the process: "{self._process}"')
        # Create the queues
        self._output_queue = Queue()
        self._error_queue = Queue()
        self._input_queue = Queue()
        logger.info("Created the queues")
        # create the tasks
        self._output_task = await create_task(
            Manager.output_runner(self._process, self._output_queue)
        )
        self._error_task = await create_task(
            Manager.error_runner(self._process, self._error_queue)
        )
        self._input_queue = await create_task(
            Manager.input_runner(self._process, self._input_queue)
        )
        logger.info("Created the tasks")

    @staticmethod
    async def output_runner(proc: Process, queue: Queue):
        logger.info("Output runner has started")
        while proc.returncode is None:
            data = await proc.stdout.readline()
            if not data:
                break
            logger.debug(f'Output runner: "{data}", {proc.returncode} {bool(data)}')
            try:
                await queue.put(data)
            except QueueFull:
                logger.warning(f'Output queue is full, removing "{await queue.get()}"')
                await queue.put(data)
        logger.info("Output runner has finished")

    @staticmethod
    async def error_runner(proc: Process, queue: Queue):
        logger.info("Error runner has started")
        while proc.returncode is None:
            data = await proc.stdout.readline()
            logger.debug(f'Error runner: "{data}"')
            
            try:
                await queue.put(data)
            except QueueFull:
                logger.warning(f'Error queue is full, removing "{await queue.get()}"')
                await queue.put(data)
        logger.info("Error runner has finished")

    @staticmethod
    async def input_runner(proc: Process, queue: Queue):
        logger.info("Info runner has started")
        while Process.returncode is None:
            if queue.qsize() > 0:
                data = await queue.get()
                logger.debug(f'Input runner: "{data}"')
                if not data.endswith("\n"):
                    data = data + "\n"
                logger.debug("Info runner wrote data to process")
        logger.info("Input runner has finished")


if __name__ == "__main__":
    logger.setLevel(logging.DEBUG)
    async def main():
        logger = logging.Logger("root")
        logger.setLevel(logging.DEBUG)
        proc = Manager('python -c \"print(\'hello world\')\"')
        await proc.start()
        print(await proc._output_queue.get())

    asyncio.run(main())
