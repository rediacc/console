@echo off
rem win:check vscode suite: rdc vscode connect from the interactive desktop session, started by the /IT
rem scheduled task vscode.ps1 creates. Usage: vscode.cmd <machine> <config> <exit-file>
rem The PATH is the stock one read from the registry, not the SSH session's. The CLI output goes to
rem <exit-file>.log, and <exit-file> gets the single line exit=<code> only when the command has ended.
for /f "tokens=2,*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path ^| find "Path"') do set MPATH=%%b
for /f "tokens=2,*" %%a in ('reg query "HKCU\Environment" /v Path 2^>nul ^| find "Path"') do set UPATH=%%b
call set PATH=%MPATH%;%UPATH%;C:\rdc\renet
set REDIACC_CONFIG=%2
set REDIACC_NO_PROVISION=1
set CLAUDECODE=1
node C:\rdc\cli-bundle.cjs vscode connect %1 > %3.log 2>&1
echo exit=%ERRORLEVEL% > %3
