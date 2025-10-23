; Qingyuan Search Installer Script
; NSIS (Nullsoft Scriptable Install System) required

!define APPNAME "QingYuan"
!define COMPANYNAME "QingYuan"
!define DESCRIPTION "网络搜索工具"
!define VERSIONMAJOR 1
!define VERSIONMINOR 1
!define VERSIONBUILD 0
!define HELPURL "https://github.com/your-repo/qingyuan"
!define UPDATEURL "https://github.com/your-repo/qingyuan"
!define ABOUTURL "https://github.com/your-repo/qingyuan"
!define INSTALLSIZE 50000
!define INSTALLERNAME "QingYuan_Setup.exe"

RequestExecutionLevel admin
InstallDir "$PROGRAMFILES\${APPNAME}"
Name "${APPNAME}"
outFile "${INSTALLERNAME}"

!include LogicLib.nsh

page directory
page instfiles

!macro VerifyUserIsAdmin
UserInfo::GetAccountType
pop $0
${If} $0 != "admin"
    messageBox mb_iconstop "Administrator privileges required to install ${APPNAME}."
    setErrorLevel 740
    quit
${EndIf}
!macroend

function .onInit
    setShellVarContext all
    !insertmacro VerifyUserIsAdmin
functionEnd

section "install"
    setOutPath $INSTDIR
    
    ; Copy main program
    file "dist\*.exe"
    
    ; Copy config file
    file "sites_config.json"
    
    ; Copy static files
    file /r "public"
    
    ; Copy documentation
    file "README.txt"
    
    ; Copy utility scripts
    file "close.bat"
    
    ; No shortcuts needed
    
    ; Write uninstaller
    writeUninstaller "$INSTDIR\uninstall.exe"
    
    ; Write registry information
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayName" "${APPNAME}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "UninstallString" "$INSTDIR\uninstall.exe"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "InstallLocation" "$INSTDIR"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayIcon" "$INSTDIR\QingYuan.exe"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "Publisher" "${COMPANYNAME}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "HelpLink" "${HELPURL}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "URLUpdateInfo" "${UPDATEURL}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "URLInfoAbout" "${ABOUTURL}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayVersion" "${VERSIONMAJOR}.${VERSIONMINOR}.${VERSIONBUILD}"
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "VersionMajor" ${VERSIONMAJOR}
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "VersionMinor" ${VERSIONMINOR}
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "NoModify" 1
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "NoRepair" 1
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "EstimatedSize" ${INSTALLSIZE}
sectionEnd

section "uninstall"
    ; Stop the program before uninstalling
    ExecWait '"$INSTDIR\close.bat"'
    
    ; Delete files
    delete "$INSTDIR\*.exe"
    delete "$INSTDIR\sites_config.json"
    delete "$INSTDIR\README.txt"
    delete "$INSTDIR\close.bat"
    delete "$INSTDIR\uninstall.exe"
    rmDir /r "$INSTDIR\public"
    rmDir "$INSTDIR"
    
    ; No shortcuts to delete
    
    ; Delete registry information
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}"
sectionEnd
