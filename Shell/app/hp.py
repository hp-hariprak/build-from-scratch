import os,sys,io
import shlex
import readline
import subprocess

class MiniShell:
    def __init__(self):
        self.builtins = {"type", "echo", "exit", "pwd", "cd"}
        self.redirects = {">", ">>", "1>", "1>>", "2>", "2>>"}
        self.paths = os.getenv("PATH", "").split(":")
        self.tab_state = {"count": 0, "last_text": ""}  
        self.commands = self.get_all_commands()
        self.setup_readline()       

    def get_all_commands(self):
        cmds = set(self.builtins)
        for path in self.paths:
            try:
                for file in os.listdir(path):
                    full = os.path.join(path, file)
                    if os.path.isfile(full) and os.access(full, os.X_OK):
                        cmds.add(file)
            except (FileNotFoundError, PermissionError):
                continue
        return sorted(cmds)

    def find_exe(self, cmd):
        for path in self.paths:
            try:
                full_path = os.path.join(path, cmd)
                if os.path.isfile(full_path) and os.access(full_path, os.X_OK):
                    return full_path
            except (FileNotFoundError, PermissionError):
                continue
        return None

    def setup_readline(self):
        readline.set_completer(self.completer)
        readline.parse_and_bind("tab: complete")
        readline.set_completer_delims(" \t\n")
        
    def completer(self,text, state):
        matches = [cmd for cmd in self.commands if cmd.startswith(text)]
        if self.tab_state["last_text"] != text:
            self.tab_state["count"] = 0
            self.tab_state["last_text"] = text

        if state == 0 and len(matches) > 1:
            if self.tab_state["count"] == 0:
                if all(match.startswith(matches[0]) for match in matches[1:]):
                    return matches[0]
                self.tab_state["count"] += 1
                return None
            else:
                print("\n" + "  ".join(matches))
                print(f"$ {text}")
                sys.stdout.flush()
                return text
        if state < len(matches):
            return matches[state] + " "
        return None


    def cmd_exit(self, args,out=sys.stdout):
        raise SystemExit

    def cmd_echo(self, args,out=sys.stdout):
        print(" ".join(args),file=out)

    def cmd_pwd(self, args,out=sys.stdout):
        print(os.getcwd(),file=out)

    def cmd_cd(self, args,out=sys.stdout):
        try:
            target = args[0] if args else os.path.expanduser("~")
            if target == "~":
                target = os.path.expanduser("~")
            os.chdir(target)
        except FileNotFoundError:
            print(f"cd: {target}: No such file or directory",file=out)
        except NotADirectoryError:
            print(f"cd: {target}: Not a directory",file=out)
        except PermissionError:
            print(f"cd: {target}: Permission denied",file=out)

    def cmd_type(self, args,out=sys.stdout):
        try:
            name = args[0]
            if name in self.builtins:
                print(f"{name} is a shell builtin",file=out)
            else:
                path = self.find_exe(name)
                if path:
                    print(f"{name} is {path}",file=out)
                else:
                    print(f"{name}: not found",file=out)
        except IndexError:
            print("type: missing operand",file=out)
                      
    def exe_pipeline(self,commands):
        if not commands:
            return
        processes = []
        prev_stdout = None
        prev_stdin=None
        for i, cmd_tokens in enumerate(commands):
            exe = cmd_tokens[0]
            args = cmd_tokens[1:]
            if exe in self.builtins:
                ob = io.StringIO()
                self.dispatch(exe, args, out=ob)
                output_str = ob.getvalue()
                
                if i < len(commands) - 1:
                    prev_stdin = output_str.encode() if output_str else None
                else:
                    print(output_str, end="")
            else:
                path = self.find_exe(exe)
                if not path:
                    print(f"{exe}: command not found")
                    return
                stdin_arg = prev_stdin if prev_stdin else (prev_stdout if prev_stdout else None)
                stdout_arg = subprocess.PIPE if i < len(commands) - 1 else None
                
                try:
                    proc = subprocess.Popen([exe] + args, stdin=stdin_arg, stdout=stdout_arg, executable=path)
                    processes.append(proc)
                    prev_stdout = proc.stdout
                    prev_stdin = None 
                except Exception as e:
                    print(f"Error starting {exe}: {e}")
                    return
        
        try:
            for proc in processes:
                proc.wait()
        except KeyboardInterrupt:
            for proc in processes:
                proc.terminate()
            print()

    def execute_external(self, exe, args,out=sys.stdout):
        path = self.find_exe(exe)
        if not path:
            print(f"{exe}: command not found",file=out)
            return
        try:
            subprocess.run([exe] + args, executable=path)
        except FileNotFoundError:
            print(f"{exe}: command not found",file=out)
        except PermissionError:
            print(f"{exe}: permission denied",file=out)
        except Exception as e:
            print(f"{exe}: error: {e}",file=out)

    def dispatch(self, exe, args,out=sys.stdout):
        try:
            if exe == "exit":
                self.cmd_exit(args,out)
            elif exe == "echo":
                self.cmd_echo(args,out)
            elif exe == "pwd":
                self.cmd_pwd(args,out)
            elif exe == "cd":
                self.cmd_cd(args,out)
            elif exe == "type":
                self.cmd_type(args,out)
            else:
                self.execute_external(exe, args)
        except SystemExit:
            raise
        except Exception as e:
            print(f"Error: {e}",file=out)

    def run(self):
        while True:
            try:
                raw = input("$ ")
                if not raw.strip():
                    continue
                if "|" in raw:
                    temp=raw.split("|")
                    c=[]
                    for i in temp:
                        tokens=shlex.split(i)
                        c.append(tokens) if tokens else None
                        self.exe_pipeline(c)
                else:
                    tokens = shlex.split(raw)
                    exe = tokens[0]
                    args = tokens[1:]
                    self.dispatch(exe, args)
            except KeyboardInterrupt:
                print()  
            except EOFError:
                print()
                break
            except SystemExit:
                break
            except Exception as e:
                print(f"Unexpected error: {e}")

if __name__ == "__main__":
    shell = MiniShell()
    shell.run()