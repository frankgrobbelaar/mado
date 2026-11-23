; A small installer that runs Mado's install hooks (hooks.nsh) around a pretend copy of a new
; engine, into a scratch folder: hooks-test.ps1 builds and runs it. Not part of Mado's installer.
; makensis /DHOOKS=<hooks.nsh> /DOUT=<exe> /DDIR=<install folder> [/DSTOP] hooks-test.nsi
; With /DEXPLORER it runs the uninstall hook instead, against a root of classes of its own
; (HKCU\Software\Mado hooks test\Classes), as an uninstall, or as an update with /DUPDATING.
Unicode true
RequestExecutionLevel user
SilentInstall silent
!include LogicLib.nsh
!include FileFunc.nsh
!ifdef EXPLORER
  !define MADO_CLASSES "Software\Mado hooks test\Classes"
!endif
!include "${HOOKS}"

Name "Mado install hooks test"
OutFile "${OUT}"
InstallDir "${DIR}"

!ifdef EXPLORER
  Var UpdateMode
  Var DeleteAppDataCheckboxState
!endif

Section Install
  SetOutPath $INSTDIR
  !ifdef EXPLORER
    StrCpy $DeleteAppDataCheckboxState 0 ; never Mado's data folder
    !ifdef UPDATING
      StrCpy $UpdateMode 1
    !else
      StrCpy $UpdateMode 0
    !endif
    !insertmacro NSIS_HOOK_POSTUNINSTALL
  !else
    !insertmacro NSIS_HOOK_PREINSTALL
    !ifdef STOP
      Abort "stopped on purpose"
    !endif
    CreateDirectory "$INSTDIR\engine\_internal\mado-0.3.0.dist-info"
    FileOpen $0 "$INSTDIR\engine\_internal\mado-0.3.0.dist-info\METADATA" w
    FileWrite $0 "Version: 0.3.0"
    FileClose $0
    FileOpen $0 "$INSTDIR\engine\new-engine.txt" w
    FileWrite $0 "new"
    FileClose $0
    !insertmacro NSIS_HOOK_POSTINSTALL
  !endif
SectionEnd
