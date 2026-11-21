Set fso = CreateObject("Scripting.FileSystemObject")
dirPath = fso.GetParentFolderName(WScript.ScriptFullName)
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = dirPath

venvGui = dirPath & "\.venv\Scripts\agy-petw.exe"
venvPyw = dirPath & "\.venv\Scripts\pythonw.exe"

If fso.FileExists(venvGui) Then
    sh.Run """" & venvGui & """", 0, False
ElseIf fso.FileExists(venvPyw) Then
    sh.Run """" & venvPyw & """ -m antigravity_whale_pet", 0, False
Else
    sh.Run "agy-petw", 0, False
End If
