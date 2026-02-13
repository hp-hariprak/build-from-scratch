import os
import sys
import shlex
import subprocess
import shutil
import readline
from pathlib import Path

class Autocompleter:
    available_commands = ("echo", "type", "exit", "pwd", "cd", "history")

    def __init__(self):
        self.options = self.get_options()
        self.matches = []

    def get_options(self):
        options = list(self.available_commands)
        options.extend(self._get_path_executable())
        return options

    @staticmethod
    def _get_path_executable():
        for path in os.environ["PATH"].split(os.pathsep):
            path = Path(path)
            if path.exists():
                for file in path.iterdir():
                    if file.is_file() and shutil.which(file.name):
                        yield file.name

    def complete(self, text, state):
        if state == 0:
            if text:
                self.matches = [
                    option for option in self.options if option.startswith(text)
                ]
            else:
                self.matches = self.options[:]
        if state < len(self.matches):
            return f"{self.matches[state]} "
        else:
            return None

    @classmethod
    def complete_hook(cls, substitution, matches, longest_match_length):
        print()
        print(" ".join(matches))
        print("$ " + readline.get_line_buffer(), end="", flush=True)


completer = Autocompleter()
readline.set_completer(completer.complete)
readline.set_completion_display_matches_hook(Autocompleter.complete_hook)
readline.parse_and_bind("tab: complete")
readline.set_auto_history(False)
HISTORY = []


class CommandHandler:
    TYPE_TEMPLATE = "{arg} is a shell builtin"
    TYPES_BUILTIN = {"history", "echo", "type", "exit", "pwd"}

    @staticmethod
    def split_command(command: str) -> tuple[str, str]:
        command, *arg = shlex.split(command)
        return command, arg

    @staticmethod
    def find_executable(command: str) -> str | None:
        return shutil.which(command)

    @staticmethod
    def is_a_redirect(command: str) -> bool:
        return ">" in command or "1>" in command

    @staticmethod
    def is_a_pipe(command: str) -> bool:
        return "|" in command

    @staticmethod
    def handle_echo(arg: str) -> bool:
        print(f"{" ".join(arg)}")
        return False

    def handle_type(self, arg: str) -> bool:
        arg = "".join(arg)
        if arg in self.TYPES_BUILTIN:
            print(self.TYPE_TEMPLATE.format(arg=arg))
        elif pathname := shutil.which(arg):
            print(pathname)
        else:
            print(f"{arg}: not found")
        return False

    @staticmethod
    def handle_pwd() -> bool:
        print(os.getcwd())
        return False

    @staticmethod
    def handle_exec(command: str, arg: str) -> bool:
        args = [command, *arg]
        subprocess.run(args)
        return False
        
    @staticmethod
    def handle_history(arg: list[str]) -> bool:
        if not arg:
            for i in range(len(HISTORY)):
                # Updated format: 4 spaces before number, 2 after
                print(f"    {i+1}  {HISTORY[i]}")
            return False
        if len(arg) == 2 and arg[0] == "-r":
            fn = arg[1]
            try:
                with open(os.path.expanduser(fn), "r") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            HISTORY.append(line)
                            readline.add_history(line)
            except (FileNotFoundError, PermissionError, OSError):
                pass
            return False
        if len(arg) == 2 and arg[0] == "-w":
            fn = arg[1]
            try:
                with open(os.path.expanduser(fn), "w") as f:
                    for i in HISTORY:
                        f.write(i + "\n")
            except (PermissionError, OSError):
                print(f"history: cannot write {fn}")
            return False
        if len(arg) == 2 and arg[0] == "-a":
            fn = arg[1]
            try:
                with open(os.path.expanduser(fn), "a") as f:
                    for i in HISTORY:
                        f.write(i + "\n")
                HISTORY.clear()
            except (PermissionError, OSError):
                print(f"history: cannot append to {fn}")
            return False
        try:
            n = int(arg[0])
            if n <= 0:
                print("history: argument must be a positive integer")
                return False
            b = len(HISTORY)
            start = max(0, b - n)
            for i in range(start, b):
                print(f"    {i+1}  {HISTORY[i]}")
        except (ValueError, IndexError):
            print("history: invalid argument")
        return False
    
    @staticmethod
    def handle_cd(arg: str) -> bool:
        arg = Path("".join(arg))
        try:
            os.chdir(arg.expanduser())
        except FileNotFoundError:
            print(f"cd: {arg}: No such file or directory")
        return False

    @staticmethod
    def subprocess_call(command: str) -> bool:
        subprocess.call(command, shell=True)
        return False

    @staticmethod
    def handle_default(command: str) -> bool:
        print(f"{command}: command not found")
        return False

    def handle_command(self, command: str) -> bool:
        if self.is_a_redirect(command) or self.is_a_pipe(command):
            return self.subprocess_call(command)
        match self.split_command(command):
            case ("exit", _):
                return True
            case ("history", arg):
                return self.handle_history(arg)
            case ("echo", arg):
                return self.handle_echo(arg)
            case ("type", arg):
                return self.handle_type(arg)
            case ("pwd", _):
                return self.handle_pwd()
            case ("cd", arg):
                return self.handle_cd(arg)
            case (command, arg):
                if self.find_executable(command):
                    return self.handle_exec(command, arg)
                return self.handle_default(command)
        return False


def main() -> None:
    history_file = os.getenv("HISTFILE")
    if history_file:
        try:
            with open(os.path.expanduser(history_file), "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        HISTORY.append(line)
                        readline.add_history(line)
        except (FileNotFoundError, PermissionError, OSError):
            pass
    while True:
        user_input = input("$ ")
        if user_input.strip():
            HISTORY.append(user_input)
            readline.add_history(user_input)
        should_exit = CommandHandler().handle_command(user_input)
        if should_exit:
            break
    if history_file:
        try:
            max_history = 1000
            if len(HISTORY) > max_history:
                HISTORY[:] = HISTORY[-max_history:]
            with open(os.path.expanduser(history_file), "w") as f:
                for item in HISTORY:
                    f.write(item + "\n")
        except (OSError, PermissionError):
            pass


if __name__ == "__main__":
    main()