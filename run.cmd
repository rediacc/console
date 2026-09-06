@echo off
rem run.cmd -- the cmd.exe entry point. It is a shim over run.ps1 and holds no logic.
rem
rem WHY IT DELEGATES INSTEAD OF CALLING wsl.exe ITSELF. Calling wsl.exe directly
rem from here would take four lines and would then be a SECOND launcher: the UNC
rem path translation, the distro pin and the exit-code propagation that run.ps1
rem documents would each have to exist twice, and the copy that is used less
rem often is the copy that rots. One implementation, two front doors.
rem
rem -ExecutionPolicy Bypass is scoped to this invocation and changes no machine
rem policy. Without it a default Windows install refuses to run an unsigned .ps1
rem from a checkout, and the failure reads as though the repository is broken.
rem
rem %* forwards every argument verbatim, and `exit /b %ERRORLEVEL%` propagates
rem the gate run's exit code for the same reason run.ps1 ends the way it does.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" %*
exit /b %ERRORLEVEL%
