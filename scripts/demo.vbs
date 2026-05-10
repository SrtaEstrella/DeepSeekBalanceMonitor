CreateObject("WScript.Shell").Run "pythonw """ & CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName) & "\..\main.py"" --demo", 0, False
