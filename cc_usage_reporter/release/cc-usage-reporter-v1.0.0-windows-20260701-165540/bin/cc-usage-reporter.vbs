Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
baseDir = fso.GetParentFolderName(WScript.ScriptFullName)
cliPath = fso.BuildPath(baseDir, "cc-usage-reporter-cli.exe")
If Not fso.FileExists(cliPath) Then
  MsgBox "Missing file: " & cliPath, 16, "CC Usage Reporter"
  WScript.Quit 1
End If
shell.Run """" & cliPath & """ gui", 0, False
