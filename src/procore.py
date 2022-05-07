import asyncio
import logging
from re import match, sub

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

class Manager(object):
    def __init__(self, cmd, manage_stdin: bool = False, dedicated_stderr: bool = False) -> None:
        self._cmd = cmd
        self._manage_stdin = manage_stdin
        self._dedicated_stderr = dedicated_stderr
        
    async def start(self) -> None:
        if self._dedicated_stderr and self._manage_stdin:
            self._process = await asyncio.subprocess.create_subprocess_shell(
                self._cmd, stderr=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stdin=asyncio.subprocess.PIPE
            )
        elif self._dedicated_stderr:
            self._process = await asyncio.subprocess.create_subprocess_shell(
                self._cmd, stderr=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE
            )
        elif self._manage_stdin:
            self._process = await asyncio.subprocess.create_subprocess_shell(
                self._cmd, stderr=asyncio.subprocess.STDOUT, stdout=asyncio.subprocess.PIPE, stdin=asyncio.subprocess.PIPE
            )
        else:
            self._process = await asyncio.subprocess.create_subprocess_shell(
                self._cmd, stderr=asyncio.subprocess.STDOUT, stdout=asyncio.subprocess.PIPE
            )
            
        logger.info(f'Created the process: "{self._process}"')
        # Create the queues
        self._output_queue = asyncio.Queue()
        self._error_queue = asyncio.Queue()
        self._input_queue = asyncio.Queue()
        logger.info("Created the queues")
        #create the tasks
        
        self._output_task = asyncio.create_task(
            Manager.output_runner(self._process, self._output_queue)
        )
        if self._dedicated_stderr:
            self._error_task = asyncio.create_task(
                Manager.error_runner(self._process, self._error_queue)
            )
        if self._manage_stdin:
            self._input_task = asyncio.create_task(
                Manager.input_runner(self._process, self._input_queue)
            )
        logger.info("Created the task(s)")
    
    async def read(self):
        try:
            return await self._output_queue.get()
        except asyncio.QueueEmpty:
            return b''
    
    async def write(self, data: bytes = b'\r\n'):        
        if self._process.returncode is None:
            if data.endswith(b'\r\n'):
                self._input_queue.put(data)
            else:
                self._input_queue.put(data + b'\r\n')

    @staticmethod
    async def output_runner(proc: asyncio.subprocess.Process, queue: asyncio.Queue):
        logger.debug("Output runner has started")
        while proc.returncode is None:
            data = await proc.stdout.readline()
            if not data:
                break
            logger.debug(f'Output runner: "{data}", {proc.returncode} {bool(data)}')
            try:
                await queue.put(data)
            except asyncio.QueueFull:
                logger.warning(f'Output queue is full, removing "{await queue.get()}"')
                await queue.put(data)
            await asyncio.sleep(0)
        logger.debug("Output runner has finished")

    @staticmethod
    async def error_runner(proc: asyncio.subprocess.Process, queue: asyncio.Queue):
        logger.info("Error runner has started")
        while proc.returncode is None:
            data = await proc.stdout.readline()
            if not data:
                break
            logger.debug(f'Error runner: "{data}"')

            try:
                await queue.put(data)
            except asyncio.QueueFull:
                logger.warning(f'Error queue is full, removing "{await queue.get()}"')
                await queue.put(data)
        logger.info("Error runner has finished")

    @staticmethod
    async def input_runner(proc: asyncio.subprocess.Process, queue: asyncio.Queue, delay: float = 0):
        logger.info("Input runner has started")
        while proc.returncode is None:
            if queue.qsize() > 0:
                data = await queue.get()
                if proc.stdin.is_closing():
                    break
                else:
                    proc.stdin.write(data)
                    await proc.stdin.drain()
            else:
                await asyncio.sleep(0)
        logger.info("Input runner has finished")

async def perform_action(action: dict = {}, data: str = ''):
    if 'condition' in action.keys() and match(action['condition'], data):
        logger.debug('action condition matches data')
        if 'remove_steps' in action.keys():
            for remove_step in action['remove_steps']:
                # pass the execution to the loop
                asyncio.sleep(0)
                # if the remove step matches, remove the match.
                data = sub(remove_step, '', data)

if __name__ == "__main__":
    async def main():
        proc = Manager(r"echo hello && pause")
        await proc.start()
        while proc._process.returncode is None:
            print((await proc.read()).decode(), end='')


    asyncio.run(main())
