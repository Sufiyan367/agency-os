' Autonomous B2B Lead-Gen & Sales Agency — Silent Windows Background Launcher
' Launches the agency service runner completely hidden with 0 console window.

Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

ScriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
ProjectDir = fso.GetParentFolderName(ScriptDir)

WshShell.CurrentDirectory = ProjectDir
PythonExe = "C:\Users\sufiy\AppData\Local\Programs\Python\Python311\python.exe"

If Not fso.FileExists(PythonExe) Then
    PythonExe = "python.exe"
End If

Cmd = """" & PythonExe & """ -m app.service.runner"
WshShell.Run Cmd, 0, False
