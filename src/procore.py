import asyncio
import json
import yaml
import logging
from re import match, sub, compile, Pattern
from importlib import import_module
from typing import Callable

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


class Action(object):
    def __init__(
        self, condition: Pattern, action_callable: Callable, remove_patterns: list = []
    ) -> None:
        self._condition = condition
        self._callable = action_callable
        self._remove_patterns = remove_patterns
        self._actions = []

    async def perform_action(self, data: bytes = b""):
        """This function will test the data against the condtion.
        If it matches, it will perform removal steps and pass it to the callable.

        Args:
            data (bytes, optional): This value is the data that will be checked against
            the condition. Defaults to b"".
        """
        decoded_data = data.decode()
        if match(self._condition, decoded_data):
            for pattern in self._remove_patterns:
                decoded_data = sub(pattern=pattern, repl="", string=decoded_data)
            self._callable(decoded_data)


class Actions(object):
    async def register_actions(self, actions: list = []) -> None:
        """This function will compile all patterns, import the callable,
        and keep track of the actions.

        Args:
            actions (list, optional): This should  be a list of action dicts.
            Defaults to [].
        """
        for action in actions:
            action_condition = compile(action["condition"])
            action_remove_patterns = []
            if precompiled_patterns := action.get("remove_patterns"):
                for precompiled_patttern in precompiled_patterns:
                    action_remove_patterns.append(compile(precompiled_patttern))
            action_callable = import_module(action["callable"])
            self._actions.append(
                Action(
                    condition=action_condition,
                    action_callable=action_callable,
                    remove_patterns=action_remove_patterns,
                )
            )

    async def perform_actions(self, data: bytes = b""):
        """This function will call perform_action and pass data on all registed actions.

        Args:
            data (bytes, optional): This is the value to run the actions on.
            Defaults to b"".
        """
        for action in self._actions:
            await action.perform_action(data)


class Manager(object):
    def __init__(
        self, cmd, manage_stdin: bool = False, dedicated_stderr: bool = False
    ) -> None:
        self._cmd = cmd
        self._manage_stdin = manage_stdin
        self._dedicated_stderr = dedicated_stderr
        self._process = None

    def __del__(self):
        if self._process is not None and self._process.returncode is None:
            logger.debug("Killing the process")
            self._process.kill()

    async def start(self) -> None:
        # This will initallize the stderr and stdin with PIPEs
        if self._dedicated_stderr and self._manage_stdin:
            self._process = await asyncio.subprocess.create_subprocess_shell(
                self._cmd,
                stderr=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE,
            )
        # This one just sets the stderr and stdout to PIPEs
        elif self._dedicated_stderr:
            self._process = await asyncio.subprocess.create_subprocess_shell(
                self._cmd,
                stderr=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
            )
        # This one is just for PIPEing the stdin
        elif self._manage_stdin:
            self._process = await asyncio.subprocess.create_subprocess_shell(
                self._cmd,
                stderr=asyncio.subprocess.STDOUT,
                stdout=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE,
            )
        # This one does not create dedicated PIPEs for stdin or stderr.
        else:
            self._process = await asyncio.subprocess.create_subprocess_shell(
                self._cmd,
                stderr=asyncio.subprocess.STDOUT,
                stdout=asyncio.subprocess.PIPE,
            )

        logger.info(f'Created the process: "{self._process}"')
        # Create the queues
        self._output_queue = asyncio.Queue()
        self._error_queue = asyncio.Queue()
        self._input_queue = asyncio.Queue()
        logger.info("Created the queues")
        # create the tasks
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

    async def read(self) -> bytes:
        return await self._output_queue.get()

    async def write(self, data: bytes = b"\r\n"):
        if self._process.returncode is None:
            if data.endswith(b"\r\n"):
                await self._input_queue.put(data)
            else:
                await self._input_queue.put(data + b"\r\n")

    @staticmethod
    async def output_runner(proc: asyncio.subprocess.Process, queue: asyncio.Queue):
        logger.debug("Output runner has started")
        while proc.returncode is None:
            data = await proc.stdout.readline()
            if not data:
                break
            try:
                await queue.put(data)
            except asyncio.QueueFull:
                logger.warning(f'Output queue is full, removing "{await queue.get()}"')
                await queue.put(data)
        await queue.put(b"")
        logger.debug("Output runner has finished, sending empty byte string")

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
    async def input_runner(
        proc: asyncio.subprocess.Process, queue: asyncio.Queue, delay: float = 0
    ):
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


async def load_config(config_path: str) -> dict:
    with open(config_path, "r") as config_file:
        if config_path.endswith(".yml"):
            return yaml.safe_load(config_file)
        elif config_path.endswith(".json"):
            return json.load(config_file)
        else:
            raise ValueError(
                f'"{config_file}" is not a supported config file type. (*.json, *.yml)'
            )


# This is the legacy action system. Kept in for reference. \
# However, will remove eventually
# async def perform_action(action: dict = {}, data: str = "") -> None:
#     if "condition" in action.keys() and match(action["condition"], data):
#         logger.debug("action condition matches data")
#         if "remove_steps" in action.keys():
#             logger.debug(
#                 f"Found remove_steps: " f" {len(action['remove_steps'])} steps"
#             )
#             for remove_step in action["remove_steps"]:
#                 # pass the execution to the loop
#                 await asyncio.sleep(0)
#                 # if the remove step matches, remove the match.
#                 pre_data = data
#                 data = sub(remove_step, "", data)
#                 # helps debug steps
#                 if data == pre_data:
#                     logger.warning(f'"{remove_step}" had no effect')


if __name__ == "__main__":

    async def main():
        logger.setLevel(logging.DEBUG)
        from sys import argv

        if len(argv) > 1:
            config = await load_config(argv[1])
        else:
            config = await load_config(
                r"C:\Users\jbloo\Documents\Git\proman_core\config.json"
            )
        # create and register the actions stored in the config

        proc = Manager(config["command"])
        await proc.start()
        while data := await proc.read():
            if data:
                data = data.decode()
                # await perform_action(action=config["action"], data=data)
                print(data, end="")
        logger.debug("Main function has stopped the loop")

    asyncio.run(main())
