Set ws = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
ws.CurrentDirectory = here
ws.Run """" & here & "\wb2api.exe"" -config """ & here & "\config.json""", 0, False
