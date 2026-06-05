Set shell = CreateObject("WScript.Shell")
Set fileSystem = CreateObject("Scripting.FileSystemObject")
scriptFolder = fileSystem.GetParentFolderName(WScript.ScriptFullName)
shell.Run """" & fileSystem.BuildPath(scriptFolder, "start-diary.bat") & """", 0, False
