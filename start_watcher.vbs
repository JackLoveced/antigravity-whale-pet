Set fso = CreateObject("Scripting.FileSystemObject")
dirPath = fso.GetParentFolderName(WScript.ScriptFullName)
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = dirPath

venvPyw = dirPath & "\.venv\Scripts\pythonw.exe"
assetsDir = dirPath & "\assets"

If fso.FileExists(venvPyw) Then
    sh.Run """" & venvPyw & """ -m antigravity_whale_pet watch --assets-dir """ & assetsDir & """", 0, False
Else
    sh.Run "pythonw -m antigravity_whale_pet watch", 0, False
End If
