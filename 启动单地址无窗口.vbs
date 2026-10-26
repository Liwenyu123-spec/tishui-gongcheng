' 不弹出命令行窗口，只启动已经构建好的单地址后端。
' 日志写到 backend\data\server.log。停止服务时在任务管理器结束 python.exe。
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("Wscript.Shell")
root = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = root & "\backend"
sh.Environment("PROCESS")("PYTHONPATH") = "."
python = root & "\.venv\Scripts\python.exe"
log = root & "\backend\data\server.log"
' 0 表示隐藏窗口。cmd /c 负责把输出追加到日志，窗口本身不显示。
sh.Run "cmd /c """ & python & """ -m app >> """ & log & """ 2>&1", 0, False
